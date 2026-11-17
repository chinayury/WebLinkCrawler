# Copyright (C) 2026 智维ITMSKY
# SPDX-License-Identifier: AGPL-3.0-or-later

"""网络边界防护：协议、主机与重定向目标校验。"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit


class UnsafeUrlError(ValueError):
    """目标协议、主机或重定向不符合安全策略。"""


# RFC 6598 共享地址空间（运营商级 NAT，100.64.0.0/10）：
# Python 的 ipaddress.is_private 不覆盖该段，显式拦截，避免被当作公网地址放行（F-02）。
_CGNAT_NET = ipaddress.ip_network("100.64.0.0/10")


def is_ip_literal(host):
    """主机是否为 IP 字面量（IPv4 或方括号 IPv6）；域名返回 False。"""
    try:
        ipaddress.ip_address((host or "").strip("[]"))
        return True
    except ValueError:
        return False


def is_private_host(host):
    """判断主机是否为回环、链路本地、私有或未指定地址。

    覆盖：RFC1918 私有段、回环、链路本地、保留、未指定、组播、
    CGNAT 100.64.0.0/10，以及 IPv4-mapped IPv6（::ffff:x.x.x.x 按内层
    IPv4 判定，堵住「映射绕过」）。
    """
    host = (host or "").strip("[]").rstrip(".").lower()
    if host in ("localhost", "localhost.localdomain", "ip6-localhost"):
        return True
    try:
        ip = ipaddress.ip_address(host)
        if ip.version == 6 and ip.ipv4_mapped is not None:
            ip = ip.ipv4_mapped
        if ip.version == 4 and ip in _CGNAT_NET:
            return True
        return bool(
            ip.is_private or ip.is_loopback or ip.is_link_local
            or ip.is_reserved or ip.is_unspecified or ip.is_multicast
        )
    except ValueError:
        return False


def resolved_is_private(host):
    """解析域名并判断是否落入私有/回环范围。

    返回三态：
    - True：任一解析结果为私有/回环/CGNAT 地址；
    - False：全部解析结果为公网地址；
    - None：解析失败（DNS 不可用等），无法判定。

    调用方必须把 None 按「不安全」处理（fail-closed）：旧实现解析失败
    返回 False 直接放行，等于把 DNS 故障变成 SSRF 窗口（F-03）。
    """
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
        addresses = {info[4][0] for info in infos}
    except (socket.gaierror, OSError):
        return None
    return any(is_private_host(address) for address in addresses)


def resolve_pinned_ip(host, *, allow_private=True):
    """解析主机并返回用于建连的 IP（DNS 重绑定 TOCTOU 防护，F-03 余项）。

    「校验时解析一次、连接时再解析一次」之间存在重绑定窗口；本函数把
    「解析 + 私有地址判定」与建连收敛到一次：连接层拿本函数返回的 IP
    直连，SNI/证书校验仍用原域名（urllib3 2.x ``server_hostname``）。

    返回值语义：
    - IP 字面量主机（含 127.0.0.1 这类回环字面量与代理场景）→ ``None``，
      无需解析，按原样建连即为「已钉定」；
    - 其他主机 → 首个公网 IP（IPv4 优先）；
    - 全部解析结果为私有/回环且 allow_private=False（默认拦截策略）→
      抛 :class:`UnsafeUrlError`（fail-closed）；
    - allow_private=True（内网站点开关）→ 私有地址正常返回；
    - 解析失败 → 抛 :class:`UnsafeUrlError`（与 F-03 的 fail-closed 口径一致）。
    """
    host = (host or "").strip()
    if is_ip_literal(host):
        return None
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
        # 去重保序：getaddrinfo 可能对同一地址返回多行（不同 socktype）
        addresses = list(dict.fromkeys(info[4][0] for info in infos))
    except (socket.gaierror, OSError) as exc:
        raise UnsafeUrlError(f"DNS 解析失败: {host}") from exc
    public = [a for a in addresses if not is_private_host(a)]
    if public:
        v4 = [a for a in public if ":" not in a]
        return (v4 or public)[0]
    if allow_private and addresses:
        v4 = [a for a in addresses if ":" not in a]
        return (v4 or addresses)[0]
    raise UnsafeUrlError(f"私有或回环地址已按策略拦截: {host}")


def validate_target(url, *, follow_redirect=False, allow_private=True,
    allowed_netloc=None):
    """校验 URL结构、协议、凭据与重定向归属。"""
    try:
        parts = urlsplit(url)
        port = parts.port #触发端口格式校验
    except (TypeError, ValueError) as exc:
        raise UnsafeUrlError(f"URL格式无效: {exc}") from exc
    if parts.scheme.lower() not in ("http", "https"):
        raise UnsafeUrlError("仅支持 HTTP/HTTPS抓取")
    if len(url) >8192:
        raise UnsafeUrlError("URL长度超过限制")
    if not parts.hostname:
        raise UnsafeUrlError("URL缺少主机名")
    if parts.username is not None or parts.password is not None:
        raise UnsafeUrlError("URL不得包含用户名或密码")
    if port is not None and not (1 <= port <=65535):
        raise UnsafeUrlError("URL端口超出范围")
    if follow_redirect and allowed_netloc:
        if parts.netloc.lower() != allowed_netloc.lower():
            raise UnsafeUrlError("重定向跨域，已停止")
    if not allow_private and is_private_host(parts.hostname):
        raise UnsafeUrlError("目标属于私有或回环地址，已按策略拦截")
    return url
