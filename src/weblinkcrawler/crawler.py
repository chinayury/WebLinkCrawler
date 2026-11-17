# Copyright (C) 2026 智维ITMSKY
# SPDX-License-Identifier: AGPL-3.0-or-later

"""抓取引擎：链接提取、并发爬取、链接体检与结构化导出。

本模块是 GUI（app.py）与测试（tests/test_core.py）共同依赖的稳定接口层，对外
暴露的名称与签名不得随意变更：
same_domain / CrawlerEngine
CrawlerEngine.fetch / extract_links / crawl / resume_pending / check_links / export
控制方法 stop / pause / resume / reset与只读属性 stopped

健壮性约定（与项目红线一致）：
-所有网络与解析异常一律在内部捕获并记录，绝不向 GUI抛出未捕获异常；
-每个线程持有独立的 requests.Session（线程本地），避免共享会话的并发不安全；
-初始 URL与每一次重定向都经 security.validate_target校验，且始终 verify=True；
-初始 URL与页面链接默认拦截私有/回环地址（network_policy.block_private_targets，
 可关闭）；域名解析失败按 fail-closed 拦截，解析结果按主机缓存；
-响应体按 network_policy.max_html_bytes截断，避免大文件耗尽内存。
"""

from __future__ import annotations

import csv
import json
import os
import random
import ssl
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin, urlsplit

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.connection import HTTPConnection, HTTPSConnection
from urllib3.connectionpool import HTTPConnectionPool, HTTPSConnectionPool
from urllib3.exceptions import NameResolutionError

from .config import canonical_key, normalize_url
from .logutil import get_logger
from .security import (
    UnsafeUrlError,
    is_ip_literal,
    is_private_host,
    resolve_pinned_ip,
    resolved_is_private,
    validate_target,
)

log = get_logger()

# 资源型标签：src或 href都可能承载链接
_RESOURCE_TAGS = ("img", "link", "script", "iframe", "area", "base")
# 支持 srcset 的标签
_SRCSET_TAGS = ("img", "source")
# 视为“重定向”的状态码
_REDIRECT_CODES = (301, 302, 303, 307, 308)
# 允许出现在结果中的协议（ftp/sftp 只用于分类，不交给 requests 请求）
_ALLOWED_SCHEMES = ("http", "https", "ftp", "sftp")
_HTTP_SCHEMES = ("http", "https")
_MAX_HTML_DEFAULT = 5 * 1024 * 1024
_REDIRECT_LIMIT = 5
_ROBOTS_MAX_BYTES = 512 * 1024
_ROBOTS_REDIRECT_LIMIT = 3
# robots 缓存容量上限（普通 dict + FIFO 淘汰，不引 LFU）
_ROBOTS_CACHE_LIMIT = 256
# per-host 节流簿记容量上限：极端多主机场景下丢弃最旧条目，避免无界增长
_THROTTLE_MAX_HOSTS = 4096
# per-host 节流抖动倍率：等待 interval ~ interval*2 之间均匀取
_THROTTLE_JITTER = 2.0
# 触发退避重试的状态码（限流/网关不可用/请求超时）
_RETRY_STATUS_CODES = (429, 503, 408)
# 429/503/408 的额外重试次数上限（受 request_strategy.retries 约束）
_STATUS_RETRY_LIMIT = 2
# Retry-After / 退避等待封顶（秒），与 request_strategy.retry_after_cap 默认值一致
_RETRY_AFTER_CAP_DEFAULT = 30
# 默认视为正常的体检状态码（可由 link_check.ok_status_codes 覆盖）
_DEFAULT_OK_STATUS_CODES = (200, 206, 999)
# 默认 HEAD 回退只读 GET 的状态码
_DEFAULT_HEAD_FALLBACK_CODES = (405, 501)
# 默认可解析子链接的 Content-Type
_DEFAULT_PARSEABLE_TYPES = ("text/html", "application/xhtml+xml", "text/plain")


class _PinnedHTTPSConnection(HTTPSConnection):
    """连接目标改用 pin_resolver 返回的 IP；SNI/证书校验保留原域名。

    DNS 重绑定 TOCTOU 防护的连接层落地（F-03 余项，docs/04 §10）：socket
    直连「校验过的 IP」，``server_hostname`` 保留域名，握手与证书校验语义
    与直连域名完全一致。IP 字面量/解析不可用时回退默认行为。
    """

    def __init__(self, *args, pin_resolver=None, **kwargs):
        self._pin_resolver = pin_resolver
        super().__init__(*args, **kwargs)

    def _new_conn(self):
        if self._pin_resolver is None:
            return super()._new_conn()
        try:
            ip = self._pin_resolver(self.host)
        except UnsafeUrlError as exc:
            # 转译为 urllib3 连接类异常：引擎/CLI 侧按 ConnectionError 语义处理
            raise NameResolutionError(self.host, self, exc) from exc
        if not ip or ip == self.host:
            return super()._new_conn()
        orig_host = self.host
        self.host = ip
        try:
            # super()._new_conn() 以 (ip, port) 建连；随后的 TLS 封装使用
            # __init__ 里显式传入的 server_hostname（原域名），语义不变
            return super()._new_conn()
        finally:
            self.host = orig_host


class _PinnedHTTPConnection(HTTPConnection):
    """HTTP 明文连接的同款钉定（无 TLS 语义，仅替换 socket 目标）。"""

    def __init__(self, *args, pin_resolver=None, **kwargs):
        self._pin_resolver = pin_resolver
        super().__init__(*args, **kwargs)

    def _new_conn(self):
        if self._pin_resolver is None:
            return super()._new_conn()
        try:
            ip = self._pin_resolver(self.host)
        except UnsafeUrlError as exc:
            raise NameResolutionError(self.host, self, exc) from exc
        if not ip or ip == self.host:
            return super()._new_conn()
        orig_host = self.host
        self.host = ip
        try:
            return super()._new_conn()
        finally:
            self.host = orig_host


class _PinnedHTTPSConnectionPool(HTTPSConnectionPool):
    """HTTPS 池：连接类替换为钉定版（池键/Host/SNI 均保留域名语义）。"""

    ConnectionCls = _PinnedHTTPSConnection


class _PinnedHTTPConnectionPool(HTTPConnectionPool):
    """HTTP 池：连接类替换为钉定版。"""

    ConnectionCls = _PinnedHTTPConnection


class _PinnedAdapter(HTTPAdapter):
    """按「解析后 IP」建连的适配器（DNS 重绑定 TOCTOU 防护）。

    注意：urllib3 2.8 的 PoolKey 会把 connection_pool_kw 的所有字段纳入
    池键构造（``key_<name>``），自定义 kwarg 直接破坏 PoolKey——因此
    pin_resolver 不能走池构造参数，改为包裹池管理器的
    ``connection_from_host``，在池首次创建后把 resolver 注入
    ``pool.conn_kw``（连接类在 ``_new_conn`` 时读取）。Host 头与 URL
    保留域名，socket 目标为 resolver 返回的 IP。代理池同样覆盖（教训同
    _SSLAdapter：只处理 init_poolmanager 会让代理用户静默失效）。
    """

    def __init__(self, *args, pin_resolver=None, **kwargs):
        self._pin_resolver = pin_resolver
        super().__init__(*args, **kwargs)

    def _pooled_schemes(self):
        return {
            "http": _PinnedHTTPConnectionPool,
            "https": _PinnedHTTPSConnectionPool,
        }

    def _inject_pinned_pools(self, manager):
        """替换池类并包裹池获取入口：池创建后注入 resolver 到 conn_kw。"""
        manager.pool_classes_by_scheme = self._pooled_schemes()
        resolver = self._pin_resolver
        if resolver is None:
            return
        original = manager.connection_from_host

        def connection_from_host(host, port=None, scheme="http", pool_kwargs=None):
            pool = original(host, port=port, scheme=scheme, pool_kwargs=pool_kwargs)
            if not getattr(pool, "_pin_resolver_injected", False):
                pool.conn_kw["pin_resolver"] = resolver
                pool._pin_resolver_injected = True
            return pool

        manager.connection_from_host = connection_from_host

    def init_poolmanager(self, *args, **kwargs):
        super().init_poolmanager(*args, **kwargs)
        self._inject_pinned_pools(self.poolmanager)

    def proxy_manager_for(self, proxy, **kwargs):
        manager = super().proxy_manager_for(proxy, **kwargs)
        self._inject_pinned_pools(manager)
        return manager


class _SSLAdapter(_PinnedAdapter):
    """遗留服务器 SSL 兼容适配器（由 network_policy.ssl_compat_legacy_servers 开启）。

    部分老站仍在使用 1024 位 RSA 证书或弱 DH 参数，OpenSSL 3 的默认安全级别
    (SECLEVEL=2) 会在握手阶段直接拒绝（EE certificate key too weak）。此处把
    安全级别降到 1 换取连通性，但仍然校验证书链与主机名，也不放回 SSLv3/TLS1.0。

    必须同时覆写 ``init_poolmanager`` 与 ``proxy_manager_for``：requests 的代理
    池走后者，只覆前者会让代理用户的兼容能力静默失效（本品按请求传 proxies）。
    """

    def _build_context(self):
        try:
            context = ssl.create_default_context()
        except Exception:
            return None
        try:
            context.set_ciphers("DEFAULT:@SECLEVEL=1")
            return context
        except ssl.SSLError:
            pass
        except Exception:
            return None
        # LibreSSL 等不支持 @SECLEVEL=1 时退回 DEFAULT
        try:
            fallback = ssl.create_default_context()
            fallback.set_ciphers("DEFAULT")
            return fallback
        except Exception:
            return None

    def init_poolmanager(self, *args, **kwargs):
        context = self._build_context()
        if context is not None:
            kwargs["ssl_context"] = context
        return super().init_poolmanager(*args, **kwargs)

    def proxy_manager_for(self, proxy, **kwargs):
        context = self._build_context()
        if context is not None:
            kwargs["ssl_context"] = context
        return super().proxy_manager_for(proxy, **kwargs)



def _csv_cell(value):
    """中和 CSV 公式注入（F-01）。

    链接等字段来自不可信第三方页面：以 = + - @ 或制表/回车开头的单元格，
    在 Excel/WPS 中会被当公式执行（HYPERLINK 外带数据、cmd|'...'!A1
    走 DDE）。统一加单引号前缀（Excel 转义惯例，不改变显示内容）。
    txt/json 不是公式执行面，无需处理。
    """
    text = "" if value is None else str(value)
    if text[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + text
    return text


def same_domain(a, b):
    """判断两个 URL是否属于同一主机（host:port相同）。解析失败或缺少主机名返回 False。"""
    try:
        netloc_a = urlsplit(a).netloc.lower()
        netloc_b = urlsplit(b).netloc.lower()
    except Exception:
        return False
    if not netloc_a or not netloc_b:
        return False
    return netloc_a == netloc_b


def _canonical_dedup_key(link, rules):
    """按去重规则生成 canonical key；规则关闭或异常时退回原始链接本身。"""
    enabled, strip_params, keep_params = rules
    if not enabled:
        return link
    try:
        return canonical_key(link, strip_params, keep_params) or link
    except Exception as exc:
        log.debug("生成去重键失败(%s): %s", type(exc).__name__)
        return link


class CrawlerEngine:
    """抓取引擎：单请求抓取、递归爬取、断点续爬、链接体检与导出。"""

    def __init__(self, config, db=None):
        self.config = config
        self.db = db
        # 线程本地会话：每个工作线程各持一个 requests.Session，避免共享连接池
        self._tls = threading.local()
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._robots_cache = {}
        self._robots_lock = threading.Lock()
        # robots 按 root 的 in-flight 锁表：同站一次在飞、跨站并行
        self._robots_inflight = {}
        self._throttle_lock = threading.Lock()
        # per-host 节流簿记：{host: 下次可请求时刻}（空键为全局桶）
        self._throttle_next = {}
        # 主机私有属性解析缓存：{host: True/False/None}，None=解析失败（fail-closed，F-03）
        self._private_host_cache = {}
        self._private_host_lock = threading.Lock()

    # ------------------------------------------------------------------
    # 会话与控制
    # ------------------------------------------------------------------
    @property
    def session(self):
        """返回当前线程独占的 requests.Session（首次访问时创建）。"""
        session = getattr(self._tls, "session", None)
        if session is None:
            session = requests.Session()
            resolver = self._pinned_resolver()
            if self._ssl_compat_enabled():
                session.mount("https://", _SSLAdapter(pin_resolver=resolver))
                session.mount("http://", _PinnedAdapter(pin_resolver=resolver))
            else:
                session.mount("https://", _PinnedAdapter(pin_resolver=resolver))
                session.mount("http://", _PinnedAdapter(pin_resolver=resolver))
            self._tls.session = session
        return session

    def _pinned_resolver(self):
        """构造建连解析器：解析 + 私有地址判定一次完成（重绑定防护）。

        allow_private 取 network_policy.block_private_targets 的反义：
        用户显式放行内网站点时，私有地址正常返回用于建连。
        """
        def resolver(host):
            allow_private = not self._block_private_targets()
            return resolve_pinned_ip(host, allow_private=allow_private)
        return resolver

    def _block_private_targets(self):
        try:
            return self.config.get_bool(
                "network_policy", "block_private_targets", default=True,
            )
        except Exception:
            return True

    def _ssl_compat_enabled(self):
        """是否启用遗留服务器 SSL 兼容（默认关闭，不改变现有行为）。"""
        try:
            return self.config.get_bool(
                "network_policy", "ssl_compat_legacy_servers", default=False,
            )
        except Exception:
            return False

    def stop(self):
        """请求停止抓取：置停止位并唤醒处于暂停等待中的线程。"""
        self._stop_event.set()
        # 清暂停位，否则等待中的线程永远醒不来
        self._pause_event.clear()

    def pause(self):
        """暂停抓取（工作线程在下一个检查点等待）。"""
        self._pause_event.set()

    def resume(self):
        """仅恢复 pause()造成的暂停，不会让已 stop()的任务重新运行。"""
        self._pause_event.clear()

    def reset(self):
        """清空停止/暂停状态，供新一轮抓取使用。"""
        self._stop_event.clear()
        self._pause_event.clear()

    @property
    def stopped(self):
        return self._stop_event.is_set()

    def _wait_if_paused(self):
        """暂停期间原地等待；一旦被 stop()唤醒立即返回。"""
        while self._pause_event.is_set() and not self._stop_event.is_set():
            time.sleep(0.1)

    @staticmethod
    def _emit(on_event, kind, *args):
        """安全触发事件回调：回调自身抛错不影响抓取。"""
        if on_event is None:
            return
        try:
            on_event(kind, *args)
        except Exception as exc:
            log.debug("事件回调异常(%s): %s", kind, type(exc).__name__)

    @staticmethod
    def _safe_close(response):
        if response is None:
            return
        try:
            response.close()
        except Exception:
            pass

    @staticmethod
    def _backoff_seconds(interval, attempt):
        """指数退避：interval * 2^attempt，上限 30 秒。"""
        try:
            base = float(interval or 0)
        except (TypeError, ValueError):
            base = 0.0
        if base <= 0:
            return 0.0
        return min(base * (2 ** max(0, attempt)), 30.0)

    @staticmethod
    def _parse_retry_after(value):
        """解析 Retry-After：纯数字按秒、HTTP 日期按秒差；无法解析返回 None。

        借鉴 site-crawler 的 fetch_with_retry：只有能真正解读的 Retry-After
        才被采纳，否则退回指数退避，绝不把无法解析的值当成 0 秒立即重试。
        """
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        if text.isascii() and text.isdigit():
            try:
                return max(0.0, float(text))
            except (TypeError, ValueError, OverflowError):
                return None
        try:
            moment = parsedate_to_datetime(text)
        except (TypeError, ValueError, OverflowError, IndexError):
            return None
        if moment is None:
            return None
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        try:
            delta = (moment - datetime.now(timezone.utc)).total_seconds()
        except (TypeError, ValueError, OverflowError):
            return None
        # 已过去的时间视为 0（可立即重试），不返回负值
        return max(0.0, delta)

    def _retry_after_cap(self):
        """Retry-After / 退避等待的封顶秒数（0~300，默认 30）。"""
        try:
            return self.config.get_int(
                "anti_anti_crawl", "request_strategy", "retry_after_cap",
                default=_RETRY_AFTER_CAP_DEFAULT, lo=0, hi=300,
            )
        except Exception:
            return _RETRY_AFTER_CAP_DEFAULT

    def _retry_wait(self, response, attempt):
        """计算 429/503/408 的重试等待：优先 Retry-After，否则指数退避，统一封顶。"""
        cap = self._retry_after_cap()
        if cap <= 0:
            return 0.0
        wait = None
        try:
            raw = response.headers.get("Retry-After")
        except Exception:
            raw = None
        parsed = self._parse_retry_after(raw)
        if parsed is not None:
            wait = parsed
        else:
            try:
                interval = float(self.config.request_params()[5] or 0)
            except Exception:
                interval = 0.0
            wait = self._backoff_seconds(interval, attempt)
        try:
            return max(0.0, min(float(wait), cap))
        except (TypeError, ValueError, OverflowError):
            return 0.0

    def _fetch_with_retry(self, url, on_event=None):
        """抓取页面；429/503/408 按 Retry-After 或指数退避重试后再交调用方。

        修复旧版污染缺陷：旧实现对任意响应体直接抽链，429 错误页里的整站布局
        链接会被当成页面链接收进来。现对限流类状态码先退避重试，次数用尽返回
        None（由调用方按失败记录且不抽链）。
        """
        try:
            retries = self.config.get_int(
                "anti_anti_crawl", "request_strategy", "retries",
                default=3, lo=0, hi=10,
            )
        except Exception:
            retries = 3
        attempts = 1 if retries <= 0 else min(retries, _STATUS_RETRY_LIMIT) + 1

        for attempt in range(attempts):
            if self.stopped:
                return None
            response = self.fetch(url, method="GET")
            if response is None:
                return None
            code = getattr(response, "status_code", None)
            if code not in _RETRY_STATUS_CODES:
                return response
            wait = self._retry_wait(response, attempt)
            self._safe_close(response)
            if attempt >= attempts - 1:
                self._emit(on_event, "log", "warn",
                    f"[放弃重试] {self._safe_url(url)} 持续返回 {code}")
                return None
            self._emit(on_event, "log", "warn",
                f"[{code} 限流] {self._safe_url(url)}，{wait:.1f}秒后重试"
                f"（{attempt + 1}/{attempts - 1}）")
            if wait > 0:
                self._stop_event.wait(wait)
        return None

    # ------------------------------------------------------------------
    # robots.txt（由 network_policy.respect_robots 控制）
    # ------------------------------------------------------------------
    def _robots(self, url):
        """读取并缓存站点 robots.txt 的 Disallow/Allow 规则与 Crawl-delay。

        仅采纳 ``User-agent: *`` 分组；支持 ``*`` 通配与 ``$`` 结束锚定
        （参考 reppy / google-robotstxt 的做法），避免旧版仅做前缀匹配导致
        ``/private/*`` 这类规则完全失效。

        并发去重（借鉴 linkchecker 的 cache/robots_txt.py）：先查缓存，未命中
        按 root 取 in-flight 锁，锁内二次查缓存后才真正抓取——同站一次在飞、
        跨站并行、全局一份缓存。严禁把 ``_robots_lock`` 放宽罩住抓取：同一路径
        上「读缓存」与「写缓存」两次 acquire 会自死锁，故另设专用锁表。
        """
        try:
            parts = urlsplit(url)
            scheme = parts.scheme.lower()
            netloc = parts.netloc.lower()
        except Exception:
            return [], 0.0
        if scheme not in _HTTP_SCHEMES or not netloc:
            return [], 0.0

        root = f"{scheme}://{netloc}"
        with self._robots_lock:
            cached = self._robots_cache.get(root)
        if cached is not None:
            return cached

        with self._root_lock(root):
            with self._robots_lock:
                cached = self._robots_cache.get(root)
            if cached is not None:
                return cached
            disallow, delay = [], 0.0
            response = None
            try:
                try:
                    headers, proxies, cookies, timeout, _retries, _interval = (
                    self.config.request_params()
                    )
                except Exception:
                    headers = {"User-Agent": "WebLinkCrawler"}
                    proxies = cookies = None
                    timeout = 8

                # 修复 SSRF 缺口：旧版此处 allow_redirects=True，robots.txt 一旦被
                # 302 到任意主机（含内网地址）就会无条件跟随。现改为手动跟随，
                # 每一跳都过一次安全校验。
                robots_url = f"{root}/robots.txt"
                response = self._request(
                    "GET", robots_url, headers, proxies, cookies, timeout,
                )
                if response is not None:
                    try:
                        block_private = self.config.get_bool(
                            "network_policy", "block_private_redirects", default=True,
                        )
                    except Exception:
                        block_private = True
                    response = self._follow_redirects(
                        response, "GET", robots_url, headers, proxies, cookies,
                        timeout, _ROBOTS_REDIRECT_LIMIT, follow=True,
                        block_private=block_private,
                    )
                if response is not None and response.status_code == 200:
                    body = bytearray()
                    for chunk in response.iter_content(chunk_size=65536):
                        if chunk:
                            body.extend(chunk)
                            if len(body) >= _ROBOTS_MAX_BYTES:
                                break
                    text = bytes(body).decode("utf-8", errors="replace")
                    allow, agent_matches = [], False
                    for line in text.splitlines():
                        line = line.split("#", 1)[0].strip()
                        if not line or ":" not in line:
                            continue
                        key, value = line.split(":", 1)
                        key = key.strip().lower()
                        value = value.strip()
                        if key == "user-agent":
                            # 只采纳 User-agent: * 分组；进入其他分组即停止收集
                            agent_matches = value == "*"
                        elif not agent_matches:
                            continue
                        elif key == "disallow" and value:
                            disallow.append(value)
                        elif key == "allow" and value:
                            allow.append(value)
                        elif key == "crawl-delay":
                            try:
                                delay = max(0.0, float(value))
                            except (TypeError, ValueError):
                                delay = 0.0
                    if allow:
                        # 统一以 (类型, 规则) 二元组返回，避免调用方还要分辨两种格式
                        disallow = ([("allow", p) for p in allow]
                                    + [("disallow", p) for p in disallow])
                    else:
                        disallow = [("disallow", p) for p in disallow]
            except Exception as exc:
                # robots 读取失败按放行处理（可用性优先），但必须留痕（F-09）
                log.warning("robots.txt 读取失败，按放行处理(%s): %s", root, type(exc).__name__)
                disallow, delay = [], 0.0
            finally:
                self._safe_close(response)

            # 统一为 [(kind, pattern), ...]；kind 取 "allow" / "disallow"
            normalized = [(kind, str(pattern))
                          for kind, pattern in disallow
                          if isinstance(pattern, str) and pattern]
            result = (normalized, delay)
            self._store_robots(root, result)
            return result

    def _root_lock(self, root):
        """取（或创建）某个 robots root 的专用互斥量，仅护锁表本身。"""
        with self._robots_lock:
            lock = self._robots_inflight.get(root)
            if lock is None:
                lock = threading.Lock()
                self._robots_inflight[root] = lock
            return lock

    def _store_robots(self, root, result):
        """写入 robots 缓存；超过容量上限时 FIFO 淘汰（普通 dict，不引 LFU）。"""
        with self._robots_lock:
            if root not in self._robots_cache and len(self._robots_cache) >= _ROBOTS_CACHE_LIMIT:
                for stale in list(self._robots_cache)[:max(1, _ROBOTS_CACHE_LIMIT // 4)]:
                    self._robots_cache.pop(stale, None)
                    # 只清理未被持有的 in-flight 锁，避免误伤正在抓取的线程
                    stale_lock = self._robots_inflight.get(stale)
                    if stale_lock is not None and not stale_lock.locked():
                        self._robots_inflight.pop(stale, None)
            self._robots_cache[root] = result

    def robots_allows(self, url):
        """robots.txt 是否允许抓取该 URL；任何异常都按"允许"处理。

        规则按 RFC 9309 的"最长匹配优先"：命中 Allow 的长度不小于命中的
        Disallow 长度时视为允许。
        """
        try:
            if not self.config.get_bool("network_policy", "respect_robots", default=True):
                return True
            rules, _delay = self._robots(url)
            path = urlsplit(url).path or "/"
            matched_allow = -1
            matched_disallow = -1
            for kind, pattern in rules:
                if not pattern:
                    continue
                length = self._robots_match_length(path, pattern)
                if length is None:
                    continue
                if kind == "allow":
                    matched_allow = max(matched_allow, length)
                else:
                    matched_disallow = max(matched_disallow, length)
            if matched_disallow < 0:
                return True
            return matched_allow >= matched_disallow
        except Exception as exc:
            # robots 判定异常按放行处理（可用性优先），但必须留痕（F-09）
            log.warning("robots 判定异常，按放行处理(%s): %s", self._safe_url(url), type(exc).__name__)
            return True

    @staticmethod
    def _robots_match_length(path, pattern):
        """返回规则在 path 上命中的前缀长度；未命中返回 None。

        支持 ``*`` 通配（任意长度）与 ``$`` 结束锚定，与主流 robots 解析器
        （reppy / google-robotstxt）语义一致。
        """
        try:
            if pattern.endswith("$"):
                body = pattern[:-1]
                anchored = True
            else:
                body = pattern
                anchored = False
            segments = body.split("*")
            if len(segments) == 1:
                # 无通配：纯前缀匹配
                if path.startswith(body):
                    return len(body)
                return None
            index = 0
            for position, segment in enumerate(segments):
                if not segment:
                    continue
                found = path.find(segment, index)
                if found < 0:
                    return None
                if position == 0 and found != 0:
                    return None
                index = found + len(segment)
            if anchored and index != len(path):
                return None
            return index
        except Exception:
            return None

    # ------------------------------------------------------------------
    # 单请求：重试 + 指数退避 + 安全校验 + 体积上限
    # ------------------------------------------------------------------
    def _request(self, method, url, headers, proxies, cookies, timeout):
        """发出单个请求（不自动跟随重定向）；异常交由调用方处理。"""
        self._throttle(url)
        return self.session.request(
            method,
            url,
            headers=headers,
            proxies=proxies,
            cookies=cookies,
            timeout=timeout,
            allow_redirects=False,
            verify=True,
            stream=True,
        )

    @staticmethod
    def _host_key(url):
        """节流簿记的键：取 URL的 host:port（与 robots 的 root 键口径一致）。"""
        try:
            netloc = urlsplit(str(url or "")).netloc.lower()
        except Exception:
            netloc = ""
        return netloc or "*"

    def _throttle(self, url=None):
        """请求节流：按主机维护「下次可请求时刻」簿记 + 均匀抖动。

        借鉴 linkchecker 的 per-host 节流（aggregator.wait_for_host）：快站点
        不再被慢站点的槽位挤后，不同主机之间互不等待。未提供 url 时退化为
        全局桶，兼容不关心主机的调用方。

        节流与"重试指数退避"是两个独立职责：前者约束正常请求的节奏，
        后者只作用于失败重试。等待在锁外按 ≤0.25s 切片，保证可被 stop 唤醒。
        """
        try:
            interval = float(self.config.throttle_interval() or 0)
        except Exception:
            interval = 0.0
        if interval <= 0:
            return
        key = self._host_key(url)
        while True:
            with self._throttle_lock:
                now = time.monotonic()
                wait = self._throttle_next.get(key, 0.0) - now
                if wait <= 0:
                    self._throttle_next[key] = now + random.uniform(
                        interval, interval * _THROTTLE_JITTER,
                    )
                    if len(self._throttle_next) > _THROTTLE_MAX_HOSTS:
                        # 容量保护：极端多主机场景下丢弃最旧的一半条目
                        for stale in list(self._throttle_next)[:_THROTTLE_MAX_HOSTS // 2]:
                            self._throttle_next.pop(stale, None)
                    return
            # 在锁外等待，保证可被 stop 及时唤醒
            if self._stop_event.wait(min(wait, 0.25)):
                return

    @staticmethod
    def _safe_url(url):
        """日志脱敏：仅保留 scheme://host/path，去掉 query / fragment / userinfo。"""
        try:
            parts = urlsplit(str(url or ""))
        except Exception:
            return "<invalid-url>"
        if not parts.scheme or not parts.netloc:
            return "<invalid-url>"
        netloc = parts.netloc
        if "@" in netloc:
            netloc = netloc.split("@", 1)[1]
        return f"{parts.scheme.lower()}://{netloc}{parts.path or '/'}"

    def _block_private_targets(self):
        """是否对抓取目标（种子 URL 与页面链接）拦截私有/回环地址（F-04，默认开启）。"""
        try:
            return self.config.get_bool(
                "network_policy", "block_private_targets", default=True
            )
        except Exception:
            return True

    def _host_is_blocked_private(self, host):
        """按 fail-closed 判定主机是否私有/回环（带缓存，F-03/F-04）。

        字面 IP 直接判定（零成本）；域名解析一次并按 host 缓存，
        避免每次请求都做 DNS。解析失败（None）一律按不安全处理。
        """
        if not host:
            return False
        if is_private_host(host):
            return True
        if is_ip_literal(host):
            return False
        with self._private_host_lock:
            cached = self._private_host_cache.get(host)
            known = host in self._private_host_cache
        if not known:
            cached = resolved_is_private(host)
            with self._private_host_lock:
                self._private_host_cache[host] = cached
        return cached is None or bool(cached)

    def _check_redirect_target(self, url, block_private):
        """校验单个重定向目标；不合法时抛出 UnsafeUrlError。"""
        if not block_private:
            validate_target(url)
            return
        validate_target(url, follow_redirect=True, allow_private=False)
        host = urlsplit(url).hostname
        if self._host_is_blocked_private(host):
            raise UnsafeUrlError("重定向目标属于私有/回环地址或无法解析，已按策略拦截")

    def _follow_redirects(self, response, method, origin_url, headers, proxies,
        cookies, timeout, max_redirects, follow=True, block_private=None):
        """手动跟随重定向：允许跨主机，但受 max_redirects 与私有重定向策略约束。

        block_private 为 None 时按配置读取；显式传入可让 robots.txt 抓取
        等场景复用同一套安全校验。
        """
        if block_private is None:
            try:
                block_private = self.config.get_bool(
                    "network_policy", "block_private_redirects", default=True
                )
            except Exception:
                block_private = True

        current_url = origin_url
        redirects = 0
        while response is not None and response.status_code in _REDIRECT_CODES:
            if not follow:
                break
            location = (response.headers.get("Location") or "").strip()
            if not location:
                break
            if redirects >= max_redirects:
                log.warning("重定向次数超过上限 %s，已停止: %s",
                    max_redirects, self._safe_url(origin_url))
                self._safe_close(response)
                return None
            try:
                next_url = urljoin(current_url, location)
            except Exception as exc:
                log.error("解析重定向地址失败 %s: %s",
                    self._safe_url(current_url), type(exc).__name__)
                self._safe_close(response)
                return None
            try:
                self._check_redirect_target(next_url, block_private)
            except UnsafeUrlError as exc:
                log.warning("重定向目标不符合安全策略，已停止 %s -> %s: %s",
                    self._safe_url(current_url), self._safe_url(next_url),
                    type(exc).__name__)
                self._safe_close(response)
                return None
            except Exception as exc:
                log.error("校验重定向目标异常 %s: %s",
                    self._safe_url(next_url), type(exc).__name__)
                self._safe_close(response)
                return None
            self._safe_close(response)
            redirects += 1
            current_url = next_url
            try:
                response = self._request(method, next_url, headers, proxies,
                    cookies, timeout)
            except Exception as exc:
                log.error("重定向后请求失败 %s: %s",
                    self._safe_url(next_url), type(exc).__name__)
                return None
        return response

    def _read_body(self, response, max_html):
        """按上限读取响应体，并把结果写回 response，使 .text可直接使用。"""
        body = bytearray()
        try:
            for chunk in response.iter_content(chunk_size=65536):
                if not chunk:
                    continue
                body.extend(chunk)
                if len(body) >= max_html:
                    del body[max_html:]
                    log.warning("响应体超过上限 %s字节，已截断", max_html)
                    break
        except Exception as exc:
            log.warning("读取响应体失败: %s", type(exc).__name__)
        finally:
            self._safe_close(response)
        try:
            response._content = bytes(body)
            response._content_consumed = True
        except Exception:
            pass
        return response

    def _perform(self, url, method="GET", follow_redirects=True, read_body=True):
        """执行一次（含重试与重定向）HTTP请求；失败返回 None，不抛异常。

        read_body=False 时返回「只读状态/响应头、不读 body」的 GET 变体：
        用于 HEAD 被拒后的回退探测，避免把一次回退放大成整站轻量抓取
        （GET 分支默认会读至 max_html_bytes）。
        """
        try:
            validate_target(url, allow_private=not self._block_private_targets())
        except UnsafeUrlError as exc:
            log.warning("目标地址不安全，已跳过 %s: %s", self._safe_url(url), type(exc).__name__)
            return None
        except Exception as exc:
            log.error("校验目标地址异常(%s): %s", self._safe_url(url), type(exc).__name__)
            return None

        method = (method or "GET").upper()
        try:
            headers, proxies, cookies, timeout, retries, interval = (
            self.config.request_params()
            )
        except Exception as exc:
            log.error("读取请求参数失败，改用默认值: %s", type(exc).__name__)
            headers, proxies, cookies, timeout, retries, interval = (
            {}, None, None, 10, 1, 0,
            )

        try:
            max_html = self.config.get_int(
                "network_policy", "max_html_bytes",
                default=_MAX_HTML_DEFAULT, lo=1, hi=100 * 1024 * 1024,
            )
            max_redirects = self.config.get_int(
                "network_policy", "max_redirects",
                default=_REDIRECT_LIMIT, lo=0, hi=20,
            )
        except Exception:
            max_html, max_redirects = _MAX_HTML_DEFAULT, _REDIRECT_LIMIT

        try:
            attempts = max(1, int(retries or 1))
        except (TypeError, ValueError):
            attempts = 1

        for attempt in range(attempts):
            if self.stopped:
                return None
            self._wait_if_paused()

            try:
                response = self._request(
                    method, url, headers, proxies, cookies, timeout,
                )
            except requests.RequestException as exc:
                log.debug("请求失败(%s/%s) %s: %s", attempt + 1, attempts, self._safe_url(url), type(exc).__name__)
                if attempt < attempts - 1:
                    delay = self._backoff_seconds(interval, attempt)
                    if delay > 0:
                        # 用 stop 事件等待，停止指令可即时生效（最长 30s 退避）
                        self._stop_event.wait(delay)
                continue
            except Exception as exc:
                log.error("请求异常(%s): %s", self._safe_url(url), type(exc).__name__)
                return None

            try:
                response = self._follow_redirects(
                    response, method, url, headers, proxies, cookies,
                    timeout, max_redirects, follow=follow_redirects,
                )
            except Exception as exc:
                log.error("处理重定向异常(%s): %s", self._safe_url(url), type(exc).__name__)
                self._safe_close(response)
                return None

            if response is None:
                return None

            # HEAD 与「只读 GET」都只需要响应头，关闭响应体后直接返回
            if method == "HEAD" or not read_body:
                self._safe_close(response)
                return response

            try:
                return self._read_body(response, max_html)
            except Exception as exc:
                log.error("读取响应异常(%s): %s", self._safe_url(url), type(exc).__name__)
                self._safe_close(response)
                return None

        log.debug("请求在 %s次尝试后仍失败: %s", attempts, self._safe_url(url))
        return None

    def fetch(self, url, method="GET"):
        """抓取单个 URL并返回 requests.Response；任何失败返回 None（不抛异常）。

        GET会读取响应体（上限 network_policy.max_html_bytes，可直接用 .text取文本）；
        HEAD关闭响应体后返回，便于读取 Content-Length等头部。
        """
        return self._perform(url, method=method, follow_redirects=True)
    @staticmethod
    def _decode(response):
        """把响应解码为文本；无法判定编码时回退 apparent_encoding / utf-8。"""
        if response is None:
            return ""
        try:
            encoding = (response.encoding or "").lower()
            if not encoding or encoding in ("iso-8859-1", "ascii"):
                response.encoding = response.apparent_encoding or "utf-8"
        except Exception:
            try:
                response.encoding = "utf-8"
            except Exception:
                pass
        try:
            return response.text or ""
        except Exception as exc:
            log.warning("响应解码失败: %s", type(exc).__name__)
            return ""

    # ------------------------------------------------------------------
    # 链接提取
    # ------------------------------------------------------------------
    def extract_links(self, html, base_url, css_selector=""):
        """从 HTML中提取规范化后的绝对链接（去重、保持出现顺序）。

        提取范围：a[href]；img/link/script/iframe/area/base的 src|href；
        img/source的 srcset。CSS选择器为空、非法或选不到元素时回退整页。
        """
        if not html:
            return []
        if isinstance(html, bytes):
            html = html.decode("utf-8", errors="replace")
        elif not isinstance(html, str):
            html = self._decode(html)
        if not html:
            return []

        try:
            soup = BeautifulSoup(html, "html.parser")
        except Exception as exc:
            log.warning("HTML解析失败(%s): %s", self._safe_url(base_url), type(exc).__name__)
            return []

        targets = [soup]
        selector = (css_selector or "").strip()
        if selector:
            selected = []
            try:
                selected = soup.select(selector)
            except Exception as exc:
                log.warning("CSS选择器无效(%s)，回退整页: %s", selector, exc)
                selected = []
            # 选择器选到空结果同样回退整页，避免误判“页面无链接”
            if selected:
                targets = selected

        raw = []
        for target in targets:
            try:
                for anchor in target.find_all("a", href=True):
                    raw.append(anchor.get("href"))
                for tag in target.find_all(_RESOURCE_TAGS):
                    raw.append(tag.get("src") or tag.get("href"))
                for tag in target.find_all(_SRCSET_TAGS):
                    srcset = tag.get("srcset")
                    if not srcset:
                        continue
                    for part in str(srcset).split(","):
                        part = part.strip()
                        if not part:
                            continue
                        pieces = part.split()
                        if pieces and pieces[0]:
                            raw.append(pieces[0])
            except Exception as exc:
                log.debug("遍历标签异常(%s): %s", self._safe_url(base_url), type(exc).__name__)

        return self._normalize_links(raw, base_url)

    def _normalize_links(self, raw_links, base_url):
        """把原始 href/src规范化为绝对链接：过滤无效协议、应用排除规则并去重保序。

        去重采用「raw URL + canonical key」双轨制（借鉴 scrapy 的
        LxmlLinkExtractor）：返回的始终是原始绝对链接，canonical key 只作为
        去重键，导出入库一律写原始 URL。
        """
        output = []
        seen = set()
        seen_keys = set()
        dedup_rules = self._dedup_query_rules()
        for raw in raw_links:
            if not raw:
                continue
            href = str(raw).strip()
            if not href:
                continue
            if href.lower().startswith(("#", "javascript:", "mailto:", "tel:", "data:")):
                continue
            try:
                absolute = normalize_url(urljoin(str(base_url or ""), href))
            except Exception:
                continue
            if not absolute:
                continue
            try:
                if urlsplit(absolute).scheme.lower() not in _ALLOWED_SCHEMES:
                    continue
            except Exception:
                continue
            if len(absolute) >8192:
                continue
            if absolute in seen:
                continue
            key = _canonical_dedup_key(absolute, dedup_rules)
            if key in seen_keys:
                continue
            try:
                if self.config.excluded(absolute):
                    continue
            except Exception as exc:
                log.debug("排除规则匹配异常(%s): %s", self._safe_url(absolute), type(exc).__name__)
            seen.add(absolute)
            seen_keys.add(key)
            output.append(absolute)
        return output

    def _dedup_query_rules(self):
        """读取 query 去重黑白名单；异常时按默认启用，绝不影响主流程。"""
        try:
            return self.config.dedup_query_rules()
        except Exception as exc:
            log.debug("读取 query 去重配置失败，按默认启用: %s", type(exc).__name__)
            return True, None, None

    # ------------------------------------------------------------------
    # 文件大小 / 最后修改时间过滤
    # ------------------------------------------------------------------
    def _passes_file_filters(self, link):
        """按 Content-Length（MB）与 Last-Modified（天）判断文件链接是否保留。

        未开启过滤、非文件链接、或无法拿到元数据时一律保留；异常不得向外抛出。
        """
        try:
            if not self.config.enhanced_enabled:
                return True
            if not self.config.get_bool("file_filters", "enabled", default=True):
                return True
            size_on = self.config.get_bool(
                "file_filters", "size_filter", "enabled", default=False,
            )
            time_on = self.config.get_bool(
                "file_filters", "time_filter", "enabled", default=False,
            )
            if not (size_on or time_on):
                return True
            if not self.config.is_file_link(link):
                return True

            min_mb = self.config.get_float(
                "file_filters", "size_filter", "min_size", default=0,
            )
            max_mb = self.config.get_float(
                "file_filters", "size_filter", "max_size", default=0,
            )
            days = self.config.get_int(
                "file_filters", "time_filter", "days", default=7,
            )
        except Exception as exc:
            log.debug("读取文件过滤配置失败，保留 %s: %s", self._safe_url(link), type(exc).__name__)
            return True

        response = None
        try:
            response = self.fetch(link, method="HEAD")
            if response is None or getattr(response, "status_code", None) != 200:
                return True
            headers = getattr(response, "headers", None) or {}

            if size_on:
                raw_length = headers.get("Content-Length")
                try:
                    length = int(str(raw_length).strip())
                except (TypeError, ValueError):
                    length = None
                if length is not None and length >= 0:
                    size_mb = length / (1024 * 1024)
                    if min_mb > 0 and size_mb < min_mb:
                        return False
                    if max_mb > 0 and size_mb > max_mb:
                        return False

            if time_on:
                modified = headers.get("Last-Modified")
                if modified:
                    try:
                        mod_dt = parsedate_to_datetime(modified)
                        if mod_dt is not None:
                            if mod_dt.tzinfo is None:
                                mod_dt = mod_dt.replace(tzinfo=timezone.utc)
                            threshold = datetime.now(timezone.utc) - timedelta(
                            days=max(0, days)
                            )
                            if mod_dt < threshold:
                                return False
                    except (TypeError, ValueError, OverflowError):
                        pass
            return True
        except Exception as exc:
            log.debug("文件过滤判定异常，保留 %s: %s", self._safe_url(link), type(exc).__name__)
            return True
        finally:
            self._safe_close(response)

    def _filter_records(self, records):
        """对记录列表应用文件过滤；单条判定异常时保留该条。

        修复旧版缺陷：旧实现逐条串行发起 HEAD，几千个文件链接会把
        主流程卡死数分钟。现改为并发探测，单个元数据只取一次。
        """
        kept = list(records or [])
        if not kept:
            return kept
        try:
            if not self.config.enhanced_enabled:
                return kept
            if not self.config.get_bool("file_filters", "enabled", default=True):
                return kept
            size_on = self.config.get_bool("file_filters", "size_filter", "enabled",
                                            default=False)
            time_on = self.config.get_bool("file_filters", "time_filter", "enabled",
                                           default=False)
            if not (size_on or time_on):
                return kept
        except Exception as exc:
            log.debug("读取文件过滤配置失败，保留全部: %s", type(exc).__name__)
            return kept

        # 只对"可能需要元数据"的文件链接做并发探测
        candidates = []
        for index, record in enumerate(kept):
            link = self._record_get(record, "link")
            try:
                if link and self.config.is_file_link(link):
                    candidates.append((index, link))
            except Exception:
                continue
        if not candidates:
            return kept

        meta = {}

        def probe(item):
            index, link = item
            if self.stopped:
                return index, True
            try:
                ok = self._passes_file_filters(link)
            except Exception:
                ok = True
            return index, ok

        try:
            concurrency = max(2, int(self.config.concurrency))
        except Exception:
            concurrency = 4
        executor = ThreadPoolExecutor(max_workers=min(concurrency, len(candidates)))
        try:
            for index, ok in executor.map(probe, candidates):
                if not ok:
                    kept[index] = None
        finally:
            executor.shutdown(wait=True)
        return [record for record in kept if record is not None]

    # ------------------------------------------------------------------
    # 递归抓取（BFS + 有界并发）
    # ------------------------------------------------------------------
    def crawl(self, urls, on_event=None, resume_tasks=None):
        """按层（BFS）抓取链接，返回 [{"link": str, "depth": int}]。

        -每层使用 ThreadPoolExecutor(max_workers=config.concurrency)并发；
        -全局 max_pages上限，超限后停止扩展；
        -仅对同域、非文件、未被排除的链接继续下钻；
        -事件：("log", level, message) / ("page", url, count, depth) / ("done", records)。
        记录中的 depth表示“发现该链接的页面所在层级”（0表示来自起始页）。
        resume_tasks仅供断点续爬内部使用：{起始 URL：既有 task_id}，默认 None。
        """
        try:
            max_depth = max(0, int(self.config.max_depth))
        except Exception:
            max_depth = 0
        try:
            max_pages = max(1, int(self.config.max_pages))
        except Exception:
            max_pages = 1
        try:
            concurrency = max(1, int(self.config.concurrency))
        except Exception:
            concurrency = 1
        try:
            selector = self.config.css_selector or ""
        except Exception:
            selector = ""

        resume_map = resume_tasks if isinstance(resume_tasks, dict) else {}

        start_urls = []
        for raw in urls or []:
            try:
                candidate = normalize_url(raw)
            except Exception:
                candidate = ""
            if not candidate or candidate in start_urls:
                continue
            try:
                scheme = urlsplit(candidate).scheme.lower()
            except Exception:
                scheme = ""
            if scheme not in _HTTP_SCHEMES:
                self._emit(on_event, "log", "warn",
                    f"[跳过]非 HTTP(S)目标: {self._safe_url(raw)}")
                continue
            start_urls.append(candidate)

        if not start_urls:
            self._emit(on_event, "log", "warn", "没有可抓取的目标地址。")
            self._emit(on_event, "done", [])
            return []

        all_records = {}
        # canonical 去重键集合：与 all_records 同步维护，键仍是原始链接
        seen_keys = set()
        dedup_rules = self._dedup_query_rules()
        page_count = 0

        for start in start_urls:
            if self.stopped:
                break

            resume_id = None
            for key, value in resume_map.items():
                try:
                    if normalize_url(key) == start:
                        resume_id = value
                        break
                except Exception:
                    continue

            resuming = resume_id is not None and self.db is not None
            task_id = None
            visited = set()
            if resuming:
                task_id = resume_id
                try:
                    self.db.update_task(task_id, "crawling")
                except Exception as exc:
                    log.error("恢复任务状态失败 task_id=%s: %s",
                        task_id, type(exc).__name__)
                try:
                    saved_rows = self.db.links_for_task(task_id)
                except Exception as exc:
                    log.error("读取任务历史链接失败 task_id=%s: %s",
                        task_id, type(exc).__name__)
                    saved_rows = []
                for item in saved_rows or []:
                    try:
                        _source, link, depth = item
                        depth = int(depth)
                    except Exception:
                        continue
                    if link and link not in all_records:
                        all_records[link] = depth
                        seen_keys.add(_canonical_dedup_key(link, dedup_rules))
                try:
                    visited = set(self.db.visited_for_task(task_id) or ())
                except Exception as exc:
                    log.error("读取任务已访问页面失败 task_id=%s: %s",
                        task_id, type(exc).__name__)
                    visited = set()
            elif self.db is not None:
                try:
                    task_id = self.db.create_task(start, max_depth)
                except Exception as exc:
                    self._emit(on_event, "log", "error",
                        f"创建任务失败（继续抓取）: {type(exc).__name__}")

            self._emit(on_event, "log", "info",
                f"开始抓取: {self._safe_url(start)}（深度 {max_depth}，"
                f"并发 {concurrency}，上限 {max_pages}页）")

            frontier = [start]
            crawled_pages = 0
            try:
                for depth in range(max_depth + 1):
                    if self.stopped:
                        break

                    candidates = []
                    if depth == 0:
                        candidates = [start]
                    else:
                        if resuming:
                            for link, level in all_records.items():
                                if level != depth - 1:
                                    continue
                                if self._should_descend(link, start):
                                    candidates.append(link)
                        candidates.extend(frontier)

                    if not candidates:
                        break

                    to_fetch = []
                    for candidate in candidates:
                        if page_count >= max_pages:
                            self._emit(on_event, "log", "warn",
                                f"已达到页面上限 {max_pages}，停止扩展。")
                            break
                        if candidate in visited:
                            continue
                        visited.add(candidate)
                        page_count += 1
                        crawled_pages += 1
                        to_fetch.append(candidate)

                    if not to_fetch:
                        frontier = []
                        continue

                    results = self._crawl_round(
                        to_fetch, depth, concurrency, selector, on_event,
                    )

                    next_frontier = []
                    round_rows = []
                    for page_url, links in results:
                        for link in links:
                            if link in all_records:
                                continue
                            key = _canonical_dedup_key(link, dedup_rules)
                            if key in seen_keys:
                                continue
                            all_records[link] = depth
                            seen_keys.add(key)
                            if task_id is not None:
                                round_rows.append(
                                    self._link_row(task_id, page_url, link, depth)
                                )
                        for link in links:
                            if link in visited:
                                continue
                            if self._should_descend(link, start):
                                next_frontier.append(link)
                        self._emit(on_event, "page", self._safe_url(page_url), len(links), depth)

                    self._write_rows(round_rows, on_event)
                    frontier = list(dict.fromkeys(next_frontier))

                    if self.stopped:
                        break
            finally:
                if self.db is not None and task_id is not None:
                    try:
                        self.db.update_task(
                            task_id,
                            "stopped" if self.stopped else "completed",
                            end_time=datetime.now().isoformat(timespec="seconds"),
                            total_links=len(all_records),
                            crawled_links=len(visited),
                        )
                    except Exception as exc:
                        log.error("更新任务状态失败 task_id=%s: %s",
                            task_id, type(exc).__name__)

            if resuming and crawled_pages == 0:
                self._emit(on_event, "log", "info",
                    f"任务已完成，无新增页面: {self._safe_url(start)}")
            else:
                self._emit(
                    on_event, "log", "warn" if self.stopped else "info",
                    f"任务{'已停止' if self.stopped else '完成'}: "
                    f"{self._safe_url(start)}，共抓取 {crawled_pages}个页面，"
                    f"累计 {len(all_records)}个链接",
                )

        records = [{"link": link, "depth": depth} for link, depth in all_records.items()]
        records = self._filter_records(records)
        self._emit(on_event, "done", records)
        return records

    def _crawl_round(self, urls, depth, concurrency, selector, on_event):
        """并发抓取一层页面，按提交顺序返回 [(page_url, links), ...]。

        按提交顺序收集结果可让记录顺序稳定，同时不牺牲并发度。
        """
        def worker(target_url):
            try:
                if self.stopped:
                    return target_url, []
                self._wait_if_paused()
                if self.stopped:
                    return target_url, []
                if not self.robots_allows(target_url):
                    self._emit(on_event, "log", "warn", f"[robots拒绝] {self._safe_url(target_url)}")
                    return target_url, []
                delay =0.0
                if self.config.get_bool(
                    "network_policy", "respect_robots", default=True,
                ):
                    _disallow, delay = self._robots(target_url)
                # 429/503/408 先退避重试；次数用尽按失败处理，不抽链
                response = self._fetch_with_retry(target_url, on_event)
                if response is None:
                    self._emit(on_event, "log", "error", f"[请求失败] {self._safe_url(target_url)}")
                    return target_url, []
                if not self._should_parse_body(response):
                    # Content-Type 闸门：非可解析类型（JSON/二进制/媒体）不解析、
                    # 不下钻；链接是否存活由体检阶段的 HEAD 判定，两者互不重复
                    self._emit(on_event, "log", "info",
                        f"[跳过解析] {self._safe_url(target_url)} 非可解析内容类型")
                    return target_url, []
                links = self.extract_links(
                    self._decode(response), target_url, selector,
                )
                if delay > 0:
                    # 与退避等待同手法：Crawl-delay 等待也可被 stop 即时打断
                    self._stop_event.wait(min(delay, 10.0))
                return target_url, links
            except Exception as exc:
                self._emit(on_event, "log", "error",
                    f"[抓取异常] {self._safe_url(target_url)}: {type(exc).__name__}")
                return target_url, []

        results = []
        executor = ThreadPoolExecutor(max_workers=concurrency)
        try:
            futures = [executor.submit(worker, target_url) for target_url in urls]
            for target_url, future in zip(urls, futures):
                try:
                    results.append(future.result())
                except Exception as exc:
                    self._emit(on_event, "log", "error",
                        f"[抓取异常] {self._safe_url(target_url)}: {type(exc).__name__}")
                    results.append((target_url, []))
        finally:
            executor.shutdown(wait=True)
        return results

    def _parseable_content_types(self):
        """可解析子链接的 Content-Type 集合（小写，含分号前的媒体类型）。"""
        try:
            types = self.config.get_list(
                "content_gate", "parseable_content_types",
                default=list(_DEFAULT_PARSEABLE_TYPES),
            )
        except Exception:
            types = list(_DEFAULT_PARSEABLE_TYPES)
        return {str(item).strip().lower() for item in types if str(item).strip()}

    def _should_parse_body(self, response):
        """Content-Type 闸门：本次已 GET 到的 body 要不要解析出子链接。

        只回答「能否解析」这一个问题，用本次响应头、零额外网络请求；
        绝不做大小/时限判断（那是 _passes_file_filters 的职责，另发 HEAD
        取 Content-Length / Last-Modified）。未声明 Content-Type 时按旧行为
        放行解析，避免把「缺头部的正常页面」误判为不可解析。
        """
        if response is None:
            return False
        try:
            if not self.config.get_bool("content_gate", "enabled", default=True):
                return True
        except Exception:
            pass
        try:
            content_type = response.headers.get("Content-Type") or ""
        except Exception:
            return False
        mime = content_type.split(";", 1)[0].strip().lower()
        if not mime:
            return True
        return mime in self._parseable_content_types()

    def _should_descend(self, link, start_url):
        """判断链接是否值得继续下钻（同域、非文件、未被排除）。"""
        try:
            if urlsplit(link).scheme.lower() not in _HTTP_SCHEMES:
                return False
            if not same_domain(link, start_url):
                return False
            if self.config.is_file_link(link):
                return False
            if self.config.excluded(link):
                return False
            return True
        except Exception as exc:
            log.debug("下钻判定异常(%s): %s", self._safe_url(link), type(exc).__name__)
            return False

    def _link_row(self, task_id, source_url, link, depth):
        """构造 add_links_bulk所需行。

        行格式：(task_id, source_url, link, depth, file_name,
        file_type, file_size, last_modified, status)
        """
        try:
            file_name = os.path.basename(urlsplit(link).path) or ""
        except Exception:
            file_name = ""
        try:
            file_type = self.config.file_type_of(link)
        except Exception:
            file_type = ""
        return (
            task_id, source_url, link, depth,
            file_name, file_type, None, None, "crawled",
        )

    def _write_rows(self, rows, on_event=None):
        """批量写入链接记录；数据库异常只记录日志，不中断抓取。"""
        if not rows or self.db is None:
            return
        try:
            self.db.add_links_bulk(rows)
        except Exception as exc:
            log.error("链接入库失败（已跳过 %s条）: %s", len(rows), type(exc).__name__)
            self._emit(on_event, "log", "error", f"链接入库失败（继续抓取）: {type(exc).__name__}")

    # ------------------------------------------------------------------
    # 断点续爬
    # ------------------------------------------------------------------
    def resume_pending(self, on_event=None):
        """从数据库读取未完成任务并续爬；同一 URL 只续最早的 task_id。"""
        if not self.config.get_bool("resumable_crawling", "enabled", default=True):
            self._emit(on_event, "log", "warn",
                "断点续爬未启用，请在增强功能配置中开启。")
            return []
        if self.db is None:
            self._emit(on_event, "log", "warn", "数据库未初始化，无法断点续爬。")
            return []

        try:
            pending = self.db.pending_tasks()
        except Exception as exc:
            self._emit(on_event, "log", "error",
                f"读取未完成任务失败: {type(exc).__name__}")
            return []

        task_map = {}
        superseded = []
        for item in pending or []:
            try:
                task_id, url = item[0], item[1]
            except Exception:
                continue
            if not url or not isinstance(task_id, int):
                continue
            if url in task_map:
                superseded.append(task_id)
            else:
                task_map[url] = task_id

        for task_id in superseded:
            try:
                self.db.update_task(task_id, "superseded")
            except Exception as exc:
                log.error("标记 superseded失败 task_id=%s: %s",
                    task_id, type(exc).__name__)

        if not task_map:
            self._emit(on_event, "log", "info", "没有需要续爬的任务。")
            return []

        urls = list(task_map.keys())
        self._emit(on_event, "log", "info", f"恢复 {len(urls)}个未完成目标…")
        self.reset()
        return self.crawl(urls, on_event=on_event, resume_tasks=task_map)

    # ------------------------------------------------------------------
    # 链接体检
    # ------------------------------------------------------------------
    def _ok_status_codes(self):
        """视为正常的状态码集合（默认 2xx 基线 + link_check.ok_status_codes）。"""
        try:
            codes = self.config.get_int_list(
                "link_check", "ok_status_codes",
                default=list(_DEFAULT_OK_STATUS_CODES),
            )
        except Exception:
            codes = list(_DEFAULT_OK_STATUS_CODES)
        return {code for code in codes if isinstance(code, int)}

    def _classify_status(self, code):
        """状态分级：ok / redirect / blocked / dead / error。

        分级语义仍收敛在本方法内，只改「哪些 code 视为 ok」：
        先保留 2xx 基线防回归，再判 link_check.ok_status_codes（默认含 999 这类
        CDN/反爬层非标准码），且该判定必须早于 3xx，才能把 304 这类「存在但
        并非重定向」的码正确归位。不新增 state key，展示/导出层无需改动。
        """
        try:
            if code is None:
                return "error"
            code = int(code)
        except (TypeError, ValueError):
            return "error"
        if 200 <= code < 300:
            return "ok"
        if code in self._ok_status_codes():
            return "ok"
        if 300 <= code < 400:
            return "redirect"
        if code in (401, 403, 429):
            return "blocked"
        if code in (404, 410):
            return "dead"
        return "error"

    def _head_fallback_codes(self):
        """HEAD 取到这些状态码时，回退一次只读 GET 再判定。"""
        try:
            enabled = self.config.get_bool(
                "link_check", "head_fallback_get", default=True,
            )
        except Exception:
            enabled = True
        if not enabled:
            return set()
        try:
            codes = self.config.get_int_list(
                "link_check", "head_fallback_codes",
                default=list(_DEFAULT_HEAD_FALLBACK_CODES),
            )
        except Exception:
            codes = list(_DEFAULT_HEAD_FALLBACK_CODES)
        try:
            if self.config.get_bool(
                "link_check", "head_fallback_include_403", default=False,
            ):
                codes = codes + [403]
        except Exception:
            pass
        return {code for code in codes if isinstance(code, int)}

    def check_links(self, links, on_event=None, task_id=None):
        """并发 HEAD体检链接，返回 {link: (state, code)}。

        HEAD 取到回退集状态码（默认 405/501，403 为 opt-in）时，对同一 link 再发
        一次只读 GET 并用 GET 的 code 重新分级；GET 自身失败则保持原 HEAD 判定。
        分级集合由 link_check.ok_status_codes 配置（默认含 206/999）。
        ftp/sftp链接不发起请求，判为 error 并附原因（无 HTTP 语义，无法体检）。
        """
        items = []
        seen = set()
        for raw in links or []:
            link = (raw or "").strip()
            if not link or link in seen:
                continue
            seen.add(link)
            items.append(link)

        total = len(items)
        results = {}
        if total == 0:
            self._emit(on_event, "check_done", results)
            return results

        try:
            concurrency = max(2, int(self.config.concurrency))
        except Exception:
            concurrency = 2

        def worker(link):
            try:
                if self.stopped:
                    return link, ("error", None)
                scheme = urlsplit(link).scheme.lower()
                if scheme in ("ftp", "sftp"):
                    # ftp/sftp 无 HTTP 语义、无法自动体检；旧实现零请求直接判 ok
                    # 属于虚假结论（F-07），改为 error 并附原因
                    return link, ("error", "ftp/sftp 协议不支持自动体检")
                if scheme not in _HTTP_SCHEMES:
                    return link, ("error", None)
                # 体检需要看到原始3xx，因此不跟随重定向
                response = self._perform(link, method="HEAD", follow_redirects=False)
                code = None if response is None else response.status_code
                if code is not None and code in self._head_fallback_codes():
                    # HEAD 被拒（默认 405/501，403 为 opt-in）：对同一 link 再发
                    # 一次只读 GET（不读 body、不新增线程、节流复用 _request），
                    # 用 GET 的 code 重新分级，语义对齐浏览器真实访问。
                    fallback = self._perform(
                        link, method="GET", follow_redirects=False, read_body=False,
                    )
                    if fallback is not None:
                        code = fallback.status_code
                    # GET 自身网络异常（None）时保持原 HEAD 判定，不改写结果
                return link, (self._classify_status(code), code)
            except Exception as exc:
                log.debug("体检异常(%s): %s", self._safe_url(link), type(exc).__name__)
                return link, ("error", None)

        done = 0
        db_rows = []
        executor = ThreadPoolExecutor(max_workers=concurrency)
        try:
            futures = {executor.submit(worker, link): link for link in items}
            for future in as_completed(futures):
                if self.stopped:
                    break
                link = futures[future]
                try:
                    link, result = future.result()
                except Exception as exc:
                    log.debug("体检结果异常(%s): %s", self._safe_url(link), type(exc).__name__)
                    result = ("error", None)
                results[link] = result
                db_rows.append((task_id, link, result[0], result[1]))
                done += 1
                self._emit(on_event, "progress", done, total)
        finally:
            executor.shutdown(wait=True)

        if self.db is not None and db_rows:
            try:
                self.db.add_checks_bulk(db_rows)
            except Exception as exc:
                log.error("体检结果入库失败: %s", type(exc).__name__)
                self._emit(on_event, "log", "error", f"体检结果入库失败: {type(exc).__name__}")

        self._emit(on_event, "check_done", results)
        return results

    # ------------------------------------------------------------------
    # 导出（txt / csv / json）
    # ------------------------------------------------------------------
    @staticmethod
    def _record_get(record, key, default=""):
        if isinstance(record, dict):
            value = record.get(key, default)
            return default if value is None else value
        return default

    def export(self, records, path, fmt="txt", meta=None):
        """导出记录到 txt / csv / json，自动创建父目录；返回写入路径。"""
        meta = meta if isinstance(meta, dict) else {}
        records = list(records or [])
        fmt = (fmt or "txt").lower()
        if fmt not in ("txt", "csv", "json"):
            fmt = "txt"

        try:
            parent = os.path.dirname(os.path.abspath(path))
            if parent and not os.path.isdir(parent):
                os.makedirs(parent, exist_ok=True)
        except Exception as exc:
            log.error("创建导出目录失败: %s", exc)

        if fmt == "csv":
            self._export_csv(records, path)
        elif fmt == "json":
            self._export_json(records, path, meta)
        else:
            self._export_txt(records, path, meta)
        return path

    def _export_txt(self, records, path, meta):
        """沿用旧版 txt版式，保证历史导出文件格式兼容。"""
        crawl_time = meta.get("crawl_time") or datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(f"抓取自: {meta.get('source', '')}\n")
            handle.write(f"抓取时间: {crawl_time}\n")
            handle.write(f"筛选类型: {meta.get('filter_type', '')}\n")
            handle.write(f"关键词: {meta.get('keyword', '')}\n")
            handle.write(
                f"CSS选择器: {meta.get('css_selector', '') or '整个页面'}\n"
            )
            handle.write(f"链接数量: {len(records)}\n")
            handle.write("=" * 50 + "\n\n")
            for index, record in enumerate(records, 1):
                handle.write(f"{index:3d}. {self._record_get(record, 'link')}\n")

    def _export_csv(self, records, path):
        # utf-8-sig 便于 Excel 直接识别中文
        with open(path, "w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["序号", "链接", "文件类型", "协议", "深度", "状态"])
            for index, record in enumerate(records, 1):
                writer.writerow([
                    index,
                    _csv_cell(self._record_get(record, "link")),
                    _csv_cell(self._record_get(record, "file_type")),
                    _csv_cell(self._record_get(record, "protocol")),
                    self._record_get(record, "depth"),
                    _csv_cell(self._record_get(record, "state")),
                ])

    def _export_json(self, records, path, meta):
        crawl_time = meta.get("crawl_time") or datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        payload = {
            "meta": {
                "source": meta.get("source", ""),
                "crawl_time": crawl_time,
                "filter_type": meta.get("filter_type", ""),
                "keyword": meta.get("keyword", ""),
                "css_selector": meta.get("css_selector", "") or "整个页面",
                "count": len(records),
            },
            "links": [
                {
                    "index": index,
                    "link": self._record_get(record, "link"),
                    "file_type": self._record_get(record, "file_type"),
                    "protocol": self._record_get(record, "protocol"),
                    "depth": self._record_get(record, "depth"),
                    "state": self._record_get(record, "state"),
                }
                for index, record in enumerate(records, 1)
            ],
        }
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
