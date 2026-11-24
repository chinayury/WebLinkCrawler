# Copyright (C) 2026 智维ITMSKY
# SPDX-License-Identifier: AGPL-3.0-or-later

"""日志工具（logutil.py）的回归测试：临时目录，无网络。

注意：``setup_logging`` 的幂等依赖模块级 ``_configured`` 标志——进程内
首个调用生效。其他测试（CLI 冒烟）可能已触发过，故本用例在 setUp 中重置
模块状态与处理器，保证隔离与确定性。
"""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
import unittest

import weblinkcrawler.logutil as logutil


class LogutilTest(unittest.TestCase):
    def setUp(self):
        self._orig_cwd = os.getcwd()
        self._tmp = tempfile.mkdtemp(prefix="wlc-log-test-")
        os.chdir(self._tmp)
        # 重置模块幂等状态与既有处理器（进程隔离）
        logutil._configured = False
        self._logger = logging.getLogger("weblinkcrawler")
        for handler in list(self._logger.handlers):
            self._logger.removeHandler(handler)

    def tearDown(self):
        for handler in list(self._logger.handlers):
            self._logger.removeHandler(handler)
        logutil._configured = False
        os.chdir(self._orig_cwd)
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_setup_creates_file_and_console_handlers(self):
        logger = logutil.setup_logging()
        self.assertIs(logger, self._logger)
        self.assertTrue(os.path.isfile("weblinkcrawler.log"))
        kinds = {type(h).__name__ for h in self._logger.handlers}
        self.assertIn("FileHandler", kinds)
        self.assertIn("StreamHandler", kinds)

    def test_setup_is_idempotent(self):
        logutil.setup_logging()
        first = len(self._logger.handlers)
        logutil.setup_logging()
        self.assertEqual(first, len(self._logger.handlers))

    def test_get_logger_returns_weblinkcrawler_logger(self):
        logger = logutil.get_logger()
        self.assertEqual("weblinkcrawler", logger.name)
        self.assertIs(logger, self._logger)

    def test_logger_does_not_propagate_to_root(self):
        logutil.setup_logging()
        self.assertFalse(self._logger.propagate)


if __name__ == "__main__":
    unittest.main()
