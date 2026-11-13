# Copyright (C) 2026 智维ITMSKY
# SPDX-License-Identifier: AGPL-3.0-or-later

"""轻量日志工具：文件 + 控制台分级输出。"""

from __future__ import annotations

import logging

_DEFAULT_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_configured = False


def setup_logging(log_file="weblinkcrawler.log", level=logging.INFO, console=True):
    """初始化根 logger（幂等）。返回 logger。"""
    global _configured
    logger = logging.getLogger("weblinkcrawler")
    logger.setLevel(level)
    if _configured:
        return logger
    fmt = logging.Formatter(_DEFAULT_FORMAT)
    try:
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setLevel(level)
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    except Exception:
        pass
    if console:
        ch = logging.StreamHandler()
        ch.setLevel(level)
        ch.setFormatter(fmt)
        logger.addHandler(ch)
    logger.propagate = False
    _configured = True
    return logger


def get_logger():
    return logging.getLogger("weblinkcrawler")
