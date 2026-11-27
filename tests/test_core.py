# Copyright (C) 2026 智维ITMSKY
# SPDX-License-Identifier: AGPL-3.0-or-later

"""核心层单元测试（无网络、无 tkinter 依赖）。

覆盖：版本元数据一致性、security 私有地址判定（含 CGNAT / IPv4-mapped
回归项 F-02）、config URL 归一化与去重键、crawler 纯函数与导出回退。
运行：``python -m unittest discover -s tests``（CI 与本机一致）。
"""

from __future__ import annotations

import os
import re
import tempfile
import unittest
from pathlib import Path

from weblinkcrawler import (
    APP_COPYRIGHT,
    APP_LICENSE,
    APP_NAME_EN,
    APP_VERSION,
)
from weblinkcrawler.config import ConfigManager, canonical_key, normalize_url
from weblinkcrawler.crawler import CrawlerEngine, _csv_cell, same_domain
from weblinkcrawler.security import is_ip_literal, is_private_host

_REPO_ROOT = Path(__file__).resolve().parent.parent
_PYPROJECT = _REPO_ROOT / "pyproject.toml"


class VersionMetadataTest(unittest.TestCase):
    """版本号单一来源：APP_VERSION 必须与 pyproject.toml 严格一致。"""

    def test_app_version_matches_pyproject(self):
        self.assertTrue(_PYPROJECT.exists(), "pyproject.toml 不在仓库根目录")
        text = _PYPROJECT.read_text(encoding="utf-8")
        match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
        self.assertIsNotNone(match, "pyproject.toml 未找到 version 字段")
        self.assertEqual(APP_VERSION, match.group(1))

    def test_license_and_copyright_constants(self):
        self.assertEqual("AGPL-3.0-or-later", APP_LICENSE)
        self.assertTrue(APP_NAME_EN)
        self.assertTrue(APP_COPYRIGHT)


class SecurityTest(unittest.TestCase):
    """私有/回环地址判定（docs/04 安全设计 §3 的纯函数回归）。"""

    def test_private_hosts(self):
        for host in (
            "127.0.0.1", "10.0.0.5", "172.16.0.1", "192.168.1.1",
            "100.64.0.1",  # CGNAT（F-02 回归）
            "::ffff:127.0.0.1",  # IPv4-mapped 回环（映射绕过回归）
            "localhost", "::1", "169.254.1.1",
        ):
            with self.subTest(host=host):
                self.assertTrue(is_private_host(host))

    def test_public_hosts(self):
        for host in ("8.8.8.8", "1.1.1.1", "example.com", ""):
            with self.subTest(host=host):
                self.assertFalse(is_private_host(host))

    def test_ip_literal(self):
        self.assertTrue(is_ip_literal("8.8.8.8"))
        self.assertTrue(is_ip_literal("[2001:db8::1]"))
        self.assertFalse(is_ip_literal("example.com"))
        self.assertFalse(is_ip_literal(""))


class ConfigNormalizeTest(unittest.TestCase):
    """URL 归一化与去重键（config.py 纯函数）。"""

    def test_normalize_bare_host_gets_scheme(self):
        self.assertEqual("https://example.com/path", normalize_url("example.com/path"))

    def test_normalize_keeps_non_http_scheme_untouched(self):
        self.assertEqual("javascript:alert(1)", normalize_url("javascript:alert(1)"))
        self.assertEqual("mailto:a@b.com", normalize_url("mailto:a@b.com"))

    def test_normalize_strips_credentials_and_fragment(self):
        self.assertEqual(
            "http://example.com/Page",
            normalize_url("HTTP://User:Pass@example.com/Page#sec"),
        )

    def test_normalize_empty_input(self):
        self.assertEqual("", normalize_url(None))
        self.assertEqual("", normalize_url("   "))

    def test_canonical_key_dedup_semantics(self):
        key = canonical_key(
            "https://example.com/list?b=1&id=2&utm_source=x#frag",
            strip_params=["utm_source"],
            keep_params=[],
        )
        self.assertEqual("https://example.com/list?b=1&id=2", key)

    def test_canonical_key_bad_input_returns_text(self):
        # 解析失败退回原文，保证去重键始终可用
        self.assertEqual("::not-a-url::", canonical_key("::not-a-url::"))


class CrawlerPureFunctionTest(unittest.TestCase):
    """crawler 模块纯函数与导出回退（无网络请求）。"""

    def test_same_domain(self):
        self.assertTrue(same_domain("https://a.com/x", "http://a.com/y"))
        self.assertFalse(same_domain("https://a.com", "https://b.com"))
        self.assertFalse(same_domain("https://a.com", "https://a.com:8443"))

    def test_first_base_resolves_links_and_each_base_uses_response_url(self):
        engine = CrawlerEngine(ConfigManager())
        links = engine.extract_links(
            '<base target="_blank"><base href="media/"><base href="other/">'
            '<a href="guide">Guide</a><img src="a.png" srcset="b.png 2x">',
            "https://example.org/docs/index.html",
        )
        self.assertEqual(links, [
            "https://example.org/docs/media/guide",
            "https://example.org/docs/media/",
            "https://example.org/docs/other/",
            "https://example.org/docs/media/a.png",
            "https://example.org/docs/media/b.png",
        ])

    def test_selected_content_uses_document_base(self):
        engine = CrawlerEngine(ConfigManager())
        page = "https://example.org/docs/index.html"
        for href, expected in (
            ("https://cdn.example.org/files/", "https://cdn.example.org/files/guide"),
            ("", "https://example.org/docs/guide"),
            ("data:text/plain,hello", "https://example.org/docs/guide"),
            ("https://[", "https://example.org/docs/guide"),
            ("https://example.org:bad/", "https://example.org/docs/guide"),
        ):
            with self.subTest(href=href):
                html = (f'<base href="{href}"><base href="/ignored/">'
                        '<a href="outside">Skip</a><main><a href="guide">Guide</a></main>')
                self.assertEqual(engine.extract_links(html, page, "main"), [expected])

    def test_csv_cell_neutralizes_formula_injection(self):
        # F-01：以 = + - @ 或制表/回车开头的单元格统一加单引号前缀
        for raw in ("=cmd|' /c calc'!A1", "+1", "-x", "@SUM(A1)", "\tTab", "\rCR"):
            with self.subTest(raw=raw):
                self.assertEqual("'" + raw, _csv_cell(raw))

    def test_csv_cell_plain_values_untouched(self):
        self.assertEqual("https://example.com", _csv_cell("https://example.com"))
        self.assertEqual("", _csv_cell(None))

    def test_export_unsupported_fmt_falls_back_to_txt(self):
        engine = CrawlerEngine(config=None)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "nested", "report.xml")
            written = engine.export([], path, fmt="xml")
            self.assertTrue(os.path.isfile(written))
            self.assertEqual("report.xml", os.path.basename(written))


if __name__ == "__main__":
    unittest.main()
