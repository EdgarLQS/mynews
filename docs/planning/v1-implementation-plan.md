---
title: mynews v1 热点收集器实施计划
doc_type: plan
status: current
implementation_status: in_progress
version: 1.0
created: 2026-08-02
updated: 2026-08-02
owner: project-maintainers
---

# mynews v1 热点收集器实施计划

## 目标与成功标准

实现一个 Python 3.12 + uv 本地命令行工具，从国内外 AI 与科技渠道收集热点线索；v1 优先模型、AI 编程工具、开发者平台及相关重大科技动态。系统严格回溯第一方原始信息，并将每次运行结果保存为可版本化的 JSON。

v1 成功要求：

- 手动运行默认收集最近 24 小时，也支持一天、七天和指定日期范围。
- 全局、子命令和脚本均提供中文 `--help`。
- 所有候选落盘；只有第一方证据通过程序复核的条目可标为 `verified`。
- 每次运行写独立 JSON，历史不覆盖；失败不得污染 `latest.json`。
- 所有来源可以单独 `probe`，实验来源失败不得伪装为正常。
- 提供每天北京时间 09:30 的 launchd 安装脚本，但不自动安装。
- 首次真实验收完成过去七天收集。

## v1 范围

### 包含

- CLI：`collect`、`probe` 与完整 help。
- 稳定 RSS/Atom/API、GitHub Release 和来源专用网页 Adapter。
- Hacker News 发现；知乎热榜和 Bloomberg 实验性探测。
- 国内外模型、平台、AI 编程工具、价格页和更新日志。
- 候选规范化、相关性过滤、热度排序和跨运行去重。
- 可配置 Codex CLI Verifier 和单次候选预算；v1 初始配置使用 `gpt-5.6-luna`、默认上限 30 条，不在领域逻辑中写死。
- JSON Run、latest、去重状态和价格快照。
- built-in 来源插件注册表和稳定的内部 SourcePlugin interface。

### 不包含

- UI、数据库、自动发布、内容创作工作台。
- 绕过登录、付费墙、robots 或验证码。
- Claude Code Adapter。
- 第三方 Python 包的动态插件加载；代码结构预留兼容 seam，正式 entry-point 协议推迟到后续版本。

## 实施阶段

### 阶段 0：文档治理与 AI 协作门禁（已完成）

- 建立 docs 总入口、计划、架构、功能矩阵、来源目录、JSON 契约、ADR 与 archive 机制。
- 以根 `AGENTS.md` 统一项目 AI 开发规则，`CLAUDE.md` 只负责 Claude Code 导入和入口说明。
- 建立 [项目验收规则](../testing/acceptance-rules.md) 和 Claude Code `/acceptance` 项目技能。
- 提供零依赖 `scripts/check_docs.py`，固定文档头、内部链接、JSON 示例和 AI 入口检查。

验收：文档头、内部链接和状态同步检查通过；技能 frontmatter 验证通过；运行时代码仍保持 Proposed。

#### 阶段 0 验收记录（2026-08-02）

结论：`PASS`。范围是文档治理、AI 项目规则、验收流程和文档检查脚本；基线为 `55a81bdd7bb15358aded95a910ba1a525e5fd6e2`。本结论不代表采集运行时代码已实现。

| 门禁 | 命令或检查 | 结果 |
| --- | --- | --- |
| G0 | Standards 与 Spec 双轴复核 `git diff --cached HEAD` | 初审问题已修正，复审无可行动问题 |
| G1 | `python3 scripts/check_docs.py` | 17 个 Markdown/AI 入口文件，0 个错误 |
| G1 | `git diff --cached --check HEAD` | 退出码 0 |
| G1-S | `quick_validate.py .claude/skills/acceptance` | `Skill is valid!` |
| 脚本 | `python3 scripts/check_docs.py --help` 与 Python 编译检查 | 退出码 0 |
| 脚本边界 | 从 `/tmp` 运行绝对脚本路径；测试不存在和非项目 `--root` | 有效项目退出码 0；无效参数退出码 2、中文错误且无 traceback |

G2 至 G7：本阶段没有采集运行时代码，按门禁矩阵不适用；不得据此上调任何 CLI、来源、核验、存储或定时功能状态。

### 阶段 1：工程骨架与契约

- [x] 建立 `pyproject.toml`、Python 3.12、uv、src layout、测试和质量检查。
- [x] 实现 `mynews --help`、`collect --help`、`probe --help` 与 `scripts/collect.sh --help`。
- [x] 定义 `CollectionRequest`、`Candidate`、`Evidence`、`NewsItem`、`SourceResult` 和 `RunReport`。
- [x] 先用 Pydantic 固定 JSON Schema，并写兼容性测试。

验收：CLI help 可执行；非法日期给出中文原因；Schema fixture 通过。

#### 阶段 1 功能验收记录（2026-08-02）

结论：`PASS`（G0–G4）。验收范围为当前分支相对 `main` 的全部提交和工作树变更；基线为
`main=8acafc2`，验收时工作树无未提交或未跟踪变更。本记录与完整证据见
[阶段 1 功能验收说明](../testing/phase1-functional-acceptance.md)。

本阶段完成工程骨架、CLI 参数契约和离线 JSON 模型兼容测试；当前分支另包含 CC Switch
官方 Release 的离线解析 Adapter 增量。两者都不代表来源采集运行时、Codex 核验、JSON
Store、真实网络或 launchd 已实现。

| 门禁 | 命令或检查 | 结果 |
| --- | --- | --- |
| G0 | Git 范围、功能矩阵、计划和当前状态核对 | 通过；无越界状态夸大 |
| G1 | `python3 scripts/check_docs.py` | 通过；17 个 Markdown 文件，0 个错误 |
| G1 | `git diff --check main...HEAD`、`git diff --check` | 通过 |
| G2 | `UV_CACHE_DIR=/tmp/mynews-uv-cache uv run ruff check .` | 通过 |
| G2 | `UV_CACHE_DIR=/tmp/mynews-uv-cache uv run mypy src` | 通过；6 个源文件无问题 |
| G3 | 受影响测试和 `UV_CACHE_DIR=/tmp/mynews-uv-cache uv run pytest` | 通过；30 passed，0 skipped |
| G4 | 全局/子命令/脚本 help、非法参数、退出码和 Schema fixture | 通过；help 为 0，非法参数为 2 |

G5、G6-S、G6-V、G7：本阶段没有执行；真实来源、Codex、存储和定时能力留给后续计划，不能据此标记为 Verified。

### 阶段 2：来源插件与原始采集

- 实现 SourcePlugin interface、built-in registry、共享 HTTP 客户端和来源隔离。
- 先接 Hacker News、CC Switch 官方 Changelog/Release、其他官方 Feed/GitHub Release，再接来源专用网页。
- 实现 `probe` 和来源健康状态。
- 所有响应设置超时、有限重试、User-Agent、并发上限和缓存头。

当前进展：阶段 2 的第一批稳定机器来源已完成：CC Switch 官方 GitHub Release、Hacker News
官方 API 和 Qwen 官方 RSS 均有独立 fixture、SourcePlugin 接线、结构化健康状态和真实
`probe --source` 证据。来源专用网页、其他未给出明确官方机器入口的来源，以及阶段 3/4
能力仍未实现。

#### 阶段 2 实现与真实 probe 记录（2026-08-02）

结论：`Implemented`；三个内置来源的 live probe 为 `Verified`。本阶段只输出原始候选和
健康快照，不执行阶段 3 的规范化、去重、JSON Store，也不执行阶段 4 的第一方核验。

| 门禁 | 实际命令/检查 | 结果 |
| --- | --- | --- |
| 离线 Adapter | `UV_CACHE_DIR=/tmp/mynews-uv-cache uv run pytest tests/test_cc_switch.py tests/test_http_client.py tests/test_sources.py tests/test_hacker_news.py tests/test_feed.py tests/test_cli_sources.py -q` | PASS；32 passed |
| 共享 HTTP/类型 | `uv run ruff check src tests`；`uv run mypy src` | PASS |
| CC Switch | `uv run mynews probe --source cc-switch` | Verified；healthy，退出码 0 |
| Hacker News | `uv run mynews probe --source hacker-news` | Verified；healthy，退出码 0 |
| Qwen RSS | `uv run mynews probe --source qwen` | Verified；healthy，退出码 0 |

live probe 输出中的 `fetched_count` 是探测窗口内实际读取的条目数，不是新闻真实性结论。

验收：每个 Adapter 有离线 fixture；实时 probe 如实给出状态。

### 阶段 3：规范化、去重与 JSON Store

- 规范 URL、时间、语言、来源角色和事件类型。
- 使用 URL、实体、标题、日期和内容指纹生成稳定事件键。
- 区分热度、相关性和真实性，不用单一分数代替。
- 原子写入 run JSON；仅完整或部分成功时更新 latest。
- 保存价格页规范化快照和 first_observed_at。

验收：一日/七日范围、跨日去重、原子写入和失败保护测试通过。

### 阶段 4：第一方证据核验

- 官方来源自身满足域名、正文和日期规则时直接核验。
- 按配置的候选预算和批大小调用 Codex Verifier；v1 初始默认最多处理排名前 30 条未核验线索。
- Codex 只返回结构化建议；程序再次校验 URL、官方域名、GitHub 组织和正文摘录。
- 无证据、不可访问、内容不匹配或代理失败均保持 `unverified` 并记录原因。

验收：伪造子域名、媒体转述、搜索摘要和坏 JSON 不能进入 verified。

### 阶段 5：脚本、定时模板与真实验收

- `scripts/collect.sh` 固定 cwd、uv、代理继承和日志位置。
- 提供 launchd plist 渲染、安装、状态和卸载脚本，不自动执行安装。
- 执行 `collect --days 7`，检查来源覆盖、去重和全部 verified 证据。

验收：`plutil -lint` 通过；七天结果满足 JSON Schema；每条 verified 均有可访问的第一方证据。

## 命令与语义

```bash
uv run mynews --help
uv run mynews collect
uv run mynews collect --days 7
uv run mynews collect --date 2026-08-02
uv run mynews collect --from 2026-07-27 --to 2026-08-02
uv run mynews probe
uv run mynews probe --source hacker-news
./scripts/collect.sh --help
```

- 默认窗口：运行时刻前 24 小时。
- 日期时区：`Asia/Shanghai`。
- 日期选择器互斥；`--from` 与 `--to` 必须同时提供。
- 退出码：`0` 完整成功，`3` 有可用 JSON 但部分失败，`1` 致命失败，`2` 参数错误。

## 验证命令

```bash
uv run pytest
uv run ruff check .
uv run mypy src
git diff --check
```

真实网络 probe 和七天回溯是独立验收门槛，不得用离线测试通过代替；本轮仅完成阶段 2
内置来源 probe，七天回溯留给阶段 5/后续流水线。
每个阶段开发完成后，按 [项目验收规则](../testing/acceptance-rules.md) 选择门禁并输出独立验收结论。

## 文档联动

- 每完成一个阶段，同步本计划、[功能矩阵](../product/feature-matrix.md) 和 [文档总览](../README.md)。
- CLI/JSON 变化同步 [JSON 数据契约](../reference/json-data-contract.md)。
- 来源变化同步 [信息来源目录](../reference/source-catalog.md)。
- seam、插件协议或核验门槛变化同步 [系统架构](../architecture/system-architecture.md)，必要时新增 ADR。
