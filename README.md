# WebLinkCrawler · 网页链接抓取工具

[![CI](https://github.com/chinayury/WebLinkCrawler/actions/workflows/ci.yml/badge.svg)](https://github.com/chinayury/WebLinkCrawler/actions/workflows/ci.yml)
[![License: AGPL-3.0-or-later](https://img.shields.io/badge/License-AGPL--3.0--or--later-blue.svg)](LICENSE)

> 桌面端网页链接提取、筛选、深度抓取与链接体检工具

WebLinkCrawler 是一款面向运维、内容整理与站点巡检场景的 Windows 桌面工具。输入一个或多个网址，即可提取页面中的链接，按文件类型、协议、关键词筛选，支持同域深度抓取、反反爬请求策略、断点续爬、CSS 元素区域限定、链接存活体检，以及 TXT / CSV / JSON 结构化导出。

本工具已进入正式稳定版，此前各轮开发迭代的功能全部保留。版本号只维护在代码与构建元数据中（`src/weblinkcrawler/__init__.py` 的 `APP_VERSION` 与 `pyproject.toml`），README 不展示具体版本。当前视觉体系为「**宣纸·墨黛**」（Rice Paper & Ink）。

## 核心能力

- **多目标抓取**：单 / 多 URL，支持导入（UTF-8 / GBK / GB18030 / BIG5 自动识别）、导出、格式校验与去重。
- **多维筛选**：单选 / 多选文件分类、HTTPS / HTTP、关键词（子串 / 正则）。
- **区域限定**：CSS 选择器限定抓取范围；PyQt5 网页预览点选（未安装时降级为 HTML 结构点选）。
- **深度抓取**：同域 BFS，0–5 级可配，有界并发（1–64）与最大页数上限（1–100000）。
- **请求策略**：动态 UA、HTTP / SOCKS5 代理、Cookie、per-host 请求节流 / 重试 / 超时与指数退避（429 / 503 / 408 支持 Retry-After）。
- **爬虫礼仪**：可选 robots.txt 遵循（`*` 通配、`$` 锚定、Allow 最长优先）与 Crawl-delay。
- **排除规则**：通配 / 正则，抓取阶段即过滤噪声链接。
- **文件过滤**：按 Content-Length（MB）与 Last-Modified（天）过滤，并发探测。
- **去重口径**：raw URL + canonical key 双轨制（导出入库一律写原始 URL）；query 噪声参数黑白名单，白名单优先保护真分页参数。
- **断点续爬**：SQLite 持久化任务与已访问页面，恢复时跳过已访问页面、合并已有结果。
- **链接体检**：并发 HEAD 校验（HEAD 被拒时回退只读 GET），五级分级（可用 / 重定向 / 受限 / 失效 / 异常），结果入库。
- **结构化导出**：TXT（兼容旧版式）、CSV（utf-8-sig，Excel 友好）、JSON（含元信息）。
- **安全边界**：协议 / 主机校验、逐跳重定向校验、私有地址拦截（含 CGNAT 网段与 IPv4-mapped IPv6，网段明细见 [docs/04-安全设计说明.md](docs/04-安全设计说明.md)；种子与页面链接默认拦截，`network_policy.block_private_targets` 可配置放行）、域名解析失败 fail-closed、响应体上限、导出 CSV 公式注入中和、参数化 SQL、DDL 标识符白名单、日志脱敏。

## 技术栈

| 层 | 选型 |
|---|---|
| 语言 | Python 3.12+ |
| GUI | Tkinter + ttkbootstrap |
| 网络 | requests（线程本地 Session，手动跟随重定向） |
| 解析 | beautifulsoup4（html.parser） |
| 存储 | sqlite3（WAL、参数化 SQL、单连接 + 锁） |
| 可选预览 | PyQt5 + PyQtWebEngine（独立子进程） |
| 代理 | PySocks |

依赖版本全部锁定，见 `requirements.txt`（含传递依赖）与 `requirements-preview.txt`（可选预览）；`pyproject.toml` 同步声明依赖与 `weblinkcrawler` 命令入口。

## 环境要求

- Windows 10/11（主支持），macOS / Linux 可运行
- Python **3.12+**
- 依赖见 `requirements.txt`（版本全部锁定）

## 快速启动

```bash
# 1. 安装依赖（建议虚拟环境）
python -m pip install -r requirements.txt

# 2a. 直接以模块方式启动（无需安装包）
python -m weblinkcrawler

# 2b. 或注册命令后启动
python -m pip install -e .
weblinkcrawler
```

首次启动会在当前工作目录生成 `enhanced_config.json`、`file_type_config.json` 与 `crawling_progress.db`（空库）。**建议从项目根目录启动**，以保持配置和数据库位置稳定。

### 命令行模式（无 GUI，运维巡检 / 自动化场景）

```bash
# 同域深度抓取提取链接（depth 为最大下钻深度）
weblinkcrawler crawl https://example.com --depth 2 --export links.json

# 链接存活体检
weblinkcrawler check https://example.com https://example.com/about --export checks.json
```

- 与 GUI 共用同一核心引擎与 `enhanced_config.json` 配置；配置生成于当前工作目录。
- 默认按安全策略拦截私有/回环地址（含 127.0.0.1）；需抓内网站点时在
  `enhanced_config.json` 将 `network_policy.block_private_targets` 置 `false`。
- 详细参数见 `weblinkcrawler crawl --help` / `weblinkcrawler check --help`。

### 可选：网页预览点选

真实浏览器点选需要 PyQt5 WebEngine：

```bash
python -m pip install -r requirements-preview.txt
# 或：python -m pip install -e ".[preview]"
```

未安装时，工具自动使用内置 HTML 结构预览，点击标签行即可提取 CSS 选择器，主要功能不受影响。

## 构建与发布

- **CI**（`.github/workflows/ci.yml`）：Ubuntu / Windows / macOS 三平台构建 wheel + sdist，并执行包元数据、核心模块、GUI 导入与 Tk 无头冒烟。
- **Release**（`.github/workflows/release.yml`）：推送 `v*` Tag 或手动触发后，产出 wheel、sdist 与 `WebLinkCrawler-<version>-Windows-x64.zip`（PyInstaller 单文件窗口版），随后清理旧 Release 附件与历史 Actions artifacts。
- 产物名中的 `<version>` 统一取自 `src/weblinkcrawler/__init__.py` 的 `APP_VERSION`。

## 目录结构

```
WebLinkCrawler-网页链接抓取/
├── src/
│   └── weblinkcrawler/        # 业务源码（11 个模块，6526 行）
│       ├── __init__.py        # 版本号与常量（唯一版本来源）
│       ├── __main__.py        # python -m weblinkcrawler 入口
│       ├── app.py             # GUI 组装与交互（2390 行：左导航 + 四页面板）
│       ├── crawler.py         # 抓取 / 体检 / 导出引擎（1792 行）
│       ├── config.py          # 配置合并、校验、URL 规范化（580 行）
│       ├── database.py        # SQLite 持久化（244 行）
│       ├── security.py        # 网络边界校验（94 行）
│       ├── preview.py         # 可选 PyQt5 元素选择进程（422 行）
│       ├── theme.py           # 视觉体系与 3 套配色方案（456 行）
│       ├── icons.py           # 自绘「墨线」线性图标，35 个（487 行）
│       └── logutil.py         # 分级日志（37 行）
├── packaging/
│   └── pyinstaller_desktop.py # PyInstaller 桌面版打包入口
├── .github/workflows/
│   ├── ci.yml                 # 三平台构建与冒烟
│   └── release.yml            # Tag 发布、产物上传与发布后清理
├── docs/                      # 交付文档（五篇）
│   ├── 01-项目介绍与架构.md
│   ├── 02-环境部署教程.md
│   ├── 03-功能使用说明.md
│   ├── 04-安全设计说明.md
│   └── 05-开发日志.md
├── pyproject.toml             # 构建配置（包名、依赖、入口点）
├── requirements.txt           # 锁定依赖清单
├── requirements-preview.txt   # 可选 PyQt5 预览依赖
├── enhanced_config.example.json   # 增强配置占位模板
├── file_type_config.example.json  # 文件类型映射占位模板
├── .gitignore                 # 运行产物与本地配置忽略规则
├── .dockerignore              # 容器构建忽略规则
├── CHANGELOG.md               # 变更日志（只追加）
├── README.md
├── NOTICE                     # 版权与授权声明
└── LICENSE                    # AGPL-3.0-or-later 全文
```

## 文档索引

| 文档 | 内容 |
|---|---|
| [docs/01-项目介绍与架构.md](docs/01-项目介绍与架构.md) | 项目概述、核心设计原则、模块结构、分层原则、技术选型 |
| [docs/02-环境部署教程.md](docs/02-环境部署教程.md) | 环境要求、安装方式、配置说明、启动方式、故障排查 |
| [docs/03-功能使用说明.md](docs/03-功能使用说明.md) | 各页面用法、对话框、导出格式、参数说明、已知限制 |
| [docs/04-安全设计说明.md](docs/04-安全设计说明.md) | 安全架构、输入校验、凭据管理、路径防护、降级策略、依赖安全 |
| [docs/05-开发日志.md](docs/05-开发日志.md) | 缺陷修复（现象→根因→解决方案）、功能新增、架构改进 |
| [CHANGELOG.md](CHANGELOG.md) | 变更日志（只追加，不修改历史） |

## 视觉体系说明

**「宣纸·墨黛」（Rice Paper & Ink）** —— 全浅色、无暗色主题、无背景图。

- **色相族**：近单色「墨」+ 单一「朱印」。主色中性墨 `#22262B`，强调色朱印 `#B03A2E` 仅用于品牌标记、每页唯一主操作按钮与失效计数；画布宣纸白 `#FAF8F3`、面板纯白 `#FFFFFF`、凹陷区 `#F1EEE6`。
- **导航**：浅色纸底 `#F5F2EA` + 右侧 1px 边线；激活项用 2px 朱红左杠 + 加粗文字表达；分组为「作业 / 观测 / 整备」。
- **面板**：通栏纸底标题带 + 底部 1px 细线，层级靠字重与字号表达。
- **按钮三档**：实底墨色 / 1px 描边 / 纯文字链（`Ghost.TButton`）。
- **表格**：只保留横向细线（无竖线、无斑马纹），行高 30。
- **语义色降饱和**：成功 `#3F7A4E` / 警示 `#A87A16` / 危险 `#A8443C` / 信息 `#4A6E8A`，使五级链接状态色成为近单色画布上唯一高饱和信号。
- **配色方案**：固定 3 套循环切换（宣纸·墨黛默认 / 黛蓝·琥珀 / 陶红·亚麻）。
- **图标**：35 个纯 Python 自绘「墨线」线性图标——1.6 / 1.2 / 1.9px 三级笔宽、圆头圆角、24×24 网格 2px 内缩、圆角容器；3×3 超采样软件光栅化，无第三方图像依赖。

## 数据与隐私

- `crawling_progress.db` 保存抓取任务、链接与体检结果，可能包含带查询参数的 URL，请按敏感数据管理。
- `enhanced_config.json` 可能保存代理、Cookie 等凭据，**禁止提交入库、禁止打入交付包**；交付时只保留 `enhanced_config.example.json` 占位模板。
- 日志文件默认 `weblinkcrawler.log`（URL 已脱敏），不在交付包内。
- 工具不上传任何数据；所有抓取由本机发起。

## 免责声明

本工具仅用于合法用途。请遵守目标站点服务条款、robots 协议与当地法律法规，勿用于未授权抓取、绕过访问控制或高频压测。

## 许可与信息
开发者：智维ITMSKY
版权：Copyright (C) 2026 智维ITMSKY
官网：http://www.itmsky.com
许可证：GNU Affero General Public License v3.0 or later（AGPL-3.0-or-later，见 LICENSE）
SPDX-License-Identifier: AGPL-3.0-or-later

> 本程序是自由软件：你可以遵照 GNU Affero 通用公共许可证第3版或后续版本的规定，重新分发和/或修改它。
> 本程序旨在广泛共享，但不提供任何担保；甚至不包含适销性和特定用途适用性的默示保证。详情请参阅 GNU Affero General Public License。
> 如果你修改本程序并通过网络向公众提供服务（SaaS、Web、API等在线服务），你必须向该服务的使用者提供对应修改后的完整源代码。
> 你应当随本程序一同收到 GNU Affero General Public License 的副本；如未收到，详见 <https://www.gnu.org/licenses/>。
