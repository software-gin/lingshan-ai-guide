"""
==============================================================
两级评测脚本（Agent 评测体系 v1）
==============================================================
评测分组：
1. rag  —— RAG 检索质量：search_knowledge(top5) 是否命中标注关键词
          指标：检索命中率（hit@5）
2. agent —— Agent 工具调用决策：ReAct 首轮是否按期望调用工具（含参数关键词检查）
          指标：工具调用准确率
3. direct —— 直答判断：寒暄/闲聊类问题不触发任何工具
          指标：直答准确率

用法（在 backend 目录下）：
    python -m evaluation.run_eval --group rag --n 10     # 抽样评测
    python -m evaluation.run_eval --group agent          # 全量
    python -m evaluation.run_eval --group all            # 全部

输出：
    终端汇总指标 + 失败明细；明细 JSON 存入 evaluation/results/

注意：评测会真实调用 LLM 与向量库（消耗 quota）；
     "回答文本正确率"属人工评测项，不在本脚本自动判定范围。
==============================================================
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND_ROOT = os.path.dirname(HERE)
sys.path.insert(0, BACKEND_ROOT)

DATASET_PATH = os.path.join(HERE, "eval_dataset.json")
RESULTS_DIR = os.path.join(HERE, "results")


def load_dataset() -> dict:
    with open(DATASET_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


# ======================== 1. RAG 检索评测 ========================

def eval_rag(cases, n=None):
    from app import create_app
    app = create_app()
    results = []
    with app.app_context():
        from services.rag_service import get_knowledge_processor
        proc = get_knowledge_processor()
        cases = cases if n is None else cases[:n]
        for c in cases:
            t0 = time.time()
            try:
                hits_docs = proc.search_knowledge(c["query"], top_k=5)
            except Exception as e:
                results.append({**c, "hit": False, "error": str(e)[:200], "latency": round(time.time() - t0, 2)})
                continue
            # 检索返回字段为 {text, metadata, ...}（KnowledgeVectorDB.search）
            joined = " ".join(str(d.get("text") or d.get("content") or "") for d in hits_docs)
            hit = any(kw in joined for kw in c["expect_keywords"])
            top1_meta = (hits_docs[0].get("metadata") or {}) if hits_docs else {}
            results.append({
                **c,
                "hit": hit,
                "latency": round(time.time() - t0, 2),
                "top1_title": str(top1_meta.get("title") or top1_meta.get("filename") or "")[:40],
                "top1_category": top1_meta.get("category", ""),
                "preview": joined[:150],
            })
            print(f"[RAG] {c['id']} {'PASS' if hit else 'FAIL'} {round(time.time()-t0,2)}s {c['query'][:30]}")
    return results


# ======================== 2. Agent 工具调用评测 ========================

def _first_round_tool_calls(query: str):
    """跑 Orchestrator 第一轮（严格两级：只挂子 Agent 工具），返回 (tool_calls, 文本增量)"""
    from agents.orchestrator import ORCHESTRATOR_PROMPT
    from agents.registry import get_orchestrator_tools
    from services.llm_service import get_llm_service

    llm = get_llm_service()
    messages = [{"role": "system", "content": ORCHESTRATOR_PROMPT}, {"role": "user", "content": query}]
    calls, text = [], []
    for event in llm.chat_with_tools_stream(messages, get_orchestrator_tools()):
        if event["type"] == "content":
            text.append(event["text"])
        elif event["type"] == "tool_calls":
            calls = event["calls"]
    return calls, "".join(text)


# 领域工具 → 子 Agent 映射（评测口径：Orchestrator 首轮应派发的子 Agent）
TOOL_TO_AGENT = {
    "search_knowledge": "consult_retrieval_specialist",
    "get_route_recommendation": "consult_trip_specialist",
    "get_spot_info": "consult_trip_specialist",
}


def eval_agent(cases, n=None):
    from app import create_app
    app = create_app()
    results = []
    cases = cases if n is None else cases[:n]
    with app.app_context():
        for c in cases:
            t0 = time.time()
            try:
                calls, _ = _first_round_tool_calls(c["query"])
            except Exception as e:
                results.append({**c, "pass": False, "error": str(e)[:200], "latency": round(time.time() - t0, 2)})
                continue
            names = [call.get("name") for call in calls]
            # 评测口径：领域工具名映射到 Orchestrator 首轮应派发的子 Agent
            expect_agent = c.get("expect_agent") or TOOL_TO_AGENT.get(c.get("expect_tool"), c.get("expect_tool"))
            ok_tool = expect_agent in names
            # 参数关键词检查（宽松：任一调用的参数 JSON 中包含关键词即可）
            ok_args = True
            if c.get("args_keywords"):
                args_blob = " ".join(json.dumps(call.get("arguments", {}), ensure_ascii=False) for call in calls)
                ok_args = all(kw in args_blob for kw in c["args_keywords"])
            passed = ok_tool and ok_args
            results.append({
                **c,
                "pass": passed,
                "called_tools": names,
                "latency": round(time.time() - t0, 2),
            })
            print(f"[Agent] {c['id']} {'PASS' if passed else 'FAIL'} "
                  f"expect={expect_agent} got={names} {c['query'][:30]}")
    return results


# ======================== 3. 直答判断评测 ========================

def eval_direct(cases, n=None):
    from app import create_app
    app = create_app()
    results = []
    cases = cases if n is None else cases[:n]
    with app.app_context():
        for c in cases:
            t0 = time.time()
            try:
                calls, _ = _first_round_tool_calls(c["query"])
            except Exception as e:
                results.append({**c, "pass": False, "error": str(e)[:200], "latency": round(time.time() - t0, 2)})
                continue
            passed = len(calls) == 0  # 期望不触发任何工具
            results.append({**c, "pass": passed, "called_tools": [call.get("name") for call in calls],
                            "latency": round(time.time() - t0, 2)})
            print(f"[Direct] {c['id']} {'PASS' if passed else 'FAIL'} {c['query'][:30]}")
    return results


# ======================== 汇总 ========================

def summarize(results, metric_key):
    total = len(results)
    passed = sum(1 for r in results if r.get(metric_key))
    return {"total": total, "passed": passed, "rate": round(passed / total * 100, 1) if total else 0.0}


def main():
    parser = argparse.ArgumentParser(description="灵山 AI 导游两级评测")
    parser.add_argument("--group", choices=["rag", "agent", "direct", "all"], default="all")
    parser.add_argument("--n", type=int, default=None, help="每组抽样条数（默认全量）")
    args = parser.parse_args()

    ds = load_dataset()
    summary, details = {}, {}

    if args.group in ("rag", "all"):
        details["rag"] = eval_rag(ds["rag_cases"], args.n)
        summary["rag_hit@5"] = summarize(details["rag"], "hit")
    if args.group in ("agent", "all"):
        details["agent"] = eval_agent(ds["agent_cases"], args.n)
        summary["agent_tool_acc"] = summarize(details["agent"], "pass")
    if args.group in ("direct", "all"):
        details["direct"] = eval_direct(ds["no_tool_cases"], args.n)
        summary["direct_acc"] = summarize(details["direct"], "pass")

    print("\n========== 评测汇总 ==========")
    for k, v in summary.items():
        print(f"{k}: {v['passed']}/{v['total']} = {v['rate']}%")

    os.makedirs(RESULTS_DIR, exist_ok=True)
    out = os.path.join(RESULTS_DIR, f"eval_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "details": details}, f, ensure_ascii=False, indent=2)
    print(f"明细已保存：{out}")


if __name__ == "__main__":
    main()
