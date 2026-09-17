# vidforge 上手指南（v0.4）

vidforge 把"脚本 → 成片 → 发布"做成一条流水线，配一个本地网页向导。你负责**写脚本、挑画面**，它负责配音、字幕、运镜、拼接、封面、章节、上传。

```
 1 脚本        2 配音          3 画面                 4 渲染             5 发布
 整篇贴进来    选声音，试听     每段挑图/视频片段/动画   一键出片，看进度    YouTube 一键上传
 自动拆段      全部配音        搜索三大素材库          草稿/成片质量      章节+署名自动生成
```

---

## 0. 安装与启动（一次）

**Windows**：双击 `start-vidforge.cmd`。它会检查 Python、安装 vidforge、用 winget 装 ffmpeg，然后打开向导。
**macOS**：双击 `start-vidforge.command`（第一次右键 → 打开）。用 Homebrew 装 ffmpeg。

装好后只需要记一条命令：
```powershell
vidforge start              # 打开上次的项目；没有就进"项目页"新建/选择
vidforge shortcut           # 在桌面生成 vidforge 快捷方式，以后双击即开（Windows .lnk / Mac .command）
```
项目默认放在 `~/vidforge-projects/`（设 `VIDFORGE_WORKSPACE` 可换）。左侧栏点项目名可随时切换项目。

**界面**：左侧是五步导航（完成的步骤变绿）；左下角切主题——跟随系统 / 亮色 / 暗色 / **护眼**（暖色低蓝光）；右上角「✦ AI 助手」打开侧栏。

**保存与后悔药**（不需要数据库，全是文件）：
- 每次改动 0.7 秒后自动保存（右上角显示上次保存时间）；「保存」按钮或 **Ctrl+S** 立即保存并留一份整份历史；
- 「历史版本…」下拉：回到任一时刻的整份项目（`.history/`，保留 30 份）；
- **每段独立版本**：第 1 步每行、第 3 步编辑器都有「版本」——这一段每次保存有变化就留一版（A1…A5），点哪版就只回这一段，其他段不动；
- **每段成片独立缓存**：`build/clips/<段>.<哈希>.mp4`，只重渲改过的段；回到旧版本时旧成片还在（每段保留 5 版），几乎不用等。

手动方式：
```powershell
winget install Gyan.FFmpeg          # Mac: brew install ffmpeg
cd C:\Simon\Projects\vidforge
python -m pip install -e .
vidforge ui examples\demo           # 打开 http://127.0.0.1:8765
```

页面右上角有一排**状态点**：ffmpeg（含用到的编码器）、Pexels、Pixabay、Commons、动画、YouTube。红点不影响基本使用——Commons 永远可用、无需 key。

---

## 1. 五步向导

### 第 1 步 · 脚本
- 把整篇脚本贴进大文本框，**一段一空行**，点「拆成段落」。超过 ~50 词的段落会按句子再切。
- 段首一行 `# 章节名` 会成为该段的章节名（YouTube 章节、章节标题卡都用它）。
- 旁白**按口语写、短句、标点齐全**：标点决定字幕在哪断行、TTS 在哪停顿。
- 每段 = 一个意思 = 一组画面。2–4 句最合适。

**用你浏览器里的 AI 直接生成脚本**（第 1 步顶部的折叠面板）：填主题、时长、受众、要点 → 选网站（ChatGPT / Claude / Gemini / DeepSeek / Grok / 千问 / Kimi / 文心）→「在我的浏览器里生成」。第一次先点「登录各站点…」：会打开一个**专用的 Edge 窗口**（独立配置文件，不动你日常的浏览器），逐个登录后关窗即可，之后不用再登。生成时那个窗口会自动打开、输入、等待、复制回答，回答填进文本框后点「拆成段落」。不想让它碰账号就点「只复制提示词」自己去贴。
⚠ 这些网站的条款都不允许自动化访问；它是**你自己的账号、可见窗口、一次一问**，风险由你判断，遇到验证码手动点一下即可。

**AI 助手侧栏**（右上角 ✦）：选「本地模型」（装了 Ollama 时，离线、1–8 秒）或任一你登录过的网站（ChatGPT / Claude / Gemini / DeepSeek …），提问后答案显示在侧栏，「附上当前段」把选中段的旁白带进问题，「插入脚本框」一键放进第 1 步的文本框。

### 第 2 步 · 配音
- 配音服务：`edge`（免费）默认；`ElevenLabs` 需在 `.env` 放 key；`静音占位` 不联网，只用来快速看画面。
- 点声音框会列出可选声音；「用第一段试听这个声音」几秒出结果。
- 「全部配音」后每段一行播放条。改了文字的段会标 ⟳，重新试听即可（缓存按文字+声音区分，不会重复扣费）。

### 第 3 步 · 画面（核心）
左边**故事板**：每段一张卡（缩略图、时长、片段数）；缺画面的段有红点。点卡片进入右侧编辑器。

右侧上半是这一段的**片段条**：可以放多个片段，按顺序播放，总长自动对齐旁白：
- 视频片段显示「4.0 → 9.5 s」，点「选段」拖两个滑块选起止；
- 图片片段可设运镜（推近/拉远/左右平移）和时长（留空 = 自适应补满）；
- 上方的绿字/黄字告诉你「已选 x 秒 / 需要 y 秒」以及不够时怎么补（延长或循环最后一个片段）。
- 「▶ 预览这一段」：草稿质量只渲这一段，几秒到几十秒出结果——**不用等全片**。

右侧下半是**添加片段**的三个 tab：
1. **搜索素材**：来源 Pexels / Pixabay / Wikimedia Commons，图片或视频；搜索框已按旁白预填了关键词，下面有建议词可点。
   - 图片：点即加入。竖图/古画会自动用"模糊背景 + 完整居中"处理，不裁切。
   - 视频：悬停预览，点开选段对话框，拖起止点（默认给你选了正好补满旁白的长度），「播放所选」确认后加入。
   - 每张素材的作者与许可自动记进 `credits.txt`，发布时贴进简介。只接许可明确的来源（Commons 只保留公有领域 / CC0 / CC BY）。
   - **Google 图片 · 仅 CC 许可**：通过你的浏览器搜（会弹出 Edge 窗口约 15 秒），默认只返回带 Creative Commons 标记的结果；**Google 全部 / 百度图片**标 ⚠ 版权未知，加入前要确认——用于变现视频可能收到版权投诉，来源页会记进 credits。
   - 声音：第 2 步「浏览…」按口音/地区/性别筛（英语 14 种口音、普通话、东北话、陕西话、粤语、台湾国语），每个可 3 秒试听；每段行右侧「换声」可只给这一段换声音。
2. **本地文件**：拖入或选择图片/视频（会复制进 `assets/local/`）。iPhone 的 HEIC 请先转 JPG。
3. **动画（Remotion）**：TitleCard 标题卡 / Timeline 时间轴 / BarChart 柱状图，加入后点「编辑」改文字。第一次用需要 `vidforge remotion setup`（要 Node.js）。
4. **🎥 我的镜头**：从你自己录的素材库里按标签取一段真人画面（详见下文 2.6）。

「✨ 没画面的段一键自动配图」：按每段关键词生成搜索片段，渲染时自动取第一张——先出一版粗剪，再逐段替换不满意的。

### 第 4 步 · 渲染
- 质量：**草稿**（快 3 倍，看效果）/ **成片**（CRF 18、2× 超采样、锐化）。
- 字幕：只出 `.srt`（推荐，上传时作字幕轨，利于 SEO）或烧进画面；样式可选白字黑边 / 半透明底框。
- 转场：片段间交叉淡化秒数（0 = 硬切）。背景音乐：填 `assets/bgm.mp3`，说话时自动压低。
- 章节标题卡：每个有章节名的段前自动加 3 秒卡片。旁白响度归一默认开。
- 点「▶ 渲染」：进度条显示阶段（配音 / 取素材 / 动画 / 渲染 n/N 段 / 合成）和预计剩余时间；可「停止」。完成后播放器、封面、章节、下载链接出现。

### 第 5 步 · 发布
- 填 YouTube 标题、标签、可见性、分类、简介；章节和素材署名会自动追加。
- 「⬆ 上传到 YouTube」：默认私有（未通过 Google 审核的应用一律锁私有），到 YouTube Studio 检查后公开/定时。每天约 5 条配额。首次需要 `~/.vidforge/client_secret.json`（见下文）。
- 头条/西瓜没有上传接口：拿 `build/final.mp4` + `thumbnail.jpg` 手动发。

---

## 2. 中文版 / 多语言

右上角切换语言（`en` / `zh`）。切到 `zh` 后：第 1 步的文本框编辑的是中文旁白、第 2 步选中文声音（默认 `zh-CN-YunxiNeural`），标题/简介也各自独立；画面共用。渲染输出到 `build_zh/`，英文版 `build/` 不受影响。

没翻译的段会在顶部列出；也可以用命令行导出翻译表：
```powershell
vidforge i18n export my-video --lang zh   # 生成 i18n_zh.json，填空后
vidforge i18n import my-video --lang zh
```

---

## 2.5 本地小模型（可选，推荐）

装 [Ollama](https://ollama.com) 后执行 `ollama pull qwen2.5:3b`（约 2 GB；内存充裕可用 `qwen2.5:7b`），vidforge 会自动检测（左下角状态点"本地模型"变绿）并用它做：素材搜索的「✦ AI 建议」关键词、中文搜索词自动译成英文再搜 Pexels/Pixabay、AI 侧栏的离线问答。完全本地、免费、不联网。整篇脚本生成这类重活仍建议用浏览器里的大模型。

## 2.6 真人素材库 + 口型同步（P3.5）

「素材是无人出镜的 TTS+图库」是 2026 年最容易被平台判定低质量的模式；把自己录的镜头混进画面能显著降低这个风险。做法：

1. **建库**：把你不同场景/衣服/发型下录的素材，放进 `~/.vidforge/me/`（所有项目共用）或某个项目的 `assets/me/`（只给这个项目用，优先级更高）。**文件名就是标签**，用 `_`/`-`/空格 分词，例如：
   - `backyard_glasses_talking_01.mp4` → 标签 `backyard glasses`，含"说话/talking"关键词 → 判定为**说话镜头**
   - `study_bluejacket_02.mp4` → 标签 `study bluejacket` → 沉默 B-roll
   - 中文同理：`说话_书房_01.mp4`、`散步_海边.mp4`。
2. **沉默镜头（推荐，零风险）**：你在录像里走动、望向远方、翻书——不需要说话，也就不需要口型同步，加入片段/画中画后直接配旁白，跟普通素材视频没区别，风险最低。
3. **说话镜头（需口型同步）**：你对着镜头说话的素材，会被裁剪/循环到旁白时长，再用第 4 步渲染设置里的 **口型同步 provider** 对上嘴型：
   - `synclabs`（sync.so API，`SYNC_API_KEY`，视频经临时文件托管上传，第三方经手）
   - `musetalk`（本地命令 `LIPSYNC_CMD`，接你自己跑的 MuseTalk/LatentSync，需要 NVIDIA 显卡，视频不出本机）
   - 不设置也能渲染，但嘴型对不上，只适合真的不介意穿帮的片段。
4. 第 3 步「🎥 我的镜头」tab：选标签/说话与否，「作为本段主画面」或「作为画中画」——不指定具体文件，渲染时自动挑**用得最少**的匹配镜头，同一素材不会一集比一集眼熟。上传新镜头、改标签都能在这个 tab 直接做，或用命令行 `vidforge me scan` / `vidforge me tag <文件名> --tags a,b --talking true`。
5. 只要真的用了口型同步（provider ≠ none），vidforge 会自动在简介里加上"主持人形象为数字合成"的 AI 内容披露（YouTube synthetic 标记 + 中国 2025-09-01 标注新规都要求）；纯沉默镜头不触发这条。

## 3. 各种 key（都可选）

在项目目录（或 vidforge 目录）建 `.env`：
```
PEXELS_API_KEY=...        # https://www.pexels.com/api/  免费，200 次/小时
PIXABAY_API_KEY=...       # https://pixabay.com/api/docs/  免费
ELEVENLABS_API_KEY=...    # https://elevenlabs.io  付费
```
YouTube：Google Cloud 控制台 → 启用 YouTube Data API v3 → OAuth 客户端（桌面应用）→ 下载 JSON 存为 `C:\Users\<你>\.vidforge\client_secret.json`；`pip install -e ".[youtube]"`。

---

## 4. 命令行（向导做的事命令行都能做）

```powershell
vidforge init my-video                 # 新项目模板
vidforge build my-video [--lang zh] [--burn] [--only-tts]
vidforge assets my-video               # 只取素材不渲染
vidforge upload my-video [--lang zh] [--publish-at 2026-10-01T09:00:00Z]
vidforge voices --lang zh-CN | --provider elevenlabs
vidforge remotion setup | studio
vidforge doctor
vidforge browser login [chatgpt claude …]   # 打开专用浏览器登录各 AI 站点（一次）
vidforge chat deepseek "用三句话介绍坦博拉火山"   # 通过你的浏览器提问并打印回答
python tools/stress.py out --minutes 30 && vidforge build out   # 30 分钟压力测试
python -m unittest discover -s tests   # 56 个测试；e2e 需 pip install -e ".[dev]"
```

`project.json` 是唯一真相，向导和命令行改的是同一个文件。片段写法：
```jsonc
{ "id": "eruption", "label": "The eruption", "text": "…", "text_zh": "…",
  "clips": [
    { "video": "assets/pexels/lava-123.mp4", "in": 4.0, "out": 9.5 },
    { "image": "assets/commons/tambora.jpg", "motion": "zoom_in", "duration": 4 },
    { "video": "pexels:volcanic ash cloud" },
    { "remotion": { "composition": "TitleCard", "props": { "title": {"en": "1815", "zh": "一八一五"} } } }
  ] }
```

---

## 5. 性能与长视频

- 30 分钟（40 段）在这台机器上 **2.7–4.5 分钟**渲完（Intel QSV 硬编 + 并行段渲染；含首次配音约 4.5 分钟，配音已缓存约 2.7 分钟）；没有硬件编码器时用 libx264，慢 3–5 倍。
- 改一段只重做那一段的配音；素材和动画都有缓存；「预览这一段」不动其他段。
- 时间轴用每段的**实际**时长累加：30 分钟字幕漂移 21 ms（一个音频帧）。
- 段落建议 ≤ 600 字符；超过 2500 会警告（ElevenLabs 单次上限 5000）。

## 6. 常见问题

| 现象 | 处理 |
|---|---|
| 状态点 ffmpeg 红 | 新开终端；`vidforge doctor`；或设 `VIDFORGE_FFMPEG_DIR` |
| 搜索提示需要 key | 填 `.env`，或来源切 Commons |
| 上传的图不能用 | 只支持 JPG/PNG/WebP、MP4/MOV；HEIC 先转 |
| 中文字幕方块 | 字幕字体：Windows `Microsoft YaHei`，Mac `PingFang SC`（`variants.zh.subtitles.font`） |
| 渲染失败 | 看进度条下的日志；`build/build.log` 有全文，贴给我 |
| 上传后是私有 | 正常，Studio 里改 |
| 浏览器生成提示"没找到输入框" | 先 `vidforge browser login`（或页面上「登录各站点…」）登录；或该站点改了页面结构——把 `~/.vidforge/browser-<站点>-*.png` 截图发我 |
| Google 图片提示 unusual traffic | 在弹出的窗口里完成人机验证后重试；一次别搜太多 |
| 想手工精修 | `build/merged.mp4`（无 BGM、未烧字幕）+ `final.srt` 拖进 DaVinci Resolve |
