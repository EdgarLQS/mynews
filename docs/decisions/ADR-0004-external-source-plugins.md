---
title: ADR-0004 受显式控制的外部来源插件
doc_type: adr
status: current
implementation_status: implemented
version: 1.0
created: 2026-08-09
updated: 2026-08-09
owner: project-maintainers
decision_status: accepted
---

# ADR-0004：受显式控制的外部来源插件

## 背景

内置 SourcePlugin registry 已能隔离来源，但把每个新 Adapter 都放入主仓库会扩大
正式来源目录和发布面。v1.4 需要允许仓库外的本地 Python 包接入，同时保持来源只
负责发现候选和报告健康，不接触 Store、Verifier、Codex 或 `verified` 状态。

## 决定

- 只发现 Python entry-point group `mynews.source_plugins`。
- entry-point 的名称作为显式 `--plugin <id>`；只有显式选择才解析工厂并实例化。
- 工厂必须无参数，返回 SourcePlugin API 1.0 对象；loader 严格校验元数据、能力、
  方法和 source_id 唯一性。外部 source_id 与内置 source_id 冲突时拒绝加载。
- 加载后的对象进入现有 SourceRegistry；其 collect/probe 运行时异常复用现有结构化
  SourceHealth 和 failed Run 保护。
- 插件代码被视为受信任的本地 Python 代码。显式允许是加载控制，不是进程级沙箱；
  文档和 CLI 不承诺阻止插件导入文件、网络或其他 Python 能力。

## 取舍与后果

显式选择和严格校验减少了默认运行的惊喜，也让重复 ID、协议升级和工厂失败可在
进入流水线前报告。entry-point 发现依赖 Python 分发元数据，隔离测试必须使用真实
临时 `.dist-info`；代价是插件部署需要正确安装或暴露分发包。由于没有进程级沙箱，
使用者必须信任本地插件来源；本 ADR 不扩大访问控制或第一方证据门槛。

## 不采用的方案

- 不自动加载环境中所有 entry-point，避免普通 collect/probe 改变结果。
- 不开放 Verifier/Codex 插件，避免外部代码改变证据结论。
- 不把临时验证分发包登记为内置来源或 source-catalog 正式来源。
- 不实现进程级沙箱；这需要独立的安全边界、部署模型和验收标准。

## 实现与验证

实现位于 `mynews.sources.external` 和现有 SourceRegistry/CLI seam；RunReport 继续
使用 1.x 契约。P1–P6 离线门禁通过后改为 Implemented；真实网络、Codex 和 launchd
能力仍按项目规则单独判定。
