# mynews

面向个人使用的 AI 与科技热点收集器，优先覆盖模型、AI 编程工具、开发者平台及相关重大科技动态。项目从热点渠道发现线索，回溯并验证第一方原始信息，再以结构化 JSON 保存，供后续筛选、分析和产品开发使用。

> 当前状态：v1.6 已按 Implemented 归档，v1.7 分时情报分析与人工反馈闭环的 P0–P4 已按离线门禁实现；真实 Codex 双档、latest-only 补跑和失败恢复仍须独立验收。网络受限时保持 `BLOCKED`，不得用任务文档或 mock 代替 Verified。外部插件是受信任本地 Python 代码，显式清单不是进程级沙箱。

日常运行直接执行 `scripts/collect.sh`，默认收集最近 1 天；默认 registry 已内置 newsFromAI 当前 25 个自动 Feed，并保留不重复的旧 mynews 来源补充，运行不依赖 `/Users/edgarlqs/Downloads/newsFromAI` 工程。需要回溯时可使用 `scripts/collect.sh --days 7` 或其他日期选择参数。脚本固定在项目根目录运行，支持 `render-plist`、`install`、`status` 和 `uninstall`；这些 launchd 动作支持中文 help 和 `--dry-run`，安装动作必须显式执行，任务 label 为 `com.mynews.collect`，计划时间为主机本地时间每日 09:30（采集进程使用 `TZ=Asia/Shanghai`）。采集脚本使用 `logs/collect.lock` 防止定时任务重叠，并保留底层 `collect` 退出码。只有显式加 `--digest` 才会在采集成功后追加简报生成。运行数据统一写入项目内专用且不提交的 `output/`、`state/`、`logs/` 目录。需要时可用 `collect --verification-reasoning-effort medium` 和 `digest --summary-reasoning-effort medium` 调整 Codex 推理强度；这不会改变证据核验门槛。外部 entry-point 插件仍必须显式使用 `mynews plugin list` 发现、`mynews plugin probe --plugin <id>` 检查；`--plugin` 是 plugin-only，`--with-plugin` 才是 built-in + 插件追加。`scripts/collect-expanded.sh` 仅保留为兼容别名，不再重复加载旧插件来源。

发布前可执行：

```bash
uv run mynews validate --run output/latest.json --schema-out /tmp/mynews.schema.json
uv run mynews report --run output/latest.json --out output/report.md
uv run mynews digest --run output/latest.json --out-dir output --no-codex
uv run mynews watchlist --file config/manual-watchlist.json --out output/watchlist.md
uv run mynews prepare --date 2026-08-11
uv run mynews publication add --candidate-file output/editorial/2026-08-11/candidates.json \
  --event-id event-2026-08-11-example --title "已发布标题" --platform "平台" \
  --url https://example.com/post --published-at 2026-08-11T18:00:00+08:00
uv run mynews feedback record --week 2026-W32 --platform "平台" \
  --reads 0 --favorites 0 --shares 0 --new-followers 0
```

增加 `--check-evidence` 会重新抓取每条 `verified` 证据。若页面整体发生变化，但原摘录、日期和官方边界仍成立，校验结果会产生 `changed_supporting` warning；支持文本、日期或安全边界失效时仍然失败。

如果个人使用只需要人工查看候选，可以使用 `mynews digest --no-codex` 生成线索链接，再自行打开官方页面确认。该模式不会把 `unverified` 条目升级为 `verified`；不要直接编辑 `output/latest.json`，也不要把人工判断冒充 `codex_primary_evidence`。需要程序正式接收人工证据时，应另行增加带 URL、日期、摘录和哈希校验的人工复核入口。report、digest、watchlist、publication 和 feedback 会拒绝绝对路径、疑似密钥和敏感 URL 查询参数。

分时任务规范见根目录 [news-task.md](news-task.md)。它只定义 09:00/18:00 的任务契约和报告/状态边界，不自动注册 Codex 任务、操作 launchd、修改 publication ledger 或 weekly feedback。

## 文档入口

- [文档总览与当前状态](docs/README.md)
- [v1.7 收口至 v2.0 统一开发总计划](docs/planning/v1.7-v2.0-master-plan.md)
- [newsFromAI 来源与人工清单映射](docs/reference/newsfromai-v16-mapping.md)
- [v1.4 外部插件归档计划](docs/archive/plan/2026/v1.4-source-plugins-plan.md)
- [v1.3 Digest 归档与真实验收记录](docs/archive/README.md)
- [系统架构与代码结构](docs/architecture/system-architecture.md)
- [功能矩阵](docs/product/feature-matrix.md)
- [项目验收规则](docs/testing/acceptance-rules.md)
- [信息来源目录](docs/reference/source-catalog.md)
- [JSON 数据契约](docs/reference/json-data-contract.md)
- [架构决策记录](docs/decisions/README.md)

文档的状态、归档和同步规则见 [文档治理规范](docs/GOVERNANCE.md)。历史文档只保留背景信息，不代表当前实现状态。

## AI 开发与验收

- Codex 读取 [AGENTS.md](AGENTS.md)，Claude Code 读取 [CLAUDE.md](CLAUDE.md)；通用项目规则只在 `AGENTS.md` 维护。
- 开发完成后可以直接说“按项目验收规则开始验收”。
- 在 Claude Code 中也可以输入 `/acceptance`；默认验收只读，不会自动修改或提交代码。

文档或 AI 规则变更后，可运行 `python3 scripts/check_docs.py` 做本地一致性检查；该脚本也提供 `--help`。
