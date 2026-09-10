# 程序快照说明

- 项目名称：手机自动拍照 + AI 图片分析（全自动写字机视觉巡检原型）
- 项目作用：在手机网页端调用摄像头，按固定间隔自动拍照并保存到本地；可将最新照片发送到 Vercel 后端，由 Gemini API 做视觉分析并把结果返回网页。
- 当前主要功能：
  1. 手机浏览器调用前/后摄像头。
  2. 每 5 秒自动拍照。
  3. 照片保存到浏览器 IndexedDB，本地画廊显示。
  4. 支持手动分析最新照片。
  5. 支持“每拍一张都自动交给 AI 分析”。
  6. 前端不保存 Gemini API Key；后端通过 Vercel 环境变量 GEMINI_API_KEY 读取密钥。
  7. 后端直接调用 Gemini Developer API，不使用 Vercel AI Gateway 额度。
  8. 当前默认视觉模型：gemini-3.5-flash-lite。
- 版本号：v1.0-working
- 快照日期：2026-09-10
- GitHub 仓库：a1507813774-dotcom/a1507813774-dotcom.github.io
- 快照分支：snapshot-camera-ai-v1.0-2026-09-10
- 生产网页：https://a1507813774-dotcom-github-io.vercel.app
- 关键文件：
  - index.html：手机端拍照、图库、AI 分析界面与调用逻辑。
  - api/analyze.js：Vercel Serverless Function，直接调用 Gemini API。
  - package.json：项目依赖与模块配置。

## 运行所需服务器环境变量

- GEMINI_API_KEY：必需。只存放在 Vercel 环境变量中，不应写入源码或公开仓库。
- GEMINI_MODEL：可选。未设置时使用 gemini-3.5-flash-lite。
- ANALYZE_TOKEN：可选。若设置，则前端请求需要提供匹配的分析访问码。

## 以后在其他 ChatGPT 对话中的调用方式

可直接说：

“调用我 GitHub 仓库 a1507813774-dotcom/a1507813774-dotcom.github.io 的 snapshot-camera-ai-v1.0-2026-09-10 分支，这是 2026-09-10 已验证可用的手机自动拍照 + Gemini 图片分析程序。先读取 SNAPSHOT_INFO.md、index.html、api/analyze.js、package.json，再基于它继续修改；保留旧版本，不覆盖这个快照分支。”

此快照用于长期保留当前已验证可用版本，后续开发应新建版本或新分支，不覆盖本快照。
