---
title: mynews 文档总览与当前状态
doc_type: index
status: current
implementation_status: implemented
version: 1.1
created: 2026-08-02
updated: 2026-08-05
owner: project-maintainers
---

# mynews 文档总览与当前状态

本页是项目文档的唯一总入口。判断“当前要做什么、设计是什么、实现到哪里”时，应从本页进入，不应直接从归档文件推断。

## 当前状态

| 项目 | 状态 | 说明 |
| --- | --- | --- |
| 产品范围 | Current | 聚焦 AI 与科技，继续覆盖模型、AI 编程工具和开发者平台 |
| v1.2 计划 | Current / In Progress | 受控解析、pending 增量核验、原子状态事务和证据生命周期已实现；完整 CI 与真实 G6-V 按计划记录 |
| v1.1 计划 | Archived / Implemented | 原文和验收记录完整归档；discovery G6-V 未完成的历史结论未被改写 |
| 系统架构 | Current / Implemented | SourcePlugin、registry、规范化/去重、EvidenceVerifier、pending、证据生命周期和 NewsStore seam 已实现 |
| AI 开发说明 | Current / Implemented | Codex 与 Claude Code 共用一套项目规则 |
| 验收流程 | Current / Implemented | 统一验收规则与 Claude `/acceptance` 入口已建立 |
| 工程骨架与 JSON 契约 | Implemented | Python 3.12 + uv、中文 CLI、Pydantic 模型和 1.x 兼容测试已建立 |
| 来源运行时 | Implemented | 内置 registry、共享 HTTP 策略、来源隔离和 Adapter 已保留并纳入主线全量回归 |
| 规范化与新闻去重 | Implemented | 相关性过滤和跨运行 DedupState 保持独立；不相关 discovery 不进入核验 |
| 第一方证据核验 | Implemented | 固定解析顺序、精确域名/组织、重定向、摘录、日期和哈希二次校验已实现；真实 discovery G6-V 尚未通过 |
| Pending 增量核验 | Implemented | 首次可重试失败进入独立状态，后续即使命中新闻去重仍可重试；成功、上限和 TTL 有明确状态 |
| 证据生命周期 | Implemented | 复核区分 current、changed_supporting 和 failed；支持事实或安全边界失效时降级 |
| JSON Store | Implemented | 历史 run、latest、dedup 和 pending 使用同一逻辑提交事务并支持失败恢复 |
| 自动定时 | Implemented | `scripts/collect.sh` 的离线测试保留；本次没有安装或调用真实 launchd |
| 发布前校验 | Implemented | `validate --check-evidence` 将仍具支持事实的正文漂移报告为 warning，真正失效仍为错误 |

实现状态必须使用以下口径：

- **Proposed**：设计或计划存在，但代码未完成。
- **Implemented**：约定内容已完成并通过离线检查，不等于真实环境可用。
- **Verified**：已完成约定的真实来源、真实网络或定时运行验收。

## 阅读顺序

1. [功能矩阵](product/feature-matrix.md)：确认当前、未来和明确不做的范围。
2. [项目验收规则](testing/acceptance-rules.md)：了解每次开发完成后的统一质量门禁。
3. [v1.2 当前计划](planning/v1.2-evidence-lifecycle-plan.md)：查看当前实施顺序和验收门槛。
4. [系统架构](architecture/system-architecture.md)：理解模块、数据流、代码结构和插件策略。
5. [信息来源目录](reference/source-catalog.md)：查看渠道角色、稳定等级和核验规则。
6. [JSON 数据契约](reference/json-data-contract.md)：查看后续开发可依赖的数据格式。
7. [架构决策记录](decisions/README.md)：查看关键决策及其理由。
8. [历史归档](archive/README.md)：追溯被替代计划和原始验收记录。

## 文档职责

| 目录/文件 | 唯一职责 | 不应包含 |
| --- | --- | --- |
| `planning/` | 当前实施计划、里程碑和验收结果 | 长期架构真相 |
| `architecture/` | 当前系统结构、接口和约束 | 每日执行流水 |
| `product/feature-matrix.md` | 功能范围与实现状态 | 详细代码设计 |
| `reference/source-catalog.md` | 信息来源清单与来源策略 | 运行时健康结果 |
| `reference/json-data-contract.md` | 稳定 JSON 字段与兼容规则 | 临时调试输出 |
| `testing/` | 当前测试策略、质量门禁和验收规则 | 临时测试日志 |
| `decisions/` | 已接受的重要架构决策 | 可随意改写的计划 |
| `archive/` | 被替代的历史原文 | 当前状态入口 |

完整维护规则见 [文档治理规范](GOVERNANCE.md)。

## 当前权威文档

| 文档 | 状态 | 实现状态 |
| --- | --- | --- |
| [v1.2 当前计划](planning/v1.2-evidence-lifecycle-plan.md) | Current | In Progress |
| [系统架构](architecture/system-architecture.md) | Current | Implemented |
| [功能矩阵](product/feature-matrix.md) | Current | Implemented |
| [项目验收规则](testing/acceptance-rules.md) | Current | Implemented |
| [信息来源目录](reference/source-catalog.md) | Current | Implemented |
| [JSON 数据契约](reference/json-data-contract.md) | Current | Implemented |
| [ADR-0001](decisions/ADR-0001-strict-evidence-and-module-seams.md) | Accepted | Implemented |
| [ADR-0002](decisions/ADR-0002-controlled-resolution-and-evidence-lifecycle.md) | Accepted | Implemented |
