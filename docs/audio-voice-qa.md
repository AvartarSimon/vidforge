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

---

<a id="q1"></a>
## 1. 录视频 → 提取音频 → 用我自己的声音当旁白

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

### 4.1 干净背景的录像/录音功能 —— ❌ 没有

界面里搜不到任何 `getUserMedia` / `MediaRecorder` / `navigator.mediaDevices`。
录制完全在 vidforge 之外，你得自己录好文件再丢进 `~/.vidforge/me/`。

顺带一提：「背景干净」目前也没有工具支持——没有抠像（chromakey）、没有背景虚化、没有背景替换。

### 4.2 手机录音降噪 —— ❌ 没有

没有 `afftdn`（FFT 降噪）、`arnndn`（RNN 降噪）、`anlmdn`，也没有高通滤波去低频轰鸣。

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
| 从视频提取音频 | ❌ | `ffmpeg.py` 没有这个帮手 |
| 用自己录的声音当旁白 | ❌ | provider 契约是 `text -> audio`；`Segment` 无音频字段 |
| 自己的脸（出镜） | ✅ | `me.py` + `lipsync.py`，但对的是 TTS 的声音 |
| 设计一个独特音色 | ✅ | VoxCPM（本地开源）/ ElevenLabs Voice Design |
| 克隆真人声音 | ❌ | 两个引擎都是「设计」，不读参考音频 |
| 响度统一 | ✅ | `loudnorm I=-16`，默认开 |
| EQ / 压缩 / 齿音 / 浑厚磁性 | ❌ | 全仓库只有 loudnorm |
| 降噪 | ❌ | 无 afftdn / arnndn / anlmdn |
| 字幕逐词对齐（TTS） | ✅ | edge / ElevenLabs 帧级；VoxCPM 近似 |
| 对任意音频做对齐 | ❌ | 无 whisper / forced aligner |
| 录像录音 | ❌ | UI 里没有 `MediaRecorder` |
| 抠像 / 背景虚化 / 换背景 | ❌ | — |
| 背景音乐（自备文件） | ✅ | 循环 + 淡出 + 人声压低音乐 |
| 生成背景音乐 | ❌ | 故意不做：授权陷阱 |
| 音频标记（sting） | ✅ | 正弦波合成，无需清权 |
| logo / slogan / 片头 / 片尾 | ✅ | `Brand.intro/outro` 默认开，构建时自动拼 |

---

<a id="q6"></a>
## 6. 建议：补一条「自己的声音」链路

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
