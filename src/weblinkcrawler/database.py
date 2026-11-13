"""SQLite 持久化：抓取任务 / 链接 / 体检结果。

- 沿用既有 crawling_tasks、crawled_links 表结构（向后兼容旧库）；
- 新增 link_checks 表用于链接体检；
- 单连接 + 锁 + WAL，支持抓取子线程并发写入；
- 全部参数化 SQL，防注入；启动时做轻量列迁移。
"""

from __future__ import annotations

import re
import sqlite3
import threading
from datetime import datetime

from .logutil import get_logger

log = get_logger()

DB_FILE = "crawling_progress.db"

_TASKS_COLUMNS = {
    "id", "url", "depth", "status", "start_time", "end_time",
    "total_links", "crawled_links",
}
_LINKS_COLUMNS = {
    "id", "task_id", "url", "link", "depth", "status", "file_name",
    "file_type", "file_size", "last_modified", "crawled_at",
}


class DatabaseManager:
    def __init__(self, db_file=DB_FILE):
        self.db_file = db_file
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(db_file, check_same_thread=False, timeout=30)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        with self._lock:
            cur = self._conn.cursor()
            try:
                cur.execute("PRAGMA journal_mode=WAL")
            except Exception:
                pass
            cur.execute("PRAGMA busy_timeout=30000")
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS crawling_tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT NOT NULL,
                    depth INTEGER NOT NULL,
                    status TEXT DEFAULT 'pending',
                    start_time DATETIME,
                    end_time DATETIME,
                    total_links INTEGER DEFAULT 0,
                    crawled_links INTEGER DEFAULT 0
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS crawled_links (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id INTEGER,
                    url TEXT NOT NULL,
                    link TEXT NOT NULL,
                    depth INTEGER NOT NULL,
                    status TEXT DEFAULT 'pending',
                    file_name TEXT,
                    file_type TEXT,
                    file_size INTEGER,
                    last_modified DATETIME,
                    crawled_at DATETIME,
                    FOREIGN KEY (task_id) REFERENCES crawling_tasks(id)
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS link_checks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id INTEGER,
                    link TEXT NOT NULL,
                    state TEXT,
                    status_code INTEGER,
                    checked_at DATETIME
                )
                """
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_links_task ON crawled_links(task_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_checks_task ON link_checks(task_id)")
            self._migrate_columns(cur, "crawling_tasks", _TASKS_COLUMNS)
            self._migrate_columns(cur, "crawled_links", _LINKS_COLUMNS)
            self._conn.commit()

    @staticmethod
    def _migrate_columns(cur, table, expected):
        """为旧库补齐缺失列。

        安全说明：``table`` / ``col`` 仅来自模块内的常量集合（_TASKS_COLUMNS /
        _LINKS_COLUMNS），不是用户输入；但仍用标识符白名单做二次约束，
        防止未来改动误把外部字符串带入 DDL。
        """
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table):
            log.warning("拒绝迁移：表名非法 %r", table)
            return
        cur.execute(f"PRAGMA table_info({table})")
        have = {row[1] for row in cur.fetchall()}
        for col in sorted(expected - have):
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", col):
                log.warning("拒绝迁移：列名非法 %r", col)
                continue
            try:
                cur.execute(f"ALTER TABLE {table} ADD COLUMN {col} TEXT")
                log.info("迁移: 为 %s 增加缺失列 %s", table, col)
            except Exception as e:
                log.warning("迁移列失败 %s.%s: %s", table, col, e)

    # ---- 任务 ----
    def create_task(self, url, depth, status="crawling"):
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                "INSERT INTO crawling_tasks (url, depth, status, start_time) VALUES (?, ?, ?, ?)",
                (url, depth, status, datetime.now().isoformat(timespec="seconds")),
            )
            self._conn.commit()
            return cur.lastrowid

    def update_task(self, task_id, status, end_time=None, total_links=None, crawled_links=None):
        fields, values = ["status = ?"], [status]
        if end_time is not None:
            fields.append("end_time = ?")
            values.append(end_time)
        if total_links is not None:
            fields.append("total_links = ?")
            values.append(total_links)
        if crawled_links is not None:
            fields.append("crawled_links = ?")
            values.append(crawled_links)
        values.append(task_id)
        with self._lock:
            self._conn.execute(
                f"UPDATE crawling_tasks SET {', '.join(fields)} WHERE id = ?", values
            )
            self._conn.commit()

    def pending_tasks(self):
        """未完成任务（含 stopped），按 id 升序，便于取每个 URL 最早的 task_id。"""
        with self._lock:
            cur = self._conn.execute(
                "SELECT id, url, depth FROM crawling_tasks "
                "WHERE status IN ('pending','crawling','stopped') ORDER BY id ASC"
            )
            return [(r["id"], r["url"], r["depth"]) for r in cur.fetchall()]

    def links_for_task(self, task_id):
        """返回任务已保存的链接记录 (source_url, link, depth)，按写入顺序。"""
        with self._lock:
            cur = self._conn.execute(
                "SELECT url, link, depth FROM crawled_links "
                "WHERE task_id = ? ORDER BY id",
                (task_id,),
            )
            return [(r["url"], r["link"], r["depth"]) for r in cur.fetchall()]

    def visited_for_task(self, task_id):
        """返回任务已抓取过的页面 URL 集合（去重）。"""
        with self._lock:
            cur = self._conn.execute(
                "SELECT DISTINCT url FROM crawled_links WHERE task_id = ?",
                (task_id,),
            )
            return {r["url"] for r in cur.fetchall() if r["url"]}

    # ---- 链接 ----
    def add_link(self, task_id, url, link, depth, file_name=None, file_type=None,
                 status="crawled", file_size=None, last_modified=None):
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO crawled_links
                    (task_id, url, link, depth, status, file_name, file_type,
                     file_size, last_modified, crawled_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (task_id, url, link, depth, status, file_name, file_type,
                 file_size, last_modified, datetime.now().isoformat(timespec="seconds")),
            )
            self._conn.commit()

    def add_links_bulk(self, rows):
        if not rows:
            return
        now = datetime.now().isoformat(timespec="seconds")
        payload = [
            (task_id, url, link, depth, status, file_name, file_type,
             file_size, last_modified, now)
            for (task_id, url, link, depth, file_name, file_type, file_size, last_modified, status)
            in rows
        ]
        with self._lock:
            self._conn.executemany(
                """
                INSERT INTO crawled_links
                    (task_id, url, link, depth, status, file_name, file_type,
                     file_size, last_modified, crawled_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                payload,
            )
            self._conn.commit()

    # ---- 体检 ----
    def add_check(self, task_id, link, state, status_code):
        with self._lock:
            self._conn.execute(
                "INSERT INTO link_checks (task_id, link, state, status_code, checked_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (task_id, link, state, status_code, datetime.now().isoformat(timespec="seconds")),
            )
            self._conn.commit()

    def add_checks_bulk(self, rows):
        if not rows:
            return
        now = datetime.now().isoformat(timespec="seconds")
        payload = [(task_id, link, state, code, now) for (task_id, link, state, code) in rows]
        with self._lock:
            self._conn.executemany(
                "INSERT INTO link_checks (task_id, link, state, status_code, checked_at) "
                "VALUES (?, ?, ?, ?, ?)",
                payload,
            )
            self._conn.commit()

    def close(self):
        try:
            with self._lock:
                self._conn.close()
        except Exception as e:
            log.warning("关闭数据库连接异常: %s", e)
