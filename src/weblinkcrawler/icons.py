# Copyright (C) 2026 智维ITMSKY
# SPDX-License-Identifier: AGPL-3.0-or-later

"""纯 Python 线性图标渲染（无第三方图像依赖）—— 「墨线」Ink-Line 风格。

与旧版（2px 直角折线）的差异：
- **描边宽度**：主笔 1.6px（旧 2.0px），细笔 1.2px，强调笔 1.9px，三级笔宽构成
  墨色浓淡层次；
- **拐角处理**：所有折线拐角与端点统一为圆头（round cap / round join），
  由端点实心圆点（dot）与顶点圆点叠加实现，去掉旧版的直角尖角；
- **网格**：24×24 归一化盒，内容统一内缩 2px（2..22），几何中心对齐，
  圆角容器半径 2.5，保证小尺寸（17px）下不糊边；
- **造型语言**：以「圆角矩形 + 圆头折线 + 实心圆点」三种基本件拼装，
  闭合容器一律圆角，开放式轨迹（托盘、抽屉、罐体）用折线表达，
  与「宣纸·墨黛」的近单色纸面呼应。

渲染机制不变：3×3 超采样软件光栅化，按前景/背景覆盖率混合出抗锯齿边缘，
经 ``tk.PhotoImage.put`` 生成位图；容器背景已知且为纯色，无需 alpha 通道。

对外契约不变：:func:`photo` / :func:`icon` / :func:`available`；
既有 32 个图标名全部保留（本轮新增 ``seal`` / ``refresh``，共 34 个）。
"""

from __future__ import annotations

import math

try:  # 允许在无显示环境导入（仅在使用 photo() 时才需要 Tk）
    import tkinter as tk
except Exception:  # pragma: no cover
    tk = None

# ---- 墨线风格常量 ---------------------------------------------------------
W = 1.6        # 主笔宽
W_THIN = 1.2   # 细笔宽（内部细节、次要结构）
W_BOLD = 1.9   # 强调笔宽（勾选、主操作）
R_CORNER = 2.5  # 圆角容器半径

# ---- 图元构造助手（坐标均在 0..24 归一化盒内） -----------------------------

def poly(points, width=2, fill=False):
    """（兼容旧版）折线图元。"""
    return ("poly", [tuple(p) for p in points], width, fill)


def circle(cx, cy, r, width=2, fill=False):
    """（兼容旧版）圆图元。"""
    return ("circle", (cx, cy), r, width, fill)


def rect(x, y, w, h, width=2, fill=False):
    """（兼容旧版）直角矩形图元。"""
    return ("rect", (x, y, w, h), width, fill)


def line(x1, y1, x2, y2, width=2):
    """（兼容旧版）单段直线。"""
    return ("poly", [(x1, y1), (x2, y2)], width, False)


def dot(cx, cy, r):
    """实心圆点（随尺寸缩放）——圆头端点 / 拐角 / 节点。"""
    return ("dot", (cx, cy), r)


def arc(cx, cy, r, a0, a1, width=W, cap=True):
    """圆弧（角度制，0° 指向右，顺时针为正，a1 > a0）；cap 控制两端圆头。"""
    ops = [("arc", (cx, cy), r, a0, a1, width)]
    if cap:
        for a in (a0, a1):
            rad = math.radians(a)
            ops.append(("dot", (cx + r * math.cos(rad), cy + r * math.sin(rad)),
                        width / 2.0))
    return ops


def roundrect(x, y, w, h, r=R_CORNER, width=W, fill=False):
    """圆角矩形（新版闭合容器的标准件）。"""
    return ("roundrect", (x, y, w, h), r, width, fill)


def stroke(points, width=W, closed=False):
    """圆头折线：折线本体 + 每个顶点/端点的实心圆点（round join + round cap）。"""
    pts = [tuple(p) for p in points]
    if closed and pts[0] != pts[-1]:
        pts.append(pts[0])
    ops = [("poly", pts, width, False)]
    hw = width / 2.0
    for pt in pts:
        ops.append(("dot", pt, hw))
    return ops


# ---- 图标库（24×24 归一化盒，内容内缩 2px） ---------------------------------

ICONS = {
    # 品牌 / 链接
    "link": [
        circle(8.6, 15.4, 4.2, W),
        circle(15.4, 8.6, 4.2, W),
        *stroke([(10.8, 13.2), (13.2, 10.8)], W),
    ],
    "seal": [  # 新增：品牌标记（圆角印框 + 内嵌链环）
        roundrect(3.4, 3.4, 17.2, 17.2, 3.6, 1.8),
        circle(9.2, 14.8, 3.0, 1.5),
        circle(14.8, 9.2, 3.0, 1.5),
        *stroke([(11.2, 12.8), (12.8, 11.2)], 1.5),
    ],
    # 检索 / 观察
    "search": [
        circle(10.8, 10.8, 6.4, W),
        *stroke([(15.6, 15.6), (20.4, 20.4)], W),
    ],
    "globe": [
        circle(12, 12, 8.8, W),
        *stroke([(3.6, 12), (20.4, 12)], W_THIN),
        *stroke([(12, 3.6), (12, 20.4)], W_THIN),
    ],
    "radar": [
        circle(12, 12, 8.4, W_THIN),
        circle(12, 12, 4.8, W_THIN),
        *stroke([(12, 12), (17, 7)], W),
        dot(12, 12, 1.3),
    ],
    "pulse": [
        *stroke([(2.6, 12), (7.4, 12), (9.6, 6.6), (13, 17.4),
                 (15, 12), (21.4, 12)], W),
    ],
    "chart": [
        *stroke([(4, 4), (4, 20)], W),
        *stroke([(4, 20), (20, 20)], W),
        roundrect(7, 13.4, 3.2, 6.6, 1.2, 0, True),
        roundrect(12, 10, 3.2, 10, 1.2, 0, True),
        roundrect(17, 6.4, 3.2, 13.6, 1.2, 0, True),
    ],
    # 传输 / 文件
    "download": [
        *stroke([(12, 3.4), (12, 13.6)], W),
        *stroke([(7.6, 9.6), (12, 14), (16.4, 9.6)], W),
        *stroke([(4.2, 14.6), (4.2, 19.4), (19.8, 19.4), (19.8, 14.6)], W),
    ],
    "upload": [
        *stroke([(12, 14.6), (12, 4.4)], W),
        *stroke([(7.6, 8.4), (12, 3.2), (16.4, 8.4)], W),
        *stroke([(4.2, 19.6), (4.2, 14.4), (19.8, 14.4), (19.8, 19.6)], W),
    ],
    "save": [
        roundrect(5, 3, 14, 18, 2.2, W),
        *stroke([(8.2, 3), (8.2, 9), (15.8, 9), (15.8, 3)], W),
        dot(12, 15.6, 1.7),
    ],
    "folder": [
        *stroke([(3.4, 6.4), (9, 6.4), (11.2, 8.8), (20.6, 8.8),
                 (20.6, 19.2), (3.4, 19.2), (3.4, 6.4)], W),
    ],
    "doc": [
        *stroke([(5.2, 3), (14, 3), (18.8, 7.8), (18.8, 21),
                 (5.2, 21), (5.2, 3)], W),
        *stroke([(14, 3), (14, 7.8), (18.8, 7.8)], W_THIN),
        *stroke([(8.4, 13), (15.6, 13)], W_THIN),
        *stroke([(8.4, 16.6), (15.6, 16.6)], W_THIN),
    ],
    "copy": [
        *stroke([(4.9, 14.9), (4.9, 6.1), (6.1, 4.9), (14.9, 4.9),
                 (14.9, 8.9)], W),
        roundrect(9.1, 9.1, 11.8, 11.8, 2.2, W),
    ],
    "database": [
        circle(12, 6.4, 7.4, W),
        *stroke([(4.6, 6.4), (4.6, 17.2)], W),
        *stroke([(19.4, 6.4), (19.4, 17.2)], W),
        *arc(12, 17.2, 7.4, 0, 180, W),
    ],
    # 运行控制
    "play": [
        ("poly", [(8, 5), (19, 12), (8, 19)], 0, True),
        dot(8, 5, 1.2), dot(19, 12, 1.2), dot(8, 19, 1.2),
    ],
    "pause": [
        roundrect(6.8, 5, 3.6, 14, 1.6, 0, True),
        roundrect(13.6, 5, 3.6, 14, 1.6, 0, True),
    ],
    "stop": [
        roundrect(6.4, 6.4, 11.2, 11.2, 2.4, 0, True),
    ],
    "clock": [
        circle(12, 12, 8.8, W),
        *stroke([(12, 7), (12, 12), (16, 14)], W),
    ],
    "refresh": [  # 新增：重抓 / 重试（圆头圆弧 + 箭头）
        *arc(12, 12, 8.2, 45, 315, W),
        *stroke([(15.1, 5.5), (17.8, 6.2), (17.1, 3.5)], W),
    ],
    # 筛选 / 规则
    "filter": [
        *stroke([(3.4, 5), (20.6, 5), (14, 12.4), (14, 19.2),
                 (9.8, 19.2), (9.8, 12.4), (3.4, 5)], W),
    ],
    "rules": [
        *stroke([(3.4, 6), (20.6, 6)], W),
        *stroke([(3.4, 12), (20.6, 12)], W),
        *stroke([(3.4, 18), (20.6, 18)], W),
        dot(9, 6, 2.4), dot(15.2, 12, 2.4), dot(7, 18, 2.4),
    ],
    "settings": [  # 齿轮：外环 + 八齿 + 轴孔
        circle(12, 12, 6.6, W),
        circle(12, 12, 3.0, W),
        *stroke([(18.6, 12), (21, 12)], W),
        *stroke([(16.7, 16.7), (18.4, 18.4)], W),
        *stroke([(12, 18.6), (12, 21)], W),
        *stroke([(7.3, 16.7), (5.6, 18.4)], W),
        *stroke([(5.4, 12), (3, 12)], W),
        *stroke([(7.3, 7.3), (5.6, 5.6)], W),
        *stroke([(12, 5.4), (12, 3)], W),
        *stroke([(16.7, 7.3), (18.4, 5.6)], W),
    ],
    "target": [
        circle(12, 12, 8, W),
        dot(12, 12, 2.2),
        *stroke([(12, 1.6), (12, 4.6)], W),
        *stroke([(12, 19.4), (12, 22.4)], W),
        *stroke([(1.6, 12), (4.6, 12)], W),
        *stroke([(19.4, 12), (22.4, 12)], W),
    ],
    # 数据 / 列表
    "table": [  # 仅横向细线，呼应新版表格造型
        roundrect(3.4, 4.4, 17.2, 15.2, 2, W),
        *stroke([(3.4, 9.6), (20.6, 9.6)], W_THIN),
        *stroke([(3.4, 14.6), (20.6, 14.6)], W_THIN),
    ],
    "list": [
        dot(5, 6, 1.35), dot(5, 12, 1.35), dot(5, 18, 1.35),
        *stroke([(9, 6), (20, 6)], W),
        *stroke([(9, 12), (20, 12)], W),
        *stroke([(9, 18), (20, 18)], W),
    ],
    "grid": [
        roundrect(3.4, 3.4, 7.4, 7.4, 1.8, W),
        roundrect(13.2, 3.4, 7.4, 7.4, 1.8, W),
        roundrect(3.4, 13.2, 7.4, 7.4, 1.8, W),
        roundrect(13.2, 13.2, 7.4, 7.4, 1.8, W),
    ],
    "layers": [
        *stroke([(12, 3), (21, 8), (12, 13), (3, 8), (12, 3)], W_THIN),
        *stroke([(3, 12), (12, 17), (21, 12)], W_THIN),
        *stroke([(3, 16), (12, 21), (21, 16)], W_THIN),
    ],
    "compass": [
        circle(12, 12, 8.6, W),
        *stroke([(15.6, 8.4), (13.2, 13.2), (8.4, 15.6), (10.8, 10.8),
                 (15.6, 8.4)], W_THIN),
    ],
    # 状态 / 安全
    "check": [
        *stroke([(4.8, 12.6), (10, 17.8), (19.2, 6.4)], W_BOLD),
    ],
    "shield": [
        *stroke([(12, 3), (20, 6), (20, 12), (12, 21), (4, 12), (4, 6),
                 (12, 3)], W),
        *stroke([(9, 11.8), (11.4, 14.2), (15.4, 9.4)], W),
    ],
    "info": [
        circle(12, 12, 8.8, W),
        dot(12, 7.6, 1.25),
        *stroke([(12, 11), (12, 16.4)], W),
    ],
    "spark": [  # 四角星 + 辅点：配色 / 灵感
        *stroke([(12, 3), (14.2, 9.8), (21, 12), (14.2, 14.2),
                 (12, 21), (9.8, 14.2), (3, 12), (9.8, 9.8), (12, 3)], W),
        dot(18.6, 5.4, 1.1),
    ],
    "close": [  # 新增：取消全选 / 清除
        *stroke([(6.6, 6.6), (17.4, 17.4)], W),
        *stroke([(17.4, 6.6), (6.6, 17.4)], W),
    ],
    # 清理 / 外链
    "trash": [
        *stroke([(4.6, 7), (19.4, 7)], W),
        *stroke([(9.6, 7), (9.6, 4.2)], W),
        *stroke([(14.4, 7), (14.4, 4.2)], W),
        *stroke([(6.4, 7), (6.4, 19.2), (17.6, 19.2), (17.6, 7)], W),
        *stroke([(10.2, 11), (10.2, 16.4)], W_THIN),
        *stroke([(13.8, 11), (13.8, 16.4)], W_THIN),
    ],
    "external": [
        *stroke([(14, 3.6), (20.4, 3.6), (20.4, 10)], W),
        *stroke([(19.6, 4.4), (4.4, 19.6)], W),
        *stroke([(13, 20.4), (20.4, 20.4), (20.4, 13)], W),
    ],
}


# ---- 光栅化 ---------------------------------------------------------------

def _dist_point_seg(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _in_roundrect(px, py, x, y, w, h, r):
    """点是否落在圆角矩形内（含圆角）。"""
    if px < x or px > x + w or py < y or py > y + h:
        return False
    if x + r <= px <= x + w - r or y + r <= py <= y + h - r:
        return True
    qx = min(max(px, x + r), x + w - r)
    qy = min(max(py, y + r), y + h - r)
    return math.hypot(px - qx, py - qy) <= r


def _point_ink(px, py, ops, s, sw_scale):
    """判断像素坐标系中的点是否落在墨迹上。s 为缩放系数。"""
    for op in ops:
        kind = op[0]
        if kind == "poly":
            pts, width, fill = op[1], op[2], op[3]
            hw = (width * sw_scale) / 2.0
            sp = [(x * s, y * s) for (x, y) in pts]
            if fill:
                if _point_in_poly(px, py, sp):
                    return True
            else:
                for i in range(len(sp) - 1):
                    ax, ay = sp[i]
                    bx, by = sp[i + 1]
                    if _dist_point_seg(px, py, ax, ay, bx, by) <= hw:
                        return True
        elif kind == "circle":
            (cx, cy), r, width, fill = op[1], op[2], op[3], op[4]
            ccx, ccy, cr = cx * s, cy * s, r * s
            d = math.hypot(px - ccx, py - ccy)
            if fill:
                if d <= cr:
                    return True
            else:
                if abs(d - cr) <= (width * sw_scale) / 2.0:
                    return True
        elif kind == "dot":
            (cx, cy), r = op[1], op[2]
            if math.hypot(px - cx * s, py - cy * s) <= r * s:
                return True
        elif kind == "rect":
            (x, y, w, h), width, fill = op[1], op[2], op[3]
            rx, ry, rw, rh = x * s, y * s, w * s, h * s
            inside = rx <= px <= rx + rw and ry <= py <= ry + rh
            if fill:
                if inside:
                    return True
            else:
                hw = (width * sw_scale) / 2.0
                if inside and (px - rx <= hw or rx + rw - px <= hw
                               or py - ry <= hw or ry + rh - py <= hw):
                    return True
        elif kind == "roundrect":
            (x, y, w, h), r, width, fill = op[1], op[2], op[3], op[4]
            rx, ry, rw, rh = x * s, y * s, w * s, h * s
            rr = r * s
            if fill:
                if _in_roundrect(px, py, rx, ry, rw, rh, rr):
                    return True
            else:
                hw = (width * sw_scale) / 2.0
                if (_in_roundrect(px, py, rx, ry, rw, rh, rr)
                        and not _in_roundrect(px, py, rx + hw, ry + hw,
                                              rw - 2 * hw, rh - 2 * hw,
                                              max(0.0, rr - hw))):
                    return True
        elif kind == "arc":
            (cx, cy), r, a0, a1, width = op[1], op[2], op[3], op[4], op[5]
            ccx, ccy, cr = cx * s, cy * s, r * s
            d = math.hypot(px - ccx, py - ccy)
            if abs(d - cr) <= (width * sw_scale) / 2.0:
                ang = math.degrees(math.atan2(py - ccy, px - ccx)) % 360.0
                start, end = a0 % 360.0, a1 % 360.0
                if end < start:
                    end += 360.0
                if start <= (ang if ang >= start else ang + 360.0) <= end:
                    return True
    return False


def _point_in_poly(px, py, poly_pts):
    inside = False
    n = len(poly_pts)
    j = n - 1
    for i in range(n):
        xi, yi = poly_pts[i]
        xj, yj = poly_pts[j]
        if ((yi > py) != (yj > py)) and \
                (px < (xj - xi) * (py - yi) / (yj - yi + 1e-12) + xi):
            inside = not inside
        j = i
    return inside


def _blend(bg, fg, cov):
    if cov <= 0:
        return bg
    if cov >= 1:
        return fg
    return tuple(int(round(bg[k] + (fg[k] - bg[k]) * cov)) for k in range(3))


def _hex(rgb):
    return "#%02x%02x%02x" % (rgb[0] & 255, rgb[1] & 255, rgb[2] & 255)


def _parse_color(c):
    if isinstance(c, str):
        c = c.lstrip("#")
        if len(c) == 3:
            c = "".join(ch * 2 for ch in c)
        return (int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16))
    return tuple(c[:3])


# ---- 全部已创建 PhotoImage 的强引用注册表 ----------------------------------
# Tk 对象被 cyclic GC 回收时会执行 PhotoImage.__del__（调用 Tcl），若回收
# 发生在非主线程（如抓取工作线程），不满足 Tcl 线程模型，Windows 下实测
# 致命异常（0x80000003，见开发日志 S-11 / 安全审查报告 F-13）。
# 客户端进程内图标规模有界（图标 × 配色 × 尺寸，百级），注册表内存代价可忽略。
_ALL_IMAGES = []


def photo(name, fg, bg, size=20, master=None):
    """生成图标 PhotoImage。需在 Tk root 存在后调用。"""
    if tk is None:
        raise RuntimeError("tkinter 不可用，无法渲染图标")
    if name not in ICONS:
        raise KeyError(f"未知图标: {name}")
    ops = ICONS[name]
    s = size / 24.0
    # 墨线风格：随尺寸轻微缩放笔画，但保持"线性"观感（下限 1.0）
    sw_scale = max(1.0, size / 24.0)
    fg_rgb = _parse_color(fg)
    bg_rgb = _parse_color(bg)
    samples = (0.25, 0.5, 0.75)
    img = tk.PhotoImage(master=master, width=size, height=size)
    for py in range(size):
        cols = []
        for px in range(size):
            ink = 0
            for sy in samples:
                for sx in samples:
                    if _point_ink(px + sx, py + sy, ops, s, sw_scale):
                        ink += 1
            cov = ink / (len(samples) ** 2)
            cols.append(_hex(_blend(bg_rgb, fg_rgb, cov)))
        # 按行写入：Tk 的 photo put 要求「行列表」结构——整行用花括号包成一个
        # Tcl 列表元素；若直接传扁平颜色列表，Tcl 会把每个颜色当成独立的一行
        # （整行纯色），导致除首行外全部留空（旧版图标不显示的根因）。
        img.put("{" + " ".join(cols) + "}", to=(0, py, size, py + 1))
    # 强引用登记：保证 Tk 对象只在主线程解释器退出时收尾，绝不进工作线程
    # 的 cyclic GC（与测试侧 conftest 的 gc.disable() 对称防护）
    _ALL_IMAGES.append(img)
    return img


# ---- 带缓存获取 -----------------------------------------------------------

_cache = {}


def _cache_key(name, fg, bg, size):
    """缓存键：把当前默认 Tk 根一并纳入。

    PhotoImage 归属于创建时的 Tk 解释器；同一进程若出现第二个根
    （测试脚手架、嵌入场景），跨根复用缓存图像会报
    ``image "pyimageNN" doesn't exist``。按根分区后，每个根各自缓存，
    单根产品行为不变。根对象进键同时保持强引用，避免 id 复用造成误命中。
    """
    root = getattr(tk, "_default_root", None)
    return (root, name, _hex(_parse_color(fg)), _hex(_parse_color(bg)), size)


def icon(name, fg, bg, size=20):
    key = _cache_key(name, fg, bg, size)
    img = _cache.get(key)
    if img is None:
        img = photo(name, fg, bg, size)
        _cache[key] = img  # 保持引用，防止被 Tk 回收
    return img


def available():
    return sorted(ICONS.keys())
