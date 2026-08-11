---
title: ADR-0001 严格第一方证据与模块 seam
doc_type: adr
status: current
decision_status: accepted
implementation_status: implemented
version: 1.1
created: 2026-08-02
updated: 2026-08-11
owner: project-maintainers
---

# ADR-0001：严格第一方证据与模块 seam

## 背景

热点榜、媒体和社区适合发现线索，但可能引用错误、缺少上下文或晚于实际事件。项目还需要持续增加国内外来源，如果每个来源直接操作存储和核验，Collector 会快速失控，后续插件也难以测试。

## 决定

1. 发现和证据分层：热点渠道只能生成 Candidate；只有第一方原始信息可生成 verified NewsItem。
2. Codex 负责搜索和语义建议，但程序负责 URL、官方域名、正文摘录和 Schema 的最终校验。
3. Collector 通过 SourcePlugin、EvidenceVerifier 和 NewsStore 三个真实 seam 使用外部能力。
4. 来源插件只采集和解释本来源，不写存储、不调用 Codex、不决定 verified。
5. v1 使用 built-in 插件注册表；仓库外动态插件等出现真实需求后再发布稳定 interface。
6. JSON 是 v1 稳定输出 interface，内部 Python 结构不作为外部契约。

### v1.1 约束补充

7. 来源保留详细稳定等级；`experimental` 的异常不影响 Run 状态，稳定来源异常仍必须显式反映在 RunReport 中。
8. discovery 候选先经过确定性的 AI/科技相关性过滤；通过的候选可以进入 Codex 第一方证据查找，但 Codex 不能扩大程序提供的精确官方域名或 GitHub 组织白名单。
9. 官方 HTML 目录页只有同时具备标题和日期才产生事件；无日期目录只保存 SourceSnapshot，摘要上限为 500 字。质量统计和离线 Markdown report 由 RunReport/NewsStore seam 提供。

## 被否决的方案

- 媒体或热榜多次重复即可自动确认：重复只能证明热度，不能证明真实性。
- 完全信任 Codex 返回结果：模型输出、搜索摘要和网页内容都可能不可靠。
- 每种 Feed、HTML、API 都暴露独立公共 interface：会把实现差异泄露给 Collector。
- v1 直接承诺第三方插件兼容性：当前没有真实外部插件消费者，过早冻结会增加长期负担。

## 后果

正面：

- 真实性门槛清晰，失败时可以安全保持 unverified。
- 新来源局部实现，主流程和 JSON 消费者不变。
- 测试可以使用 FakeVerifier、InMemoryNewsStore 和 fixture SourcePlugin。

代价：

- 新来源必须维护官方域名和日期语义。
- Codex 搜索成功后仍要额外抓取和校验证据。
- 一些付费墙或动态网页只能保持 experimental/manual。

## 实现与验证

阶段 4 的离线实现、伪造来源测试和当时约定的真实 Codex G6-V 已完成。v1.1 的离线实现已完成，但其 discovery G6-V 未完成，完整记录保留在 [v1.1 归档计划](../archive/plan/2026/v1.1-information-quality-plan.md)。

v1.2 对模型边界、跨运行重试和证据复核生命周期的新增决定由 [ADR-0002](ADR-0002-controlled-resolution-and-evidence-lifecycle.md) 管理；当前实施入口是 [v1.7 分时情报分析与人工反馈闭环计划](../planning/v1.7-intelligence-loop-plan.md)，不回写改变本 ADR 的原始结论。
