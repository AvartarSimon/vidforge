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
| **录音棚（提词器 + 设备选择 + 电平表）** | ✅ | `RecordStudio.tsx` — 提词器压在摄像头画面**上面**（念稿时眼睛要能看镜头）、摄像头/麦克风分别选（「音频口」几乎从不是浏览器默认）、实时电平表（录废的最常见原因是选错输入，事后才发现是一片静音）、3 秒倒数。**一条录像可以同时**当这一段的旁白和素材库里的出镜镜头 |
| **实时美颜/美型/换背景/换装** | ✅ | [`ui/react/src/fx/`](../vidforge/ui/react/src/fx/) — 浏览器内 MediaPipe（人像多类分割：背景/头发/身体皮肤/脸部皮肤/衣服 + 478 点人脸网格）+ WebGL。磨皮是**只作用在皮肤上**的双边滤波；瘦脸/大眼是局部形变，上限压低；背景虚化/书房/图片/视频/纯色不要绿幕；衣服/头发只换色。录的是处理后的 canvas，所见即所得。模型首次使用时由 [`webmodels.py`](../vidforge/webmodels.py) 下到 `~/.vidforge/models/` |
| **提词器自动滚动** | ✅ | `fx/Teleprompter.tsx` — 按字/分钟滚动，空格暂停、↑↓ 调速、R 回开头；位置靠上/满屏/靠下，可镜像 |
| **一条录像 = 画面 + 旁白** | ✅ | `/api/record/save` `as_visual` — 按首尾声音切同一个 mp4，旁白掐静音时没东西可掐，口型和声音同帧开始；`as_window` 让它当竖屏模板的小窗 |
| **录像不丢** | ✅ | `narration.save_upload` 每条按时间命名，重录不覆盖；`/api/takes` 列出项目里全部录像和用在哪一段，`/api/takes/use` 放回（画面/小窗/旁白）；录了没用就重录、换段、离开页面时 `RecordStudio` 以 `keep_only` 自动存下。保存走 `merge.merge3` 三方合并（页面带上它载入时的 `base`），后台写入不再被页面的旧副本盖掉——实测过五条录像就是这样从项目里「消失」的 |
| **后台保存队列** | ✅ | `state/saveQueue.ts` — 「用这一条」把 Blob 交给模块级队列（切页面不丢），按顺序以原始字节 POST `/api/record/save?o=<json>`，页面立刻跳下一段；`BackgroundJobs` 在顶栏显示保存/渲染进度、渲染完成提醒并 reload。保存后 `State.warm_narration` 在后台把 Whisper 对齐写进渲染要用的 `build/audio/<seg>.own.json`，`narration.prepare` 有锁，不会和渲染重复跑 |
| **特效引擎帧率** | ✅ | `fx/engine.ts` — 只处理摄像头新帧（`requestVideoFrameCallback`），以前 60Hz 循环把同一帧过两遍模型，M1 上录出来只有 14 帧；两个模型都开且单帧超过 24ms 时轮流跑、复用上一帧结果 |
| **原声录音** | ✅ | `utils.micConstraints` — 默认关掉浏览器的回声消除/通话降噪/自动增益（为视频通话调的，会削掉低频和泛音、让音量起伏）；实测录音底噪本来就在 −76 dB。RNNoise（arnndn）也测过，在这种录音上没有改善，没加 |
| **导出 / 下载** | ✅ | 第 5 步顶部是成片（`ResultCard`）：下载链接走 `/files/...?download=<标题>`，服务器回 `Content-Disposition: attachment`（RFC 5987 中文名）——只靠 `download` 属性时有的浏览器直接开播放页；所有链接带 mtime，重渲/重导后不会从缓存拿旧文件；`/api/reveal` 在访达/资源管理器中显示。多平台导出按任务状态轮询，离开页面再回来接着显示进度（以前会永远停在「导出中…」） |
| **浑厚磁性（自然）人声** | ✅ | `voicefx` `magnetic`：胸腔 EQ + 轻泛音 + 慢压缩，不移调。试听 `/api/voicefx/preview` 现在走和渲染一样的 `chain()` + `pitch_filter()`（以前用原始滤镜串、不带音高滑块，试听和成片不一致）；面板同时放进录制棚 |
| **画面预设（柔肤/补光）** | ✅ | [`videofx.py`](../vidforge/videofx.py) — `bilateral` 保边平滑 + `unsharp` 回加细节。**不是 `gblur`**：普通模糊会把眼睛、发丝、下颌线一起抹掉。每个预设都不改分辨率和时长 |
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
| **10 个 Remotion 组件** | 🟡 | [`remotion/app/src/compositions/`](../vidforge/remotion/app/src/compositions/) — Intro、Outro、TitleCard、Timeline、BarChart、LineChart、BigNumber、Compare、Host、Vocab。**每个都按旁白的精确长度渲染**，图表自带出处字幕。竖屏项目里 Timeline 改成竖排（左边竖线、事件上下排列），图表都画在小窗和字幕之间那一带。需要 Node |
| **真实数据 → 图表** | ✅ | [`data/worldbank.py`](../vidforge/data/worldbank.py) — 世界银行开放数据，不要 key、约 16000 个指标、缓存 30 天。数值自动换算成万亿/亿/万，**出处一路带到屏幕上**。也支持 `from_csv()` 粘表格。原则：**绝不编数字** |

### 4.3 出镜与人脸

| 功能 | 状态 | 怎么实现的 |
|---|---|---|
| **自己的素材库** | ✅ | [`me.py`](../vidforge/me.py) — `~/.vidforge/me/`，标签从文件名来，按「用得最少」挑，所以同一个镜头不会连着几期都出现 |
| **口型同步** | ⚠️ | [`lipsync.py`](../vidforge/lipsync.py) — `synclabs`（要 key，素材会过第三方主机）或 `musetalk`（本地命令，要 GPU） |
| **数字主持人** | 🟡 | [`avatar/`](../vidforge/avatar/) — `host` 是 Remotion 画的卡通形象，嘴型由音频包络驱动，**本地免费且不需要声明**（它明显是个卡通）；`heygen` 是写实数字人，⚠ 未实测，用了会自动打合成内容标 |
| **人脸遮盖 / 换头** | ✅ | [`video/heads.py`](../vidforge/video/heads.py) — OpenCV YuNet 检测（权重自动下到 `~/.vidforge/models/`）→ 跟踪平滑 → 用静态图**或一段动态视频**（椭圆遮罩、逐帧锁定）盖住每张脸 |
| **照片变会说话的头** | 🟡 | [`video/face.py`](../vidforge/video/face.py) — `motion`（音频包络驱动的木偶，不要 GPU）或 `cmd`（`PHOTO_TALK_CMD` → SadTalker/EchoMimic/Hallo，要 GPU） |
| **叠加层 / 画中画 / 分屏** | ✅ | `Overlay` — 滑入/淡入、描边（可选颜色）、`shape` 方/圆角/圆（Pillow 抗锯齿遮罩 + alphamerge）、`height` 固定框裁切铺满（分屏）。`PipEditor.tsx` 在画面上拖动/缩放、吸附，七种一键布局 |
| **智能剪口播** | ✅ | [`video/jumpcut.py`](../vidforge/video/jumpcut.py) — `silencedetect` 找停顿（默认 -38dB、≥0.45s 才剪、两边留 0.12s），trim+concat 画面声音同一组切点。**剪「嗯」「呃」**（`fillers=True`，要 faster-whisper）：Whisper 认出哪些是语气词（提示词里带着「嗯、呃」它才不把它们删掉），切点按电平找到的那一小段声音定，那段声音里只有语气词才剪，贴着别的字的不剪只计数；那个/就是/然后不剪 |
| **视频美化（后期）** | ✅ | `VideoBeautify.tsx` — 已有视频按原速过一遍实时特效并重录，`/api/fx/save` 收原始字节转 h264 |
| **竖屏主题模板** | ✅ | [`theme.py`](../vidforge/theme.py) — 1080×1920、小窗 24% 宽 3:4 圆角在上方、字幕抬高 24% 避开平台底部、系列角标（`finalize` 叠加）、6 套明亮配色 |

---

<a id="q5"></a>
## 5. 第 4 步 渲染

| 功能 | 状态 | 怎么实现的 |
|---|---|---|
| **分段缓存** | ✅ | `pipeline._segment_key()` — 把段落定义、音频文件的**大小+mtime**、渲染设置一起哈希。改一段只重渲那一段。实测重建 0.6s |
| **按段叠字幕（dress）** | ✅ | `pipeline._stage_dress` + `render.dress_segment` — 字幕（每段从 0 写 .ass/.srt）、系列角标、开场大字、进度条按段叠加，缓存为 `clips/<seg>.<key>.d<k>.mp4`（`_dress_key`）；`finalize(dressed=True)` 画面直接拷贝、只混音。`merged.mp4`（没烧字幕）仍由未叠加的段拼成，给竖版切片用。实测 M1、128 秒视频：无改动重渲 4s（以前约 19s），全部重叠 23s。单个硬件编码器，并发 1/2/4 一样快 |
| **两遍响度** | ✅ | `voicefx.loudnorm` — 先 `print_format=json` 量整段，再 `linear=true` 固定增益；量不出（静音）回到单遍动态。`render.AUDIO_FORMAT` 在分段缓存键里，旧缓存自动重做一次 |
| **按录音识别文字** | ✅ | `align.recognize` + `/api/narration/recognize`（`apply` 写回脚本并后台重新对齐）+ `RecognizeDialog`。字幕仍然说脚本说的——只是让脚本变成实际说的，且先给人看（逐字 diff、可改）。对齐命中率存进 sidecar（`hits/total`，`narration.match`），项目视图 `resolved[seg].align`，低于 `align.LOW_MATCH`(0.8) 时渲染日志和第 4 步提醒。Whisper 只用风格提示（`style_prompt`）：用脚本当提示词时，照稿念的一段从 81% 掉到 3%（Whisper 把提示当成已说过的话，跳过音频）。`align.VERSION` 在对齐缓存键里 |
| **硬编自动选择** | ✅ | `render.pick_encoder()` — nvenc / qsv / amf / videotoolbox / libx264 按序探测。实测 30 分钟 40 段约 2.7–4.5 分钟渲完 |
| **并行段渲染** | ✅ | `_stage_render` 多 worker |
| **字幕** | ✅ | [`subtitles.py`](../vidforge/subtitles.py) — SRT + ASS。`write_ass()` 支持 `none`/`keywords`/`karaoke`/`word`（逐词：正在说的词变色放大 112%，竖屏模板默认）四种高亮；**数字和关键词自动高亮**；双语字幕；可选烧入。⚠ 实测烧字幕从 45s 涨到 89s，**瓶颈是字幕滤镜本身，不是编码器** |
| **AI 标题 / 简介 / 话题** | ✅ | [`platforms.py`](../vidforge/platforms.py) `suggest_text()` — 本地模型（Ollama）从旁白写 5 个标题、一段简介、5 个话题，按项目语言写。标题里出现旁白没有的数字（阿拉伯或中文数字都查，`cn_number()`）就整条去掉；话题太长不截断而是不要。发布页点一下才用，不会自动写进项目。`/api/platforms/suggest` |
| **各平台封面** | ✅ | [`platforms.py`](../vidforge/platforms.py) `make_covers()` — 多平台导出时每个平台再出封面：竖屏 9:16，抖音/快手/视频号再加一张 3:4（主页网格）；横屏 1280×720。用构建留下的 `cover_src.jpg`（封面那张图），竖封面上的标题自动折成两三行（`thumbnail.wrap_for`）；中文改用粗体 |
| **进度条** | ✅ | [`render.py`](../vidforge/render.py) `finalize` — `progress_bar: true`，高 0.6% 的强调色细条随时间从左长到右；横屏在底边，竖屏在顶边（抖音/快手自己的进度条在底部）。和角标、开场大字一样在最后一遍叠加 |
| **转场音效** | ✅ | [`sfx.py`](../vidforge/sfx.py) — `transition_sfx: whoosh|tick`，每两段交接处一声，ffmpeg 用噪声/正弦现合成（没有授权问题，也不会被平台的音频指纹匹配到），峰值约 -20 dBFS，压在 -16 LUFS 的旁白下面；在 BGM 闪避之后混入，不会把音乐压下去 |
| **口播推近** | ✅ | [`render.py`](../vidforge/render.py) `punch_windows()` — `punch_in: true` 时，真人镜头（录制棚 takes/、我的镜头）在旁白的句间停顿处全景/近景（115%，裁切点略偏上，脸在上半部）交替；短于 1.5 秒的不切，没有句读的长镜头每 4 秒换一次。只换画面不动声音 |
| **参考视频** | ✅ | [`references.py`](../vidforge/references.py) — 左侧栏「参考」：YouTube（搜索页解析）和 B站（官方搜索接口，按播放量）按主题搜，YouTube/TikTok 等用 yt-dlp 下（480p），B站用 html5 播放地址下（DASH 在海外被 567 拦）；抖音/快手/小红书搜不了，粘贴链接试、不行就导入本地文件。存 `~/.vidforge/references/<id>/`，只在本机看，不进成片 |
| **框架（从参考视频提取）** | ✅ | [`frameworks.py`](../vidforge/frameworks.py) — Whisper 转写 + ffmpeg 场景切点 + 本地模型分块（没有模型时按时间粗分并标明），节奏数字（字/分钟、平均镜头秒数、前 15 秒切几次、开头有没有问题/数字）；第一块超过 20 秒切出 15 秒钩子。存成结构模板 `~/.vidforge/structures/ref-<id>.json`，出现在「脚本 → 段落骨架」（`structure.user_templates()`），可直接套用、写进 AI 提示词 |
| **片头片尾与音乐（界面）** | ✅ | 渲染页「片头、片尾和音乐」：频道品牌包（`brand.py`，`~/.vidforge/brand/brand.json`，所有视频共用）的频道名/slogan/片头片尾时长/订阅语/下期预告，片头音效（合成或上传）、片尾音乐上传、预览；每条视频可单独关片头/片尾（`project.brand.intro/outro`）；背景音乐上传到 `assets/music/`、音量/闪避/淡出。`/api/brand*`、`/api/audio/upload`。项目有配色时片头片尾跟配色走（`brand.for_project`），竖屏字号放大 |
| **配图可选 / 小窗⇄全屏** | ✅ | [`pipeline.py`](../vidforge/pipeline.py) `fill_bare_segments()` — 没画面的段落：自己录的视频旁白→全屏；只有小窗→小窗放大全屏；都没有→配色纯色底写章节名（`render.plain_page`），日志逐段说明，整片和单段预览都适用。`/api/segment/swap` 把视频片段改成小窗（`theme.presenter_overlay`）或把小窗改回全屏，第 3 步的按钮 |
| **下一期（系列）** | ✅ | [`project.py`](../vidforge/project.py) `next_episode()` + `/api/new {next_episode}` — 沿用画幅、配色、字幕、品牌、BGM（文件一起复制）、音效等 `SERIES_KEYS`，角标里的数字加一（保留补零），脚本、开场大字、上传文案清空。项目卡片里的「下一期」按钮 |
| **画幅与风格** | ✅ | [`theme.py`](../vidforge/theme.py) `FRAMES`（16:9 / 9:16 / 3:4 / 1:1）+ 6 套配色，任何画幅都能套；竖的画幅才用手机版式（字幕上移、每行 12 字）。真人小窗按画幅自己的比例算（`window_box`：竖 3:4、横 4:3、圆形正方），四个角可选，下方的角让开字幕（`window_place`）。界面：顶栏画幅标签、渲染页卡片、新建项目时选画幅。多平台导出加了小红书 3:4 和 B站 |
| **开场大字** | ✅ | [`hook.py`](../vidforge/hook.py) — `project.json` 的 `hook.text` 在旁白开始时压在画面中上部 `hook.seconds`（默认 3，1–6）秒，淡入淡出。PIL 画成图片在 `render.finalize` 里叠加（和系列角标一样），不需要 libass 或 Remotion；叠加而不是插标题卡，第一句旁白不往后推。文字只用用户写的 |
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
| **多平台导出** | ✅ | [`platforms.py`](../vidforge/platforms.py) — 抖音/快手/视频号/TikTok/头条·西瓜/YouTube/Shorts 各自画幅码率，横转竖复用竖版切片；每个平台一份可粘贴的标题/简介/话题/AI 声明；时长只警告不拦截 |
| **YouTube 上传** | 🟡 | [`upload/youtube.py`](../vidforge/upload/youtube.py) — 视频 + 封面 + 字幕 + 章节。要 `client_secret.json`（放 `~/.vidforge/`） |
| **AI 使用声明** | ✅ | `project.Disclosure` — 同时驱动 YouTube 的「改动或合成内容」标记和中国 2025-09-01 标识要求的简介文案。`ai_voice` 默认 `True`；**全部段落用自己的录音后，界面会提示取消这个勾选** |
| **多语言成片** | ✅ | `build_<lang>/` 各自一套，`variants` 指定各语言的声音 |

---

<a id="q7"></a>
## 7. 横向

| 功能 | 状态 | 怎么实现的 |
|---|---|---|
| **Web 界面** | ✅ | 后端 [`ui/__init__.py`](../vidforge/ui/__init__.py) 是 **stdlib `ThreadingHTTPServer`**（不是 Flask/FastAPI——少一个依赖），端口 8765。前端 `ui/react/`（Vite + MUI），后端在 `/` 直接服务 `dist/`，首次启动自动构建一次；没装 Node 时 `/` 是一页说明。旧的 vanilla 界面（`ui/static/`、`/old`）2026-11-17 已删除，它独有的语言版本切换搬到了 React 顶栏 |
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
vidforge videofx list|try                        # 画面预设（柔肤/补光/锐利）
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
| **声音克隆（录一次，以后只打字）** | 还没做。挡路的不是代码：**没有录音样本**，而且这台机器只有 Intel 核显（无 CUDA）。见 [audio-voice-qa.md 第 8 节](audio-voice-qa.md#q8) |
| **实时逼真换脸 / 整件换衣服** | 没做。能做到不假的开源方案（inswapper/Deep-Live-Cam、IDM-VTON）要 GPU、权重是非商用授权，而且让整条视频变成要标注的合成内容。换背景、衣服头发换色已经做了（见 4.3） |
| **生成背景音乐** | **故意不做**。每条「免费 AI 音乐」路线都有授权陷阱——MusicGen 是 CC-BY-NC，变现频道不能用。所以只做正弦波合成的音频标记 |
| **克隆真人声音** | 不需要了——直接用你本人念的（见 3 节） |
| **BGM 自动踩点** | 计划里，还没做 |
| **地图组件** | 计划里的下一个 P2（世界/中国地图高亮 + 路线动画） |
| **FRED / 国家统计局数据** | 世界银行是年度粒度，月度 CPI、利率这些还接不到 |
| **Docker / 数据库 / 云服务** | 见第 1 节。单机单人、文件驱动是设计，不是妥协 |
