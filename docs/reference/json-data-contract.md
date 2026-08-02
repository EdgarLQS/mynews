---
title: mynews JSON 数据契约
doc_type: reference
status: current
implementation_status: proposed
version: 1.0
created: 2026-08-02
updated: 2026-08-02
owner: project-maintainers
---

# mynews JSON 数据契约

## 目标

JSON 是 v1 的持久化和后续开发 interface。UI、数据库导入或分析脚本应读取本契约，不依赖内部 Python 对象或日志文本。

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
    "timezone": "Asia/Shanghai"
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
- `verified` 至少包含一条通过程序复核的 `primary_evidence`。
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
