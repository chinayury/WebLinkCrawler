"""视觉体系「宣纸·墨黛」（Rice Paper & Ink）—— 全浅色，无暗色主题，无背景图。

设计要点（与既有三套「青瓷·赭石 / 黛蓝·琥珀 / 陶红·亚麻」形成双轴差异）：
- **色相族**：近单色「墨」+ 单一「朱印」。主色由饱和彩色改为中性墨 #22262B，
  强调色朱印 #B03A2E 仅用于品牌标记、主操作与失效计数；青瓷绿 / 黛蓝 / 陶红
  三族全部退场，色相族零重叠；
- **造型语言**：去掉「左侧深色导航栏」这一视觉锚点，导航改为浅色纸底
  #F5F2EA + 1px 右边线，激活项用 2px 朱红左杠 + 加粗文字表达；面板去掉
  「左侧色条 + 通栏标题带」的彩色色条，改「通栏浅标题带 + 底部 1px 细线」；
  按钮改为「实底墨色 / 1px 描边 / 纯文字链」三档；表格只保留横向细线
  （无竖线、无斑马纹）；层级主要靠字重与字号，墨色浓淡由三级笔宽承担；
- **语义色降饱和**：成功 / 警示 / 危险 / 信息全部压低饱和度，使五级链接
  状态色成为近单色画布上唯一的高饱和信号，不被主色稀释。

本模块只负责配色、字体与 ttk 样式定义；图标光栅化在 icons.py。
所有样式集中在此，保证界面换肤只需改一处。

对外契约（保持不变）：apply_theme / font / FONT_FAMILY / MONO_FAMILY /
PALETTES / DEFAULT_PALETTE / CURRENT_PALETTE / palette_names / set_palette /
next_palette / ico / rail_ico / btn_ico，以及全部既有命名样式名。
"""

from __future__ import annotations

from . import icons

# ---- 配色 ---------------------------------------------------------------
# 画布与面板（宣纸）
BG = "#FAF8F3"            # 应用画布（宣纸白）
SURFACE = "#FFFFFF"       # 面板/卡片
SURFACE_ALT = "#F7F5EF"   # 次级面板（芯片、条纹）
SURFACE_SUNK = "#F1EEE6"  # 凹陷区（输入框底、代码块）

# 左侧导航栏（浅色纸底，去掉深色导航栏）
RAIL = "#F5F2EA"          # 导航纸底
RAIL_HOVER = "#EFEBE0"    # 导航悬停底
RAIL_ACTIVE = "#EAE6DA"   # 导航激活底（极浅，激活主要靠左杠与字重表达）
RAIL_ACTIVE_FG = "#22262B"  # 导航激活文字（墨，加粗）
RAIL_FG = "#22262B"       # 导航主文字（墨）
RAIL_FG_DIM = "#7A7361"   # 导航次文字（分组标题、底部信息）
RAIL_LINE = "#E2DCCF"     # 导航分隔线
RAIL_EDGE = "#E2DCCF"     # 导航右侧 1px 边线（与画布分隔）

# 主色（墨）
PRIMARY = "#22262B"
PRIMARY_HOVER = "#171B1F"
PRIMARY_ACTIVE = "#0E1114"
PRIMARY_SOFT = "#ECEAE4"  # 墨色浅底（选中态、标签）

# 强调色（朱印）——仅用于品牌标记、主操作、失效计数
ACCENT = "#B03A2E"
ACCENT_HOVER = "#973124"
ACCENT_ACTIVE = "#7C281D"
ACCENT_SOFT = "#F7E9E6"   # 朱印浅底

# 文本
INK = "#2B2F35"           # 主文本
INK_STRONG = "#181B1F"    # 标题文本
MUTED = "#6E6A5F"         # 次文本
MUTED_LIGHT = "#9C957F"   # 三级文本 / 占位符

# 边框
BORDER = "#E2DCCF"        # 常规边框
BORDER_STRONG = "#C9C0AC"  # 聚焦态边框（须深于常规边框，聚焦环才可见）
DIVIDER = "#EDE8DE"       # 细分隔线

# 语义色（降饱和）
SUCCESS = "#3F7A4E"
SUCCESS_HOVER = "#356843"
SUCCESS_ACTIVE = "#2A5436"
SUCCESS_SOFT = "#E9F0EA"
WARNING = "#A87A16"
WARNING_HOVER = "#8C6512"
WARNING_ACTIVE = "#6F5010"
WARNING_SOFT = "#F7EFDD"
DANGER = "#A8443C"
DANGER_HOVER = "#8E3831"
DANGER_ACTIVE = "#722C27"
DANGER_SOFT = "#F7E7E5"
INFO = "#4A6E8A"
INFO_HOVER = "#3D5B73"
INFO_ACTIVE = "#31495C"
INFO_SOFT = "#E8EEF3"

# 禁用态
DISABLED_BG = "#DCD7CA"
DISABLED_FG = "#F4F1EA"

# 顶栏
TOPBAR_BG = SURFACE
TOPBAR_FG = INK_STRONG
TOPBAR_SUB = MUTED

# 表格（只留横向细线：无竖线、无斑马纹）
STRIPE = SURFACE          # 不使用斑马纹（与 SURFACE 同色即无条纹）
TREE_HEAD_BG = "#F5F2EA"  # 表头纸底

# 代码 / 日志区
CODE_BG = "#F7F5EF"

# 面板标题带（通栏浅标题带 + 底部 1px 细线）
PANEL_BAND_BG = "#F5F2EA"
PANEL_BAND_LINE = "#E2DCCF"

# ---- 间距与形状规范（供界面装配引用，避免散落魔数） -----------------------
SPACE_XS = 4    # 紧凑间距（图标与文字、芯片内）
SPACE_SM = 8    # 小间距（同行控件）
SPACE_MD = 12   # 中间距（分区内）
SPACE_LG = 16   # 大间距（面板内边距纵向）
SPACE_XL = 20   # 面板之间
PANEL_PAD_X = 18   # 面板左右内边距
PANEL_PAD_Y = 14   # 面板标题带纵向内边距
RAIL_W = 236       # 左侧导航宽度
BAND_H = 46        # 面板标题带高度

# ---- 配色方案（可切换的视觉主题）----------------------------------------
# 「切换配色」循环切换三套完整配色：宣纸·墨黛（默认）+ 黛蓝·琥珀 + 陶红·亚麻。
# 旧默认「青瓷·赭石」随本轮视觉重构整体退场（其色相族与造型语言均被替换）。
PALETTES = {
    "宣纸·墨黛": {},
    "黛蓝·琥珀": {
        "PRIMARY": "#2E4F7A", "PRIMARY_HOVER": "#244066",
        "PRIMARY_ACTIVE": "#1B3050", "PRIMARY_SOFT": "#E3EAF3",
        "ACCENT": "#B4813A", "ACCENT_HOVER": "#97682C",
        "ACCENT_ACTIVE": "#7A5322", "ACCENT_SOFT": "#F6EEE1",
        "RAIL": "#22364F", "RAIL_HOVER": "#2A4260", "RAIL_ACTIVE": "#2F4C6C",
        "RAIL_LINE": "#3A5C82", "RAIL_EDGE": "#22364F",
        "RAIL_FG": "#E6ECF4", "RAIL_FG_DIM": "#9DAEC4",
        "RAIL_ACTIVE_FG": "#FFFFFF",
        "BG": "#EEF1F5", "SURFACE_ALT": "#F7F9FB", "SURFACE_SUNK": "#E3E8EE",
        "BORDER": "#D3DAE2", "BORDER_STRONG": "#B9C3CE", "DIVIDER": "#E5EAF0",
        "PANEL_BAND_BG": "#EDF1F6", "PANEL_BAND_LINE": "#D3DAE2",
        "STRIPE": "#F7F9FB", "TREE_HEAD_BG": "#E6EBF2",
        "DISABLED_BG": "#C9D2DD", "DISABLED_FG": "#EFF3F8",
    },
    "陶红·亚麻": {
        "PRIMARY": "#9C4A38", "PRIMARY_HOVER": "#843D2E",
        "PRIMARY_ACTIVE": "#6B3125", "PRIMARY_SOFT": "#F5E7E2",
        "ACCENT": "#4E6E52", "ACCENT_HOVER": "#3F5B44",
        "ACCENT_ACTIVE": "#324A37", "ACCENT_SOFT": "#E7EEE8",
        "RAIL": "#4A2A22", "RAIL_HOVER": "#57332A", "RAIL_ACTIVE": "#65382D",
        "RAIL_LINE": "#7C4A3B", "RAIL_EDGE": "#4A2A22",
        "RAIL_FG": "#F2E8E2", "RAIL_FG_DIM": "#C4A99B",
        "RAIL_ACTIVE_FG": "#FFFFFF",
        "BG": "#F5F1EA", "SURFACE_ALT": "#FBF8F2", "SURFACE_SUNK": "#EAE3D6",
        "BORDER": "#DDD2C0", "BORDER_STRONG": "#C7B9A3", "DIVIDER": "#EDE6D8",
        "PANEL_BAND_BG": "#F3EEE3", "PANEL_BAND_LINE": "#DDD2C0",
        "STRIPE": "#FBF8F2", "TREE_HEAD_BG": "#EFE8DA",
        "DISABLED_BG": "#D8CDBB", "DISABLED_FG": "#F6F1E8",
    },
}
DEFAULT_PALETTE = "宣纸·墨黛"

# 运行期当前配色方案名（供界面显示与持久化）
CURRENT_PALETTE = DEFAULT_PALETTE
# 被覆盖的基线值，供切换配色时还原
_BASE_COLORS = {
    "PRIMARY": PRIMARY, "PRIMARY_HOVER": PRIMARY_HOVER,
    "PRIMARY_ACTIVE": PRIMARY_ACTIVE, "PRIMARY_SOFT": PRIMARY_SOFT,
    "ACCENT": ACCENT, "ACCENT_HOVER": ACCENT_HOVER,
    "ACCENT_ACTIVE": ACCENT_ACTIVE, "ACCENT_SOFT": ACCENT_SOFT,
    "RAIL": RAIL, "RAIL_HOVER": RAIL_HOVER, "RAIL_ACTIVE": RAIL_ACTIVE,
    "RAIL_LINE": RAIL_LINE, "RAIL_EDGE": RAIL_EDGE,
    "RAIL_FG": RAIL_FG, "RAIL_FG_DIM": RAIL_FG_DIM,
    "RAIL_ACTIVE_FG": RAIL_ACTIVE_FG,
    "BG": BG, "SURFACE_ALT": SURFACE_ALT, "SURFACE_SUNK": SURFACE_SUNK,
    "BORDER": BORDER, "BORDER_STRONG": BORDER_STRONG, "DIVIDER": DIVIDER,
    "PANEL_BAND_BG": PANEL_BAND_BG, "PANEL_BAND_LINE": PANEL_BAND_LINE,
    "STRIPE": STRIPE, "TREE_HEAD_BG": TREE_HEAD_BG,
    "DISABLED_BG": DISABLED_BG, "DISABLED_FG": DISABLED_FG,
}

# ---- 字体 ---------------------------------------------------------------
_FONT_CANDIDATES = ("Microsoft YaHei UI", "Microsoft YaHei", "PingFang SC",
                    "Noto Sans CJK SC", "Source Han Sans SC", "Segoe UI", "Arial")
_MONO_CANDIDATES = ("Cascadia Mono", "Consolas", "DejaVu Sans Mono",
                    "Sarasa Mono SC", "Courier New")


def _pick(candidates):
    """从候选字体中挑选系统实际安装的第一款；失败则退回候选末位。"""
    try:
        import tkinter.font as tkfont
        have = set(tkfont.families())
        for f in candidates:
            if f in have:
                return f
    except Exception:
        pass
    return candidates[-1]


FONT_FAMILY = _pick(_FONT_CANDIDATES)
MONO_FAMILY = _pick(_MONO_CANDIDATES)

# 字号阶梯（全局统一，避免散落的魔数）；层级以字重 + 字号 + 色彩三级表达
SIZE_DISPLAY = 17   # 顶栏页面标题
SIZE_TITLE = 12     # 面板标题（标题带内）
SIZE_SUBTITLE = 9   # 副标题 / 辅助说明
SIZE_BODY = 10      # 正文
SIZE_SMALL = 9      # 小字
SIZE_CHIP = 15      # 统计芯片数值
SIZE_MONO = 9       # 等宽正文
SIZE_MONO_LG = 10   # 等宽正文（大）


def font(size=SIZE_BODY, bold=False, mono=False):
    """统一字体工厂：返回 (字体名, 字号, 字形)。"""
    fam = MONO_FAMILY if mono else FONT_FAMILY
    return (fam, size, "bold" if bold else "normal")


def track(text, gap="\u2009"):
    """给短标签插入窄空格，近似字距（Tk 字体不支持 letter-spacing）。

    仅用于分组标题、眉头一类的短标签；长文本使用会破坏可读性。
    """
    return gap.join(text) if text else text


# ---- 图标助手 -----------------------------------------------------------

def ico(name, fg=PRIMARY, bg=SURFACE, size=20):
    """取得面板内的线性图标（带缓存）。"""
    return icons.icon(name, fg, bg, size)


def rail_ico(name, fg=RAIL_FG, bg=RAIL, size=18):
    """取得左侧导航栏图标。"""
    return icons.icon(name, fg, bg, size)


def btn_ico(name, bg=PRIMARY, size=17):
    """取得实底按钮上的白色图标。"""
    return icons.icon(name, "#FFFFFF", bg, size)


# ---- 样式应用 -----------------------------------------------------------

def apply_theme(style, root=None):
    """在给定 ttk.Style 上配置「宣纸·墨黛」全部命名样式，并把根背景设为 BG。"""
    global FONT_FAMILY, MONO_FAMILY, CURRENT_PALETTE
    FONT_FAMILY = _pick(_FONT_CANDIDATES)
    MONO_FAMILY = _pick(_MONO_CANDIDATES)
    _apply_palette(CURRENT_PALETTE)
    s = style

    # 基础容器
    s.configure("TFrame", background=BG)
    s.configure("App.TFrame", background=BG)
    s.configure("Surface.TFrame", background=SURFACE)
    s.configure("Alt.TFrame", background=SURFACE_ALT)
    s.configure("Sunk.TFrame", background=SURFACE_SUNK)

    # 标题与文本
    s.configure("PanelTitle.TLabel", background=SURFACE, foreground=INK_STRONG,
                font=font(SIZE_TITLE, bold=True))
    s.configure("PanelSub.TLabel", background=SURFACE, foreground=MUTED,
                font=font(SIZE_SUBTITLE))
    # 通栏浅标题带内的标题/副标题（纸底，与面板主体白底区分）
    s.configure("BandTitle.TLabel", background=PANEL_BAND_BG,
                foreground=INK_STRONG, font=font(SIZE_TITLE, bold=True))
    s.configure("BandSub.TLabel", background=PANEL_BAND_BG,
                foreground=MUTED, font=font(SIZE_SUBTITLE))
    s.configure("PageTitle.TLabel", background=TOPBAR_BG, foreground=TOPBAR_FG,
                font=font(SIZE_DISPLAY, bold=True))
    s.configure("PageSub.TLabel", background=TOPBAR_BG, foreground=TOPBAR_SUB,
                font=font(SIZE_SUBTITLE))
    s.configure("App.TLabel", background=SURFACE, foreground=INK,
                font=font(SIZE_BODY))
    s.configure("Alt.TLabel", background=SURFACE_ALT, foreground=INK,
                font=font(SIZE_BODY))
    s.configure("Muted.TLabel", background=SURFACE, foreground=MUTED,
                font=font(SIZE_SMALL))
    s.configure("MutedAlt.TLabel", background=SURFACE_ALT, foreground=MUTED,
                font=font(SIZE_SMALL))
    s.configure("Section.TLabel", background=SURFACE, foreground=INK,
                font=font(SIZE_SMALL, bold=True))
    s.configure("Metric.TLabel", background=SURFACE, foreground=PRIMARY,
                font=font(SIZE_CHIP, bold=True))
    s.configure("Code.TLabel", background=CODE_BG, foreground=MUTED,
                font=font(SIZE_MONO, mono=True))

    # 输入控件（凹陷纸底）
    s.configure("App.TEntry", fieldbackground=SURFACE_SUNK, foreground=INK,
                borderwidth=1, bordercolor=BORDER, lightcolor=BORDER,
                darkcolor=BORDER, insertcolor=INK, padding=7)
    s.map("App.TEntry",
          bordercolor=[("focus", BORDER_STRONG)],
          lightcolor=[("focus", BORDER_STRONG)],
          darkcolor=[("focus", BORDER_STRONG)])
    s.configure("App.TCombobox", fieldbackground=SURFACE_SUNK, foreground=INK,
                background=SURFACE, borderwidth=1, arrowcolor=PRIMARY,
                bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER,
                padding=5)
    s.map("App.TCombobox",
          bordercolor=[("focus", BORDER_STRONG)],
          fieldbackground=[("readonly", SURFACE_SUNK)])
    s.configure("App.TSpinbox", fieldbackground=SURFACE_SUNK, foreground=INK,
                background=SURFACE, borderwidth=1, arrowcolor=PRIMARY,
                bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER,
                padding=5)
    s.map("App.TSpinbox",
          bordercolor=[("focus", BORDER_STRONG)],
          fieldbackground=[("readonly", SURFACE_SUNK)])

    # 复选 / 单选
    s.configure("App.TCheckbutton", background=SURFACE, foreground=INK,
                font=font(SIZE_BODY), focuscolor=SURFACE)
    s.map("App.TCheckbutton",
          background=[("active", SURFACE)],
          foreground=[("disabled", MUTED_LIGHT)],
          indicatorcolor=[("selected", PRIMARY), ("!selected", "#D6D0C2")])
    s.configure("App.TRadiobutton", background=SURFACE, foreground=INK,
                font=font(SIZE_BODY), focuscolor=SURFACE)
    s.map("App.TRadiobutton",
          background=[("active", SURFACE)],
          foreground=[("disabled", MUTED_LIGHT)],
          indicatorcolor=[("selected", PRIMARY), ("!selected", "#D6D0C2")])

    # 角色按钮三档：实底墨色 / 1px 描边 / 纯文字链
    _button(s, "Primary.TButton", PRIMARY, PRIMARY_HOVER, PRIMARY_ACTIVE)
    _button(s, "Success.TButton", SUCCESS, SUCCESS_HOVER, SUCCESS_ACTIVE)
    _button(s, "Warning.TButton", WARNING, WARNING_HOVER, WARNING_ACTIVE)
    _button(s, "Danger.TButton", DANGER, DANGER_HOVER, DANGER_ACTIVE)
    _button(s, "Info.TButton", INFO, INFO_HOVER, INFO_ACTIVE)
    _button(s, "Accent.TButton", ACCENT, ACCENT_HOVER, ACCENT_ACTIVE)
    _outline_button(s, "Secondary.TButton", PRIMARY, SURFACE)
    _outline_button(s, "AccentOutline.TButton", ACCENT, SURFACE)
    _outline_button(s, "InfoOutline.TButton", INFO, SURFACE)
    _outline_button(s, "DangerOutline.TButton", DANGER, SURFACE)
    _ghost_button(s, "Ghost.TButton", INK, SURFACE)

    # 进度条
    s.configure("App.Horizontal.TProgressbar", background=PRIMARY,
                troughcolor=SURFACE_SUNK, bordercolor=SURFACE_SUNK,
                lightcolor=PRIMARY, darkcolor=PRIMARY,
                borderwidth=0, thickness=6)

    # 结果表格（只留横向细线：无竖线、无斑马纹）
    s.configure("App.Treeview", background=SURFACE, foreground=INK,
                fieldbackground=SURFACE, rowheight=30, borderwidth=1,
                bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER)
    # 表头：纸底 + 1px 底线（borderwidth=1 时 ttkbootstrap 只渲染底部细线）
    s.configure("App.Treeview.Heading", background=TREE_HEAD_BG,
                foreground=INK, font=font(SIZE_SMALL, bold=True),
                borderwidth=1, bordercolor=PANEL_BAND_LINE, relief="flat",
                padding=(8, 8))
    s.map("App.Treeview.Heading",
          background=[("active", _soft_tint(TREE_HEAD_BG))],
          foreground=[("active", INK_STRONG)])
    s.map("App.Treeview",
          background=[("selected", PRIMARY_SOFT)],
          foreground=[("selected", INK_STRONG)])

    # 笔记本（表格 / 文本）
    s.configure("App.TNotebook", background=BG, borderwidth=0, tabmargins=0)
    s.configure("App.TNotebook.Tab", background=BG, foreground=MUTED,
                font=font(SIZE_BODY), padding=(16, 7))
    s.map("App.TNotebook.Tab",
          background=[("selected", SURFACE), ("active", SURFACE_ALT)],
          foreground=[("selected", PRIMARY), ("active", INK)],
          font=[("selected", font(SIZE_BODY, bold=True))])

    # 滚动条
    s.configure("App.Vertical.TScrollbar", background=BORDER,
                troughcolor=BG, bordercolor=BG, arrowcolor=MUTED,
                borderwidth=0, arrowsize=13)
    s.map("App.Vertical.TScrollbar", background=[("active", BORDER_STRONG)])

    if root is not None:
        try:
            root.configure(background=BG)
        except Exception:
            pass


def _button(s, name, bg, hover, active):
    """实底角色按钮：平直、无圆角、无彩色投影。"""
    s.configure(name, background=bg, foreground="#FFFFFF",
                font=font(SIZE_BODY, bold=True), borderwidth=0,
                relief="flat", focusthickness=0, padding=(16, 9),
                anchor="center")
    s.map(name,
          background=[("active", hover), ("pressed", active),
                      ("disabled", DISABLED_BG)],
          foreground=[("disabled", DISABLED_FG)])


def _outline_button(s, name, color, bg=SURFACE):
    """描边角色按钮：1px 同色描边，悬停时填充极浅同色底。"""
    soft = _soft_tint(color)
    s.configure(name, background=bg, foreground=color,
                font=font(SIZE_BODY, bold=True), borderwidth=1,
                relief="solid", bordercolor=color, lightcolor=color,
                darkcolor=color, focusthickness=0, padding=(15, 8),
                anchor="center")
    s.map(name,
          background=[("active", soft), ("pressed", bg)],
          bordercolor=[("active", color)],
          foreground=[("disabled", MUTED_LIGHT)])


def _ghost_button(s, name, color, bg=SURFACE):
    """纯文字链按钮：无底无边，悬停时浮现极浅纸底并转为主色。"""
    s.configure(name, background=bg, foreground=color,
                font=font(SIZE_BODY), borderwidth=0, relief="flat",
                focusthickness=0, padding=(10, 7), anchor="center")
    s.map(name,
          background=[("active", SURFACE_ALT), ("pressed", bg)],
          foreground=[("active", PRIMARY), ("disabled", MUTED_LIGHT)])


def _soft_tint(color):
    """由主色推导出极浅同色底（用于描边按钮悬停态）。"""
    try:
        raw = color.lstrip("#")
        r, g, b = (int(raw[i:i + 2], 16) for i in (0, 2, 4))
        mix = lambda c: int(round(c * 0.12 + 255 * 0.88))
        return "#%02x%02x%02x" % (mix(r), mix(g), mix(b))
    except Exception:
        return SURFACE_ALT


def _apply_palette(name):
    """把指定配色方案写回模块级常量（基线值 + 方案覆盖）。"""
    global CURRENT_PALETTE
    CURRENT_PALETTE = name if name in PALETTES else DEFAULT_PALETTE
    overrides = PALETTES.get(CURRENT_PALETTE, {})
    for key, value in _BASE_COLORS.items():
        globals()[key] = overrides.get(key, _BASE_COLORS[key])


def palette_names():
    """列出全部可用配色方案名。"""
    return list(PALETTES.keys())


def set_palette(name):
    """切换配色方案；返回是否成功（未知名称不改变现状）。"""
    if name not in PALETTES:
        return False
    _apply_palette(name)
    return True


def next_palette():
    """循环切换到下一个配色方案，返回新方案名。"""
    names = palette_names()
    try:
        idx = names.index(CURRENT_PALETTE)
    except ValueError:
        idx = -1
    nxt = names[(idx + 1) % len(names)]
    set_palette(nxt)
    return nxt
