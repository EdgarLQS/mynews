---
title: newsFromAI datacollection 与 mynews v1.6 映射清单
doc_type: reference
status: current
implementation_status: implemented
version: 1.0
created: 2026-08-11
updated: 2026-08-11
owner: project-maintainers
---

# newsFromAI datacollection 与 mynews v1.6 映射清单

本清单以 `/Users/edgarlqs/Downloads/newsFromAI/datacollection/config.yaml` 当前快照为输入，证明自动 Feed 17/17、人工清单 65/65 覆盖。重复人工 ID 保留为独立条目并加稳定后缀，不丢失原始 URL、名称和备注。

## 自动 Feed 覆盖（17/17）

| newsFromAI ID | mynews seam | 角色 | freshness | URL |
| --- | --- | --- | ---: | --- |
| `openai-news` | v1.5 `RssFeedPlugin`/SourcePlugin | `primary` | 2 天 | https://openai.com/news/rss.xml |
| `google-blog` | v1.5 `RssFeedPlugin`/SourcePlugin | `primary` | 2 天 | https://blog.google/rss/ |
| `github-changelog` | v1.5 `RssFeedPlugin`/SourcePlugin | `primary` | 2 天 | https://github.blog/changelog/feed/ |
| `hugging-face-blog` | v1.5 `RssFeedPlugin`/SourcePlugin | `primary` | 2 天 | https://huggingface.co/blog/feed.xml |
| `google-deepmind` | v1.5 `RssFeedPlugin`/SourcePlugin | `primary` | 2 天 | https://deepmind.google/blog/rss.xml |
| `nvidia-ai` | v1.5 `RssFeedPlugin`/SourcePlugin | `primary` | 2 天 | https://blogs.nvidia.com/blog/category/deep-learning/feed/ |
| `aws-machine-learning` | v1.5 `RssFeedPlugin`/SourcePlugin | `primary` | 2 天 | https://aws.amazon.com/blogs/machine-learning/feed/ |
| `qwen-blog-rss` | 复用现有 RSS/Atom seam（不复用旧 qwen ID，保持配置 ID） | `primary` | 7 天 | https://qwenlm.github.io/blog/index.xml |
| `kimi-k2-releases` | v1.5 `RssFeedPlugin`/SourcePlugin | `research` | 7 天 | https://github.com/MoonshotAI/Kimi-K2/releases.atom |
| `glm-releases` | v1.5 `RssFeedPlugin`/SourcePlugin | `research` | 7 天 | https://github.com/THUDM/GLM/releases.atom |
| `deepseek-status` | v1.5 `RssFeedPlugin`/SourcePlugin | `incident` | 1 天 | https://status.deepseek.com/history.atom |
| `hacker-news` | 复用现有 Hacker News API 语义并提供 RSS 配置适配 | `discovery` | 1 天 | https://hnrss.org/frontpage |
| `techcrunch-ai` | v1.5 `RssFeedPlugin`/SourcePlugin | `discovery` | 2 天 | https://techcrunch.com/category/artificial-intelligence/feed/ |
| `paperswithcode-daily` | 保留 SourcePlugin manual/blocked 边界 | `benchmark` | 2 天 | https://paperswithcode.co/feeds/daily.xml |
| `openai-status` | v1.5 `RssFeedPlugin`/SourcePlugin | `incident` | 1 天 | https://status.openai.com/history.rss |
| `anthropic-status` | v1.5 `RssFeedPlugin`/SourcePlugin | `incident` | 1 天 | https://status.anthropic.com/history.rss |
| `github-status` | v1.5 `RssFeedPlugin`/SourcePlugin | `incident` | 1 天 | https://www.githubstatus.com/history.atom |

自动 Feed 覆盖率：`17 / 17 = 100%`。`qwen-blog-rss` 不把既有 `qwen` 注册成第二个事实来源；prepare 使用配置 ID 以便与来源清单一一对应。`paperswithcode-daily` 没有稳定官方 daily Feed，仍以结构化 `blocked/manual_source` 记录，不伪装健康。

## manual_watchlist 覆盖（65/65）

| 序号 | 原始 ID | mynews ID | 角色 | URL |
| ---: | --- | --- | --- | --- |
| 1 | `openai-api-pricing` | `openai-api-pricing` | `primary` | https://developers.openai.com/api/docs/pricing/ |
| 2 | `openai-api-changelog` | `openai-api-changelog` | `primary` | https://developers.openai.com/api/docs/changelog |
| 3 | `deepseek-v4-official` | `deepseek-v4-official` | `primary` | https://api-docs.deepseek.com/zh-cn/updates/ |
| 4 | `deepseek-api-pricing` | `deepseek-api-pricing` | `primary` | https://api-docs.deepseek.com/quick_start/pricing/ |
| 5 | `github-copilot-changelog` | `github-copilot-changelog` | `primary` | https://github.blog/changelog/?query=Copilot |
| 6 | `github-models-changelog` | `github-models-changelog` | `primary` | https://github.blog/changelog/?query=Models |
| 7 | `google-ai-developer-changelog` | `google-ai-developer-changelog` | `primary` | https://ai.google.dev/gemini-api/docs/changelog |
| 8 | `openai-x` | `openai-x` | `discovery` | https://x.com/OpenAI |
| 9 | `codex-x` | `codex-x` | `discovery` | https://x.com/OpenAICodex |
| 10 | `chatgpt-x` | `chatgpt-x` | `discovery` | https://x.com/ChatGPTapp |
| 11 | `anthropic-x` | `anthropic-x` | `discovery` | https://x.com/AnthropicAI |
| 12 | `claude-x` | `claude-x` | `discovery` | https://x.com/claudeai |
| 13 | `google-gemini-x` | `google-gemini-x` | `discovery` | https://x.com/GeminiApp |
| 14 | `google-deepmind-x` | `google-deepmind-x` | `discovery` | https://x.com/GoogleDeepMind |
| 15 | `mistral-x` | `mistral-x` | `discovery` | https://x.com/MistralAI |
| 16 | `meta-ai-x` | `meta-ai-x` | `discovery` | https://x.com/MetaAI |
| 17 | `microsoft-copilot-x` | `microsoft-copilot-x` | `discovery` | https://x.com/MSFTCopilot |
| 18 | `cursor-x` | `cursor-x` | `discovery` | https://x.com/cursor_ai |
| 19 | `huggingface-x` | `huggingface-x` | `discovery` | https://x.com/huggingface |
| 20 | `ollama-x` | `ollama-x` | `discovery` | https://x.com/ollama |
| 21 | `replicate-x` | `replicate-x` | `discovery` | https://x.com/replicate |
| 22 | `vercel-x` | `vercel-x` | `discovery` | https://x.com/vercel |
| 23 | `anthropic-news` | `anthropic-news` | `discovery` | https://www.anthropic.com/news |
| 24 | `mistral-news` | `mistral-news` | `discovery` | https://mistral.ai/news/ |
| 25 | `microsoft-ai-updates` | `microsoft-ai-updates` | `discovery` | https://learn.microsoft.com/en-us/azure/ai-foundry/whats-new-ai-foundry |
| 26 | `google-gemini-changelog` | `google-gemini-changelog` | `discovery` | https://ai.google.dev/gemini-api/docs/changelog |
| 27 | `microsoft-ai-blog` | `microsoft-ai-blog` | `discovery` | https://blogs.microsoft.com/ai/ |
| 28 | `qwen-blog` | `qwen-blog` | `primary` | https://qwenlm.github.io/blog/ |
| 29 | `deepseek-official` | `deepseek-official` | `primary` | https://www.deepseek.com/ |
| 30 | `deepseek-status` | `deepseek-status` | `incident` | https://status.deepseek.com/ |
| 31 | `kimi-blog` | `kimi-blog` | `primary` | https://platform.kimi.ai/blog |
| 32 | `zhipu-releases` | `zhipu-releases` | `primary` | https://docs.bigmodel.cn/cn/update/new-releases |
| 33 | `zhipu-devday` | `zhipu-devday` | `primary` | https://www.zhipuai.cn/devday |
| 34 | `doubao-volcengine` | `doubao-volcengine` | `primary` | https://developer.volcengine.com/ |
| 35 | `baidu-qianfan` | `baidu-qianfan` | `primary` | https://cloud.baidu.com/news/ |
| 36 | `tencent-hunyuan` | `tencent-hunyuan` | `primary` | https://cloud.tencent.cn/document/product/1729/97765 |
| 37 | `tencent-hunyuan-api-updates` | `tencent-hunyuan-api-updates` | `primary` | https://cloud.tencent.com.cn/document/product/1729/101849 |
| 38 | `huawei-pangu` | `huawei-pangu` | `primary` | https://www.huaweicloud.com/product/pangu.html |
| 39 | `minimax-releases` | `minimax-releases` | `primary` | https://platform.minimax.io/docs/release-notes/models |
| 40 | `minimax-announcements` | `minimax-announcements` | `primary` | https://platform.minimaxi.com/document/Announcement |
| 41 | `meta-ai-blog` | `meta-ai-blog` | `discovery` | https://ai.meta.com/blog/ |
| 42 | `cohere-blog` | `cohere-blog` | `discovery` | https://cohere.com/blog |
| 43 | `replicate-blog` | `replicate-blog` | `discovery` | https://replicate.com/blog |
| 44 | `ollama-blog` | `ollama-blog` | `discovery` | https://ollama.com/blog |
| 45 | `cursor-changelog` | `cursor-changelog` | `discovery` | https://www.cursor.com/changelog |
| 46 | `vercel-ai-sdk` | `vercel-ai-sdk` | `discovery` | https://ai-sdk.dev/ |
| 47 | `langchain-changelog` | `langchain-changelog` | `discovery` | https://changelog.langchain.com/ |
| 48 | `llamaindex-blog` | `llamaindex-blog` | `discovery` | https://www.llamaindex.ai/blog |
| 49 | `nvidia-nim-docs` | `nvidia-nim-docs` | `discovery` | https://docs.nvidia.com/nim/ |
| 50 | `huggingface-models` | `huggingface-models` | `research` | https://huggingface.co/models?sort=trending |
| 51 | `huggingface-daily-papers` | `huggingface-daily-papers` | `research` | https://huggingface.co/papers |
| 52 | `lmarena-leaderboard` | `lmarena-leaderboard` | `benchmark` | https://lmarena.ai/leaderboard |
| 53 | `china-cac-ai` | `china-cac-ai` | `discovery` | https://www.cac.gov.cn/ |
| 54 | `china-miit-ai` | `china-miit-ai` | `discovery` | https://www.miit.gov.cn/ |
| 55 | `china-gov-ai` | `china-gov-ai` | `discovery` | https://www.gov.cn/ |
| 56 | `qwen-official` | `qwen-official` | `discovery` | https://qwenlm.github.io/ |
| 57 | `alibaba-model-studio` | `alibaba-model-studio` | `discovery` | https://help.aliyun.com/zh/model-studio/model-release-notes |
| 58 | `modelscope` | `modelscope` | `discovery` | https://modelscope.cn/ |
| 59 | `deepseek-official` | `deepseek-official-duplicate-2` | `discovery` | https://www.deepseek.com/ |
| 60 | `zhipu-bigmodel` | `zhipu-bigmodel` | `discovery` | https://bigmodel.cn/ |
| 61 | `moonshot-kimi` | `moonshot-kimi` | `discovery` | https://platform.moonshot.cn/docs/ |
| 62 | `minimax-official` | `minimax-official` | `discovery` | https://www.minimaxi.com/ |
| 63 | `baidu-qianfan` | `baidu-qianfan-duplicate-2` | `discovery` | https://cloud.baidu.com/product-s/qianfan_home |
| 64 | `tencent-hunyuan` | `tencent-hunyuan-duplicate-2` | `discovery` | https://cloud.tencent.com/product/hunyuan |
| 65 | `volcengine-ark` | `volcengine-ark` | `discovery` | https://www.volcengine.com/product/ark |

人工清单覆盖率：`65 / 65 = 100%`。原始重复 ID：`deepseek-official`、`baidu-qianfan`、`tencent-hunyuan`；后出现的重复项使用 `-duplicate-2`，只是清单身份修复，不改变事实来源或 URL。

## 行为映射

| newsFromAI 语义 | mynews v1.6 实现 |
| --- | --- |
| `freshness_filter` | prepare 以业务日期结束边界和每 Feed `max_age_days` 过滤，并保留当天/前一天边界测试 |
| `raw item`/enrichment | SourcePlugin Candidate 的摘要、正文、作者、标签、外链和图片候选进入 JSON-safe 字段；清理/截断/失败状态确定性记录 |
| `news_observations` | JSON Store `state/editorial-observations.json` 保存跨 prepare/refresh 观察历史，不复制 SQLite |
| `cluster`/`repeat_count` | 稳定 URL/标题去重、来源族和保守跨来源事件聚类；重复观察单独计数 |
| candidate contract | `src/mynews/application/candidates.py` 与 `docs/reference/candidate-contract-v1.schema.json`；旧 RunReport 读取保持不变 |
| publication history/weekly feedback | `output/editorial/publication-ledger.csv` 与 `weekly-feedback.md` 只读提示，不自动发布 |
