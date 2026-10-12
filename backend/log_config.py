"""
==============================================================
【结构化日志配置】
- RotatingFileHandler 写 logs/app.log（5MB x 3 轮转，UTF-8）
- 控制台同步输出
- 每条日志携带 request_id（HTTP 请求自动分配；后台线程/WS 显示 "-"）
==============================================================
"""

import logging
import os
import uuid
from logging.handlers import RotatingFileHandler

from flask import g, has_request_context

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE_DIR, "logs")
LOG_FILE = os.path.join(LOG_DIR, "app.log")

LOG_FORMAT = "%(asctime)s [%(levelname)s] [%(name)s] [req:%(request_id)s] %(message)s"


class RequestIdFilter(logging.Filter):
    """给每条日志记录注入 request_id（无请求上下文时为 -）"""

    def filter(self, record):
        try:
            if has_request_context():
                record.request_id = g.get("request_id", "-")
            else:
                record.request_id = "-"
        except Exception:
            record.request_id = "-"
        return True


def setup_logging(level=logging.INFO):
    """配置 root logger：文件轮转 + 控制台。幂等，重复调用不叠加 handler。"""
    root = logging.getLogger()
    if getattr(root, "_lingshan_configured", False):
        return
    root.setLevel(level)

    os.makedirs(LOG_DIR, exist_ok=True)
    fmt = logging.Formatter(LOG_FORMAT)
    filt = RequestIdFilter()

    file_handler = RotatingFileHandler(
        LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)
    file_handler.addFilter(filt)

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    console.addFilter(filt)

    root.addHandler(file_handler)
    root.addHandler(console)

    # 降噪：第三方库访问日志不刷 INFO
    logging.getLogger("werkzeug").setLevel(logging.WARNING)

    root._lingshan_configured = True


def init_request_tracking(app):
    """每个 HTTP 请求进入时分配 request_id，贯穿本次请求的全部日志"""

    @app.before_request
    def _assign_request_id():
        g.request_id = uuid.uuid4().hex[:8]
