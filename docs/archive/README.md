---
title: mynews 历史文档归档索引
doc_type: archive-index
status: current
implementation_status: not_applicable
version: 1.0
created: 2026-08-02
updated: 2026-08-02
owner: project-maintainers
---

# mynews 历史文档归档索引

本目录只保存被替代的计划、架构和参考文档原文，供追溯背景；这里的内容不代表当前状态，也不应作为新开发的直接需求来源。

## 目录约定

```text
archive/
├── plan/<year>/
├── architecture/<year>/
└── reference/<year>/
```

当前暂无归档文档。

## 归档要求

- 保留原文，只修改文档头为 `status: archived` 并增加 `superseded_by`。
- 在本页登记原路径、归档路径、归档日期、原因和替代文档。
- 更新 `docs/README.md`、planning 索引及所有内部链接。
- 归档文档不得重新出现在“当前权威文档”表中。
- 归档是移动而不是复制；仓库中不能同时存在两份 Current 版本。

完整流程见 [文档治理规范](../GOVERNANCE.md)。
