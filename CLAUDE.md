@AGENTS.md

# Claude Code 补充说明

- `AGENTS.md` 是通用项目规则的权威来源，本文件不复制其中的开发规范。
- 用户输入 `/acceptance` 时，执行 `.claude/skills/acceptance/SKILL.md`；用户直接说“按项目验收规则开始验收”时执行同一流程。
- 用户询问当前进度、下一阶段、最新计划、实施说明或验收说明时，执行 `.claude/skills/plan-implement/SKILL.md`，先核对当前文档和 Git 状态再生成交接内容。
- 用户要求“实施验收”时，采用“只读首轮验收 → 独立修复 → 修复后复验”的三段式流程；首轮不修改文件，最终以复验结果为准。
- 详细验收标准只维护在 `docs/testing/acceptance-rules.md`，不得在本文件创建第二套标准。
- 当前扩展来源与安全交接的实施顺序和验收门槛见 [v1.5 计划](docs/planning/v1.5-expanded-sources-safe-handoff-plan.md)；具体规则仍以 `AGENTS.md` 为准。
- v1.5 P1–P5 已有离线实现；`--plugin`、`--with-plugin`、`watchlist` 和独立来源包的真实验收仍必须按计划记录，fixture/mock 不能升级为 `Verified`。
