---
title: mynews JSON 数据契约
doc_type: reference
status: current
implementation_status: in_progress
version: 1.0
created: 2026-08-02
updated: 2026-08-02
owner: project-maintainers
---

# mynews JSON 数据契约

## 目标

JSON 是 v1 的持久化和后续开发 interface。UI、数据库导入或分析脚本应读取本契约，不依赖内部 Python 对象或日志文本。

阶段 1 已由 Pydantic 模型固定运行报告 schema；代码和 schema 的唯一来源是
`mynews.domain.models.RunReport.model_json_schema()`。`tests/fixtures/run-report-v1.json`
是兼容性 fixture，当前只证明模型和契约可离线互读，不代表真实采集已经实现。

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

- Run 文件追加保存，不覆盖历史。
- `latest.json` 是最近一次 complete 或 partial Run 的原子副本。
- failed Run 可保存诊断，但不能覆盖 latest。
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

- `complete`：所有启用的 stable 来源完成，核验链路可用。
- `partial`：已有可用结果，但 stable 来源或核验链路部分失败。
- `failed`：没有可用来源、配置无效、Schema 无效或无法提交结果。

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

## 阶段 2 CLI 原始采集输出

`mynews probe` 和 `mynews collect` 在阶段 2 已接入内置来源，但尚未进入阶段 3 的
`RunReport`/JSON Store。它们输出临时 JSON 对象：

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

`probe` 省略 `candidates`，`collect` 只增加来源 Adapter 的原始 `candidates`；两者都不
生成 `run_id`、事件键、去重状态、`latest.json` 或 `verified` 证据。非 healthy 来源必须
包含 `error.code` 和 `error.message`，单个来源失败不会吞掉其他来源。

## NewsItem

```json
{
  "id": "evt_<stable-hash>",
  "event_key": "<dedup-key>",
  "event_type": "pricing_change",
  "title_original": "Original title",
  "language_original": "en",
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

规则：

- `verification_status` 只有 `verified` 和 `unverified`。
- `verified` 至少包含一条通过程序复核的 `primary_evidence`；该证据的 `reachable`、`official_domain` 和 `excerpt_matched` 必须都为 `true`。
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
- 当前模型接受 `1.x` minor 版本和未知字段，并拒绝未知 major `schema_version`；持久化和原子写入在阶段 3 实现。
