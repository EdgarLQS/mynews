---
title: ADR-0002 受控解析与证据生命周期
doc_type: adr
status: current
decision_status: accepted
implementation_status: implemented
version: 1.0
created: 2026-08-05
updated: 2026-08-05
owner: project-maintainers
---

# ADR-0002：受控解析与证据生命周期

## 背景

ADR-0001 已规定只有第一方证据经过程序校验后才能产生 `verified`。v1.1 仍存在两个运行期缺口：跨运行去重会永久跳过首次无证据条目；整页正文发生无关变化时，严格整页哈希会把仍然支持原事实的证据判为失效。

同时，候选页、重定向和 Codex 建议都属于不可信输入。若模型能够自行增加白名单，或程序只校验字符串后缀和相似组织名，攻击者可通过伪造子域名、近似 GitHub 组织或跨域重定向越过第一方边界。

## 决定

1. 证据解析采用固定顺序：候选自身官方 URL、候选页首个第一方链接、Codex 结构化建议。模型不能改变顺序或官方边界。
2. 官方边界只接受精确 HTTPS host 和精确 GitHub 组织；搜索页、媒体页、伪造子域名、近似组织和跨域重定向不能产生 `verified`。
3. 首次核验必须同时通过可达性、官方边界、重定向、可见正文逐字摘录、发布日期和正文哈希校验。
4. 可重试失败进入独立的 pending 状态；pending 不受新闻去重永久抑制，并具有尝试上限、退避、TTL 和稳定终止原因。
5. run、latest、dedup 和 pending 作为同一逻辑事务提交。失败运行不推进 dedup 或 pending。
6. 证据复核区分 `current`、`changed_supporting` 和 `failed`。正文变化但原摘录、日期和安全边界仍存在时保留 verified，并产生显式警告；支持事实或边界失效时必须降级。
7. RunReport 1.2 采用 minor additive 兼容；1.0/1.1 可继续读取，但只有 1.2 强制完整新门槛。

## 被否决的方案

- 在 DedupState 中复用 pending：新闻输出去重和核验重试具有不同生命周期，耦合会再次造成永久跳过。
- 接受子域名后缀匹配：`openai.com.attacker.example` 等字符串可伪装第一方边界。
- 让 Codex 增加域名或组织：模型输出不能成为信任根。
- 复核继续要求整页哈希完全一致：导航、页脚或无关正文变化会造成不必要的证据失效。
- 在各状态文件写入后再单独提交 latest：中途失败会产生彼此不一致的运行状态。

## 后果

正面：

- 首次核验门槛仍然严格，模型或媒体不能直接提升真实性状态。
- 暂时不可达或模型不可用的条目能在后续运行继续核验，不受新闻去重影响。
- 证据正文漂移变得可解释，不会掩盖真正的支持事实消失。
- 失败提交能够恢复到一致的 run/latest/dedup/pending 状态。

代价：

- pending 保存完整核验目标，状态模型和报告字段增加。
- Store 提交需要暂存和回滚多个文件。
- 复核必须重新抓取页面并解析日期与可见正文。
- 真实 G6-V 仍依赖可用的 Codex CLI、网络和可复查第一方页面，外部阻断时只能报告 BLOCKED。

## 实现与验证状态

受控解析、pending 状态机、事务 Store、证据生命周期和 RunReport 1.2 已在 `codex/v1.2-evidence-lifecycle` 实现，并由 Python 3.12 CI 执行静态检查和全量测试。

离线实现最高只能标记为 Implemented。只有至少一个已知真实 discovery 候选经过生产 Codex 路径，并由程序完成 URL、域名、重定向、摘录、日期和哈希二次核验后，本 ADR 的真实核验部分才可标记为 Verified。当前 G6-V 保持 BLOCKED。
