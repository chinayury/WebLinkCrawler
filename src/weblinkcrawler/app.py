"""WebLinkCrawler GUI —— 「宣纸·墨黛」视觉体系（Rice Paper & Ink）。

版式：浅色纸底分组导航栏 + 右侧工作区（顶栏 + 分页面板）；面板为「通栏纸底
标题带 + 底部 1px 细线」，无左侧色条；按钮分「实底 / 1px 描边 / 纯文字链」三档。
交互：所有后台事件经线程安全队列回主线程更新，GUI 元素只在主线程读写。
功能：完整保留 v0.1.0 既有能力——单/多 URL、筛选、文件类型编辑、深度抓取、
反反爬、断点续爬、元素选择/CSS 选择器、链接体检、TXT/CSV/JSON 导出。
"""

from __future__ import annotations

import importlib.util
import json
import math
import os
import queue
import re
import subprocess
import sys
import tempfile
import threading
import webbrowser
from datetime import datetime

import tkinter as tk
from tkinter import filedialog, messagebox

import ttkbootstrap as ttk

from . import APP_SITE, APP_VENDOR, APP_VERSION, theme
from .config import ConfigManager, is_valid_url, normalize_url
from .crawler import CrawlerEngine
from .database import DatabaseManager
from .logutil import get_logger, setup_logging

log = get_logger()


def _qt_webengine_available():
    """无导入探测 PyQt5 + QtWebEngine，避免在主进程创建 Qt 环境。"""
    try:
        spec = importlib.util.find_spec("PyQt5")
        if spec is None:
            return False
        for base in spec.submodule_search_locations or []:
            for name in ("QtWebEngineWidgets.pyd", "QtWebEngineWidgets.py",
                "QtWebEngineWidgets.so", "QtWebEngineWidgets.dylib"):
                if os.path.isfile(os.path.join(base, name)):
                    return True
    except Exception:
        pass
    return False


PYQT_WEB = _qt_webengine_available()

# 独立网页预览进程（与 Tk 主循环分进程，避免 Qt/Tk 事件循环冲突）
_PREVIEW_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "preview.py")
_PREVIEW_POLL_MS = 300
_PREVIEW_POLL_MAX = 600

# 体检状态 → 中文文案 / 表格标签色
_STATE_TEXT = {
    "ok": "可用", "redirect": "重定向", "dead": "失效",
    "blocked": "受限", "error": "异常", "": "未检",
}
_STATE_TAG = {
    "ok": "ok", "redirect": "redirect", "dead": "dead",
    "blocked": "blocked", "error": "error", "": "unknown",
}
# 按钮样式 → 底色（用于图标前景/背景配对）
_ROLE_BG = {
    "Primary.TButton": theme.PRIMARY, "Success.TButton": theme.SUCCESS,
    "Warning.TButton": theme.WARNING, "Danger.TButton": theme.DANGER,
    "Info.TButton": theme.INFO, "Accent.TButton": theme.ACCENT,
    "Secondary.TButton": theme.SURFACE, "AccentOutline.TButton": theme.SURFACE,
    "InfoOutline.TButton": theme.SURFACE, "DangerOutline.TButton": theme.SURFACE,
    "Ghost.TButton": theme.SURFACE,
}
# 描边按钮的前景文字色
_OUTLINE_FG = {
    "Secondary.TButton": theme.PRIMARY, "AccentOutline.TButton": theme.ACCENT,
    "InfoOutline.TButton": theme.INFO, "DangerOutline.TButton": theme.DANGER,
    "Ghost.TButton": theme.INK,
}


class App:
    """应用主窗口：装配导航、页面、控件与业务交互。"""

    # 导航项 → 图标名（兜底映射；导航项自身也记录图标名，配色切换时据此重绘）
    _NAV_ICONS = {
        "targets": "radar", "results": "table",
        "logs": "list", "settings": "settings",
    }

    def __init__(self, root):
        self.root = root
        self.root.title(f"网页链接抓取工具 · WebLinkCrawler v{APP_VERSION}")
        self.root.geometry("1360x880")
        self.root.minsize(1120, 720)

        self.config = ConfigManager()
        self.config.load_file_types()
        self.config.load_enhanced()
        self.db = DatabaseManager()
        self.engine = CrawlerEngine(self.config, self.db)

        # ---- 运行时状态 ----
        self.all_records = []          # [{"link","file_type","protocol","depth","state"}]
        self.filtered_records = []
        self.link_states = {}          # link -> (state, code)
        self.is_crawling = False
        self.is_checking = False
        self._paused = False
        self._sort_col = None
        self._sort_rev = False
        self.events = queue.Queue()
        self._resume_mode = False
        self._preview_proc = None
        self._preview_result_path = None
        self._preview_seq = 0
        self._pages = {}
        self._nav_buttons = {}
        self._icon_slots = []
        # 配色切换时需重绘的 tk 元素登记表（背景 / 前景 / 面板标题带）
        self._surface_slots = []   # [(widget, 背景令牌名)]
        self._fg_slots = []        # [(widget, 前景令牌名)]
        self._panel_slots = []     # [(band, line, body, icon_label, 图标名)]
        self._menus = []           # [tk.Menu]，随配色重绘菜单配色

        self.style = ttk.Style()
        try:
            self.style.theme_use("bootstrap-light")
        except Exception:
            pass
        theme.apply_theme(self.style, self.root)

        self._build_menu()
        self._build_shell()
        self._build_pages()
        self._bind_shortcuts()

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(60, self._poll_events)
        self._show_page("targets")

    # =====================================================================
    # 通用构件
    # =====================================================================
    def _reg_surface(self, widget, token):
        """登记 tk 容器背景：配色切换时按令牌重绘，避免残留旧配色底色。"""
        self._surface_slots.append((widget, token))

    def _reg_fg(self, widget, token):
        """登记 tk 文字前景：配色切换时按令牌重绘。"""
        self._fg_slots.append((widget, token))

    def _panel(self, parent, title, subtitle="", icon="grid", expand=True):
        """构造一个面板：通栏纸底标题带 + 底部 1px 细线 + 内容区。返回内容区。

        新版去掉「左侧 3px 彩色色条」，标题带用 `PANEL_BAND_BG` 纸底与主体白底
        区分，层级靠字重与字号表达；面板图标置于标题带右端（朱印色）。
        `expand=False` 用于内容较少的滚动页，让面板按内容高度排布而非被拉高。
        """
        panel = tk.Frame(parent, bg=theme.SURFACE, highlightbackground=theme.BORDER,
                         highlightthickness=1, bd=0)
        panel.pack(fill=tk.BOTH, expand=expand,
                   padx=theme.SPACE_XL, pady=(0, theme.SPACE_XL))

        head = tk.Frame(panel, bg=theme.PANEL_BAND_BG, height=theme.BAND_H)
        head.pack(fill=tk.X)
        head.pack_propagate(False)

        text_box = tk.Frame(head, bg=theme.PANEL_BAND_BG)
        text_box.pack(side=tk.LEFT, fill=tk.Y, padx=(theme.PANEL_PAD_X, 0))
        ttk.Label(text_box, text=title, style="BandTitle.TLabel").pack(anchor="w")
        if subtitle:
            ttk.Label(text_box, text=subtitle, style="BandSub.TLabel").pack(anchor="w")

        ic = ttk.Label(head, image=theme.ico(icon, theme.ACCENT,
                                             theme.PANEL_BAND_BG, 22),
                       background=theme.PANEL_BAND_BG)
        ic.image = theme.ico(icon, theme.ACCENT, theme.PANEL_BAND_BG, 22)
        ic.pack(side=tk.RIGHT, padx=(0, theme.PANEL_PAD_X))

        line = tk.Frame(panel, bg=theme.PANEL_BAND_LINE, height=1)
        line.pack(fill=tk.X)

        body = tk.Frame(panel, bg=theme.SURFACE)
        body.pack(fill=tk.BOTH, expand=True, padx=theme.PANEL_PAD_X,
                  pady=(theme.SPACE_MD, theme.SPACE_MD))
        self._panel_slots.append((head, line, body, ic, icon))
        return body

    def _btn(self, parent, text, icon, role, command, width=None):
        """构造带自绘线性图标的按钮。

        按钮会被登记到 self._icon_slots，配色方案切换时据此重绘图标，
        避免沿用旧配色的缓存位图。
        """
        img = None
        if icon:
            bg = _ROLE_BG.get(role, theme.PRIMARY)
            fg = _OUTLINE_FG.get(role, "#FFFFFF")
            img = theme.ico(icon, fg, bg, 17)
        btn = ttk.Button(parent, text=text, image=img, compound="left", style=role,
                         command=command)
        if img:
            btn.image = img
        if icon:
            self._icon_slots.append((btn, icon, role, 17))
        if width:
            btn.configure(width=width)
        return btn

    @staticmethod
    def _field_label(parent, text, hint=""):
        """构造带说明的字段标签（说明以次要色小字紧随其后）。"""
        box = tk.Frame(parent, bg=theme.SURFACE)
        box.pack(fill=tk.X, pady=(0, 4))
        ttk.Label(box, text=text, style="Section.TLabel").pack(side=tk.LEFT)
        if hint:
            ttk.Label(box, text=hint, style="Muted.TLabel").pack(side=tk.LEFT, padx=(8, 0))
        return box

    # =====================================================================
    # 菜单
    # =====================================================================
    def _menu_colors(self):
        """菜单配色（tk.Menu 不走 ttk 样式，需按当前配色手动给出）。"""
        return {
            "bg": theme.SURFACE, "fg": theme.INK,
            "activebackground": theme.PRIMARY_SOFT,
            "activeforeground": theme.INK_STRONG,
            "bd": 0, "relief": "flat",
        }

    def _make_menu(self, parent):
        """构造带「宣纸·墨黛」配色的下拉菜单，并登记以便配色切换时重绘。"""
        menu = tk.Menu(parent, tearoff=0, **self._menu_colors())
        self._menus.append(menu)
        return menu

    def _build_menu(self):
        menubar = tk.Menu(self.root, **self._menu_colors())
        self.root.config(menu=menubar)
        self._menus.append(menubar)

        file_menu = self._make_menu(menubar)
        menubar.add_cascade(label="文件", menu=file_menu)
        file_menu.add_command(label="保存链接到文件", command=self.save_links,
                              accelerator="Ctrl+S")
        file_menu.add_command(label="导出 URL 列表", command=self.export_urls)
        file_menu.add_separator()
        file_menu.add_command(label="退出", command=self._on_close)

        edit_menu = self._make_menu(menubar)
        menubar.add_cascade(label="编辑", menu=edit_menu)
        edit_menu.add_command(label="清除所有", command=self.clear_all,
                              accelerator="Ctrl+D")
        edit_menu.add_command(label="切换配色方案", command=self.toggle_theme)
        edit_menu.add_separator()
        edit_menu.add_command(label="编辑文件类型", command=self.edit_file_types)
        edit_menu.add_command(label="增强功能配置", command=self.configure_enhanced)

        help_menu = self._make_menu(menubar)
        menubar.add_cascade(label="帮助", menu=help_menu)
        help_menu.add_command(label="使用说明", command=self._show_help)
        help_menu.add_command(label="关于", command=self.show_about)

    def _bind_shortcuts(self):
        self.root.bind("<Control-s>", lambda e: self.save_links())
        self.root.bind("<Control-d>", lambda e: self.clear_all())
        self.root.bind("<Control-1>", lambda e: self._show_page("targets"))
        self.root.bind("<Control-2>", lambda e: self._show_page("results"))
        self.root.bind("<Control-3>", lambda e: self._show_page("logs"))

    # =====================================================================
    # 外壳：左侧导航栏 + 右侧工作区
    # =====================================================================
    def _build_shell(self):
        shell = tk.Frame(self.root, bg=theme.BG)
        shell.pack(fill=tk.BOTH, expand=True)

        self._build_rail(shell)
        self._build_workbench(shell)

    # ---- 左侧导航栏 ----
    def _build_rail(self, parent):
        """浅色纸底导航：无深色栏，右侧 1px 边线与画布分隔。"""
        outer = tk.Frame(parent, bg=theme.BG)
        outer.pack(side=tk.LEFT, fill=tk.Y)

        rail = tk.Frame(outer, bg=theme.RAIL, width=theme.RAIL_W)
        rail.pack(side=tk.LEFT, fill=tk.Y)
        rail.pack_propagate(False)
        self._rail = rail
        # 导航右侧 1px 边线（与画布分隔）
        edge = tk.Frame(outer, bg=theme.RAIL_EDGE, width=1)
        edge.pack(side=tk.LEFT, fill=tk.Y)
        self._rail_edge = edge

        # 品牌区
        brand = tk.Frame(rail, bg=theme.RAIL)
        brand.pack(fill=tk.X, padx=theme.SPACE_LG, pady=(theme.SPACE_XL, theme.SPACE_LG))
        self._reg_surface(brand, "RAIL")
        mark = tk.Frame(brand, bg=theme.RAIL)
        mark.pack(side=tk.LEFT)
        self._reg_surface(mark, "RAIL")
        logo = ttk.Label(mark, image=theme.rail_ico("seal", theme.ACCENT, theme.RAIL, 24),
                         background=theme.RAIL)
        logo.image = theme.rail_ico("seal", theme.ACCENT, theme.RAIL, 24)
        logo.pack()
        self._rail_brand_icon = (logo, "seal")
        name = tk.Label(brand, text="WebLinkCrawler", bg=theme.RAIL, fg=theme.RAIL_FG,
                        font=theme.font(13, bold=True))
        name.pack(anchor="w", pady=(8, 0))
        self._reg_surface(name, "RAIL")
        self._reg_fg(name, "RAIL_FG")
        sub = tk.Label(brand, text=f"网页链接抓取工具 · v{APP_VERSION}", bg=theme.RAIL,
                       fg=theme.RAIL_FG_DIM, font=theme.font(9))
        sub.pack(anchor="w")
        self._reg_surface(sub, "RAIL")
        self._reg_fg(sub, "RAIL_FG_DIM")

        sep = tk.Frame(rail, bg=theme.RAIL_LINE, height=1)
        sep.pack(fill=tk.X, padx=theme.SPACE_LG, pady=(0, theme.SPACE_MD))
        self._rail_sep = sep

        # 分组导航
        nav = tk.Frame(rail, bg=theme.RAIL)
        nav.pack(fill=tk.X, padx=10)
        self._reg_surface(nav, "RAIL")
        groups = (
            ("作业", (("targets", "任务布设", "radar"),)),
            ("观测", (("results", "结果清册", "table"), ("logs", "事件流水", "list"))),
            ("整备", (("settings", "参数配置", "settings"),)),
        )
        for group_name, items in groups:
            head = tk.Label(nav, text=theme.track(group_name), bg=theme.RAIL,
                            fg=theme.RAIL_FG_DIM, font=theme.font(9, bold=True))
            head.pack(anchor="w", padx=10, pady=(theme.SPACE_MD, 4))
            self._reg_surface(head, "RAIL")
            self._reg_fg(head, "RAIL_FG_DIM")
            for key, label, icon in items:
                self._nav_buttons[key] = self._nav_item(nav, key, label, icon)

        # 底部信息
        foot = tk.Frame(rail, bg=theme.RAIL)
        foot.pack(side=tk.BOTTOM, fill=tk.X, padx=theme.SPACE_LG, pady=(0, theme.SPACE_LG))
        self._reg_surface(foot, "RAIL")
        self._rail_palette_label = tk.Label(
            foot, text=f"配色 · {theme.CURRENT_PALETTE}", bg=theme.RAIL,
            fg=theme.RAIL_FG_DIM, font=theme.font(9))
        self._rail_palette_label.pack(anchor="w")
        self._reg_surface(self._rail_palette_label, "RAIL")
        self._reg_fg(self._rail_palette_label, "RAIL_FG_DIM")
        copy_row = tk.Label(foot, text=f"© 2026 {APP_VENDOR}", bg=theme.RAIL,
                            fg=theme.RAIL_FG_DIM, font=theme.font(9))
        copy_row.pack(anchor="w")
        self._reg_surface(copy_row, "RAIL")
        self._reg_fg(copy_row, "RAIL_FG_DIM")

    def _nav_item(self, parent, key, label, icon):
        """单个导航项：图标 + 文案；激活态为 2px 朱红左杠 + 加粗墨字。"""
        holder = tk.Frame(parent, bg=theme.RAIL)
        holder.pack(fill=tk.X, pady=1)
        self._reg_surface(holder, "RAIL")
        marker = tk.Frame(holder, bg=theme.RAIL, width=2, height=20)
        marker.pack(side=tk.LEFT, fill=tk.Y)
        marker.pack_propagate(False)

        img = theme.rail_ico(icon, theme.RAIL_FG, theme.RAIL, 17)
        icon_label = ttk.Label(holder, image=img, background=theme.RAIL)
        icon_label.image = img
        icon_label.pack(side=tk.LEFT, padx=(10, 8), pady=6)
        text_label = tk.Label(holder, text=label, bg=theme.RAIL, fg=theme.RAIL_FG,
                              font=theme.font(10))
        text_label.pack(side=tk.LEFT, pady=6)
        self._reg_surface(text_label, "RAIL")
        self._reg_fg(text_label, "RAIL_FG")

        def activate(_event=None, k=key):
            self._show_page(k)

        for widget in (holder, marker, icon_label, text_label):
            widget.bind("<Button-1>", activate)
            widget.configure(cursor="hand2")

        return {"holder": holder, "marker": marker, "icon": icon_label,
                "text": text_label, "img": img, "name": icon}

    # ---- 右侧工作区 ----
    def _build_workbench(self, parent):
        area = tk.Frame(parent, bg=theme.BG)
        area.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._build_topbar(area)

        body = tk.Frame(area, bg=theme.BG)
        body.pack(fill=tk.BOTH, expand=True)
        self.page_host = body

    def _build_topbar(self, parent):
        """顶栏：页面主标题 + 副标题 + 统计芯片 + 轻量动作。"""
        top = tk.Frame(parent, bg=theme.TOPBAR_BG, height=78,
                       highlightbackground=theme.BORDER, highlightthickness=1)
        top.pack(fill=tk.X)
        top.pack_propagate(False)
        self._reg_surface(top, "TOPBAR_BG")

        text_box = tk.Frame(top, bg=theme.TOPBAR_BG)
        text_box.pack(side=tk.LEFT, padx=24, pady=14)
        self._reg_surface(text_box, "TOPBAR_BG")
        self._page_title = ttk.Label(text_box, text="任务布设", style="PageTitle.TLabel")
        self._page_title.pack(anchor="w")
        self._page_subtitle = ttk.Label(
            text_box, text="录入目标与筛选条件，落定即开跑",
            style="PageSub.TLabel")
        self._page_subtitle.pack(anchor="w")

        # 统计芯片
        chips = tk.Frame(top, bg=theme.TOPBAR_BG)
        chips.pack(side=tk.RIGHT, padx=(0, 20))
        self._reg_surface(chips, "TOPBAR_BG")
        self._chip_labels = {}
        for key, label in (("total", "命中链接"), ("https", "HTTPS"),
                           ("http", "HTTP"), ("dead", "失效")):
            chip = tk.Frame(chips, bg=theme.SURFACE_ALT,
                            highlightbackground=theme.BORDER, highlightthickness=1)
            chip.pack(side=tk.LEFT, padx=5)
            self._reg_surface(chip, "SURFACE_ALT")
            inner = tk.Frame(chip, bg=theme.SURFACE_ALT)
            inner.pack(padx=12, pady=6)
            self._reg_surface(inner, "SURFACE_ALT")
            tk.Label(inner, text=label, bg=theme.SURFACE_ALT, fg=theme.MUTED,
                     font=theme.font(9)).pack(anchor="e")
            val = tk.Label(inner, text="0", bg=theme.SURFACE_ALT,
                           fg=theme.ACCENT if key == "dead" else theme.PRIMARY,
                           font=theme.font(15, bold=True))
            val.pack(anchor="e")
            self._reg_surface(val, "SURFACE_ALT")
            self._reg_fg(val, "ACCENT" if key == "dead" else "PRIMARY")
            self._chip_labels[key] = val

        actions = tk.Frame(top, bg=theme.TOPBAR_BG)
        actions.pack(side=tk.RIGHT, padx=(0, 8))
        self._reg_surface(actions, "TOPBAR_BG")
        palette_btn = self._btn(actions, "配色", "spark", "Ghost.TButton",
                                self.toggle_theme)
        palette_btn.pack(side=tk.LEFT, padx=4)
        site = tk.Label(actions, text="官网 ↗", bg=theme.TOPBAR_BG,
                        fg=theme.PRIMARY, font=theme.font(10, bold=True),
                        cursor="hand2")
        site.pack(side=tk.LEFT, padx=10)
        self._reg_surface(site, "TOPBAR_BG")
        self._reg_fg(site, "PRIMARY")
        site.bind("<Button-1>", lambda e: webbrowser.open(APP_SITE))

    # =====================================================================
    # 页面
    # =====================================================================
    def _build_pages(self):
        """构建全部页面（一次性建好，通过 pack_forget / pack 切换）。"""
        for key in ("targets", "results", "logs", "settings"):
            frame = tk.Frame(self.page_host, bg=theme.BG)
            self._pages[key] = frame

        self._build_targets_page(self._pages["targets"])
        self._build_results_page(self._pages["results"])
        self._build_logs_page(self._pages["logs"])
        self._build_settings_page(self._pages["settings"])

    def _show_page(self, key):
        """切换当前页面，并同步顶栏标题与导航高亮。"""
        frame = self._pages.get(key)
        if frame is None:
            return
        for other in self._pages.values():
            other.pack_forget()
        frame.pack(fill=tk.BOTH, expand=True)

        titles = {
            "targets": ("任务布设", "录入目标与筛选条件，落定即开跑"),
            "results": ("结果清册", "排序、筛选、体检，落定后导出"),
            "logs": ("事件流水", "分级记录抓取事件、警告与异常"),
            "settings": ("参数配置", "配色方案、文件类型映射与抓取策略"),
        }
        title, subtitle = titles.get(key, ("", ""))
        self._page_title.configure(text=title)
        self._page_subtitle.configure(text=subtitle)

        for nav_key, parts in self._nav_buttons.items():
            self._paint_nav_item(nav_key, nav_key == key)

    def _paint_nav_item(self, key, active):
        """按激活态绘制单个导航项：2px 朱红左杠 + 加粗墨字 + 按激活底重绘图标。"""
        parts = self._nav_buttons.get(key)
        if parts is None:
            return
        icon = parts.get("name") or self._NAV_ICONS.get(key)
        try:
            parts["holder"].configure(bg=theme.RAIL_ACTIVE if active else theme.RAIL)
            parts["marker"].configure(bg=theme.ACCENT if active else theme.RAIL)
            parts["text"].configure(
                bg=theme.RAIL_ACTIVE if active else theme.RAIL,
                fg=theme.RAIL_ACTIVE_FG if active else theme.RAIL_FG,
                font=theme.font(10, bold=active))
            parts["icon"].configure(background=theme.RAIL_ACTIVE if active else theme.RAIL)
            # 激活底与导航底不同，图标需按当前底色重绘，避免留下旧底色的浅晕
            img = theme.rail_ico(icon, theme.RAIL_FG,
                                 theme.RAIL_ACTIVE if active else theme.RAIL, 17)
            parts["icon"].configure(image=img)
            parts["icon"].image = img
        except Exception:
            pass

    # ---- 页面一：任务布设 ----
    def _build_targets_page(self, page):
        scroll = tk.Frame(page, bg=theme.BG)
        scroll.pack(fill=tk.BOTH, expand=True)
        self._reg_surface(scroll, "BG")

        canvas = tk.Canvas(scroll, bg=theme.BG, highlightthickness=0)
        bar = ttk.Scrollbar(scroll, orient=tk.VERTICAL, style="App.Vertical.TScrollbar",
                             command=canvas.yview)
        canvas.configure(yscrollcommand=bar.set)
        bar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        inner = tk.Frame(canvas, bg=theme.BG)
        window = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>",
                   lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(window, width=e.width))

        def wheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", wheel))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))

        self._build_url_panel(inner)
        self._build_filter_panel(inner)
        self._build_control_panel(inner)

    def _build_url_panel(self, parent):
        body = self._panel(parent, "目标清单", "每行一条网址，# 开头为注释", "globe",
                           expand=False)

        self.url_text = None
        self.entry_url = None
        if self.config.get_bool("multi_url", "enabled", default=True):
            self._field_label(body, "网址清单", "每行一条")

            holder = tk.Frame(body, bg=theme.SURFACE)
            holder.pack(fill=tk.X)
            self._reg_surface(holder, "SURFACE")
            self.url_text = tk.Text(holder, width=100, height=5, font=theme.font(10, mono=True),
                                    wrap=tk.WORD, bd=1, relief="solid", bg=theme.SURFACE_SUNK,
                                    fg=theme.INK, insertbackground=theme.INK,
                                    highlightbackground=theme.BORDER,
                                    highlightthickness=1, highlightcolor=theme.BORDER_STRONG)
            self.url_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            scroll = ttk.Scrollbar(holder, orient=tk.VERTICAL,
                                   style="App.Vertical.TScrollbar",
                                   command=self.url_text.yview)
            scroll.pack(side=tk.RIGHT, fill=tk.Y)
            self.url_text.config(yscrollcommand=scroll.set)

            row = tk.Frame(body, bg=theme.SURFACE)
            row.pack(fill=tk.X, pady=(10, 0))
            self._reg_surface(row, "SURFACE")
            self._btn(row, "导入清单", "download", "Secondary.TButton",
                      self.import_urls).pack(side=tk.LEFT, padx=(0, 8))
            self._btn(row, "导出清单", "upload", "Secondary.TButton",
                      self.export_urls).pack(side=tk.LEFT, padx=(0, 8))
            self._btn(row, "校验地址", "check", "Ghost.TButton",
                      self.validate_urls).pack(side=tk.LEFT)
        else:
            row = tk.Frame(body, bg=theme.SURFACE)
            row.pack(fill=tk.X)
            self._reg_surface(row, "SURFACE")
            ttk.Label(row, text="网页地址", style="Section.TLabel").pack(side=tk.LEFT, padx=(0, 8))
            self.entry_url = ttk.Entry(row, style="App.TEntry", font=theme.font(10))
            self.entry_url.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # 元素区域限定
        tk.Frame(body, bg=theme.DIVIDER, height=1).pack(fill=tk.X, pady=(14, 12))

        self._field_label(body, "范围限定", "仅抓取指定元素内的链接")
        row = tk.Frame(body, bg=theme.SURFACE)
        row.pack(fill=tk.X)
        self._reg_surface(row, "SURFACE")
        preview_text = "网页预览选元素" if PYQT_WEB else "网页预览选元素（降级）"
        self._btn(row, preview_text, "target", "InfoOutline.TButton",
                  self.preview_page).pack(side=tk.LEFT, padx=(0, 8))
        self._btn(row, "手动填写 CSS 选择器", "rules", "Primary.TButton",
                  self.get_element_selector).pack(side=tk.LEFT, padx=(0, 12))
        self.current_selector_var = tk.StringVar(value=self._selector_text())
        ttk.Label(row, textvariable=self.current_selector_var,
                  style="Muted.TLabel").pack(side=tk.LEFT)

    def _build_filter_panel(self, parent):
        body = self._panel(parent, "筛选规则", "按类型、协议与关键词收敛结果", "filter",
                           expand=False)

        mode = tk.Frame(body, bg=theme.SURFACE)
        mode.pack(fill=tk.X, pady=(0, 10))
        self._reg_surface(mode, "SURFACE")
        self.filter_mode = tk.StringVar(value="single")
        ttk.Radiobutton(mode, text="单选模式", style="App.TRadiobutton",
                        variable=self.filter_mode, value="single",
                        command=self._update_filter_mode).pack(side=tk.LEFT, padx=(0, 20))
        ttk.Radiobutton(mode, text="多选模式", style="App.TRadiobutton",
                        variable=self.filter_mode, value="multiple",
                        command=self._update_filter_mode).pack(side=tk.LEFT)

        self.single_filter_frame = tk.Frame(body, bg=theme.SURFACE)
        self.single_filter_frame.pack(fill=tk.X)
        self._reg_surface(self.single_filter_frame, "SURFACE")
        self.filter_combobox = ttk.Combobox(self.single_filter_frame, style="App.TCombobox",
                                            values=self.config.filter_options(),
                                            state="readonly", width=20,
                                            font=theme.font(10))
        self.filter_combobox.set("所有链接")
        self.filter_combobox.pack(side=tk.LEFT)

        self.multiple_filter_frame = tk.Frame(body, bg=theme.SURFACE)
        self._reg_surface(self.multiple_filter_frame, "SURFACE")
        self._build_checkboxes()

        tk.Frame(body, bg=theme.DIVIDER, height=1).pack(fill=tk.X, pady=(12, 12))

        self._field_label(body, "关键词", "子串匹配，或勾选正则表达式")
        kw = tk.Frame(body, bg=theme.SURFACE)
        kw.pack(fill=tk.X)
        self._reg_surface(kw, "SURFACE")
        self.keyword_entry = ttk.Entry(kw, style="App.TEntry", font=theme.font(10))
        self.keyword_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.keyword_regex = tk.BooleanVar(value=False)
        ttk.Checkbutton(kw, text="正则表达式", style="App.TCheckbutton",
                        variable=self.keyword_regex).pack(side=tk.LEFT, padx=10)

    def _update_filter_mode(self):
        """按单选/多选模式切换筛选控件的显示。"""
        if self.filter_mode.get() == "single":
            self.multiple_filter_frame.pack_forget()
            self.single_filter_frame.pack(fill=tk.X)
        else:
            self.single_filter_frame.pack_forget()
            self.multiple_filter_frame.pack(fill=tk.X)

    def _build_checkboxes(self):
        """重建文件类型多选复选框（文件类型映射变更后需重新生成）。"""
        for widget in self.multiple_filter_frame.winfo_children():
            widget.destroy()
        self.selected_file_types = {cat: tk.BooleanVar(value=False)
                                    for cat in self.config.file_type_mapping.keys()}
        grid = tk.Frame(self.multiple_filter_frame, bg=theme.SURFACE)
        grid.pack(fill=tk.X)
        cats = list(self.config.file_type_mapping.keys())
        mid = (len(cats) + 1) // 2
        col_a = tk.Frame(grid, bg=theme.SURFACE)
        col_a.pack(side=tk.LEFT, fill=tk.X, expand=True)
        col_b = tk.Frame(grid, bg=theme.SURFACE)
        col_b.pack(side=tk.LEFT, fill=tk.X, expand=True)
        for index, cat in enumerate(cats):
            host = col_a if index < mid else col_b
            ttk.Checkbutton(host, text=cat, style="App.TCheckbutton",
                            variable=self.selected_file_types[cat]).pack(anchor="w", pady=2)
        ctrl = tk.Frame(self.multiple_filter_frame, bg=theme.SURFACE)
        ctrl.pack(fill=tk.X, pady=(8, 0))
        self._reg_surface(ctrl, "SURFACE")
        self._btn(ctrl, "全选", "check", "Secondary.TButton",
                  lambda: [v.set(True) for v in self.selected_file_types.values()]
                  ).pack(side=tk.LEFT, padx=(0, 8))
        self._btn(ctrl, "取消全选", "close", "Secondary.TButton",
                  lambda: [v.set(False) for v in self.selected_file_types.values()]
                  ).pack(side=tk.LEFT)

    def _build_control_panel(self, parent):
        body = self._panel(parent, "执行控制", "启动、暂停、续爬与结果体检", "pulse",
                           expand=False)

        row = tk.Frame(body, bg=theme.SURFACE)
        row.pack(fill=tk.X)
        self._reg_surface(row, "SURFACE")
        self.btn_start = self._btn(row, "开始抓取", "play", "Accent.TButton",
                                   self.start_scraping)
        self.btn_start.pack(side=tk.LEFT, padx=(0, 8))
        self.btn_pause = self._btn(row, "暂停", "pause", "Warning.TButton",
                                   self.toggle_pause)
        self.btn_pause.pack(side=tk.LEFT, padx=(0, 8))
        self.btn_stop = self._btn(row, "停止", "stop", "Danger.TButton",
                                  self.stop_crawling)
        self.btn_stop.pack(side=tk.LEFT, padx=(0, 8))
        self.btn_resume = self._btn(row, "断点续爬", "refresh", "Secondary.TButton",
                                    self.resume_crawl)
        self.btn_resume.pack(side=tk.LEFT, padx=(0, 8))

        row2 = tk.Frame(body, bg=theme.SURFACE)
        row2.pack(fill=tk.X, pady=(10, 0))
        self._reg_surface(row2, "SURFACE")
        self._btn(row2, "应用筛选", "filter", "Primary.TButton",
                  self.apply_filter).pack(side=tk.LEFT, padx=(0, 8))
        self.btn_check = self._btn(row2, "链接体检", "shield", "Info.TButton",
                                   self.check_links_ui)
        self.btn_check.pack(side=tk.LEFT, padx=(0, 8))
        self._btn(row2, "导出结果", "save", "Secondary.TButton",
                  self.export_dialog).pack(side=tk.LEFT, padx=(0, 8))
        self._btn(row2, "清空工作区", "trash", "DangerOutline.TButton",
                  self.clear_all).pack(side=tk.LEFT)

        pf = tk.Frame(body, bg=theme.SURFACE)
        pf.pack(fill=tk.X, pady=(16, 0))
        self._reg_surface(pf, "SURFACE")
        self.progress = ttk.Progressbar(pf, style="App.Horizontal.TProgressbar",
                                         mode="determinate", maximum=100)
        self.progress.pack(fill=tk.X)
        self.progress_label = ttk.Label(pf, text="就绪 · 等待开始", style="Muted.TLabel")
        self.progress_label.pack(anchor="w", pady=(6, 0))

    # ---- 页面二：结果清册 ----
    def _build_results_page(self, page):
        body = self._panel(page, "链接清册", "点表头排序，体检后显示存活状态",
                           "table")

        self.notebook = ttk.Notebook(body, style="App.TNotebook")
        self.notebook.pack(fill=tk.BOTH, expand=True)

        tbl_tab = tk.Frame(self.notebook, bg=theme.SURFACE)
        self.notebook.add(tbl_tab, text="  表格视图  ")
        cols = ("#", "链接", "类型", "协议", "深度", "状态")
        self.tree = ttk.Treeview(tbl_tab, columns=cols, show="headings",
                                 style="App.Treeview", height=18)
        widths = {"#": 52, "链接": 760, "类型": 120, "协议": 76,
                  "深度": 66, "状态": 96}
        for col in cols:
            self.tree.heading(col, text=col, command=lambda c=col: self._sort_by(c))
            self.tree.column(col, width=widths[col], anchor="w",
                             stretch=(col == "链接"))
        vsb = ttk.Scrollbar(tbl_tab, orient=tk.VERTICAL, style="App.Vertical.TScrollbar",
                            command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        for tag, color in (("ok", theme.SUCCESS), ("dead", theme.DANGER),
                           ("redirect", theme.INFO), ("blocked", theme.WARNING),
                           ("error", theme.MUTED), ("unknown", theme.MUTED_LIGHT)):
            self.tree.tag_configure(tag, foreground=color)

        txt_tab = tk.Frame(self.notebook, bg=theme.SURFACE)
        self.notebook.add(txt_tab, text="  文本视图  ")
        self.text_scroll = ttk.Scrollbar(txt_tab, orient=tk.VERTICAL,
                                          style="App.Vertical.TScrollbar")
        self.text_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.result_text = tk.Text(txt_tab, font=theme.font(10, mono=True),
                                   wrap=tk.WORD, bd=0, bg=theme.SURFACE,
                                   fg=theme.INK, insertbackground=theme.INK,
                                   yscrollcommand=self.text_scroll.set)
        self.result_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.text_scroll.config(command=self.result_text.yview)

        row = tk.Frame(body, bg=theme.SURFACE)
        row.pack(fill=tk.X, pady=(12, 0))
        self._reg_surface(row, "SURFACE")
        self._btn(row, "复制筛选结果", "copy", "InfoOutline.TButton",
                  self.copy_filtered).pack(side=tk.LEFT, padx=(0, 8))
        self._btn(row, "复制全部结果", "copy", "Secondary.TButton",
                  self.copy_all).pack(side=tk.LEFT)
        self._result_summary = ttk.Label(row, text="", style="Muted.TLabel")
        self._result_summary.pack(side=tk.RIGHT)

    # ---- 页面三：事件流水 ----
    def _build_logs_page(self, page):
        body = self._panel(page, "流水记录", "info / warn / error / ok 四级着色", "list")
        self.log_text = tk.Text(body, height=22, font=theme.font(9, mono=True),
                                wrap=tk.WORD, bd=1, relief="solid",
                                bg=theme.CODE_BG, fg=theme.INK,
                                insertbackground=theme.INK,
                                highlightbackground=theme.BORDER,
                                highlightthickness=1)
        self.log_text.pack(fill=tk.BOTH, expand=True)
        self.log_text.tag_configure("info", foreground=theme.INK)
        self.log_text.tag_configure("warn", foreground=theme.WARNING)
        self.log_text.tag_configure("error", foreground=theme.DANGER)
        self.log_text.tag_configure("ok", foreground=theme.SUCCESS)
        self.log_text.configure(state=tk.DISABLED)

    # ---- 页面四：参数配置 ----
    def _build_settings_page(self, page):
        scroll = tk.Frame(page, bg=theme.BG)
        scroll.pack(fill=tk.BOTH, expand=True)
        self._reg_surface(scroll, "BG")
        canvas = tk.Canvas(scroll, bg=theme.BG, highlightthickness=0)
        bar = ttk.Scrollbar(scroll, orient=tk.VERTICAL, style="App.Vertical.TScrollbar",
                             command=canvas.yview)
        canvas.configure(yscrollcommand=bar.set)
        bar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        inner = tk.Frame(canvas, bg=theme.BG)
        window = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>",
                   lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(window, width=e.width))

        def wheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", wheel))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))

        # 配色方案
        body = self._panel(inner, "纸墨配色", "三套浅色方案，循环切换", "spark",
                           expand=False)
        row = tk.Frame(body, bg=theme.SURFACE)
        row.pack(fill=tk.X)
        self._reg_surface(row, "SURFACE")
        self._palette_buttons = {}
        for name in theme.palette_names():
            btn = self._btn(row, name, "layers", "Secondary.TButton",
                            lambda n=name: self._apply_palette(n))
            btn.pack(side=tk.LEFT, padx=(0, 8))
            self._palette_buttons[name] = btn
        self._palette_hint = ttk.Label(
            body, text=f"当前配色方案：{theme.CURRENT_PALETTE}", style="Muted.TLabel")
        self._palette_hint.pack(anchor="w", pady=(10, 0))

        # 抓取策略
        body = self._panel(inner, "策略参数", "深度、并发、排除与网络边界", "rules",
                           expand=False)
        self._field_label(body, "增强功能配置", "深度 / 并发 / 页数上限 / 排除规则 / robots / 代理")
        row = tk.Frame(body, bg=theme.SURFACE)
        row.pack(fill=tk.X)
        self._reg_surface(row, "SURFACE")
        self._btn(row, "打开增强功能配置", "settings", "Primary.TButton",
                  self.configure_enhanced).pack(side=tk.LEFT, padx=(0, 8))
        self._btn(row, "编辑文件类型映射", "grid", "Secondary.TButton",
                  self.edit_file_types).pack(side=tk.LEFT)

        # 运行环境
        body = self._panel(inner, "环境信息", "版本、依赖与数据落点", "compass",
                           expand=False)
        info = tk.Frame(body, bg=theme.SURFACE)
        info.pack(fill=tk.X)
        self._reg_surface(info, "SURFACE")
        rows = (
            ("应用版本", f"WebLinkCrawler v{APP_VERSION}"),
            ("Python 版本", sys.version.split()[0]),
            ("网页预览能力", "PyQt5 + QtWebEngine 可用" if PYQT_WEB
             else "未安装 PyQt5/QtWebEngine，使用内置降级预览"),
            ("配置文件", os.path.abspath(self.config.enhanced_config_file)),
            ("数据库文件", os.path.abspath(self.db.db_file)),
        )
        for label, value in rows:
            line = tk.Frame(info, bg=theme.SURFACE)
            line.pack(fill=tk.X, pady=2)
            self._reg_surface(line, "SURFACE")
            ttk.Label(line, text=label, style="Section.TLabel").pack(side=tk.LEFT)
            ttk.Label(line, text=value, style="Muted.TLabel").pack(side=tk.LEFT, padx=(12, 0))

        row = tk.Frame(body, bg=theme.SURFACE)
        row.pack(fill=tk.X, pady=(14, 0))
        self._reg_surface(row, "SURFACE")
        self._btn(row, "使用说明", "doc", "Secondary.TButton",
                  self._show_help).pack(side=tk.LEFT, padx=(0, 8))
        self._btn(row, "关于本工具", "info", "Secondary.TButton",
                  self.show_about).pack(side=tk.LEFT)

    # =====================================================================
    # 逻辑
    # =====================================================================
    def _selector_text(self):
        """当前 CSS 选择器的展示文案。"""
        return f"当前选择器：{self.config.css_selector or '整个页面'}"

    def _get_input_urls(self):
        """读取界面上的目标网址（多行或单行两种模式）。"""
        if self.url_text is not None:
            content = self.url_text.get(1.0, tk.END).strip()
            if not content:
                return []
            urls = []
            for line in content.split("\n"):
                line = line.strip()
                if line and not line.startswith("#"):
                    urls.append(normalize_url(line))
            return urls
        elif self.entry_url is not None:
            value = self.entry_url.get().strip()
            return [normalize_url(value)] if value else []
        return []

    # ---- 抓取控制 ----
    def start_scraping(self):
        """校验输入并启动抓取线程。"""
        if self.is_crawling:
            messagebox.showinfo("提示", "已有抓取任务正在进行中。")
            return
        urls = self._get_input_urls()
        if not urls:
            messagebox.showerror("错误", "请输入要抓取的网页 URL。")
            return
        bad = [u for u in urls if not is_valid_url(u)]
        if bad and self.config.get_bool("multi_url", "url_validation", default=True):
            if not messagebox.askyesno("URL 校验", f"有 {len(bad)} 个 URL 格式可疑，仍要继续？"):
                return

        self.all_records = []
        self.filtered_records = []
        self.link_states = {}
        self._refresh_results()
        self._log("info", f"开始抓取 {len(urls)} 个目标，深度 {self.config.max_depth}，"
                          f"并发 {self.config.concurrency}，上限 {self.config.max_pages} 页")
        self.is_crawling = True
        self._resume_mode = False
        self._paused = False
        self.btn_pause.configure(text="暂停")
        self._set_crawl_controls(True)
        self.progress.configure(mode="indeterminate")
        self.progress.start(12)
        self.progress_label.configure(text="抓取中…")

        self.engine.reset()
        threading.Thread(target=self._crawl_worker, args=(urls,), daemon=True).start()

    def _crawl_worker(self, urls):
        """后台抓取线程；异常一律转为日志事件，不向 GUI 抛出。"""
        try:
            self.engine.crawl(urls, on_event=self._emit_event)
        except Exception as exc:
            log.exception("抓取线程异常")
            self._emit_event("log", "error", f"抓取过程发生错误: {exc}")
            self._emit_event("done", [])

    def toggle_pause(self):
        """暂停 / 恢复抓取。"""
        if not self.is_crawling:
            return
        if self._paused:
            self.engine.resume()
            self._paused = False
            self.btn_pause.configure(text="暂停")
            self._log("info", "已恢复抓取。")
        else:
            self.engine.pause()
            self._paused = True
            self.btn_pause.configure(text="恢复")
            self._log("warn", "已暂停抓取。")

    def stop_crawling(self):
        """请求停止抓取。"""
        if not self.is_crawling:
            return
        self.engine.stop()
        self._paused = False
        self._log("warn", "正在停止抓取…")

    def resume_crawl(self):
        """从数据库恢复未完成的抓取任务。"""
        if self.is_crawling:
            messagebox.showinfo("提示", "已有抓取任务正在进行中。")
            return
        self._resume_mode = True
        self.is_crawling = True
        self._paused = False
        self.btn_pause.configure(text="暂停")
        self._set_crawl_controls(True)
        self.progress.configure(mode="indeterminate")
        self.progress.start(12)
        self.progress_label.configure(text="恢复中…")
        self._log("info", "正在恢复未完成的抓取任务…")
        threading.Thread(target=self._resume_worker, daemon=True).start()

    def _resume_worker(self):
        """后台续爬；resume_pending 无任务时不会发 done，这里补齐。"""
        seen_done = {"done": False}

        def on_event(kind, *args):
            if kind == "done":
                seen_done["done"] = True
            self._emit_event(kind, *args)

        try:
            self.engine.resume_pending(on_event=on_event)
        except Exception as exc:
            log.exception("断点续爬线程异常")
            self._emit_event("log", "error", f"断点续爬发生错误: {exc}")
        if not seen_done["done"]:
            self._emit_event("done", [])

    # ---- 链接体检 ----
    def check_links_ui(self):
        """对当前筛选结果发起并发 HEAD 体检。"""
        if self.is_checking:
            return
        links = [r["link"] for r in (self.filtered_records or self.all_records)]
        if not links:
            messagebox.showwarning("警告", "没有可体检的链接，请先抓取。")
            return
        self.is_checking = True
        self.btn_check.configure(state=tk.DISABLED)
        self.progress.configure(mode="determinate", maximum=len(links), value=0)
        self.progress_label.configure(text=f"体检中 0/{len(links)}")
        self._log("info", f"开始链接体检，共 {len(links)} 个链接")
        threading.Thread(target=self._check_worker, args=(links,), daemon=True).start()

    def _check_worker(self, links):
        """后台体检线程。"""
        try:
            self.engine.check_links(links, on_event=self._emit_event)
        except Exception as exc:
            log.exception("体检线程异常")
            self._emit_event("log", "error", f"体检发生错误: {exc}")
            self._emit_event("check_done", {})

    # ---- 事件（线程安全）----
    def _emit_event(self, kind, *args):
        """把后台事件放入队列，由主线程统一消费。"""
        self.events.put((kind, args))

    def _poll_events(self):
        """主线程事件泵：每 60ms 排空队列。

        单个事件处理异常必须隔离（F-08）：旧实现只捕获 queue.Empty，
        任一事件抛错都会丢弃本 tick 剩余事件并打破 60ms 续跳。
        """
        try:
            while True:
                kind, args = self.events.get_nowait()
                try:
                    self._handle_event(kind, args)
                except Exception:
                    log.exception("事件处理异常（已跳过该事件）: %s", kind)
        except queue.Empty:
            pass
        finally:
            self.root.after(60, self._poll_events)

    def _handle_event(self, kind, args):
        """把事件分发到对应的界面更新逻辑。"""
        if kind == "log":
            level, msg = args
            self._log(level, msg)
        elif kind == "page":
            url, count, depth = args
            self.progress_label.configure(text=f"已抓取页面：{url}  →  {count} 个链接")
        elif kind == "progress":
            done, total = args
            if self.is_checking:
                self.progress.configure(value=done)
                self.progress_label.configure(text=f"体检中 {done}/{total}")
        elif kind == "done":
            records = args[0] if args else []
            self._on_crawl_done(records)
        elif kind == "check_done":
            results = args[0] if args else {}
            self._on_check_done(results)

    def _on_crawl_done(self, records):
        """抓取结束：刷新结果区与控件状态。"""
        was_resume = self._resume_mode
        self._resume_mode = False
        self.is_crawling = False
        self._paused = False
        self.btn_pause.configure(text="暂停")
        self._set_crawl_controls(False)
        self.progress.stop()
        self.progress.configure(mode="determinate", value=0)
        self.progress_label.configure(text="就绪 · 等待开始")

        new_records = [self._enrich(r) for r in (records or [])]
        if was_resume and not new_records:
            self._log("info", "没有可恢复的抓取结果，已保留现有结果。")
            return

        self.all_records = new_records
        self.filtered_records = list(self.all_records)
        self._refresh_results()
        self._log("ok", f"抓取完成：共 {len(self.all_records)} 个链接（已去重）。")
        self.apply_filter()

    def _on_check_done(self, results):
        """体检结束：回写状态、刷新表格与统计。"""
        self.is_checking = False
        self.btn_check.configure(state=tk.NORMAL)
        self.progress.configure(value=0)
        self.progress_label.configure(text="就绪 · 等待开始")
        self.link_states = results or {}
        for record in self.all_records:
            record["state"] = self.link_states.get(record["link"], ("", None))[0]
        self._refresh_results()
        summary = {}
        for state, _code in self.link_states.values():
            summary[state] = summary.get(state, 0) + 1
        brief = "，".join(f"{_STATE_TEXT.get(k, k)} {v}" for k, v in summary.items())
        self._log("ok", f"链接体检完成：{brief or '无结果'}")

    def _enrich(self, record):
        """为原始记录补齐文件类型、协议与体检状态。"""
        link = record["link"]
        protocol = ""
        for prefix, name in (("https://", "https"), ("http://", "http"),
                             ("ftp://", "ftp"), ("sftp://", "sftp")):
            if link.startswith(prefix):
                protocol = name
                break
        return {
            "link": link,
            "file_type": self.config.file_type_of(link),
            "protocol": protocol,
            "depth": record.get("depth", ""),
            "state": self.link_states.get(link, ("", None))[0],
        }

    def _set_crawl_controls(self, crawling):
        """抓取期间禁用/恢复相关按钮。"""
        state = tk.DISABLED if crawling else tk.NORMAL
        self.btn_start.configure(state=state)
        self.btn_stop.configure(state=tk.NORMAL if crawling else tk.DISABLED)
        self.btn_pause.configure(state=tk.NORMAL if crawling else tk.DISABLED)
        if getattr(self, "btn_resume", None) is not None:
            self.btn_resume.configure(state=state)

    def _log(self, level, msg):
        """写入界面日志并同步到文件日志。"""
        ts = datetime.now().strftime("%H:%M:%S")
        tag = level if level in ("info", "warn", "error", "ok") else "info"
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"[{ts}] {msg}\n", tag)
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)
        getattr(log, level if level in ("info", "warn", "error") else "info")(msg)

    # ---- 筛选 ----
    def apply_filter(self):
        """按当前筛选条件收敛结果集。"""
        if not self.all_records:
            messagebox.showwarning("警告", "请先抓取链接。")
            return
        keyword = self.keyword_entry.get().strip()
        use_regex = self.keyword_regex.get()
        mapping = self.config.file_type_mapping

        if self.filter_mode.get() == "single":
            ft = self.filter_combobox.get()
            if ft == "所有链接":
                base = list(self.all_records)
            elif ft == "HTTPS链接":
                base = [r for r in self.all_records if r["protocol"] == "https"]
            elif ft == "HTTP链接":
                base = [r for r in self.all_records if r["protocol"] == "http"]
            elif ft in mapping:
                base = [r for r in self.all_records if r["file_type"] == ft]
            else:
                base = list(self.all_records)
        else:
            cats = [c for c, v in self.selected_file_types.items() if v.get()]
            base = [r for r in self.all_records if r["file_type"] in cats] \
                if cats else list(self.all_records)

        if keyword:
            if use_regex:
                if len(keyword) > 256:
                    messagebox.showerror("正则过长", "关键词正则长度不能超过 256 个字符。")
                    return
                try:
                    pattern = re.compile(keyword, re.IGNORECASE)
                except re.error as exc:
                    messagebox.showerror("正则错误", f"关键词正则无效: {exc}")
                    return
                base = [r for r in base if pattern.search(r["link"])]
            else:
                low = keyword.lower()
                base = [r for r in base if low in r["link"].lower()]

        self.filtered_records = base
        self._refresh_results()

    def _sort_by(self, col):
        """按表头排序（再次点击同一列切换升/降序）。"""
        keymap = {"链接": "link", "类型": "file_type", "协议": "protocol",
                  "深度": "depth", "状态": "state", "#": "link"}
        key = keymap.get(col, "link")
        if self._sort_col == col:
            self._sort_rev = not self._sort_rev
        else:
            self._sort_col = col
            self._sort_rev = False
        self.filtered_records.sort(
            key=lambda r: (str(r.get(key, "")), r["link"]), reverse=self._sort_rev)
        self._refresh_results()

    def _refresh_results(self):
        """重绘表格、文本视图与统计芯片。"""
        for item in self.tree.get_children():
            self.tree.delete(item)
        for index, record in enumerate(self.filtered_records, 1):
            state_txt = _STATE_TEXT.get(record.get("state", ""), "未检")
            depth = record.get("depth", "")
            self.tree.insert("", tk.END, values=(
                index, record["link"], record["file_type"] or "—",
                record["protocol"] or "—", depth if depth != "" else "—",
                state_txt),
                tags=(_STATE_TAG.get(record.get("state", ""), "unknown"),))

        self.result_text.delete(1.0, tk.END)
        if self.filtered_records:
            self.result_text.insert(tk.END, f"找到 {len(self.filtered_records)} 个匹配的链接：\n")
            self.result_text.insert(tk.END, "=" * 50 + "\n")
            for index, record in enumerate(self.filtered_records, 1):
                self.result_text.insert(tk.END, f"{index:3d}. {record['link']}\n")
        else:
            self.result_text.insert(tk.END, "没有找到匹配的链接。\n")
        self._update_stats()

    def _update_stats(self):
        """刷新顶栏统计芯片与结果摘要。"""
        records = self.filtered_records or []
        https = sum(1 for r in records if r["protocol"] == "https")
        http = sum(1 for r in records if r["protocol"] == "http")
        dead = sum(1 for r in records if r.get("state") == "dead")
        self._chip_labels["total"].configure(text=str(len(records)))
        self._chip_labels["https"].configure(text=str(https))
        self._chip_labels["http"].configure(text=str(http))
        self._chip_labels["dead"].configure(text=str(dead))
        self._result_summary.configure(
            text=f"筛选 {len(records)} / 全部 {len(self.all_records)} 个链接")

    # ---- 复制 / 清除 ----
    def copy_filtered(self):
        """复制筛选后的链接。"""
        self._copy([r["link"] for r in self.filtered_records], "筛选")

    def copy_all(self):
        """复制全部链接。"""
        self._copy([r["link"] for r in self.all_records], "全部")

    def _copy(self, links, label):
        """写入系统剪贴板。"""
        if not links:
            messagebox.showwarning("警告", "没有可复制的链接。")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append("\n".join(links))
        self.root.update()
        messagebox.showinfo("复制成功", f"已复制 {len(links)} 个{label}链接到剪贴板。")

    def clear_all(self):
        """清空结果区与输入区。"""
        self.all_records = []
        self.filtered_records = []
        self.link_states = {}
        if self.url_text is not None:
            self.url_text.delete(1.0, tk.END)
        elif self.entry_url is not None:
            self.entry_url.delete(0, tk.END)
        self.keyword_entry.delete(0, tk.END)
        self.filter_combobox.set("所有链接")
        self.result_text.delete(1.0, tk.END)
        for item in self.tree.get_children():
            self.tree.delete(item)
        self._update_stats()
        self._log("info", "已清除所有内容。")

    # ---- 导出 ----
    def save_links(self):
        """菜单入口：保存链接到文件。"""
        self.export_dialog()

    def export_dialog(self):
        """选择导出格式与路径并写出结果。"""
        if not self.filtered_records:
            messagebox.showwarning("警告", "没有可导出的链接。")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("文本文件", "*.txt"), ("CSV 表格", "*.csv"),
                       ("JSON 数据", "*.json"), ("所有文件", "*.*")],
            initialfile=f"links_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
        )
        if not path:
            return
        ext = os.path.splitext(path)[1].lower().lstrip(".")
        fmt = ext if ext in ("txt", "csv", "json") else "txt"
        meta = self._export_meta()
        try:
            self.engine.export(self.filtered_records, path, fmt, meta)
            messagebox.showinfo("导出成功",
                                 f"已导出 {len(self.filtered_records)} 个链接到:\n{path}")
            self._log("ok", f"已导出到 {path}（{fmt.upper()}）")
        except Exception as exc:
            log.exception("导出失败")
            messagebox.showerror("导出失败", f"导出时出错: {exc}")

    def _export_meta(self):
        """构造导出元信息。"""
        if self.url_text is not None:
            raw = self.url_text.get(1.0, tk.END).strip()
            source = raw.split("\n")[0] if raw else ""
        elif self.entry_url is not None:
            source = self.entry_url.get().strip()
        else:
            source = ""
        ft = "多选" if self.filter_mode.get() == "multiple" else self.filter_combobox.get()
        return {
            "source": source,
            "crawl_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "filter_type": ft,
            "keyword": self.keyword_entry.get().strip(),
            "css_selector": self.config.css_selector,
        }

    # ---- URL 导入 / 导出 / 验证 ----
    def import_urls(self):
        """从文本文件导入 URL 清单（自动识别 UTF-8 / GBK 等常见编码）。"""
        path = filedialog.askopenfilename(title="选择 URL 列表文件",
                                          filetypes=[("文本/CSV", "*.txt *.csv"),
                                                     ("所有文件", "*.*")])
        if not path:
            return
        try:
            content = self._read_text_auto(path)
            urls = [line.strip() for line in content.splitlines()
                    if line.strip() and not line.strip().startswith("#")]
            uniq = list(dict.fromkeys(urls))
            self.url_text.delete(1.0, tk.END)
            for url in uniq:
                self.url_text.insert(tk.END, url + "\n")
            messagebox.showinfo("导入成功",
                                f"导入 {len(uniq)} 个 URL（原始 {len(urls)} 个）。")
        except Exception as exc:
            messagebox.showerror("导入失败", f"导入 URL 出错: {exc}")

    @staticmethod
    def _read_text_auto(path):
        """按常见编码依次尝试解码，避免 GBK 清单因 UTF-8 解码失败而无法导入。"""
        with open(path, "rb") as handle:
            raw = handle.read()
        for encoding in ("utf-8-sig", "utf-8", "gb18030", "gbk", "big5",
                         "latin-1"):
            try:
                return raw.decode(encoding)
            except (UnicodeDecodeError, LookupError):
                continue
        return raw.decode("utf-8", errors="replace")

    def export_urls(self):
        """导出当前 URL 清单到文本文件。"""
        content = self.url_text.get(1.0, tk.END).strip()
        if not content:
            messagebox.showwarning("警告", "没有 URL 可导出。")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("文本", "*.txt"), ("CSV", "*.csv")],
            initialfile=f"urls_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
        if not path:
            return
        try:
            urls = [line.strip() for line in content.split("\n") if line.strip()]
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(f"URL 列表导出\n导出时间: "
                             f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                handle.write(f"URL 数量: {len(urls)}\n" + "=" * 50 + "\n\n")
                handle.write("\n".join(urls) + "\n")
            messagebox.showinfo("导出成功", f"URL 列表已保存到:\n{path}")
        except Exception as exc:
            messagebox.showerror("导出失败", f"导出 URL 出错: {exc}")

    def validate_urls(self):
        """校验 URL 清单并可选剔除无效项。"""
        content = self.url_text.get(1.0, tk.END).strip()
        if not content:
            messagebox.showwarning("警告", "没有 URL 可验证。")
            return
        raw = [line.strip() for line in content.split("\n") if line.strip()]
        valid = [u for u in raw if is_valid_url(normalize_url(u))]
        invalid = [u for u in raw if not is_valid_url(normalize_url(u))]
        msg = (f"总 URL 数: {len(raw)}\n有效: {len(valid)}\n无效: {len(invalid)}\n\n"
               f"无效列表(前10):\n" + ("\n".join(invalid[:10]) or "（无）")
               + ("…" if len(invalid) > 10 else ""))
        messagebox.showinfo("URL 验证", msg)
        if invalid and messagebox.askyesno("过滤无效 URL", "是否只保留有效 URL？"):
            self.url_text.delete(1.0, tk.END)
            for url in valid:
                self.url_text.insert(tk.END, url + "\n")
            messagebox.showinfo("过滤完成", f"已保留 {len(valid)} 个有效 URL。")

    # ---- 元素选择 ----
    def preview_page(self):
        """打开网页预览以点选元素。"""
        urls = self._get_input_urls()
        if not urls:
            messagebox.showwarning("警告", "请先输入 URL。")
            return
        url = urls[0]
        if self._start_preview_process(url):
            return
        self._fallback_preview(url)

    @staticmethod
    def _project_root():
        """项目根目录（预览子进程的工作目录）。"""
        try:
            here = os.path.dirname(os.path.abspath(__file__))
            return os.path.dirname(os.path.dirname(here))
        except Exception:
            return os.getcwd()

    @staticmethod
    def _safe_remove(path):
        """尽力删除临时文件，失败不抛异常。"""
        try:
            if path and os.path.exists(path):
                os.remove(path)
        except OSError:
            pass

    def _start_preview_process(self, url):
        """启动独立预览子进程；成功返回 True（结果由轮询读取）。"""
        if self._preview_proc is not None:
            messagebox.showinfo("提示", "网页预览窗口已在运行，请先完成或关闭它。")
            return True
        if getattr(sys, "frozen", False):
            log.info("打包运行环境不启动独立预览进程，改用降级预览。")
            return False
        script = _PREVIEW_SCRIPT
        if not os.path.isfile(script):
            log.warning("未找到网页预览脚本: %s", script)
            return False
        result_path = None
        try:
            fd, result_path = tempfile.mkstemp(prefix="wlc_preview_", suffix=".json")
            os.close(fd)
            proc = subprocess.Popen(
                [sys.executable, script, "--url", url, "--result", result_path],
                cwd=self._project_root(),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        except Exception as exc:
            log.warning("启动网页预览进程失败: %s", exc)
            self._safe_remove(result_path)
            return False
        self._preview_proc = proc
        self._preview_result_path = result_path
        self._preview_seq += 1
        seq = self._preview_seq
        self._log("info", "正在启动网页预览窗口…")
        self.root.after(_PREVIEW_POLL_MS,
                        lambda: self._poll_preview(result_path, url, 0, seq))
        return True

    def _poll_preview(self, result_path, url, attempt, seq):
        """轮询预览子进程结果文件。"""
        if seq != self._preview_seq:
            return
        data = self._read_preview_result(result_path)
        if data is not None:
            self._finish_preview(seq)
            self._apply_preview_result(data)
            return
        proc = self._preview_proc
        if proc is not None and proc.poll() is not None:
            stderr_text = ""
            try:
                _out, stderr_text = proc.communicate(timeout=5)
            except Exception:
                stderr_text = ""
            self._finish_preview(seq, terminate=False)
            self._report_preview_unavailable(stderr_text or "", url)
            return
        if attempt >= _PREVIEW_POLL_MAX:
            self._log("warn", "网页预览超时（约 3 分钟），已关闭预览进程。")
            self._finish_preview(seq)
            return
        self.root.after(_PREVIEW_POLL_MS,
                        lambda: self._poll_preview(result_path, url, attempt + 1, seq))

    def _finish_preview(self, seq, terminate=True):
        """结束预览子进程并清理临时文件。"""
        self._preview_seq = max(self._preview_seq, seq) + 1
        proc = self._preview_proc
        self._preview_proc = None
        if terminate and proc is not None and proc.poll() is None:
            try:
                proc.terminate()
            except Exception:
                pass
        path = self._preview_result_path
        self._preview_result_path = None
        self._safe_remove(path)

    @staticmethod
    def _read_preview_result(path):
        """读取预览结果 JSON；文件不存在或内容为空时返回 None。"""
        try:
            with open(path, "r", encoding="utf-8") as handle:
                text = handle.read()
        except FileNotFoundError:
            return None
        except Exception as exc:
            log.debug("读取预览结果失败: %s", exc)
            return None
        if not text.strip():
            return None
        try:
            data = json.loads(text)
        except Exception:
            return None
        return data if isinstance(data, dict) else None

    def _report_preview_unavailable(self, stderr_text, url):
        """预览不可用时给出明确原因并回落到降级预览。"""
        stderr_text = (stderr_text or "").strip()
        if "QT_UNAVAILABLE" in stderr_text:
            msg = "未安装 PyQt5/QtWebEngine，网页预览不可用"
        else:
            brief = stderr_text.splitlines()[-1][:200] if stderr_text else "未知原因"
            msg = f"网页预览进程启动失败：{brief}"
        self._log("warn", f"{msg}，已切换到降级预览。")
        try:
            messagebox.showwarning(
                "预览不可用", f"{msg}。\n将使用内置降级预览（HTML 文本点选）。")
        except Exception:
            pass
        self._fallback_preview(url)

    def _apply_preview_result(self, data):
        """把预览返回的 CSS 选择器写入配置。"""
        selector = str(data.get("css_selector") or "").strip()
        if data.get("cancelled") and not selector:
            self._log("info", "已取消网页预览选元素，CSS 选择器保持不变。")
            return
        if not selector:
            self._log("info", "网页预览未返回 CSS 选择器，保持不变。")
            return
        try:
            node = self.config.enhanced_config.get("element_crawling")
            if not isinstance(node, dict):
                node = {}
                self.config.enhanced_config["element_crawling"] = node
            node["css_selector"] = selector
            if not self.config.save_enhanced():
                raise OSError("写入 enhanced_config.json 失败")
        except Exception as exc:
            log.exception("保存 CSS 选择器失败")
            messagebox.showerror("保存失败", f"保存 CSS 选择器失败: {exc}")
            return
        self.current_selector_var.set(self._selector_text())
        self._log("ok", f"已设置 CSS 选择器: {selector}")

    @staticmethod
    def _prepare_dialog(win, geometry=None):
        """对话框通用外观：纸底背景（Toplevel 不继承 ttk 根背景）。"""
        try:
            win.configure(background=theme.BG)
        except Exception:
            pass
        if geometry:
            win.geometry(geometry)
        return win

    @staticmethod
    def _dialog_box(win, pad=theme.SPACE_LG):
        """对话框主体：白底 + 1px 边框（与面板同一造型语言）。"""
        box = tk.Frame(win, bg=theme.SURFACE, highlightbackground=theme.BORDER,
                       highlightthickness=1, bd=0)
        box.pack(fill=tk.BOTH, expand=True, padx=pad, pady=pad)
        return box

    @staticmethod
    def _dialog_head(box, title, subtitle=""):
        """对话框眉头：PanelTitle / PanelSub（白底场景，不用标题带）。"""
        ttk.Label(box, text=title, style="PanelTitle.TLabel").pack(anchor="w")
        if subtitle:
            ttk.Label(box, text=subtitle, style="PanelSub.TLabel").pack(
                anchor="w", pady=(2, 0))

    def _fallback_preview(self, url):
        """内置降级预览：展示 HTML 结构，点击标签行提取选择器。"""
        win = self._prepare_dialog(ttk.Toplevel(self.root), "900x650")
        win.title(f"网页结构预览 - {url}")
        box = self._dialog_box(win, theme.SPACE_MD)
        self._dialog_head(box, "网页结构预览",
                          "预览页面结构，点击任意标签行以提取 CSS 选择器")
        txt = tk.Text(box, font=theme.font(9, mono=True), wrap=tk.WORD,
                      bd=1, relief="solid", bg=theme.CODE_BG, fg=theme.INK,
                      insertbackground=theme.INK,
                      highlightbackground=theme.BORDER, highlightthickness=1)
        txt.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, pady=(10, 0))
        sb = ttk.Scrollbar(box, orient=tk.VERTICAL, style="App.Vertical.TScrollbar",
                            command=txt.yview)
        sb.pack(side=tk.RIGHT, fill=tk.Y, pady=(10, 0))
        txt.config(yscrollcommand=sb.set)

        def load():
            try:
                html = self.engine.fetch(url)
                text = self.engine._decode(html) if html else ""
                from bs4 import BeautifulSoup
                pretty = BeautifulSoup(text, "html.parser").prettify() if text else "加载失败"
            except Exception as exc:
                pretty = f"加载失败: {exc}"
            self.root.after(0, lambda: (txt.delete(1.0, tk.END),
                                        txt.insert(tk.END, pretty)))

        threading.Thread(target=load, daemon=True).start()

        def pick(_event):
            """从点击行提取 id / class 生成选择器。"""
            line = txt.index(tk.CURRENT).split(".")[0]
            content = txt.get(f"{line}.0", f"{line}.end").strip()
            match = re.match(r"\s*<(/?)(\w+)", content)
            if not match:
                return
            tag = match.group(2)
            id_match = re.search(r'id="([^"]+)"', content)
            class_match = re.search(r'class="([^"]+)"', content)
            selector = tag
            if id_match:
                selector = f"#{id_match.group(1)}"
            elif class_match:
                selector = "." + ".".join(class_match.group(1).split())
            self.config.enhanced_config["element_crawling"]["css_selector"] = selector
            self.config.save_enhanced()
            self.current_selector_var.set(self._selector_text())
            self._log("ok", f"已设置 CSS 选择器: {selector}")
            win.destroy()

        txt.bind("<Button-1>", pick)

    def get_element_selector(self):
        """手动填写 CSS 选择器。"""
        win = self._prepare_dialog(ttk.Toplevel(self.root), "660x520")
        win.title("元素选择器")
        box = self._dialog_box(win, theme.SPACE_LG)
        self._dialog_head(box, "元素选择器", "用 CSS 选择器指定要抓取链接的区域")
        help_text = ("  #content → id 为 content 的元素内\n"
                     "  .links  → class 为 links 的元素内\n"
                     "  div / ul / article / section → 指定标签内\n"
                     "  留空 → 整个页面")
        ttk.Label(box, text=help_text, style="App.TLabel",
                  justify="left").pack(anchor="w", pady=(10, 10))
        entry = ttk.Entry(box, style="App.TEntry", font=theme.font(10))
        entry.pack(fill=tk.X)
        entry.insert(0, self.config.css_selector)
        presets = tk.Frame(box, bg=theme.SURFACE)
        presets.pack(fill=tk.X, pady=10)
        for index, (text, value) in enumerate(
                [("整个页面", ""), ("#content", "#content"), (".links", ".links"),
                 ("div", "div"), ("ul", "ul"), ("article", "article"),
                 ("section", "section"), ("table", "table")]):
            ttk.Button(presets, text=text, style="Secondary.TButton",
                       command=lambda v=value: (entry.delete(0, tk.END),
                                               entry.insert(0, v))
                       ).grid(row=index // 4, column=index % 4, padx=4, pady=4, sticky="w")
        btns = tk.Frame(box, bg=theme.SURFACE)
        btns.pack(fill=tk.X, pady=(12, 0))

        def save():
            selector = entry.get().strip()
            node = self.config.enhanced_config.get("element_crawling")
            if not isinstance(node, dict):
                node = {}
                self.config.enhanced_config["element_crawling"] = node
            node["css_selector"] = selector
            self.config.save_enhanced()
            self.current_selector_var.set(self._selector_text())
            self._log("ok", f"CSS 选择器已设置: {selector or '整个页面'}")
            win.destroy()

        self._btn(btns, "保存选择器", "check", "Primary.TButton", save).pack(side=tk.RIGHT)
        self._btn(btns, "取消", "close", "Secondary.TButton",
                  win.destroy).pack(side=tk.RIGHT, padx=(0, 8))

    # ---- 增强功能配置 ----
    def configure_enhanced(self):
        """打开增强功能配置窗口。"""
        win = self._prepare_dialog(ttk.Toplevel(self.root), "780x840")
        win.title("增强功能配置")
        win.minsize(700, 580)
        ec = self.config.enhanced_config

        def sec(*keys):
            """按路径取/建配置子节点，避免旧配置缺键时抛 KeyError。"""
            node = ec
            for key in keys:
                child = node.get(key)
                if not isinstance(child, dict):
                    child = {}
                    node[key] = child
                node = child
            return node

        def lines_of(widget):
            text = widget.get(1.0, tk.END)
            return [line.strip() for line in text.splitlines() if line.strip()]

        def int_of(var, label, lo, hi):
            """解析整数输入，越界或非法时抛出带友好提示的 ValueError。"""
            raw = str(var.get()).strip()
            if not raw:
                raise ValueError(f"「{label}」不能为空，请输入 {lo}~{hi} 的整数。")
            try:
                value = int(raw, 10)
            except (TypeError, ValueError):
                try:
                    number = float(raw)
                except (TypeError, ValueError):
                    raise ValueError(f"「{label}」不是有效整数：{raw}") from None
                if not math.isfinite(number) or not number.is_integer():
                    raise ValueError(f"「{label}」必须是整数：{raw}")
                value = int(number)
            if value < lo or value > hi:
                raise ValueError(f"「{label}」超出范围（{lo}~{hi}）：{value}")
            return value

        def float_of(var, label, lo=0.0):
            """解析浮点输入，越界或非法时抛出带友好提示的 ValueError。"""
            raw = str(var.get()).strip()
            if not raw:
                raise ValueError(f"「{label}」不能为空。")
            try:
                value = float(raw)
            except (TypeError, ValueError):
                raise ValueError(f"「{label}」不是有效数字：{raw}") from None
            if not math.isfinite(value) or value < lo:
                raise ValueError(f"「{label}」必须 ≥ {lo:g}。")
            return value

        def fmt_number(value):
            try:
                return f"{float(value):g}"
            except (TypeError, ValueError):
                return "0"

        def section(title):
            """配置窗口内的分组区块（白底 + 1px 边框 + 标题下细线）。"""
            frame = tk.Frame(inner, bg=theme.SURFACE,
                             highlightbackground=theme.BORDER, highlightthickness=1)
            frame.pack(fill=tk.X, padx=theme.SPACE_MD, pady=(theme.SPACE_MD, 0))
            ttk.Label(frame, text=title, style="PanelTitle.TLabel").pack(
                anchor="w", padx=theme.SPACE_MD + 2, pady=(10, 6))
            tk.Frame(frame, bg=theme.PANEL_BAND_LINE, height=1).pack(
                fill=tk.X, pady=(0, 6))
            return frame

        def row_of(frame):
            row = tk.Frame(frame, bg=theme.SURFACE)
            row.pack(fill=tk.X, padx=14, pady=3)
            return row

        def check(frame, text, var):
            ttk.Checkbutton(frame, text=text, style="App.TCheckbutton",
                            variable=var).pack(anchor="w", padx=14, pady=2)

        def textbox(frame, height=4):
            widget = tk.Text(frame, height=height, font=theme.font(9, mono=True),
                             wrap=tk.WORD, bd=1, relief="solid", bg=theme.CODE_BG,
                             fg=theme.INK, insertbackground=theme.INK,
                             highlightbackground=theme.BORDER,
                             highlightthickness=1)
            widget.pack(fill=tk.X, padx=14, pady=(0, 8))
            return widget

        # 保存/取消栏先打包，保证长表单滚动时按钮始终可见
        bar = tk.Frame(win, bg=theme.BG)
        bar.pack(fill=tk.X, side=tk.BOTTOM, pady=8, padx=12)

        container = tk.Frame(win, bg=theme.BG)
        container.pack(fill=tk.BOTH, expand=True)
        canvas = tk.Canvas(container, bg=theme.BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient=tk.VERTICAL,
                                   style="App.Vertical.TScrollbar",
                                   command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        inner = tk.Frame(canvas, bg=theme.BG)
        inner_item = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>",
                   lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>",
                    lambda e: canvas.itemconfig(inner_item, width=e.width))

        def wheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", wheel))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # 基础
        frame = section("基础")
        enabled = tk.BooleanVar(value=bool(ec.get("enabled", True)))
        check(frame, "启用增强功能", enabled)

        # 多 URL
        frame = section("多 URL 抓取")
        multi = sec("multi_url")
        mu_enabled = tk.BooleanVar(value=bool(multi.get("enabled", True)))
        mu_batch = tk.BooleanVar(value=bool(multi.get("batch_import", True)))
        mu_validate = tk.BooleanVar(value=bool(multi.get("url_validation", True)))
        check(frame, "启用多 URL 模式", mu_enabled)
        check(frame, "启用批量导入（文件导入 URL）", mu_batch)
        check(frame, "启用 URL 格式校验", mu_validate)
        ttk.Label(frame, text="（多 URL 模式切换需重启程序后生效）",
                  style="Muted.TLabel").pack(anchor="w", padx=14, pady=(0, 8))

        # 深度与上限
        frame = section("抓取深度与上限")
        depth_cfg = sec("crawling_depth")
        depth_enabled = tk.BooleanVar(value=bool(depth_cfg.get("enabled", True)))
        check(frame, "启用深度抓取", depth_enabled)
        try:
            current_depth = int(depth_cfg.get("depth", 1))
        except (TypeError, ValueError):
            current_depth = 1
        depth_var = tk.IntVar(value=current_depth)
        depth_row = row_of(frame)
        for text, value in [("仅当前页", 0), ("+1 级", 1), ("+2 级", 2), ("自定义", 3)]:
            ttk.Radiobutton(depth_row, text=text, style="App.TRadiobutton",
                            variable=depth_var, value=value).pack(side=tk.LEFT, padx=(0, 12))
        custom_depth = tk.StringVar(value=str(current_depth if current_depth > 2 else 3))
        custom_row = row_of(frame)
        ttk.Label(custom_row, text="自定义深度(1~5):", style="App.TLabel").pack(side=tk.LEFT)
        ttk.Spinbox(custom_row, from_=1, to=5, width=5,
                    textvariable=custom_depth, style="App.TSpinbox").pack(side=tk.LEFT, padx=6)

        limits = sec("crawl_limits")
        max_pages = tk.StringVar(value=str(limits.get("max_pages", 200)))
        concurrency = tk.StringVar(value=str(limits.get("concurrency", 8)))
        limits_row = row_of(frame)
        ttk.Label(limits_row, text="最大抓取页数(1~100000):", style="App.TLabel").pack(side=tk.LEFT)
        ttk.Spinbox(limits_row, from_=1, to=100000, width=10,
                    textvariable=max_pages, style="App.TSpinbox").pack(side=tk.LEFT, padx=6)
        ttk.Label(limits_row, text="并发数(1~64):", style="App.TLabel").pack(
            side=tk.LEFT, padx=(16, 0))
        ttk.Spinbox(limits_row, from_=1, to=64, width=6,
                    textvariable=concurrency, style="App.TSpinbox").pack(side=tk.LEFT, padx=6)

        # 排除规则
        frame = section("排除规则")
        exclude = sec("exclude_rules")
        ex_enabled = tk.BooleanVar(value=bool(exclude.get("enabled", False)))
        ex_regex = tk.BooleanVar(value=bool(exclude.get("use_regex", False)))
        check(frame, "启用排除规则", ex_enabled)
        check(frame, "使用正则（否则按通配符匹配）", ex_regex)
        ttk.Label(frame, text="规则（每行一条，如 *.jpg 或 /ads/）:",
                  style="App.TLabel").pack(anchor="w", padx=14, pady=(6, 2))
        exclude_text = textbox(frame, 4)
        exclude_text.insert(tk.END, "\n".join(exclude.get("patterns") or []))

        # 元素抓取
        frame = section("元素抓取")
        element = sec("element_crawling")
        el_enabled = tk.BooleanVar(value=bool(element.get("enabled", True)))
        check(frame, "启用元素抓取", el_enabled)
        ttk.Label(frame, text="默认 CSS 选择器（留空 = 整个页面）:",
                  style="App.TLabel").pack(anchor="w", padx=14, pady=(6, 2))
        element_text = textbox(frame, 2)
        element_text.insert(tk.END, element.get("css_selector", "") or "")

        # 文件过滤
        frame = section("文件过滤")
        file_filters = sec("file_filters")
        ff_enabled = tk.BooleanVar(value=bool(file_filters.get("enabled", True)))
        check(frame, "启用文件过滤", ff_enabled)
        size_filter = sec("file_filters", "size_filter")
        sf_enabled = tk.BooleanVar(value=bool(size_filter.get("enabled", False)))
        check(frame, "启用大小过滤（仅对文件链接生效）", sf_enabled)
        min_size = tk.StringVar(value=fmt_number(size_filter.get("min_size", 0)))
        max_size = tk.StringVar(value=fmt_number(size_filter.get("max_size", 0)))
        size_row = row_of(frame)
        ttk.Label(size_row, text="最小(MB, ≥0):", style="App.TLabel").pack(side=tk.LEFT)
        ttk.Entry(size_row, width=8, textvariable=min_size,
                  style="App.TEntry").pack(side=tk.LEFT, padx=6)
        ttk.Label(size_row, text="最大(MB, ≥0，0=不限):", style="App.TLabel").pack(
            side=tk.LEFT, padx=(12, 0))
        ttk.Entry(size_row, width=8, textvariable=max_size,
                  style="App.TEntry").pack(side=tk.LEFT, padx=6)
        time_filter = sec("file_filters", "time_filter")
        tf_enabled = tk.BooleanVar(value=bool(time_filter.get("enabled", False)))
        check(frame, "启用时间过滤（按 Last-Modified）", tf_enabled)
        days = tk.StringVar(value=str(time_filter.get("days", 7)))
        days_row = row_of(frame)
        ttk.Label(days_row, text="最近天数(1~365):", style="App.TLabel").pack(side=tk.LEFT)
        ttk.Spinbox(days_row, from_=1, to=365, width=6,
                    textvariable=days, style="App.TSpinbox").pack(side=tk.LEFT, padx=6)
        tk.Frame(frame, bg=theme.SURFACE, height=6).pack(fill=tk.X)

        # 断点续爬
        frame = section("断点续爬")
        resumable_cfg = sec("resumable_crawling")
        resumable = tk.BooleanVar(value=bool(resumable_cfg.get("enabled", True)))
        check(frame, "启用断点续爬（任务与链接实时入库）", resumable)
        tk.Frame(frame, bg=theme.SURFACE, height=6).pack(fill=tk.X)

        # 反反爬与请求策略
        frame = section("反反爬与请求策略")
        anti = sec("anti_anti_crawl")
        aac_enabled = tk.BooleanVar(value=bool(anti.get("enabled", True)))
        check(frame, "启用反反爬", aac_enabled)
        dynamic_ua = tk.BooleanVar(value=bool(anti.get("dynamic_ua", True)))
        check(frame, "动态 User-Agent（从 UA 列表随机选择）", dynamic_ua)
        ttk.Label(frame, text="UA 列表（每行一个）:", style="App.TLabel").pack(
            anchor="w", padx=14, pady=(4, 2))
        ua_text = textbox(frame, 4)
        ua_text.insert(tk.END, "\n".join(anti.get("ua_list") or []))
        proxy_cfg = sec("anti_anti_crawl", "proxy")
        proxy_enabled = tk.BooleanVar(value=bool(proxy_cfg.get("enabled", False)))
        check(frame, "启用代理", proxy_enabled)
        proxy_type = tk.StringVar(value=str(proxy_cfg.get("type", "http") or "http"))
        proxy_row = row_of(frame)
        ttk.Label(proxy_row, text="代理类型:", style="App.TLabel").pack(side=tk.LEFT, padx=(0, 6))
        ttk.Radiobutton(proxy_row, text="HTTP", style="App.TRadiobutton",
                        variable=proxy_type, value="http").pack(side=tk.LEFT, padx=(0, 12))
        ttk.Radiobutton(proxy_row, text="SOCKS5", style="App.TRadiobutton",
                        variable=proxy_type, value="socks5").pack(side=tk.LEFT)
        ttk.Label(frame, text="代理列表（每行一个，如 host:port 或 user:pass@host:port）:",
                  style="App.TLabel").pack(anchor="w", padx=14, pady=(4, 2))
        proxy_text = textbox(frame, 3)
        proxy_text.insert(tk.END, "\n".join(proxy_cfg.get("proxy_list") or []))
        cookie_cfg = sec("anti_anti_crawl", "cookies")
        cookie_enabled = tk.BooleanVar(value=bool(cookie_cfg.get("enabled", False)))
        check(frame, "启用 Cookie", cookie_enabled)
        ttk.Label(frame, text="Cookie 列表（每行一个 k=v）:", style="App.TLabel").pack(
            anchor="w", padx=14, pady=(4, 2))
        cookie_text = textbox(frame, 3)
        cookie_text.insert(tk.END, "\n".join(cookie_cfg.get("cookie_list") or []))
        strategy = sec("anti_anti_crawl", "request_strategy")
        rs_enabled = tk.BooleanVar(value=bool(strategy.get("enabled", True)))
        check(frame, "启用请求策略（间隔/重试/超时）", rs_enabled)
        interval = tk.StringVar(value=str(strategy.get("interval", 2)))
        retries = tk.StringVar(value=str(strategy.get("retries", 3)))
        timeout = tk.StringVar(value=str(strategy.get("timeout", 10)))
        strategy_row = row_of(frame)
        for label, var, lo, hi in [("间隔(s)0~60", interval, 0, 60),
                                  ("重试 1~10", retries, 1, 10),
                                  ("超时(s)3~120", timeout, 3, 120)]:
            ttk.Label(strategy_row, text=f"{label}:", style="App.TLabel").pack(
                side=tk.LEFT, padx=(0, 4))
            ttk.Spinbox(strategy_row, from_=lo, to=hi, width=6,
                        textvariable=var, style="App.TSpinbox").pack(side=tk.LEFT, padx=(0, 14))
        tk.Frame(frame, bg=theme.SURFACE, height=6).pack(fill=tk.X)

        # 网络安全
        frame = section("网络安全")
        policy = sec("network_policy")
        respect_robots = tk.BooleanVar(value=bool(policy.get("respect_robots", True)))
        block_private = tk.BooleanVar(value=bool(policy.get("block_private_redirects", True)))
        check(frame, "遵守 robots.txt", respect_robots)
        check(frame, "阻止重定向到内网/私有地址", block_private)
        max_html = tk.StringVar(value=str(policy.get("max_html_bytes", 5 * 1024 * 1024)))
        max_redirects = tk.StringVar(value=str(policy.get("max_redirects", 5)))
        html_row = row_of(frame)
        ttk.Label(html_row, text="HTML 上限(字节 65536~104857600):",
                  style="App.TLabel").pack(side=tk.LEFT)
        ttk.Spinbox(html_row, from_=65536, to=104857600, increment=65536, width=12,
                    textvariable=max_html, style="App.TSpinbox").pack(side=tk.LEFT, padx=6)
        redirect_row = row_of(frame)
        ttk.Label(redirect_row, text="重定向上限(0~20):", style="App.TLabel").pack(side=tk.LEFT)
        ttk.Spinbox(redirect_row, from_=0, to=20, width=6,
                    textvariable=max_redirects, style="App.TSpinbox").pack(side=tk.LEFT, padx=6)
        tk.Frame(frame, bg=theme.SURFACE, height=6).pack(fill=tk.X)

        def save():
            """校验并保存全部配置项。"""
            try:
                depth_choice = depth_var.get()
            except Exception:
                depth_choice = 1
            if depth_choice not in (0, 1, 2, 3):
                depth_choice = 1
            try:
                depth_value = int_of(custom_depth, "自定义深度", 1, 5) \
                    if depth_choice == 3 else depth_choice
                max_pages_value = int_of(max_pages, "最大抓取页数", 1, 100000)
                concurrency_value = int_of(concurrency, "并发数", 1, 64)
                interval_value = int_of(interval, "请求间隔", 0, 60)
                retries_value = int_of(retries, "重试次数", 1, 10)
                timeout_value = int_of(timeout, "超时时间", 3, 120)
                days_value = int_of(days, "时间过滤天数", 1, 365)
                min_size_value = float_of(min_size, "最小文件大小(MB)", 0.0)
                max_size_value = float_of(max_size, "最大文件大小(MB)", 0.0)
                max_html_value = int_of(max_html, "HTML体积上限(字节)", 65536, 104857600)
                max_redirects_value = int_of(max_redirects, "重定向上限", 0, 20)
            except ValueError as exc:
                messagebox.showerror("参数错误", str(exc), parent=win)
                return
            if max_size_value > 0 and min_size_value > max_size_value:
                messagebox.showerror("参数错误", "最小文件大小不能大于最大文件大小。", parent=win)
                return

            ec["enabled"] = bool(enabled.get())
            sec("multi_url").update({
                "enabled": bool(mu_enabled.get()),
                "batch_import": bool(mu_batch.get()),
                "url_validation": bool(mu_validate.get()),
            })
            sec("crawling_depth")["enabled"] = bool(depth_enabled.get())
            sec("crawling_depth")["depth"] = depth_value
            sec("crawl_limits")["max_pages"] = max_pages_value
            sec("crawl_limits")["concurrency"] = concurrency_value
            sec("exclude_rules").update({
                "enabled": bool(ex_enabled.get()),
                "use_regex": bool(ex_regex.get()),
                "patterns": lines_of(exclude_text),
            })
            sec("element_crawling")["enabled"] = bool(el_enabled.get())
            sec("element_crawling")["css_selector"] = element_text.get(1.0, tk.END).strip()
            sec("file_filters")["enabled"] = bool(ff_enabled.get())
            sec("file_filters", "size_filter").update({
                "enabled": bool(sf_enabled.get()),
                "min_size": min_size_value,
                "max_size": max_size_value,
            })
            sec("file_filters", "time_filter").update({
                "enabled": bool(tf_enabled.get()),
                "days": days_value,
            })
            sec("resumable_crawling")["enabled"] = bool(resumable.get())
            sec("anti_anti_crawl")["enabled"] = bool(aac_enabled.get())
            sec("anti_anti_crawl")["dynamic_ua"] = bool(dynamic_ua.get())
            sec("anti_anti_crawl")["ua_list"] = lines_of(ua_text)
            sec("anti_anti_crawl", "proxy").update({
                "enabled": bool(proxy_enabled.get()),
                "type": proxy_type.get() if proxy_type.get() in ("http", "socks5") else "http",
                "proxy_list": lines_of(proxy_text),
            })
            sec("anti_anti_crawl", "cookies").update({
                "enabled": bool(cookie_enabled.get()),
                "cookie_list": lines_of(cookie_text),
            })
            sec("anti_anti_crawl", "request_strategy").update({
                "enabled": bool(rs_enabled.get()),
                "interval": interval_value,
                "retries": retries_value,
                "timeout": timeout_value,
            })
            sec("network_policy").update({
                "respect_robots": bool(respect_robots.get()),
                "max_html_bytes": max_html_value,
                "max_redirects": max_redirects_value,
                "block_private_redirects": bool(block_private.get()),
            })
            if not self.config.save_enhanced():
                messagebox.showerror("保存失败",
                                     "写入 enhanced_config.json 失败，请检查文件权限。",
                                     parent=win)
                return
            self.current_selector_var.set(self._selector_text())
            messagebox.showinfo("保存成功", "增强功能配置已保存。", parent=win)
            win.destroy()

        self._btn(bar, "保存配置", "check", "Primary.TButton", save).pack(side=tk.RIGHT)
        self._btn(bar, "取消", "close", "Secondary.TButton",
                  win.destroy).pack(side=tk.RIGHT, padx=(0, 8))

    # ---- 文件类型编辑 ----
    def edit_file_types(self):
        """打开文件类型映射编辑器。"""
        win = self._prepare_dialog(ttk.Toplevel(self.root), "740x700")
        win.title("编辑文件类型")
        box = self._dialog_box(win, theme.SPACE_LG)
        self._dialog_head(box, "编辑文件类型映射",
                          "左侧选择分类，右侧维护该分类的扩展名")

        cols = tk.Frame(box, bg=theme.SURFACE)
        cols.pack(fill=tk.BOTH, expand=True, pady=(10, 0))
        left = tk.Frame(cols, bg=theme.SURFACE)
        left.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 14))
        ttk.Label(left, text="分类", style="Section.TLabel").pack(anchor="w")
        cat_lb = tk.Listbox(left, width=18, font=theme.font(10), bd=1, relief="solid",
                            bg=theme.SURFACE_SUNK, fg=theme.INK,
                            selectbackground=theme.PRIMARY_SOFT,
                            selectforeground=theme.INK_STRONG,
                            highlightbackground=theme.BORDER,
                            highlightcolor=theme.BORDER_STRONG,
                            highlightthickness=1)
        cat_lb.pack(fill=tk.Y, expand=True, pady=6)
        right = tk.Frame(cols, bg=theme.SURFACE)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        ttk.Label(right, text="扩展名", style="Section.TLabel").pack(anchor="w")
        ext_lb = tk.Listbox(right, width=30, font=theme.font(10), bd=1, relief="solid",
                            bg=theme.SURFACE_SUNK, fg=theme.INK,
                            selectbackground=theme.PRIMARY_SOFT,
                            selectforeground=theme.INK_STRONG,
                            highlightbackground=theme.BORDER,
                            highlightcolor=theme.BORDER_STRONG,
                            highlightthickness=1)
        ext_lb.pack(fill=tk.BOTH, expand=True, pady=6)

        def pop_cats():
            """刷新分类列表。"""
            cat_lb.delete(0, tk.END)
            for cat in sorted(self.config.file_type_mapping.keys()):
                cat_lb.insert(tk.END, cat)

        def pop_exts(cat):
            """刷新指定分类的扩展名列表。"""
            ext_lb.delete(0, tk.END)
            for ext in sorted(self.config.file_type_mapping.get(cat, [])):
                ext_lb.insert(tk.END, ext)

        def on_sel(_event):
            """分类选中时联动刷新扩展名。"""
            selection = cat_lb.curselection()
            if selection:
                pop_exts(cat_lb.get(selection[0]))

        cat_lb.bind("<<ListboxSelect>>", on_sel)

        inp = tk.Frame(box, bg=theme.SURFACE)
        inp.pack(fill=tk.X, pady=8)
        ttk.Label(inp, text="新分类:", style="App.TLabel").pack(side=tk.LEFT)
        cat_e = ttk.Entry(inp, style="App.TEntry", width=16)
        cat_e.pack(side=tk.LEFT, padx=6)
        ttk.Label(inp, text="新扩展名(逗号分隔):", style="App.TLabel").pack(side=tk.LEFT, padx=(12, 0))
        ext_e = ttk.Entry(inp, style="App.TEntry", width=24)
        ext_e.pack(side=tk.LEFT, padx=6)

        def add_cat():
            """新增分类（支持逗号分隔批量）。"""
            names = [x.strip() for x in cat_e.get().split(",") if x.strip()]
            added = 0
            for name in names:
                if name not in self.config.file_type_mapping:
                    self.config.file_type_mapping[name] = []
                    added += 1
            pop_cats()
            cat_e.delete(0, tk.END)
            messagebox.showinfo("添加分类", f"新增 {added} 个分类。")

        def add_ext():
            """向选中分类追加扩展名。"""
            selection = cat_lb.curselection()
            if not selection:
                messagebox.showwarning("警告", "请先选择分类。")
                return
            cat = cat_lb.get(selection[0])
            exts = [x.strip().lower() for x in ext_e.get().split(",") if x.strip()]
            added = 0
            for ext in exts:
                if not ext.startswith("."):
                    ext = "." + ext
                if ext not in self.config.file_type_mapping[cat]:
                    self.config.file_type_mapping[cat].append(ext)
                    added += 1
            pop_exts(cat)
            ext_e.delete(0, tk.END)
            messagebox.showinfo("添加扩展名", f"新增 {added} 个扩展名。")

        def del_cat():
            """删除选中分类（需确认）。"""
            selection = cat_lb.curselection()
            if not selection:
                return
            cat = cat_lb.get(selection[0])
            if messagebox.askyesno("确认", f"删除分类「{cat}」？"):
                del self.config.file_type_mapping[cat]
                pop_cats()
                ext_lb.delete(0, tk.END)

        def del_ext():
            """删除选中扩展名。"""
            selection = cat_lb.curselection()
            ext_selection = ext_lb.curselection()
            if not selection or not ext_selection:
                return
            cat = cat_lb.get(selection[0])
            ext = ext_lb.get(ext_selection[0])
            if ext in self.config.file_type_mapping[cat]:
                self.config.file_type_mapping[cat].remove(ext)
            pop_exts(cat)

        btns = tk.Frame(box, bg=theme.SURFACE)
        btns.pack(fill=tk.X, pady=8)
        self._btn(btns, "添加分类", "check", "Secondary.TButton", add_cat).pack(side=tk.LEFT, padx=(0, 6))
        self._btn(btns, "删除分类", "trash", "DangerOutline.TButton", del_cat).pack(side=tk.LEFT, padx=(0, 16))
        self._btn(btns, "添加扩展名", "check", "Secondary.TButton", add_ext).pack(side=tk.LEFT, padx=(0, 6))
        self._btn(btns, "删除扩展名", "trash", "DangerOutline.TButton", del_ext).pack(side=tk.LEFT)

        savebar = tk.Frame(win, bg=theme.BG)
        savebar.pack(fill=tk.X, side=tk.BOTTOM, pady=8, padx=16)

        def save():
            """保存文件类型映射并刷新筛选控件。"""
            self.config.save_file_types()
            self.filter_combobox.configure(values=self.config.filter_options())
            self._build_checkboxes()
            self._update_filter_mode()
            messagebox.showinfo("保存成功", "文件类型映射已更新。")
            win.destroy()

        self._btn(savebar, "保存更改", "check", "Primary.TButton", save).pack(side=tk.RIGHT)
        self._btn(savebar, "取消", "close", "Secondary.TButton",
                  win.destroy).pack(side=tk.RIGHT, padx=(0, 8))

        pop_cats()

    # ---- 关于 / 帮助 ----
    def show_about(self):
        """关于窗口。"""
        win = self._prepare_dialog(ttk.Toplevel(self.root))
        win.title("关于")
        win.resizable(False, False)
        box = self._dialog_box(win, 26)
        logo = ttk.Label(box, image=theme.ico("seal", theme.ACCENT, theme.SURFACE, 44),
                         background=theme.SURFACE)
        logo.image = theme.ico("seal", theme.ACCENT, theme.SURFACE, 44)
        logo.pack(pady=(0, 10))
        ttk.Label(box, text="网页链接抓取工具", style="PanelTitle.TLabel").pack()
        ttk.Label(box, text=f"v{APP_VERSION} · {theme.CURRENT_PALETTE}视觉体系",
                  style="Muted.TLabel").pack(pady=(2, 12))
        desc = ("支持单/多 URL 链接抓取、多维筛选、深度抓取、反反爬、断点续爬、\n"
                "元素选择/CSS 选择器、链接体检与结构化导出。")
        ttk.Label(box, text=desc, style="App.TLabel", justify="center",
                  wraplength=400).pack(pady=(0, 14))
        ttk.Label(box, text=f"开发者: {APP_VENDOR}", style="App.TLabel").pack()
        site = tk.Label(box, text=APP_SITE.replace("http://", ""), bg=theme.SURFACE,
                        fg=theme.PRIMARY, font=theme.font(10, bold=True), cursor="hand2")
        site.pack(pady=6)
        site.bind("<Button-1>", lambda e: webbrowser.open(APP_SITE))
        ttk.Label(box, text=f"© 2026 {APP_VENDOR}. 保留所有权利。",
                  style="Muted.TLabel").pack(pady=(10, 0))
        win.update_idletasks()
        x = (win.winfo_screenwidth() - win.winfo_width()) // 2
        y = (win.winfo_screenheight() - win.winfo_height()) // 2
        win.geometry(f"+{x}+{y}")

    def _show_help(self):
        """使用说明。"""
        messagebox.showinfo(
            "使用说明",
            "1. 在「任务布设」页输入目标网址（每行一条，可导入/导出/校验）。\n"
            "2. 需要限定区域时，用「范围限定」预览选元素或手动填写 CSS 选择器。\n"
            "3. 在「筛选规则」选择类型与关键词，点击「开始抓取」。\n"
            "4. 抓取后在「结果清册」页查看表格，可点表头排序、应用筛选、\n"
            "   「链接体检」查看存活状态，并导出 TXT / CSV / JSON。\n"
            "5. 「事件流水」页查看分级事件与异常。\n"
            "6. 更多选项见「参数配置」页或菜单「编辑」。",
        )

    # ---- 配色方案 ----
    def toggle_theme(self):
        """循环切换到下一个配色方案（真正改变配色，而非只换底板）。"""
        name = theme.next_palette()
        self._apply_palette(name)
        self._log("info", f"已切换配色方案: {name}")

    def _apply_palette(self, name):
        """应用指定配色方案并重绘受影响的界面元素。"""
        if not theme.set_palette(name):
            return
        theme.apply_theme(self.style, self.root)
        self._repaint_shell()
        self._repaint_surfaces()
        self._repaint_panels()
        self._repaint_buttons()
        self._repaint_menus()
        self._repaint_table_tags()
        self._palette_hint.configure(text=f"当前配色方案：{theme.CURRENT_PALETTE}")
        if getattr(self, "_rail_palette_label", None) is not None:
            self._rail_palette_label.configure(text=f"配色 · {theme.CURRENT_PALETTE}")

    def _repaint_shell(self):
        """重绘导航栏纸底、右侧边线与品牌图标。"""
        try:
            self._rail.configure(bg=theme.RAIL)
            self._rail_edge.configure(bg=theme.RAIL_EDGE)
            self._rail_sep.configure(bg=theme.RAIL_LINE)
        except Exception:
            pass
        brand = getattr(self, "_rail_brand_icon", None)
        if brand is not None:
            try:
                label, icon = brand
                img = theme.rail_ico(icon, theme.ACCENT, theme.RAIL, 24)
                label.configure(image=img, background=theme.RAIL)
                label.image = img
            except Exception:
                pass
        # 重新触发当前页高亮
        try:
            self._show_page(self._current_page())
        except Exception:
            pass

    def _repaint_surfaces(self):
        """按当前配色重绘全部登记的 tk 容器背景与文字前景。"""
        for widget, token in list(self._surface_slots):
            try:
                widget.configure(bg=getattr(theme, token))
            except Exception:
                pass
        for widget, token in list(self._fg_slots):
            try:
                widget.configure(fg=getattr(theme, token))
            except Exception:
                pass

    def _repaint_panels(self):
        """重绘各面板标题带、底部细线、内容区与标题带图标。"""
        for head, line, body, icon_label, icon in list(self._panel_slots):
            try:
                head.configure(bg=theme.PANEL_BAND_BG)
                line.configure(bg=theme.PANEL_BAND_LINE)
                body.configure(bg=theme.SURFACE)
                icon_label.configure(background=theme.PANEL_BAND_BG)
                img = theme.ico(icon, theme.ACCENT, theme.PANEL_BAND_BG, 22)
                icon_label.configure(image=img)
                icon_label.image = img
            except Exception:
                pass

    def _repaint_menus(self):
        """重绘 tk 菜单配色（tk.Menu 不走 ttk 命名样式）。"""
        colors = self._menu_colors()
        for menu in list(self._menus):
            try:
                menu.configure(**colors)
            except Exception:
                pass

    def _current_page(self):
        """推断当前显示的页面键（用于配色切换后恢复高亮）。"""
        for key, frame in self._pages.items():
            if frame.winfo_ismapped():
                return key
        return "targets"

    def _repaint_buttons(self):
        """按当前配色重绘全部按钮图标与导航图标。"""
        for button, icon, role, size in list(self._icon_slots):
            try:
                bg = _ROLE_BG.get(role, theme.SURFACE)
                fg = _OUTLINE_FG.get(role, "#FFFFFF")
                img = theme.ico(icon, fg, bg, size)
                button.configure(image=img)
                button.image = img
            except Exception:
                continue
        current = self._current_page()
        for key in self._nav_buttons:
            self._paint_nav_item(key, key == current)

    def _repaint_table_tags(self):
        """重绘结果表格的状态标签颜色。"""
        try:
            for tag, color in (("ok", theme.SUCCESS), ("dead", theme.DANGER),
                               ("redirect", theme.INFO), ("blocked", theme.WARNING),
                               ("error", theme.MUTED), ("unknown", theme.MUTED_LIGHT)):
                self.tree.tag_configure(tag, foreground=color)
        except Exception:
            pass

    # ---- 关闭 ----
    def _on_close(self):
        """关闭窗口：必要时先停止抓取并清理子进程。"""
        if self.is_crawling:
            if not messagebox.askyesno("退出", "抓取正在进行，确定退出？"):
                return
            self.engine.stop()
        self._stop_preview_process()
        try:
            self.db.close()
        except Exception:
            pass
        self.root.destroy()

    def _stop_preview_process(self):
        """关闭 App 时终止仍存活的网页预览进程。"""
        self._finish_preview(self._preview_seq)


def main():
    """程序入口。"""
    setup_logging()
    root = ttk.Window()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
