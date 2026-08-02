---
title: mynews 架构决策记录索引
doc_type: index
status: current
implementation_status: proposed
version: 1.0
created: 2026-08-02
updated: 2026-08-02
owner: project-maintainers
---

# mynews 架构决策记录索引

ADR 记录重要、长期且不应被普通计划静默改写的决定。

## 当前决策

| ADR | 决策状态 | 实现状态 |
| --- | --- | --- |
| [ADR-0001：严格第一方证据与模块 seam](ADR-0001-strict-evidence-and-module-seams.md) | Accepted | Proposed |

## 新增 ADR 的条件

- verified 定义变化。
- SourcePlugin 或 JSON 主版本出现不兼容变化。
- 引入数据库、外部插件系统或新的强依赖。
- 安全、归档、数据保留策略发生重要变化。

ADR 应包含：背景、决定、替代方案、后果、实现与验证状态。已接受 ADR 不直接改写结论；方向改变时新增 ADR 并将旧 ADR 标为 Superseded。
