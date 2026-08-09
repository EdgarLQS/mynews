---
title: mynews 阶段 1 功能验收说明
doc_type: test
status: current
implementation_status: implemented
version: 1.0
created: 2026-08-02
updated: 2026-08-09
owner: project-maintainers
---

# mynews 阶段 1 功能验收说明

## 结论

`PASS`（阶段 1 G0–G4）。本说明是当前分支进入后续开发计划前的功能交接依据；不代表完整
v1 发布验收，也不把离线通过写成真实来源或定时能力的 `Verified`。

验收日期：2026-08-02（Asia/Shanghai）

## 范围与基线

- 仓库：`/Users/edgarlqs/Downloads/mynews`
- 分支：`codex/v1-phase1-scaffold`
- 基线：`main=8acafc2`
- 当前提交：`HEAD=5008094`
- 范围：`main...HEAD` 的 2 个提交、23 个文件，以及验收时的全部工作树状态
- 工作树：无未提交、未跟踪或暂存变更

当前分支包含两个功能增量：

1. Python 3.12 + uv 工程骨架、中文 CLI 参数契约、Pydantic v1 领域模型和 JSON 兼容 fixture。
2. CC Switch 官方 GitHub Release 的离线“新功能”解析 Adapter 和 v3.19.1 fixture。

## 已验收功能

### CLI 契约

- `mynews --help`、`collect --help`、`probe --help` 和 `scripts/collect.sh --help` 可执行。
- 日期选择器、时区边界、`--from/--to` 配对和非法日期均有测试。
- 帮助和参数错误使用中文；帮助退出码为 0，非法参数退出码为 2。
- `collect` 和 `probe` 的真实采集运行时仍未实现，当前只验收阶段 1 契约。

### JSON 与领域模型

- 已定义 `CollectionRequest`、`Candidate`、`Evidence`、`NewsItem`、`SourceResult` 和
  `RunReport`。
- `verified` 条目必须具备通过 `reachable`、`official_domain`、`excerpt_matched` 的第一方证据。
- 非 `healthy` 来源必须带结构化错误。
- 接受 `1.x` minor 版本和未知字段，拒绝未知 major 版本。
- fixture 与模型可离线互读；JSON Store 和原子写入尚未实现。

### CC Switch 离线 Adapter

- 只接受 `farion1231/cc-switch` 的稳定 Release。
- `## 新功能` 下的每个 `###` 条目生成一个候选。
- 保留官方 Release 发布时间；未知发布时间保持 `null`。
- 非官方 Release URL、预发布、缺失字段和非法日期会失败或被跳过。
- 尚未接入 SourcePlugin registry、共享 HTTP client、CLI 运行时和真实 `probe`。

## 门禁证据

| 门禁 | 实际命令/检查 | 结果 |
| --- | --- | --- |
| G0 | Git 范围、功能矩阵、实施计划和当前状态人工核对 | PASS；无越界状态夸大 |
| G1 | `python3 scripts/check_docs.py` | PASS；17 个 Markdown 文件，0 个错误 |
| G1 | `git diff --check main...HEAD`、`git diff --check` | PASS |
| G2 | `UV_CACHE_DIR=/tmp/mynews-uv-cache uv run ruff check .` | PASS；All checks passed |
| G2 | `UV_CACHE_DIR=/tmp/mynews-uv-cache uv run mypy src` | PASS；6 个源文件无问题 |
| G3 | 受影响测试文件 + `UV_CACHE_DIR=/tmp/mynews-uv-cache uv run pytest` | PASS；30 passed，0 skipped |
| G4 | 全局/子命令/脚本 help | PASS；退出码 0 |
| G4 | 未知命令、缺失参数、非法日期 | PASS；退出码 2，中文错误 |
| G4 | `UV_CACHE_DIR=/tmp/mynews-uv-cache uv run pytest tests/test_models.py -q` | PASS；8 passed |

## 问题与限制

本轮未发现由当前分支变更引入的阶段 1 G0–G4 缺陷。

未执行的 G5、G6-S、G6-V、G7 不纳入本阶段结论。它们对应离线集成、真实来源、真实核验、
运维和七天回溯，必须在后续计划中单独验收。

## 后续开发交接

后续工作当时进入 [v1.1 计划](../archive/plan/2026/v1.1-information-quality-plan.md)，其原始实施和验收记录现已归档；当前实施入口为 [v1.3 计划](../planning/v1.3-intelligence-digest-plan.md)。阶段 1 交接时约定的优先顺序为：

1. 建立 built-in `SourcePlugin` registry 和稳定内部接口。
2. 增加共享 HTTP client、超时、有限重试、User-Agent、并发上限和缓存头。
3. 将 CC Switch Adapter 接入运行时和 `probe`，对失败输出结构化健康状态。
4. 为 Hacker News 和其他官方 Feed/GitHub Release 增加 Adapter fixture 与 live probe。
5. 完成后执行 G5、G6-S，并保持 `SRC-07` 为 `In progress`，直到真实 probe 通过。

下一阶段不得把本说明中的离线测试结果当作真实来源、Codex、Store、launchd 或七天回溯的验收证据。
