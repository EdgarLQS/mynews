---
title: mynews 文档治理规范
doc_type: governance
status: current
implementation_status: not_applicable
version: 1.0
created: 2026-08-02
updated: 2026-08-02
owner: project-maintainers
---

# mynews 文档治理规范

## 目标

文档治理要同时做到：当前入口少而明确、历史证据可追溯、设计和实现不混淆、代码变化能找到必须同步的文档。

## 必填文档头

除根 README、`AGENTS.md`、`CLAUDE.md` 和 AI 技能入口外，当前文档都使用以下头部：

```yaml
---
title: 文档标题
doc_type: plan | architecture | matrix | reference | adr | index | archive-index | governance | test
status: draft | current | superseded | archived
implementation_status: proposed | in_progress | implemented | verified | not_applicable
version: 1.0
created: YYYY-MM-DD
updated: YYYY-MM-DD
owner: project-maintainers
---
```

`status` 描述文档是否仍是当前真相；`implementation_status` 描述文档中的能力是否真正落地。两者不得合并。
ADR 可以额外使用 `decision_status: proposed | accepted | superseded`，但仍必须保留独立的实现状态。

## 单一真相来源

| 问题 | 权威位置 |
| --- | --- |
| 现在做哪些功能 | `product/feature-matrix.md` |
| 当前实施顺序 | `planning/README.md` 和活动计划 |
| 模块、接口、代码结构 | `architecture/system-architecture.md` |
| 为什么采用关键设计 | `decisions/` 下的 ADR |
| 收哪些来源、如何定位 | `reference/source-catalog.md` |
| 后续程序读取什么 JSON | `reference/json-data-contract.md` |
| AI 如何开发本项目 | 根目录 `AGENTS.md`；`CLAUDE.md` 只做 Claude Code 适配 |
| 如何验收一次变更 | `testing/acceptance-rules.md` |
| 当前总体状态 | `docs/README.md` |

根 README 只做项目介绍和导航，不复制详细状态表。

## 生命周期与归档

1. 新提案先创建 `draft` 文档或更新当前计划。
2. 确认后设为 `current`；涉及难以逆转的设计时新增 ADR。
3. 实施过程中只更新 `implementation_status` 和计划进度，不夸大为 Verified。
4. 完成真实验收后，补充命令、日期和结果，再设为 `verified`。
5. 文档被替代时，原文移动到 `archive/<doc_type>/<year>/`，头部改为 `archived`，并增加 `superseded_by`。
6. `archive/README.md` 记录归档原因和替代文档；当前索引不再把归档文档列为入口。

不删除有历史价值的计划、验收和决策，不保留两份都声称为 Current 的同类文档。

## 变更同步矩阵

| 代码或需求变化 | 必须同步 |
| --- | --- |
| CLI 命令、参数、退出码 | 根 README、v1 计划、JSON 契约（如影响输出） |
| JSON 字段或兼容规则 | JSON 契约、相关测试、功能矩阵 |
| 新增或删除来源 | 来源目录、配置、来源测试、功能矩阵 |
| 核验门槛变化 | ADR、系统架构、JSON 契约、计划 |
| 模块 seam 或插件协议变化 | 系统架构；不兼容时新增 ADR |
| 功能完成 | 活动计划、功能矩阵、docs 总览 |
| 真实环境验收 | 计划验收记录、功能矩阵、docs 总览 |
| AI 开发规则变化 | 根 `AGENTS.md`；涉及 Claude 入口时同步 `CLAUDE.md` |
| 验收门禁或结论口径变化 | `testing/acceptance-rules.md`、相关 AI 入口、活动计划 |
| 计划被替代 | planning 索引、archive 索引和所有入口链接 |

## 文档写作规则

- 使用明确状态词：Proposed、Implemented、Verified。
- “支持”必须说明范围；真实网络、性能或定时能力没有证据时不得写“已完成”。
- 信息来源链接优先指向官方长期入口；临时网页要记录访问日期。
- 归档文档中的外部引用优先使用稳定 URL 或固定版本链接。
- 避免在多个文档复制同一大段表格；复制不可避免时注明权威来源。
- 新目录必须在 `docs/README.md` 中说明职责，否则不创建。

## 每次文档变更检查

```bash
python3 scripts/check_docs.py
git diff --check
rg -n "Proposed|Implemented|Verified|Not implemented" README.md AGENTS.md CLAUDE.md docs
```

还要检查：

- `docs/README.md` 与功能矩阵的状态是否一致。
- 根 README 是否仍指向有效入口。
- Markdown 相对链接是否存在。
- 新计划是否已加入 `planning/README.md`。
- 归档文件是否已加入 `archive/README.md`。
- 是否存在两个 Current 文档描述同一件事。
- AI 入口是否仍指向同一份项目规则和验收规则。
