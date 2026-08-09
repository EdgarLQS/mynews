---
title: ADR-0003 基于证据的情报简报
doc_type: adr
status: current
decision_status: accepted
implementation_status: implemented
version: 1.0
created: 2026-08-09
updated: 2026-08-09
owner: project-maintainers
---

# ADR-0003：基于证据的情报简报

## 背景

RunReport 已经区分第一方核验事实和待核验线索，但直接消费原始条目会造成重复事件、排序不稳定，以及把发现渠道的内容误读为事实。v1.3 需要输出可读的中文简报，同时保持 v1.2 的 `verified` 门槛、证据生命周期和 pending 独立性不变。

## 决定

1. 新增独立 `DigestBuilder`，输入只包含已保存的 `RunReport` 和上一期 Digest；它不调用采集器，不推进核验，不改写 RunReport。
2. Digest 主榜只接收 `verified`；`unverified` 进入线索观察，保留原因、重试状态和原有排序信息。Digest Schema 在模型层拒绝主榜/线索交叉污染。
3. 事件聚合采用保守规则：精确事件键或 URL 可合并；跨 URL 还要同时满足事件类型、共同实体、标题高相似度和日期距离。相似厂商或单个关键词不能触发合并。
4. 排序固定使用相关性 35%、热度 25%、时效 20%、事件类型 20%，最后用发布时间和事件键稳定打破平局。生命周期只比较已保存事实、证据和评分，输出 `new`、`updated` 或 `ongoing`。
5. Codex 只接收 RunReport 中已保存且通过严格门槛的证据引用。程序验证条目 ID、引用 URL、中文摘要、中文影响判断、外部 URL 和提示注入标记；调用失败、超时或非法输出回退到标题与证据摘录，检测到输入注入时不回显可疑摘录，并将 Digest 标为 `partial`。
6. Digest 历史 JSON、`digest-latest.json` 和 `digest-latest.md` 作为一个原子提交单元。失败恢复旧 latest，不写入采集的 `output/latest.json`，不留下临时文件。

## 被否决的方案

- 让 DigestBuilder 重新抓取来源或重新判断 verified：这会复制并可能降低 v1.2 的核验门槛。
- 让 unverified 条目进入主榜并用“可信度”排序：热度和相关性不能证明事实，必须保持事实/线索隔离。
- 把 Codex 自由文本直接写入简报：模型输出不是证据，未知引用和外部 URL 必须回退。
- 只替换 latest、不保存历史 Digest：无法判断事件生命周期，也无法审计上一期变化。

## 后果

正面：简报可以离线重建，主榜事实边界清楚，线索不被静默升级，失败输出不会破坏旧 latest，排序和生命周期可重复验证。

代价：需要维护独立 Schema、聚类规则和原子 Store；没有严格保存证据的历史 verified 条目只能安全回退或以 `partial` 输出，不能由模型补齐事实。

## 实现与验证状态

`DigestBuilder`、Digest Schema 1.0、Codex 摘要 seam、中文 `mynews digest`、`collect.sh --digest` 和原子 `DigestFileStore` 已实现，并由离线测试覆盖聚类、误合并、排序、生命周期、事实/线索隔离、Codex 异常、安全回退、Schema 和恢复。

本 ADR 的真实 Codex 摘要、真实来源和定时集成尚未执行；离线实现最高只能标记为 Implemented，不写成 Verified。
