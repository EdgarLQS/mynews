---
title: mynews P5 外部插件分发准备计划
doc_type: plan
status: draft
implementation_status: proposed
version: 1.0
created: 2026-08-23
updated: 2026-08-23
owner: project-maintainers
---

# mynews P5 外部插件分发准备计划

## 定位与当前结论

本文是 v1.7 P5 的前置准备计划，不替代唯一 Current 计划
[v1.7 分时情报分析与人工反馈闭环计划](v1.7-intelligence-loop-plan.md)，也不把 P5
从 `BLOCKED` 改为 `PASS`。当前仓库的插件源码包已经存在，缺少的是在 P5 隔离运行环境中
构建并安装可发现的独立分发产物。

当前事实：

- 本地 `main` 为 `cd29a4d`，v1.7 P0–P4 仍为 `Implemented`；固定 P5 代码基线为
  `e60c0c7`。
- P5-A 离线首验通过：文档检查、Ruff、Mypy、相关测试 117 项、全量测试 291 项和中文
  CLI help 均通过。
- P5-B 在隔离 venv 中发现 `loaded=false`，15 个插件 probe 全部返回
  `plugin_not_found`，因此 P5 继续为 `BLOCKED`。
- `plugins/newsfromai-source-pack/pyproject.toml` 已定义分发包
  `mynews-newsfromai-sources` 0.1.0、`mynews.source_plugins` entry-point group 和 15 个
  entry-point；这不是新增来源开发缺口。
- `paperswithcode-daily` 没有可确认的官方 RSS/Atom daily 入口，安装后也必须保持
  `manual/blocked`，不得请求猜测的 Feed 或伪装为 healthy。

## 目标

在不修改主项目生产代码、CLI、Schema、来源清单和 `verified` 门槛的前提下：

1. 从仓库已有 `plugins/newsfromai-source-pack/` 构建可追溯的本地 wheel；
2. 只把该 wheel 安装到 P5 固定 detached worktree 的隔离 venv；
3. 证明 15 个 entry-point 可发现、可显式加载，并分别记录真实 probe 结果；
4. 通过插件选择和扩展采集兼容门禁后，解除 P5-B 阻断并恢复原 P5 顺序。

## 范围与来源角色

插件 ID、官方入口和域名边界以[信息来源目录](../reference/source-catalog.md)和插件包
`pyproject.toml`为准，不在本计划中重新发明 URL 或 source_id。

| 角色 | entry-point | 验收要求 |
| --- | --- | --- |
| primary | `openai-news`、`google-blog`、`github-changelog`、`hugging-face-blog`、`google-deepmind`、`nvidia-ai`、`aws-machine-learning` | 真实 probe 后才能作为正式候选来源；仍须第一方证据核验 |
| research | `kimi-k2-releases`、`glm-releases` | 真实 probe 后进入研究类候选；不放宽证据门槛 |
| incident | `deepseek-status`、`openai-status`、`anthropic-status`、`github-status` | 真实 probe 后记录服务事件；失败必须结构化保留 |
| discovery | `techcrunch-ai` | 只能发现线索，不能单独产生 `verified` |
| benchmark/manual | `paperswithcode-daily` | 保持 `manual/blocked`，不得请求猜测的 RSS/Atom |

## 分阶段计划

### D0：冻结基线与准备输入

- 从最新本地 `main` 创建本计划分支；本计划交付只包含文档。
- 继续使用 P5 固定提交 `e60c0c7` 和现有 `/private/tmp/mynews-p5-runtime`，不从旧功能分支
  继续开发。
- 记录 Python 3.12、uv、插件包版本、构建命令、wheel SHA-256 和隔离 venv 路径。
- 不安装到仓库 `.venv`，不修改 `output/`、`state/`、源码、文档、publication ledger 或
  weekly feedback。

### D1：构建本地分发产物

在仓库外临时目录构建，不提交 wheel：

```bash
uv build \
  --project plugins/newsfromai-source-pack \
  --out-dir /private/tmp/mynews-p5-plugin-package/dist
```

构建后检查：

- 包名为 `mynews-newsfromai-sources`，版本与源码元数据一致；
- wheel 包含 `mynews_newsfromai_sources` 和 `*.dist-info/entry_points.txt`；
- 15 个 entry-point 与来源目录完全一致；
- 依赖只有已声明的兼容主包，不新增主项目生产依赖；
- 构建失败记为 `FAIL`，缺少构建环境或权限记为 `BLOCKED`，不绕过构建系统直接复制源码。

### D2：仅在隔离 venv 安装

在 P5 worktree 的 `logs/p5/runtime/` 下固定 venv、uv cache、Python 字节码和工具 cache，
再安装 D1 wheel。安装动作只作用于该 venv，并记录：

- wheel 绝对路径、SHA-256、安装时间和 Python/uv 版本；
- `importlib.metadata` 读取到的包版本和 entry-point group；
- 安装前后主仓库、固定 worktree 已跟踪文件和人工台账校验值；
- 运行目录之外没有 `.venv`、pytest/mypy/ruff cache 或 `__pycache__`。

### D3：发现、加载与逐源 probe

使用与 P5 相同的隔离权限和环境：

1. `mynews plugin list` 必须发现 15 个 ID；
2. 对上表 15 个 ID 逐一执行 `mynews plugin probe --plugin <id>`；
3. 记录安装状态、工厂加载结果、来源状态、抓取数、接受数、限制、退出码和时间；
4. primary/research/incident 的健康结果不能直接写入 `verified`，仍须运行既有证据核验；
5. discovery 只保留线索，manual 只保留 `manual/blocked`；
6. 任一工厂异常、metadata 冲突或协议错误都停止后续 P5，不用其它来源替代。

### D4：兼容与扩展采集门禁

插件就绪后先完成离线和同权限兼容检查，再恢复 P5-B 手动彩排：

- 默认 `collect/probe` 不加载外部插件；
- `--plugin` 保持 plugin-only；
- `--with-plugin` 保持 built-in + 显式插件追加；
- RunReport 的 `requested_range.source_ids` 记录实际选择顺序；
- `plugins/newsfromai-source-pack/tests` 和受影响项目测试通过；
- `scripts/collect-expanded.sh --days 2` 的失败、partial、输出保护和来源隔离保持原契约；
- 不以 fixture、`plugin list` 或一次空 Feed 结果代替真实 probe。

### D5：解除阻断并恢复 P5

D0–D4 全部通过后，才把 P5-B 从 `BLOCKED` 重新评估为可执行，继续原 v1.7 计划：

1. 复用五步手动彩排：`prepare --refresh` → 扩展采集 → evidence validate → digest → 报告；
2. 彩排通过后才注册一个项目级 Scheduled Task；不操作旧 09:30 launchd；
3. 观察 09:00/18:00、latest-only、前置失败保护、报告先于状态和恢复运行；
4. 只有全部真实场景通过，才允许 P5-E 回写 `AI-02`、`DATA-07`、`OPS-04` 的真实状态。

## 验收门禁

| 门禁 | 通过条件 | 失败处理 |
| --- | --- | --- |
| PKG-01 来源映射 | 15/15 ID 与 source catalog、entry-point 完全一致 | 映射缺失或冲突为 `FAIL` |
| PKG-02 构建产物 | wheel 元数据、版本、entry-point 和 SHA-256 可复查 | 构建错误为 `FAIL`；环境缺失为 `BLOCKED` |
| PKG-03 隔离安装 | 只写 P5 runtime，主仓库和台账校验值不变 | 越界写入或残留为 `FAIL` |
| PKG-04 加载协议 | 15 个 entry-point 可发现、无参数工厂可加载、协议校验通过 | 未安装/不可发现为 `BLOCKED`；工厂/协议错误为 `FAIL` |
| PKG-05 真实来源 | 每个 ID 有独立 probe 证据；manual/discovery 角色保持边界 | 网络或访问限制如实 `BLOCKED`，不得降级伪装 |
| PKG-06 兼容性 | 默认、plugin-only、追加模式和扩展脚本回归通过 | 破坏公共契约为 `FAIL` |
| PKG-07 P5 解锁 | D0–D5 通过且可进入同权限手动彩排 | 任一必需门禁未满足则 P5 保持 `BLOCKED` |

## 非目标与禁止事项

- 不新增来源、不改 RSS/Atom URL、不改 SourcePlugin 1.0、Candidate、Digest 或 RunReport Schema；
- 不把插件源码包合并进主 wheel，不新增主项目生产依赖；
- 不自动发布、不生成 PPT/图片/Canva/TTS/视频；
- 不安装或操作旧 09:30 launchd，不在 P5-B 阻断时注册 Scheduled Task；
- 不把 `plugin list`、fixture、mock、空 Feed 或单次手动运行写成 `Verified`；
- 不修改 `output/`、`state/`、`logs/` 之外的验收产物，不提交 wheel、runtime cache 或秘密；
- 不因本计划改变 v1.7 Current 或提前激活 v1.8 Draft 路线图。

## 交付物与状态回写

本计划本身保持 `Draft / Proposed`。D1–D4 的离线和隔离证据最多证明插件分发准备
`Implemented`；只有真实来源 probe、P5 双档、latest-only 和恢复场景全部通过后，才由
v1.7 计划按治理矩阵回写对应能力。P5 仍为 `BLOCKED` 时，不能更新功能矩阵的 Verified
状态，也不能启动 v1.8。

验收记录必须包含：固定提交、wheel SHA-256、安装路径、命令和退出码、15 个 source_id 的
逐项结果、隔离目录校验值、失败限制和未执行门禁。运行产物只留在隔离目录，不进入 Git。

## 计划分支与后续分支

本计划从 `main@cd29a4d` 创建 `codex/p5-plugin-distribution-plan`，完成文档检查后再由用户
决定是否 fast-forward 合入本地 `main`；不自动 push。真正执行 D1–D5 时，继续使用固定 P5
worktree；若需要修改源码或插件包，必须另立独立实施分支，不在验收 worktree 内修复。
