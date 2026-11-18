# Copyright (C) 2026 智维ITMSKY
# SPDX-License-Identifier: AGPL-3.0-or-later

"""robots.txt 解析与匹配的边界用例（无网络）。

- `_parse_robots_rules`：分组选择、注释剥离、空 Disallow、Crawl-delay 容错、
  Allow/Disallow 二元组归一化（原内联逻辑的纯函数回归面）；
- `_robots_match_length`：``*`` 通配与 ``$`` 结束锚定；
- 缓存集成：预置 robots 缓存后 `robots_allows` 走 RFC 9309 最长匹配优先，
  不发起任何网络请求。
"""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest

from weblinkcrawler.crawler import CrawlerEngine, _parse_robots_rules
from weblinkcrawler.config import ConfigManager

_robots_match_length = CrawlerEngine._robots_match_length


class ParseRobotsRulesTest(unittest.TestCase):
    def test_star_group_rules_and_delay(self):
        text = (
            "User-agent: *\n"
            "Disallow: /private/\n"
            "Allow: /private/ok$\n"
            "Crawl-delay: 2.5\n"
        )
        rules, delay = _parse_robots_rules(text)
        self.assertEqual(
            [("allow", "/private/ok$"), ("disallow", "/private/")],
            rules,
        )
        self.assertEqual(2.5, delay)

    def test_other_agent_group_ignored_and_star_reentry(self):
        text = (
            "User-agent: Googlebot\n"
            "Disallow: /x\n"
            "User-agent: *\n"
            "Disallow: /y\n"
            "User-agent: Bingbot\n"
            "Disallow: /z\n"
            "User-agent: *\n"
            "Disallow: /w\n"
        )
        rules, _ = _parse_robots_rules(text)
        self.assertEqual([("disallow", "/y"), ("disallow", "/w")], rules)

    def test_comments_and_empty_disallow_skipped(self):
        text = (
            "# header comment\n"
            "User-agent: *  # inline comment\n"
            "Disallow: # 空值 = 全放行，跳过\n"
            "Disallow:/secret   # 无空格分隔\n"
            "garbage-line-without-colon\n"
        )
        rules, _ = _parse_robots_rules(text)
        self.assertEqual([("disallow", "/secret")], rules)

    def test_invalid_crawl_delay_defaults_zero(self):
        text = "User-agent: *\nCrawl-delay: soon\n"
        rules, delay = _parse_robots_rules(text)
        self.assertEqual([], rules)
        self.assertEqual(0.0, delay)

    def test_empty_text(self):
        rules, delay = _parse_robots_rules("")
        self.assertEqual([], rules)
        self.assertEqual(0.0, delay)


class RobotsMatchLengthTest(unittest.TestCase):
    def test_plain_prefix(self):
        self.assertEqual(len("/private/"), _robots_match_length("/private/x", "/private/"))
        self.assertIsNone(_robots_match_length("/public/x", "/private/"))

    def test_wildcard(self):
        # 返回「命中字面前缀长度」（通配跨度不计入）——对 RFC 9309
        # 最长匹配优先的相对比较自洽即可
        self.assertEqual(len("/private/"), _robots_match_length("/private/x.jpg", "/private/*"))
        self.assertIsNone(_robots_match_length("/other/x.jpg", "/private/*"))

    def test_end_anchor(self):
        self.assertEqual(len("/a.pdf"), _robots_match_length("/a.pdf", "*.pdf$"))
        self.assertIsNone(_robots_match_length("/a.pdf.bak", "*.pdf$"))


class RobotsAllowsIntegrationTest(unittest.TestCase):
    """预置缓存后走 robots_allows 的最长匹配优先判定（无网络）。"""

    def setUp(self):
        self._orig_cwd = os.getcwd()
        self._tmp = tempfile.mkdtemp(prefix="wlc-robots-test-")
        os.chdir(self._tmp)
        self.engine = CrawlerEngine(
            ConfigManager(
                config_file=os.path.join(self._tmp, "file_type_config.json"),
                enhanced_config_file=os.path.join(self._tmp, "enhanced_config.json"),
            ),
            db=None,
        )
        self.engine.config.load_file_types()
        self.engine.config.load_enhanced()

    def tearDown(self):
        os.chdir(self._orig_cwd)
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _seed(self, rules):
        self.engine._store_robots("https://example.com", (rules, 0.0))

    def test_longest_match_allow_wins(self):
        self._seed([("allow", "/private/ok$"), ("disallow", "/private/")])
        self.assertFalse(self.engine.robots_allows("https://example.com/private/x"))
        self.assertTrue(self.engine.robots_allows("https://example.com/private/ok"))
        self.assertTrue(self.engine.robots_allows("https://example.com/public/x"))

    def test_disallow_only_blocks(self):
        self._seed([("disallow", "/*.pdf$")])
        self.assertFalse(self.engine.robots_allows("https://example.com/doc.pdf"))
        self.assertTrue(self.engine.robots_allows("https://example.com/doc.html"))

    def test_no_rules_allows_everything(self):
        self._seed([])
        self.assertTrue(self.engine.robots_allows("https://example.com/anything"))


if __name__ == "__main__":
    unittest.main()
