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
| 2026-08-02T09:00:48Z | openai | healthy | 0 | 官方开发者模型/价格页替代入口 |
| 2026-08-02T09:00:36Z | anthropic | healthy | 0 | 官方公开页级元数据回退；跳过 `mailto:` 页脚 |
| 2026-08-02T09:00:52Z | google-gemini | healthy | 0 | 官方 Gemini API Release notes |
| 2026-08-02T09:00:43Z | deepseek | healthy | 0 | 官方中文更新日志 |
| 2026-08-02T09:00:43Z | trae | healthy | 0 | 官方更新日志 |
| 2026-08-02T09:00:47Z | openai-pricing | healthy | 0 | 官方开发者模型/价格页快照入口 |
| 2026-08-02T09:00:44Z | deepseek-pricing | healthy | 0 | 官方模型与价格页快照入口 |
| 2026-08-02T09:00:52Z | qwen | healthy | 0 | 官方 RSS，5/5 条探针窗口条目 |
| 2026-08-02T09:00:42Z | zhihu-hot | blocked | 1 | 官方入口 HTTP 403；未尝试非官方 API 或登录 |
| 2026-08-02T09:00:51Z | bloomberg-ai | blocked | 1 | 页面没有可公开读取的元数据卡片；未触碰付费墙 |

此前的沙箱默认网络尝试对所有新增来源返回 `network_error: Operation not permitted`；该
结果没有被写成来源 blocked，重试只读升级权限后才采用上表结果。原始 probe JSON 在命令
标准输出中保留；本表只记录摘要，避免把实时健康报告混入来源目录。

## 本次独立验收补充（2026-08-02）

本次验收在同一仓库执行，使用
`UV_CACHE_DIR=/tmp/mynews-acceptance-cache uv run mynews probe --source <source-id>`，并用
`curl -sS -L --max-time 20 -o /dev/null -w '%{http_code}|%{url_effective}' <entry-url>`
记录重定向后的最终 URL。运行输出只保存在系统临时目录，仓库没有生成 `output/` 或
`state/`。

| 时间（UTC） | 来源 | 入口 URL | 最终 URL | HTTP | health | CLI | 限制 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-08-02T09:20:13Z | openai | `https://developers.openai.com/api/docs/models` | `https://developers.openai.com/api/docs/models` | 200 | healthy | 0 | 无 |
| 2026-08-02T09:20:20Z | anthropic | `https://www.anthropic.com/news` | `https://www.anthropic.com/news` | 200 | healthy | 0 | 无 |
| 2026-08-02T09:20:28Z | google-gemini | `https://ai.google.dev/gemini-api/docs/changelog` | `https://ai.google.dev/gemini-api/docs/changelog` | 200 | healthy | 0 | 无 |
| 2026-08-02T09:20:33Z | deepseek | `https://api-docs.deepseek.com/zh-cn/updates` | `https://api-docs.deepseek.com/zh-cn/updates/` | 200 | healthy | 0 | 站点规范化尾斜杠 |
| 2026-08-02T09:20:34Z | trae | `https://www.trae.cn/changelog` | `https://www.trae.cn/changelog` | 200 | healthy | 0 | 无 |
| 2026-08-02T09:20:35Z | openai-pricing | `https://developers.openai.com/api/docs/models` | `https://developers.openai.com/api/docs/models` | 200 | healthy | 0 | 与 OpenAI 更新页共用入口 |
| 2026-08-02T09:20:40Z | deepseek-pricing | `https://api-docs.deepseek.com/zh-cn/quick_start/pricing` | `https://api-docs.deepseek.com/zh-cn/quick_start/pricing/` | 200 | healthy | 0 | 站点规范化尾斜杠 |
| 2026-08-02T09:20:40Z | qwen | `https://qwenlm.github.io/blog/index.xml` | `https://qwenlm.github.io/blog/index.xml` | 200 | healthy | 0 | 5/5 条探针窗口条目 |
| 2026-08-02T09:20:45Z | zhihu-hot | `https://www.zhihu.com/hot` | `https://www.zhihu.com/hot` | 403 | blocked | 1 | 未尝试登录或非官方 API |
| 2026-08-02T09:20:45Z | bloomberg-ai | `https://www.bloomberg.com/technology` | `https://www.bloomberg.com/technology` | 403 | blocked | 1 | 未读取付费墙，仅保留公开访问限制 |

本轮确认国内第一方来源为 Qwen、DeepSeek、TRAE，国外第一方来源为 OpenAI、Anthropic、
Google Gemini；稳定来源均真实 healthy。知乎和 Bloomberg 的 CLI 顶层 `status` 为
`failed`，但来源 health 和结构化错误如实为 `blocked`，符合当前 probe 退出码约定。

## G6-V 独立验收记录（2026-08-02）

结论：`FAIL`。真实 `codex-cli 0.144.1` 可用，并对新增官方来源产生了结构化建议；但程序
二次校验均返回 `evidence_excerpt_mismatch`，没有任何新增官方来源被标为 `verified`。

| 来源 | 真实采集候选 | Codex 建议 | 程序二次校验 |
| --- | --- | --- | --- |
| deepseek | `https://api-docs.deepseek.com/zh-cn/` | `https://api-docs.deepseek.com/zh-cn/updates/`，DeepSeek-V4-Flash 更新 | `unverified / evidence_excerpt_mismatch` |
| google-gemini | `https://ai.google.dev/gemini-api/docs/interactions-overview` | 同一官方 URL，Interactions API | `unverified / evidence_excerpt_mismatch` |

验收使用真实 `SubprocessCodexRunner`、模型 `gpt-5.6-luna` 和临时 Store；Codex 返回的
建议数量均为 1。失败原因不是网络或权限阻塞，而是 Adapter 的页面级摘录与 Codex 建议
摘录无法在程序重抓正文中逐字匹配。相关实现位置为
`src/mynews/sources/builtins/official_pages.py` 的页面回退逻辑和
`src/mynews/verification/codex.py` 的摘录校验逻辑。修复后必须重新执行 G6-V。

## G6-V 修复后重验记录（2026-08-02）

修复范围没有放宽域名或摘录规则：官方 HTML Adapter 使用稳定的页面标题作为 `excerpt`，完整卡片
文本保留在 `content`；核验器把 HTML 转为可见文本后进行逐字匹配，并仅去除零宽格式字符；Codex
提示明确要求返回页面中逐字连续、不可改写/翻译/拼接/添加归因的原文片段。原始失败记录保留在上节。

| 时间（UTC） | 场景 | 来源 | 结果 | 证据 |
| --- | --- | --- | --- | --- |
| 2026-08-02T10:13:58Z | 真实 `collect --days 7` | deepseek | `healthy`，`verified` | 官方 URL `https://api-docs.deepseek.com/zh-cn`，`excerpt_matched=true` |
| 2026-08-02T10:13:58Z | 真实 `collect --days 7` | google-gemini | `healthy`，`verified` | 官方 URL `https://ai.google.dev/gemini-api/docs/interactions-overview`，`excerpt_matched=true` |
| 2026-08-02T10:17:27Z | 真实 `SubprocessCodexRunner` Codex 分支重验 | google-gemini | `verified / codex_primary_evidence` | 同一官方 URL；`reachable/official_domain/excerpt_matched=true` |

新增来源回溯命令为：

```bash
UV_CACHE_DIR=/tmp/mynews-acceptance-cache uv run --project /Users/edgarlqs/Downloads/mynews \
  mynews collect --days 7 --source deepseek --source google-gemini
```

该命令在 `/tmp` 隔离根目录执行，退出码为 0，两个新增来源均 `healthy`，`verified_count=2`。真实
Codex 分支重验返回的逐字摘录为 Google 官方页面中的
`The Interactions API is the best way to build with Gemini models and agents.`，程序二次抓取确认
摘录、官方域名和可访问性均通过。
