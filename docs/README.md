---
title: mynews 文档总览与当前状态
doc_type: index
status: current
implementation_status: in_progress
version: 1.0
created: 2026-08-02
updated: 2026-08-02
owner: project-maintainers
---

# mynews 文档总览与当前状态

本页是项目文档的唯一总入口。判断“当前要做什么、设计是什么、实现到哪里”时，应从本页进入，不应直接从归档文件推断。

## 当前状态

| 项目 | 状态 | 说明 |
| --- | --- | --- |
| 产品范围 | Current | 聚焦 AI 与科技，v1 优先模型、AI 编程工具和开发者平台 |
| v1 计划 | Current / In progress | 阶段 0 和阶段 1 已完成，来源采集运行时尚未开始 |
| 系统架构 | Current / Proposed | 模块、接口和扩展 seam 已设计 |
| AI 开发说明 | Current / Implemented | Codex 与 Claude Code 共用一套项目规则 |
| 验收流程 | Current / Implemented | 统一验收规则与 Claude `/acceptance` 入口已建立 |
| 工程骨架与 JSON 契约 | Implemented | 阶段 1 已建立 Python 3.12 + uv、CLI 入口、Pydantic 模型和兼容测试 |
| CC Switch 更新日志 Adapter | In progress | 已完成官方 Release 的离线“新功能”解析，尚未接入运行时 probe/Store |
| 采集运行时 | Not implemented | 阶段 2 开始实现来源 Adapter 和实际采集 |
| 自动定时 | Not implemented | 仅在计划中提供 launchd 安装脚本 |
| 新闻数据 | None | 尚未执行首次七天回溯 |

实现状态必须使用以下口径：

- **Proposed**：设计或计划存在，但代码未完成。
- **Implemented**：约定内容已完成并通过离线检查，不等于真实环境可用。
- **Verified**：已完成约定的真实来源、真实网络或定时运行验收。

## 阅读顺序

1. [功能矩阵](product/feature-matrix.md)：确认 v1、未来和明确不做的范围。
2. [项目验收规则](testing/acceptance-rules.md)：了解每次开发完成后的统一质量门禁。
3. [阶段 1 功能验收说明](testing/phase1-functional-acceptance.md)：确认已验收能力和下一计划边界。
4. [v1 实施计划](planning/v1-implementation-plan.md)：查看实施顺序和验收门槛。
5. [系统架构](architecture/system-architecture.md)：理解模块、数据流、代码结构和插件策略。
6. [信息来源目录](reference/source-catalog.md)：查看渠道角色、稳定等级和核验规则。
7. [JSON 数据契约](reference/json-data-contract.md)：查看后续开发可依赖的数据格式。
8. [架构决策记录](decisions/README.md)：查看关键决策及其理由。

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
| [v1 实施计划](planning/v1-implementation-plan.md) | Current | In progress |
| [系统架构](architecture/system-architecture.md) | Current | Proposed |
| [功能矩阵](product/feature-matrix.md) | Current | In progress |
| [项目验收规则](testing/acceptance-rules.md) | Current | Implemented |
| [阶段 1 功能验收说明](testing/phase1-functional-acceptance.md) | Current | Implemented |
| [信息来源目录](reference/source-catalog.md) | Current | In progress |
| [JSON 数据契约](reference/json-data-contract.md) | Current | In progress |
| [ADR-0001](decisions/ADR-0001-strict-evidence-and-module-seams.md) | Accepted | Proposed |
