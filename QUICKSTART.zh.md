# vidforge 上手指南（v0.2）

vidforge 把"脚本 → 成片 → 发布"做成一条流水线，配一个本地网页向导。你负责**写脚本、挑画面**，它负责配音、字幕、运镜、拼接、封面、章节、上传。

```
 1 脚本        2 配音          3 画面                 4 渲染             5 发布
 整篇贴进来    选声音，试听     每段挑图/视频片段/动画   一键出片，看进度    YouTube 一键上传
 自动拆段      全部配音        搜索三大素材库          草稿/成片质量      章节+署名自动生成
```

---

## 0. 安装（一次）

**Windows**：双击 `start-vidforge.cmd`。它会检查 Python、安装 vidforge、用 winget 装 ffmpeg，然后打开向导。
**macOS**：双击 `start-vidforge.command`（第一次右键 → 打开）。用 Homebrew 装 ffmpeg。

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
2. **本地文件**：拖入或选择图片/视频（会复制进 `assets/local/`）。iPhone 的 HEIC 请先转 JPG。
3. **动画（Remotion）**：TitleCard 标题卡 / Timeline 时间轴 / BarChart 柱状图，加入后点「编辑」改文字。第一次用需要 `vidforge remotion setup`（要 Node.js）。

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
python tools/stress.py out --minutes 30 && vidforge build out   # 30 分钟压力测试
python -m unittest discover -s tests   # 44 个测试；e2e 需 pip install -e ".[dev]"
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
| 想手工精修 | `build/merged.mp4`（无 BGM、未烧字幕）+ `final.srt` 拖进 DaVinci Resolve |
