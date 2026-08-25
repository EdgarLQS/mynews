---
title: mynews 功能矩阵
doc_type: matrix
status: current
implementation_status: implemented
version: 1.7
created: 2026-08-02
updated: 2026-08-23
owner: project-maintainers
---

# mynews 功能矩阵

本表是产品范围和实现状态的唯一真相来源。唯一 Current 的统一总计划从 v1.7 P5 收口推进到
v2.0；v1.7 分时情报分析和人工反馈闭环的 P0–P4 已按 Implemented 落地，真实双档仍未验收。
`paperswithcode-daily` 当前为
manual/blocked。外部插件仍是受信任本地 Python 代码，显式清单只控制加载，不承诺进程级
沙箱。真实 Codex 任务和 launchd 未经授权不加载。

状态：`Planned`、`In progress`、`Implemented`、`Verified`、`Future`、`Out`。

| ID | 领域 | 功能 | 当前状态 | 验收入口 |
| --- | --- | --- | --- | --- |
| DOC-01 | 治理 | 文档索引、状态、计划和归档机制 | Implemented | `python3 scripts/check_docs.py`；唯一 Current 计划和运行目录保护 |
| AI-01 | 协作 | `AGENTS.md` 与 `CLAUDE.md` 共用项目规则 | Implemented | 指令入口检查 |
| AI-02 | 协作 | `news-task.md` 驱动 09:00/18:00 分时情报任务 | Implemented | 元数据、latest-only、证据隔离和失败停止；P5 已开始但 G6-V/真实双档当前 BLOCKED |
| ARCH-01 | 架构 | 深 `ApplicationRuntime` 与 CLI 薄 Adapter | Planned | 统一总计划 M2；P5 PASS 后实施，公共 CLI/JSON 行为不变 |
| ARCH-02 | 架构 | 统一 `ArtifactCommitter` 文件提交 module | Planned | 统一总计划 M3；失败恢复、latest 和报告先于状态语义保持兼容 |
| ARCH-03 | 架构 | 共享结构化 Codex 进程 Adapter | Planned | 统一总计划 M6；只统一进程机制，不合并领域 prompt 或复核 |
| QA-01 | 验收 | 统一验收规则、Claude `/acceptance` 与真实环境交接 | Implemented | 验收规则 + v1.2 真实环境清单 |
| CLI-01 | CLI | 全局、子命令和脚本中文 `--help` | Implemented | `uv run mynews --help`、子命令和脚本 help |
| CLI-02 | CLI | 默认最近 24 小时收集 | Implemented | 日期边界 + 流水线测试 |
| CLI-03 | CLI | `--days`、`--date`、`--from/--to` 参数契约与时区校验 | Implemented | 日期参数测试 |
| CLI-04 | CLI | 结构化退出码 0/1/2/3 | Implemented | 来源状态与流水线测试 |
| CLI-05 | CLI | RunReport/Schema/verified 证据校验命令 | Implemented | `mynews validate`；离线 Schema/结构检查与可选逐条重抓 |
| CLI-06 | CLI | 从 RunReport 离线生成中文 Markdown `mynews report` | Implemented | report fixture、中文 help 和文件输出测试 |
| CLI-07 | CLI | `mynews digest` 及其输出、条数、摘要模型/超时、推理强度、`--no-codex` 和人工查看线索 | Implemented | Digest fixture、中文 help、推理参数、回退、线索链接和原子输出测试 |
| CLI-08 | CLI | `plugin list`、`plugin probe --plugin` 及 collect/probe 的显式 `--plugin` 选择 | Implemented | 中文 help、非法参数、退出码、entry-point 发现和 source selection 测试 |
| CLI-09 | CLI | collect/probe 的 `--with-plugin` 追加选择与扩展采集脚本 | Implemented | 默认采集不变；扩展运行同时记录 built-in 与插件来源；P6 真实组合采集已记录，Codex G6-V 仍 SKIPPED/BLOCKED |
| CLI-10 | CLI | `mynews watchlist` 人工官方页面检查清单 | Implemented | Pydantic 契约、确定性 Markdown、无网络/Store/Codex 副作用 |
| CLI-11 | CLI | `mynews prepare --date` 与 `--refresh` editorial 候选包 | Implemented | 日期重放、refresh、中文 help、0/1/3 退出码和失败恢复测试 |
| CLI-12 | CLI | `mynews publication add` 人工发布记录 | Implemented | Candidate ID、多事件、幂等、缺失字段、CSV 兼容和原子恢复 |
| CLI-13 | CLI | `mynews feedback record` 周反馈记录 | Implemented | 指标校验、稳定区块、冲突/replace、隐私和原子恢复 |
| CLI-14 | CLI | `mynews evaluate` 可重复质量评估 | Planned | 统一总计划 M4；独立 QualityEvaluation 1.0 JSON/Markdown |
| CLI-15 | CLI | `mynews ops` 诊断、保留计划与隔离恢复检查 | Planned | 统一总计划 M5；不自动删除或原地覆盖 |
| CLI-16 | CLI | `mynews editorial review` 周复盘与只读建议 | Planned | 统一总计划 M7；数据不足 partial，Codex 可选且可回退 |
| SRC-01 | 来源 | Hacker News 官方 API | Verified | fixture + 既有真实 probe；v1.2 目标环境重新执行 G6-S |
| SRC-02 | 来源 | 官方 RSS/Atom/API、GitHub Release 与官方 HTML 更新页 | Implemented | fixtures、Adapter 测试和目标环境 G6-S |
| SRC-03 | 来源 | 官方价格页和更新日志监控 | Implemented | 首观快照、规范化差异与 `pricing_change` 测试 |
| SRC-04 | 来源 | 知乎热榜实验 Adapter | Implemented | 公开元数据 fixture；登录/受限时结构化 `blocked` |
| SRC-05 | 来源 | Bloomberg 实验 Adapter | Implemented | 公开元数据 fixture；不读取付费墙内容 |
| SRC-06 | 来源 | 国内外 AI 与重点科技官方来源 | Verified | 既有真实来源验收；v1.2 目标环境重新记录 G6-S 限制 |
| SRC-07 | 来源 | CC Switch 官方 Changelog 新功能监控 | Verified | fixture 与既有真实 probe |
| SRC-08 | 来源 | newsFromAI 核对得到的 15 个独立来源插件（含 1 个 manual） | Implemented | 14 个 RSS/Atom fixture、1 个明确 manual/blocked entry-point、entry-point、域名/组织校验和隔离测试；修复后 G6-S 已复验：12 个有效记录、2 个合法空 Feed、1 个 manual/blocked |
| SRC-09 | 来源 | newsFromAI 当前 25 个自动 Feed 配置映射 | Implemented | `config/newsfromai-feeds.json`、25/25 映射、RSS/Atom 失败隔离和 freshness 测试；真实 probe 仍按 P7 记录 |
| PIPE-01 | 处理 | 规范化、相关性、热度分离 | Implemented | Normalizer 与相关性回归测试 |
| PIPE-02 | 处理 | 跨来源、跨日期、跨运行去重 | Implemented | 批内与跨运行状态恢复测试；目标环境 G7 |
| PIPE-03 | 处理 | discovery AI/科技确定性筛选与质量统计 | Implemented | 词边界、HTML/URL 清理和统计测试 |
| VER-01 | 核验 | 第一方官方证据直接核验 | Verified | 既有官方直验；v1.2 严格门槛回归通过 |
| VER-02 | 核验 | 可配置 Codex Verifier、推理强度与单次候选预算 | Implemented | Fake/预算/批次/推理参数测试；strict JSON Schema 兼容回归通过；真实候选 G6-V 仍 BLOCKED |
| VER-03 | 核验 | URL、域名、重定向、摘录、日期和哈希二次校验 | Implemented | 伪造来源、跨域重定向和严格契约测试 |
| VER-04 | 核验 | discovery 候选进入生产 Codex，模型不得扩大白名单 | Implemented | discovery 主页域名不会进入核验白名单；离线 seam 和生产 CLI 协议兼容已通过；真实 `codex_primary_evidence` G6-V 未满足 |
| VER-05 | 核验 | Pending 独立重试、次数上限和 TTL | Implemented | 越过去重重试、终止原因和失败来源保护测试；目标环境 G7 记录真实样本 |
| VER-06 | 核验 | 证据生命周期 current/changed_supporting/failed | Implemented | 生命周期、降级和 validate warning 测试 |
| DATA-00 | 数据 | Pydantic RunReport 1.x 兼容契约 | Implemented | 1.0/1.1 读取兼容和 1.2 严格性测试 |
| DATA-01 | 数据 | 每次运行独立 JSON | Implemented | JSON Store 追加运行测试；目标环境 G7 |
| DATA-02 | 数据 | run/latest/dedup/pending 事务提交与失败保护 | Implemented | 注入替换失败、完整回滚和 failed 保护测试 |
| DATA-03 | 数据 | 去重、pending、价格和来源快照 JSON | Implemented | 重启恢复、状态演进和快照测试 |
| DATA-04 | 数据 | report/digest/watchlist 可分享输出隐私门禁与 report 原子写入 | Implemented | 敏感值不回显、失败不覆盖旧文件、无临时文件残留 |
| DATA-05 | 数据 | Candidate Contract v1、公开 JSON Schema、兼容读取和匹配统计 | Implemented | Schema/旧 categories 读取、最多 500 条、`firstSeenAt <= generatedAt` 和隐私门禁 |
| DATA-06 | 数据 | editorial 观察历史、first-seen、source family、重复观察和保守事件聚类 | Implemented | `duplicateGroupId`、`multiSources`、`repeat_count` 和跨来源误合并测试 |
| DATA-07 | 数据 | 分时报告和任务状态的原子写入与 latest-only 演进 | Implemented | 报告先提交、状态后推进、失败恢复、相对路径和无敏感值；P5 真实双档当前 BLOCKED |
| DATA-08 | 数据 | QualityEvaluation、Operations、EditorialReview 独立 1.0 Schema | Planned | 各阶段独立契约；不修改 RunReport、Candidate、Digest 或 automation state |
| EDITORIAL-01 | 编辑 | candidates JSON/Markdown、完整 manual watchlist、publication history 和 weekly feedback 提示 | Implemented | 确定性输出、人工只读台账、失败状态和原子多文件写入 |
| EDITORIAL-02 | 编辑 | 0–6 条四问式情报、中国 AI 单列和人工反馈闭环 | Implemented | verified 主榜边界、重要更新、跳过原因、发布历史和周反馈提示 |
| EDITORIAL-03 | 编辑 | 基于已保存事实与人工反馈的周复盘和选题提示 | Planned | 统一总计划 M7；只读输入、建议可追溯、不自动发布 |
| DIGEST-01 | 情报 | 独立 DigestBuilder 读取 RunReport/上一期 Digest，保守聚合、权重排序和 new/updated/ongoing | Implemented | 聚类、误合并、排序、生命周期和 max-items 测试 |
| DIGEST-02 | 情报 | 主榜只含 verified；unverified 进入线索观察并保留原因、重试状态 | Implemented | Schema 隔离、原因/重试和 Markdown 测试 |
| DIGEST-03 | 情报 | 仅依据已保存严格证据的 Codex 中文摘要/影响判断与安全回退 | Implemented | 合法引用、未知引用、非法输出、超时和安全回退测试 |
| DIGEST-04 | 数据 | Digest Schema 1.0，历史 JSON、digest-latest.json/md 原子输出及失败恢复 | Implemented | Schema、碰撞保护、替换失败恢复和临时文件检查 |
| OPS-01 | 运维 | 已注册内置来源 `probe`，稳定/实验等级参与 Run 状态 | Implemented | 目标环境 G6-S，实验 blocked 不伪装成功 |
| OPS-02 | 运维 | 主机本地 09:30 launchd 安装脚本 | Implemented | 离线脚本和 Fake launchctl 测试；本次真实环境清单禁止操作 launchd |
| OPS-03 | 运维 | 隔离七天回溯、validate 和 Digest | Implemented | 2026-08-09 同一固定窗口两次真实运行、validate 和生产 Digest 通过；无 verified 样本，G6-V 仍阻断发布 |
| OPS-04 | 运维 | Codex 09:00/18:00 双档与 latest-only 补跑 | Implemented | 任务文档和原子状态 seam 已完成；未经授权不注册，真实双档后才可 Verified |
| OPS-05 | 运维 | 运行诊断、非破坏性保留计划和隔离恢复验证 | Planned | 统一总计划 M5；真实恢复演练后才能 Verified |
| EXT-01 | 扩展 | built-in SourcePlugin registry | Implemented | registry 隔离、重复 ID 和选择测试 |
| EXT-02 | 扩展 | 主 wheel 外的 Python entry-point 插件 | Implemented | `mynews.source_plugins`、无参数工厂、严格 metadata、显式加载、失败结构和隔离 `.dist-info` 测试 |
| EXT-03 | 扩展 | 其他核验器 Adapter | Future | 后续需求 |
| EXT-04 | 扩展 | 主 wheel 外的独立来源分发包与通用 RSS/Atom 插件辅助接口 | Implemented | 主项目无新增生产依赖；未安装时默认行为不变；真实安装/probe 仍属 P6 |
| UI-01 | 产品 | Web/桌面 UI | Out | 不属于 v1 |
| DB-01 | 数据 | 数据库存储 | Out | JSON 先行 |
| PUB-01 | 发布 | 自动生成和发布内容 | Out | 明确不做 |
| BYPASS-01 | 采集 | 绕过登录、付费墙或验证码 | Out | 安全约束 |

## 状态更新规则

- 实现内容完成且相应离线检查通过后才能从 Planned 改为 Implemented。
- 依赖真实网络、Codex 或七天运行的功能，必须完成对应真实验收才能改为 Verified。
- v1.7 P5 及后续状态回写以[统一开发总计划](../planning/v1.7-v2.0-master-plan.md)为准；v1.7 P0-P4 与更早真实限制以[归档索引](../archive/README.md)和归档原文为准。
