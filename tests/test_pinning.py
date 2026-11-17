# Copyright (C) 2026 智维ITMSKY
# SPDX-License-Identifier: AGPL-3.0-or-later

"""DNS 重绑定 TOCTOU 防护（连接层 IP 钉定）的单元与端到端测试。

- resolve_pinned_ip：IP 字面量/回环/内网开关/解析失败 fail-closed 口径；
- 端到端：以 ``localhost`` 抓取本地 fixture（socket 钉定到 127.0.0.1、
  Host 头保留 localhost），验证钉定连接层真实可用；
- fail-closed：resolver 拒绝的主机（NXDOMAIN）→ 链接 error 级。
"""

from __future__ import annotations

import unittest
from unittest import mock

from test_cli_headless import CliHeadlessTest  # 复用 HTTP fixture 与配置装配

from weblinkcrawler.cli import main
from weblinkcrawler.crawler import _PinnedAdapter
from weblinkcrawler.security import UnsafeUrlError, resolve_pinned_ip


class ResolvePinnedIpTest(unittest.TestCase):
    def test_ip_literal_returns_none(self):
        # 字面量无需解析：按原样建连即为「已钉定」
        self.assertIsNone(resolve_pinned_ip("127.0.0.1"))
        self.assertIsNone(resolve_pinned_ip("8.8.8.8"))
        self.assertIsNone(resolve_pinned_ip("[::1]"))

    def test_loopback_blocked_by_default(self):
        with self.assertRaises(UnsafeUrlError):
            resolve_pinned_ip("localhost", allow_private=False)

    def test_intranet_allowed_when_opted_in(self):
        self.assertEqual("127.0.0.1", resolve_pinned_ip("localhost", allow_private=True))

    def test_dns_failure_fails_closed(self):
        # .invalid TLD 保证 NXDOMAIN（RFC 2606），离线可复现
        with self.assertRaises(UnsafeUrlError):
            resolve_pinned_ip("nonexistent.invalid", allow_private=False)
        with self.assertRaises(UnsafeUrlError):
            resolve_pinned_ip("nonexistent.invalid", allow_private=True)


class PinningEngineTest(CliHeadlessTest):
    """复用 CliHeadlessTest 的本地 HTTP fixture 与配置装配。"""

    def test_session_mounts_pinned_adapter(self):
        engine, _ = self._make_engine_pair()
        session = engine.session
        self.assertIsInstance(session.get_adapter("https://example.com"), _PinnedAdapter)
        self.assertIsInstance(session.get_adapter("http://example.com"), _PinnedAdapter)

    def test_crawl_via_pinned_localhost_connects(self):
        """以 localhost（非字面量）抓取 fixture：连接层钉定路径真实可用。"""
        engine, _ = self._make_engine_pair()
        url = self.base_url.replace("127.0.0.1", "localhost", 1)
        records = list(engine.crawl([url], on_event=None))
        links = {r["link"] for r in records}
        self.assertTrue(any(l.endswith("/alpha") for l in links), links)
        self.assertTrue(any(l.endswith("/beta") for l in links), links)

    def test_resolver_refusal_fails_closed(self):
        """resolver 拒绝的主机（NXDOMAIN）→ 请求失败、体检 error → 退出码 1。"""
        engine, _ = self._make_engine_pair()
        with mock.patch("weblinkcrawler.cli._make_engine", return_value=(engine, None)):
            exit_code = main(["check", "https://nonexistent.invalid"])
        self.assertEqual(exit_code, 1)


if __name__ == "__main__":
    unittest.main()
