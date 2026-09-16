# vidforge 上手指南（中文）

vidforge 不是一个有界面的剪辑软件。它是一条命令行流水线：**你写一个 `project.json`（每段旁白 + 每段配什么画面），它输出成片 `final.mp4` + 字幕 + 封面。**

先建立这个心智模型：

```
你负责                          vidforge 负责
─────────────────────────       ─────────────────────────────────────────────
写脚本，切成若干段                每段：配音（TTS）→ 逐词时间戳 → 字幕
每段指定一张图 / 一段视频 /       每段：图片加推拉运镜（Ken Burns）或视频循环/裁切成旁白长度
  或一个 Pexels 搜索词           全部段拼接 → 混 BGM → 可选烧字幕 → 封面 → 章节时间表
```

一段 = 一张画面 + 讲这张画面时说的话。时长你不用填，由配音长度决定。

---

## 第 0 步：一次性安装（已在这台 Windows 上完成）

```powershell
winget install Gyan.FFmpeg              # 装 ffmpeg（Mac: brew install ffmpeg）
cd C:\Simon\Projects\vidforge
python -m pip install -e .              # 安装 vidforge 命令
vidforge doctor                         # 应看到 ffmpeg 路径、edge-tts: ok
```

> Windows 上 winget 装完 ffmpeg 要**重新开一个终端**，PATH 才会更新。就算没更新，vidforge 也会自己去 winget 的安装目录找。

在 Mac 上做同样的三步即可，代码是跨平台的。

---

## 第 1 步：先跑通 demo（1 分钟，不需要任何 key）

打开 PowerShell（或 Mac 终端），随便找个放项目的目录：

```powershell
cd C:\Simon\Projects
vidforge demo demo1          # 生成一个 4 段的示例项目：demo1\project.json + demo1\assets\*.jpg
vidforge build demo1         # 渲染，约 1 分钟
```

看到：

```
[vidforge] 4 segments · tts edge · voice en-US-AndrewNeural
[vidforge]   tts  hook           24 words    8.64s
...
[vidforge] done in 55.8s · 42.6s video · C:\Simon\Projects\demo1\build\final.mp4
[vidforge] chapters:
  00:00 hook
  00:08 eruption
```

打开 `demo1\build\` 目录：

| 文件 | 是什么 |
|---|---|
| `final.mp4` | **成片**（demo 里字幕已烧进画面） |
| `final.srt` | 字幕文件，上传 YouTube 时作为字幕轨单独上传（比烧进去更利于 SEO） |
| `thumbnail.jpg` | 1280×720 封面图 |
| `timeline.json` | 每段起止时间，终端里打印的 `chapters` 直接粘到 YouTube 简介就是章节 |
| `merged.mp4` | 未混 BGM、未烧字幕的纯旁白版本，想手工精修就把它拖进 DaVinci Resolve |
| `audio/*.mp3` | 每段配音；`*.json` 是逐词时间戳缓存 |
| `clips/*.mp4` | 每段单独的成片 |

---

## 第 2 步：做你自己的第一条视频

### 2.1 建项目

```powershell
cd C:\Simon\Projects
vidforge init my-first-video
```

得到：

```
my-first-video\
  project.json      ← 你要编辑的唯一文件
  assets\           ← 把图片放这里
```

### 2.2 准备素材

- 图片：JPG/PNG，**横图**，建议 ≥ 1920 宽。来源：自己的图、公有领域（Wikimedia Commons、Internet Archive）、或用 `pexels:` 搜索词让它自动下载（见第 3 步）。
- BGM（可选）：一段 mp3，放进 `assets\bgm.mp3`。

### 2.3 编辑 `project.json`

用 VS Code 打开，照这个改：

```jsonc
{
  "title": "The Year Without a Summer",
  "language": "en",
  "voice": "en-US-AndrewNeural",         // 声音，见 2.4
  "rate": "-3%",                          // 语速，负数变慢
  "tts": { "provider": "edge" },          // 免费；换 ElevenLabs 见第 4 步
  "width": 1920, "height": 1080, "fps": 30,
  "bgm": { "file": "assets/bgm.mp3", "volume_db": -18, "fade_out": 3 },   // 没有就写 null
  "subtitles": { "burn": false, "max_chars": 42, "font": "Arial", "font_size": 22 },
  "thumbnail_text": "THE YEAR\nWITHOUT A SUMMER",     // 封面大字，\n 换行
  "segments": [
    { "id": "hook",     "text": "In 1815, a volcano ...",  "image": "assets/01.jpg", "motion": "zoom_in",  "pause_after": 0.6 },
    { "id": "eruption", "text": "Mount Tambora ...",       "image": "assets/02.jpg", "motion": "pan_right" },
    { "id": "europe",   "text": "By the following June ...", "image": "pexels:snow covered farm field", "motion": "zoom_out" },
    { "id": "legacy",   "text": "Out of that cold ...",    "video": "pexels:rain on window" }
  ]
}
```

每段字段：

| 字段 | 说明 |
|---|---|
| `id` | 段名，唯一；会成为章节名和文件名 |
| `text` | 这一段的旁白原文。**按口语写、短句、标点齐全**——标点决定字幕在哪里断行、TTS 在哪里停顿 |
| `image` | 本地图片路径（相对 project.json），或 `pexels:搜索词` |
| `video` | 本地视频，或 `pexels:搜索词`；与 `image` 二选一。视频会循环/裁到旁白长度，自带声音丢弃 |
| `motion` | `zoom_in` / `zoom_out` / `pan_left` / `pan_right` / `none`（仅图片有效） |
| `pause_after` | 这段说完后停几秒（默认 0.5） |
| `voice` | 只给这一段换个声音（比如引用别人的话） |

### 2.4 选声音

```powershell
vidforge voices --lang en-US        # 英文声音列表；常用 en-US-AndrewNeural、en-US-BrianNeural、en-GB-RyanNeural
vidforge voices --lang zh-CN        # 中文；常用 zh-CN-YunxiNeural（男）、zh-CN-XiaoxiaoNeural（女）
```

### 2.5 先只听配音，再渲染

```powershell
vidforge build my-first-video --only-tts    # 只生成 audio\*.mp3，几秒钟；打开听一遍，改错字、改断句
vidforge build my-first-video               # 满意后完整渲染
vidforge build my-first-video --burn        # 想把字幕烧进画面就加 --burn
```

**改了某一段的文字 → 重新 build 只会重新合成那一段的配音**（其它段走缓存），所以放心反复改。

渲染速度：1080p 约 1.3× 实时，20 分钟视频约 25 分钟。想快速预览，在 project.json 里加 `"supersample": 1`。

---

## 第 3 步：让 Pexels 自动配图（免费，要注册 key）

1. 到 https://www.pexels.com/api/ 注册，拿到 API key（免费，200 次/小时）。
2. 在项目目录（或 `C:\Simon\Projects\vidforge\`）新建文件 `.env`：
   ```
   PEXELS_API_KEY=你的key
   ```
3. 在 segment 里用 `"image": "pexels:搜索词"` 或 `"video": "pexels:搜索词"`（英文搜索词效果最好）。
4. **先看图再渲染**：
   ```powershell
   vidforge assets my-first-video      # 只下载素材到 assets\pexels\，不渲染
   ```
   打开 `assets\pexels\` 看图；不满意就改搜索词，删掉 `assets\pexels\index.json` 里对应的那一条（或整个文件），再跑一次。

规则：同一个项目里不会两段用到同一张图；视频优先选比旁白长的片段；`build\credits.txt` 会列出所有素材的作者和链接，贴到视频简介里（Pexels 不强制署名，但有它更像"有来源的内容"）。

---

## 第 4 步：换 ElevenLabs 配音（付费，$5/月起）

1. https://elevenlabs.io → Profile → API keys，拿 key；在 Voices 里挑一个声音（或克隆自己的）。
2. `.env` 里加一行 `ELEVENLABS_API_KEY=你的key`。
3. 看你库里有哪些声音：
   ```powershell
   vidforge voices --provider elevenlabs
   ```
4. project.json 改两处：
   ```jsonc
   "voice": "Brian",                                 // 声音名，或 voice_id
   "tts": { "provider": "elevenlabs", "model": "eleven_multilingual_v2",
            "stability": 0.5, "similarity_boost": 0.75, "style": 0.0 }
   ```
   - `eleven_multilingual_v2`：质量最好，中英都行；`eleven_flash_v2_5`：便宜一半、快，质量略低。
   - `rate` 仍然有效（映射到 speed 0.7–1.2）。
5. 一样先 `--only-tts` 试听。ElevenLabs 按字符计费，缓存保证同一段文字不会重复扣费。

---

## 常见问题

| 现象 | 处理 |
|---|---|
| `ffmpeg not found` | 新开终端；或 `vidforge doctor` 看它找到的路径；或设环境变量 `VIDFORGE_FFMPEG_DIR` |
| `image not found` | 路径相对 project.json 所在目录写；Windows 也用 `/` |
| 字幕中文显示方块 | `subtitles.font` 改成 `"Microsoft YaHei"`（Windows）/ `"PingFang SC"`（Mac） |
| 配音读错了数字/缩写 | 在 `text` 里直接改成读法（"1815" → "eighteen fifteen"），字幕会跟着变，这是可接受的取舍 |
| edge-tts 报错/无声 | 它是非官方接口，偶尔抖动；重跑即可。已生成的段有缓存不受影响 |
| 想手工精修 | 把 `build\merged.mp4` + `final.srt` 拖进 DaVinci Resolve |

## 典型工作流（一条 20 分钟视频）

1. 写脚本（我可以在对话里按 segment 结构直接给你 JSON）→ 30–40 段，每段 2–4 句。
2. `vidforge build x --only-tts` → 听一遍 → 改文字 → 再听。
3. 每段填 `image`/`video`：手头有的用本地图，没有的写 `pexels:` 搜索词 → `vidforge assets x` 看图。
4. `vidforge build x` → 看成片 → 改 → 再 build（只重做改过的段）。
5. 上传 `final.mp4`，字幕轨用 `final.srt`，封面 `thumbnail.jpg`，简介贴 chapters 和 `credits.txt`。
