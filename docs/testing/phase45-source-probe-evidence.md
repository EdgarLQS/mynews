---
title: mynews v1 阶段 4.5 来源 probe 证据
doc_type: test
status: current
implementation_status: implemented
version: 1.0
created: 2026-08-02
updated: 2026-08-02
owner: project-maintainers
---

# 阶段 4.5 来源 probe 证据

以下命令均在 `/Users/edgarlqs/Downloads/mynews` 执行，使用
`UV_CACHE_DIR=/tmp/mynews-uv-cache uv run mynews probe --source <source-id>`；因沙箱默认网络
不可用，最终一轮使用允许网络访问的只读升级权限执行。`health` 是来源入口/解析健康状态，
不是候选真实性结论；CLI 对 `blocked` 返回退出码 1 是当前 `probe` 约定。

| 时间（UTC） | 来源 | health | CLI 结果 | 证据/限制 |
| --- | --- | --- | --- | --- |
| 2026-08-02T08:48:54Z | openai | healthy | 0 | 官方开发者模型/价格页替代入口 |
| 2026-08-02T08:47:12Z | anthropic | healthy | 0 | 官方公开页级元数据回退；跳过 `mailto:` 页脚 |
| 2026-08-02T08:46:20Z | google-gemini | healthy | 0 | 官方 Gemini API Release notes |
| 2026-08-02T08:46:18Z | deepseek | healthy | 0 | 官方中文更新日志 |
| 2026-08-02T08:46:19Z | trae | healthy | 0 | 官方更新日志 |
| 2026-08-02T08:48:58Z | openai-pricing | healthy | 0 | 官方开发者模型/价格页快照入口 |
| 2026-08-02T08:46:17Z | deepseek-pricing | healthy | 0 | 官方模型与价格页快照入口 |
| 2026-08-02T08:47:26Z | qwen | healthy | 0 | 官方 RSS，5/5 条探针窗口条目 |
| 2026-08-02T08:46:19Z | zhihu-hot | blocked | 1 | 官方入口 HTTP 403；未尝试非官方 API 或登录 |
| 2026-08-02T08:46:21Z | bloomberg-ai | blocked | 1 | 页面没有可公开读取的元数据卡片；未触碰付费墙 |

此前的沙箱默认网络尝试对所有新增来源返回 `network_error: Operation not permitted`；该
结果没有被写成来源 blocked，重试只读升级权限后才采用上表结果。原始 probe JSON 在命令
标准输出中保留；本表只记录摘要，避免把实时健康报告混入来源目录。
