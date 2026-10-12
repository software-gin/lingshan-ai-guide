"""
==============================================================
多模态大模型接口封装模块（通义千问 Qwen 系列）
支持：
- 文本对话（流式/非流式）
- 图片理解（Qwen3.5-Omni-Flash 多模态）
- 函数调用（Function Calling，用于 Agent 工具调度）
- 连接池管理（requests.Session）
- 自动重试（指数退避）
- 流式逐字文本推送

API文档参考：https://help.aliyun.com/zh/model-studio/qwen3-5-omni-flash
==============================================================
"""

import os
import sys
import json
import base64
import time
import random
import re
import threading
import requests
from typing import Optional, List, Dict, Any, Generator

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import (
    LLM_API_KEY, LLM_API_BASE, LLM_MODEL_NAME,
    LLM_VISION_MODEL, LLM_MAX_TOKENS, LLM_TEMPERATURE,
    UPLOAD_FOLDER,
    LLM_MAX_RETRIES, LLM_CONNECT_TIMEOUT, LLM_READ_TIMEOUT,
    LLM_CIRCUIT_BREAKER_THRESHOLD, LLM_CIRCUIT_BREAKER_RECOVERY,
    LLM_CONCURRENCY_LIMIT, LLM_TOKEN_BUDGET_WARN,
)


class LLMService:
    """
    通义千问大模型服务
    封装 Qwen3.5-Omni-Flash 多模态模型的文本/图片问答与函数调用功能
    支持流式输出、连接池复用、自动重试
    """

    def __init__(self):
        self.api_key = LLM_API_KEY
        self.api_base = LLM_API_BASE.rstrip("/")
        self.model_name = LLM_MODEL_NAME
        self.vision_model = LLM_VISION_MODEL
        self.max_tokens = LLM_MAX_TOKENS
        self.temperature = LLM_TEMPERATURE

        # 连接池：复用TCP连接，减少握手开销
        self._session = None
        self._init_session()

        # 可靠性：并发信号量（限制同时进行的 LLM 请求数，防止限流雪崩）
        self._semaphore = threading.Semaphore(max(1, LLM_CONCURRENCY_LIMIT))

        # 可靠性：熔断器（连续失败达阈值后快速失败，恢复期内放探测请求）
        self._cb_lock = threading.Lock()
        self._cb_failures = 0          # 连续失败计数
        self._cb_open_until = 0.0      # 熔断解除时间戳

        # 配额统计：累计 token 消耗（用于预算告警，不影响功能）
        self._token_lock = threading.Lock()
        self._total_tokens = 0
        self._warned_budget = False

        print(f"[LLM] 通义千问服务初始化完成，接口：{self.api_base}，模型：{self.model_name}")

    def _init_session(self):
        """初始化HTTP连接池"""
        self._session = requests.Session()
        # 连接池大小：最多保持10个连接
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=10,
            pool_maxsize=20,
            max_retries=0  # 我们自己控制重试
        )
        self._session.mount("https://", adapter)
        self._session.mount("http://", adapter)
        self._session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        })

    def _should_retry(self, status_code: int) -> bool:
        """判断是否应该重试"""
        return status_code in (429, 500, 502, 503, 504)

    def _circuit_breaker_allow(self) -> bool:
        """
        熔断器检查：返回 True 表示允许本次请求。
        - 失败数未达阈值：放行
        - 处于熔断期（open）：拒绝，除非恢复期已到（放一个探测请求）
        """
        with self._cb_lock:
            if self._cb_failures < LLM_CIRCUIT_BREAKER_THRESHOLD:
                return True
            now = time.time()
            if now < self._cb_open_until:
                return False
            # 恢复期到：重置失败计数，放一个探测请求
            self._cb_failures = 0
            self._cb_open_until = 0.0
            return True

    def _record_failure(self):
        """记录一次失败：连续失败数+1，达阈值则开启熔断"""
        with self._cb_lock:
            self._cb_failures += 1
            if self._cb_failures >= LLM_CIRCUIT_BREAKER_THRESHOLD:
                self._cb_open_until = time.time() + LLM_CIRCUIT_BREAKER_RECOVERY
                print(f"[LLM] 熔断器开启：连续失败 {self._cb_failures} 次，"
                      f"{LLM_CIRCUIT_BREAKER_RECOVERY}s 后恢复探测")

    def _record_success(self):
        """记录一次成功：清零连续失败计数"""
        with self._cb_lock:
            if self._cb_failures > 0:
                self._cb_failures = 0
                self._cb_open_until = 0.0

    def _record_tokens(self, usage: Optional[Dict[str, Any]]):
        """累计 token 消耗并按阈值告警（仅统计，不阻断）"""
        if not usage or not isinstance(usage, dict):
            return
        total = usage.get("total_tokens") or 0
        if not total:
            return
        with self._token_lock:
            self._total_tokens += total
            if (LLM_TOKEN_BUDGET_WARN and not self._warned_budget
                    and self._total_tokens >= LLM_TOKEN_BUDGET_WARN):
                self._warned_budget = True
                print(f"[LLM] ⚠ 累计 token 消耗 {self._total_tokens} 已达预算阈值 "
                      f"{LLM_TOKEN_BUDGET_WARN}，请注意配额消耗")

    def get_token_usage(self) -> int:
        """获取累计 token 消耗（用于监控）"""
        with self._token_lock:
            return self._total_tokens

    def _do_request(self, payload: dict, stream: bool = False, max_retries: int = None) -> Optional[requests.Response]:
        """
        执行API请求（含指数退避重试 + 熔断器 + 并发信号量）

        参数：
            payload: 请求体
            stream: 是否流式
            max_retries: 最大重试次数（None 时使用配置 LLM_MAX_RETRIES）

        返回：
            Response对象或None（熔断/重试耗尽时返回None，由调用方降级）
        """
        if max_retries is None:
            max_retries = LLM_MAX_RETRIES

        # 熔断器：熔断期内快速失败，不消耗请求与 quota
        if not self._circuit_breaker_allow():
            print(f"[LLM] 熔断器生效，跳过本次请求（{LLM_CIRCUIT_BREAKER_RECOVERY}s 后恢复）")
            return None

        url = f"{self.api_base}/chat/completions"
        last_error = None

        for attempt in range(max_retries):
            # 并发信号量：同时进行的请求数受限，防止模型侧限流雪崩
            acquired = self._semaphore.acquire(timeout=LLM_CONNECT_TIMEOUT + 5)
            if not acquired:
                print("[LLM] 并发信号量等待超时，放弃本次请求")
                self._record_failure()
                return None
            try:
                response = self._session.post(
                    url,
                    json=payload,
                    stream=stream,
                    timeout=(LLM_CONNECT_TIMEOUT, LLM_READ_TIMEOUT)
                )

                if response.status_code == 200:
                    self._record_success()
                    return response

                if self._should_retry(response.status_code) and attempt < max_retries - 1:
                    wait = (2 ** attempt) + random.uniform(0, 1)
                    print(f"[LLM] 请求返回{response.status_code}，{wait:.1f}s后重试（第{attempt+1}次）")
                    time.sleep(wait)
                    continue

                print(f"[LLM] API请求失败：HTTP {response.status_code}，{response.text[:200]}")
                self._record_failure()
                return None

            except requests.exceptions.Timeout as e:
                last_error = e
                if attempt < max_retries - 1:
                    wait = (2 ** attempt) + random.uniform(0, 1)
                    print(f"[LLM] 请求超时，{wait:.1f}s后重试")
                    time.sleep(wait)
                else:
                    print(f"[LLM] 请求超时，已达最大重试次数")
            except requests.exceptions.ConnectionError as e:
                last_error = e
                if attempt < max_retries - 1:
                    wait = (2 ** attempt) + random.uniform(0, 1)
                    print(f"[LLM] 连接失败，{wait:.1f}s后重试")
                    time.sleep(wait)
                else:
                    print(f"[LLM] 连接失败，已达最大重试次数")
            except Exception as e:
                last_error = e
                print(f"[LLM] 请求异常：{e}")
                break
            finally:
                self._semaphore.release()

        print(f"[LLM] 请求最终失败：{last_error}")
        self._record_failure()
        return None

    def update_config(self, api_key: str = None, api_base: str = None,
                      model_name: str = None, vision_model: str = None):
        """运行时更新配置"""
        changed = False
        if api_key:
            self.api_key = api_key
            changed = True
        if api_base:
            self.api_base = api_base.rstrip("/")
            changed = True
        if model_name:
            self.model_name = model_name
            changed = True
        if vision_model:
            self.vision_model = vision_model
            changed = True
        if changed:
            # 重建session（因为API key变了）
            self._init_session()
            print(f"[LLM] 配置已更新：API={self.api_base}，模型={self.model_name}")

    def get_config(self) -> dict:
        return {
            "api_key": self.api_key,
            "api_base": self.api_base,
            "model_name": self.model_name,
            "vision_model": self.vision_model
        }

    def is_configured(self) -> bool:
        """检查API密钥是否有效配置"""
        return bool(self.api_key) and "your-api-key" not in self.api_key

    def chat(self, messages: List[Dict[str, str]], stream: bool = False) -> str:
        """
        文本对话接口（非流式）

        参数：
            messages: 消息列表
            stream: 是否流式输出（仅当False时返回完整文本）

        返回：
            AI回复文本
        """
        if not self.is_configured():
            return self._mock_chat(messages)

        payload = {
            "model": self.model_name,
            "messages": messages,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "stream": False
        }

        response = self._do_request(payload, stream=False)
        if not response:
            return self._mock_chat(messages)

        try:
            data = response.json()
            self._record_tokens(data.get("usage"))
            if not data.get("choices"):
                return self._mock_chat(messages)
            return data["choices"][0]["message"]["content"]
        except (KeyError, json.JSONDecodeError) as e:
            print(f"[LLM] 解析响应失败：{e}")
            return self._mock_chat(messages)

    def chat_stream(self, messages: List[Dict[str, str]]) -> Generator[str, None, None]:
        """
        流式文本对话

        参数：
            messages: 消息列表

        生成器：
            yield 逐字/逐段文本片段
        """
        if not self.is_configured():
            yield self._mock_chat(messages)
            return

        payload = {
            "model": self.model_name,
            "messages": messages,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "stream": True
        }

        response = self._do_request(payload, stream=True)
        if not response:
            yield self._mock_chat(messages)
            return

        try:
            has_content = False
            for line in response.iter_lines():
                if not line:
                    continue
                line = line.decode("utf-8")
                if line.startswith("data: "):
                    data_str = line[6:].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        data = json.loads(data_str)
                        self._record_tokens(data.get("usage"))
                        if not data.get("choices"):
                            continue
                        delta = data["choices"][0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            has_content = True
                            yield content
                    except (json.JSONDecodeError, KeyError):
                        continue

            # 流式全程未产生任何内容 → API 格式不兼容或模型不支持流式
            # 降级为 非流式 调用
            if not has_content:
                print(f"[LLM] 流式未产生内容，降级为非流式调用")
                result = self.chat(messages)
                if result:
                    yield result
        except Exception as e:
            print(f"[LLM] 流式读取失败：{e}")
            # 流式读取失败时，降级为非流式调用
            print(f"[LLM] 降级为非流式调用")
            result = self.chat(messages)
            if result:
                yield result

    def chat_tool_call(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]],
                       tool_choice: str = "auto") -> Optional[Dict[str, Any]]:
        """
        单步函数调用（Function Calling）：让模型决定是否调用工具。

        参数：
            messages: 消息列表
            tools: 工具定义列表（OpenAI 格式）
            tool_choice: 工具选择策略（auto/none/具体函数名）

        返回：
            聚合后的首个工具调用 {id, name, arguments(dict)}；
            未触发任何工具时返回 None。
        说明：
            Qwen-Omni 系列的函数调用要求 stream=True，且工具信息聚合遵循
            OpenAI 流式协议：首个 chunk 携带 id，后续 chunk 拼接 arguments。
        """
        if not self.is_configured():
            return None

        payload = {
            "model": self.model_name,
            "messages": messages,
            "tools": tools,
            "tool_choice": tool_choice,
            "stream": True,  # Qwen-Omni 函数调用强制要求流式
        }

        response = self._do_request(payload, stream=True)
        if not response:
            return None

        tool_call = {"id": "", "name": "", "arguments": ""}
        try:
            for line in response.iter_lines():
                if not line:
                    continue
                line = line.decode("utf-8")
                if line.startswith("data: "):
                    data_str = line[6:].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        data = json.loads(data_str)
                    except (json.JSONDecodeError, ValueError):
                        continue
                    choices = data.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta") or {}
                    for t in (delta.get("tool_calls") or []):
                        if t.get("id"):
                            tool_call["id"] = t["id"]
                        fn = t.get("function") or {}
                        if fn.get("name"):
                            tool_call["name"] = fn["name"]
                        tool_call["arguments"] += fn.get("arguments") or ""
        except Exception as e:
            print(f"[LLM] 函数调用流式解析失败：{e}")
            return None

        if not tool_call["name"]:
            return None

        try:
            arguments = json.loads(tool_call["arguments"]) if tool_call["arguments"].strip() else {}
        except (json.JSONDecodeError, ValueError):
            arguments = {}

        return {"id": tool_call["id"], "name": tool_call["name"], "arguments": arguments}

    def chat_with_tools_stream(self, messages: List[Dict[str, Any]],
                               tools: List[Dict[str, Any]],
                               tool_choice: str = "auto") -> Generator[Dict[str, Any], None, None]:
        """
        带工具的流式对话：同时产出文本增量与聚合后的工具调用事件（ReAct 核心方法）。

        事件格式：
            {"type": "content", "text": "..."}       文本增量（可多次）
            {"type": "tool_calls", "calls": [...]}   聚合完成的工具调用（流结束时最多一次）

        说明：
            Qwen-Omni 函数调用要求 stream=True；tool_calls 分片按 OpenAI 流式协议聚合。
        """
        if not self.is_configured():
            return

        payload = {
            "model": self.model_name,
            "messages": messages,
            "tools": tools,
            "tool_choice": tool_choice,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "stream": True,
        }

        response = self._do_request(payload, stream=True)
        if not response:
            return

        tc_buffer = {}   # index -> {id, name, arguments}
        order = []
        try:
            for line in response.iter_lines():
                if not line:
                    continue
                line = line.decode("utf-8")
                if line.startswith("data: "):
                    data_str = line[6:].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        data = json.loads(data_str)
                    except (json.JSONDecodeError, ValueError):
                        continue
                    self._record_tokens(data.get("usage"))
                    choices = data.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta") or {}
                    content = delta.get("content")
                    if content:
                        yield {"type": "content", "text": content}
                    for t in (delta.get("tool_calls") or []):
                        idx = t.get("index", 0)
                        if idx not in tc_buffer:
                            tc_buffer[idx] = {"id": "", "name": "", "arguments": ""}
                            order.append(idx)
                        if t.get("id"):
                            tc_buffer[idx]["id"] = t["id"]
                        fn = t.get("function") or {}
                        if fn.get("name"):
                            tc_buffer[idx]["name"] = fn["name"]
                        tc_buffer[idx]["arguments"] += fn.get("arguments") or ""
        except Exception as e:
            print(f"[LLM] 工具流式读取失败：{e}")

        calls = []
        for idx in order:
            b = tc_buffer[idx]
            if not b["name"]:
                continue
            try:
                args = json.loads(b["arguments"]) if b["arguments"].strip() else {}
            except (json.JSONDecodeError, ValueError):
                args = {}
            calls.append({"id": b["id"] or f"call_{idx}", "name": b["name"], "arguments": args})
        if calls:
            yield {"type": "tool_calls", "calls": calls}

    def chat_with_structured_answer(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        """调用大模型，返回带路线意图的结构化回答"""
        if not self.is_configured():
            return self._mock_structured_chat(messages)

        payload = {
            "model": self.model_name,
            "messages": messages,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "stream": False
        }

        response = self._do_request(payload, stream=False)
        if not response:
            return self._mock_structured_chat(messages)

        try:
            data = response.json()
            if not data.get("choices"):
                return self._mock_structured_chat(messages)
            content = data["choices"][0]["message"]["content"]
            return self.extract_route_info(messages[-1].get("content", ""), content)
        except (KeyError, json.JSONDecodeError) as e:
            print(f"[LLM] 结构化响应解析失败：{e}")
            return self._mock_structured_chat(messages)

    def extract_route_info(self, question: str, llm_response: str) -> Dict[str, Any]:
        """从模型输出中抽取回答与路线信息"""
        question_text = question or ""
        response_text = llm_response or ""

        candidate = response_text.strip()
        parsed = None

        try:
            if candidate.startswith("{"):
                parsed = json.loads(candidate)
        except json.JSONDecodeError:
            pass

        if parsed is None:
            match = re.search(r"\{.*\}", candidate, re.S)
            if match:
                try:
                    parsed = json.loads(match.group(0))
                except json.JSONDecodeError:
                    parsed = None

        if isinstance(parsed, dict):
            answer = parsed.get("answer") or parsed.get("text") or response_text
            if isinstance(answer, str):
                answer = answer.replace("{", "").replace("}", "")
                answer = re.sub(r'"(answer|route_intent|route_data|origin|destination|waypoints|mode|summary)"\s*:\s*', '', answer)
                answer = re.sub(r'\s+', ' ', answer).strip()
            route_intent = bool(parsed.get("route_intent")) or self._looks_like_route(question_text, answer)
            route_data = parsed.get("route_data") or (self._build_route_data(question_text, answer) if route_intent else None)
            return {
                "answer": answer,
                "route_intent": route_intent,
                "route_data": route_data,
            }

        route_intent = self._looks_like_route(question_text, response_text)
        route_data = self._build_route_data(question_text, response_text) if route_intent else None
        return {
            "answer": response_text,
            "route_intent": route_intent,
            "route_data": route_data,
        }

    def _looks_like_route(self, question: str, answer: str) -> bool:
        text = f"{question}\n{answer}".lower()
        route_keywords = [
            "怎么去", "怎么走", "怎么到", "路线", "推荐路线", "前往", "出发", "走到", "导航", "地图",
            "游览路线", "怎么玩", "游玩路线", "路线推荐", "怎么逛", "如何游览",
            "路线规划", "行程", "攻略", "怎么走最"
        ]
        return any(keyword in text for keyword in route_keywords)

    def _build_route_data(self, question: str, answer: str) -> Dict[str, Any]:
        """
        从问题与回答中提取路线数据（优先从动态路线库匹配）
        """
        text = f"{question}\n{answer}".lower()

        # 尝试从动态路线库匹配
        try:
            from services.route_service import get_all_routes, get_default_route

            all_routes = get_all_routes()
            matched_route = None
            best_score = 0

            for route in all_routes:
                score = 0
                if route.get("style") and route["style"] in text:
                    score += 5
                for tag in route.get("tags", []):
                    if tag in text:
                        score += 3
                for spot in route.get("spots", []):
                    if spot.get("name", "") in text:
                        score += 2
                if route.get("title", "") in text:
                    score += 4

                if score > best_score:
                    best_score = score
                    matched_route = route

            selected = matched_route or get_default_route() or (all_routes[0] if all_routes else None)

            if selected and selected.get("spots"):
                spots = selected["spots"]
                return {
                    "origin": spots[0]["name"],
                    "destination": spots[-1]["name"],
                    "waypoints": [s["name"] for s in spots[1:-1]] if len(spots) > 2 else [],
                    "mode": "walk",
                    "summary": f"{selected['title']}：{selected.get('description', '')[:50]}",
                    "route_name": selected.get("title"),
                    "duration": selected.get("duration"),
                    "tips": selected.get("tips", ""),
                    "spots_count": len(spots)
                }
        except Exception as e:
            print(f"[Route] 动态路线匹配失败: {e}")

        # 降级：基于关键词的硬编码匹配
        if "大佛" in text:
            destination = "灵山大佛"
            waypoints = ["佛足坛", "九龙灌浴"]
        elif "梵宫" in text:
            destination = "梵宫"
            waypoints = ["佛足坛", "九龙灌浴"]
        elif "拈花湾" in text:
            destination = "拈花湾"
            waypoints = ["梵宫", "灵山大佛"]
        elif "路线" in text or "推荐路线" in text:
            destination = "灵山大佛"
            waypoints = ["佛足坛", "九龙灌浴"]
        else:
            destination = "灵山大佛"
            waypoints = ["佛足坛", "九龙灌浴"]

        return {
            "origin": "南门",
            "destination": destination,
            "waypoints": waypoints,
            "mode": "walk",
            "summary": "适合步行游览，沿途可欣赏景区核心景点"
        }

    def _supports_base64_image(self) -> bool:
        """
        检测当前 API 是否支持 base64 图片直传
        Qwen 支持 image_url 格式（URL 或 base64 data URL）
        """
        # 所有主流多模态 API 均支持 base64 data URL 格式
        return True

    def chat_with_images_stream(self, text: str, image_urls: list) -> Generator[str, None, None]:
        """
        多图图文对话流式接口（Generator 逐段 yield 文本）

        参数：
            text: 用户文本提问
            image_urls: 图片 URL 列表（支持绝对路径或相对路径）

        生成器：
            yield 逐字/逐段文本片段
        """
        if not self.is_configured():
            yield self._mock_chat([{"role": "user", "content": text + "(含图片)"}])
            return

        if not image_urls:
            # 无图片，降级为纯文本流式
            yield from self.chat_stream([{"role": "user", "content": text}])
            return

        # 构建多模态内容数组
        content_blocks = [{"type": "text", "text": text}]
        image_count = 0

        for img_url in image_urls:
            try:
                img_path = img_url
                if img_url.startswith("/uploads/"):
                    img_path = os.path.join(UPLOAD_FOLDER, img_url.lstrip("/uploads/"))
                elif img_url.startswith("/"):
                    img_path = os.path.join(UPLOAD_FOLDER, img_url.lstrip("/"))

                if os.path.isfile(img_path):
                    with open(img_path, "rb") as f:
                        image_bytes = f.read()
                    ext = os.path.splitext(img_path)[1].lower() or ".jpg"
                    mime_types = {
                        ".png": "image/png", ".jpg": "image/jpeg",
                        ".jpeg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp"
                    }
                    mime_type = mime_types.get(ext, "image/jpeg")
                    image_base64 = base64.b64encode(image_bytes).decode("utf-8")
                    content_blocks.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime_type};base64,{image_base64}"}
                    })
                    image_count += 1
                    print(f"[LLM] 图片已加载: {img_path} ({image_count}/{len(image_urls)})")
                else:
                    content_blocks.append({
                        "type": "image_url",
                        "image_url": {"url": img_url}
                    })
                    image_count += 1
            except Exception as e:
                print(f"[LLM] 图片处理失败: {e}")
                continue

        if image_count == 0:
            print("[LLM] 所有图片加载失败，降级为纯文本流式提问")
            yield from self.chat_stream([{"role": "user", "content": text}])
            return

        payload = {
            "model": self.vision_model,
            "messages": [{"role": "user", "content": content_blocks}],
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "stream": True
        }

        response = self._do_request(payload, stream=True)
        if not response:
            yield self._mock_chat([{"role": "user", "content": text + "(含图片)"}])
            return

        try:
            has_content = False
            for line in response.iter_lines():
                if not line:
                    continue
                line = line.decode("utf-8")
                if line.startswith("data: "):
                    data_str = line[6:].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        data = json.loads(data_str)
                        if not data.get("choices"):
                            continue
                        delta = data["choices"][0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            has_content = True
                            yield content
                    except (json.JSONDecodeError, KeyError):
                        continue

            # 流式未产生内容 → 降级非流式
            if not has_content:
                print("[LLM] 图文流式未产生内容，降级为非流式调用")
                result = self.chat_with_images(text, image_urls, stream=False)
                if result:
                    yield result
        except Exception as e:
            print(f"[LLM] 图文流式读取失败：{e}")
            result = self.chat_with_images(text, image_urls, stream=False)
            if result:
                yield result

    def chat_with_image_stream(self, text: str, image_data: bytes,
                                image_name: str = "image.jpg") -> Generator[str, None, None]:
        """
        单图图文对话流式接口（兼容旧版，Generator 逐段 yield 文本）

        参数：
            text: 用户文本提问
            image_data: 图片二进制数据
            image_name: 图片文件名

        生成器：
            yield 逐字/逐段文本片段
        """
        if not self.is_configured():
            yield self._mock_chat([{"role": "user", "content": text + "(含图片)"}])
            return

        try:
            image_base64 = base64.b64encode(image_data).decode("utf-8")
            ext = os.path.splitext(image_name)[1].lower()
            mime_types = {
                ".png": "image/png", ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp"
            }
            mime_type = mime_types.get(ext, "image/jpeg")

            payload = {
                "model": self.vision_model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": text},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:{mime_type};base64,{image_base64}"}
                            }
                        ]
                    }
                ],
                "max_tokens": self.max_tokens,
                "temperature": self.temperature,
                "stream": True
            }

            response = self._do_request(payload, stream=True)
            if not response:
                yield self._mock_chat([{"role": "user", "content": text + "(含图片)"}])
                return

            try:
                has_content = False
                for line in response.iter_lines():
                    if not line:
                        continue
                    line = line.decode("utf-8")
                    if line.startswith("data: "):
                        data_str = line[6:].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            data = json.loads(data_str)
                            if not data.get("choices"):
                                continue
                            delta = data["choices"][0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                has_content = True
                                yield content
                        except (json.JSONDecodeError, KeyError):
                            continue

                if not has_content:
                    print("[LLM] 单图流式未产生内容，降级为非流式调用")
                    result = self.chat_with_image(text, image_data, image_name, stream=False)
                    if result:
                        yield result
            except Exception as e:
                print(f"[LLM] 单图流式读取失败：{e}")
                result = self.chat_with_image(text, image_data, image_name, stream=False)
                if result:
                    yield result

        except Exception as e:
            print(f"[LLM] 图文调用失败：{e}")
            yield self._mock_chat([{"role": "user", "content": text + "(含图片)"}])

    def chat_with_images(self, text: str, image_urls: list, stream: bool = False) -> str:
        """
        多图图文对话接口（支持多张图片）

        参数：
            text: 用户文本提问
            image_urls: 图片 URL 列表（支持绝对路径或相对路径）
            stream: 是否流式

        返回：
            AI回复文本
        """
        if not self.is_configured():
            return self._mock_chat([{"role": "user", "content": text + "(含图片)"}])

        if not image_urls:
            # 无图片，降级为纯文本
            return self.chat([{"role": "user", "content": text}])

        # 构建多模态内容数组
        content_blocks = [{"type": "text", "text": text}]
        image_count = 0

        for img_url in image_urls:
            try:
                # 将相对路径或本地文件路径转为 base64 data URL
                img_path = img_url
                # 如果是 /uploads/xxx 格式，转为绝对文件路径
                if img_url.startswith("/uploads/"):
                    img_path = os.path.join(UPLOAD_FOLDER, img_url.lstrip("/uploads/"))
                elif img_url.startswith("/"):
                    # 其他以 / 开头的路径，尝试从 UPLOAD_FOLDER 解析
                    img_path = os.path.join(UPLOAD_FOLDER, img_url.lstrip("/"))

                # 如果文件存在，读取并转为 base64
                if os.path.isfile(img_path):
                    with open(img_path, "rb") as f:
                        image_bytes = f.read()
                    ext = os.path.splitext(img_path)[1].lower() or ".jpg"
                    mime_types = {
                        ".png": "image/png", ".jpg": "image/jpeg",
                        ".jpeg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp"
                    }
                    mime_type = mime_types.get(ext, "image/jpeg")
                    image_base64 = base64.b64encode(image_bytes).decode("utf-8")
                    content_blocks.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime_type};base64,{image_base64}"}
                    })
                    image_count += 1
                    print(f"[LLM] 图片已加载: {img_path} ({image_count}/{len(image_urls)})")
                else:
                    # 文件不存在，跳过（可能是公开 URL，直接传递）
                    content_blocks.append({
                        "type": "image_url",
                        "image_url": {"url": img_url}
                    })
                    image_count += 1
            except Exception as e:
                print(f"[LLM] 图片处理失败: {e}")
                continue

        if image_count == 0:
            # 所有图片都加载失败，降级为纯文本
            print("[LLM] 所有图片加载失败，降级为纯文本提问")
            return self.chat([{"role": "user", "content": text}])

        # 构建请求
        payload = {
            "model": self.vision_model,
            "messages": [{"role": "user", "content": content_blocks}],
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "stream": stream
        }

        response = self._do_request(payload, stream=stream)
        if not response:
            return self._mock_chat([{"role": "user", "content": text + "(含图片)"}])

        if stream:
            parts = []
            for line in response.iter_lines():
                if not line:
                    continue
                line = line.decode("utf-8")
                if line.startswith("data: "):
                    ds = line[6:].strip()
                    if ds == "[DONE]":
                        break
                    try:
                        d = json.loads(ds)
                        if not d.get("choices"):
                            continue
                        c = d["choices"][0].get("delta", {}).get("content", "")
                        if c:
                            parts.append(c)
                    except (json.JSONDecodeError, KeyError):
                        continue
            return "".join(parts)
        else:
            data = response.json()
            if not data.get("choices"):
                return self._mock_chat([{"role": "user", "content": text + "(含图片)"}])
            return data["choices"][0]["message"]["content"]

    def chat_with_image(self, text: str, image_data: bytes,
                        image_name: str = "image.jpg", stream: bool = False) -> str:
        """
        图文对话接口（兼容旧版单图 base64）

        参数：
            text: 用户文本提问
            image_data: 图片二进制数据
            image_name: 图片文件名
            stream: 是否流式

        返回：
            AI回复文本
        """
        if not self.is_configured():
            return self._mock_chat([{"role": "user", "content": text + "(含图片)"}])

        try:
            image_base64 = base64.b64encode(image_data).decode("utf-8")
            ext = os.path.splitext(image_name)[1].lower()
            mime_types = {
                ".png": "image/png", ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp"
            }
            mime_type = mime_types.get(ext, "image/jpeg")

            payload = {
                "model": self.vision_model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": text},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{mime_type};base64,{image_base64}"
                                }
                            }
                        ]
                    }
                ],
                "max_tokens": self.max_tokens,
                "temperature": self.temperature,
                "stream": stream
            }

            response = self._do_request(payload, stream=stream)
            if not response:
                return self._mock_chat([{"role": "user", "content": text + "(含图片)"}])

            if stream:
                parts = []
                for line in response.iter_lines():
                    if not line:
                        continue
                    line = line.decode("utf-8")
                    if line.startswith("data: "):
                        ds = line[6:].strip()
                        if ds == "[DONE]":
                            break
                        try:
                            d = json.loads(ds)
                            if not d.get("choices"):
                                continue
                            c = d["choices"][0].get("delta", {}).get("content", "")
                            if c:
                                parts.append(c)
                        except (json.JSONDecodeError, KeyError):
                            continue
                return "".join(parts)
            else:
                data = response.json()
                if not data.get("choices"):
                    return self._mock_chat([{"role": "user", "content": text + "(含图片)"}])
                return data["choices"][0]["message"]["content"]

        except Exception as e:
            print(f"[LLM] 图文调用失败：{e}")
            return self._mock_chat([{"role": "user", "content": text + "(含图片)"}])

    def _mock_structured_chat(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        """模拟结构化回复（智谱AI不可用时的降级方案）"""
        answer = self._mock_chat(messages)
        user_msg = " ".join(
            msg.get("content", "") for msg in messages if msg["role"] == "user"
        )
        route_intent = self._looks_like_route(user_msg, answer)
        return {
            "answer": answer,
            "route_intent": route_intent,
            "route_data": self._build_route_data(user_msg, answer) if route_intent else None,
        }

    def _mock_chat(self, messages: List[Dict[str, str]]) -> str:
        """模拟回复（智谱AI不可用时的降级方案）"""
        user_msg = " ".join(
            msg.get("content", "") for msg in messages if msg["role"] == "user"
        )

        try:
            from services.route_service import get_all_routes
            db_routes = get_all_routes()
            if db_routes:
                lines = [f"灵山胜境为您推荐以下{len(db_routes)}条特色游览路线："]
                for r in db_routes[:5]:
                    spots_names = "→".join([s["name"] for s in r.get("spots", [])])
                    lines.append(f"{r['id']}. {r['title']}（{r.get('duration', '')}）：{spots_names}")
                route_reply = "\n".join(lines)
            else:
                route_reply = "灵山胜境为您推荐三条特色游览路线：\n1. 文化朝圣路线（3小时精华游）：南门→佛足坛→九龙灌浴→祥符禅寺→灵山大佛→梵宫→五印坛城\n2. 自然风光路线（5小时全景游）：南门→佛足坛→九龙灌浴→菩提大道→灵山大佛→曼飞龙塔→灵山精舍→梵宫广场\n3. 亲子家庭路线（4小时轻松游）：南门→九龙灌浴→佛手广场→百子戏弥勒→梵宫→五印坛城"
        except Exception:
            route_reply = "灵山胜境为您推荐三条特色游览路线：\n1. 文化朝圣路线（3小时精华游）：南门→佛足坛→九龙灌浴→祥符禅寺→灵山大佛→梵宫→五印坛城\n2. 自然风光路线（5小时全景游）：南门→佛足坛→九龙灌浴→菩提大道→灵山大佛→曼飞龙塔→灵山精舍→梵宫广场\n3. 亲子家庭路线（4小时轻松游）：南门→九龙灌浴→佛手广场→百子戏弥勒→梵宫→五印坛城"

        replies = {
            "门票": "灵山胜境景区成人门票价格为210元/人，拈花湾小镇门票为120元/人。景区开放时间：8:00-17:00。建议提前在官方小程序或携程等平台预约购票，可享优惠。",
            "大佛": "灵山大佛高达88米，是世界上最高的青铜释迦牟尼佛像之一。大佛位于灵山之巅，面向太湖，气势恢宏。登顶大佛可以俯瞰整个太湖风光，还可以体验'抱佛脚'祈福习俗。",
            "梵宫": "灵山梵宫是灵山胜境的核心建筑之一，建筑风格融合了佛教文化与现代艺术。内部有精美的壁画、雕塑、穹顶天象图等艺术作品，还有《吉祥颂》大型演出。",
            "九龙灌浴": "九龙灌浴是灵山胜境每日定时上演的经典水景表演，通过音乐、喷泉、水幕等现代科技手段，生动展现释迦牟尼诞生时'九龙吐水'的佛教传说故事。",
            "路线": route_reply,
            "交通": "灵山胜境位于无锡市滨湖区马山镇，可乘坐无锡地铁至梅园开原寺站，转乘公交88路或89路直达。自驾可通过沪宁高速、锡宜高速到达，景区设有大型停车场。",
            "住宿": "景区内推荐灵山精舍（禅意酒店，含素斋与早课体验），周边马山镇有多家酒店民宿可选，价格从几百元到上千元不等。",
            "素斋": "灵山梵宫提供素斋自助餐（50元/位），景区内还有素面套餐（35元/位），清淡雅致，适合体验佛门饮食文化。",
            "表演": "九龙灌浴每日4-5场表演，《吉祥颂》演出时间为10:35、11:30、14:00、16:00（以景区公告为准），时长约20分钟。",
            "拈花湾": "拈花湾禅意小镇以'禅意生活'为主题，有香月花街、妙音台、梵天花海等景点，适合休闲漫步、体验禅意文化。",
        }
        for keyword, reply in replies.items():
            if keyword in user_msg:
                return reply
        return "您好！我是灵山胜境AI数字人导游。我可以为您介绍灵山胜境的景点信息、门票价格、游览路线、交通方式、餐饮住宿等。请告诉我您想了解什么？"


# ======================== 全局单例 ========================
_llm_service = None


def get_llm_service() -> LLMService:
    """获取大模型服务单例"""
    global _llm_service
    if _llm_service is None:
        _llm_service = LLMService()
    return _llm_service