---
title: mynews JSON 数据契约
doc_type: reference
status: current
implementation_status: implemented
version: 1.0
created: 2026-08-02
updated: 2026-08-02
owner: project-maintainers
---

# mynews JSON 数据契约

## 目标

JSON 是 v1 的持久化和后续开发 interface。UI、数据库导入或分析脚本应读取本契约，不依赖内部 Python 对象或日志文本。

阶段 1 已由 Pydantic 模型固定运行报告 schema；代码和 schema 的唯一来源是
`mynews.domain.models.RunReport.model_json_schema()`。阶段 3 增加规范化事件、去重状态和
价格快照模型；`tests/fixtures/run-report-v1.json` 仍是兼容性 fixture。阶段 3 的实现和
JSON Store 和阶段 4.5 价格来源由离线测试证明；真实七天回溯和阶段 5 定时能力仍未完成。

## 文件布局

```text
output/
├── latest.json
└── runs/
    └── <ISO-8601-run-id>.json
state/
├── dedup.json
└── price_snapshots/
    └── <source-id>.json
```

- Run 文件追加保存，不覆盖历史；文件名中的 `:` 会替换为 `-` 以便跨平台读取。
- `latest.json` 是最近一次 complete 或 partial Run 的原子副本。
- failed Run 保存诊断文件，但不能覆盖 latest，也不能更新 dedup 状态。
- state 是可重建的运行状态，不是新闻结果的唯一副本。

## Run 顶层结构

```json
{
  "schema_version": "1.0",
  "run_id": "2026-08-02T09:30:00+08:00",
  "status": "complete",
  "requested_range": {
    "from": "2026-08-01T09:30:00+08:00",
    "to": "2026-08-02T09:30:00+08:00",
    "timezone": "Asia/Shanghai",
    "source_ids": [],
    "verification_budget": 30
  },
  "started_at": "2026-08-02T09:30:00+08:00",
  "finished_at": "2026-08-02T09:31:10+08:00",
  "sources": [],
  "stats": {},
  "items": []
}
```

必填字段：`schema_version`、`run_id`、`status`、`requested_range`、`started_at`、`finished_at`、`sources`、`stats`、`items`。

`status`：

- `complete`：所有启用的 stable 来源健康完成，阶段 3 流水线已提交；条目仍可全部为 `unverified`。
- `partial`：已有可用结果，但 stable 来源部分失败。
- `failed`：没有可用来源、配置无效、Schema 无效或无法提交结果。

`requested_range.verification_budget` 是应用层生效的 Codex 候选预算。输入请求可以省略它，
此时由 `VerificationConfig` 注入计划默认值 30；持久化的 `RunReport` 始终记录本次实际预算。

## SourceResult

```json
{
  "source_id": "hacker-news",
  "role": "discovery",
  "health": "healthy",
  "fetched_count": 30,
  "accepted_count": 5,
  "duration_ms": 420,
  "error": null
}
```

`health` 为 `healthy`、`degraded`、`blocked` 或 `failed`。错误使用稳定 `code` 和可读 `message`，不得只保存堆栈。

## 采集输出与阶段 2 原始 seam

生产命令 `mynews collect` 现在输出并持久化 `RunReport`；`mynews probe` 仍输出来源健康
快照。阶段 2 的 `SourceCollector.collect()` 保留为可替换的原始来源 seam，输出临时 JSON
对象供 Adapter 测试和兼容调用：

```json
{
  "status": "complete",
  "sources": [
    {
      "source_id": "qwen",
      "role": "primary",
      "health": "healthy",
      "fetched_count": 1,
      "accepted_count": 1,
      "duration_ms": 20,
      "checked_at": "2026-08-02T04:00:00Z",
      "error": null
    }
  ],
  "candidates": []
}
```

`probe` 省略 `candidates`，原始 `collect` 增加来源 Adapter 的 `candidates` 和可选
`price_snapshots`；生产
`collect` 才生成 `run_id`、事件键、去重状态和 `latest.json`。阶段 4 生产流水线会先尝试
官方来源直验，再将其余候选交给可配置的 Codex Verifier。非 healthy 来源必须包含
`error.code` 和 `error.message`，单个来源失败不会吞掉其他来源。

## NewsItem

```json
{
  "id": "evt_<stable-hash>",
  "event_key": "<dedup-key>",
  "event_type": "pricing_change",
  "title_original": "Original title",
  "language_original": "en",
  "canonical_url": "https://official.example/news/item",
  "entities": ["official"],
  "source_roles": ["primary"],
  "title_zh": "中文事实标题",
  "summary_zh": "只归纳证据明确支持的事实。",
  "published_at": "2026-08-02T01:00:00Z",
  "first_seen_at": "2026-08-02T09:30:15+08:00",
  "heat_score": 72,
  "relevance_score": 91,
  "discovery_sources": [],
  "verification_status": "unverified",
  "verification_reason": "missing_primary_evidence",
  "primary_evidence": [],
  "content_hash": "sha256:..."
}
```

规范化规则：

- `canonical_url` 使用小写协议/主机名，移除片段、默认端口、常见跟踪参数和非根路径尾斜线；业务查询参数保留并排序。
- 时间字段必须带时区；`published_at` 统一保存为 UTC，来源未知时为 `null`；`first_seen_at` 是本次运行首次观察时间。
- `language_original` 使用 `zh`、`en`、`mixed` 或 `und`；来源角色只允许 `discovery`、`primary`、`monitor`、`manual`。
- `event_type` 是规范化事件类别，当前包括 `model_release`、`pricing_change`、`product_update`、`research`、`security`、`funding` 和 `other`。
- `event_key` 由规范 URL、规范实体、规范标题、发布日期和内容指纹组成的稳定哈希生成；来源 ID 不参与事件键，因此允许跨来源合并。
- `heat_score`、`relevance_score` 和 `verification_status` 分别表示热度、相关性和真实性状态，不能相互推导或合并为单一分数。

规则：

- `verification_status` 只有 `verified` 和 `unverified`。
- `verified` 至少包含一条通过程序复核的 `primary_evidence`；该证据的 `reachable`、`official_domain` 和 `excerpt_matched` 必须都为 `true`。
- `primary_evidence.content_hash` 是程序重新抓取正文后计算的规范化 SHA-256；Codex 若返回哈希，
  必须与重新抓取结果一致。
- 证据访问失败、官方域名或 GitHub 组织不匹配、异常重定向、正文摘录/日期/哈希不匹配、
  Codex 超时或坏 JSON 都必须保持 `verification_status: "unverified"`，并写入稳定
  `verification_reason`。
- `published_at` 不确定时必须为 `null`，不能使用抓取时间。
- 中文摘要不能添加证据之外的性能、价格或发布时间判断。
- `heat_score` 和 `relevance_score` 不参与真实性判定。

## Evidence

```json
{
  "url": "https://official.example/news/item",
  "publisher": "Official Publisher",
  "title": "Official announcement",
  "published_at": "2026-08-02T01:00:00Z",
  "retrieved_at": "2026-08-02T09:30:20+08:00",
  "excerpt": "Short supporting excerpt",
  "content_hash": "sha256:...",
  "validation": {
    "reachable": true,
    "official_domain": true,
    "excerpt_matched": true
  }
}
```

## 兼容规则

- `schema_version` 使用 `major.minor`。
- 新增可选字段只增加 minor；删除、重命名、改变语义或必填性增加 major。
- 消费者必须忽略未知字段，但不得忽略未知 major 版本。
- 稳定枚举新增值属于兼容风险，必须同步契约测试和变更记录。
- Python Model 和导出的 JSON Schema 必须由同一处定义生成，避免运行时与文档漂移。

## 阶段 1 已实现的模型边界

- `CollectionRequest` 要求带时区且前后顺序正确的时间范围；`from_` 以 JSON 别名 `from` 序列化。
- `Candidate` 表示来源 Adapter 的未经规范化候选，不直接作为 Run JSON 顶层字段。
- `Evidence` 的校验结果默认显式为 `false`，避免未执行校验时产生成功暗示。
- `NewsItem` 的 `verified` 状态必须包含至少一条通过三项 validation 的 `primary_evidence`。
- `SourceResult` 的非 `healthy` 状态必须包含结构化 `error`。
- 当前模型接受 `1.x` minor 版本和未知字段，并拒绝未知 major `schema_version`；阶段 3 的持久化和原子写入已由 `JsonNewsStore` 实现。

## DedupState 与 PriceSnapshot

`state/dedup.json` 保存可恢复的事件键及其 `first_seen_at`、`last_seen_at`：

```json
{
  "schema_version": "1.0",
  "events": {
    "evt_stable_hash": {
      "first_seen_at": "2026-08-02T09:30:00Z",
      "last_seen_at": "2026-08-02T09:30:00Z"
    }
  }
}
```

阶段 4.5 已接入 OpenAI 官方模型/价格页和 DeepSeek 模型与价格页。价格快照先写入状态，只有
后续运行的规范化 URL 或内容哈希发生差异时，Pipeline 才生成 `event_type: pricing_change`
的候选；首次观察不会生成新闻事件。官方页面没有发布日期时，`published_at` 保持 `null`：

```json
{
  "source_id": "provider",
  "url": "https://official.example/pricing",
  "observed_at": "2026-08-02T09:30:00Z",
  "first_observed_at": "2026-08-02T09:30:00Z",
  "published_at": null,
  "content_hash": "sha256:...",
  "values": {"model": "1.00"}
}
```

同一来源和 URL 的后续快照保留最早的 `first_observed_at`；规范化内容哈希不变时不生成
`pricing_change`。价格变化事件的来源角色为 `monitor`，仍须经过统一证据流程，不能因价格
页本身而直接标为 `verified`。
