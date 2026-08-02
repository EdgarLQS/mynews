---
title: ADR-0001 严格第一方证据与模块 seam
doc_type: adr
status: current
decision_status: accepted
implementation_status: implemented
version: 1.0
created: 2026-08-02
updated: 2026-08-02
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

阶段 4 的离线实现和伪造来源测试已完成，当前为 Implemented；真实 Codex 和七天回溯仍需按
[v1 实施计划](../planning/v1-implementation-plan.md) 的独立门禁验收后才能更新为 Verified。
