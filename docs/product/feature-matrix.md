---
title: mynews 功能矩阵
doc_type: matrix
status: current
implementation_status: in_progress
version: 1.0
created: 2026-08-02
updated: 2026-08-02
owner: project-maintainers
---

# mynews 功能矩阵

本表是产品范围和实现状态的唯一真相来源。完整 v1 运行时仍为 Planned；阶段 2 已落地的
来源与 registry 能力按行记录为 Implemented/Verified，文档治理和 AI 验收入口已经落地。

状态：`Planned`、`In progress`、`Implemented`、`Verified`、`Future`、`Out`。

| ID | 领域 | 功能 | v1 状态 | 验收入口 |
| --- | --- | --- | --- | --- |
| DOC-01 | 治理 | 文档索引、状态、计划和归档机制 | Implemented | `python3 scripts/check_docs.py` |
| AI-01 | 协作 | `AGENTS.md` 与 `CLAUDE.md` 共用项目规则 | Implemented | 指令入口检查 |
| QA-01 | 验收 | 统一验收规则与 Claude `/acceptance` | Implemented | Skill 校验 + 规则链接检查 |
| CLI-01 | CLI | 全局、子命令和脚本中文 `--help` | Implemented | `uv run mynews --help`、子命令和脚本 help |
| CLI-02 | CLI | 默认最近 24 小时收集 | Implemented | 日期边界 + 流水线测试 |
| CLI-03 | CLI | `--days`、`--date`、`--from/--to` 参数契约与时区校验 | Implemented | 日期参数测试 |
| CLI-04 | CLI | 结构化退出码 0/1/2/3 | Implemented | 来源状态与流水线测试 |
| SRC-01 | 来源 | Hacker News 官方 API | Verified | fixture + `uv run mynews probe --source hacker-news` |
| SRC-02 | 来源 | 官方 RSS/Atom/API、GitHub Release 与官方 HTML 更新页 | Implemented | Qwen RSS、CC Switch Release、OpenAI/Anthropic/Gemini/DeepSeek/TRAE fixtures 与 Adapter 测试 |
| SRC-03 | 来源 | 官方价格页和更新日志监控 | Implemented | OpenAI API Pricing、DeepSeek 模型与价格页；首观快照、规范化差异与 `pricing_change` 测试 |
| SRC-04 | 来源 | 知乎热榜实验 Adapter | Implemented | 公开元数据 fixture + live probe；登录/受限时结构化 `blocked` |
| SRC-05 | 来源 | Bloomberg 实验 Adapter | Implemented | 公开元数据 fixture + live probe；不读取付费墙内容 |
| SRC-06 | 来源 | 国内外 AI 与重点科技官方来源 | Implemented | 国内 Qwen/DeepSeek/TRAE，国外 OpenAI/Anthropic/Google Gemini，逐项 probe；本次 G6-V 未通过，保持 Implemented |
| SRC-07 | 来源 | CC Switch 官方 Changelog 新功能监控 | Verified | fixture；2026-08-02 15:34 probe healthy，33/33 条，退出码 0 |
| PIPE-01 | 处理 | 规范化、相关性、热度分离 | Implemented | Normalizer 领域测试 |
| PIPE-02 | 处理 | 跨来源、跨日期、跨运行去重 | Implemented | 批内与跨运行状态恢复测试 |
| VER-01 | 核验 | 第一方官方证据直接核验 | Verified | 官方直验测试；Qwen 第一方候选真实 G6-V 复核 |
| VER-02 | 核验 | 可配置 Codex Verifier 与单次候选预算 | Verified | 阶段 4 的 Fake、预算/批次测试及既有 Qwen G6-V 通过；阶段 4.5 新增来源 G6-V 仍失败 |
| VER-03 | 核验 | URL、域名、摘录二次校验 | Verified | 伪造来源、重定向、日期/哈希、提示注入和真实页面二次校验 |
| DATA-00 | 数据 | Pydantic v1 领域模型与 JSON Schema 兼容契约 | Implemented | `uv run pytest tests/test_models.py` |
| DATA-01 | 数据 | 每次运行独立 JSON | Implemented | JSON Store 追加运行测试 |
| DATA-02 | 数据 | latest 原子更新和失败保护 | Implemented | 原子写入与 failed 保护测试 |
| DATA-03 | 数据 | 去重状态与价格快照 JSON | Implemented | 重启恢复与 first_observed_at 测试 |
| OPS-01 | 运维 | 已注册内置来源 `probe` | Implemented | 12 个 built-in 来源均可单独选择；健康、blocked、failed 证据见阶段 4.5 记录 |
| OPS-02 | 运维 | 09:30 launchd 安装脚本 | Implemented | `scripts/collect.sh render-plist/install/status/uninstall`；Fake launchctl 幂等测试与 `plutil -lint`；真实 launchd 未加载 |
| EXT-01 | 扩展 | built-in SourcePlugin registry | Implemented | registry 隔离、重复 ID 和选择测试 |
| EXT-02 | 扩展 | 仓库外 Python entry-point 插件 | Future | 后续 ADR |
| EXT-03 | 扩展 | 其他核验器 Adapter | Future | 后续需求 |
| UI-01 | 产品 | Web/桌面 UI | Out | 不属于 v1 |
| DB-01 | 数据 | 数据库存储 | Out | JSON 先行 |
| PUB-01 | 发布 | 自动生成和发布内容 | Out | 明确不做 |
| BYPASS-01 | 采集 | 绕过登录、付费墙或验证码 | Out | 安全约束 |

## 状态更新规则

- 实现内容完成且相应离线检查通过后才能从 Planned 改为 Implemented。
- 依赖真实网络、Codex 或 launchd 的功能，必须完成对应真实验收才能改为 Verified。
- 改表时同步 [文档总览](../README.md) 和 [v1 计划](../planning/v1-implementation-plan.md)。
