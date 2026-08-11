---
title: mynews JSON 数据契约
doc_type: reference
status: current
implementation_status: implemented
version: 1.6
created: 2026-08-02
updated: 2026-08-09
owner: project-maintainers
---

# mynews JSON 数据契约

## 目标与兼容策略

JSON 是持久化和后续开发的稳定 interface。RunReport 的运行时校验和导出 Schema 来源是 `mynews.domain.models.RunReport`；Digest 使用同模块的独立 `Digest` Schema 1.0。

- 新运行输出 `schema_version: "1.2"`。
- 读取器继续接受 `1.0`、`1.1` 和 `1.2`，并忽略未知 minor 字段。
- 未知 major 必须拒绝。
- 1.0/1.1 的历史 verified 条目按原契约读取；1.2 的 verified 条目强制完整新门槛。
- 删除字段、重命名或改变既有语义需要升级 major。

## 文件布局

```text
output/
├── latest.json
├── digest-latest.json
├── digest-latest.md
├── digests/
│   └── <digest-id>.json
└── runs/
    └── <run-id>.json
state/
├── dedup.json
├── pending_verifications.json
├── price_snapshots/
└── source_snapshots/
logs/
output/editorial/
├── publication-ledger.csv
├── weekly-feedback.md
└── YYYY-MM-DD/
    ├── candidates.json
    └── candidates.md
state/editorial/
└── YYYY-MM-DD/
    ├── collection.json
    └── failures.json
state/editorial-observations.json
```

- 历史 run 追加保存。
- `latest.json` 只指向最近一次 complete 或 partial Run。
- failed Run 不覆盖 latest，也不推进 dedup 或 pending。
- 一次成功提交中的 run、latest、dedup 和 pending 具有同一逻辑事务边界。
- `output/`、`state/`、`logs/` 必须被 Git 忽略。
- Digest 历史文件位于 `output/digests/`；`digest-latest.json` 和 `digest-latest.md` 与历史文件同一原子提交。Digest 失败不得覆盖旧 latest，也不得留下 `.tmp`。

## Candidate Contract v1

`mynews prepare --date YYYY-MM-DD` 生成 editorial 候选包；`--refresh` 才重新抓取当天
来源。无 refresh 时从 `state/editorial/<date>/collection.json` 稳定重放，并可重新读取
publication ledger 生成提示，不调用 Codex、不自动发布。

- 公开 Schema：[`candidate-contract-v1.schema.json`](candidate-contract-v1.schema.json)。
- 顶层 `schemaVersion` 为 `"1.0"`；未知 major 或未来不兼容版本拒绝，旧的
  newsFromAI `categories` 候选可兼容读取。
- `candidates` 最多 500 条；每项含 `candidateRef`、`idScope`、`match`、`sourceRole`、
  `firstSeenAt`、`firstSeenPrecision`、`duplicateGroupId`、`multiSources`、`repeat_count`
  和 HTTPS `evidence`。
- `firstSeenAt` 不得晚于 `generatedAt`；`verified` 仍只能由既有 EvidenceVerifier 产生，
  候选包中的 Feed 或媒体链接不能单独升级真实性。
- 观察状态保存在 JSON 文件而非 SQLite；来源失败写入 `failures.json`，全来源失败时不
  更新旧候选包或 mynews Store。

## RunReport 1.2

```json
{
  "schema_version": "1.2",
  "run_id": "2026-08-05T09:30:00+08:00",
  "status": "complete",
  "requested_range": {
    "from": "2026-07-29T09:30:00+08:00",
    "to": "2026-08-05T09:30:00+08:00",
    "timezone": "Asia/Shanghai",
    "source_ids": [],
    "verification_budget": 30,
    "verification_reasoning_effort": "medium"
  },
  "started_at": "2026-08-05T09:30:00+08:00",
  "finished_at": "2026-08-05T09:31:00+08:00",
  "sources": [],
  "stats": {},
  "reason_counts": {},
  "verification_stats": {
    "attempted": 0,
    "retried": 0,
    "pending": 0,
    "expired": 0,
    "revalidated": 0,
    "changed_supporting": 0,
    "revalidation_failed": 0
  },
  "evidence_reviews": [],
  "items": []
}
```

`status`：

- `complete`：stable 来源全部健康；条目仍可全部 unverified。
- `partial`：已有可用结果，但至少一个 stable 来源异常。
- `failed`：没有可用 stable 来源或无法完成运行。

`requested_range.verification_budget` 必须记录本次实际预算。`requested_range.verification_reasoning_effort` 记录本次核验实际使用的 Codex 推理强度，允许 `low`、`medium`、`high`、`xhigh`、`max`；旧输入可以没有该可选字段，读取器必须保持兼容。两项输入都可以省略，由应用配置注入；新生成的持久化报告会记录有效值。推理强度只影响 Codex 运行时配置，不放宽第一方证据、域名、日期、摘录、哈希或安全回退门槛。

新 CLI 运行会将 `requested_range.source_ids` 写成实际选择顺序：普通采集为 built-in
来源，`--plugin` 为 plugin-only，`--with-plugin` 为 built-in 与显式插件的合并选择。
历史 `source_ids: []` 仍可读取，表示调用方未保存具体选择。

## NewsItem

```json
{
  "id": "evt_<stable-hash>",
  "event_key": "<dedup-key>",
  "event_type": "product_update",
  "title_original": "Official product update",
  "language_original": "en",
  "title_zh": "官方产品更新",
  "summary_zh": "只归纳证据支持的事实。",
  "published_at": "2026-08-04T00:00:00Z",
  "first_seen_at": "2026-08-05T09:30:00+08:00",
  "heat_score": 50,
  "relevance_score": 90,
  "discovery_sources": ["hacker-news"],
  "source_roles": ["discovery"],
  "canonical_url": "https://media.example/story",
  "verification_status": "unverified",
  "verification_reason": "codex_timeout",
  "verification_retry": null,
  "primary_evidence": [],
  "content_hash": "sha256:...",
  "entities": []
}
```

规则：

- `verification_status` 只有 `verified` 和 `unverified`。
- 不相关 discovery 不产生 NewsItem。
- `published_at` 不确定时为 `null`，不能使用抓取时间冒充。
- 热度和相关性不能推导真实性。
- 1.2 verified 条目必须至少有一条满足完整严格门槛的 Evidence。

## Evidence 与生命周期

```json
{
  "url": "https://openai.com/index/example",
  "publisher": "OpenAI",
  "title": "Official announcement",
  "published_at": "2026-08-04T00:00:00Z",
  "retrieved_at": "2026-08-05T09:30:10+08:00",
  "reviewed_at": "2026-08-06T09:30:10+08:00",
  "excerpt": "Exact visible supporting text",
  "content_hash": "sha256:new",
  "previous_content_hash": "sha256:old",
  "validation": {
    "reachable": true,
    "official_domain": true,
    "redirect_safe": true,
    "excerpt_matched": true,
    "date_matched": true,
    "content_hash_matched": false,
    "lifecycle_status": "changed_supporting"
  }
}
```

首次核验要求：

- `reachable`、`official_domain`、`redirect_safe`、`excerpt_matched`、`date_matched` 和 `content_hash_matched` 全部为 `true`；
- `published_at` 必须存在；
- `lifecycle_status` 为 `current`。

复核允许：

- `current`：正文哈希未变化，`content_hash_matched` 为 `true`；
- `changed_supporting`：哈希变化，但原摘录、日期和安全边界仍成立；`previous_content_hash` 必须存在，并产生 warning；
- `failed`：支持文本、日期、访问或安全边界失效，条目不得继续 verified。

`content_hash` 基于可见正文进行 NFKC、大小写和空白规范化后计算 SHA-256。`script`、`style`、`noscript` 和 `template` 内容不参与哈希或摘录匹配。

## PendingVerificationState

```json
{
  "schema_version": "1.0",
  "entries": {
    "event-key": {
      "event_key": "event-key",
      "item": {},
      "source_id": "hacker-news",
      "publisher": "Hacker News",
      "excerpt": "Candidate excerpt",
      "official_domains": ["openai.com"],
      "official_github_organizations": ["openai"],
      "source_role": "discovery",
      "attempt_count": 1,
      "last_reason": "codex_timeout",
      "terminal_reason": null,
      "next_retry_at": "2026-08-05T09:31:00+08:00",
      "max_attempts": 5,
      "created_at": "2026-08-05T09:30:00+08:00",
      "updated_at": "2026-08-05T09:30:00+08:00",
      "expires_at": "2026-08-12T09:30:00+08:00",
      "status": "pending"
    }
  }
}
```

- pending 独立于 dedup。
- `status` 为 `pending` 或 `expired`。
- 次数上限终止原因是 `verification_attempt_limit_reached`。
- TTL 终止原因是 `verification_ttl_expired`。
- 成功核验后删除对应 entry。

RunReport 中的 `verification_retry` 只复制已经持久化的重试事实：状态、尝试次数、最后原因、终止原因、下次重试、上限和到期时间，不推断其他事实。

## EvidenceReview

```json
{
  "event_key": "event-key",
  "evidence_url": "https://openai.com/index/example",
  "status": "changed_supporting",
  "reason": "",
  "warning": "evidence_body_changed_support_still_present"
}
```

`status` 为 `current`、`changed_supporting` 或 `failed`。失败复核必须记录稳定原因并使条目降级。

## SourceResult 与统计

SourceResult 保留 `source_id`、`role`、`stability`、`health`、抓取/接受数量、耗时和结构化错误。非 healthy 来源必须提供 `error.code` 和 `error.message`。

`stats` 保留兼容的扁平统计；1.2 新消费者优先读取 `verification_stats`。重要字段包括：

- `attempted`：本次实际进入核验的唯一目标；
- `retried`：来自到期 pending 的目标；
- `pending`、`expired`：提交后的 pending 状态数量；
- `changed_supporting`、`revalidation_failed`：证据复核结果。

## 外部插件 CLI 报告

外部插件报告只用于 CLI 诊断，不写入 RunReport、latest、dedup、pending 或正式来源
目录；RunReport 仍复用既有 `SourceResult`。`plugin list` 的成功输出包含：

```json
{
  "status": "complete",
  "group": "mynews.source_plugins",
  "loaded": false,
  "plugins": [{"id": "temporary-hn", "value": "package:factory"}],
  "errors": []
}
```

显式加载失败或发现冲突时 `status` 为 `failed`，`errors` 每项至少包含
`plugin_id`、`code`、`message`，可选 `source_id`。稳定错误代码包括
`plugin_not_found`、`factory_import_failed`、`factory_must_be_no_argument`、
`factory_runtime_error`、`invalid_plugin_protocol`、`invalid_source_metadata`、
`protocol_incompatible`、`invalid_role`、`invalid_official_domains`、
`empty_capabilities`、`duplicate_source_id` 和 `builtin_source_id_conflict`。

`plugin probe --plugin <id>` 成功时在既有 `status`/`sources` 外附带 `plugins`；
`collect/probe --plugin <id>` 仍表示 plugin-only，`collect/probe --with-plugin <id>`
表示 built-in + 显式插件，并按实际选择写入 RunReport 的 `requested_range.source_ids`。
外部工厂
只能返回 SourcePlugin 1.0；插件代码没有 Store、Codex 或 Verifier 的公共参数，但
由于它是受信任本地 Python 代码，系统不承诺进程级沙箱。

## 人工清单 1.0

`mynews watchlist --file config/manual-watchlist.json [--out PATH]` 只读取本地 JSON
数组，每项固定包含 `id`、`name`、`url`、`role`、`note`；`url` 必须是 HTTPS，`role`
为 `primary`、`monitor` 或 `manual`。命令不访问网络、不调用 Codex、不创建 Candidate、
不修改 Store，输出按 `id` 稳定排序。

report、digest 和 watchlist 的可分享文本统一拒绝个人绝对路径、疑似密钥赋值以及
`token`/`signature` 等敏感 URL 查询参数。失败只报告字段路径和稳定原因，不回显敏感值。
report 写入使用同目录临时文件、`flush`、`fsync` 和 `os.replace`；替换失败保留旧文件
并清理临时文件。Digest 继续使用既有三文件事务。

## validate 和 report

```bash
uv run mynews validate --run output/latest.json
uv run mynews validate --run output/latest.json --check-evidence
uv run mynews report --run output/latest.json --out output/report.md
```

- 默认 validate 只做离线 Schema 检查。
- `--check-evidence` 重抓 verified 证据；`changed_supporting` 写入 `warnings`，真正失效写入 `errors` 并返回失败。
- warnings 为空时，为兼容旧 CLI 消费者可省略该字段。
- report 不访问网络或调用 Codex，只展示 RunReport 已有事实。

## Digest Schema 1.0

`mynews digest` 只读取 `status` 为 `complete` 或 `partial` 的 RunReport 和 `digest-latest.json`，不修改 RunReport、dedup、pending 或证据状态；`failed` RunReport 必须拒绝且不得写入 Digest latest。Digest 顶层字段如下：

| 字段 | 约束 |
| --- | --- |
| `schema_version` | 固定 `"1.0"`；未知 Digest major/minor 不静默接受 |
| `digest_id`、`run_id`、`generated_at` | 本次简报标识、输入 Run ID 和带时区生成时间 |
| `status` | `complete` 或 `partial`；Codex 超时、非法输出或引用失败必须为 `partial` |
| `main_items` | 只允许 `verification_status=verified` 的聚合事件 |
| `lead_items` | 只允许 `verification_status=unverified` 的线索；保留 `verification_reason` 和可选 `verification_retry` |
| `stats`、`summary_errors` | 聚类、条数、摘要回退和稳定错误事实 |

每个 DigestItem 保存 `event_key`、事件类型、中文标题/摘要/影响判断、`lifecycle`（`new`/`updated`/`ongoing`）、来源条目键、内容哈希、发布时间、四项排序分、`rank_score` 和摘要状态。`evidence_refs` 是结构化引用，只能逐字来自同一 RunReport 的严格 `primary_evidence`，保存 URL、摘录、发布日期和内容哈希；Codex 返回的未知 URL、未知条目、重复引用、外部链接、提示注入标记或非中文摘要都会触发安全回退。

排序分为：

`rank_score = relevance_score × 35% + heat_score × 25% + freshness_score × 20% + event_type_score × 20%`

其中四项均为 0–100；时效按 Digest 生成时刻每过一天衰减 10 分，事件类型分固定为 `model_release=100`、`security=95`、`product_update=85`、`research=80`、`pricing_change=75`、`funding=70`、`other=50`。相同排序分按发布时间和 `event_key` 稳定排序。不同事件只有在精确键/URL，或事件类型、共同实体、标题相似度和日期距离同时满足时才聚合。

### Digest 输出命令

```bash
uv run mynews digest \
  --run output/latest.json \
  --out-dir output \
  --max-items 20 \
  --summary-model gpt-5.6-luna \
  --summary-reasoning-effort medium \
  --summary-timeout 30
uv run mynews digest --run output/latest.json --out-dir output --no-codex
```

`--no-codex` 或模型失败时，主榜条目只使用标题和已保存证据摘录，摘要状态为 `partial`；如果当前没有主榜条目，Digest 可以保持 `complete`，但只包含线索观察。线索观察不调用 Codex，也不生成事实摘要。个人人工查看时可打开线索的 `canonical_url`，但该链接只是发现入口，不自动成为第一方证据；人工确认不能通过直接编辑 JSON 的方式升级 `verified`。

### 人工查看线索

```bash
uv run mynews digest --run output/latest.json --out-dir output --no-codex
open output/digest-latest.md
```

人工查看应从标题和 `canonical_url` 出发，继续找到官方公告、官方文档、官方仓库或发行说明，核对页面日期和逐字摘录。当前版本只支持人工阅读，不提供人工证据写入命令；`validate --check-evidence` 只复核已经是 `verified` 的证据，不会把 `unverified` 自动升级。

## 事务规则

一次 complete/partial 提交同时包含历史 run、latest、dedup 和 pending。每个文件先写同目录临时文件并 `fsync`。任一替换失败时恢复提交前内容，删除本次历史 run。

failed Run 可以保存诊断历史，但不能覆盖 latest，也不能提交本次 dedup/pending 演进结果；`mynews digest` 不能从 failed Run 生成简报。
