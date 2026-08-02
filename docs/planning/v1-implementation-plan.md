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
- 提供每天主机本地时间 09:30 的 launchd 安装脚本；采集进程使用 `TZ=Asia/Shanghai`，但不自动安装或修改系统时区。
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

结论：`Implemented`；三个内置来源均有 live probe 证据，最新 HN/Qwen 为 `healthy`，
CC Switch 最新一次为 HTTP 403 `blocked`。本阶段只输出原始候选和
健康快照，不执行阶段 3 的规范化、去重、JSON Store，也不执行阶段 4 的第一方核验。

| 门禁 | 实际命令/检查 | 结果 |
| --- | --- | --- |
| 离线 Adapter | `UV_CACHE_DIR=/tmp/mynews-uv-cache uv run pytest tests/test_cc_switch.py tests/test_http_client.py tests/test_sources.py tests/test_hacker_news.py tests/test_feed.py tests/test_cli_sources.py -q` | PASS；32 passed |
| 共享 HTTP/类型 | `uv run ruff check src tests`；`uv run mypy src` | PASS |
| CC Switch | `uv run mynews probe --source cc-switch` | 04:38 healthy；04:57 HTTP 403 blocked；05:03 重跑 healthy，退出码 0 |
| Hacker News | `uv run mynews probe --source hacker-news` | Verified；healthy，退出码 0；已触达 topstories 与 item endpoint |
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

#### 阶段 3 实现与离线验证记录（2026-08-02）

结论：`Implemented`。Normalizer、Deduplicator、JsonNewsStore 和 PipelineCollector 已接入
阶段 2 SourceCollector seam；实现只保留 `unverified`，没有 Codex 核验或真实价格来源。

| 能力 | 结果 |
| --- | --- |
| URL、时间、语言、来源角色、事件类型规范化 | 离线领域测试通过 |
| URL/实体/标题/日期/内容指纹事件键 | 稳定键与跨来源合并测试通过 |
| 一日、七日和指定日期范围 | CLI 日期契约复用并进入流水线请求 |
| 跨运行去重状态 | `state/dedup.json` 原子保存与恢复测试通过 |
| Run、latest、failed 保护 | 每次运行独立 JSON、原子替换和失败保护测试通过 |
| 通用价格快照 | `state/price_snapshots/<source-id>.json` 与 `first_observed_at` 测试通过；真实源未接入 |

本阶段门禁记录：

| 门禁 | 命令 | 结果 |
| --- | --- | --- |
| 测试 | `UV_CACHE_DIR=/tmp/mynews-uv-cache uv run pytest -q` | PASS；66 passed |
| 静态检查 | `UV_CACHE_DIR=/tmp/mynews-uv-cache uv run ruff check .` | PASS |
| 类型检查 | `UV_CACHE_DIR=/tmp/mynews-uv-cache uv run mypy src` | PASS；21 个源文件无问题 |
| 文档/差异 | `python3 scripts/check_docs.py`、`git diff --check` | PASS；18 个 Markdown 文件、0 个错误 |

### 阶段 4：第一方证据核验

- 官方来源自身满足域名、正文和日期规则时直接核验。
- 按配置的候选预算和批大小调用 Codex Verifier；v1 初始默认最多处理排名前 30 条未核验线索。
- Codex 只返回结构化建议；程序再次校验 URL、官方域名、GitHub 组织和正文摘录。
- 无证据、不可访问、内容不匹配或代理失败均保持 `unverified` 并记录原因。

验收：伪造子域名、媒体转述、搜索摘要和坏 JSON 不能进入 verified。

#### 阶段 4 实现与验收记录（2026-08-02）

结论：`Verified`。EvidenceVerifier、FakeVerifier 和 CodexVerifier 已接入
PipelineCollector；模型、预算、批大小和超时由 VerificationConfig 注入，计划默认模型
为 gpt-5.6-luna、预算为 30，默认值不写入领域层。Codex 子进程使用 ephemeral、
read-only、shell=False 和超时；Codex 只能产生结构化建议，程序重新抓取并检查最终 URL、
精确官方域名/GitHub 组织、摘录、日期和规范化正文哈希。

本次验收执行 G0、G1、G2、G3、G4、G5、G6-S、G6-V：文档检查 0 错误，受影响测试
37 passed，全量测试 81 passed；预算、批次、超时、坏结构化输出、失败恢复和历史
`latest.json` 保护均通过。伪造子域名、恶意重定向、非官方 GitHub 组织、媒体转述、
搜索摘要、正文不含摘录、日期不匹配和页面提示注入均保持 `unverified`。

G6-S：`uv run mynews probe --source cc-switch` 返回 `healthy`，`fetched_count=33`、
`accepted_count=33`，退出码 0。G6-V 使用真实 `codex-cli 0.144.1` 验证 Qwen
候选 `https://qwenlm.github.io/blog/qwen3guard/`；Codex 返回结构化建议，程序通过
真实 `SharedHttpClient` 重抓第一方页面，确认 URL、域名、摘录和正文哈希后判定
`verified`，证据校验 `reachable`、`official_domain`、`excerpt_matched` 均为 `true`。

人工复查确认页面正文包含摘录，页面日期为 `2025-09-23T04:00:00+08:00`，程序计算的
正文哈希为 `sha256:e16359e11609257b7206c77769f5b35a27451c3c43603a50e80bb77b2b969a09`。
当前日期校验按日历日匹配，尚未证明 `published_at` 的精确时间戳相等；阶段 5 的
launchd、真实价格源和七天回溯仍未实现或验收。

### 阶段 4.5：来源覆盖与价格监控（已完成实现）

- [x] 接入至少 3 个国内和 3 个国外第一方自动来源：Qwen、DeepSeek、TRAE，以及 OpenAI、
  Anthropic、Google Gemini；每个来源都有独立 fixture、registry/collect/probe 接线和结构化
  故障隔离。
- [x] 接入 OpenAI 官方开发者模型/价格更新页和 DeepSeek 官方模型与价格页；首次观察只保存
  `PriceSnapshot`，规范化 URL 或内容哈希变化后才生成 `pricing_change`，没有官方日期时
  `published_at` 保持 `null`。
- [x] 接入 `zhihu-hot` 和 `bloomberg-ai` 实验 Adapter，只读取公开标题、链接、日期等元数据；
  登录、付费墙、robots、验证码或没有公开卡片时如实返回 `blocked`，不绕过访问控制。
- [x] 保留已有 Hacker News、CC Switch 和 Qwen 来源；阶段 5 只提供需显式安装的定时模板，不做自动发布。

#### 阶段 4.5 离线与 live probe 记录（2026-08-02）

结论：离线能力为 `Implemented`，本次独立完整验收结论为 `FAIL`。离线 Adapter、registry
隔离、价格首观/差异和 discovery 保持 `unverified` 测试通过；真实 probe 的逐项命令、原始状态和访问限制见
[阶段 4.5 probe 证据](../testing/phase45-source-probe-evidence.md)。`healthy` 只表示入口和
解析器可用，不表示新闻已 `verified`。

OpenAI 原 `https://openai.com/news/` 与 `https://openai.com/api/pricing/` 首次 probe 返回
HTTP 403，已按“只能替换为同类官方来源”的要求改用官方
`https://developers.openai.com/api/docs/models` 模型/价格更新页，并记录为 `openai` 与
`openai-pricing` 的入口；没有使用媒体、搜索摘要或非官方 API。Anthropic 页面初次解析时
误把 `mailto:` 页脚识别为条目，已修复为跳过非官方卡片并以官方公开页级元数据回退，随后
probe healthy。

| 门禁 | 命令/证据 | 结果 |
| --- | --- | --- |
| TDD/Adapter | `UV_CACHE_DIR=/tmp/mynews-uv-cache uv run pytest tests/test_phase45_sources.py tests/test_sources.py tests/test_collector_pipeline.py -q` | 通过；阶段 4.5 来源、价格、隔离与既有流水线测试 |
| 来源 live probe | `uv run mynews probe --source <source-id>` 逐项执行 10 个阶段 4.5 来源 | OpenAI、Anthropic、Gemini、DeepSeek、TRAE、OpenAI pricing、DeepSeek pricing、Qwen 为 `healthy`；知乎/Bloomberg 为 `blocked`；原始 JSON 见证据文件 |
| 访问限制 | 同上，允许升级网络权限的只读 probe | 发现 HTTP 403 或没有公开元数据时退出码 1，健康状态和 error 如实保留；未绕过登录、付费墙、robots 或验证码 |
| 本次 G0-G5 | `check_docs.py`、ruff、mypy、受影响测试和全量测试 | 通过；全量测试 96 passed；运行数据仅写入临时目录 |
| 本次 G6-S | `UV_CACHE_DIR=/tmp/mynews-acceptance-cache uv run mynews probe --source <source-id>` 与最终 URL 检查 | 通过；6 个重点第一方来源和 2 个价格源 healthy；知乎/Bloomberg blocked |
| 本次 G6-V（旧记录） | 真实 `codex-cli`、DeepSeek/Google Gemini 新增来源采集和程序二次校验 | 失败；Codex 建议产生，但摘录校验为 `evidence_excerpt_mismatch`，保持 `unverified`；修复后重验见下 |

#### 阶段 4.5 G6-V 修复与重验（2026-08-02）

修复保持精确官方域名、日期、正文哈希和逐字摘录门槛：官方 HTML Adapter 将条目标题作为稳定
`excerpt`，完整卡片文本保留在 `content`；核验器只在可见 HTML 文本中匹配，并去除零宽格式字符；
Codex 提示要求返回逐字连续原文，不接受改写或归因性转述。修复后的真实结果如下：

| 门禁 | 实际命令/证据 | 结果 |
| --- | --- | --- |
| 新增来源真实回溯 | `uv run --project /Users/edgarlqs/Downloads/mynews mynews collect --days 7 --source deepseek --source google-gemini` | `complete`，两个来源 `healthy`，`verified_count=2`，退出码 0；证据校验全为 `true` |
| 真实 Codex G6-V | 对同一 Google Gemini 官方候选单独走 `SubprocessCodexRunner` 的 Codex 分支 | `verified / codex_primary_evidence`；URL 为 `https://ai.google.dev/gemini-api/docs/interactions-overview`，`reachable/official_domain/excerpt_matched=true` |

阶段 4.5 仍保持 `Implemented`；完整来源回溯中 CC Switch 当前为 `blocked/http_403`，实验来源
允许 `blocked`，不得把本次结果写成所有稳定来源均 healthy。

### 阶段 5：脚本、定时模板与真实验收（已 Implemented，v1 独立验收待执行）

- [x] `scripts/collect.sh` 固定项目 cwd、绝对 uv、代理继承和日志位置；参数使用数组安全透传，常见密钥和代理值不写入日志。
- [x] 提供中文 help、launchd plist 渲染、安装、状态和卸载动作；label 固定为 `com.mynews.collect`，
  主机本地时间每日 09:30（采集进程使用 `TZ=Asia/Shanghai`），操作幂等；四个动作支持 `--dry-run`，采集脚本使用绝对路径、互斥锁和安全日志；测试使用临时 HOME 和 Fake launchctl，不自动安装、不调用真实 launchctl、不修改系统时区。
- [x] 提供 `mynews validate`，使用同源 RunReport/JSON Schema 校验；显式 `--check-evidence` 时逐条重抓并复核已保存的 `verified` 第一方证据。
- [x] 执行隔离临时目录中的真实 `collect --days 7`，检查 Schema、12 个来源覆盖、35 条事件无重复、
  OpenAI/DeepSeek 价格快照和 5 条 verified 第一方证据。

验收：`plutil -lint` 通过；七天结果满足 JSON Schema；每条 verified 均有可访问的第一方证据。

#### 阶段 5 实现与真实回溯记录（2026-08-02）

阶段 5 代码验证为 `Implemented`，运行数据均写入隔离 `/tmp` 目录，没有进入仓库。受影响测试 31
passed；全量测试 119 passed。Fake launchctl 安装/状态/卸载幂等性、中文 help、参数/代理透传和
HTML 摘录回归测试通过；plist 渲染结果通过 `/usr/bin/plutil -lint`。全量真实回溯结果为
`status=partial`、退出码 3：12 个来源
均有结果，稳定来源中 CC Switch 为 `blocked/http_403`，知乎为 `blocked/http_403`，Bloomberg 为
`blocked/public_metadata_unavailable`；这三类状态均按来源协议如实保留。结果包含 35 条无重复事件、
5 条 verified、`openai-pricing` 和 `deepseek-pricing` 两个价格快照；对 5 条 verified 证据再次抓取后，
官方域名、可访问性和逐字摘录均通过。

真实 launchd 未加载是有意的验收边界：本阶段只用 Fake launchctl 验证管理动作，不修改系统状态；
因此 OPS-02 最高标为 `Implemented`，v1 不在独立验收前宣称 `Verified`。

#### 阶段 5 验收问题修复与重验（2026-08-02）

独立验收发现两项问题并已修复：RunReport/CLI JSON 序列化统一使用字段别名，`requested_range`
输出 `from`；第一方证据哈希改为 HTML 可见正文（去除脚本、样式和模板内容）规范化后的 SHA-256，
避免动态 HTML 壳导致同一正文哈希漂移。新增回归测试后，受影响测试 72 passed，全量测试 109
passed，文档检查、ruff 和 mypy 均通过。

修复后在新的隔离临时目录重复执行两次 `collect --days 7`：两次均为 `partial`、退出码 3，12 个来源
均有结果；首 run 35 条唯一事件、次 run 0 条新增事件，dedup 状态 35 个事件，两个价格快照存在，
原始 RunReport/latest 均符合 `from` 别名和 Schema 要求。5 条 verified 证据逐条复抓后，最终域名、
摘录、日期字段和可见正文哈希均通过；新增 Google Gemini 来源再次完成真实 Codex
`codex_primary_evidence` 核验。真实 launchd 仍未安装或调用。

#### 阶段 5 发布收口实施补充（2026-08-02）

本轮在与 origin/main 一致的干净基线创建 codex/v1-phase5-release-readiness，补齐了采集
互斥锁、四个 launchd 动作的 --dry-run 和发布前 mynews validate 命令。新增命令默认只做离线
RunReport/同源 Schema/verified 结构校验；--check-evidence 才执行真实网络重抓。当前状态仍为
Implemented，独立 v1 验收和真实 launchd 加载继续待执行；本轮不自动安装、不修改系统时区、不记录密钥，
运行数据只写临时输出目录。

本轮真实实施门禁记录（2026-08-02）：

- 新增 DeepSeek/Google Gemini 来源执行真实 `collect --days 7`，两者均 `healthy`，各 1 条候选、
  `verified_count=2`，退出码 0；`mynews validate --check-evidence` 对 2 条证据逐条重抓通过。
- 强制 Google Gemini 候选进入真实 `SubprocessCodexRunner` 分支时，首次按默认 30 秒超时返回
  `unverified/codex_timeout`；仅为冷启动重试注入 120 秒后返回 `verified/codex_primary_evidence`，
  程序二次校验 `reachable/official_domain/excerpt_matched=true`，没有放宽官方域名、日期或摘录规则。
- 全量临时回溯第一轮 `status=partial`、退出码 3，12/12 来源有结果，8 个稳定新闻/价格入口
  `healthy`，知乎 `blocked/http_403`、Bloomberg `blocked/public_metadata_unavailable`；
  44 条唯一事件、5 条 verified、2 个价格快照。第二轮同样 `partial`、退出码 3，44 条候选中
  43 条跨运行去重，1 条为滚动 `--days 7` 窗口内新出现事件；`state/dedup.json` 共 45 个事件键，
  历史 run 2 个，`latest.json` 和首轮 RunReport Schema 均通过，5 条 verified 证据逐条复核通过。
- 为验证严格相同窗口，又在同一临时目录重复执行两次
  `mynews collect --from 2026-07-27 --to 2026-08-02`：两次均 `partial`、退出码 3；首轮 35 条事件、
  次轮 35 条全部跨运行去重（`item_count=0`、`deduplicated_count=35`），`state/dedup.json` 保留
  35 个事件键、2 个历史 run 和 2 个价格快照；首轮 5 条 verified 证据的 `--check-evidence` 复核通过。
- 上述为本轮开发验证证据；真实 launchd 未加载，v1 状态保持 `Implemented`，独立验收仍待执行。

## 命令与语义

```bash
uv run mynews --help
uv run mynews collect
uv run mynews collect --days 7
uv run mynews collect --date 2026-08-02
uv run mynews collect --from 2026-07-27 --to 2026-08-02
uv run mynews probe
uv run mynews probe --source hacker-news
uv run mynews validate --run output/latest.json --schema-out /tmp/mynews-run-report.schema.json
uv run mynews validate --run output/latest.json --check-evidence
./scripts/collect.sh --help
```

- 默认窗口：运行时刻前 24 小时。
- 日期时区：`Asia/Shanghai`。
- 日期选择器互斥；`--from` 与 `--to` 必须同时提供。
- 退出码：`0` 完整成功，`3` 有可用 JSON 但部分失败，`1` 致命失败，`2` 参数错误。
- `scripts/collect.sh` 在已有 `logs/collect.lock` 时跳过重叠采集并返回 `3`；底层 `collect` 退出码原样保留。

## 验证命令

```bash
uv run pytest
uv run ruff check .
uv run mypy src
git diff --check
```

真实网络 probe 和七天回溯是独立验收门槛，不得用离线测试通过代替；阶段 3 的离线检查
只能证明 `Implemented`，不升级为真实来源、真实价格或阶段 4 的 `Verified`。
每个阶段开发完成后，按 [项目验收规则](../testing/acceptance-rules.md) 选择门禁并输出独立验收结论。

## 文档联动

- 每完成一个阶段，同步本计划、[功能矩阵](../product/feature-matrix.md) 和 [文档总览](../README.md)。
- CLI/JSON 变化同步 [JSON 数据契约](../reference/json-data-contract.md)。
- 来源变化同步 [信息来源目录](../reference/source-catalog.md)。
- seam、插件协议或核验门槛变化同步 [系统架构](../architecture/system-architecture.md)，必要时新增 ADR。
