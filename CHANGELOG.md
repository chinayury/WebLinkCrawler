# 变更日志（CHANGELOG）

>规则：仅追加，不修改历史记录。版本号严格对齐代码 `src/weblinkcrawler/__init__.py`。

## [v0.6.3] -2026-11-26

- 修复抓取重定向页面时的相对链接解析。页面跳转到其他目录后，导出的链接使用最终响应地址作为基准。

## [v0.6.2] -2026-11-25 ·许可同步核验与 logutil 补测

> 本条为**追加**小节，上方历史条目不作任何修改。版本号 v0.6.1 → v0.6.2（`pyproject.toml` 与 `src/weblinkcrawler/__init__.py` 同步递增）。

### 改进
- **许可同步核验（周期性合规项，六点全过、无需修改）**：LICENSE 官方原文（662 行 FSF 文本）/ NOTICE §13 网络服务条款 / pyproject `license = "AGPL-3.0-or-later"` + `license-files` 且无 License 分类器 / 全量 .py SPDX 头 / README 许可段逐字模板 / GitHub 仓库识别 AGPL-3.0。
- `logutil.py`（日志初始化）补入回归测试（幂等性/处理器构成/不向 root 传播，模块级 `_configured` 标志的进程隔离处理），全量 **74 项**通过（两遍连跑）。

### 兼容性说明
- `src/` **零改动**（仅新增测试）；产品行为、对外契约、构建元数据除版本号外不变。
- 验证：本机 `python -m compileall src tests` 全绿、`python -m unittest discover -s tests` 74 passed（两遍连跑）、CLI 冒烟通过；测试服务器容器内同口径全绿；CI 三平台全绿（发布前实测）。

## [v0.6.1] -2026-11-24 ·测试基建提速

> 本条为**追加**小节，上方历史条目不作任何修改。版本号 v0.6.0 → v0.6.1（`pyproject.toml` 与 `src/weblinkcrawler/__init__.py` 同步递增）。

### 改进
- 测试基建：端到端用例的引擎装配将 `anti_anti_crawl.request_strategy` 的 `interval` / `retries` / `retry_after_cap` 置零（仅影响计时与失败重试次数，不改变抓取/体检结果语义）；全量 70 项 **216s → 27s**。明确不采用「分组/标记跳过网络用例」方案——保留默认全量门禁覆盖面，快跑与门禁同一套用例。

### 兼容性说明
- `src/` **零改动**（仅 tests/ 装配逻辑）；产品行为、对外契约、构建元数据除版本号外不变。
- 验证：本机 `python -m compileall src tests` 全绿、`python -m unittest discover -s tests` 70 passed（27s）、CLI 冒烟通过；测试服务器容器内同口径全绿；CI 三平台全绿（发布前实测）。

## [v0.6.0] -2026-11-24 ·crawl --check-same-domain 外链过滤

> 本条为**追加**小节，上方历史条目不作任何修改。版本号 v0.5.0 → v0.6.0（`pyproject.toml` 与 `src/weblinkcrawler/__init__.py` 同步递增）。

### 新增
- **`crawl --check --check-same-domain`**：仅体检与起始 URL 同域的链接（复用 `crawler.same_domain`），外链不入体检范围；用于过滤 CDN/外链噪声、降低 cron/CI 告警误报。
- 新增端到端对偶用例（外链过滤 → 退出码 0 / 不过滤 → 退出码 1），全量 **70 项**通过。

### 兼容性说明
- `crawl --check` 不带新开关时行为不变（新增参数默认关闭）；`check` 子命令、GUI、引擎接口零改动。
- 验证：本机 `python -m compileall src tests` 全绿、`python -m unittest discover -s tests` 70 passed、CLI 冒烟通过；测试服务器容器内同口径全绿；CI 三平台全绿（发布前实测）。

## [v0.5.0] -2026-11-23 ·crawl --check 抓取即体检

> 本条为**追加**小节，上方历史条目不作任何修改。版本号 v0.4.5 → v0.5.0（`pyproject.toml` 与 `src/weblinkcrawler/__init__.py` 同步递增）。

### 新增
- **`weblinkcrawler crawl --check`**：抓取完成后对发现的链接做存活体检，单命令完成「抓取 + 体检」（对齐 lychee / linkchecker 的核心体验，面向巡检场景）；`--strict`（体检阶段 blocked（401/403/429）也计入失败判定）；退出码沿用 check 告警口径（dead/error → 1），可直接用于 cron / CI。
- 配套导出：`crawl --check --export` 同时产出抓取清册与体检结果（体检 JSON 含 `meta.source` 标注 "crawl --check"）。

### 改进
- 体检上报逻辑（输出/导出/退出码）合并为共用函数 `_check_and_report`（`check` 子命令与 `crawl --check` 单一来源，消除复制粘贴）；`_event_handler` 去除未使用参数。
- 新增端到端用例（fixture 含 RFC 2606 保留 TLD 外链 → NXDOMAIN → error → 退出码 1），全量 **67 项**通过。

### 兼容性说明
- 无参数启动 GUI、`--version` / `-h` 行为不变；`crawl` 不带 `--check` 时行为与 v0.4.5 逐字节一致（新增参数默认关闭）；`check` 子命令语义不变（仅内部重构为共用函数）。
- 验证：本机 `python -m compileall src tests` 全绿、`python -m unittest discover -s tests` 67 passed、CLI 冒烟通过；测试服务器容器内同口径全绿；CI 三平台全绿（发布前实测）。

## [v0.4.5] -2026-11-22 ·配置层回归面补齐

> 本条为**追加**小节，上方历史条目不作任何修改。版本号 v0.4.4 → v0.4.5（`pyproject.toml` 与 `src/weblinkcrawler/__init__.py` 同步递增）。

### 改进
- `config.py`（ConfigManager 配置层）此前零直接测试覆盖，新增 `tests/test_config.py`（9 项，临时目录、无网络）：增强配置加载迁移（部分文件 → 深合并补默认值并回写落盘）、`get_int` 非法值回退与 lo/hi 钳制、`get_bool`/`get_list` 强转与清洗、属性映射（max_depth 钳制/禁用归零/max_pages/concurrency/css_selector 剥空白）、`request_params` 六元组形状（动态 UA、代理类型映射与非法类型回退 http、Cookie 解析清洗、禁用反反爬时全默认）、文件类型映射读写回环。全量 **64 项**通过（两遍连跑）。
- 依赖双口径复扫：锁定清单与实装环境均 **0 漏洞**（连续五轮归零）。

### 兼容性说明
- 零实现变更（仅新增测试）；对外契约、行为、构建元数据除版本号外不变。
- 验证：本机 `python -m compileall src tests` 全绿、`python -m unittest discover -s tests` 64 passed（两遍连跑）、CLI 冒烟通过；测试服务器容器内同口径全绿；CI 三平台全绿（发布前实测）。

## [v0.4.4] -2026-11-21 ·持久层回归面补齐

> 本条为**追加**小节，上方历史条目不作任何修改。版本号 v0.4.3 → v0.4.4（`pyproject.toml` 与 `src/weblinkcrawler/__init__.py` 同步递增）。

### 改进
- `database.py`（SQLite WAL 持久层）此前零测试覆盖，新增 `tests/test_database.py`（4 项，临时文件库、无网络）：任务生命周期（pending/crawling/stopped 可续、done 不可续）、`add_links_bulk` 批量写入与 `links_for_task` 写入顺序、`visited_for_task` 去重、`add_checks_bulk` 落库 + 重开连接读回（WAL 持久性）、空批量 no-op。全量 **55 项**通过。
- 依赖双口径复扫：锁定清单与实装环境均 **0 漏洞**（连续四轮归零）。

### 兼容性说明
- 零实现变更（仅新增测试）；对外契约、行为、构建元数据除版本号外不变。
- 验证：本机 `python -m compileall src tests` 全绿、`python -m unittest discover -s tests` 55 passed、CLI 冒烟通过；测试服务器容器内同口径全绿；CI 三平台全绿（发布前实测）。

## [v0.4.3] -2026-11-20 ·例行复扫与对标信号确认

> 本条为**追加**小节，上方历史条目不作任何修改。版本号 v0.4.2 → v0.4.3（`pyproject.toml` 与 `src/weblinkcrawler/__init__.py` 同步递增）。

### 改进
- 依赖双口径复扫：锁定清单与实装环境均 **0 漏洞**（连续三轮归零）；对标项目无新增可借鉴信号（lychee 稳定版未变、linkchecker 无更新、LibreCrawl 结论不变），决策记录见 `docs/06` §12。
- 测试服务器容器内验证门槛常态化运行：本轮发布前容器内全量测试与 CLI 冒烟复验全绿。

### 兼容性说明
- `src/` **零改动**（除版本号）；对外契约、行为、构建元数据不变。
- 验证：本机 `python -m compileall src tests` 全绿、`python -m unittest discover -s tests` 51 passed、CLI 冒烟通过；测试服务器容器内同口径全绿；CI 三平台全绿（发布前实测）。

## [v0.4.2] -2026-11-19 ·CLI GUI 回退探测加固

> 本条为**追加**小节，上方历史条目不作任何修改。版本号 v0.4.1 → v0.4.2（`pyproject.toml` 与 `src/weblinkcrawler/__init__.py` 同步递增）。

### 修复
- **CLI 无子命令时的 tkinter 降级探测加固**：`python:3.12-slim` 等环境存在「tkinter 模块在、C 扩展 libtk8.6.so 缺失」的半损坏状态——旧实现只按 ImportError 文本匹配（`tkinter`/`_tkinter` 子串），该场景漏判导致裸 `ImportError: libtk8.6.so` 直接抛出。现改为启动 GUI 前显式 import 探测（`_tkinter_available()`，find_spec 判断不出此类损坏），命中即输出可操作提示并退出码 1。
- 该缺陷由测试服务器（python:3.12-slim 容器）全量测试捕获：51 项测试中 3 项 GUI 回退用例失败，修复后容器内全量复验 **51 项通过**。文档记录：docs/05 变更-20。

### 兼容性说明
- 仅 GUI 回退路径行为变化（此前为裸异常，现为友好提示 + 退出码 1）；无子命令启动 GUI、`--version` / `crawl` / `check` 语义不变。

## [v0.4.1] -2026-11-19 ·robots 解析/匹配测试面补齐

> 本条为**追加**小节，上方历史条目不作任何修改。版本号 v0.4.0 → v0.4.1（`pyproject.toml` 与 `src/weblinkcrawler/__init__.py` 同步递增）。

### 改进
- robots 解析循环从 `_robots()`（网络抓取方法）中提取为模块级纯函数 `_parse_robots_rules(text)`——**逐行逻辑等价，零行为变更**（分组选择/注释剥离/空 Disallow 跳过/Crawl-delay 容错/Allow-Disallow 二元组归一化）。
- 新增 `tests/test_robots.py`（11 项，无网络）：解析边界 5 组、`_robots_match_length` 通配与 `$` 锚定 3 组、预置缓存后 `robots_allows` RFC 9309 最长匹配优先集成 3 组——robots 这条 politeness/安全相关路径首次拥有独立回归保护。
- 依赖双口径复扫：锁定清单与实装环境均 **0 漏洞**（连续两轮归零）。

### 兼容性说明
- 重构为纯函数提取，`_robots()` 抓取流程与解析结果格式完全不变；对外契约零变更。
- 验证：`python -m compileall src tests` 全绿；`python -m unittest discover -s tests` **51 passed**；CLI `--version` / `check` 冒烟通过；CI 三平台全绿（发布前实测）。

## [v0.4.0] -2026-11-18 ·DNS 重绑定防护（连接层 IP 钉定）

> 本条为**追加**小节，上方历史条目不作任何修改。版本号 v0.3.2 → v0.4.0（`pyproject.toml` 与 `src/weblinkcrawler/__init__.py` 同步递增）。

### 新增（安全加固）
- **DNS 重绑定 TOCTOU 防护**（docs/04 §10 残余风险 1 处置完毕，F-03 余项收官）：连接层按「解析 + 私有地址判定一次完成」的 IP 建连——`security.resolve_pinned_ip`（IP 字面量/代理场景走原路；解析失败或私有地址未放行 → fail-closed）+ 钉定连接类（socket 直连校验过的 IP，`server_hostname` 保留原域名，SNI/证书校验语义与直连域名完全一致）；GUI 与 CLI（crawl/check）全部请求生效，无需任何配置。
- **fail-closed 口径不变**：解析失败、私有/回环地址（未显式放行内网）一律拒绝；拒绝在连接层发生时以连接错误语义上报（`NameResolutionError` 转译），链接分级为 error。
- **回归测试**：新增 `tests/test_pinning.py`（resolver 口径 4 组、钉定适配器挂载、以 `localhost` 端到端抓取 fixture 验证 socket 钉定路径、NXDOMAIN fail-closed → 退出码 1），全量 **40 项**通过。

### 边界说明（如实记录）
- 经代理（含系统环境代理）访问时，DNS 由代理侧解析，钉定不适用——重绑定风险转移给代理的解析器，与所有经代理的工具一致；引擎默认不主动配置代理（用户显式开启 `anti_anti_crawl.proxy` 时适用此边界）。
- 真站冒烟：直连模式下 resolver 返回 `www.itmsky.com → 8.146.211.19`，socket 连 IP、证书校验域名 → 200；过程与实施缺陷修正记录见 `docs/05` 变更-18、设计记录见 `docs/06` §10。

### 兼容性说明
- 对外契约不变：`crawler.py` 公开接口签名零变更；新增连接层行为对正常流量透明（Host/URL/SNI 语义不变）；内网站点开关（`network_policy.block_private_targets=false`）行为不变。
- 依赖零新增：钉定实现基于锁定的 urllib3 2.8.0 既有能力。
- 验证：`python -m compileall src tests` 全绿；`python -m unittest discover -s tests` 40 passed；CLI `--version` / `check` 冒烟通过；CI 三平台全绿（发布前实测）。

## [v0.3.2] -2026-11-18 ·CI 集成依赖漏洞扫描

> 本条为**追加**小节，上方历史条目不作任何修改。版本号 v0.3.1 → v0.3.2（`pyproject.toml` 与 `src/weblinkcrawler/__init__.py` 同步递增）。

### 改进
- **CI 新增「Security - dependency audit」步骤**（Linux 腿）：每次推送自动执行 `pip-audit -r requirements.txt --no-deps`，锁定清单有已知漏洞即红灯；依赖审计从维护轮手工执行升级为推送自动执行（借鉴 lychee / hydra 的 CI 安全扫描实践，决策记录见 `docs/06` §9）。
- 依赖双口径复扫：锁定清单 **0 漏洞**；实装环境全量审计归零（pip 26.1.2 → 26.3，PYSEC-2026-3721 修复）。

### 预研与记录
- DNS 重绑定 TOCTOU（docs/04 §10 残余风险）维持待排期：urllib3 2.8 `server_hostname` 可行路径已探明，实施需连接层改造 + 对抗性测试（明示取舍，非遗漏）。
- `docs/05` 追加变更-17；`docs/06` 追加 §9。

### 兼容性说明
- `src/` **零改动**：对外契约、CLI/GUI 行为、构建元数据除版本号外不变；本轮仅 CI 配置与文档。
- 验证：`python -m compileall src tests` 全绿；`python -m unittest discover -s tests` 21 passed；CLI `--version` / `check` 冒烟通过；CI 三平台全绿（发布前实测）。

## [v0.3.1] -2026-11-17 ·check 退出码语义（cron/CI 告警口径）

> 本条为**追加**小节，上方历史条目不作任何修改。版本号 v0.3.0 → v0.3.1（`pyproject.toml` 与 `src/weblinkcrawler/__init__.py` 同步递增）。

### 改进
- **`weblinkcrawler check` 退出码语义**（lychee / linkchecker 借鉴）：存在 **dead（断链）或 error（无法判定）**级链接时以退出码 **1** 结束（0 = 全部正常；ok / redirect / blocked 视为正常），可直接用于 cron / CI 告警判断；新增 `--strict` 开关将 blocked（401/403/429，常见为鉴权墙/反爬）也计入失败（默认放行以控制误报，与引擎把 999 类反爬码默认视为 ok 的口径一致）。请求异常仍以退出码 1 报告。`crawl` 语义不变（成功抓取即 0）。文档同步：README 命令行模式小节、docs/03 §10。
- 新增 fixture 用例 `/missing`（404 → dead → 退出码 1），全量测试 **21 项**通过。

### 预研与记录
- **DNS 重绑定 TOCTOU**（docs/04 §10 残余风险 1）：确认锁定依赖 urllib3 2.8.0 的 `HTTPSConnection` 支持 `server_hostname` 参数（按 IP 建连、SNI/证书校验保留域名的路径可行）；因需连接层改造与对抗性测试，维持待排期结论，预研结论已回写 docs/04。
- 依赖双口径复扫：锁定清单 pip-audit **0 漏洞**；实装环境经上轮 S-14 恢复后无新漂移（pillow 13.0.0 与锁定一致）。

### 兼容性说明
- `src/` 仅 `cli.py` 一处行为变更，且 `check` 为上一版（v0.3.0）新增的子命令——不存在历史行为契约变更；GUI、引擎、配置、导出格式零改动。
- 验证：`python -m compileall src tests` 全绿；`python -m unittest discover -s tests` 21 passed；CLI `--version` / `check` 冒烟通过。

## [v0.3.0] -2026-11-17 ·无头 CLI 抓取与体检模式（crawl / check 子命令）

> 本条为**追加**小节，上方历史条目不作任何修改。版本号 v0.2.1 → v0.3.0（`pyproject.toml` 与 `src/weblinkcrawler/__init__.py` 同步递增）。

### 新增
- **CLI 无头子命令**（运维巡检 / 自动化场景；来源：四轮对标——linkchecker / lychee / hydra / LibreCrawl 均支持无 GUI 使用，本项目此前抓取与体检只能进 GUI，为最大借鉴缺口，决策链见 `docs/06` §7）：
  - `weblinkcrawler crawl <URL...>`：同域 BFS 下钻提取链接，`--depth` / `--max-pages` 内存覆盖（不回写配置文件），`--export PATH --fmt txt/csv/json` 导出；
  - `weblinkcrawler check <URL...>`：并发 HEAD 链接体检（与 GUI 同一分级策略），逐行 `状态\t状态码\tURL` 输出，可选导出；
  - 实现仅消费 `config` + `crawler` 核心引擎（不导入 tkinter、不持久化数据库）；进度事件走 stderr、结果走 stdout，便于脚本消费；安全策略与 GUI 完全一致（私有地址拦截、robots / Crawl-delay 尊重）。
- **无头端到端测试**：`tests/test_cli_headless.py`（本地 HTTP fixture，无外网依赖；覆盖 crawl 导出、depth 覆盖生效、check 状态与导出、无子命令 GUI 路径回退；CI tkinter 环境自动跳过 GUI 路径用例）。

### 改进
- `README` 快速启动新增「命令行模式」小节；`docs/03` 新增 §10（子命令参数表与行为要点，原相关文档节顺延为 §11）；`docs/05` 追加 S-14 / 变更-15；`docs/06` 追加 §7。

### 兼容性说明
- 无参数启动 GUI、`--version` / `-h` 行为逐字节不变；`crawler.py` 公开接口零改动；新增子命令全部默认值与 GUI 配置同源。
- 本机验证：`python -m compileall src tests` 全绿；`python -m unittest discover -s tests` **20 passed**（含本地 fixture 端到端实爬）；CLI `crawl` / `check` / `--version` 冒烟通过；CI 三平台 × 双版本全绿（发布前实测）。

## [v0.2.1] -2026-11-15 ·第三轮维护循环（轻量轮：调研与复扫记录）

> 本条为**追加**小节，上方历史条目不作任何修改。版本号 v0.2.0 → v0.2.1（`pyproject.toml` 与 `src/weblinkcrawler/__init__.py` 同步递增）。

### 改进
- `docs/06` 追加第三轮调研记录（§6）：LibreCrawl（1114★，Web 多租户架构）与 crawlee-python（9674★，autoscaled 并发池）逐条对照——JS 渲染 / SEO 分析 / XLSX 导出 / 动态并发均判定为不同轴、不同形态或依赖红线内不采纳，无新增落地项；**robots Crawl-delay 尊重**经本轮复核确认为已有等价能力（per-host 节流融合、等待可被 stop 打断）。
- 依赖双口径复扫：锁定清单 pip-audit **0 漏洞**、锁定不变；实装环境与上轮一致、无新漂移。
- `docs/05` 追加变更-14（轻量轮记录）；0 开放 Issues，CI/Release 全绿。

### 代码影响
- `src/` 与 CI 配置**零改动**：对外契约、GUI 行为、构建元数据除版本号外不变；本轮仅文档与版本号递增。
- 验证：`python -m compileall src tests` 全绿；`python -m unittest discover -s tests` 15 passed；CLI `--version` 冒烟通过。

## [v0.2.0] -2026-11-15 ·支持下限提升至 Python 3.12 与 CI 声明范围验证

> 本条为**追加**小节，上方历史条目不作任何修改。版本号 v0.1.1 → **v0.2.0**（`pyproject.toml` 与 `src/weblinkcrawler/__init__.py` 同步递增）。

### 破坏性变更（兼容性说明）
- **Python 支持下限由 3.10 提升至 3.12**（`requires-python >=3.12`；classifiers 移除 3.10/3.11）。原因：锁定清单中 soupsieve 4.0.0（CVE-2026-126190/126192 的最小全解版本）上游 `Requires-Python >=3.11.5`，与 3.10 声明矛盾（该矛盾由 CI 矩阵扩展至 3.10 时暴露）；3.10 已于 2026-10 EOL。pip 在 3.10/3.11 环境安装本项目将被明确拒绝。0.x 系列按 SemVer §4 以 minor 表达破坏性变更，1.0.0 留给 API 稳定里程碑；仓库当前零外部消费者，无实际迁移成本。完整决策链见 `docs/05-开发日志.md` 变更-12 / 变更-13 与 `docs/06-调研与借鉴.md` §5.3 / §5.4。

### 改进
- CI 矩阵由单一 Python 3.12 扩展为声明支持边界 `[3.12, 3.14]`（三平台 × 双版本，fail-fast 关闭；3.13 由本机 WorkBuddy 环境覆盖）；「版本与元数据」冒烟断言改为正则读取 `pyproject.toml`（移除 3.10 依赖的 `tomllib`）。
- 维护轮次新增「锁定清单 + 实装环境」双口径 pip-audit 审计：锁定清单 **0 漏洞**（无需变更）；实装环境漂移（共享解释器 pillow 11.3.0，D-01 同型）经评估维持共享环境现状，处置与取舍记录见 `docs/05-开发日志.md` S-13。
- `docs/06` 追加第二轮调研记录：新角度检索（broken-link-checker 2084★ / linkinator 1288★ / siteone-crawler 1008★ 等）经逐条对照均为不同语言或不同轴，无新增落地项；`docs/05` 追加 S-13 与变更-12/13。

### 代码影响
- `src/` **零改动**：对外契约、GUI 行为、配置/数据库格式完全不变；本轮变更仅涉及构建元数据（requires-python / classifiers）、CI 矩阵与文档。
- 验证：`python -m compileall src tests` 全绿；`python -m unittest discover -s tests` 15 passed；CLI `--version` 冒烟通过；CI 三平台 × 双版本全绿（发布前实测）。

## [v0.1.1] -2026-11-14 ·CLI 版本入口、核心测试套件入库与版本号单一来源收敛

> 本条为**追加**小节，上方历史条目不作任何修改。版本号 `v0.1.0` → `v0.1.1`（`pyproject.toml` 与 `src/weblinkcrawler/__init__.py` 同步递增）。

### 新增
- **CLI 版本入口**：新增 `src/weblinkcrawler/cli.py`，console script 与 `python -m weblinkcrawler` 共用；`--version` / `-h` 仅依赖包元数据、无需 tkinter 即可应答；无参数行为与历史逐字节一致（仍直接启动 GUI）。tkinter 缺失时输出可操作的安装提示并以退出码 1 结束（此前为 ImportError 回溯）。借鉴 linkchecker / lychee 的 CLI 实践，取舍依据见 `docs/06-调研与借鉴.md`。

### 改进
- **核心测试套件入库**：新增 `tests/test_core.py`（unittest，15 项，无网络无 tkinter）：版本元数据一致性（APP_VERSION ↔ pyproject 动态比对）、私有地址判定回归（CGNAT `100.64.0.0/10` F-02、IPv4-mapped 回环）、URL 归一化与去重键、CSV 公式注入中和（F-01）、导出格式回退；CI 新增 `python -m unittest discover -s tests` 步骤。
- **CI 版本断言去硬编码**：冒烟断言由 `APP_VERSION == '0.1.0'` 改为从 `pyproject.toml` 动态读取期望值，版本递增不再需要同步修改 CI（借鉴 lychee）。

### 修复/收敛
- **版本号硬编码清理**（单一来源收敛至 `pyproject.toml` + `__init__.py`）：docs 01–05 头部「文档版本」改为随代码版本表述；docs/03 界面描述改为 `v{APP_VERSION}` 动态表述；源码 docstring 与 requirements.txt 头部去版本化；历史性陈述（CHANGELOG、「已修复」记录）按仅追加原则保留。
- 修正失同步引用：`__init__.py` / `__main__.py` docstring 中「仓库根目录 WebLinkCrawler.py」不存在 → 改为指向真实入口 `weblinkcrawler.cli`；requirements.txt 头部指向不存在的「docs/安全审查报告-v0.1.0.md」→ 改为 `docs/04-安全设计说明.md`；crawler.py docstring 引用的 `tests/test_core.py` 此前未入库 → 本轮补齐。
- **历史遗留说明**：经核实，v0.1.0 条目引用的 `docs/视觉重构规格-v0.1.0.md`、`docs/同类项目借鉴清单-v0.1.0.md`、`tests/test_hardening.py`、`tests/test_integration.py` 未随仓库提交（仓库内不存在）；按「仅追加、不修改历史」原则保留原条目，本轮以 `docs/06-调研与借鉴.md` 与 `tests/test_core.py` 补齐同类能力。

### 兼容性说明
- 对外契约不变：`crawler.py` 公开接口、GUI 行为、配置/数据库格式零变更；新增 CLI 参数默认值与历史行为逐字节兼容。
- 本机验证：`python -m compileall src tests` 全绿；`python -m unittest discover -s tests` 15 passed；`weblinkcrawler --version` / `python -m weblinkcrawler --version` / `-h` / tkinter 缺失降级路径（退出码 1）实测通过。

## [v0.1.0] -2026-11-12 ·视觉体系三轮重构（「宣纸·墨黛」替代「青瓷·赭石」）

> 版本号仍锁定 `v0.1.0`；本轮仅替换视觉体系与图标，功能零变更、对外契约不变。

### 视觉体系三轮重构
- 主题更替为「**宣纸·墨黛**」（Rice Paper & Ink）：主色由青瓷绿改为中性墨 `#22262B`，强调色改为朱印 `#B03A2E`（仅用于品牌标记、主操作、失效计数）；画布 `#FAF8F3`、面板 `#FFFFFF`、凹陷 `#F1EEE6`；**去掉左侧深色导航栏**，改浅色纸底 `#F5F2EA` + 1px 右边线，激活项用 2px 朱红左杠 + 加粗文字。
- **造型语言双轴切换**：面板去掉「左侧色条 + 通栏标题带」，改「通栏浅标题带 + 底部 1px 细线」；按钮改「实底墨色 / 1px 描边 / 纯文字链」三档（新增 `Ghost.TButton` 文字链档）；表格只留横向细线（无竖线、无斑马纹，行高 30）。
- **配色方案**：固定 3 套循环（宣纸·墨黛 / 黛蓝·琥珀 / 陶红·亚麻），旧默认「青瓷·赭石」随本轮退场；两套旧方案补齐浅色导航文字令牌，切换后导航不再出现不可见文字。
- **图标风格全面换新**：由 2px 直角折线改为「墨线」——1.6/1.2/1.9px 三级笔宽、圆头圆角、24×24 网格 2px 内缩、圆角矩形 + 圆弧图元；图标 32 → **35 个**（新增 `seal` 品牌标记 / `refresh` 续爬 / `close` 取消全选）。
- **修复既有渲染缺陷**：`icons.photo()` 的 `PhotoImage.put` 传入扁平颜色列表，被 Tcl 解释为「多行纯色」，导致界面图标整体不显示（旧版同缺陷）；改为「行列表」结构并新增出墨回归断言。
- 语义色降饱和（成功 `#3F7A4E` / 警示 `#A87A16` / 危险 `#A8443C` / 信息 `#4A6E8A`），使五级链接状态色成为近单色画布上唯一高饱和信号。
- 规格与实现一一对应：`docs/视觉重构规格-v0.1.0.md`；问题闭环：`docs/开发日志.md`。

### 测试
- `tests/test_core.py` 新增 `VisualContractTests` 5 项（既有 32 个图标名契约、图标出墨回归、配色机制与令牌还原、纸墨基底令牌、新样式存在性）；`python -m pytest tests/test_core.py -q -p no:cacheprovider` → 22 passed；`tests/test_hardening.py tests/test_integration.py` → 28 passed，无回归。

### 本轮修订（v0.1.0 收官）：引擎 9 项借鉴点落地 + 配置加固 + 交付文档与门禁

> 本条为**追加**小节，上方视觉体系三轮重构与全部历史条目不作任何修改。版本号仍锁定 `v0.1.0`（`src/weblinkcrawler/__init__.py` `APP_VERSION = "0.1.0"`）。借鉴点编号口径见 `docs/同类项目借鉴清单-v0.1.0.md` 第四节（本轮采纳 9 项：A-01 / A-02 / B-01 / C-01 / C-03 / D-01 / E-01 / G-01 / G-02）。

**改动范围**：抓取引擎（请求节奏、体检分级、解析分层、连接兼容、去重口径）、配置体系、数据库、测试与文档；GUI 布局、菜单、页面结构与对外接口契约不变。

**受影响文件与详情**

- `src/weblinkcrawler/crawler.py`
  - **A-01**：HEAD 取到 405/501（403 为 opt-in）时回退一次**只读 GET**（`read_body=False`，不读 body、不新增线程），用 GET 的状态码重新分级；GET 自身失败保留原 HEAD 判定。消除「HEAD 被拒站点整站误报」。
  - **A-02**：「视为正常」状态码集合提为可配（`link_check.ok_status_codes`，默认 `[200,206,999]`），保留 2xx 基线且判定早于 3xx；state key 仍为五个，展示/导出零改动。
  - **B-01**：Content-Type 闸门，仅 `text/html` / `application/xhtml+xml` / `text/plain` 解析子链接，与文件大小/时限过滤分层，互不重复过滤。
  - **C-01**：per-host 请求节流，簿记由单一 `float` 改为 `{host: 下次可请求时刻}`；同一主机实际间隔在 `interval ~ 2×interval` 间随机，不同主机互不等待；等待在锁外按 ≤0.25s 切片，可被 stop 即时唤醒。
  - **C-03**：robots 按 root 做 in-flight 去重（同站一次在飞、跨站并行、全局一份缓存），缓存保持普通 dict + 256 上限 FIFO 淘汰，不引 LFU。
  - **D-01**：429/503/408 先按 Retry-After（纯数字或 HTTP 日期）或指数退避重试，统一按 `retry_after_cap`（默认 30s）封顶，次数用尽按失败处理且**不抽取错误页链接**；所有等待改为 `_stop_event.wait()`，停止即时生效。
  - **E-01**：遗留服务器 SSL 兼容适配器（`set_ciphers("DEFAULT:@SECLEVEL=1")`，失败回退 `DEFAULT`），**同时覆写 `init_poolmanager` 与 `proxy_manager_for`**；开关 `network_policy.ssl_compat_legacy_servers` 默认关闭，`verify=True` 与逐跳安全校验不变。
  - **G-01 / G-02**：归一化只做去重键——新增 `canonical_key()` 纯函数与 query 噪声参数黑白名单（黑名单 24 项、白名单 20 项，白名单优先）；抓取与 `_normalize_links` 同时维护「原始链接 + canonical key」双集合，导出与 `crawled_links.link` 一律写原始 URL。
- `src/weblinkcrawler/config.py`
  - 新增 `content_gate`、`link_check`、`dedup_query` 三个配置段，以及 `network_policy.ssl_compat_legacy_servers`、`anti_anti_crawl.request_strategy.retry_after_cap` 两个键；旧配置缺键由 `deep_merge` 自动补齐并回写。
  - `normalize_url()` 仅在输入确为「裸主机名/路径」时才补协议，`javascript:` / `data:` / `mailto:` 等伪协议不再被改写成畸形 `https://` 地址；新增主机名格式校验（IPv4 / 方括号 IPv6 / 域名）。
  - 新增 `throttle_interval()`，让 `request_strategy.interval` 同时承担正常请求节流职责（此前仅作重试退避基数）。
- `src/weblinkcrawler/database.py`
  - 新增 `link_checks` 表（体检结果）与 `idx_checks_task` 索引；旧库启动时自动补齐缺失列（表名/列名过标识符白名单）。
- `tests/`
  - 新增 `tests/test_v010_enhancements.py` **62 项**，按借鉴点分九类：`HeadFallbackTests` 9、`OkStatusCodesTests` 5、`ContentGateTests` 6、`PerHostThrottleTests` 6、`RobotsInflightTests` 4、`RetryAfterTests` 12、`SslCompatTests` 6、`CanonicalKeyTests` 12、`ConfigMigrationTests` 2；`tests/test_core.py` 增补 `VisualContractTests` 5 项。测试集现为 **112 项**（`test_core.py` 22 + `test_hardening.py` 10 + `test_integration.py` 18 + `test_v010_enhancements.py` 62，本次实测收集数）。
  - **门禁实测**：`python -m pytest tests/ -q -p no:cacheprovider` → **112 passed in 62.94s**（本次会话在项目根目录真实执行）。
- `docs/`
  - 新增 `docs/功能使用说明-v0.1.0.md`、`docs/环境部署教程-v0.1.0.md`、`docs/功能优化与新增日志-v0.1.0.md`、`docs/BUG修复清单-v0.1.0.md`，均依据最终代码逐行核对重写。
  - 说明：原 `docs/开发日志.md`（视觉重构 V-01~V-09 过程日志）已由文档工程师合并为 `docs/开发日志-v0.1.0.md`（增收引擎 Q-01~Q-11），本日志历史条目中出现的旧文件名即指向该文件。

**未纳入本轮（如实记录）**

- 借鉴清单「待排期」5 项未实现：C-02（per-host 间隔 UI 语义与覆盖表）、D-02（退避移出 worker 的延迟重入队）、F-01（JS 局部发现）、H-01（`crawled_pages` 唯一索引）、I-01（robots Sitemap 种子 + source 字段）。
- 借鉴清单「不采纳」6 项：R-01 ~ R-06。
- 落地方式与借鉴清单建议的偏差（以最终代码为准）：`retry_after_cap` 与 `ssl_compat_legacy_servers` **未进 GUI**，只能在 `enhanced_config.json` 维护；「请求策略」中「间隔(s)0~60」标签未改名为「每站点请求间隔」，但引擎侧节流已按主机生效。

**已知未修复安全项（详见 `docs/BUG修复清单-v0.1.0.md` 与 `docs/安全审查报告-v0.1.0.md`）**

- D-01（高）：运行环境 `urllib3` 2.7.0 落后于锁定清单 2.8.0（含 3 项已公开 PYSEC），处置命令 `python -m pip install -U "urllib3==2.8.0"`。
- F-01（中）CSV 公式注入、F-02（中）CGNAT `100.64.0.0/10` 漏网、F-03（中）DNS 解析失败即放行、F-06（低-中）配置驱动正则拒绝服务、F-07（低）ftp/sftp 零请求直接判可用、F-08（低）GUI 事件泵异常缺口、F-10（信息）`is_valid_url` 凭据分支为死代码。

**变更 / 不兼容**

- 新增配置键由 `deep_merge` 自动补齐，旧 `enhanced_config.json` 无需手工修改。
- 数据库新增 `link_checks` 表，旧 `crawling_progress.db` 可直接使用。
- `CrawlerEngine`、`ConfigManager`、`theme`、`icons` 对外名称与签名不变；GUI 页面结构、菜单、快捷键不变。

### 安全加固轮（v0.1.0 收官修订二：安全审查发现全量处置）

> 本条为**追加**小节，上方内容与全部历史条目不作任何修改。版本号仍锁定 `v0.1.0`。
> 依据：`docs/安全审查报告-v0.1.0.md` 发现清单（F-01 ~ F-12、D-01）；问题闭环记录见 `docs/开发日志-v0.1.0.md` 第五节（S-01 ~ S-10）。

**安全修复（源码）**

- `src/weblinkcrawler/security.py`
  - **F-02**：显式拦截 CGNAT `100.64.0.0/10`；IPv4-mapped IPv6（`::ffff:x.x.x.x`）按内层 IPv4 判定，堵住映射绕过。
  - **F-03**：`resolved_is_private` 三态化（True / False / None=解析失败），解析失败不再假称公网。
- `src/weblinkcrawler/crawler.py`
  - **F-01**：新增 `_csv_cell()` 公式注入中和（`=` `+` `- ` `@` 或制表/回车开头的单元格加单引号前缀），`_export_csv` 五个文本列全部过闸。
  - **F-03**：新增 `_host_is_blocked_private()`（字面 IP 零成本判定 + 域名 per-host 解析缓存 + fail-closed）；`_check_redirect_target` 改走该方法，解析失败一并拦截。
  - **F-04**：`_perform` 对所有抓取目标执行 `validate_target(..., allow_private=not block_private_targets)`。
  - **F-07**：ftp/sftp 体检由 `('ok', None)` 改为 `('error', 'ftp/sftp 协议不支持自动体检')`。
  - **F-09**：robots 读取/判定两处异常日志由 debug 升为 warning（fail-open 行为不变，留痕可见）。
- `src/weblinkcrawler/config.py`
  - **F-04**：`network_policy` 新增 `block_private_targets`（默认 **true**，内网站点置 false 放行）。
  - **F-06**：`excluded()` 正则改按 pattern 编译缓存（`_compiled_exclude`），保留 512 字符长度上限与 `re.error` 容错。
  - **F-10**：`is_valid_url` 文档字符串明确职责边界（语法校验；私有地址返回 True 为刻意设计；策略由引擎负责）。
- `src/weblinkcrawler/app.py`
  - **F-08**：`_poll_events` 单事件异常隔离（`log.exception` 留痕后继续排空，60ms 续跳不再被打断）。
- `src/weblinkcrawler/icons.py`
  - **F-12**：`icon()` 缓存键纳入当前默认 Tk 根对象，按根分区；单根产品行为不变（加固轮测试新发现）。

**配置与模板**

- `enhanced_config.example.json` 的 `network_policy` 增加 `block_private_targets` 占位键。

**测试**

- 新增 `tests/test_security_hardening.py` **23 项**（CSV 中和 3、私有网段 3、解析三态 4、目标策略 4、排除正则 3、ftp 1、职责边界 1、robots fail-open 1、事件泵隔离 1）。
- `tests/test_integration.py`、`tests/test_v010_enhancements.py` 的本地靶机按策略显式放行私有目标（与既有 `block_private_redirects` 测试处理一致）；`ConfigMigrationTests` 增补新键回填断言。
- **门禁实测**：`python -m pytest tests/ -q -p no:cacheprovider` → **135 passed**（原 112 + 新增 23；本轮复跑实测 `135 passed in 74.87s` 起，多次复跑均通过）。

**测试基础设施（F-13，加固轮测试执行中新发现）**

- 新增 `tests/conftest.py`：测试会话禁用 cyclic GC。修复全量运行约每 3 次一次的 Windows 致命崩溃
  （`code 0x80000003`，非主线程 cyclic GC 与 Tk 对象/线程创建竞争，崩溃点漂移、进程整体死亡）；
  引用计数回收为确定性路径，全部用例显式清理，禁用不影响任何用例判定与覆盖。
- `src/weblinkcrawler/icons.py` 新增 `_ALL_IMAGES` 强引用注册表：`photo()` 产出的每个 PhotoImage
  一律登记，产品侧杜绝「工作线程 GC 回收 Tk 对象」的同类致命路径（客户端进程内图标规模有界）。
- `test_integration.py` / `test_v010_enhancements.py` 的 `_Server` 增加 `block_on_close=False`、
  `_closing` 关闭标志与 teardown GC 暂停，收窄 socketserver 关闭竞态。
- 修复实证：处置后连续 7 次全量复跑 **135 全绿、零崩溃**。测试入口统一为 `python -m pytest tests/`
  （conftest 随之加载；直接运行单个测试文件时不加载，GC 未禁用属已知环境限制）。

**依赖（D-01，环境处置）**

- 运行环境 `urllib3` 2.7.0 → **2.8.0**（`python -m pip install urllib3==2.8.0`），与 `requirements.txt` 锁定一致，消除 3 项已公开 PYSEC；`pip-audit -r requirements.txt` 复扫 **0 漏洞**。整机扫描另报的 73 项经逐包核对均属工作区内其他项目的共享依赖，不在本项目依赖树（安全报告 §6.3 如实声明）。
- **2026-11-13 复扫新增（D-03）**：漏洞情报库更新后发现 `soupsieve` 2.9.2 新公开 2 项漏洞
  （CVE-2026-126190 / CVE-2026-126192），`requirements.txt` 锁定升级为 **4.0.0**（最小全解版本），
  运行环境与测试沙箱同步升级；bs4 选择器兼容冒烟通过、全量测试 135 项真实执行通过；
  复扫 `pip-audit -r requirements.txt` → **No known vulnerabilities found**。升级依据见安全报告 §6.5。

**文档**

- `docs/安全审查报告-v0.1.0.md` 增补第六节「安全加固轮修复记录」并更新发现清单状态（13 项发现全部处置，未修复清零）；`docs/BUG修复清单-v0.1.0.md`、`docs/功能优化与新增日志-v0.1.0.md`、`docs/开发日志-v0.1.0.md`、`docs/测试报告-v0.1.0.md`、`docs/风险台账-v0.1.0.md`、`docs/交付验收清单-v0.1.0.md`、`README.md`、`docs/项目介绍-v0.1.0.md` 同步对齐（测试数量 112 → 135）。

**残余风险（如实记录，见安全报告 §6.4 与风险台账）**

- DNS 重绑定 TOCTOU：校验与连接两次解析之间仍有窗口，彻底方案为按 IP 建连，列入待排期。
- 病态正则执行超时：512 字符内的灾难性回溯无语言级解法，建议后续引入 `re2`。
- F-05（SSL 兼容开关默认关）、F-09（robots fail-open）为明示的设计取舍。

## [v0.1.0] -2026-11-10 ·正式稳定版（二次修订：视觉二轮定版 + 安全加固）

> 本条目为 v0.1.0 的二次修订记录。版本号仍锁定 `v0.1.0`（`APP_VERSION = "0.1.0"`），
> 覆盖 2026-11-08 的首版内容；首版条目保留于下方，不作修改。

### 视觉体系二轮定版（替代初版「霜蓝·链接工坊」）
- 主题更名并重构为「**青瓷·赭石**」：主色 `#2F6F62`（青瓷绿）、强调 `#C2703A`（赭石）、画布 `#F1EFE7`（暖砂白）、导航栏 `#1F4A43`（深青瓷）。
- **版式重构**：由「顶栏 + 单列滚动卡片」改为「**左侧分组导航栏 + 右侧分页面板**」，四页：采集任务 / 结果总览 / 运行日志 / 系统配置。
- **配色方案系统**：新增 3 套完整配色（青瓷·赭石 / 黛蓝·琥珀 / 陶红·亚麻），修复「切换主题」无视觉效果的问题（BUG-02）。
- **图标扩充**：自绘线性图标由 24 个增至 **32 个**，新增 radar / pulse / rules / compass / grid / doc / spark / layers。
- **标题文案重设计**：6 个区块标题 + 副标题全部更新；新增「系统配置」页。
- 顶栏统计芯片新增「**失效**」计数；新增 `Ctrl+1/2/3` 页面切换快捷键。
- 全部为浅色主题，无暗色主题、无背景图。

### 引擎与健壮性修复
- **robots.txt 通配与 Allow 优先级**（BUG-03/04）：支持 `*` 通配、`$` 结束锚定，按 RFC 9309 最长匹配优先判定。
- **robots.txt SSRF 缺口**（BUG-05）：改为主进程手动跟随重定向并逐跳安全校验。
- **请求节流落地**（BUG-07）：`request_strategy.interval` 从「仅重试退避基数」改为「同时作为全局请求节流」，可被 stop 及时唤醒。
- **文件过滤并发化**（BUG-06）：由串行逐条 HEAD 改为线程池并发探测。

### URL 处理与校验
- **伪协议识别**（BUG-08）：`javascript:` / `data:` 等不再被改写为畸形 `https://` 地址。
- **主机名合法性校验**（BUG-09）：IPv4 / 方括号 IPv6 / 域名格式校验。
- **校验口径统一**（BUG-10）：`URL 验证` 与抓取路径统一先规范化再校验。

### 导入导出
- **多编码导入**（BUG-11）：URL 清单导入支持 UTF-8 / GBK / GB18030 / BIG5 / latin-1 自动识别。

### 安全
- **依赖升级**（SEC-01）：`pillow` 12.3.0 → **13.0.0**，消除 39 项已公开 CVE/PYSEC/GHSA；`pip-audit` 复扫 **0 漏洞**。
- **DDL 标识符白名单**（SEC-02）：表名 / 列名增加格式校验。
- **代理类型白名单**（SEC-03）：限定 http/https/socks4/socks5/socks5h。

### 测试
- 测试集由 33 项扩充至 **45 项**（单元 17 + 加固 11 + 集成 17），全部真实执行通过（`45 passed in 34.26s`）。

### 文档
- 全部 15 份交付文档依据最终代码重写，与 v0.1.0 代码逐项对齐。

## [v0.1.0] -2026-11-08 ·正式稳定版（版本纪元重置）

### 发布说明
-版本号强制锁定 **v0.1.0**；该编号为正式纪元起点，覆盖旧开发迭代 v0.1–v0.6编号。
-完整保留 v0.6功能：单/多 URL、筛选、文件类型编辑、深度抓取、反反爬、断点续爬、元素选择/CSS选择器、主题切换、导入导出。

### 新增
-全新「霜蓝·链接工坊」浅色视觉体系：顶栏、统计芯片、单列滚动卡片、角色化按钮、全套自绘线性图标；无暗色主题。
-结果表格化：编号 /链接 /类型 /协议 /深度 /状态，支持表头排序，保留兼容文本视图。
-链接体检：并发 HEAD，状态分级（可用/重定向/受限/失效/异常），结果入库。
-结构化导出：CSV / JSON（TXT保持旧版格式）。
-有界并发深度抓取（默认并发8）+最大抓取页数上限。
-排除规则（通配 /正则）。
-文件大小 /最后修改时间过滤真正接入抓取流程（HEAD元数据）。
-断点续爬入口与真实恢复：复用任务、跳过已访问页面、合并已有结果。
-网络安全策略：响应体上限、重定向上限、重定向内网拦截开关、Robots开关。
-统一日志文件与界面分级日志。
-完整交付文档与测试（详见 docs、docs-archive）。

### 修复
-旧配置缺键（如 `element_crawling`）导致启动 `KeyError`崩溃 →深合并迁移。
-子线程直接操作 Tk控件导致偶发崩溃 →事件队列 +主线程调度。
-强制 UTF-8解码导致中文站点乱码 →按响应头 / apparent_encoding智能解码。
-文件扩展名判断受查询参数影响 →按 URL path扩展名判断。
-数值输入非法导致崩溃 →统一范围校验与友好提示。
-停止任务被误标为 completed →正确标记 stopped，可续爬。
-抓取记录入库字段错位 →修正批量行字段顺序。
-页面无链接时 CSS选择器空结果误判 →回退整页。
- “暂停”实为停止、恢复即重跑 →协作式暂停/恢复。
- SQLite连接关闭不彻底、临时目录被占用 →连接生命周期收敛。
-关于窗口版本号与真实版本不一致 →统一读取 `APP_VERSION`。

### 安全
-手写重定向跟随，逐跳校验协议/主机/凭据/端口，阻止不安全跳转。
- URL凭据剥离；日志脱敏（不记录查询串中的令牌）。
-响应体大小上限，避免大文件/恶意页面耗尽内存。
-参数化 SQL，迁移语句仅使用内部常量。
-配置敏感文件权限收紧（POSIX0600；Windows由 ACL /忽略规则配合）。
-依赖版本锁定，安全审查报告见 `docs/安全审查报告-v0.1.0.md`。

### 变更 /不兼容
-代码由单文件拆分为 `src/weblinkcrawler`包；入口命令不变：`python WebLinkCrawler.py`。
-数据库沿用旧表结构并新增 `link_checks`，旧 `crawling_progress.db`可直接使用。
-主题切换仅在浅色主题间切换，不再提供暗色主题（按 v0.1.0视觉要求）。
-新增配置键自动补齐；旧 `enhanced_config.json`无需手工修改。

### 验证
-自动化测试：单元 +集成 +回归（见 `docs/测试报告-v0.1.0.md`）。
-测试在临时目录运行，不触碰真实生产数据库。
-具体执行结果以测试报告为准，未通过的项不会标记为通过。

---

## [v0.1.0] -2026-11-12 · 文档修订轮勘误（仅追加，不改写历史条目）

> 本小节为 2026-11-12 文档修订轮的统一勘误记录。按 AGENTS.md「CHANGELOG 只追加、不修改历史记录」规则，历史条目（含上文 2026-11-12 本轮条目）原文一律不动，勘误以本小节为准。

### 路径勘误
- **勘误 1（坏链）**：上文 2026-11-12 本轮条目「规格与实现一一对应：`docs/视觉重构规格-v0.1.0.md`；问题闭环：`docs/开发日志.md`」中的 `docs/开发日志.md` 已按归档要求合并删除并更名为 `docs/开发日志-v0.1.0.md`（改名映射见上文「文档」小节说明），该路径为**全库唯一坏链**，正确路径为 `docs/开发日志-v0.1.0.md`。实测 `grep -rln "开发日志\.md" --include="*.md"`（排除 `docs-archive`、`versions`）仅命中 5 个文件，其余 4 处均为「原 `docs/开发日志.md` 已合并删除」的历史说明文字，非坏链（`docs/风险台账-v0.1.0.md` E-03 已按此收窄）。

### 数字勘误
- **勘误 2（pillow 漏洞数）**：`requirements.txt:21` 注释与 `docs/项目介绍-v0.1.0.md` §8、`docs/需求规格-v0.1.0.md` §2.5 S1 原写「39 项」，实测 `python -m pip_audit -r <tmp>/pillow_1230.txt`（内容仅 `pillow==12.3.0`）→ **Found 40 known vulnerabilities in 1 package**（20 项 CVE + 19 项 PYSEC + 1 项 GHSA，修复版均为 13.0.0），已统一改为 40 项（本条目第 97 行「消除 39 项已公开 CVE/PYSEC/GHSA」为历史条目，按只追加规则保留原文）。
- **勘误 3（配色令牌数）**：`docs/视觉重构规格-v0.1.0.md` §7、`docs/版本迭代说明-v0.1.0.md` §3.7 原写两套旧配色「共 27 项」覆盖，实测 `len(theme._BASE_COLORS) == 28` 且 `PALETTES["黛蓝·琥珀"]` / `PALETTES["陶红·亚麻"]` 各覆盖 28 个键，已改为 28 项（= `_BASE_COLORS` 全部条目）。
- **勘误 4（交付文档数量）**：`docs/需求规格-v0.1.0.md` §7、`version_history.md` v0.1.0 条目原写「`docs/` 下 8 份 / 5 份文档」，实测 `docs/` 下共 **16 份** `.md`，已改为 16 份并补全列举。
- **勘误 5（绑定站点数）**：`docs/开发日志-v0.1.0.md` 变更-11、`docs/版本迭代说明-v0.1.0.md` §3 引言与 §4、`docs/交付验收清单-v0.1.0.md` §1.1 原写「25 处 `.bind()`/`add_command`/`accelerator`/`yscrollcommand`」，实测当前 `src/weblinkcrawler/app.py` 为 40 处（`.bind(` 22 + `add_command(` 9 + `accelerator` 2 + `yscrollcommand` 7；源码行口径同为 40 行），已统一改为 40 处；重构前 `app.py` 未随仓库留存，「25 处」无法复现（`versions/WebLinkCrawler_v0.6.py` 同口径 19 行）。
- **勘误 6（重试用尽后的处置）**：`docs/BUG修复清单-v0.1.0.md` Q-08、`docs/开发日志-v0.1.0.md` Q-08 原写「次数用尽按 blocked 记录且不抽链」，实测 `crawler.py:334-336` 次数用尽只 emit `[放弃重试]` 并 `return None`，调用方 `crawler.py:1328-1330` emit `[请求失败]` 并 `return target_url, []`，抓取路径不产生任何 check 记录，已改为「按失败处理（记 `[请求失败]` 日志、不抽链），不产生任何体检记录」。
- **勘误 7（节流簿记淘汰策略）**：`docs/开发日志-v0.1.0.md` Q-05、`docs/BUG修复清单-v0.1.0.md` Q-05、`docs/版本迭代说明-v0.1.0.md` §3.3、`docs/需求规格-v0.1.0.md` §4 原写「簿记超 4096 FIFO 淘汰」，实测 `crawler.py:596-602` 为容量超过 `_THROTTLE_MAX_HOSTS=4096` 时一次性弹出最旧的一半（2048 条，容量保护），已改为「超 4096 时丢弃最旧一半（容量保护）」。
- **勘误 8（配置项计数口径）**：`docs/环境部署教程-v0.1.0.md` §6.1 原写缺「五个键」，`docs/风险台账-v0.1.0.md` E-07 与 `docs/交付验收清单-v0.1.0.md` §1.3/§2.1 原写缺「14 个键」，实测缺的是 5 个配置项（`content_gate` / `link_check` / `dedup_query` 三段 + `retry_after_cap` + `ssl_compat_legacy_servers` 两键），按段名计入共 14 键、按叶子键计共 11 键，三处已统一为同一口径并注明基数。
- **勘误 9（截图产物数）**：`docs/交付验收清单-v0.1.0.md` §2.3 原写「`tests/_probe_*.png`、`tests/_shot.py` 产物（8 张）」，实测 `tests/` 下 `_probe_*.png` 仅 4 个文件，全部非 `_app_*.png` 的 PNG 合计 7 个，已改为 7 张并列名。
- **勘误 10（README 与归档漂移）**：`docs/风险台账-v0.1.0.md` E-01 与 `docs/交付验收清单-v0.1.0.md` §1.1 原把「README 与最终代码漂移」列为未修事项；实测 `README.md` 已于 2026-11-12 12:46:49 更新（`:7`「宣纸·墨黛」、`:74`「112 项用例」、`:95`/`:125`「35 个图标」），漂移已不存在，E-01 已按台账维护规则追加「已关闭」标注，验收清单漂移计数由 4 处改为 3 处（E-02/E-03/E-07）。
- **勘误 11（结项归档 README）**：`docs-archive/00-Executive/README-V0.1.0-20261112.md` 原为修复前内容（青瓷·赭石 / 45 项用例 / 32 个图标），已于本次文档修订轮以最终 `README.md` 覆盖；`00-Executive/CHANGELOG-V0.1.0-20261112.md` 与当前 `CHANGELOG.md` 逐字节一致。

### 未随本轮修订处置的事项（如实记录）
- `src/weblinkcrawler/icons.py:18` 模块 docstring 仍写「既有 32 个图标名全部保留（本轮新增 `seal` / `refresh`，共 34 个）」，实测 `icons.available()` 返回 35 项（含 `close`）；本轮任务范围限定为「只改文档、绝不改代码」，故该 docstring 未修正，5 份文档中的登记项（视觉重构规格 §0/§8.2、需求规格 A14、风险台账 E-02、version_history.md、BUG修复清单）继续有效。
- 交付包 `app_20261112_125520.zip` 内《交付验收清单》副本为 2026-11-12 12:52:56 快照（14264 字节，SHA-256 `e6f71727f7fc2423b2870734109ff8f4499ceef5bf1d1da6091217065cc4c7b1`），与仓库正式版不一致；本次修订又改动了多份仓库文档，交付前须按同一排除规则重新打包（详见 `docs/交付验收清单-v0.1.0.md` §2.4）。

---

## [v0.1.0] -2026-11-13 · 项目整理：纯代码 + 文档初始版本（非 Git 仓库）

> 本条为**追加**记录，上方全部历史条目不作任何修改。版本号仍锁定 `v0.1.0`（`src/weblinkcrawler/__init__.py` `APP_VERSION = "0.1.0"`）。
> 依据：通用指令「将项目整理为纯代码 + 文档的初始版本（非 Git 仓库）」。本初始版本按项目方要求**不含测试与归档**。

### 结构调整

- **新增 `src/weblinkcrawler/__main__.py`**：支持 `python -m weblinkcrawler` 启动，等价于原根目录 `WebLinkCrawler.py` 薄启动器，转发至 `weblinkcrawler.app:main`。
- **新增 `pyproject.toml`**：标准 src 布局（`package-dir = { "" = "src" }`），包名 `weblinkcrawler` 与包目录名一致；声明直接依赖、可选预览依赖（`[preview]`），并注册入口点 `weblinkcrawler = weblinkcrawler.app:main`。
- **新增 `LICENSE`**：MIT 许可证（与 README 声明一致）。
- **移除根目录薄启动器 `WebLinkCrawler.py`**：入口统一为 `python -m weblinkcrawler`（或 `pip install -e .` 后的 `weblinkcrawler` 命令），README 与各文档同步更新启动命令。
- **移除根目录重复文件**：`WebLinkCrawler (2).py`、`WebLinkCrawler (3).py` 为历史残留，非 v0.1.0 交付代码。

### 清理（移除冗余与缓存）

- **Git 相关**：`.gitignore`（本目录非 Git 仓库）。
- **工具状态**：`.playwright-mcp/`、`.pytest_cache/`、`.vcheck_tmp/`、`.zcode/`。
- **Python 缓存**：`__pycache__/`（根与包内）、`*.pyc`。
- **构建/交付包**：`app_20261108_221206.zip`、`app_20261113_191805.zip`、`dist/`。
- **运行产物**：`crawling_progress.db`、`debug.log`。
- **敏感配置**：`enhanced_config.json`、`file_type_config.json`（真实运行配置，可能含凭据；保留 `.example.json` 占位模板）。
- **未使用资源**：`link_scraper_gui.ico`（代码使用自绘图标，不引用此文件）、`screenshots/`。
- **测试与归档**：`tests/`、`docs-archive/`（按初始版本策略移除）。
- **历史版本**：`versions/`、`versions (2)/`。
- **根级文档**：`tool_introduction.md`、`version_history.md`（内容并入 `docs/` 五篇）。

### 文档重写（docs/ 五篇）

按通用指令第五节规范重写，删除重复/过时/与代码不符的旧文档（原 16 份 `-v0.1.0.md` 全部替换为以下 5 篇，内容以源码为准逐项核对）：

- `docs/01-项目介绍与架构.md`：项目概述、核心设计原则、模块结构、分层原则、技术选型。
- `docs/02-环境部署教程.md`：环境要求、安装方式、目录与文件、配置说明、启动方式、故障排查。
- `docs/03-功能使用说明.md`：各页面用法、对话框、导出格式、参数说明、已知限制。
- `docs/04-安全设计说明.md`：安全架构、鉴权、输入校验、凭据管理、路径防护、降级策略、依赖安全、审查发现处置。
- `docs/05-开发日志.md`：缺陷修复（现象→根因→解决方案 Q-01~Q-11、V-01~V-10、S-01~S-12）、版式变更记录、技术决策。

### 根文件更新

- **`README.md` 重写**：简介、特性、快速开始（入口改为 `python -m weblinkcrawler`）、目录结构、文档索引、视觉体系、数据与隐私、许可。
- **`CHANGELOG.md`**：本条追加，历史条目不动。

### 验证（真实执行）

- `import weblinkcrawler` 成功；`python -m weblinkcrawler` 入口可加载（GUI 主循环需交互环境，以导入与入口点可解析为验证口径）。
- `pyproject.toml` 入口点 `weblinkcrawler.app:main` 可导入。
- 核心功能（配置加载、URL 规范化、去重键、安全校验、链接提取）以模块级调用实跑通过。
- README 与 docs 中所有源码路径、模块名、命令与磁盘一致；版本号多处声明一致（`__init__.py` / `pyproject.toml` / README / docs 均为 v0.1.0）。

---

## [v0.1.0] -2026-11-13 · 许可信息统一（GPL-3.0-or-later）

> 本条为**追加**记录，上方全部历史条目不作任何修改。版本号仍锁定 `v0.1.0`。
> 说明：2026-11-13「项目整理」条目中的「新增 `LICENSE`：MIT 许可证」是当时状态的真实记录，按只追加规则保留；项目当前许可证为 GPL-3.0-or-later，以本条与 `LICENSE` 文件为准。

### 统一口径

- 开发者：智维ITMSKY
- 版权：Copyright (C) 2026 智维ITMSKY
- 官网：http://www.itmsky.com
- 许可证：GNU General Public License v3.0 or later（GPL-3.0-or-later）

### 改动

- `LICENSE`：在 GPL-3.0 正文前增加项目版权与授权声明，许可证正文未改动。
- `src/weblinkcrawler/__init__.py`：新增 `APP_COPYRIGHT` / `APP_LICENSE` / `APP_LICENSE_NAME` 常量，纳入 `__all__`。
- `src/weblinkcrawler/app.py`：关于窗口新增许可证行；开发者、版权行改用统一常量与全角冒号。
- `src/weblinkcrawler/*.py`（11 个）与 `packaging/*.py`：文件头统一增加 `Copyright (C) 2026 智维ITMSKY` 与 `SPDX-License-Identifier: GPL-3.0-or-later`。
- `pyproject.toml`：保持 PEP 639 `license = "GPL-3.0-or-later"` 与 `license-files = ["LICENSE"]`；未添加 License 分类器——`License-Expression` 与 License 分类器不能并存（setuptools>=77 会报 `InvalidConfigError`）。
- `README.md`：增加 GPL-3.0-or-later 许可证徽章。
- `docs/01-项目介绍与架构.md`：页首信息增加版权行，许可证写全称。
- `docs/02-环境部署教程.md`：两处目录树为 `LICENSE` 补许可注释。
- `docs/03-功能使用说明.md`：关于窗口描述同步许可证与版权行。
- `packaging/make_version_info.py`（新增）：从包常量生成 Windows 版本资源，避免版本号多处漂移。
- `packaging/version_info.txt`：构建时生成（已加入 `.gitignore`），写入 CompanyName / LegalCopyright / ProductName 等。
- `packaging/pyinstaller_desktop.py`、`.github/workflows/release.yml`：打包前生成版本资源并传 `--version-file`。
- `.github/workflows/ci.yml`：冒烟检查增加 `APP_LICENSE` / `APP_COPYRIGHT` 断言、wheel 内 LICENSE 存在性与 `License-Expression` 元数据断言。
- `.gitignore`：忽略生成的 `packaging/version_info.txt`。

### 验证（真实执行）

- `python -m compileall -q src/weblinkcrawler packaging` → 通过。
- `python packaging/make_version_info.py` → 生成成功；PyInstaller 6.22.3 `load_version_info_from_text_file()` 解析通过，filevers/prodvers `(0, 1, 0, 0)`，CompanyName `智维ITMSKY`，LegalCopyright `Copyright (C) 2026 智维ITMSKY`。
- `python -m build --outdir dist` → wheel/sdist 构建成功；wheel METADATA 为 `License-Expression: GPL-3.0-or-later`、`Author: 智维ITMSKY`，wheel 内含 `weblinkcrawler-0.1.0.dist-info/licenses/LICENSE`；sdist 内含 `weblinkcrawler-0.1.0/LICENSE`。

---

## [v0.1.0] -2026-11-13 · 许可证切换为 AGPL-3.0-or-later

> 本条为**追加**记录，上方全部历史条目不作任何修改。版本号仍锁定 `v0.1.0`。
> 说明：上一条「许可信息统一（GPL-3.0-or-later）」记录的是切换前状态，按只追加规则保留；项目当前许可证为 AGPL-3.0-or-later，以本条与 `LICENSE` 文件为准。

### 统一口径

- 开发者：智维ITMSKY
- 版权：Copyright (C) 2026 智维ITMSKY
- 官网：http://www.itmsky.com
- 许可证：GNU Affero General Public License v3.0 or later（AGPL-3.0-or-later，见 `LICENSE`）
- SPDX-License-Identifier: `AGPL-3.0-or-later`
- 网络服务条款：修改本程序并通过网络向公众提供服务（SaaS、Web、API 等）时，须向服务使用者提供对应修改后的完整源代码（AGPL 第 13 条）。

### 改动

- `LICENSE`：替换为 GNU AGPL-3.0 官方全文（含第 13 条 Remote Network Interaction），保留项目版权头并增加网络服务源码提供提示。
- `src/weblinkcrawler/__init__.py`：`APP_LICENSE` 改为 `AGPL-3.0-or-later`，`APP_LICENSE_NAME` 改为 `GNU Affero General Public License v3.0 or later`。
- 全部 11 个包模块与 `packaging/*.py`：SPDX 文件头改为 `AGPL-3.0-or-later`。
- `src/weblinkcrawler/app.py`：关于窗口经常量自动显示 AGPL 许可证名称与标识（无硬编码改动）。
- `pyproject.toml`：`license = "AGPL-3.0-or-later"`，`license-files = ["LICENSE"]` 不变。
- `README.md`：许可证徽章、目录树注释、「许可与信息」正文与 AGPL 网络服务提示同步。
- `docs/01-项目介绍与架构.md`：页首版权/许可证信息与 SPDX 标识同步。
- `docs/02-环境部署教程.md`：两处目录树注释改为 AGPL。
- `docs/03-功能使用说明.md`：关于窗口描述改为 AGPL。
- `.github/workflows/ci.yml`：许可证常量与 wheel 元数据断言改为 `AGPL-3.0-or-later`。

### 验证（真实执行）

- `python -m compileall -q src/weblinkcrawler packaging` → 通过。
- `python -m build --outdir dist` → wheel/sdist 构建成功；wheel METADATA 为 `License-Expression: AGPL-3.0-or-later`、`Author: 智维ITMSKY`；wheel 与 sdist 内的 `LICENSE` 均为 AGPL-3.0 全文且包含第 13 条；wheel 内 `__init__.py` 的 `APP_LICENSE` 为 `AGPL-3.0-or-later`。

---

## [v0.1.0] -2026-11-13 · 许可文件结构修正（恢复 GitHub 许可证识别）

> 本条为**追加**记录，上方全部历史条目不作任何修改。版本号仍锁定 `v0.1.0`。
> 原因：LICENSE 前置项目声明后，GitHub 自动识别结果为 `Other`；将版权声明移出 LICENSE 可恢复标准识别。

### 改动

- `LICENSE`：移除项目前言，恢复 GNU AGPL-3.0 官方原文，确保 GitHub 识别为 `AGPL-3.0`。
- `NOTICE`（新增）：承载项目版权、自由软件授权声明与 AGPL 第 13 条网络服务源码提供提示。
- `pyproject.toml`：`license-files = ["LICENSE", "NOTICE"]`。
- `.github/workflows/release.yml`：Windows 发布 zip 增加 `NOTICE`。
- `.github/workflows/ci.yml`：wheel 许可文件断言增加 `NOTICE`。
- `README.md`、`docs/02-环境部署教程.md`：目录树增加 `NOTICE`。

### 验证（真实执行）

- `python -m build --outdir dist` → 构建成功；wheel 的 `licenses/` 目录同时包含 `LICENSE` 与 `NOTICE`。
- wheel METADATA 保持 `License-Expression: AGPL-3.0-or-later`。
- 推送后通过 GitHub API 复核仓库 `license.key` 应为 `agpl-3.0`。

