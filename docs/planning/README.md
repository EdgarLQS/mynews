---
title: mynews 规划文档状态索引
doc_type: index
status: current
implementation_status: verified
version: 1.0
created: 2026-08-02
updated: 2026-08-03
owner: project-maintainers
---

# mynews 规划文档状态索引

本页是规划文档的唯一当前入口。

## 活动计划

| 计划 | 文档状态 | 实现状态 | 下一门槛 |
| --- | --- | --- | --- |
| [v1.1 信息质量闭环与可读报告计划](v1.1-information-quality-plan.md) | Current | Implemented | G0-G7：来源等级、质量统计、离线 report、真实 probe 和隔离七天回溯已记录；discovery G6-V 保持未完成 |

## 已完成计划

| [v1 热点收集器实施计划](../archive/plan/2026/v1-implementation-plan.md) | Archived | Verified | 已被 v1.1 计划替代；真实 launchd 按边界不加载 |

## 计划维护规则

- 同一阶段只能有一份主计划处于 Current。
- 任务完成要记录验证命令与结果，不能只勾选完成。
- 主计划被替代或 v1 完成后，移动到 `../archive/plan/<year>/`，并在本页登记替代关系。
- 长期设计不写进计划正文，应更新系统架构或新增 ADR。

归档细则见 [文档治理规范](../GOVERNANCE.md) 与 [归档索引](../archive/README.md)。
