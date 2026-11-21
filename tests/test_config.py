# Copyright (C) 2026 智维ITMSKY
# SPDX-License-Identifier: AGPL-3.0-or-later

"""配置层（config.py ConfigManager）的回归测试：临时文件目录，无网络。

覆盖：增强配置加载迁移（部分文件 → 深合并补默认值并回写）、类型容错
（get_int 非法值回退 / lo-hi 钳制、get_bool 强转）、属性映射
（max_depth / max_pages / concurrency / css_selector）、request_params
六元组形状（动态 UA / 代理类型映射 / Cookie 解析）、文件类型映射读写回环。
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest

from weblinkcrawler.config import ConfigManager


class ConfigManagerTest(unittest.TestCase):
    def setUp(self):
        self._orig_cwd = os.getcwd()
        self._tmp = tempfile.mkdtemp(prefix="wlc-config-test-")
        os.chdir(self._tmp)

    def tearDown(self):
        os.chdir(self._orig_cwd)
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _make(self, partial_enhanced=None, partial_file_types=None):
        ft_path = os.path.join(self._tmp, "file_type_config.json")
        ec_path = os.path.join(self._tmp, "enhanced_config.json")
        if partial_file_types is not None:
            with open(ft_path, "w", encoding="utf-8") as f:
                json.dump(partial_file_types, f, ensure_ascii=False)
        if partial_enhanced is not None:
            with open(ec_path, "w", encoding="utf-8") as f:
                json.dump(partial_enhanced, f, ensure_ascii=False)
        cfg = ConfigManager(config_file=ft_path, enhanced_config_file=ec_path)
        cfg.load_file_types()
        cfg.load_enhanced()
        return cfg

    def test_load_enhanced_migrates_partial_file(self):
        # 部分配置 → 深合并补默认值并回写（迁移补齐）
        partial = {"crawl_limits": {"max_pages": 7}}
        cfg = self._make(partial_enhanced=partial)
        # 合并后默认键仍在
        self.assertIn("network_policy", cfg.enhanced_config)
        self.assertEqual(7, cfg.enhanced_config["crawl_limits"]["max_pages"])
        # 回写文件含默认键（迁移落盘）
        with open(cfg.enhanced_config_file, encoding="utf-8") as f:
            on_disk = json.load(f)
        self.assertIn("network_policy", on_disk)
        self.assertEqual(7, on_disk["crawl_limits"]["max_pages"])

    def test_get_int_clamp_and_fallback(self):
        cfg = self._make(partial_enhanced={
            "crawl_limits": {"max_pages": "not-a-number", "concurrency": 9999},
            "crawling_depth": {"depth": -3},
        })
        # 非法值回退默认；越界值钳制
        self.assertEqual(200, cfg.get_int("crawl_limits", "max_pages", default=200, lo=1, hi=100000))
        self.assertEqual(64, cfg.get_int("crawl_limits", "concurrency", default=8, lo=1, hi=64))
        self.assertEqual(0, cfg.get_int("crawling_depth", "depth", default=1, lo=0, hi=5))
        # 缺失键取 default
        self.assertEqual(3, cfg.get_int("nope", "missing", default=3))

    def test_get_bool_and_get_list(self):
        cfg = self._make(partial_enhanced={
            "network_policy": {"respect_robots": False},
            "exclude_rules": {"patterns": ["a", "", 123, None, "b"]},
        })
        self.assertIs(False, cfg.get_bool("network_policy", "respect_robots", default=True))
        self.assertIs(True, cfg.get_bool("nope", "missing", default=True))
        self.assertEqual(["a", "123", "b"], cfg.get_list("exclude_rules", "patterns"))

    def test_property_mapping(self):
        cfg = self._make(partial_enhanced={
            "crawling_depth": {"enabled": True, "depth": 9},
            "crawl_limits": {"max_pages": 500, "concurrency": 2},
            "element_crawling": {"enabled": True, "css_selector": "  .main a  "},
        })
        self.assertEqual(5, cfg.max_depth)  # hi=5 钳制
        self.assertEqual(500, cfg.max_pages)
        self.assertEqual(2, cfg.concurrency)
        self.assertEqual(".main a", cfg.css_selector)  # 剥空白

    def test_property_depth_disabled_returns_zero(self):
        cfg = self._make(partial_enhanced={
            "crawling_depth": {"enabled": False, "depth": 3},
        })
        self.assertEqual(0, cfg.max_depth)

    def test_request_params_shape_and_proxy_type_mapping(self):
        cfg = self._make(partial_enhanced={
            "anti_anti_crawl": {
                "enabled": True,
                "dynamic_ua": True,
                "ua_list": ["UA-TEST-1", "UA-TEST-2"],
                "proxy": {"enabled": True, "type": "socks5", "proxy_list": ["1.2.3.4:1080"]},
                "cookies": {"enabled": True, "cookie_list": ["k1=v1", "bad-cookie", "k2 = v2 "]},
                "request_strategy": {"enabled": True, "interval": 1, "retries": 2, "timeout": 9},
            },
        })
        headers, proxies, cookies, timeout, retries, interval = cfg.request_params()
        self.assertIn(headers["User-Agent"], ("UA-TEST-1", "UA-TEST-2"))
        self.assertEqual({"http": "socks5://1.2.3.4:1080", "https": "socks5://1.2.3.4:1080"}, proxies)
        self.assertEqual({"k1": "v1", "k2": "v2"}, cookies)
        self.assertEqual(9, timeout)
        self.assertEqual(2, retries)
        self.assertEqual(1, interval)

    def test_request_params_invalid_proxy_type_falls_back_to_http(self):
        cfg = self._make(partial_enhanced={
            "anti_anti_crawl": {
                "enabled": True,
                "proxy": {"enabled": True, "type": "bogus", "proxy_list": ["1.2.3.4:1080"]},
            },
        })
        _h, proxies, _c, _t, _r, _i = cfg.request_params()
        self.assertEqual({"http": "http://1.2.3.4:1080", "https": "http://1.2.3.4:1080"}, proxies)

    def test_request_params_without_anti_crawl(self):
        cfg = self._make(partial_enhanced={"anti_anti_crawl": {"enabled": False}})
        headers, proxies, cookies, timeout, retries, interval = cfg.request_params()
        self.assertIn("User-Agent", headers)
        self.assertIsNone(proxies)
        self.assertIsNone(cookies)

    def test_file_types_round_trip(self):
        partial = {"自定义类型": {"ext": [".xyz"], "pattern": ""}}
        cfg = self._make(partial_file_types=partial)
        with open(cfg.config_file, encoding="utf-8") as f:
            on_disk = json.load(f)
        self.assertIn("自定义类型", on_disk)
        self.assertEqual([".xyz"], on_disk["自定义类型"]["ext"])


if __name__ == "__main__":
    unittest.main()
