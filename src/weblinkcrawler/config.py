"""配置管理：默认值合并 / 迁移 / 校验 / URL 规范化。

修复原 v0.6 的缺陷：旧 enhanced_config.json 缺少 element_crawling 等键时，
原代码直接下标访问会抛 KeyError 导致启动崩溃；此处统一用深合并补齐默认值。
"""

from __future__ import annotations

import copy
import fnmatch
import json
import os
import re
from urllib.parse import urlsplit, urlunsplit

from .logutil import get_logger

log = get_logger()

CONFIG_FILE = "file_type_config.json"
ENHANCED_CONFIG_FILE = "enhanced_config.json"

DEFAULT_FILE_TYPE_MAPPING = {
    "程序文件": ['.exe', '.apk', '.deb', '.rpm', '.dmg', '.dll', '.so', '.framework', '.lib', '.msi'],
    "镜像文件": ['.iso', '.cue', '.bin', '.nrg', '.gho', '.wim', '.esd', '.img', '.vdi', '.ova', '.vma', '.ovf', '.vmdk', '.qcow2'],
    "配置文件": ['.ini', '.conf', '.cfg', '.properties', '.xml', '.json', '.yaml', '.inf', '.reg', '.udev'],
    "数据库文件": ['.mdb', '.accdb', '.sql', '.dbf', '.ldf', '.mdf', '.db', '.sqlite', '.mongo', '.cbl', '.leveldb', '.ora', '.db2'],
    "日志文件": ['.evt', '.evtx', '.journal', '.log', '.trace', '.audit', '.access'],
    "文档文件": ['.doc', '.docx', '.wps', '.pages', '.xls', '.xlsx', '.et', '.numbers', '.ppt', '.pptx', '.dps', '.keynote', '.pdf', '.epub', '.mobi', '.txt', '.md', '.csv'],
    "图片文件": ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.tif', '.webp', '.psd', '.ai', '.svg', '.cdr', '.eps'],
    "音频文件": ['.mp3', '.aac', '.ogg', '.wma', '.wav', '.flac', '.ape', '.alac', '.mid', '.midi', '.amr', '.pcm'],
    "视频文件": ['.mp4', '.mkv', '.avi', '.mov', '.flv', '.m3u8', '.wmv', '.rmvb', '.webm'],
    "字体文件": ['.ttf', '.otf', '.ttc', '.otc', '.woff', '.woff2', '.eot', '.psf', '.fon', '.dfont'],
    "压缩文件": ['.zip', '.rar', '.7z', '.tar', '.tar.gz', '.tar.bz2', '.gz', '.xz'],
}

# 链接体检：默认视为正常的状态码（含部分 CDN/反爬层返回的非标准码 999）
DEFAULT_OK_STATUS_CODES = (200, 206, 999)
# HEAD 被拒时回退只读 GET 的状态码（403 设为 opt-in，避免误伤真实鉴权拦截）
DEFAULT_HEAD_FALLBACK_CODES = (405, 501)
# 可解析子链接的 Content-Type（白名单，命中才 extract_links）
DEFAULT_PARSEABLE_TYPES = ("text/html", "application/xhtml+xml", "text/plain")
# 去重键生成时的 query 噪声参数黑名单（w3lib url_query_cleaner 语义）
QUERY_NOISE_PARAMS = (
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "utm_id", "fbclid", "fbclr", "gclid", "msclkid", "mc_cid", "mc_eid",
    "_ga", "_gl", "yclid", "igshid", "spm", "vd_source",
    "sessionid", "sessid", "phpsessid", "jsessionid", "aspsessionid", "sid",
)
# 去重键生成时始终保留的 query 参数白名单（真分页/检索参数永不被误删）
QUERY_KEEP_PARAMS = (
    "page", "p", "pg", "start", "offset", "limit", "id", "q", "s", "search",
    "lang", "category", "cat", "tag", "sort", "order", "year", "month",
    "view", "tab",
)

DEFAULT_ENHANCED_CONFIG = {
    "enabled": True,
    "multi_url": {"enabled": True, "batch_import": True, "url_validation": True},
    "crawling_depth": {"enabled": True, "depth": 1},
    "crawl_limits": {"max_pages": 200, "concurrency": 8},
    "network_policy": {
        "respect_robots": True,
        "max_html_bytes": 5 * 1024 * 1024,
        "max_redirects": 5,
        "block_private_redirects": True,
        # 抓取目标（种子 URL 与页面链接）同样拦截私有/回环地址（F-04，默认开启；
        # 需要抓内网站点时在 enhanced_config.json 中置 false）
        "block_private_targets": True,
        # 老服务器 SSL 兼容（弱证书/弱 DH），默认关闭，不改变现有行为
        "ssl_compat_legacy_servers": False,
    },
    "exclude_rules": {"enabled": False, "patterns": [], "use_regex": False},
    "element_crawling": {"enabled": True, "css_selector": ""},
    "file_filters": {
        "enabled": True,
        "size_filter": {"enabled": False, "min_size": 0, "max_size": 0},
        "time_filter": {"enabled": False, "days": 7},
    },
    # 抓取阶段 Content-Type 闸门：只决定「要不要解析子链接」，
    # 与文件大小/时限过滤（file_filters）分层，互不重复过滤。
    "content_gate": {
        "enabled": True,
        "parseable_content_types": list(DEFAULT_PARSEABLE_TYPES),
    },
    # 链接体检策略
    "link_check": {
        "ok_status_codes": list(DEFAULT_OK_STATUS_CODES),
        "head_fallback_codes": list(DEFAULT_HEAD_FALLBACK_CODES),
        # 403 默认不回退 GET（可能是真实鉴权拦截），由使用者按站点 opt-in
        "head_fallback_include_403": False,
        "head_fallback_get": True,
    },
    "anti_anti_crawl": {
        "enabled": True,
        "dynamic_ua": True,
        "ua_list": [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_2) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
        ],
        "proxy": {"enabled": False, "type": "http", "proxy_list": []},
        "cookies": {"enabled": False, "cookie_list": []},
        "request_strategy": {"enabled": True, "interval": 2, "retries": 3,
                            "timeout": 10,
                            # Retry-After / 退避等待的封顶秒数（0~300）
                            "retry_after_cap": 30},
    },
    "resumable_crawling": {"enabled": True},
    # query 噪声参数黑白名单：只影响去重键，不改写原始 URL
    "dedup_query": {
        "enabled": True,
        "strip_params": list(QUERY_NOISE_PARAMS),
        "keep_params": list(QUERY_KEEP_PARAMS),
    },
}

_URL_RE = re.compile(r'^(https?|ftp|sftp)://[^\s/$.?#].[^\s]*$', re.IGNORECASE)
# 合法主机名：点分 IPv4 / 方括号 IPv6 / 含标签的域名（不允许空格与逗号等）
_HOST_RE = re.compile(
    r'^(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(?:\.(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)){3}'
    r'|\[[0-9A-Fa-f:.]+\]'
    r'|(?!-)[A-Za-z0-9-]{1,63}(?<!-)(?:\.(?!-)[A-Za-z0-9-]{1,63}(?<!-))*\.?)$'
)


def deep_merge(base, override):
    """以 base 为默认，用 override 覆盖；嵌套 dict 递归合并，返回新 dict。"""
    result = copy.deepcopy(base)
    if not isinstance(override, dict):
        return result
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = deep_merge(result[k], v)
        else:
            result[k] = copy.deepcopy(v)
    return result


class ConfigManager:
    def __init__(self, config_file=CONFIG_FILE, enhanced_config_file=ENHANCED_CONFIG_FILE):
        self.config_file = config_file
        self.enhanced_config_file = enhanced_config_file
        self.file_type_mapping = copy.deepcopy(DEFAULT_FILE_TYPE_MAPPING)
        self.enhanced_config = copy.deepcopy(DEFAULT_ENHANCED_CONFIG)
        # 排除规则正则编译缓存：{pattern: compiled|None}，None=编译失败（F-06）
        self._exclude_regex_cache = {}

    # ---- 文件类型映射 ----
    def load_file_types(self):
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict) and data:
                    self.file_type_mapping = deep_merge(DEFAULT_FILE_TYPE_MAPPING, data)
                else:
                    self.file_type_mapping = copy.deepcopy(DEFAULT_FILE_TYPE_MAPPING)
            else:
                self.file_type_mapping = copy.deepcopy(DEFAULT_FILE_TYPE_MAPPING)
                self.save_file_types()
        except Exception as e:
            log.warning("加载文件类型配置失败，使用默认值: %s", e)
            self.file_type_mapping = copy.deepcopy(DEFAULT_FILE_TYPE_MAPPING)
        return self.file_type_mapping

    def save_file_types(self):
        try:
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(self.file_type_mapping, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            log.error("保存文件类型配置失败: %s", e)
            return False

    # ---- 增强配置 ----
    def load_enhanced(self):
        try:
            if os.path.exists(self.enhanced_config_file):
                with open(self.enhanced_config_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                merged = deep_merge(DEFAULT_ENHANCED_CONFIG, data if isinstance(data, dict) else {})
                self.enhanced_config = merged
                if merged != data:  # 发生了迁移补齐，回写
                    self.save_enhanced()
            else:
                self.enhanced_config = copy.deepcopy(DEFAULT_ENHANCED_CONFIG)
                self.save_enhanced()
        except Exception as e:
            log.warning("加载增强配置失败，使用默认值: %s", e)
            self.enhanced_config = copy.deepcopy(DEFAULT_ENHANCED_CONFIG)
        return self.enhanced_config

    def save_enhanced(self):
        try:
            with open(self.enhanced_config_file, "w", encoding="utf-8") as f:
                json.dump(self.enhanced_config, f, ensure_ascii=False, indent=2)
            try:
                os.chmod(self.enhanced_config_file,0o600)
            except OSError:
                pass
            return True
        except Exception as e:
            log.error("保存增强配置失败: %s", e)
            return False

    # ---- 取值辅助（带校验/容错）----
    def _ec(self, *keys, default=None):
        node = self.enhanced_config
        for k in keys:
            if isinstance(node, dict) and k in node:
                node = node[k]
            else:
                return default
        return node

    def get_int(self, *keys, default=0, lo=None, hi=None):
        try:
            v = int(self._ec(*keys, default=default))
        except (TypeError, ValueError):
            v = default
        if lo is not None:
            v = max(lo, v)
        if hi is not None:
            v = min(hi, v)
        return v

    def get_float(self, *keys, default=0.0, lo=None, hi=None):
        try:
            v = float(self._ec(*keys, default=default))
        except (TypeError, ValueError):
            v = default
        if lo is not None:
            v = max(lo, v)
        if hi is not None:
            v = min(hi, v)
        return v

    def get_bool(self, *keys, default=False):
        v = self._ec(*keys, default=default)
        return bool(v)

    def get_list(self, *keys, default=None):
        """读取字符串列表配置项；非列表或元素异常时回退默认值。"""
        raw = self._ec(*keys, default=None)
        if raw is None:
            return list(default or [])
        if not isinstance(raw, (list, tuple)):
            return list(default or [])
        out = []
        for item in raw:
            if item is None:
                continue
            try:
                text = str(item).strip()
            except Exception:
                continue
            if text:
                out.append(text)
        return out

    def get_int_list(self, *keys, default=None):
        """读取整数列表配置项；非整数元素被跳过（容错，不抛异常）。"""
        out = []
        for text in self.get_list(*keys, default=default):
            try:
                out.append(int(text))
            except (TypeError, ValueError):
                continue
        return out

    def dedup_query_rules(self):
        """返回 (enabled, strip_params, keep_params)，供去重键生成使用。

        读取异常时按默认启用，避免一次坏配置让去重键整体失效。
        """
        try:
            if not self.get_bool("dedup_query", "enabled", default=True):
                return False, [], []
            return (True,
                    self.get_list("dedup_query", "strip_params", default=None),
                    self.get_list("dedup_query", "keep_params", default=None))
        except Exception as exc:
            log.debug("读取 query 去重配置失败，按默认启用: %s", type(exc).__name__)
            return True, list(QUERY_NOISE_PARAMS), list(QUERY_KEEP_PARAMS)

    # ---- 派生配置 ----
    @property
    def enhanced_enabled(self):
        return self.get_bool("enabled", default=True)

    @property
    def max_depth(self):
        if self.enhanced_enabled and self.get_bool("crawling_depth", "enabled", default=True):
            return self.get_int("crawling_depth", "depth", default=1, lo=0, hi=5)
        return 0

    @property
    def max_pages(self):
        return self.get_int("crawl_limits", "max_pages", default=200, lo=1, hi=100000)

    @property
    def concurrency(self):
        return self.get_int("crawl_limits", "concurrency", default=8, lo=1, hi=64)

    @property
    def css_selector(self):
        if not self.get_bool("element_crawling", "enabled", default=True):
            return ""
        global_sel = self._ec("element_crawling", "css_selector", default="") or ""
        return global_sel.strip()

    def request_params(self):
        """依据反反爬配置返回 (headers, proxies, cookies, timeout, retries, interval)。

        说明：``interval`` 同时承担两个职责——作为重试指数退避的基数，以及
        作为请求节流间隔（见 ``throttle_interval``）。此处返回 6 个值，与
        调用方（crawler._perform / crawler._robots）的解包保持一致。
        """
        import random
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        proxies = None
        cookies = None
        timeout, retries, interval = 10, 1, 0
        if self.enhanced_enabled and self.get_bool("anti_anti_crawl", "enabled", default=True):
            aac = self.enhanced_config.get("anti_anti_crawl", {})
            if not isinstance(aac, dict):
                aac = {}
            if aac.get("dynamic_ua", True):
                ua_list = aac.get("ua_list") or []
                if isinstance(ua_list, list) and ua_list:
                    headers["User-Agent"] = random.choice(ua_list)
            proxy = aac.get("proxy", {}) if isinstance(aac.get("proxy"), dict) else {}
            if proxy.get("enabled") and proxy.get("proxy_list"):
                proxy_list = proxy.get("proxy_list") or []
                if isinstance(proxy_list, list) and proxy_list:
                    picked = str(random.choice(proxy_list)).strip()
                    if picked:
                        ptype = str(proxy.get("type", "http") or "http").lower()
                        ptype = ptype if ptype in ("http", "https", "socks4",
                                                   "socks5", "socks5h") else "http"
                        target = f"{ptype}://{picked}"
                        proxies = {"http": target, "https": target}
            ck = aac.get("cookies", {}) if isinstance(aac.get("cookies"), dict) else {}
            if ck.get("enabled") and ck.get("cookie_list"):
                cookie_list = ck.get("cookie_list") or []
                if isinstance(cookie_list, list):
                    parsed = {}
                    for item in cookie_list:
                        text = str(item)
                        if "=" in text:
                            name, value = text.split("=", 1)
                            name = name.strip()
                            if name:
                                parsed[name] = value.strip()
                    if parsed:
                        cookies = parsed
            rs = aac.get("request_strategy", {}) if isinstance(
                aac.get("request_strategy"), dict) else {}
            if rs.get("enabled", True):
                timeout = self.get_int("anti_anti_crawl", "request_strategy", "timeout",
                                        default=10, lo=3, hi=120)
                retries = self.get_int("anti_anti_crawl", "request_strategy", "retries",
                                        default=3, lo=1, hi=10)
                interval = self.get_float("anti_anti_crawl", "request_strategy", "interval",
                                          default=2, lo=0, hi=60)
        return headers, proxies, cookies, timeout, retries, interval

    def throttle_interval(self):
        """请求节流间隔（秒）：对同一线程的连续请求生效，0 表示不节流。

        修复旧版缺陷：配置项 ``interval`` 旧版只用作重试退避基数，
        正常请求之间没有任何间隔，"请求间隔"形同虚设。
        """
        try:
            if not self.enhanced_enabled:
                return 0.0
            if not self.get_bool("anti_anti_crawl", "enabled", default=True):
                return 0.0
            if not self.get_bool("anti_anti_crawl", "request_strategy", "enabled",
                                  default=True):
                return 0.0
            return self.get_float("anti_anti_crawl", "request_strategy", "interval",
                                  default=0, lo=0, hi=60)
        except Exception:
            return 0.0

    # ---- 文件类型 ----
    @staticmethod
    def path_extension(link):
        try:
            path = urlsplit(link).path
        except Exception:
            path = link
        ext = os.path.splitext(path)[1].lower()
        return ext

    def is_file_link(self, link):
        ext = self.path_extension(link)
        if not ext:
            return False
        return any(ext in exts for exts in self.file_type_mapping.values())

    def file_type_of(self, link):
        ext = self.path_extension(link)
        if not ext:
            return ""
        for cat, exts in self.file_type_mapping.items():
            if ext in exts:
                return cat
        return ""

    def filter_options(self):
        return ["所有链接", "HTTPS链接", "HTTP链接"] + list(self.file_type_mapping.keys())

    def _compiled_exclude(self, pattern):
        """编译排除规则正则并按 pattern 缓存（F-06）；编译失败返回 None。"""
        if pattern not in self._exclude_regex_cache:
            try:
                self._exclude_regex_cache[pattern] = re.compile(pattern)
            except re.error:
                self._exclude_regex_cache[pattern] = None
        return self._exclude_regex_cache[pattern]

    # ---- 排除规则 ----
    def excluded(self, link):
        if not self.get_bool("exclude_rules", "enabled", default=False):
            return False
        patterns = self._ec("exclude_rules", "patterns", default=[]) or []
        use_regex = self.get_bool("exclude_rules", "use_regex", default=False)
        for pat in patterns:
            if not pat:
                continue
            # 模式长度上限：限制病态正则的爆炸半径（F-06）
            if len(str(pat)) > 512:
                continue
            try:
                if use_regex:
                    compiled = self._compiled_exclude(str(pat))
                    if compiled is not None and compiled.search(link):
                        return True
                elif fnmatch.fnmatch(link, pat):
                    return True
            except re.error:
                continue
        return False


def normalize_url(url):
    """补协议、去片段、规范 scheme/host 大小写；非法输入原样返回（交由上层校验）。

    修复旧版缺陷：旧实现只要不含 "://" 就无条件补 ``https://``，导致
    ``javascript:alert(1)``、``data:text/html,x`` 被改写成
    ``https://javascript:alert(1)/`` 这类畸形地址并通过后续校验。
    现在仅在输入确为「裸主机名 / 路径」形式时才补协议。
    """
    if url is None:
        return ""
    url = str(url).strip()
    if not url:
        return ""
    # 带 scheme 的非 http(s)/ftp(sftp) 形式一律不改写，交由校验层拒绝
    if "://" not in url:
        if re.match(r'^[A-Za-z][A-Za-z0-9+.\-]*:', url):
            return url  # javascript: / data: / mailto: 等
        if not url.startswith("//"):
            url = "https://" + url
    try:
        parts = urlsplit(url)
        scheme = parts.scheme.lower() or "https"
        if scheme not in ("http", "https", "ftp", "sftp"):
            return url
        netloc = parts.netloc
        # 用户名/密码不应出现在抓取目标中，剥离（防泄露）
        if "@" in netloc:
            netloc = netloc.split("@", 1)[1]
        netloc = netloc.lower()
        path = parts.path or "/"
        query = parts.query
        return urlunsplit((scheme, netloc, path, query, ""))  # 丢弃 fragment
    except Exception:
        return url


def _canonical_query(query, strip_params, keep_params):
    """把 query 规范为去重键片段：排序 → 去空值 → 删黑名单名（除非白名单）→ 去重复键。

    语义对齐 w3lib 的 url_query_cleaner：默认白名单优先，remove=True 才是
    黑名单；此处固定「白名单优先、其余按黑名单删除」的组合，因为真分页参数
    （?page=2 / ?id=）被误删的代价远大于多留一个噪声参数。
    """
    if not query:
        return ""
    strip = {str(name).strip().lower() for name in (strip_params or [])}
    keep = {str(name).strip().lower() for name in (keep_params or [])}
    pairs = []
    seen = set()
    for chunk in query.split("&"):
        if not chunk:
            continue
        if "=" in chunk:
            name, value = chunk.split("=", 1)
        else:
            name, value = chunk, ""
        name = name.strip().lower()
        value = value.strip()
        if not name or not value:
            continue  # 空值参数不参与去重键
        if name not in keep:
            if name in strip or name.startswith("utm_"):
                continue
        key = (name, value)
        if key in seen:
            continue
        seen.add(key)
        pairs.append(f"{name}={value}")
    pairs.sort()
    return "&".join(pairs)


def canonical_key(url, strip_params=None, keep_params=None):
    """生成仅用于去重的规范键（raw URL 与 canonical key 双轨制）。

    借鉴 scrapy 的 LxmlLinkExtractor：canonicalize 只作去重键，不改写
    link.url 本身——导出、展示、入库一律写原始 URL，避免「导出的地址打不开」。
    归一化内容：scheme/host 小写、去 fragment、剥凭据、query 噪声参数黑白名单。
    strip_params / keep_params 传 None 时使用模块默认名单。
    """
    if url is None:
        return ""
    text = str(url).strip()
    if not text:
        return ""
    if strip_params is None:
        strip_params = QUERY_NOISE_PARAMS
    if keep_params is None:
        keep_params = QUERY_KEEP_PARAMS
    try:
        parts = urlsplit(text)
        scheme = (parts.scheme or "").lower()
        netloc = parts.netloc.lower()
        if "@" in netloc:
            netloc = netloc.split("@", 1)[1]
        path = parts.path or "/"
        query = _canonical_query(parts.query, strip_params, keep_params)
        return urlunsplit((scheme, netloc, path, query, ""))
    except Exception:
        # 解析失败时退回原文，保证去重键始终可用（不会抛给调用方）
        return text


def is_valid_url(url):
    """URL 语法校验（供界面「校验地址」使用）：协议 + 主机名格式。

    职责边界（F-10）：本函数只回答「格式是否合法」，不做网络策略判定——
    私有/回环地址在此返回 True 是刻意设计（内网站点语法同样合法）；
    是否放行由引擎的 security.validate_target 按 network_policy 决定。
    另：normalize_url 已剥离用户名/密码，此处的凭据校验为纵深防御。
    """
    try:
        candidate = normalize_url(str(url).strip())
        parts = urlsplit(candidate)
        if parts.scheme.lower() not in ("http", "https", "ftp", "sftp"):
            return False
        if not parts.hostname:
            return False
        if parts.username is not None or parts.password is not None:
            return False
        if len(candidate) > 8192:
            return False
        host = parts.hostname
        if host.lower() in ("localhost", "localhost.localdomain"):
            return True
        # urlsplit().hostname 会去掉 IPv6 的方括号，此处统一还原后再校验
        if ":" in host:
            host = f"[{host}]"
        return bool(_HOST_RE.match(host))
    except Exception:
        return False
