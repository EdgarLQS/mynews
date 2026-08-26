---
title: mynews 规划文档状态索引
doc_type: index
status: current
implementation_status: in_progress
version: 2.0
created: 2026-08-02
updated: 2026-08-26
owner: project-maintainers
---

# mynews 规划文档状态索引

本页是规划文档的唯一当前入口。

## 活动计划

| 计划 | 文档状态 | 实现状态 | 下一门槛 |
| --- | --- | --- | --- |
| [v1.7 收口至 v2.0 统一开发总计划](v1.7-v2.0-master-plan.md) | Current | In progress | M1/P5 仍 BLOCKED；M2、M3 已按用户限定范围 Implemented，后续仍按顺序推进 |

## 已完成计划

| 计划 | 文档状态 | 实现状态 | 替代关系 |
| --- | --- | --- | --- |
| [v1.7 分时情报分析与人工反馈闭环计划](../archive/plan/2026/v1.7-intelligence-loop-plan.md) | Archived | Implemented | 被统一开发总计划替代；P0-P4 保持 Implemented，P5 未完成记录保留 |
| [P5 外部插件分发准备计划](../archive/plan/2026/p5-plugin-distribution-readiness-plan.md) | Archived | Proposed | 被统一开发总计划 M1 替代；旧基线准备结果不能作为当前 P5 PASS |
| [v1.8-v2.0 产品与技术路线图](../archive/plan/2026/v1.8-v2.0-roadmap.md) | Archived | Proposed | 被统一开发总计划 M2-M7 替代；未实施状态保留 |
| [v1.6 newsFromAI 数据能力完整吸收计划](../archive/plan/2026/v1.6-newsfromai-parity-plan.md) | Archived | Implemented | 被 v1.7 分时情报分析与人工反馈闭环计划替代；来源与 Candidate 能力继续保留 |
| [v1.4 外部来源插件计划](../archive/plan/2026/v1.4-source-plugins-plan.md) | Archived | Implemented | 被 v1.5 扩展来源与安全交接计划替代；外部插件仍保持显式加载和受信任本地代码边界 |
| [v1.5 扩展来源与安全交接计划](../archive/plan/2026/v1.5-expanded-sources-safe-handoff-plan.md) | Archived | Implemented | 被 v1.6 newsFromAI 数据能力完整吸收计划替代；来源插件和安全边界继续保留 |
| [v1.1 信息质量闭环与可读报告计划](../archive/plan/2026/v1.1-information-quality-plan.md) | Archived | Implemented | 被 v1.2 增量核验与证据生命周期计划替代；discovery G6-V 未完成的记录保留在原文 |
| [v1.2 增量核验与证据生命周期计划](../archive/plan/2026/v1.2-evidence-lifecycle-plan.md) | Archived | Implemented | 被 v1.3 情报简报计划替代；真实 G6-V `BLOCKED` 和 G7 限制保留在原文 |
| [v1.3 情报简报计划](../archive/plan/2026/v1.3-intelligence-digest-plan.md) | Archived | Implemented | 被 v1.4 外部来源插件计划替代；真实 Digest Codex `BLOCKED` 记录保留在原文 |
| [v1 热点收集器实施计划](../archive/plan/2026/v1-implementation-plan.md) | Archived | Verified | 已被 v1.1 计划替代；真实 launchd 按边界不加载 |

## 计划维护规则

- 仓库只能有一份主计划处于 Current；当前总计划内部按 M1–M7 顺序直接在 `main` 推进，不创建或切换阶段分支。
- 任务完成要记录验证命令与结果，不能只勾选完成。
- 主计划被替代或 v1 完成后，移动到 `../archive/plan/<year>/`，并在本页登记替代关系。
- 长期设计不写进计划正文，应更新系统架构或新增 ADR。

归档细则见 [文档治理规范](../GOVERNANCE.md) 与 [归档索引](../archive/README.md)。
