# Copyright (C) 2026 智维ITMSKY
# SPDX-License-Identifier: AGPL-3.0-or-later

"""命令行入口：``weblinkcrawler``（console script）与 ``python -m weblinkcrawler`` 共用。

无参数时委托 ``weblinkcrawler.app:main`` 启动 GUI（与历史行为一致）；
``--version`` / ``-h`` 只依赖包元数据，无需 tkinter 即可应答。
tkinter 不可用时给出可操作的安装提示，而不是抛出 ImportError 回溯。
"""

from __future__ import annotations

import argparse
import sys

from . import APP_LICENSE, APP_NAME, APP_NAME_EN, APP_VERSION


def _build_parser():
    parser = argparse.ArgumentParser(
        prog=APP_NAME_EN,
        description=f"{APP_NAME}——桌面端网页链接提取、筛选、深度抓取与链接体检",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"{APP_NAME_EN} {APP_VERSION}（{APP_LICENSE}）",
    )
    return parser


def main(argv=None):
    """命令行入口；无参数时启动 GUI（与历史行为一致）。"""
    # Windows 控制台默认 charmap 编码，直接输出中文/全角字符会 UnicodeEncodeError：
    # 统一切到 UTF-8（不支持的终端用 errors="replace" 兜底，保证永不崩溃）。
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass
    _build_parser().parse_args(argv)
    try:
        from .app import main as app_main
    except ImportError as exc:
        if "tkinter" in str(exc) or "_tkinter" in str(exc):
            print(
                "未找到 tkinter：当前环境缺少 GUI 运行库，无法启动图形界面。\n"
                "Windows / macOS 官方 Python 自带 tkinter；Debian/Ubuntu 可执行\n"
                "    sudo apt-get install python3-tk\n"
                "后重试。版本查询不受影响：weblinkcrawler --version",
                file=sys.stderr,
            )
            return 1
        raise
    return app_main()
