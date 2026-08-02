---
title: mynews 信息来源目录
doc_type: reference
status: current
implementation_status: in_progress
version: 1.0
created: 2026-08-02
updated: 2026-08-02
owner: project-maintainers
---

# mynews 信息来源目录

本目录记录计划支持的来源、角色和核验方式。它是配置设计清单，不是实时健康报告；真实可用性必须由 `mynews probe` 生成 JSON 结果证明。

内容范围是 AI 与科技；v1 来源优先覆盖模型、AI 编程工具、开发者平台、芯片/云基础设施及重大科技产品动态。下表是优先接入清单，不是允许核验的厂商穷举表；任何表外线索仍必须回溯到对应第一方来源。

## 阶段 2 当前内置实现

当前 built-in registry 已接入 `cc-switch`、`hacker-news` 和 `qwen`。三者均有独立离线
fixture；2026-08-02 使用 `mynews probe --source <source-id>` 逐项返回 `healthy`，因此
这三项的来源连通性为 `Verified`。本节不把 probe 通过解释为候选已 `verified`，候选核验
留给阶段 4。

## 来源角色

- `discovery`：发现热点，只能产生候选，不能单独证明事实。
- `primary`：厂商公告、官方文档、官方 Release 或论文原文，可作为第一方证据。
- `monitor`：价格、套餐、状态或更新日志页面，需要快照比较。
- `manual`：没有可靠机器入口时保留官方检查入口，不宣称自动采集。

## 稳定等级

- `stable-planned`：有 RSS、Atom、API 或明确结构化入口，仍需 live probe。
- `adapter-planned`：需要来源专用 HTML Adapter 和日期验证。
- `experimental`：可能受 robots、登录、地区或页面结构影响，失败允许标记 blocked。
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
| openai | OpenAI / Codex | primary, monitor | 公告、Release Notes、价格页 | adapter-planned | https://openai.com/news/ |
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
- `windsurf.com/changelog` 当前会跳转到 Devin Docs；实现前必须确认产品归属、历史连续性和新的官方域名白名单，因此暂列 experimental。

## CC Switch 更新日志监控约定

- 稳定来源 ID 为 `cc-switch`；官方 Changelog 页面是候选回链，版本内容通过官方仓库
  `https://api.github.com/repos/farion1231/cc-switch/releases` 获取。
- 仅接受 `farion1231/cc-switch` 的稳定 Release；草稿、预发布和非官方仓库 URL 不进入候选。
- 每个版本 `## 新功能` 下的 `###` 条目单独产生一个候选，发布日期使用 Release 的
  `published_at`，不知道发布时间时不得用抓取时间补齐。
- v3.19.1 已有离线 fixture，覆盖官方厂商模型目录镜像和腾讯混元 Codex 预设；运行时
  `probe --source cc-switch` 于 2026-08-02 返回 `healthy`，退出码为 0。JSON Store 仍待阶段 3。

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
