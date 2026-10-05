# 声音与录制：现有功能对照

日期：2026-10-05 · 范围：旁白声音来源、音质处理、字幕对齐、录制与配乐
说明：每一条结论都标了代码出处，可以直接跳过去看。声音「设计 vs 克隆」的技术路线全览见
[custom-voice-guide.md](custom-voice-guide.md)，本文只回答「**现在的 vidforge 有没有**」。

## 目录

1. [录视频 → 提取音频 → 用我自己的声音当旁白](#q1)
2. [声音美化（浑厚、磁性）](#q2)
3. [字幕与声音对齐](#q3)
4. [还缺什么：录制、降噪、配乐、片头片尾](#q4)
5. [一张总表](#q5)
6. [建议：补一条「自己的声音」链路](#q6)
7. [✅ 2026-10-05 实现记录](#q7)

---

<a id="q1"></a>
## 1. 录视频 → 提取音频 → 用我自己的声音当旁白

> ⚠️ **2026-10-05 已实现，此前回答作废。**下面保留的是当时的现状调查，最终结论紧跟在「✅ 现在」里。实现细节见 [第 7 节](#q7)。

**✅ 现在：可以了。** `Segment.narration` 指向一个录音文件就不走 TTS，录音会和这一段的脚本
强制对齐（见第 3 节）。支持音频文件，也支持直接丢一个视频进去自动抽音频；首尾静音自动掐掉。

```powershell
vidforge narration my-video attach --segment seg1 --file take.m4a
vidforge narration my-video list
```

界面在「2 配音」步骤和「声音」页：🎙 用我自己的声音——按段落录（浏览器直接录，或选手机录好的文件）。

---

**以下是 2026-10-05 之前的现状（已过时，保留作为背景）：**

**结论：没有。整条链路都不存在。**

依据：

- TTS 的 provider 契约写死了方向是「文字 → 音频」：
  `synthesize(text, voice, out_path) -> list[Word]`（[`tts/__init__.py:34`](../vidforge/tts/__init__.py#L35)）。
  三个实现 edge / elevenlabs / voxcpm 全是这个形状。
- `Segment` 没有「用这个音频文件当旁白」的字段。它只有 `voice: str | None`，
  那是**TTS 音色名**，不是文件（[`project.py:109`](../vidforge/project.py#L109)）。
- 没有任何地方从视频里抽音频。`ffmpeg.py` 只有 `find_binary / run / duration / video_size /
  filter_path / print_versions`，没有 extract-audio 这类帮手。

**容易混淆的三样东西**，都不是「你的声音」：

| 有的东西 | 实际是什么 |
|---|---|
| `me.py` 自己的出镜素材库 | 你**自己的脸**；说话的镜头由 `lipsync.py` 对上 **TTS 的声音** |
| `tts/voxcpm.py` | 按**文字描述**设计一个世界上不存在的新音色，不读参考音频 |
| `tts/voice_design.py` | ElevenLabs Voice Design，文件头第 3 行明写 "No real person is cloned" |

所以之前存下来的 `Simon1` 是一个**设计出来的音色**，不是你的声音。
现在的成片形态是「**我的脸 + 合成的声音**」。

---

<a id="q2"></a>
## 2. 声音美化（浑厚、磁性）

> ⚠️ **2026-10-05 已实现，此前回答作废。**下面保留的是当时的现状调查，最终结论紧跟在「✅ 现在」里。实现细节见 [第 7 节](#q7)。

**✅ 现在：有 5 个预设。** `voice_fx` 选一个，自己录的和合成的声音都会过这一层：

| id | 名字 | 做什么 |
|---|---|---|
| `none` | 不处理 | 只做响度统一 |
| `clean` | 只清理 | 去低频轰鸣 + 降底噪，不改音色 |
| `warm` | **浑厚解说** | 120 Hz 加身体感、300 Hz 去箱音、5 kHz 压齿音 + 压缩 |
| `clear` | 清亮口播 | 提亮 3 kHz 的咬字 |
| `phone` | 手机录音补救 | 降噪更狠、压缩更重 |

不是机器学习，就是 `highpass` / `afftdn` / `equalizer` / `acompressor` 几条滤镜；
`loudnorm` 永远排在最后（预设管音色，loudnorm 管电平）。
界面里可以**试听对比**（同一句话渲染两遍，原声和处理后并排放）。

每个预设都**不改变时长**——这是硬约束而不是巧合：字幕的逐词时间是按这段音频量出来的，
一个会拉伸时长的滤镜（`atempo`、`rubberband`）会把整条字幕轨悄悄推偏。这一条写成了测试。

---

**以下是 2026-10-05 之前的现状（已过时，保留作为背景）：**

**结论：基本没有。只有响度统一，没有音色处理。**

唯一的音频处理是一条 `loudnorm`：

```
loudnorm=I=-16:TP=-1.5:LRA=11
```

出处 [`render.py:354`](../vidforge/render.py#L354)，开关是 `normalize_audio`
（[`project.py:241`](../vidforge/project.py#L241)，默认开）。它的作用是**让不同段落、不同
provider 的音量一致**，不是让声音更好听。

全仓库搜过 `equalizer / acompressor / compand / deesser / afftdn / arnndn / anlmdn / speechnorm`
——除了上面那条 loudnorm，一条都没有。所以没有 EQ、没有压缩器、没有齿音处理、没有降噪。

**现在唯一能影响「浑厚磁性」的入口是在设计音色时用文字描述**，
`voice_design.py` 的示例 literally 就是这个需求：

> "deep, warm, magnetic male narrator in his forties, unhurried, slight British colour"

也就是说：音色是**选**出来的，不是**调**出来的。选定之后没有任何后续美化手段。

---

<a id="q3"></a>
## 3. 字幕与声音对齐

> ⚠️ **2026-10-05 部分修正。**「只对 TTS 有效」已经不成立了——现在任意音频都能对齐。
> 下面的 provider 对照表仍然准确。

**✅ 现在：任意录音都能对齐**（`align.py`，基于 faster-whisper）。关键设计是**转写只用来定位时间，
不用来决定字幕内容**：字幕永远显示脚本原文，Whisper 只回答「这个词在第几秒」。

拿 edge-tts 的真实 WordBoundary 当标准答案量出来的误差：

| | 平均 | 中位数 | p90 |
|---|---|---|---|
| 中文 `align()` | **0.068s** | 0.050s | 0.125s |
| 中文 平均摊（旧 fallback） | 0.301s | 0.251s | 0.629s |
| 英文 `align()` | **0.066s** | 0.050s | 0.171s |
| 英文 平均摊 | 0.432s | 0.512s | 0.771s |

比平均摊好 2.8–6.5 倍。没装 faster-whisper 时自动退回平均摊，构建不会失败。

---

**以下是 2026-10-05 之前的现状（provider 表仍然有效）：**

**结论：有，而且是逐词级的——但只对 TTS 自己生成的音频有效，且分 provider。**

| provider | 时间从哪来 | 精度 |
|---|---|---|
| edge-tts（默认） | 流里的真实 `WordBoundary` 事件，带 `offset` / `duration`（[`tts/edge.py:44`](../vidforge/tts/edge.py#L44)） | 帧级准确 |
| ElevenLabs | `/v1/text-to-speech/{id}/with-timestamps` | 帧级准确 |
| VoxCPM | **没有** forced alignment。按量出来的真实总长把词平均摊开（[`tts/voxcpm.py:165`](../vidforge/tts/voxcpm.py#L165) 的注释写明「正常语速下接近，但不会帧级准确」） | 近似 |

这些 `Word` 时间往下驱动了相当多东西：`final.srt`、ASS 的逐词关键词高亮、章节时间点、
以及竖版切片按切点重新计时。

**⚠ 但要分清**：这是「**TTS 自己报告它念到哪了**」，不是「**对任意一段音频做对齐**」。
全仓库没有 whisper，也没有任何 forced aligner。

所以第 1 条和第 3 条是**同一个缺口的两面**：一旦用自己录的声音，字幕对齐同时也就没有了。

---

<a id="q4"></a>
## 4. 还缺什么：录制、降噪、配乐、片头片尾

### 4.1 干净背景的录像/录音功能 —— 🟡 录音有了，画面没有

**✅ 录音**：「2 配音」步骤里每个段落一个录音按钮（`MediaRecorder`，开了浏览器自带的
`echoCancellation` / `noiseSuppression` / `autoGainControl`）。**按段录，不是整条录**——
一个段落就是一个意思、两到四句，念错只重录这一段。

**❌ 画面**：抠像、背景虚化、换背景仍然没有。录像还是在 vidforge 之外。

~~### 4.1（旧）干净背景的录像/录音功能 —— ❌ 没有~~

界面里搜不到任何 `getUserMedia` / `MediaRecorder` / `navigator.mediaDevices`。
录制完全在 vidforge 之外，你得自己录好文件再丢进 `~/.vidforge/me/`。

顺带一提：「背景干净」目前也没有工具支持——没有抠像（chromakey）、没有背景虚化、没有背景替换。

### 4.2 手机录音降噪 —— ✅ 有了

`afftdn=nr=10:nf=-30` + `highpass`，在 `clean` / `warm` / `clear` 三个预设里；
嘈杂环境用 `phone`（`nr=20` + 更重的压缩 + 400 Hz 下陷，手机麦克风就堆在那个频段）。
详见第 2 节。

### 4.3 配背景音乐 —— ✅ 有，而且做得不错

`Bgm(file, volume_db=-18.0, fade_out=3.0, duck)`（[`project.py:195`](../vidforge/project.py#L195)）。
混音在 [`render.py:466`](../vidforge/render.py#L466)：

- 音乐自动循环（`-stream_loop -1`）铺满全片
- 结尾 3 秒淡出
- `duck=true` 时用 `sidechaincompress` 做**人声压低音乐**：说话时音乐降约 10 dB，停了 0.4 秒恢复

这是整个音频链路里唯一做得比较完整的部分。**但音乐文件要你自己提供**（授权自己负责）。

### 4.4 生成与视频相关的背景音乐 —— ❌ 没有，而且是故意不做

[`brand.py:18`](../vidforge/brand.py#L18) 记了原因：

> 每条「免费 AI 音乐」路线都有授权陷阱——MusicGen 是 **CC-BY-NC**，变现频道不能用。

替代做法是 `vidforge brand sting`：用纯正弦波**合成**一个 1.4 秒的音频标记，
理由很直接——**没人拥有一条正弦波，所以没有东西需要清权**。

这个取舍在「变现」这个前提下是对的。如果以后要做真正的配乐，得先解决授权，不是先解决技术。

### 4.5 logo / slogan / 片头 / 片尾自动加入 —— ✅ 有，默认就开

`Brand` 的 `intro: bool = True` / `outro: bool = True`（[`brand.py`](../vidforge/brand.py) 的
`class Brand`），构建时由 `pipeline._with_brand()`
（[`pipeline.py:453`](../vidforge/pipeline.py#L453)）自动在前面接 1.2 秒片头、后面接 6 秒片尾。

一套 kit（`~/.vidforge/brand.json`）同时决定片头、片尾和**每张图表的配色**，所以频道看起来是一个频道。

实现上有个细节值得记住：**片头必须先渲染**，因为它的长度决定旁白从第几秒开始——
之前就是漏了这一步导致字幕整体偏移（视频 8.34 秒 vs 时间轴 7.17 秒）。

---

<a id="q5"></a>
## 5. 一张总表

| 功能 | 状态 | 出处 / 说明 |
|---|---|---|
| 从视频提取音频 | ✅ | `narration.extract()`；`ffmpeg.pcm()` 给 Whisper 解码 |
| 用自己录的声音当旁白 | ✅ | `Segment.narration`，走 `narration.prepare()` 而不是 TTS |
| 自己的脸（出镜） | ✅ | `me.py` + `lipsync.py`，但对的是 TTS 的声音 |
| 设计一个独特音色 | ✅ | VoxCPM（本地开源）/ ElevenLabs Voice Design |
| 克隆真人声音 | ❌ | 不需要了——直接用你本人念的 |
| 响度统一 | ✅ | `loudnorm I=-16`，默认开 |
| EQ / 压缩 / 齿音 / 浑厚磁性 | ✅ | `voice_fx` 5 个预设，可试听对比 |
| 降噪 | ✅ | `afftdn` + `highpass`，`phone` 预设更狠 |
| 字幕逐词对齐（TTS） | ✅ | edge / ElevenLabs 帧级；VoxCPM 近似 |
| 对任意音频做对齐 | ✅ | `align.py`（faster-whisper，可选依赖），中文平均误差 0.068s |
| 录音 | ✅ | 「2 配音」里每段一个录音按钮 |
| 录像 | ❌ | 仍在 vidforge 之外 |
| 抠像 / 背景虚化 / 换背景 | ❌ | — |
| 背景音乐（自备文件） | ✅ | 循环 + 淡出 + 人声压低音乐 |
| 生成背景音乐 | ❌ | 故意不做：授权陷阱 |
| 音频标记（sting） | ✅ | 正弦波合成，无需清权 |
| logo / slogan / 片头 / 片尾 | ✅ | `Brand.intro/outro` 默认开，构建时自动拼 |

---

<a id="q6"></a>
## 6. 建议：补一条「自己的声音」链路

> ✅ **2026-10-05：第 1、2、3、4 步都做完了。** 实现见 [第 7 节](#q7)。下面是当时的计划。

上面的 ❌ 不是零散的，它们是**同一条链路**的各个环节。现在是「我的脸 + 合成的声音」，
缺的是把声音也变成自己的：

```
录（手机/麦克风）→ 提取音频 → 降噪 → 音色美化 → 和文字对齐 → 当旁白用
      4.1            1          4.2       2          3           1
```

按「投入 / 产出」排，建议的顺序：

**第一步：让 `Segment` 能直接吃一个音频文件。**
加一个 `narration: Path | None` 字段，有它就跳过 TTS。这一步解锁了整条链路的出口，
而且技术上最简单——`synthesize_cached` 的缓存逻辑可以照用。

**第二步：用 faster-whisper 做对齐。**
本地跑、免费、中文够用。读音频 + 已有的脚本文字 → 逐词时间，填进现成的 `Word` 结构，
下游的字幕/高亮/章节/竖版切片**一行都不用改**（它们只认 `Word`）。
这一步也顺带让 VoxCPM 从「近似」升到「准确」。

**第三步：一条 ffmpeg 人声链。**
不需要机器学习，纯滤镜就能明显改善手机录音：

```
highpass=f=80            去空调/交通的低频轰鸣
afftdn=nr=12             降底噪
acompressor              压缩，让音量更稳、听上去更「厚」
equalizer 低频 +2~3dB    浑厚
equalizer 高频轻微衰减    去毛刺
loudnorm                 已有，放最后
```

做成几个预设（「浑厚解说」「清亮口播」），而不是暴露一堆参数。
这是**性价比最高的一步**——几条滤镜就能解决第 2、4.2 两问。

**第四步（可选）：浏览器里直接录。**
`MediaRecorder` 录完 POST 到后端存进 `~/.vidforge/me/`。
省掉「手机录 → 传电脑 → 找文件」这一圈，但不解锁任何新能力，所以排最后。

**不建议做的：生成背景音乐。** 授权风险 > 收益，`brand sting` 那条正弦波路线已经够用。

### 顺带一个合规上的好处

`Disclosure.ai_voice` 默认是 `True`（[`project.py:157`](../vidforge/project.py#L157)），
于是每条视频的简介都会自动带上一句：

> 本视频包含人工智能生成内容：配音由 AI 合成。

这是为了满足中国 2025-09-01 的 AI 内容标识要求。**如果旁白换成你自己录的声音，
这个标志就可以置为 `false`**，那行字也就不必出现了——配合 `me.py` 的自己出镜，
整条视频可以从「AI 生成内容」回到「真人创作」。

这正好接上项目一直的那条设计原则：**自己的声音 / 自己的素材 / 原创图表才是答案，
而不是规避标识**。所以第一步「让 `Segment` 能吃音频文件」不只是省事，
它是现在离「完全不用打 AI 标」最近的一块拼图。

---

<a id="q7"></a>
## 7. ✅ 2026-10-05 实现记录

第 6 节的四步全部做完。新增三个模块：

| 模块 | 职责 |
|---|---|
| [`vidforge/align.py`](../vidforge/align.py) | 把录音和脚本强制对齐，返回和 TTS 一样的 `list[Word]` |
| [`vidforge/narration.py`](../vidforge/narration.py) | 非 TTS 的旁白：解码、掐静音、对齐、缓存 |
| [`vidforge/voicefx.py`](../vidforge/voicefx.py) | 5 个人声预设（只有滤镜，没有模型） |

### 7.1 为什么转写不能当字幕

转写在**最要紧的地方**是错的：人名听错、标点全丢、脚本写「2025」它写「二零二五」。
所以职责分开——**脚本决定说什么，Whisper 只回答什么时候**：

```
script tokens  ──┐
                 ├─ difflib.SequenceMatcher 在归一化 key 上对齐 ─→ 命中的词直接取时间
whisper tokens ──┘                                            ─→ 没命中的按相邻词插值
```

没命中的词借用两侧的时间，所以一个听错的人名只影响它自己，不会把整条轨道带歪。

### 7.2 一块块都是量出来的，不是猜的

拿 edge-tts 的 WordBoundary 当标准答案（见第 3 节的表）：中文平均误差 **0.068s**，
比平均摊好 4.4 倍。另外测了一件事：把汉字数字归一化到阿拉伯数字（`二零二一` → `2021`）后，
中文平均误差从 0.109s 降到 **0.068s**，p90 从 0.380s 降到 **0.125s**（3 倍）。
对一个满篇是数字的频道，这一条值三行代码。注意只映射纯数字，不动 `百`/`十`——
那两个要靠解析而不是替换（`六百八十万` 不是字符替换能处理的）。

### 7.3 实现里撞到的三个问题

1. **`av` 19 和 faster-whisper 1.2 不兼容**：`av.open()` 删掉了 `metadata_errors` 参数，
   faster-whisper 还在传，直接 `TypeError`。没有去钉版本，而是加了
   `ffmpeg.pcm()` 自己解码成 16 kHz 单声道 float 数组喂进去——vidforge 本来就依赖 ffmpeg，
   这样彻底不碰 PyAV，以后这对版本怎么变都不影响。
2. **`_interpolate` 会输出倒退的时间轴**（被测试抓到）：Whisper 的时间戳是按转写 segment 给的，
   两个 segment 交界处偶尔重叠，而我原来无条件信任锚点。现在最后加一道单调性钳制——
   **晚一点可以忍，乱序不行**。
3. **`afftdn` 对数字静音会出问题**，和 `loudnorm` 一样。所以两者共用同一个 `audio_is_silent()` 判断。

### 7.4 缓存

Whisper 一次录音只跑一遍，不是一次构建跑一遍。sidecar `.json` 的 key 覆盖
**录音文件的大小+mtime、脚本文字、Whisper 模型名、是否掐静音**——重录或改台词会重新对齐，
别的都不会。实测：首次构建含对齐 10.1s，重建 **0.6s**。

音色预设故意**不**进这个 key：它在 `render.py` 和 `loudnorm` 同一道做，
所以换预设不会让 Whisper 重跑一遍。换预设只会让段落片段缓存失效（`voice_fx` 进了
`_segment_key`），那是必须的。

### 7.5 合规

`Disclosure.ai_voice` 本来默认 `True`，会在简介里自动写「配音由 AI 合成」。
全部段落都用自己的录音之后，「5 发布」那一步会提示这个勾选该取消，一键关掉。
配合 `me.py` 的自己出镜，整条视频可以从「AI 生成内容」回到真人创作——
这正是项目一直的那条原则：**自己的声音 / 自己的素材 / 原创图表才是答案，而不是规避标识**。

### 7.6 还是没做的

- **生成背景音乐**：仍然故意不做（授权陷阱，见 4.4）。
- **抠像 / 背景虚化 / 换背景**：没做。
- **录像**：只录音，不录像。
- **faster-whisper 是可选依赖**：没装的话字幕退回平均摊，界面会提示，构建不会失败。
  装：`pip install faster-whisper`（模型下到 `~/.vidforge/models/whisper/`，CPU 够用，
  默认 `small`，`VIDFORGE_WHISPER_MODEL` 可改）。
