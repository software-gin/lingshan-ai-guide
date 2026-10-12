"""
==============================================================
【持久化任务队列】（P1 改造）
==============================================================
替代裸 threading.Thread 的非实时后台任务（建图 / 会话记忆压缩等）：

- 入队即落库（SQLite job 表）：进程重启后 pending 任务不丢失
- 单 worker 线程轮询消费，按 job_type 分发到注册的 handler
- 失败指数退避重试（RETRY_BASE_SECONDS * 2^retry_count），超限标 failed
- worker 启动时回收上次进程遗留的 running 任务（标回 pending 重跑）
- 会话内即时副作用（数字人队列/欢迎语/TTS 预热）不走本队列，仍用进程内线程
==============================================================
"""

import json
import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Callable, Dict, List, Optional

from models import db, Job

logger = logging.getLogger(__name__)

# 类型 -> 处理函数；handler(payload: dict) -> 可选的结果摘要（会 JSON 序列化存 result）
_handlers: Dict[str, Callable[[dict], object]] = {}

_worker_started = False
_worker_lock = threading.Lock()

# 轮询间隔（秒）
POLL_INTERVAL = 1.0
# 单次循环最多连续消费的任务数（避免长期占住 worker 饿死新任务调度判断）
BATCH_LIMIT = 5
# 退避基数（秒）：第 n 次重试等待 BASE * 2^n
RETRY_BASE_SECONDS = 5


def register_handler(job_type: str, handler: Callable[[dict], object]) -> None:
    """注册任务类型对应的处理函数（模块导入时调用）"""
    _handlers[job_type] = handler


def enqueue(job_type: str, payload: Optional[dict] = None, max_retries: int = 3) -> int:
    """任务入队（需处于 Flask app/request 上下文中），返回 job id"""
    job = Job(
        job_type=job_type,
        payload=json.dumps(payload or {}, ensure_ascii=False),
        status="pending",
        max_retries=max_retries,
        run_after=datetime.now(),
    )
    db.session.add(job)
    db.session.commit()
    logger.info(f"[Job] 入队 #{job.id} type={job_type}")
    return job.id


def get_job(job_id: int) -> Optional[dict]:
    """查询单个任务状态"""
    job = Job.query.get(job_id)
    return job.to_dict() if job else None


def list_recent_jobs(limit: int = 50, job_type: Optional[str] = None) -> List[dict]:
    """查询最近任务（默认最近 50 条，按创建时间倒序）"""
    q = Job.query
    if job_type:
        q = q.filter_by(job_type=job_type)
    return [j.to_dict() for j in q.order_by(Job.id.desc()).limit(limit).all()]


def start_worker(app) -> None:
    """启动后台 worker 线程（幂等，重复调用无副作用）"""
    global _worker_started
    with _worker_lock:
        if _worker_started:
            return
        _worker_started = True

    def _loop():
        # 回收上次进程退出时遗留的 running 任务，重新排队执行
        try:
            with app.app_context():
                stuck = Job.query.filter_by(status="running").all()
                for j in stuck:
                    j.status = "pending"
                    j.run_after = datetime.now()
                if stuck:
                    db.session.commit()
                    logger.warning(f"[Job] 回收遗留 running 任务 {len(stuck)} 个")
        except Exception as e:
            logger.exception(f"[Job] 回收遗留任务失败：{e}")

        logger.info("[Job] 任务队列 worker 已启动")
        while True:
            try:
                with app.app_context():
                    _consume_once()
            except Exception as e:
                logger.exception(f"[Job] worker 循环异常：{e}")
            time.sleep(POLL_INTERVAL)

    threading.Thread(target=_loop, daemon=True, name="job-worker").start()


def _consume_once() -> None:
    """消费一批到期任务（须在 app 上下文中调用）"""
    now = datetime.now()
    jobs = (Job.query
            .filter(Job.status == "pending", Job.run_after <= now)
            .order_by(Job.id)
            .limit(BATCH_LIMIT)
            .all())
    for job in jobs:
        _run_one(job)


def _run_one(job: Job) -> None:
    handler = _handlers.get(job.job_type)
    job.status = "running"
    db.session.commit()

    if handler is None:
        job.status = "failed"
        job.error = f"未注册的任务类型：{job.job_type}"
        db.session.commit()
        logger.error(f"[Job] #{job.id} 失败：{job.error}")
        return

    try:
        payload = json.loads(job.payload) if job.payload else {}
        result = handler(payload)
        job.status = "done"
        job.error = None
        if result is not None:
            job.result = json.dumps(result, ensure_ascii=False, default=str)
        db.session.commit()
        logger.info(f"[Job] #{job.id} type={job.job_type} 完成")
    except Exception as e:
        db.session.rollback()
        # 失败重取，避免 rollback 后 job 实例状态不确定
        job = Job.query.get(job.id)
        job.retry_count += 1
        job.error = str(e)[:500]
        if job.retry_count > job.max_retries:
            job.status = "failed"
            logger.error(f"[Job] #{job.id} type={job.job_type} 超过最大重试次数，标记失败：{e}")
        else:
            backoff = RETRY_BASE_SECONDS * (2 ** job.retry_count)
            job.status = "pending"
            job.run_after = datetime.now() + timedelta(seconds=backoff)
            logger.warning(f"[Job] #{job.id} type={job.job_type} 第 {job.retry_count} 次失败，"
                           f"{backoff}s 后重试：{e}")
        db.session.commit()
