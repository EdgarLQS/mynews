---
schema_version: 1
enabled: true
timezone: Asia/Shanghai
schedule:
  - "09:00"
  - "18:00"
catch_up: latest_only
language: zh-CN
report:
  minimum_items: 0
  maximum_items: 6
  directory: output/editorial/automation/reports
state_file: state/editorial/automation/state.json
---

# mynews 分时情报分析任务

本文档是 Codex 分时任务的唯一操作规范。它描述任务如何运行，但不会注册 Codex
任务、操作 launchd、访问受限页面或自动发布内容。

## 目标与档位

- 使用 `Asia/Shanghai` 确定业务日期和当前档位。
- 每天只处理 `09:00` 和 `18:00` 两个档位。
- 任务恢复时使用 `catch_up=latest_only`：错过多个档位时只执行恢复时应处理的最新档位。
- 每档正式情报允许 `0–6` 条；可靠内容不足时写“本轮暂无重要更新”，不得用旧闻或弱
  证据补足数量。

## 固定运行顺序

严格按以下顺序执行，不得跳过前置失败：

1. `mynews prepare --refresh`（实际调用需附 `--date YYYY-MM-DD`）；
2. `scripts/collect-expanded.sh --days 2`；
3. `mynews validate --check-evidence`（实际调用需附 `--run output/latest.json`）；
4. `mynews digest`（实际调用需附 `--run output/latest.json`）；
5. 读取 Digest、上一档报告、任务状态、publication ledger 和 weekly feedback，生成本档报告。

`prepare` 或扩展采集返回 `3 (partial)` 时，只有必要输出完整且失败已结构化记录才可继续，
并在报告中保留警告。返回 `1`、`2`、证据校验失败、输出缺失或状态输入损坏时，必须停止，
不得覆盖已有报告，也不得推进成功档位。

## 事实边界

- 正式情报只能来自 Digest `main_items` 中 `verification_status=verified` 的条目。
- Candidate、manual watchlist、discovery 和 Digest `lead_items` 只能进入“待核查线索”，不能
  写入正式情报，也不能通过报告文字修改 `verified`。
- 每条正式情报回答：发生了什么、影响谁、为什么重要、现在是否需要行动，并保留已保存的
  第一方证据链接和摘录。
- 中国 AI 动态可以单列，但计入总数，不设强制配额；唯一官方来源的争议事项必须明确标注。
- 已报告或已发布事件默认跳过，只有功能、价格、可用范围、日期、迁移要求、风险或限制
  发生实质变化时才作为重要更新。

## 报告与状态

报告文件名为 `YYYY-MM-DD-HHmm.md`，写入 `output/editorial/automation/reports/`，至少包含：

- 生成时间、业务日期和档位；
- 0–6 条正式情报；
- 待核查线索、重要更新、重复跳过、未入选原因和运行警告；
- 每条正式情报的四问式结论、核验状态和第一方证据；
- 无可靠更新时的明确结论。

任务状态写入 `state/editorial/automation/state.json`，固定包含：

```json
{
  "schemaVersion": 1,
  "lastAttemptAt": null,
  "lastSuccessAt": null,
  "lastCompletedSlot": null,
  "lastReport": null,
  "reportedEvents": {}
}
```

报告必须先在目标目录使用临时文件、`flush`、`fsync` 和 `os.replace` 原子写入；报告成功后
才可更新状态。状态写入失败不得把档位标成成功。`reportedEvents` 每项只保存事件键、上次
报告时间、内容哈希和报告相对路径，不保存密钥、Cookie、授权头或个人绝对路径。

## 明确边界

- 本任务不修改 `publication-ledger.csv` 或 `weekly-feedback.md`；它们只作为人工反馈上下文读取。
- 本任务不生成平台发布素材，不自动发布，不生成 PPT、图片、Canva、TTS 或视频。
- 本任务不访问网络以外的受限内容，不绕过登录、付费墙、robots、验证码或访问控制。
- 本文档和离线测试最多证明 `Implemented`；真实双档、latest-only 补跑和失败恢复必须经
  独立授权后验收，不能提前写成 `Verified`。
