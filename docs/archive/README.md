---
title: mynews 历史文档归档索引
doc_type: archive-index
status: current
implementation_status: not_applicable
version: 1.3
created: 2026-08-02
updated: 2026-08-05
owner: project-maintainers
---

# mynews 历史文档归档索引

本目录只保存被替代的计划、架构和参考文档原文，供追溯背景；这里的内容不代表当前状态，也不应作为新开发的直接需求来源。

## 目录约定

```text
archive/
├── plan/<year>/
├── architecture/<year>/
├── reference/<year>/
└── testing/<year>/
```

## 已归档文档

| 原路径 | 归档路径 | 日期 | 原因 | 替代文档 |
| --- | --- | --- | --- | --- |
| `docs/planning/v1.1-information-quality-plan.md` | `plan/2026/v1.1-information-quality-plan.md` | 2026-08-05 | v1.1 已实现并由增量核验与证据生命周期 v1.2 替代；原文保留未完成 discovery G6-V 记录 | [v1.2 归档计划](plan/2026/v1.2-evidence-lifecycle-plan.md) |
| `docs/planning/v1.2-evidence-lifecycle-plan.md` | `plan/2026/v1.2-evidence-lifecycle-plan.md` | 2026-08-09 | v1.2 被 v1.3 情报简报替代；保留实际离线门禁和真实 G6-S/G6-V/G7 结论 | [v1.3 计划](../planning/v1.3-intelligence-digest-plan.md) |
| `docs/testing/v1.2-real-environment-acceptance.md` | `testing/2026/v1.2-real-environment-acceptance.md` | 2026-08-09 | v1.2 真实验收清单已完成回写；G6-V 仍为 `BLOCKED`，不再作为当前验收入口 | [v1.3 计划](../planning/v1.3-intelligence-digest-plan.md) |
| `docs/planning/v1-implementation-plan.md` | `plan/2026/v1-implementation-plan.md` | 2026-08-03 | v1 完成并由信息质量闭环 v1.1 替代 | [v1.1 归档计划](plan/2026/v1.1-information-quality-plan.md) |

## 归档要求

- 保留原文，只修改文档头为 `status: archived` 并增加 `superseded_by`。
- 在本页登记原路径、归档路径、归档日期、原因和替代文档。
- 更新 `docs/README.md`、planning 索引及所有内部链接。
- 归档文档不得重新出现在“当前权威文档”表中。
- 归档是移动而不是复制；仓库中不能同时存在两份 Current 版本。

完整流程见 [文档治理规范](../GOVERNANCE.md)。
