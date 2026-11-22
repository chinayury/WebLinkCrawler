# Copyright (C) 2026 智维ITMSKY
# SPDX-License-Identifier: AGPL-3.0-or-later

"""无头 CLI（crawl / check 子命令）端到端测试：本地 HTTP fixture，无外网依赖。

- 私有地址策略默认拦截 127.0.0.1（F-04 安全设计），测试以内存覆盖关闭
  （该开关的正当用途即「需要抓内网站点」，见 enhanced_config 注释）；
- 测试统一 chdir 到临时目录：隔离 setup_logging 的日志文件与配置回写，
  不污染仓库工作区；
- 无子命令的 GUI 路径测试在 tkinter 可用的环境跳过（否则会真启动 GUI 阻塞）。
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

from weblinkcrawler.cli import main
from weblinkcrawler.config import ConfigManager
from weblinkcrawler.crawler import CrawlerEngine

try:
    import tkinter  # noqa: F401
    _HAVE_TK = True
except ImportError:
    _HAVE_TK = False

_INDEX_HTML = (
    "<html><body>"
    '<a href="/alpha">alpha</a>'
    '<a href="/beta">beta</a>'
    '<a href="https://external.example">external</a>'
    "</body></html>"
)


class _FixtureHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/robots.txt":
            self.send_response(404)
            self.end_headers()
            return
        body = _INDEX_HTML.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_HEAD(self):
        # /missing 固定 404：供 check 退出码语义用例（error → 退出码 1）
        if self.path == "/missing":
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *args):
        pass


class CliHeadlessTest(unittest.TestCase):
    server = None

    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _FixtureHandler)
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}/"
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        self._orig_cwd = os.getcwd()
        self._tmp = tempfile.mkdtemp(prefix="wlc-cli-test-")
        os.chdir(self._tmp)

    def tearDown(self):
        os.chdir(self._orig_cwd)
        import shutil

        shutil.rmtree(self._tmp, ignore_errors=True)

    def _make_engine_pair(self):
        config = ConfigManager(
            config_file=os.path.join(self._tmp, "file_type_config.json"),
            enhanced_config_file=os.path.join(self._tmp, "enhanced_config.json"),
        )
        config.load_file_types()
        config.load_enhanced()
        policy = config.enhanced_config["network_policy"]
        # 内存覆盖：测试抓取目标就是 127.0.0.1（该开关的正当内网用途）
        policy["block_private_targets"] = False
        policy["block_private_redirects"] = False
        return CrawlerEngine(config, db=None), config

    def test_crawl_exports_discovered_links(self):
        out = os.path.join(self._tmp, "out", "links.json")
        pair = self._make_engine_pair()
        with mock.patch("weblinkcrawler.cli._make_engine", return_value=pair):
            exit_code = main(["crawl", self.base_url, "--depth", "1", "--export", out])
        self.assertEqual(exit_code, 0)
        with open(out, encoding="utf-8") as f:
            payload = json.load(f)
        links = {item["link"] for item in payload["links"]}
        # 引擎语义：records 为「发现的链接」，不含种子 URL 自身
        self.assertTrue(any(l.endswith("/alpha") for l in links), links)
        self.assertTrue(any(l.endswith("/beta") for l in links), links)
        self.assertEqual(payload["meta"]["count"], len(payload["links"]))

    def test_crawl_depth_override_applies(self):
        pair = self._make_engine_pair()
        with mock.patch("weblinkcrawler.cli._make_engine", return_value=pair):
            exit_code = main(["crawl", self.base_url, "--depth", "0"])
        self.assertEqual(exit_code, 0)
        # depth=0 → 只取起始页；engine.max_depth 属性已被覆盖为 0
        self.assertEqual(pair[0].config.max_depth, 0)

    def test_check_reports_ok_state(self):
        pair = self._make_engine_pair()
        with mock.patch("weblinkcrawler.cli._make_engine", return_value=pair):
            exit_code = main(["check", self.base_url])
        self.assertEqual(exit_code, 0)

    def test_check_exit_code_signals_error(self):
        """退出码语义：error 级链接 → 1（cron 告警判断口径）。"""
        pair = self._make_engine_pair()
        with mock.patch("weblinkcrawler.cli._make_engine", return_value=pair):
            exit_code = main(["check", self.base_url + "missing"])
        self.assertEqual(exit_code, 1)

    def test_crawl_check_combined_reports_failures(self):
        """crawl --check 组合模式：抓取后对发现链接体检，失败级存在 → 退出码 1。

        fixture 的 /alpha /beta 同域可访问（ok），但页面含 external.example
        （RFC 2606 保留 TLD，NXDOMAIN）→ error → 退出码 1。
        """
        pair = self._make_engine_pair()
        with mock.patch("weblinkcrawler.cli._make_engine", return_value=pair):
            exit_code = main(["crawl", self.base_url, "--depth", "1", "--check"])
        self.assertEqual(exit_code, 1)

    def test_check_export_json(self):
        out = os.path.join(self._tmp, "checks.json")
        pair = self._make_engine_pair()
        with mock.patch("weblinkcrawler.cli._make_engine", return_value=pair):
            exit_code = main(["check", self.base_url, "--export", out])
        self.assertEqual(exit_code, 0)
        with open(out, encoding="utf-8") as f:
            payload = json.load(f)
        self.assertEqual(payload["meta"]["count"], 1)
        self.assertEqual(payload["links"][0]["link"], self.base_url)
        self.assertEqual(payload["links"][0]["state"], "ok")

    @unittest.skipIf(_HAVE_TK, "tkinter available: would launch a real GUI")
    def test_no_command_keeps_gui_path_with_friendly_error(self):
        """无子命令时仍走 GUI 路径：本机无 tkinter → 友好提示 + 退出码 1。"""
        exit_code = main([])
        self.assertEqual(exit_code, 1)


if __name__ == "__main__":
    unittest.main()
