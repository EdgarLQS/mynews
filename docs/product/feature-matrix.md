---
title: mynews 功能矩阵
doc_type: matrix
status: current
implementation_status: implemented
version: 1.2
created: 2026-08-02
updated: 2026-08-05
owner: project-maintainers
---

# mynews 功能矩阵

本表是产品范围和实现状态的唯一真相来源。状态使用 `Planned`、`In Progress`、`Implemented`、`Verified`、`Future`、`Out`。

依赖真实网络、Codex 或 launchd 的能力只有完成对应真实门禁后才能标记为 Verified；mock、连接器读取和离线测试只能证明 Implemented。

| ID | 领域 | 功能 | 状态 | 验收入口 |
| --- | --- | --- | --- | --- |
| DOC-01 | 治理 | 文档索引、唯一 Current 计划和完整归档 | Implemented | `python3 scripts/check_docs.py` |
| AI-01 | 协作 | `AGENTS.md` 与 `CLAUDE.md` 共用项目规则 | Implemented | 指令入口检查 |
| QA-01 | 验收 | 统一验收规则与 Claude `/acceptance` | Implemented | 规则和技能检查 |
| CLI-01 | CLI | 全局及 collect/probe/validate/report 中文 help | Implemented | GitHub Actions Python 3.12 help 门禁 |
| CLI-02 | CLI | 日期范围、来源过滤、预算和退出码 | Implemented | CLI 与日期参数测试 |
| CLI-03 | CLI | RunReport/Schema/证据校验 | Implemented | `mynews validate` 与兼容测试 |
| CLI-04 | CLI | 离线中文 Markdown 报告 | Implemented | report fixture 和文件输出测试 |
| SRC-01 | 来源 | Hacker News 官方 API | Verified | fixture + 既有真实 probe 记录 |
| SRC-02 | 来源 | 官方 RSS/API/GitHub Release/HTML Adapter | Implemented | 主线 Adapter fixture 与全量测试 |
| SRC-03 | 来源 | 官方价格页和更新日志监控 | Implemented | 快照和 `pricing_change` 测试 |
| SRC-04 | 来源 | 知乎和 Bloomberg 实验 Adapter | Implemented | 公开元数据 fixture；受限时结构化 blocked |
| SRC-05 | 来源 | 内置来源实时 probe | Verified | v1.1 真实 probe 记录；v1.2 未改变来源边界 |
| PIPE-01 | 处理 | 规范化、热度、相关性分离 | Implemented | Normalizer 与 relevance 测试 |
| PIPE-02 | 处理 | 跨来源、跨日期、跨运行新闻去重 | Implemented | DedupState 恢复测试 |
| PIPE-03 | 处理 | 不相关 discovery 在核验前停止 | Implemented | 单词边界、HTML/URL 清理和 Collector 测试 |
| VER-01 | 核验 | 第一方官方 URL 直接核验 | Implemented | 严格日期、摘录、重定向和哈希测试 |
| VER-02 | 核验 | 固定顺序的受控证据解析 | Implemented | 自身官方 URL、首个第一方链接、Codex 顺序测试 |
| VER-03 | 核验 | 精确域名和 GitHub 组织安全边界 | Implemented | 伪造子域名、近似组织、搜索页和跨域重定向测试 |
| VER-04 | 核验 | Codex 结构化建议后程序二次核验 | Implemented | Fake runner、预算/批次和哈希测试 |
| VER-05 | 核验 | 已知真实 discovery 经生产 Codex 后 verified | In Progress | G6-V；当前没有通过证据，外部阻断必须记为 BLOCKED |
| VER-06 | 核验 | pending 跨运行增量重试 | Implemented | 首次失败、去重后重试、成功清除、上限和 TTL 测试 |
| VER-07 | 核验 | 证据生命周期 current/changed_supporting/failed | Implemented | 正文漂移、支持文本消失和域名异常测试 |
| DATA-00 | 数据 | Pydantic RunReport 1.x 契约 | Implemented | 1.0/1.1 读取和 1.2 严格校验测试 |
| DATA-01 | 数据 | 每次运行独立 JSON 和 latest | Implemented | JSON Store 测试 |
| DATA-02 | 数据 | run/latest/dedup/pending 逻辑事务 | Implemented | 中途替换失败回滚测试 |
| DATA-03 | 数据 | 独立 DedupState 与 PendingVerificationState | Implemented | 跨运行恢复和失败运行不污染测试 |
| DATA-04 | 数据 | 来源和价格快照 | Implemented | 快照原子保存与 first_observed_at 测试 |
| OPS-01 | 运维 | 隔离两次七天采集、validate 和 report | In Progress | G7；只允许临时目录，不污染仓库运行目录 |
| OPS-02 | 运维 | launchd 模板与管理脚本 | Implemented | Fake launchctl、plist lint 和 dry-run；真实 launchd 未加载 |
| EXT-01 | 扩展 | built-in SourcePlugin registry | Implemented | registry 隔离、重复 ID 和选择测试 |
| EXT-02 | 扩展 | 仓库外 Python entry-point 插件 | Future | 后续 ADR |
| EXT-03 | 扩展 | 其他核验器 Adapter | Future | 后续需求 |
| UI-01 | 产品 | Web/桌面 UI | Out | 不属于当前版本 |
| DB-01 | 数据 | 数据库存储 | Out | JSON 先行 |
| PUB-01 | 发布 | 自动生成和发布内容 | Out | 明确不做 |
| BYPASS-01 | 采集 | 绕过登录、付费墙或验证码 | Out | 安全约束 |

## 状态更新规则

- 实现内容完成且对应离线检查通过后，才能标记为 Implemented。
- G6-V 和 G7 的真实条件未满足时，相关功能保持 In Progress 或 BLOCKED，不能因 mock 测试通过而标记 Verified。
- 更新本表时同步 [文档总览](../README.md)、[v1.2 计划](../planning/v1.2-evidence-lifecycle-plan.md) 和相关 ADR。
