# mynews

面向个人使用的 AI 与科技热点收集器，v1 优先覆盖模型、AI 编程工具、开发者平台及相关重大科技动态。项目目标是从热点渠道发现线索，回溯并验证第一方原始信息，再以结构化 JSON 保存，供后续筛选、分析和产品开发使用。

> 当前状态：阶段 1 契约与阶段 2 原始来源采集已 Implemented；三项内置来源的真实 probe 已 Verified。阶段 3 去重/JSON Store 和阶段 4 第一方核验仍未实现。

## 文档入口

- [文档总览与当前状态](docs/README.md)
- [v1 实施计划](docs/planning/v1-implementation-plan.md)
- [系统架构与代码结构](docs/architecture/system-architecture.md)
- [功能矩阵](docs/product/feature-matrix.md)
- [项目验收规则](docs/testing/acceptance-rules.md)
- [信息来源目录](docs/reference/source-catalog.md)
- [JSON 数据契约](docs/reference/json-data-contract.md)

文档的状态、归档和同步规则见 [文档治理规范](docs/GOVERNANCE.md)。历史文档只保留背景信息，不代表当前实现状态。

## AI 开发与验收

- Codex 读取 [AGENTS.md](AGENTS.md)，Claude Code 读取 [CLAUDE.md](CLAUDE.md)；通用项目规则只在 `AGENTS.md` 维护。
- 开发完成后可以直接说“按项目验收规则开始验收”。
- 在 Claude Code 中也可以输入 `/acceptance`；默认验收只读，不会自动修改或提交代码。若当前 Claude 会话启动时还没有 `.claude/skills/`，新建入口后重启一次会话。

文档或 AI 规则变更后，可运行 `python3 scripts/check_docs.py` 做本地一致性检查；该脚本也提供 `--help`。
