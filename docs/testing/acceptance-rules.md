---
title: mynews 项目验收规则
doc_type: test
status: current
implementation_status: implemented
version: 1.2
created: 2026-08-02
updated: 2026-08-11
owner: project-maintainers
---

# mynews 项目验收规则

## 目的与调用方式

本规则用于开发完成后的独立验收，回答“改了什么、要求哪些门禁、实际通过了什么、还有哪些未验证”。

- 通用触发语：`按项目验收规则开始验收` 或 `开始验收`。
- Claude Code：输入 `/acceptance`；可在后面补充文件、提交或功能范围。
- 未指定范围时：验收当前工作树相对 `HEAD` 的全部已跟踪和未跟踪变更。
- v1.2 的真实 G6-S、G6-V、G7 结果见[归档验收清单](../archive/testing/2026/v1.2-real-environment-acceptance.md)；当前开发按唯一 [v1.7 Current 计划](../planning/v1.7-intelligence-loop-plan.md) 的 P0–P5 执行。

验收默认只读。除非用户明确要求“验收并修复”，验收人员不得修改、格式化、提交或删除项目文件。

## 结论口径

验收只能给出以下结论之一：

| 结论 | 使用条件 |
| --- | --- |
| `PASS` | 所有必需门禁通过，没有未解释的必需项跳过 |
| `PASS_WITH_LIMITATIONS` | 用户明确要求部分验收，已声明范围内门禁通过，但不能代表完整发布验收 |
| `FAIL` | 发现由验收范围内变更造成的缺陷、回归或规则违反 |
| `BLOCKED` | 必需门禁因网络、权限、凭据、服务或缺失环境无法执行，不能判定通过或失败 |

`SKIPPED` 只能描述单项门禁，不是最终结论。完整验收中只要必需门禁被跳过，最终结论必须是 `BLOCKED`。

## 验收流程

### 1. 固定范围与基线

1. 确认仓库根目录和当前分支。
2. 记录 `git status --short`、验收基线和目标范围。
3. 默认基线为 `HEAD`；用户指定提交、分支或范围时使用指定 fixed point。
4. 列出已修改、已新增、已删除和未跟踪文件；未跟踪文件不能遗漏。
5. 从 [功能矩阵](../product/feature-matrix.md) 和活动计划提取本次需求及状态口径。

### 2. 选择门禁

先按变更类型选择必需门禁，再执行命令。一个变更命中多类时取并集。

| 变更类型 | 必需门禁 |
| --- | --- |
| 仅文档、AI 指令或验收规则 | G0、G1；技能变化时加 G1-S |
| CLI、日期解析、退出码 | G0、G1、G2、G3、G4 |
| 领域模型、规范化、排序、去重 | G0、G1、G2、G3、G5 |
| SourcePlugin 或来源配置 | G0、G1、G2、G3、G5、G6-S |
| 外部插件分发包、插件选择或扩展采集脚本 | G0、G1、G2、G3、G4、G5、G6-S；涉及调度时再加 G7 |
| 核验器或 verified 判定 | G0、G1、G2、G3、G5、G6-V |
| JSON Schema、Store、latest、状态快照 | G0、G1、G2、G3、G4、G5 |
| 人工清单、可分享输出安全或原子文本输出 | G0、G1、G2、G3、G4、G5 |
| Codex 任务文档、分时报告或任务状态 | G0、G1、G1-S、G4、G5；执行真实 Codex 或定时任务时增加 G6-V、G7 |
| launchd、安装脚本或运行脚本 | G0、G1、G2、G3、G7 |
| v1 阶段完成或发布候选 | G0 至 G7 全部适用项 |

### 3. 执行门禁

| ID | 门禁 | 最低要求 |
| --- | --- | --- |
| G0 | 范围与需求一致性 | 对照需求、计划和功能矩阵检查漏项、越界改动和状态夸大 |
| G1 | 仓库与文档质量 | `python3 scripts/check_docs.py` 和 `git diff --check` 通过；索引和状态同步无误 |
| G1-S | AI 技能有效性 | `SKILL.md` frontmatter 和目录名有效；入口只引用权威计划/验收规则；关联 UI metadata 与技能描述一致；目标工具可用时再检查实际发现 |
| G2 | 静态质量 | `uv run ruff check .` 与 `uv run mypy src` 通过；尚未建立代码骨架时仅文档变更可记为不适用 |
| G3 | 自动化测试 | 先运行受影响测试，再运行 `uv run pytest`；报告测试数量、失败和跳过 |
| G4 | 外部契约 | 全局/子命令/脚本 help、非法参数、退出码和 JSON Schema 兼容测试通过；插件选择变化还要覆盖默认、plugin-only 和追加模式 |
| G5 | 离线集成 | Adapter fixture、Fake Verifier、跨运行去重、原子写入和失败恢复覆盖对应变更；扩展采集必须证明同一 Run 同时保留 built-in 与插件来源，未安装插件不得静默降级 |
| G6-S | 真实来源 | 对每个受影响 source_id 独立执行 live probe，记录时间、插件安装状态、状态、抓取/接受数和限制；实验来源允许如实 `blocked`，但不能伪装成功或用其他来源代替 |
| G6-V | 真实核验 | 至少一个已知候选完成真实 Codex 核验和程序二次校验；第一方 URL、域名、日期与摘录可复查 |
| G7 | 运维与回溯 | 脚本 help 可执行，`plutil -lint` 通过；涉及 v1 完成时执行七天回溯并校验 JSON 与 verified 证据 |

不得用下列证据替代门禁：

- 只阅读代码，未运行本可运行的测试。
- 只运行 mock，却声称真实来源、Codex 或 launchd 已验证。
- 使用搜索摘要、转载或模型回答证明新闻真实。
- 因命令预计会失败而省略执行，却不标记 `SKIPPED` 或 `BLOCKED`。
- `plugin list` 发现了 entry-point，却没有执行工厂、真实 probe 或扩展采集。
- 只验证新增插件来源，却没有回归普通 collect/probe 的原有来源选择。

### v1.5/v1.6 来源与 editorial 继承判定

- 当前 v1.6 代码状态：P0–P6 的离线实现可以标为 `Implemented`；P7 已执行逐源
  `prepare` registry probe，但受限/人工入口必须继续记录为 `BLOCKED` 或 `partial`，不得
  把 fixture、mock 或空 Feed 结果写成 `Verified`。
- v1.5 的独立来源分发包、`--plugin` 和 `--with-plugin` 兼容边界继续有效；首轮只读验收
  不得临时安装或改写环境。必需插件未准备导致无法执行时写 `BLOCKED`，仓库缺少计划内
  分发包或入口写 `FAIL`。
- 普通 collect/probe 必须保持只使用 built-in；`--plugin` 继续 plugin-only；
  `--with-plugin` 才允许在同一运行中追加插件来源。
- v1.6 归档计划列出的 17 个 source_id 必须逐一判定；`qwen-blog-rss` 和
  `hacker-news` 是 prepare registry 中的配置来源，不能把旧 built-in 选择重复加入同一
  次 prepare；不存在于当前来源配置的 arXiv 测试期望不得被计入覆盖率。
- fixture 与隔离 entry-point 测试最高证明 Implemented。单个来源只有真实 probe
  `healthy` 且解析到有效记录后才可写 Verified；网络或访问限制写 BLOCKED。
- 可分享输出安全测试必须确认异常不回显敏感值，原子写入失败不覆盖旧文件且不遗留
  `.tmp`；不得通过关闭检查或改写已保存证据来获得 PASS。
- editorial 输出还必须确认无 refresh 不重新请求来源，refresh 才追加观察，候选包不超过
  500 条，并且 `firstSeenAt <= generatedAt`。

### v1.7 分时任务与人工反馈专项判定

- `news-task.md` 是已实施的离线任务契约，不等于已注册或运行的 Codex 任务；静态文档、
  mock 或单次人工摘要最多证明 Implemented，真实 09:00/18:00 双档和 latest-only 补跑
  完成后才可判定对应 Verified。
- 正式情报只能引用 Digest `main_items` 的 `verified` 条目；Candidate、manual watchlist、
  discovery 和 `lead_items` 只能作为待核查线索，不能通过任务文案升级事实状态。
- `prepare`/collect 返回 `3 (partial)` 时必须保留结构化失败并检查必要输出；返回 `1/2`、
  evidence validation 失败或输出不完整时不得覆盖已有报告或推进成功档位。
- 任务报告必须先原子提交，再更新状态；`reportedEvents` 只能保存事件键、时间、哈希和
  相对路径，不得包含密钥、Cookie、授权头或个人绝对路径。
- 分时任务不得自动修改 publication ledger 或 weekly feedback，不得生成平台素材或发布。
- `publication add` 必须校验 Candidate event ID、完整公开链接和带时区时间；多事件分别
  记录，完全重复幂等，缺失信息不得写占位行。
- `feedback record` 必须校验 ISO 周和非负指标；冲突默认失败，只有显式 `--replace` 才能
  替换稳定区块。两个回填命令都必须无网络/Store/Codex 副作用，并通过隐私和原子恢复测试。

### 4. 区分新增问题与既有问题

- 先判断失败是否由验收范围内变更引入；有证据时分别标记“本次引入”或“预先存在”。
- 无法证明归属时标记“归属未确认”，不得擅自忽略。
- 预先存在的问题不自动导致本次变更 `FAIL`，但若它阻止必需门禁执行，结论仍为 `BLOCKED`。
- 发现问题时给出文件、行号、复现命令、实际结果和期望结果。

### 5. 输出验收报告

报告必须自包含，采用以下结构：

```text
结论：PASS | PASS_WITH_LIMITATIONS | FAIL | BLOCKED
范围：<文件、提交或功能>
基线：<commit/ref>

变更核对：<需求覆盖与越界情况>

门禁结果：
| 门禁 | 是否必需 | 命令/检查 | 结果 | 证据 |

问题：<按严重程度列出；没有则写“无”>
SKIPPED/BLOCKED：<项目、原因、解除条件>
预先存在的问题：<单独列出>
剩余风险：<无法由本轮证明的事项>
```

每条命令必须记录真实结果；不得把“计划执行”“理论可行”写成已通过。依赖真实环境的验证还要记录执行日期、环境边界和必要的脱敏信息。

## 状态回写

- `PASS` 后才允许按 [文档治理规范](../GOVERNANCE.md) 更新计划和功能矩阵。
- 只有离线门禁通过时，功能最高为 `Implemented`。
- G6 或 G7 中对应的真实门禁通过后，相关功能才可标为 `Verified`。
- `FAIL` 或 `BLOCKED` 不得把功能状态上调；修复后必须重新执行受影响门禁。
