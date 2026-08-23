---
name: plan-implement
description: Maintain the current project phase and produce repository-grounded implementation handoffs plus staged acceptance-and-fix instructions. Use for current progress, next-phase plans, implementation or acceptance instructions, source/plugin expansion, cross-session handoffs, and project decision summaries.
---

# 计划与实施

把当前项目状态转换成可执行、可验收、可复制的开发交接。先读取仓库事实，再输出计划；不得用历史聊天或旧计划猜测当前实现。

## 工作流

1. 确认 `pwd`、当前分支、Git 状态、未提交和未跟踪文件；保护不属于本任务的变更。新阶段实施必须以已包含上一阶段交付的最新 `main` HEAD 为基线，再创建新的 `codex/<phase>` 分支；不得直接从旧阶段分支续做。
2. 从 `docs/README.md` 进入文档体系，读取功能矩阵、`docs/planning/README.md` 和唯一 Current 计划，再按变更类型读取架构、来源目录、ADR 和数据契约。用户要求验收时完整读取 `docs/testing/acceptance-rules.md`。
3. 以 `docs/README.md` 和功能矩阵判断实现状态；用 `Proposed`、`Implemented`、`Verified`、`BLOCKED`、`FAIL` 区分设计、离线实现和真实能力。发现用户口径与文档冲突时，指出冲突并要求实际证据，不能自行改写状态。
4. 判断请求类型：
   - “当前进度/下一步”：说明已完成能力、未完成门槛和推荐下一阶段。
   - “实施说明”：生成新分支、范围、接口、文档同步、测试和禁止事项。
   - “验收说明/实施验收”：生成三段式流程：首轮只读验收、独立修复发现的问题、修复后的完整复验；首轮只读期间不得修改文件。
   - “总结本会话”：只提炼稳定的用户目标、已确认决策、当前事实、未决风险和下一步，不把临时运行产物当作代码能力。
5. 多文件或多步骤任务先给不超过 5 句话的策略与验证计划；交接内容使用 `references/templates.md` 的结构。

## 项目不变量

- 当前实现以 `docs/README.md` 为准，产品范围以 `docs/product/feature-matrix.md` 为准，当前顺序以 `docs/planning/` 为准。
- 同一主题只能有一份 Current 计划；被替代计划按 `docs/GOVERNANCE.md` 归档并登记索引。
- 只有官方公告、文档、价格页、官方仓库或发行说明经程序复核后才能是 `verified`；发现渠道、媒体、搜索摘要和模型回答不能单独证明事实。
- 离线测试只能证明 `Implemented`；依赖真实网络、生产 Codex 或定时器的能力必须执行对应真实验收后才可写 `Verified`。外部阻断写 `BLOCKED`，程序错误写 `FAIL`。
- 任何来源失败、Codex 失败或存储失败都必须结构化记录，不能静默成功、污染 `latest.json` 或覆盖历史 run。
- 外部来源计划必须区分主 wheel、独立插件分发包、默认 built-in、plugin-only 和追加扩展模式；来源清单以 Current 计划和来源目录为准，不能从另一个仓库的旧测试推断。
- v1.6 已按 Implemented 归档，收集功能没有新的计划缺口；来源健康、真实 Codex 和定时结果仍分别标为 Verified、BLOCKED 或 FAIL。
- 唯一 Current 是 `docs/planning/v1.7-v2.0-master-plan.md`；M0–M7 按顺序和独立分支推进，前一阶段未 PASS 并合入最新 `main` 时不得启动下一阶段。
- v1.7 P0–P4 已归档为 Implemented：分析层使用根目录 `news-task.md`，固定 Asia/Shanghai 双档、latest-only、报告先于状态；不得新增核心 Briefing 模型或放宽 Digest 主榜；只有 publication/feedback 人工回填进入确定性 CLI，P5 真实双档仍待授权。
- `ApplicationRuntime`、`ArtifactCommitter`、`evaluate`、`ops` 和 `editorial review` 在对应阶段落地前都只是 Planned/Proposed，不能从总计划推断已实现。
- 默认不操作真实 launchd，不修改或提交 `output/`、`state/`、`logs/` 运行产物。

## 实施交接要求

实施说明必须明确：

- 从哪个基线创建什么 `codex/` 分支；是否允许修改和提交。
- 基线必须是已合入上一阶段交付的最新 `main`；若 `main` 未包含上一阶段提交，先停止并报告，不从旧阶段分支绕行。
- 本阶段目标、非目标、公共 CLI/JSON/模块接口和兼容规则。
- 涉及来源或插件时，明确每个 source_id、角色、官方边界、安装/显式加载方式，以及普通采集如何保持兼容。
- 需要同步的计划、架构、ADR、功能矩阵、README、数据契约和 AI 入口。
- 最小相关测试、静态检查、全量测试、真实环境门禁和成功判定。
- 不得顺带重构、扩展未经批准的来源、绕过访问控制或把 mock 当作真实验收。
- 批准或实施统一总计划不等于授权真实 P5；只有用户再次明确要求“开始 P5 真实验收”后，才允许真实网络 probe、Scheduled Task 注册或故障恢复演练。v1.7 实施不得操作真实 launchd、修改人工台账或生成平台素材。
- v1.7 人工回填必须验证 Candidate 的 `duplicateGroupId` 优先匹配、带时区 HTTPS 链接、ISO 周非负指标、幂等/冲突/replace，以及隐私和原子恢复；不得调用网络、Store、Codex 或修改 `verified`。

## 验收交接要求

验收说明必须明确：

- 以目标分支与 `main` 的 merge-base 为基线，覆盖提交、未提交和未跟踪文件。
- 首轮只读执行；不得在首轮修复、格式化、暂存、提交、切换分支或污染运行目录。
- 实际执行文档检查、`git diff --check`、Ruff、Mypy、相关测试、全量测试和中文 CLI help；未执行项标 `SKIPPED` 并说明原因。
- 对真实来源、生产 Codex、隔离回溯和定时能力分别判定；只能 mock 或外部阻断不得 PASS。
- 外部来源变更分别验收 entry-point 发现、工厂加载、默认采集、plugin-only、追加扩展采集和每个 source_id 的 live probe；插件未准备不得静默跳过。
- 输出安全或人工清单变更检查敏感值不回显、无网络/Store 副作用、原子失败恢复和旧输出保护。
- v1.7 还要检查 task 双档/latest-only、verified/lead 隔离、报告先于状态推进，以及 publication/feedback 的人工确认、幂等和冲突规则。
- 首轮只读后，逐项记录问题、严重性、文件和证据；修复作为独立开发步骤，不能在首轮验收中顺手修改。
- 修复完成后重新运行受影响门禁和完整验收；只有复验无未解决问题时才能给 `PASS`。外部阻断为 `BLOCKED`，程序问题为 `FAIL`。
- 报告使用“计划、执行、验证”结构，并分别说明首轮发现、修复结果和复验结果。

## 结果格式

面向用户的内容简洁直接。开发交接和验收交接分别放入可复制代码块；不要把“建议”“已实现”“已验证”混用。若当前事实不足，保留为待确认门槛而不是猜测补全。

详细模板见 [references/templates.md](references/templates.md)。
