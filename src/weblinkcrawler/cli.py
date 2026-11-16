# Copyright (C) 2026 智维ITMSKY
# SPDX-License-Identifier: AGPL-3.0-or-later

"""命令行入口：``weblinkcrawler``（console script）与 ``python -m weblinkcrawler`` 共用。

- 无参数：委托 ``weblinkcrawler.app:main`` 启动 GUI（与历史行为一致）；
- ``crawl`` / ``check``：无 GUI 的抓取与链接体检模式（运维巡检 / 自动化场景），
  只依赖 ``config`` + ``crawler`` 核心引擎，不导入 tkinter；
- ``--version`` / ``-h``：只读包元数据应答。
tkinter 不可用时给出可操作的安装提示，而不是抛出 ImportError 回溯。
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime

from . import APP_LICENSE, APP_NAME, APP_NAME_EN, APP_VERSION

_EXPORT_FORMATS = ("txt", "csv", "json")


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
    sub = parser.add_subparsers(dest="command", metavar="command")

    crawl = sub.add_parser(
        "crawl",
        help="无 GUI 抓取模式：从起始 URL 同域下钻提取链接，可导出 TXT/CSV/JSON",
    )
    crawl.add_argument("urls", nargs="+", metavar="URL", help="起始 URL（一个或多个）")
    crawl.add_argument("--depth", type=int, default=None, metavar="N",
                       help="最大下钻深度（缺省取配置文件 crawl.max_depth）")
    crawl.add_argument("--max-pages", type=int, default=None, metavar="N",
                       help="全局抓取页数上限（缺省取配置文件 crawl.max_pages）")
    crawl.add_argument("--export", default=None, metavar="PATH",
                       help="导出路径（自动创建父目录）")
    crawl.add_argument("--fmt", choices=_EXPORT_FORMATS, default="json",
                       help="导出格式（默认 json，仅 --export 生效）")

    check = sub.add_parser(
        "check",
        help="无 GUI 链接体检模式：并发 HEAD 体检给定 URL 的存活状态",
    )
    check.add_argument("urls", nargs="+", metavar="URL", help="待体检 URL（一个或多个）")
    check.add_argument("--export", default=None, metavar="PATH",
                       help="导出路径（自动创建父目录）")
    check.add_argument("--fmt", choices=_EXPORT_FORMATS, default="json",
                       help="导出格式（默认 json，仅 --export 生效）")
    check.add_argument("--strict", action="store_true",
                       help="blocked（401/403/429）也计入失败判定（默认仅 dead/error 算失败）")
    return parser


def _redirect_quiet_stderr():
    """Windows 控制台默认 charmap 编码，中文/全角输出会 UnicodeEncodeError：
    统一切到 UTF-8（不支持的终端用 errors="replace" 兜底，保证永不崩溃）。"""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass


def _make_engine():
    """构建核心引擎（无 GUI、无数据库持久化；配置与 GUI 同源：当前工作目录）。"""
    from .config import ConfigManager
    from .crawler import CrawlerEngine

    config = ConfigManager()
    config.load_file_types()
    config.load_enhanced()
    return CrawlerEngine(config, db=None), config


def _event_handler(args):
    def on_event(event):
        try:
            kind = event[0] if isinstance(event, tuple) else None
            if kind == "page":
                _, url, count, depth = event
                print(f"[depth {depth}] {url} -> {count} links", file=sys.stderr)
            elif kind == "log":
                _, level, message = event
                print(f"[{level}] {message}", file=sys.stderr)
        except Exception:
            pass
    return on_event


def _apply_overrides(config, args):
    """命令行覆盖项写入内存配置（不回写配置文件）。

    键位与 ConfigManager 属性映射一致：max_depth ← crawling_depth.depth、
    max_pages ← crawl_limits.max_pages（见 config.py @property 段）。
    """
    crawling = config.enhanced_config.setdefault("crawling_depth", {})
    limits = config.enhanced_config.setdefault("crawl_limits", {})
    if getattr(args, "depth", None) is not None:
        crawling["depth"] = max(0, int(args.depth))
    if getattr(args, "max_pages", None) is not None:
        limits["max_pages"] = max(1, int(args.max_pages))


def _run_crawl(args):
    from .logutil import setup_logging

    setup_logging()
    engine, config = _make_engine()
    _apply_overrides(config, args)
    records = engine.crawl(list(dict.fromkeys(args.urls)), on_event=_event_handler(args))
    records = list(records or [])
    print(f"crawl done: {len(records)} links from {len(args.urls)} start URL(s)")
    if args.export:
        path = engine.export(
            records, args.export, fmt=args.fmt,
            meta={"source": "; ".join(args.urls),
                  "crawl_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")},
        )
        print(f"exported: {path}")
    return 0


def _run_check(args):
    from .logutil import setup_logging

    setup_logging()
    engine, _ = _make_engine()
    results = engine.check_links(list(dict.fromkeys(args.urls)), on_event=_event_handler(args))
    results = dict(results or {})
    counters = {}
    for link in results:
        state = str(results[link][0]) if isinstance(results[link], tuple) else str(results[link])
        counters[state] = counters.get(state, 0) + 1
    for link, outcome in results.items():
        state, code = outcome if isinstance(outcome, tuple) else (outcome, "")
        print(f"{state}\t{code}\t{link}")
    summary = ", ".join(f"{k}={v}" for k, v in sorted(counters.items())) or "none"
    print(f"check done: {len(results)} link(s) [{summary}]")
    if args.export:
        records = [
            {"link": link, "state": state, "code": code}
            for link, (state, code) in results.items()
        ]
        path = engine.export(
            records, args.export, fmt=args.fmt,
            meta={"source": "; ".join(args.urls),
                  "crawl_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")},
        )
        print(f"exported: {path}")
    # 退出码语义（借鉴 lychee / linkchecker）：存在失败级链接 → 1，供 cron 告警判断。
    # 引擎状态词表：ok / redirect / blocked / dead / error。
    # dead（断链）+ error（无法判定）必判失败；blocked（401/403/429，常见为鉴权墙/反爬）
    # 默认放行以控制误报，与引擎把 999 类反爬码默认视为 ok 的口径一致；--strict 收紧。
    fail_states = {"dead", "error"}
    if getattr(args, "strict", False):
        fail_states.add("blocked")
    failed = sum(counters.get(s, 0) for s in fail_states)
    return 1 if failed else 0


def main(argv=None):
    """命令行入口；无参数时启动 GUI（与历史行为一致）。"""
    _redirect_quiet_stderr()
    args = _build_parser().parse_args(argv)
    command = getattr(args, "command", None)
    if command == "crawl":
        try:
            return _run_crawl(args)
        except Exception as exc:
            print(f"crawl failed: {exc}", file=sys.stderr)
            return 1
    if command == "check":
        try:
            return _run_check(args)
        except Exception as exc:
            print(f"check failed: {exc}", file=sys.stderr)
            return 1
    # 无子命令：GUI 路径（历史行为；tkinter 缺失给可操作提示）
    try:
        from .app import main as app_main
    except ImportError as exc:
        if "tkinter" in str(exc) or "_tkinter" in str(exc):
            print(
                "未找到 tkinter：当前环境缺少 GUI 运行库，无法启动图形界面。\n"
                "无 GUI 抓取/体检可用子命令：weblinkcrawler crawl|check（见 --help）。\n"
                "Windows / macOS 官方 Python 自带 tkinter；Debian/Ubuntu 可执行\n"
                "    sudo apt-get install python3-tk\n"
                "后重试。版本查询不受影响：weblinkcrawler --version",
                file=sys.stderr,
            )
            return 1
        raise
    return app_main()
