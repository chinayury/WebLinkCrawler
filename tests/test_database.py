# Copyright (C) 2026 智维ITMSKY
# SPDX-License-Identifier: AGPL-3.0-or-later

"""SQLite 持久层（database.py）的回归测试：临时文件库，无网络。

覆盖：任务生命周期（pending/crawling/stopped 可续、done 不可续）、
批量写入（9 元组行）、links_for_task 写入顺序、visited_for_task 去重、
体检批量落库、重开连接后的持久性（WAL 落盘读回）。
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import tempfile
import unittest

from weblinkcrawler.database import DatabaseManager


class DatabaseManagerTest(unittest.TestCase):
    def setUp(self):
        self._orig_cwd = os.getcwd()
        self._tmp = tempfile.mkdtemp(prefix="wlc-db-test-")
        os.chdir(self._tmp)
        self._db_path = os.path.join(self._tmp, "crawling_progress.db")

    def tearDown(self):
        os.chdir(self._orig_cwd)
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_task_lifecycle_pending_semantics(self):
        db = DatabaseManager(self._db_path)
        tid = db.create_task("https://example.com", 1, status="crawling")
        self.assertEqual(tid, 1)
        # crawling 状态属于可续任务
        self.assertEqual([1], [t[0] for t in db.pending_tasks()])
        # stopped 也算可续（断点续爬口径）
        db.update_task(tid, "stopped")
        self.assertEqual([t[0] for t in db.pending_tasks()], [1])
        # done 后不可续
        db.update_task(tid, "done", end_time="2026-01-01T00:00:00",
                       total_links=10, crawled_links=7)
        self.assertEqual(db.pending_tasks(), [])
        db.close()

    def test_links_order_and_visited_dedup(self):
        db = DatabaseManager(self._db_path)
        tid = db.create_task("https://example.com", 1)
        rows = [
            (tid, "https://example.com/a", "https://example.com/a", 0, None, None, None, None, "crawled"),
            (tid, "https://example.com/a", "https://example.com/b", 1, None, None, None, None, "crawled"),
            (tid, "https://example.com/b", "https://example.com/c", 1, None, None, None, None, "crawled"),
        ]
        db.add_links_bulk(rows)
        links = db.links_for_task(tid)
        self.assertEqual(
            [("https://example.com/a", "https://example.com/a", 0),
             ("https://example.com/a", "https://example.com/b", 1),
             ("https://example.com/b", "https://example.com/c", 1)],
            links,
        )
        self.assertEqual(
            {"https://example.com/a", "https://example.com/b"},
            db.visited_for_task(tid),
        )
        db.close()

    def test_checks_bulk_persist_and_reopen(self):
        db = DatabaseManager(self._db_path)
        tid = db.create_task("https://example.com", 1)
        db.add_checks_bulk([
            (tid, "https://example.com/a", "ok", 200),
            (tid, "https://example.com/b", "dead", 404),
        ])
        db.close()
        # 重开连接：数据落盘可读（WAL 检查点归并）
        db2 = DatabaseManager(self._db_path)
        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(
                "SELECT link, state, status_code FROM link_checks "
                "WHERE task_id = ? ORDER BY link",
                (tid,),
            ).fetchall()
        self.assertEqual(
            [("https://example.com/a", "ok", 200),
             ("https://example.com/b", "dead", 404)],
            [(r[0], r[1], r[2]) for r in rows],
        )
        db2.close()

    def test_empty_bulk_calls_are_noop(self):
        db = DatabaseManager(self._db_path)
        tid = db.create_task("https://example.com", 1)
        db.add_links_bulk([])  # 不应抛异常
        db.add_checks_bulk([])
        self.assertEqual([], db.links_for_task(tid))
        db.close()


if __name__ == "__main__":
    unittest.main()
