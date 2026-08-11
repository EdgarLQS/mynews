---
title: mynews 文档总览与当前状态
doc_type: index
status: current
implementation_status: implemented
version: 1.7
created: 2026-08-02
updated: 2026-08-11
owner: project-maintainers
---

# mynews 文档总览与当前状态

本页是项目文档的唯一总入口。判断“当前要做什么、设计是什么、实现到哪里”时，应从本页进入，不应直接从归档文件推断。

## 当前状态

| 项目 | 状态 | 说明 |
| --- | --- | --- |
| 产品范围 | Current | 聚焦 AI 与科技，继续覆盖模型、AI 编程工具和开发者平台 |
| v1.3 情报简报计划 | Archived / Implemented | DigestBuilder、Digest Schema 1.0、主榜/线索隔离、摘要回退和原子输出已完成；真实 Digest Codex 验收记录仍为 `BLOCKED`，原文保留在归档 |
| v1.4 外部来源插件计划 | Archived / Implemented | Python entry-point 外部 SourcePlugin、显式插件选择、严格加载校验、结构化失败和 Store 保护已通过离线门禁；历史计划已归档 |
| v1.5 扩展来源与安全交接计划 | Archived / Implemented | 已移动到历史归档；来源插件、人工清单和安全边界继续被 v1.6 复用 |
| v1.6 newsFromAI 数据能力完整吸收计划 | Archived / Implemented | datacollection 能力已完成吸收；逐来源真实状态和 partial 限制保留在归档原文 |
| v1.7 分时情报分析与人工反馈闭环计划 | Current / Proposed | 计划新增双档 Codex 任务文档和人工确认后的 publication/feedback CLI；尚未实施 |
| v1.2 计划与真实验收 | Archived / In Progress | 实际命令、两次 Run ID、G6-S 限制、G6-V `BLOCKED` 和 G7 结果已归档；真实发布门禁未完成，不能写成 Verified |
| 系统架构 | Current / Implemented | SourcePlugin、registry、规范化/去重、EvidenceVerifier、pending、证据生命周期、NewsStore 和 Digest seam 已实现 |
| AI 开发说明 | Current / Implemented | Codex 与 Claude Code 共用一套项目规则 |
| 验收流程 | Current / Implemented | 统一验收规则与 Claude `/acceptance` 入口已建立 |
| 工程骨架与 JSON 契约 | Implemented | Python 3.12 + uv、中文 CLI、Pydantic 模型和 1.x 兼容测试已建立 |
| 来源运行时 | Implemented | 内置 registry、共享 HTTP 策略、来源隔离和 Adapter 已保留；外部 entry-point 仅在显式插件选择时加载 |
| 规范化与新闻去重 | Implemented | 相关性过滤和跨运行 DedupState 保持独立；不相关 discovery 不进入核验 |
| 第一方证据核验 | Implemented | 固定解析顺序、精确域名/组织、重定向、摘录、日期和哈希二次校验已实现；真实 discovery G6-V 尚未通过 |
| Pending 增量核验 | Implemented | 首次可重试失败进入独立状态，后续即使命中新闻去重仍可重试；成功、上限和 TTL 有明确状态 |
| 证据生命周期 | Implemented | 复核区分 current、changed_supporting 和 failed；支持事实或安全边界失效时降级 |
| JSON Store | Implemented | 历史 run、latest、dedup 和 pending 使用同一逻辑提交事务并支持失败恢复 |
| 情报简报 | Implemented | DigestBuilder 只读取 RunReport/上一期 Digest；主榜严格 verified，线索显示原因/重试；Codex 异常安全回退；Digest 三文件原子恢复有离线测试 |
| 自动定时 | Implemented | `scripts/collect.sh` 的离线测试保留；本次没有安装或调用真实 launchd |
| 发布前校验 | Implemented | `validate --check-evidence` 将仍具支持事实的正文漂移报告为 warning，真正失效仍为错误 |

实现状态必须使用以下口径：

- **Proposed**：设计或计划存在，但代码未完成。
- **Implemented**：约定内容已完成并通过离线检查，不等于真实环境可用。
- **Verified**：已完成约定的真实来源、真实网络或定时运行验收。

## 阅读顺序

1. [功能矩阵](product/feature-matrix.md)：确认当前、未来和明确不做的范围。
2. [项目验收规则](testing/acceptance-rules.md)：了解每次开发完成后的统一质量门禁。
3. [v1.7 当前计划](planning/v1.7-intelligence-loop-plan.md)：查看分时情报分析和人工反馈闭环的实施范围与验收门槛。
4. [newsFromAI 映射表](reference/newsfromai-v16-mapping.md)：查看 17 个 Feed 与全部人工清单覆盖率。
5. [系统架构](architecture/system-architecture.md)：理解采集、核验、Digest 模块和数据流。
6. [信息来源目录](reference/source-catalog.md)：查看渠道角色、稳定等级和核验规则。
7. [JSON 数据契约](reference/json-data-contract.md)：查看 RunReport 和 Digest 格式。
8. [架构决策记录](decisions/README.md)：查看关键设计及其理由。
9. [历史归档](archive/README.md)：追溯 v1.2 计划、真实验收和更早历史。

## 文档职责

| 目录/文件 | 唯一职责 | 不应包含 |
| --- | --- | --- |
| `planning/` | 当前实施计划、里程碑和验收结果 | 长期架构真相 |
| `architecture/` | 当前系统结构、接口和约束 | 每日执行流水 |
| `product/feature-matrix.md` | 功能范围与实现状态 | 详细代码设计 |
| `reference/source-catalog.md` | 信息来源清单与来源策略 | 运行时健康结果 |
| `reference/json-data-contract.md` | 稳定 JSON 字段与兼容规则 | 临时调试输出 |
| `testing/` | 当前测试策略、质量门禁和验收规则 | 临时测试日志或未经脱敏的秘密 |
| `decisions/` | 已接受的重要架构决策 | 可随意改写的计划 |
| `archive/` | 被替代的历史原文 | 当前状态入口 |

完整维护规则见 [文档治理规范](GOVERNANCE.md)。

## 当前权威文档

| 文档 | 状态 | 实现状态 |
| --- | --- | --- |
| [v1.7 当前计划](planning/v1.7-intelligence-loop-plan.md) | Current | Proposed；尚未实施，真实 Codex 双档和任务注册不得提前写成 Verified |
| [系统架构](architecture/system-architecture.md) | Current | Implemented |
| [功能矩阵](product/feature-matrix.md) | Current | Implemented |
| [项目验收规则](testing/acceptance-rules.md) | Current | Implemented |
| [信息来源目录](reference/source-catalog.md) | Current | Implemented |
| [JSON 数据契约](reference/json-data-contract.md) | Current | Implemented |
| [ADR-0001](decisions/ADR-0001-strict-evidence-and-module-seams.md) | Accepted | Implemented |
| [ADR-0002](decisions/ADR-0002-controlled-resolution-and-evidence-lifecycle.md) | Accepted | Implemented |
| [ADR-0003](decisions/ADR-0003-evidence-grounded-intelligence-digest.md) | Accepted | Implemented；未执行真实 Digest Codex 验收 |
| [ADR-0004](decisions/ADR-0004-external-source-plugins.md) | Accepted | Implemented；外部插件为受信任本地代码，不提供进程级沙箱 |
