# vidforge 功能清单：有什么，怎么实现的

日期：2026-10-05 · 这是**参考文档**，按五步向导的顺序列，每条都标了代码位置和状态。
状态图例：✅ 实测可用 · 🟡 可用但有前提（要 key / 要 Node / 要 GPU） · ⚠️ 写了但没在这台机器上跑通过

架构的一句话总结在 [CLAUDE.md](../CLAUDE.md)；设计取舍见 [best-practices.md](best-practices.md)。

## 目录

1. [底层：为什么没有 Docker、没有数据库](#q1)
2. [第 1 步 脚本](#q2)
3. [第 2 步 配音](#q3)
4. [第 3 步 画面](#q4)
5. [第 4 步 渲染](#q5)
6. [第 5 步 发布](#q6)
7. [横向：界面、本地模型、缓存、启动](#q7)
8. [命令行总表](#q8)
9. [没有的功能（以及为什么）](#q9)

---

<a id="q1"></a>
## 1. 底层：为什么没有 Docker、没有数据库

**一个视频 = 一个 `project.json` + 一个文件夹。** 没有数据库、没有容器、没有云服务。

| 存哪 | 内容 |
|---|---|
| `~/vidforge-projects/<名字>/` | `project.json`、`assets/`、`build/`、`.history/` |
| `~/.vidforge/` | 浏览器配置、`me/`（自己的素材）、`categories/`、`voices/`、`models/`、`brand.json` |
| `.env`（项目旁或仓库根） | 各种 key，**从不提交** |

**为什么这样**：一个人单机用，没有并发写、没有关系查询的需求。普通文件反而更强——能直接拷走备份、
能进 git 版本管理、能直接用编辑器打开改、出问题能一眼看出是哪个文件。
加数据库只会换来一个需要迁移脚本的东西。

实现：[`project.py`](../vidforge/project.py) 把 JSON 读成 `Project` / `Segment` / `Clip` / `Overlay`
四个 dataclass，**加载时就校验**（路径存不存在、枚举值对不对、`voice_fx` 拼没拼错）——
不让错误等到渲染三分钟之后才炸。

---

<a id="q2"></a>
## 2. 第 1 步 脚本

### 2.0 选题发现（在写脚本之前）

| 功能 | 状态 | 怎么实现的 |
|---|---|---|
| **热点抓取** | ✅ | [`trends/`](../vidforge/trends/) — 今日头条热榜（50 条 JSON）、百度热搜（52 条）、B 站排行榜（100 条）、Google News RSS（按关键词）、Hacker News。都是公开端点、不要 key、15 分钟缓存 |
| **YouTube 热门** | 🟡 | 要 `YOUTUBE_API_KEY` 走 `chart=mostPopular`。**无 key 的 trending 页实测 0 条**（要 JS/consent），所以没有 key 时这一源为空而不是乱解析 |
| **抖音 / TikTok / 快手** | ❌ | `trends.UNREACHABLE` 里带着实测原因：抖音热点榜 API 返回 200 但 **0 字节**（要 a-bogus 签名）、TikTok 页面 JSON 不含视频列表、快手 TLS 握手超时 |
| **按频道匹配度打分** | ✅ | [`trends/score.py`](../vidforge/trends/score.py) — 平台权重 × 榜位衰减 + 九个方向的领域匹配 + 标题里有数字（能配图表）+ 时间/历史线索。全本地计算，`explain()` 给出**为什么**得这个分 |
| **热榜 / 领域新闻分组** | ✅ | `SOURCES` 的 `kind`：`hot`（大家在看什么）和 `news`（我的方向今天发生了什么）。混在一张表里大的会把小的埋掉 |
| **接到调研验证** | ✅ | 界面每行一个「查同类视频」，直接调现成的 `/api/research/youtube` |



| 功能 | 状态 | 怎么实现的 |
|---|---|---|
| **用我自己浏览器里的 AI 写脚本** | ✅ | [`browser/`](../vidforge/browser/) — Playwright 驱动**你本机的 Chrome/Edge 配置**，把提示词打进 ChatGPT / Claude / Gemini / DeepSeek / Grok / 千问 / Kimi / 文心的网页，等回答抓回来。**不需要任何 API key**，用的是你已经登录的账号 |
| **粘贴的 AI 文本 → 段落** | ✅ | [`script_parser.py`](../vidforge/script_parser.py) — 认「第N段 章节名」「画面：」两栏式、剧本式 `旁白:/Narration:`；**剥掉** AI 的客套话、字数统计、`（停顿）`之类的舞台提示、Markdown 符号 |
| **中英混杂检测** | ✅ | `script_parser.language_issues()` — 中文项目里混进英文句子会被标出来，因为混语旁白读起来是灾难 |
| **结构模板 + 留存体检** | ✅ | [`structure.py`](../vidforge/structure.py)（每次构建都会自动体检，见 5 节） — 三套骨架（数据解说/历史解说/热点解读），每块带时长与字数配额；`check()` 用五条规则体检现有脚本。详见 [data-channel-plan.md 第 11 节](data-channel-plan.md#q11) |
| **选题调研（值不值得做）** | ✅ | [`research/youtube.py`](../vidforge/research/youtube.py) — 查同类视频的播放/时长/频道数。**有 `YOUTUBE_API_KEY` 走 Data API，没有就解析公开搜索页的 `ytInitialData`**，两条路都不用登录。[`research/analyze.py`](../vidforge/research/analyze.py) 把这张表喂给 AI，要回一个 JSON：做/换角度/别做、饱和度、5 个标题、3 个开场钩子、别人没覆盖的空白 |
| **分类预设** | ✅ | [`categories.py`](../vidforge/categories.py) — 每个选题方向一套设置（平台、资料源、禁用词、默认时长）。普通 JSON 文件，`~/.vidforge/categories/<id>.json` |
| **多语言版本** | ✅ | [`i18n.py`](../vidforge/i18n.py) — `export` 导出翻译表 → 翻译 → `import` 合回去；`variants` 让不同语言用不同声音 |
| **生词卡（语言学习变体）** | 🟡 | [`vocab.py`](../vidforge/vocab.py) — 从脚本里挑 6–10 个值得教的词（有 Ollama 时带音标/释义/例句，没有就退回最长实词）。需要 Remotion 渲 `Vocab` 组件 |

---

<a id="q3"></a>
## 3. 第 2 步 配音

| 功能 | 状态 | 怎么实现的 |
|---|---|---|
| **edge-tts（默认）** | ✅ | [`tts/edge.py`](../vidforge/tts/edge.py) — 免费、不要 key。关键是它回传真实的 `WordBoundary` 事件（offset/duration），**逐词时间是帧级准确的**，整条字幕/高亮/章节都建在这上面 |
| **ElevenLabs** | 🟡 | [`tts/elevenlabs.py`](../vidforge/tts/elevenlabs.py) — `/with-timestamps` 端点，同样帧级准确。要 key、按字符收费 |
| **VoxCPM2（本地设计音色）** | 🟡 | [`tts/voxcpm.py`](../vidforge/tts/voxcpm.py) — Apache-2.0 可商用，30 语言 + 9 种方言，**纯文字描述生成一个不存在的新音色**。⚠ 实测 CPU 上约 39 倍实时（12.96s 的输出跑了 505s），只有真有 GPU 才实用。没有 forced alignment，时间按真实总长平均摊 |
| **声音设计（文字描述 → 音色）** | 🟡 | [`tts/voice_design.py`](../vidforge/tts/voice_design.py)（ElevenLabs）/ `voxcpm.design()`。**不克隆任何真人**，所以没有肖像/声音授权问题。你存的 `Simon1` 就是这条路出来的 |
| **用我自己的录音当旁白** | ✅ | [`narration.py`](../vidforge/narration.py) — `Segment.narration` 指一个文件就不走 TTS。解码（**视频也行，自动抽音频**）→ 掐掉首尾静音 → 强制对齐 → sidecar 缓存。按段落录，不是整条录 |
| **字幕与任意录音对齐** | ✅ | [`align.py`](../vidforge/align.py) — faster-whisper（可选依赖）。**转写只用来定位时间，不用来决定字幕内容**：字幕永远显示脚本原文。`difflib` 在归一化 key 上对齐两串 token，没命中的借相邻词插值。实测中文平均误差 **0.068s**，比平均摊好 4.4 倍 |
| **人声美化（浑厚/磁性）** | ✅ | [`voicefx.py`](../vidforge/voicefx.py) — 7 个预设（none/clean/warm/clear/**deep 低沉磁性**/**radio 电台质感**/phone），只有 `highpass`/`afftdn`/`equalizer`/`acompressor` 几条 ffmpeg 滤镜，没有模型。界面可试听对比。**每个预设都不改变时长**——字幕时间是按这段音频量出来的 |
| **音高微调** | ✅ | `voice_pitch` ±4 半音，`rubberband` **只改音高不改时长**（实测 −1 要求得到 −0.97）。界面是一个滑块。只有 `deep` 预设自带变调，其余预设不动基频 |
| **响度统一** | ✅ | `loudnorm=I=-16:TP=-1.5:LRA=11`，在 [`render.py`](../vidforge/render.py) 里**永远排在音色预设之后**（预设管音色，loudnorm 管电平） |
| **TTS 并行提速** | ✅ | `pipeline.TTS_WORKERS = {edge:4, elevenlabs:2, silent:8, voxcpm:1}`。实测 26.0s → 7.4s。VoxCPM 是 1，因为模型跑在本机，并行只会自己抢核 |
| **每段试听 / 换音色** | ✅ | `/api/tts`，界面里每段一个播放按钮 |

---

<a id="q4"></a>
## 4. 第 3 步 画面

### 4.1 素材

| 功能 | 状态 | 怎么实现的 |
|---|---|---|
| **7 个素材源** | ✅ | [`assets/`](../vidforge/assets/) — Pexels、Pixabay、Wikimedia Commons、Openverse、Internet Archive、Google 图片、百度图片。`Clip.source` 存的是**未解析的规格**（`"commons:Battle of Lexington 1775"`），构建时或一键配图时才解析 |
| **一键配图（每段 3–10 张）** | ✅ | `pick_many()` — 一次搜索拿多张、并行下载。跨源累积、`claimed` 去重，实测 19 → 103 张且 0 重复 |
| **准确性把关（宁缺毋滥）** | ✅ | 三道闸：`relevant()`（连续实词二元组，中文另走 `relevant_cjk()`）+ `branded()`（logo/水印/广告词）+ `blocked_host()`。弱关键词只允许走主源。**宁可留空也不插一张不相关的图** |
| **AI 看图复核** | 🟡 | `llm.vision_check()` 用本地 `qwen2.5vl:3b` 判断水印/文字叠加/是否真的画的是这个东西。慢，所以是后台队列 |
| **中文优先搜索** | ✅ | 中文项目先用中文关键词（`llm.keywords_ranked` 按优先级排序），不行才 `translate_batch` 退英文 |
| **巨图瘦身** | ✅ | `normalise()` 把博物馆级大图缩到 2560px 以内，实测素材从 307 MB → 40 MB |
| **素材库台账** | ✅ | `assets/index.json` 记授权、出处、选用情况、看图复核结论 |

### 4.2 动效与图形

| 功能 | 状态 | 怎么实现的 |
|---|---|---|
| **Ken Burns 推拉** | ✅ | ffmpeg `zoompan`，`motion_amount` 控制幅度 |
| **8 种转场** | ✅ | `render.TRANSITIONS` — xfade 里挑了适合讲解类的 8 种（不是炫技那些） |
| **统一调色** | ✅ | `render.LOOKS` + `look_filter()` |
| **段间黑场** | ✅ | `_boundary_fade()` — **保持时长**的淡入淡出，不是 xfade（xfade 会吃掉时间，把字幕推偏） |
| **10 个 Remotion 组件** | 🟡 | [`remotion/app/src/compositions/`](../vidforge/remotion/app/src/compositions/) — Intro、Outro、TitleCard、Timeline、BarChart、LineChart、BigNumber、Compare、Host、Vocab。**每个都按旁白的精确长度渲染**，图表自带出处字幕。需要 Node |
| **真实数据 → 图表** | ✅ | [`data/worldbank.py`](../vidforge/data/worldbank.py) — 世界银行开放数据，不要 key、约 16000 个指标、缓存 30 天。数值自动换算成万亿/亿/万，**出处一路带到屏幕上**。也支持 `from_csv()` 粘表格。原则：**绝不编数字** |

### 4.3 出镜与人脸

| 功能 | 状态 | 怎么实现的 |
|---|---|---|
| **自己的素材库** | ✅ | [`me.py`](../vidforge/me.py) — `~/.vidforge/me/`，标签从文件名来，按「用得最少」挑，所以同一个镜头不会连着几期都出现 |
| **口型同步** | ⚠️ | [`lipsync.py`](../vidforge/lipsync.py) — `synclabs`（要 key，素材会过第三方主机）或 `musetalk`（本地命令，要 GPU） |
| **数字主持人** | 🟡 | [`avatar/`](../vidforge/avatar/) — `host` 是 Remotion 画的卡通形象，嘴型由音频包络驱动，**本地免费且不需要声明**（它明显是个卡通）；`heygen` 是写实数字人，⚠ 未实测，用了会自动打合成内容标 |
| **人脸遮盖 / 换头** | ✅ | [`video/heads.py`](../vidforge/video/heads.py) — OpenCV YuNet 检测（权重自动下到 `~/.vidforge/models/`）→ 跟踪平滑 → 用静态图**或一段动态视频**（椭圆遮罩、逐帧锁定）盖住每张脸 |
| **照片变会说话的头** | 🟡 | [`video/face.py`](../vidforge/video/face.py) — `motion`（音频包络驱动的木偶，不要 GPU）或 `cmd`（`PHOTO_TALK_CMD` → SadTalker/EchoMimic/Hallo，要 GPU） |
| **叠加层** | ✅ | `Overlay` — 画中画，支持滑入/淡入、细边框、出处标注 |

---

<a id="q5"></a>
## 5. 第 4 步 渲染

| 功能 | 状态 | 怎么实现的 |
|---|---|---|
| **分段缓存** | ✅ | `pipeline._segment_key()` — 把段落定义、音频文件的**大小+mtime**、渲染设置一起哈希。改一段只重渲那一段。实测重建 0.6s |
| **硬编自动选择** | ✅ | `render.pick_encoder()` — nvenc / qsv / amf / videotoolbox / libx264 按序探测。实测 30 分钟 40 段约 2.7–4.5 分钟渲完 |
| **并行段渲染** | ✅ | `_stage_render` 多 worker |
| **字幕** | ✅ | [`subtitles.py`](../vidforge/subtitles.py) — SRT + ASS。`write_ass()` 支持 `none`/`keywords`/`karaoke` 三种高亮；**数字和关键词自动高亮**；双语字幕；可选烧入。⚠ 实测烧字幕从 45s 涨到 89s，**瓶颈是字幕滤镜本身，不是编码器** |
| **留存体检（每次构建）** | ✅ | `pipeline._stage_retention` — TTS 完、真实时长已知时跑 `structure.check()`，把问题打进构建日志。**从不阻断构建**（41 秒开场值不值得是作者的决定），但也不让这个决定被默默做掉 |
| **章节** | ✅ | `timeline.json` 用**真实段落时长**（容器长度，不是计划长度——AAC 帧是 21ms，40 段会把字幕推偏一秒）→ YouTube 章节 |
| **背景音乐** | ✅ | `Bgm(file, volume_db=-18, fade_out=3, duck)`。自动循环铺满、结尾淡出；`duck` 用 `sidechaincompress` 让人声把音乐压低约 10 dB、0.4s 恢复 |
| **品牌包** | ✅ | [`brand.py`](../vidforge/brand.py) — 一套 kit（`~/.vidforge/brand.json`）同时决定片头、片尾和**每张图表的配色**。logo 是生成的 SVG（ticks/line/axis 三种刻度标志）；1.2s 片头 + 6s 片尾**默认开**，构建时自动拼。音效用**纯正弦波合成**——没人拥有一条正弦波，所以没有东西要清权 |
| **竖版切片** | ✅ | [`video/vertical.py`](../vidforge/video/vertical.py) — 从**已渲好**的长视频裁一段换画幅，不重渲。`blur`（保全画面，图表不被切）或 `crop`（裁满屏）。字幕按切点重新计时、加大上移 |
| **封面** | ✅ | [`thumbnail.py`](../vidforge/thumbnail.py) — 从某一帧 + 封面文字生成 |

---

<a id="q6"></a>
## 6. 第 5 步 发布

| 功能 | 状态 | 怎么实现的 |
|---|---|---|
| **YouTube 上传** | 🟡 | [`upload/youtube.py`](../vidforge/upload/youtube.py) — 视频 + 封面 + 字幕 + 章节。要 `client_secret.json`（放 `~/.vidforge/`） |
| **AI 使用声明** | ✅ | `project.Disclosure` — 同时驱动 YouTube 的「改动或合成内容」标记和中国 2025-09-01 标识要求的简介文案。`ai_voice` 默认 `True`；**全部段落用自己的录音后，界面会提示取消这个勾选** |
| **多语言成片** | ✅ | `build_<lang>/` 各自一套，`variants` 指定各语言的声音 |

---

<a id="q7"></a>
## 7. 横向

| 功能 | 状态 | 怎么实现的 |
|---|---|---|
| **Web 界面** | ✅ | 后端 [`ui/__init__.py`](../vidforge/ui/__init__.py) 是 **stdlib `ThreadingHTTPServer`**（不是 Flask/FastAPI——少一个依赖），端口 8765。前端 `ui/react/`（Vite + MUI），后端在 `/` 直接服务 `dist/`，首次启动自动构建一次。旧的 vanilla 界面冻结在 `/old`，只作没装 Node 时的兜底 |
| **五步向导 + 三个素材页** | ✅ | 步骤 = 流程（脚本→配音→画面→渲染→发布）；左侧「视频 / 声音 / 图片」= 素材中心页 |
| **陈旧进程自动替换** | ✅ | `STAMP` = 代码 mtime，`/api/health` 带上它；启动时发现在跑的是旧版就 `POST /api/shutdown`（不行就按 PID 杀）。**这个 bug 真实咬过两次**：旧后端配新前端 JS，一键配图直接报 not found |
| **历史版本** | ✅ | 每次写 `project.json` 存一份到 `.history/`，界面里能翻回去 |
| **本地 LLM（可选）** | 🟡 | [`llm.py`](../vidforge/llm.py) — Ollama。文本 `qwen2.5:3b`（搜索词、翻译、章节名，`keywords_batch()` 批处理）；视觉 `qwen2.5vl:3b`（水印/文字叠加/内容核对）。**没装就全部退回启发式规则，不会失败** |
| **一键启动** | ✅ | `start-vidforge.cmd`（检查 Python、装 vidforge、winget 装 ffmpeg）/ `vidforge start`（上次的项目，没有就开选择器）/ `vidforge shortcut`（桌面快捷方式） |
| **空闲自动退出** | ✅ | `VIDFORGE_IDLE_EXIT`，默认 60 分钟。关网页不等于关进程，所以要有这个 |
| **环境自检** | ✅ | `vidforge doctor` |
| **测试** | ✅ | `python -m unittest discover -s tests` — **294 个，离线**（provider/TTS/对齐都 mock 掉）。e2e 浏览器测试没装 playwright 时跳过；真实对齐测试没装 faster-whisper 时跳过 |

---

<a id="q8"></a>
## 8. 命令行总表

界面能做的，命令行都能做：

```powershell
vidforge start                 # 开上次的项目（或选择器）
vidforge init / demo           # 空项目 / 可跑的样例
vidforge build <项目>          # 渲染
vidforge doctor                # 检查 ffmpeg / 依赖

vidforge structure list|outline|prompt|check     # 段落骨架与留存体检
vidforge chat / browser login                    # 用浏览器里的 AI
vidforge i18n export|import                      # 翻译表

vidforge voices / voice design|keep              # 列音色 / 设计音色
vidforge narration <项目> list|attach|clear      # 用自己的录音
vidforge voicefx list|try                        # 人声预设
vidforge trends list|sources                     # 热点发现 + 打分

vidforge assets <项目>                           # 只下素材不渲染
vidforge data search|chart                       # 公开数据集 → 图表
vidforge video heads|detect|face                 # 遮脸 / 照片说话
vidforge me scan|tag                             # 自己的素材库

vidforge brand init|sting|preview                # 品牌包
vidforge short <项目> --list|--segments          # 竖版切片
vidforge upload <项目>                           # 传 YouTube

vidforge category / remotion setup|studio / ui / shortcut
```

---

<a id="q9"></a>
## 9. 没有的功能（以及为什么）

| 没有 | 为什么 |
|---|---|
| **视频中途的关注/点赞引导** | 片尾有 `subscribe` 文案，但中途没有任何 CTA。见 [第 13 节](data-channel-plan.md#q13) |
| **抖音 / TikTok / 快手 热榜** | 要请求签名，拿不到（见 2.0）。正规途径是抖音开放平台 / 巨量算数，都要注册审核 |
| **声音克隆（录一次，以后只打字）** | 还没做，但路线是清的，见 [audio-voice-qa.md 第 8 节](audio-voice-qa.md#q8) |
| **生成背景音乐** | **故意不做**。每条「免费 AI 音乐」路线都有授权陷阱——MusicGen 是 CC-BY-NC，变现频道不能用。所以只做正弦波合成的音频标记 |
| **克隆真人声音** | 不需要了——直接用你本人念的（见 3 节） |
| **录像 / 抠像 / 背景虚化 / 换背景** | 只录音，不录像。画面处理仍在 vidforge 之外 |
| **BGM 自动踩点** | 计划里，还没做 |
| **地图组件** | 计划里的下一个 P2（世界/中国地图高亮 + 路线动画） |
| **FRED / 国家统计局数据** | 世界银行是年度粒度，月度 CPI、利率这些还接不到 |
| **Docker / 数据库 / 云服务** | 见第 1 节。单机单人、文件驱动是设计，不是妥协 |
