---
title: mynews 信息来源目录
doc_type: reference
status: current
implementation_status: implemented
version: 1.2
created: 2026-08-02
updated: 2026-08-11
owner: project-maintainers
---

# mynews 信息来源目录

本目录记录计划支持的来源、角色和核验方式。它是配置设计清单，不是实时健康报告；真实可用性必须由 `mynews probe` 生成 JSON 结果证明。

内容范围是 AI 与科技；v1 来源优先覆盖模型、AI 编程工具、开发者平台、芯片/云基础设施及重大科技产品动态。下表是优先接入清单，不是允许核验的厂商穷举表；任何表外线索仍必须回溯到对应第一方来源。

## 当前内置实现

当前 built-in registry 已接入 `cc-switch`、`hacker-news`、`qwen`、`openai`、`anthropic`、
`google-gemini`、`deepseek`、`trae`、`openai-pricing`、`deepseek-pricing`、`zhihu-hot` 和
`bloomberg-ai`。阶段 4.5 新增来源均有独立 fixture、`collect`/`probe` 接线和故障隔离；本节
不把 probe 通过解释为候选已 `verified`，候选核验仍由阶段 4 的统一流程负责。

阶段 2 的 Hacker News、Qwen 和 CC Switch 既有真实 probe 证据继续保留；阶段 4.5 的每个
新增来源 probe 命令和当次状态见 v1 归档计划；本目录只描述策略，不代替实时 probe。

v1.1 将来源详细等级写入 `SourceHealth`/`SourceResult`。`experimental` 是不影响 Run
状态的实验等级；`stable-planned`、`adapter-planned` 等其余当前内置等级按稳定来源处理，
其异常仍会使 Run 变为 `partial` 或 `failed`。这使来源质量和 Run 状态在 JSON 与 report 中可解释。

## v1.5 Implemented 外部来源包

下表是 [v1.5 当前计划](../planning/v1.5-expanded-sources-safe-handoff-plan.md) 的权威来源
清单。独立分发包、entry-point、fixture 和离线隔离测试已经 Implemented；它们是否安装和
真实可用仍由逐来源 probe 证明。它们只能通过独立分发包和显式扩展模式接入；普通 built-in
采集保持不变。

| 来源 ID | 角色 | 等级 | 官方入口 | 官方边界 |
| --- | --- | --- | --- | --- |
| openai-news | primary | stable-planned | https://openai.com/news/rss.xml | `openai.com` |
| google-blog | primary | stable-planned | https://blog.google/rss/ | `blog.google` |
| github-changelog | primary | stable-planned | https://github.blog/changelog/feed/ | `github.blog` |
| hugging-face-blog | primary | stable-planned | https://huggingface.co/blog/feed.xml | `huggingface.co` |
| google-deepmind | primary | stable-planned | https://deepmind.google/blog/rss.xml | `deepmind.google` |
| nvidia-ai | primary | stable-planned | https://blogs.nvidia.com/blog/category/deep-learning/feed/ | `blogs.nvidia.com` |
| aws-machine-learning | primary | stable-planned | https://aws.amazon.com/blogs/machine-learning/feed/ | `aws.amazon.com` |
| kimi-k2-releases | research | stable-planned | https://github.com/MoonshotAI/Kimi-K2/releases.atom | `github.com/MoonshotAI` |
| glm-releases | research | stable-planned | https://github.com/THUDM/GLM/releases.atom | `github.com/THUDM` |
| deepseek-status | incident | experimental | https://status.deepseek.com/history.atom | `status.deepseek.com` |
| openai-status | incident | experimental | https://status.openai.com/history.rss | `status.openai.com` |
| anthropic-status | incident | experimental | https://status.claude.com/history.rss | `status.claude.com` |
| github-status | incident | experimental | https://www.githubstatus.com/history.atom | `githubstatus.com` |
| techcrunch-ai | discovery | experimental | https://techcrunch.com/category/artificial-intelligence/feed/ | `techcrunch.com` |
| paperswithcode-daily | benchmark | manual | https://huggingface.co/papers | `huggingface.co` |

`qwen-blog-rss` 和 Hacker News RSS 与当前 built-in 重复，不计入新增来源；当前配置不存在
的 `arxiv-cs-ai`、`arxiv-cs-cl`、`arxiv-cs-lg` 测试期望也不计入计划覆盖。

`paperswithcode-daily` 当前没有可确认的官方 RSS/Atom daily 入口；旧官方页面当前转到
Hugging Face Daily Papers，因此保留 `https://huggingface.co/papers` 作为人工检查入口。
显式插件 probe/collect 必须结构化为 `blocked`/`manual_source`，不得请求猜测的 Feed URL，
也不得用 fixture 结果把它标为 healthy 或 Verified。

## 阶段 4.5 来源覆盖

| 来源 ID | 地区 | 角色 | 官方入口 | 采集类型 | 发布时间语义 |
| --- | --- | --- | --- | --- | --- |
| openai | 国外 | primary | https://developers.openai.com/api/docs/models | 官方开发者模型/价格更新页 | 页面提供则使用，否则 `null` |
| anthropic | 国外 | primary | https://www.anthropic.com/news | 官方 HTML 新闻页 | 页面提供则使用，否则 `null` |
| google-gemini | 国外 | primary | https://ai.google.dev/gemini-api/docs/changelog | 官方 HTML 更新页 | 页面提供则使用，否则 `null` |
| qwen | 国内 | primary | https://qwenlm.github.io/blog/index.xml | 官方 RSS | Feed 日期，否则 `null` |
| deepseek | 国内 | primary | https://api-docs.deepseek.com/zh-cn/updates | 官方 HTML 更新页 | 页面提供则使用，否则 `null` |
| trae | 国内 | primary | https://www.trae.cn/changelog | 官方 HTML 更新页 | 页面提供则使用，否则 `null` |
| openai-pricing | 国外 | monitor | https://developers.openai.com/api/docs/models | 官方开发者模型/价格页快照 | 无官方日期时 `null` |
| deepseek-pricing | 国内 | monitor | https://api-docs.deepseek.com/zh-cn/quick_start/pricing | 官方价格页快照 | 无官方日期时 `null` |
| zhihu-hot | 国内 | discovery | https://www.zhihu.com/hot | 公开 HTML 元数据实验 | 页面提供则使用，否则 `null` |
| bloomberg-ai | 国外 | discovery | https://www.bloomberg.com/technology | 公开 HTML 元数据实验 | 页面提供则使用，否则 `null` |

本次六个重点官方自动来源均使用第一方入口。OpenAI 原 `https://openai.com/news/` 与
`https://openai.com/api/pricing/` 在 2026-08-02 live probe 返回 HTTP 403，因此按同类
替换规则改用可公开访问的官方 `developers.openai.com/api/docs/models` 模型/价格更新页，
并由 `openai` 与 `openai-pricing` fixture/probe 覆盖；Anthropic、Gemini、DeepSeek 和
TRAE 的入口由实现前的公开页面检查确认。若 live probe 受本机网络、登录、付费墙
或 robots 限制，记录为 `blocked`/`failed`，不改用媒体、搜索摘要或非官方 API。

价格来源首次观察只保存 `state/price_snapshots/<source-id>.json`；官方 HTML 目录页没有任何
可确认日期时只保存 `state/source_snapshots/<source-id>.json`。只有后续运行规范化快照
的 URL 或内容哈希变化时，才产生 `pricing_change` 候选。实验来源只保留公开标题、链接、
日期等元数据，不能采集登录后正文或付费墙内容。

## 来源角色

- `discovery`：发现热点，只能产生候选，不能单独证明事实。
- `primary`：厂商公告、官方文档、官方 Release 或论文原文，可作为第一方证据。
- `monitor`：价格、套餐、状态或更新日志页面，需要快照比较。
- `research`：官方研究仓库、论文或 Release，可作为对应研究产物的第一方候选。
- `incident`：官方服务状态与事故历史，只能证明对应服务事件，不能证明产品发布。
- `benchmark`：聚合基准、论文或代码线索，只负责发现，不能单独证明事实。
- `manual`：没有可靠机器入口时保留官方检查入口，不宣称自动采集。

## 稳定等级

- `stable-planned`：有 RSS、Atom、API 或明确结构化入口，仍需 live probe。
- `adapter-planned`：需要来源专用 HTML Adapter 和日期验证。
- `experimental`：可能受 robots、登录、地区或页面结构影响，失败允许标记 blocked，且不影响 Run 状态。
- `manual`：v1 仅保留链接或由 Codex 搜索发现。

## 发现与媒体渠道

| ID | 来源 | 角色 | 计划方式 | 等级 | 官方入口 | v1 规则 |
| --- | --- | --- | --- | --- | --- | --- |
| hacker-news | Hacker News | discovery | 官方 API | stable-planned | https://github.com/HackerNews/API | 保存排名/分数；跳转原文后再核验 |
| zhihu-hot | 知乎热榜 | discovery | 来源专用网页 | experimental | https://www.zhihu.com/hot | 不依赖非官方 API；失败标 blocked |
| bloomberg-ai | Bloomberg AI/Technology | discovery | 页面/RSS 探测 | experimental | https://www.bloomberg.com/technology | 不绕过付费墙；仅保存可公开元数据 |

## 国外官方来源

| ID | 产品/机构 | 角色 | 计划方式 | 等级 | 官方入口 |
| --- | --- | --- | --- | --- | --- |
| openai | OpenAI / Codex | primary, monitor | 官方开发者模型/价格更新页（原 News 入口 403 后替换） | adapter-planned | https://developers.openai.com/api/docs/models |
| anthropic | Anthropic / Claude | primary, monitor | News、文档更新、价格页 | adapter-planned | https://www.anthropic.com/news |
| google-gemini | Google Gemini | primary, monitor | Gemini API changelog、价格页 | stable-planned | https://ai.google.dev/gemini-api/docs/changelog |
| github-copilot | GitHub Copilot | primary, monitor | GitHub Changelog、官方文档 | stable-planned | https://github.blog/changelog/label/copilot/ |
| cursor | Cursor | primary, monitor | Changelog、价格页 | adapter-planned | https://cursor.com/changelog |
| windsurf | Windsurf / Devin Desktop | primary, monitor | Changelog、价格页 | experimental | https://docs.devin.ai/desktop/changelog |
| nvidia-ai | NVIDIA AI | primary | Developer Blog、Release | adapter-planned | https://developer.nvidia.com/blog/ |
| huggingface | Hugging Face | primary, discovery | Blog、模型/库 Release | adapter-planned | https://huggingface.co/blog |
| cc-switch | CC Switch | primary, monitor | 官方 Changelog + GitHub Releases API | adapter-planned | https://ccswitch.io/zh/changelog/3.19.1 |

## 国内官方来源

| ID | 产品/机构 | 角色 | 计划方式 | 等级 | 官方入口 |
| --- | --- | --- | --- | --- | --- |
| qwen | Qwen | primary | 官方 Blog RSS | stable-planned | https://qwenlm.github.io/blog/index.xml |
| deepseek | DeepSeek | primary, monitor | API 更新、价格、状态 | adapter-planned | https://api-docs.deepseek.com/zh-cn/updates/ |
| kimi-code | Kimi / Kimi Code | primary, monitor | 官方资源、价格、GitHub Release | adapter-planned | https://www.kimi.com/zh-cn/products/ |
| glm-codegeex | GLM / CodeGeeX | primary, monitor | 官方平台、GitHub Release | adapter-planned | https://bigmodel.cn/ |
| tongyi-lingma | 通义灵码 | primary, monitor | 官方产品与文档页 | adapter-planned | https://lingma.aliyun.com/ |
| trae | TRAE | primary, monitor | Changelog、价格页 | adapter-planned | https://www.trae.cn/changelog |
| codebuddy | CodeBuddy | primary, monitor | 官方文档、价格页 | adapter-planned | https://www.codebuddy.cn/docs/ide/Account/pricing |
| baidu-comate | 百度 Comate | primary, monitor | 官方文档、更新、价格页 | adapter-planned | https://cloud.baidu.com/doc/COMATE/index.html |
| minimax | MiniMax | primary, monitor | 官方新闻、开放平台 | manual | https://www.minimaxi.com/ |
| doubao-volcengine | 豆包 / 火山引擎 | primary, monitor | 官方产品、API 文档 | manual | https://www.volcengine.com/product/doubao |

## 第一方核验规则

- `verified` 证据必须来自配置的精确官方域名或官方 GitHub 组织。
- 重定向后的最终域名也必须通过检查；形似官方名称的子域名不能自动信任。
- 证据摘录必须存在于实际抓取正文中，只有搜索摘要不够。
- 官方状态页只证明服务状态，不自动证明模型发布或价格变化。
- 价格页没有发布日期时，事件日期为空，只记录首次观察时间和前后哈希。
- 多个媒体重复同一消息只能提高热度，不能提高第一方证据等级。
- 实现使用精确官方主机名匹配；GitHub 证据还必须匹配配置的官方组织，伪造子域名、
  跨域异常重定向和不可访问页面均保持 unverified。
- `windsurf.com/changelog` 当前会跳转到 Devin Docs；实现前必须确认产品归属、历史连续性和新的官方域名白名单，因此暂列 experimental。

## v1.1 discovery 与 HTML 规则

- discovery 候选先经过确定性的 AI/科技相关性词表；词表只匹配候选可读文本，URL 和 HTML 标记不计为命中；不相关候选只记录 `filtered` 原因，不进入规范化或核验。
- 通过筛选的 discovery 候选允许进入统一 Codex 第一方证据查找；模型只能在程序提供的官方域名/GitHub 组织范围内建议，不能扩大白名单。
- 程序白名单对当前已确认入口使用精确主机名，例如 `developers.openai.com`、`www.anthropic.com` 和 `www.trae.cn`；主域名相似或未经配置的 host 不会因为模型建议而获信任。
- 官方 HTML Adapter 只用同时存在的标题和页面日期生成单个事件；候选摘要最多 500 字。目录页没有日期事件时保存页面内容哈希快照，不伪造事件日期。

## CC Switch 更新日志监控约定

- 稳定来源 ID 为 `cc-switch`；官方 Changelog 页面是候选回链，版本内容通过官方仓库
  `https://api.github.com/repos/farion1231/cc-switch/releases` 获取。
- 仅接受 `farion1231/cc-switch` 的稳定 Release；草稿、预发布和非官方仓库 URL 不进入候选。
- 每个版本 `## 新功能` 下的 `###` 条目单独产生一个候选，发布日期使用 Release 的
  `published_at`，不知道发布时间时不得用抓取时间补齐。
- v3.19.1 已有离线 fixture，覆盖官方厂商模型目录镜像和腾讯混元 Codex 预设；运行时
  `probe --source cc-switch` 于 2026-08-02 15:34（Asia/Shanghai）返回 `healthy`，
  `fetched_count=33`、`accepted_count=33`，退出码为 0；JSON Store 已在阶段 3 实现，
  真实价格源仍未接入。

## 阶段 2 其他稳定入口

- Hacker News 使用官方 Firebase API：`topstories.json` 加 `item/{id}.json`，发布时间来自
  API 的 Unix 时间；无外链的 Ask HN 条目回退到官方 item URL。
- Qwen 使用官方 Blog RSS：`https://qwenlm.github.io/blog/index.xml`；日期无法确认时保持
  `published_at: null`，不使用抓取时间代替。

## 新增来源流程

1. 在本目录增加来源 ID、角色、官方入口和计划等级。
2. 证明来源归属，确认日期字段语义和访问限制。
3. 增加配置、Adapter fixture 和 `probe`。
4. 更新功能矩阵；实现通过后改为 Implemented，live probe 通过后才可标 Verified。
5. 如果来源需要改变 SourcePlugin interface，先更新架构并新增 ADR。
