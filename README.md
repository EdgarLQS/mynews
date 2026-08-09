# mynews

面向个人使用的 AI 与科技热点收集器，优先覆盖模型、AI 编程工具、开发者平台及相关重大科技动态。项目从热点渠道发现线索，回溯并验证第一方原始信息，再以结构化 JSON 保存，供后续筛选、分析和产品开发使用。

> 当前状态：v1.4 外部来源插件已实现 Python entry-point、显式 `--plugin` 加载、严格协议校验、结构化失败和 Store 保护。v1.3 Digest 的真实 Codex 记录仍为 `BLOCKED`，不宣称 Verified；真实 launchd 按验收边界未加载。外部插件是受信任本地 Python 代码，显式清单不是进程级沙箱。

日常运行可使用 `scripts/collect.sh --days 7`。脚本固定在项目根目录运行，支持 `render-plist`、`install`、`status` 和 `uninstall`；这些 launchd 动作支持中文 help 和 `--dry-run`，安装动作必须显式执行，任务 label 为 `com.mynews.collect`，计划时间为主机本地时间每日 09:30（采集进程使用 `TZ=Asia/Shanghai`）。采集脚本使用 `logs/collect.lock` 防止定时任务重叠，并保留底层 `collect` 退出码。只有显式加 `--digest` 才会在采集成功后追加简报生成，默认行为不变。运行数据写入 `output/`、`state/`，日志写入 `logs/`，这些目录不提交。需要时可用 `collect --verification-reasoning-effort medium` 和 `digest --summary-reasoning-effort medium` 调整 Codex 推理强度；这不会改变证据核验门槛。外部来源必须显式使用 `mynews plugin list` 发现、`mynews plugin probe --plugin <id>` 检查，或在 `collect/probe` 中传入 `--plugin <id>`；默认命令不会加载外部插件。

发布前可执行：

```bash
uv run mynews validate --run output/latest.json --schema-out /tmp/mynews.schema.json
uv run mynews report --run output/latest.json --out output/report.md
uv run mynews digest --run output/latest.json --out-dir output --no-codex
```

增加 `--check-evidence` 会重新抓取每条 `verified` 证据。若页面整体发生变化，但原摘录、日期和官方边界仍成立，校验结果会产生 `changed_supporting` warning；支持文本、日期或安全边界失效时仍然失败。

如果个人使用只需要人工查看候选，可以使用 `mynews digest --no-codex` 生成线索链接，再自行打开官方页面确认。该模式不会把 `unverified` 条目升级为 `verified`；不要直接编辑 `output/latest.json`，也不要把人工判断冒充 `codex_primary_evidence`。需要程序正式接收人工证据时，应另行增加带 URL、日期、摘录和哈希校验的人工复核入口。

## 文档入口

- [文档总览与当前状态](docs/README.md)
- [v1.4 当前计划](docs/planning/v1.4-source-plugins-plan.md)
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
