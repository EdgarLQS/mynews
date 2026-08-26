# mynews 项目 AI 开发说明

本文件是仓库级 AI 开发规则的单一真相来源。Codex 自动读取本文件；Claude Code 通过根目录 `CLAUDE.md` 导入本文件。

## 项目边界

- 项目目标：收集 AI 与科技热点，v1 优先覆盖模型、AI 编程工具、开发者平台及相关重大科技动态，回溯第一方原始信息，并保存结构化 JSON。
- 当前实现状态以 `docs/README.md` 为准，不从计划或历史文档推断功能已经落地。
- 产品范围以 `docs/product/feature-matrix.md` 为准，实施顺序以 `docs/planning/` 中的活动计划为准。
- 不自动发布内容，不绕过登录、付费墙、robots、验证码或访问控制。

## 开工规则

1. 先确认工作目录、Git 状态和已有变更，保护不属于当前任务的内容。
2. 从 `docs/README.md` 进入文档体系；只读取本次任务需要的权威文档。
3. 多文件或多步骤任务先给出不超过 5 句话的策略与验证计划。
4. 需求存在会改变实现方向的实质歧义时，列出至少两种解释并请求确认；小歧义采用最小、可逆的合理假设继续。
5. 只修改任务直接相关内容，不顺带重构或添加未经要求的依赖。
6. 用户询问“当前进度”“下一阶段”“最新计划”“实施说明”“验收说明”或要求跨会话交接时，先读取 `.claude/skills/plan-implement/SKILL.md`，按其中流程重新核对当前文档和 Git 状态。
7. 阶段交付完成后继续留在 `main`；后续阶段直接基于已包含上一阶段交付的最新 `main` HEAD 开发，不创建或切换 `codex/<phase>` 分支。开始前先确认基线提交和工作树状态。

## 架构与编码规则

- 使用 Python 3.12、uv、src layout；新增生产依赖前说明必要性。
- 保持 `collector`、`normalizer`、`verifier`、`store`、`orchestrator` 的模块边界，来源差异封装在 SourcePlugin Adapter 内。
- 领域对象不得依赖具体来源、CLI 或文件系统实现；外部 I/O 必须可替换、可离线测试。
- 单个函数尽量不超过 50 行；优先类型明确、职责单一和可测试的实现，避免为未来猜测做过度抽象。
- 面向用户的 CLI 帮助和参数错误使用中文；日志和 JSON 字段保持稳定、机器可读。
- 任何来源失败都必须显式记录，不得静默丢失、伪装成功或污染 `latest.json`。
- 外部来源只通过 Python entry-point group `mynews.source_plugins` 接入；`plugin list` 不执行工厂，`--plugin <id>` 表示 plugin-only，`--with-plugin <id>` 表示 built-in + 显式插件追加，均只加载无参数工厂。外部插件是受信任本地 Python 代码，显式允许不是进程级沙箱；插件不得接触 Store、Codex、Verifier 或修改 `verified`。v1.5 的 15 个来源实现位于独立分发包，真实 probe 仍需单独记录状态。

## 统一总计划与 v1.7 分时情报边界

- 唯一 Current 计划是 `docs/planning/v1.7-v2.0-master-plan.md`。M0–M7 必须按顺序推进；
  当前阶段未 PASS 或未合入最新 `main` 时，不得启动后续阶段，除非用户明确记录范围受限的阶段豁免。
- 批准或实施统一总计划不等于授权真实 P5。只有用户明确要求“开始 P5 真实验收”后，才允许
  真实网络 probe、Scheduled Task 注册或故障恢复演练；P5 未 PASS 时不得启动 v1.8。用户于
  2026-08-26 明确允许在 P5 保持 BLOCKED 的前提下开始 M2，该豁免不代表 P5 Verified。
- `ApplicationRuntime` 在 M2 中已 Implemented；`ArtifactCommitter` 在 M3 中已 Implemented；
  `evaluate`、`ops` 和 `editorial review` 当前仍为 Planned/Proposed，不能从计划文档推断代码已经存在。

- 根目录 `news-task.md` 固定 `Asia/Shanghai`、`09:00`/`18:00`、`catch_up=latest_only` 和每档 `0–6` 条正式情报；它是离线任务契约，不代表已注册 Codex 或 launchd 任务。
- 固定顺序为 `prepare --refresh`、`scripts/collect-expanded.sh --days 2`、`validate --check-evidence`、`digest`、报告生成；只有 Digest `main_items` 的 `verified` 条目能进入正式情报，Candidate、manual watchlist、discovery 和 `lead_items` 只能进入待核查线索。
- 报告必须先原子写入 `output/editorial/automation/reports/`，成功后才推进 `state/editorial/automation/state.json`；失败不得更新成功档位，任务不得修改 publication ledger、weekly feedback 或生成发布素材。
- `publication add` 与 `feedback record` 只处理作者明确提供的本地事实，必须离线、复用隐私门禁和原子写入，不得接触 Store、Codex、网络、Candidate/Digest Schema 或 `verified`。

## 新闻与证据规则

- 热榜、媒体和社区只负责发现线索，不能单独证明新闻真实。
- 只有官方公告、官方文档、官方价格页、官方仓库或发行说明等第一方证据通过程序复核后，条目才能标记为 `verified`。
- 搜索摘要、转载、模型推断和不可访问链接不能作为已核验证据。
- 证据不足时允许少收、漏收或保持 `unverified`，不得为了数量降低核验标准。

## 文档同步规则

- 遵循 `docs/GOVERNANCE.md`；设计、实现和真实验收必须分别使用 Proposed、Implemented、Verified。
- CLI、JSON、来源、插件 seam、核验门槛或功能状态变化时，按治理文档的同步矩阵更新权威文档。
- 新增文档目录前先在 `docs/README.md` 中定义其唯一职责。
- 计划被替代后移入 `docs/archive/`，不得让两个文档同时声称是同一主题的当前真相。

## 开发验证规则

- 新行为必须有对应测试；优先先写失败测试，再完成最小实现。
- 先运行最小相关测试，再运行静态检查和完整测试；未执行的门禁必须明确标为 `SKIPPED` 并说明原因。
- 离线测试通过只能证明 Implemented；依赖真实网络、Codex 或 launchd 的能力完成对应真实验收后才能写 Verified。
- 完成后报告实际执行的命令、退出状态、结果和剩余风险，不用“应该可以”代替证据。

## 验收触发规则

- 用户说“按项目验收规则开始验收”“开始验收”，或调用 Claude Code 的 `/acceptance` 时，完整读取并执行 `docs/testing/acceptance-rules.md`。
- 默认验收是只读审查：不得在验收过程中顺手修复、格式化、提交或改写文件；发现问题后先给出证据和结论。
- 用户明确要求“验收并修复”时，先完成并报告首轮验收，再把修复作为独立开发步骤处理，修复后重新验收。
- 用户要求“实施验收”时，固定执行“只读首轮验收 → 独立修复问题 → 修复后复验”；首轮验收不得修改文件，最终只有复验无未解决问题时才可通过。

## Code Review Rules

- 标记任何没有第一方证据却写入 `verified` 的路径。
- 标记任何致命失败后仍覆盖 `latest.json`、非原子写入或破坏历史 run 的路径。
- 标记任何来源错误被吞掉、健康状态失真或退出码与约定不一致的路径。
- 标记任何未同步 Schema 和兼容测试的 JSON 破坏性变更。
- 标记测试只覆盖 mock、却把真实网络或定时能力声称为 Verified 的情况。
