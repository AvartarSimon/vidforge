# vidforge 路线图 v0.4 → v1.0：方案、思路、任务清单

日期：2026-09-17 · 依据：用户 9-17 的六组需求（脚本 / 配音 / 画面 / 渲染 / 高级功能 ①–⑥）· 当前版本 0.3.0
写法：每项 = **现状 → 目标 → 方案与思路 → 关键决定/风险 → 任务清单 → 验收**。工作量按"一个人 + Claude"估。
标记：✅ 已有 · 🔧 改造 · 🆕 新建 · ⚠️ 风险/法律 · 🧪 需实验

---

## 总览与建议顺序

| 阶段 | 内容 | 为什么先做 | 估时 |
|---|---|---|---|
| **P1 ✅ 9-17** | 1.2 粘贴脚本智能分段 · 2 声音浏览器（口音/性别/方言、逐段换声） · 3.3 多段选取 & 复用 · 4 渲染日志可读化 + 高级参数面板 · **浏览器桥**（用已登录的 Edge 驱动 8 个 AI 聊天站生成脚本；Google 图片 CC 筛选 / 百度图片） | 全是已有能力的补齐 | 完成 |
| **P2 ✅ 9-17** | 1.1 脚本生成（走浏览器桥，非 API） · 5.1 选题助手（YouTube 同类 TOP 20：有 key 走 Data API，无 key 读搜索页 `ytInitialData`；AI 评估走浏览器桥/剪贴板） · 5.2 规范 `docs/best-practices.md` + 页面检查器（钩子、段长、总长、章节、画面变化、自制画面、标题/标签/披露） | 决定"做什么"比"怎么做"更值钱 | 完成；`tools/channel_study.py` 数据核对待做 |
| **P2.5 真实性层** | 段级录音 `audio:`（whisper 对齐字幕） · `presenter` 段（真人录像保留原声 `keep_audio`） · 真人画中画预设（5.3 叠加层 `camera: true`） · ElevenLabs 克隆自己声音 provider · 发布页「AI 使用声明」生成器（YouTube 合成内容开关判断 + 国内平台声明文案） · 开场/封面模板轮换 | 应对 YPP inauthentic content 与国内 AI 标识法规：真人 + 原创 + 合规披露，而不是"避开检查" | 3–4 天 |
| **P3** | 3.2 更多素材源（Openverse、Internet Archive、Google CSE-CC） · 5.3 画中画 | 素材面和表现力 | 4 天 |
| **P4** | 5.6 品牌包（logo/slogan/片头片尾/音乐） | 有了内容后再做门面 | 3 天 + 挑选往返 |
| **P5** | 5.5 专属声音（独立工具 voiceforge） · 5.4 真人出镜美化/数字人 | 依赖 GPU/第三方，独立立项 | 各 1–2 周，🧪 |

---

## 0 平台风险：为什么"避开检查"不是路，"真实性层"才是（2026-09-17 补）

- YouTube 的 inauthentic content 是**人工审核的价值判断**，不是 AI 声音检测器：用 AI 工具本身不违规，批量/模板/复读/无增值才违规。换音频库无效；真人出镜、原创脚本、自制图形、来源列表有效。
- 中国 2025-09-01 的 AI 标识是**法规**：主动声明是义务，vidforge 只做"帮你正确声明"，不做"避开标识"。国内平台无大陆实名不能变现 → 定位为分发与品牌。
- 因此新增 **P2.5 真实性层**（见总览表），并把 A1–A7 写进 `docs/best-practices.md` 由页面检查。收入结构：YouTube 英文长视频广告 + 会员/赞助为主；国内平台引流；学习变体（3.4）可带课程/私域。

## 1 脚本

### 1.1 给标题 + 内容要点 → 自动生成全文并分段 🆕

**现状**：脚本只能手写或粘贴。
**目标**：输入标题、受众、时长、要点/参考资料 → 生成口语化旁白，按"一个意思一段"分好，每段附章节名、画面建议、搜索关键词。

**方案**
- 新建 `vidforge/llm/`：统一接口 `generate(messages, json_schema) -> dict`，三类 provider：
  1. **OpenAI 兼容**（一个实现覆盖 OpenAI、DeepSeek、通义千问 DashScope、Gemini 的 OpenAI 兼容端点、本地 Ollama）——只是 base_url + key 不同；
  2. **Anthropic**（Claude API）；
  3. **剪贴板模式**：没有 API key 时，页面生成一段完整 prompt → 你贴到 ChatGPT/Claude/DeepSeek 网页 → 把回答贴回来 → 解析。**零成本、零配置**，也是默认。
- 输出用固定 JSON schema：`{title, hook, segments:[{label, text, visual_hint, keywords[], est_seconds}], description, tags}`；解析失败时回退到 1.2 的文本分段。
- Prompt 模板放在 `vidforge/llm/prompts/*.md`（中英各一份），内容包含：开场 30 秒钩子、每段 2–4 句、口语、标点齐全、数字读法、章节名、每段给 2 个英文搜索词。这是 5.2 研究结论的落点。

**关键决定/风险**
- ⚠️ ChatGPT Plus / Claude Pro 的**网页订阅不能当 API 用**；API 另计费（DeepSeek 最便宜 ~¥1/百万 token，一篇 30 分钟脚本 < ¥0.1；Claude/GPT 约 $0.05–0.3/篇）。所以剪贴板模式必须是一等公民。
- 事实性：历史内容 LLM 会编。prompt 要求"每个具体数字/日期标注来源或标 [核实]"，页面把 `[核实]` 高亮。

**任务清单**
- [ ] `llm/base.py` 接口 + `openai_compat.py` + `anthropic.py` + `clipboard.py`
- [ ] `.env` 增加 `OPENAI_API_KEY / OPENAI_BASE_URL / DEEPSEEK_API_KEY / DASHSCOPE_API_KEY / GEMINI_API_KEY / ANTHROPIC_API_KEY`；`doctor` 显示
- [ ] prompt 模板（zh/en）+ JSON schema + 解析器（含容错：markdown 代码块、多余文字）
- [ ] 第 1 步页面：新增「✨ 生成脚本」面板：标题 / 受众 / 目标时长 / 要点或参考文本 / 语气 → 生成 → 预览 → 「采用」写入 segments
- [ ] 剪贴板模式 UI：「复制提示词」→「粘贴回答」
- [ ] 单测：schema 解析容错、`[核实]` 标注；e2e 用 clipboard 模式跑通
- **验收**：只给标题"没有夏天的一年"+ 3 个要点，得到 8–12 段可直接配音的脚本。

### 1.2 粘贴他处 AI 生成的文本 → 智能分段 🔧

**现状**：按空行拆段；`# 标题` 识别章节；>50 词按句再切。
**目标**：识别常见结构标记并**尊重已有分段**。

**方案**：解析器识别（优先级从高到低）：Markdown 标题 `#/##`；编号 `1.` `1)` `一、` `第一章/第一节/Part 1/Segment 3:`；`【标题】`；`Scene 1:` `画面：` `旁白：`（剧本体——只取旁白列为 text，画面列进 `visual_hint`）；空行。识别到结构则每个结构块一段，块内不再按句切（除非 > 90 词）；识别不到才回退到现在的逻辑。粘贴前预览拆分结果（表格：段号/章节名/字数/预计秒），可合并/拆开再"采用"。

**任务清单**
- [ ] `vidforge/script_parser.py`（纯函数，可单测）：结构识别 + 剧本体两列分离
- [ ] 第 1 步页面：拆分预览表 + 合并/拆分按钮
- [ ] 单测：6 种格式样本（中英）
- **验收**：把 ChatGPT 输出的带 `## 1. …` 的脚本粘贴 → 段落数与标题数一致。

---

## 2 配音：口音、性别、方言、逐段换声 🔧

**事实（2026-09-17 实测 edge-tts）**
- 英语 45 个声音 / 14 种口音：美 en-US 17、**英伦 en-GB 5**（女 Sonia/Libby/Maisie，男 Ryan/Thomas）、澳 en-AU 2（Natasha/William）、新西兰 en-NZ 2（Molly/Mitchell）、爱尔兰、加拿大、印度、南非、新加坡、香港、菲律宾、尼日利亚、肯尼亚、坦桑尼亚。
- 中文 14 个：普通话 6（女 Xiaoxiao/Xiaoyi，男 Yunxi/Yunjian/Yunxia/Yunyang）、**东北话** liaoning-Xiaobei（女）、**陕西关中话** shaanxi-Xiaoni（女）、**粤语** zh-HK 3（女 HiuGaai/HiuMaan，男 WanLung）、台湾国语 3。
- **没有闽南语**（edge/Azure/ElevenLabs 都没有）。可行路径只有开源克隆（GPT-SoVITS 用闽南语样本训练），质量一般——归入 5.5。
- ElevenLabs：多语言模型口音靠声音库选择（有大量英美澳口音的库音），中文方言弱。

**方案**
- **声音浏览器**：按语言 → 口音/地区 → 性别筛选，每个声音「▶ 3 秒试听」（用当前项目第一句），⭐ 收藏；结果缓存。
- **逐段换声**：`segment.voice` 已支持，补 UI：片段编辑区加"这一段用别的声音"（引用他人的话、对话体）。
- **语速/停顿**：全局语速滑块已有；补"句间停顿 ms"（在文本里按标点插入 SSML `<break>`；edge-tts 支持 SSML 子集）。
- 口音标签用中文写清（"英式·女·沉稳"），来自 edge 的 `VoicePersonalities`。

**任务清单**
- [ ] `/api/voices` 返回 locale/gender/personality 结构化字段；前端浏览器组件（筛选 + 试听 + 收藏到 `~/.vidforge/favorites.json`）
- [ ] 第 2 步：声音选择改为浏览器弹窗；每段行增加"换声"下拉
- [ ] 句间停顿参数 → SSML 注入（edge provider）
- [ ] 文档表：口音 → 推荐声音（历史类：en-GB Ryan/Sonia、en-US Andrew/Ava、中文 Yunxi/Xiaoxiao）
- **验收**：一段用美音男声、一段用英伦女声、一段粤语，渲染一次成功。

---

## 3 画面

### 3.1 每段多张图片、可排序 ✅（v0.2 已有）
片段条支持任意多个片段、←/→ 调序、每张设运镜与停留。**待补**：拖拽排序；缩略图更大的"放大预览"。

### 3.2 素材搜索：推荐 + 多平台 🔧🆕

**现状**：Pexels / Pixabay / Wikimedia Commons，图+视频，按旁白关键词预填。
**目标**：更多来源，包括"网页图片"，但**不引入版权风险**。

**⚠️ 关键决定**：Google 图片 / 百度图片的普通搜索结果**绝大多数有版权**，用了会被 Content ID / 版权投诉，直接威胁变现（见 Q&A Q1）。所以"接 Google/百度"要做成**只返回可商用许可的结果**，而不是原样搬搜索页：
- **Google Custom Search JSON API**：`searchType=image&rights=cc_publicdomain|cc_attribute|cc_sharealike`，免费 100 次/天，需 key + 搜索引擎 ID。可做。
- **百度**：没有官方图片搜索 API，抓取网页违反 ToS 且无许可信息 → **不做**；中文关键词可以先由本地词典/LLM 翻成英文再搜英文源（Commons 支持中文搜索）。
- **Bing 图片 API**：微软 2025-08 已下线。
- 更好的补充：**Openverse**（openverse.org，CC 素材聚合 8 亿+，官方 API，**无需 key**）；**Internet Archive**（公有领域老电影/纪录片/照片，API 无需 key，历史频道的宝库）；**Unsplash**（免费 key，照片质量最高）；视频：Pexels/Pixabay 已有，**Coverr**、Internet Archive 视频。YouTube 上的 CC 视频用 yt-dlp 下载**违反 YouTube ToS** → 不做。
- "推荐"：每段关键词自动搜多个来源 → 合并排序（已有 rank）→ 显示"推荐 6 张"，下面才是各来源 tab。

**任务清单**
- [ ] provider：`openverse.py`（图+音频）、`archive.py`（Internet Archive 图/视频，搜索 `mediatype:(image OR movies)`）、`unsplash.py`、`google_cse.py`（仅 CC rights）
- [ ] 中文关键词 → 英文：优先 LLM（1.1 的 provider），无则内置小词典 + 原文并行搜 Commons
- [ ] 挑选器"推荐"栏：跨来源合并前 6；来源 tab 保留
- [ ] 视频候选显示时长、分辨率、fps；Internet Archive 视频显示年代
- **验收**：搜"Tambora"能同时看到 Commons 版画、Openverse 照片、Archive 老纪录片片段。

### 3.4 学习变体：双语字幕 + 片尾词汇卡（面向国内英语学习者）🆕

**思路**：同一条英文配音视频，多出一个 `en-zh` 变体——字幕两行（上英下中，中文来自已有的 `text_zh`），片尾一张 Remotion「本集词汇」卡：6–10 个词的单词 / 音标 / 释义 / 例句，由浏览器里的 AI 从脚本提取；发头条 / 西瓜 / B 站英语学习区，**不发主频道**（母语观众反感双语字幕）。多账号 = 多主题各自试，**不是**同一内容复制到同平台多个账号（会判重复）。
**任务**：`subtitles.bilingual`（SRT 双行 + 烧录样式）· `outro: vocab` 组件 · 词汇提取 prompt · 变体 `en-zh` 输出到 `build_en-zh/`。估 2 天，排 P3。

### 3.3 视频：去原声 ✅ · 多时间段选取 ✅（P1 已做） · 排序 ✅

**去原声**：**已经做到**——每个视频片段渲染时带 `-an`（丢弃源音轨），成片声音只有旁白 + 可选 BGM。你担心的"讲我们的主题却出现别人的声音"不会发生。（如果某天想保留环境音，做成片段级 `keep_audio: true, volume: -20dB` 再说。）

**多段选取**：同一视频选多段目前要"搜索→选段"重复两次。改为：
- 选段对话框支持**多区间**：「＋ 再加一段」在同一条时间轴上加第二、第三个区间，每个区间一个片段，一次确认全部加入，顺序 = 区间顺序；
- 片段条上任何视频片段有「用同一素材再选一段」，直接打开对话框（不重新下载）；
- 区间条上显示已选总长 vs 旁白需要；
- 排序 ←/→ 已有；补拖拽。

**任务清单**
- [ ] 选段对话框多区间（区间列表 + 各自 in/out 滑块 + 总长提示）
- [ ] 片段"再选一段"入口
- [ ] 拖拽排序（HTML5 DnD，无依赖）
- [ ] e2e：一个视频选两段 + 一张图 → 渲染时长核对
- **验收**：一个 60 s 素材选 3 个区间，按指定顺序出现在段内。

---

## 4 渲染：黑底日志是什么、能调什么 📖🔧

**日志逐行含义**
```
[vidforge] 6 segments · tts edge · voice en-US-AndrewNeural · final · h264_qsv
   段数 · 配音服务 · 声音 · 质量档 · 实际选用的视频编码器（qsv=Intel 显卡硬编；nvenc=NVIDIA；libx264=CPU）
[vidforge] warning: segment 'x' is 2800 characters …      超长段提醒
[vidforge]   tts  hook            24 words    8.64s       这一段配音：词数、时长（缓存命中也会显示）
[vidforge]   asset hook  image <- 'commons:…' -> file.jpg  自动取素材：来源 → 落地文件
[vidforge] [remotion] rendering Timeline (366 frames)     动画渲染（帧数 = 时长 × fps）
[vidforge] rendering 6 segments with 7 worker(s)          并行渲染的线程数（= CPU 核数 / 2）
[vidforge]   clip eruption      11.74s  (2 clips: video,zoom_in)   每段完成：实际时长、片段数与类型
[vidforge] done in 46.4s · 59.4s video · …\final.mp4       总耗时 · 成片时长 · 路径
[vidforge] chapters: 00:00 hook …                          可贴到 YouTube 简介的章节
ERROR: …                                                    失败原因（ffmpeg 报错会带完整命令，贴给我即可定位）
```
**需要关注的只有三类**：`warning`（建议处理）、`ERROR`（必须处理）、`done` 行的耗时（判断机器性能）。

**可调参数（在 `project.json`，其中带 ★ 的已在页面上）**

| 参数 | 作用 | 默认 |
|---|---|---|
| ★ `quality` | draft 快 3 倍 / final 高质量 | final |
| `encoder` | auto / libx264 / h264_nvenc / h264_qsv / h264_amf / h264_videotoolbox | auto |
| `parallel` | 同时渲几段（0 = 核数/2）；机器卡就调小 | 0 |
| `supersample` | 运镜超采样倍数（默认 draft 1 / final 2）；3 更细腻但慢 2 倍 | 按质量 |
| `motion_amount` | 运镜幅度（0.15 = 推近 15%）；0.08 更克制 | 0.15 |
| ★ `transition` | 片段间交叉淡化秒数 | 0 |
| `width/height/fps` | 1920×1080@30；4K 写 3840×2160（渲染时间 ×4） | — |
| ★ `bgm.volume_db / duck / fade_out` | 音乐音量、说话时压低、结尾淡出 | -18 / 开 / 3 |
| ★ `subtitles.burn / style / font / font_size / max_chars` | 烧字幕、样式、字体、字号、每行字数 | 否 / outline / Arial / 22 / 42 |
| ★ `normalize_audio` | 旁白响度归一 -16 LUFS | 开 |
| ★ `auto_title_cards` | 章节标题卡 | 关 |
| 段级 `pause_after` / `fit` / 片段级 `motion` `duration` `in` `out` | 见第 3 步 | — |

**任务清单**
- [ ] 日志中文化 + 颜色分级（info/warn/error），每行悬停有解释
- [ ] 第 4 步「高级参数」折叠面板：encoder / parallel / supersample / motion_amount / 分辨率 / fps，改动即写 `project.json`
- [ ] 渲染结束显示"性能小结"：总耗时、每段平均、编码器、是否建议开硬编
- [ ] `vidforge doctor` 输出可用编码器列表及一次 3 秒基准测速
- **验收**：不看文档能从页面理解每个参数。

---

## 5 高级功能

### 5.1 选题助手：接 LLM 评估主题、给视角、看同类内容 🆕

**方案**：新增**第 0 步「选题」**（可跳过）：
1. 输入主题（或几个候选）；
2. **YouTube Data API `search.list` + `videos.list`**（已有 key 体系，免费配额 10,000 单位/天，一次搜索 100 单位）→ 拉同题材前 20 条：标题、频道、发布时间、播放/点赞/评论、时长、缩略图 → 表格 + "供需比"（近 1 年产量 vs 平均播放）；
3. LLM（1.1 的 provider）读这张表 + 你的定位 → 输出：**值不值得做**（饱和度、长尾潜力）、**3 个差异化视角**、**标题 5 选**、**开场钩子 3 选**、**同类优点提取**（每条视频的标题公式/结构/封面特征）；
4. 选定 → 带入第 1 步生成脚本。
- 头条/B 站/抖音没有开放的搜索 API → 只做 YouTube 数据面；其他平台由 LLM 凭知识补充并标注"未核实"。
- 免费 LLM：DeepSeek/Qwen 便宜；Gemini 有免费额度；本地 Ollama 免费但分析质量一般。

**任务清单**
- [ ] `research/youtube.py`：搜索 + 统计 + 缓存 24h
- [ ] `research/analyze.py`：prompt 模板（评估/视角/标题/钩子/优点提取），JSON 输出
- [ ] 第 0 步页面：主题输入 → 同类表格 → LLM 结论 → 「用这个视角写脚本」
- [ ] 单测 mock；剪贴板模式兜底
- **验收**：输入"没有夏天的一年"，得到同类 TOP 20 表和 3 个可选视角。

### 5.2 爆款研究 → 写成规范 → 反哺流程 🆕📖

**思路**：这是一次研究任务 + 一次产品改动。
1. **研究**（我做）：选 20 个频道（历史/科普英文：Kings and Generals、OverSimplified、Kurzgesagt、Veritasium、Fall of Civilizations、History Matters；中文：李永乐老师、回形针、小Lin说、观视频、罗翔说刑法……）+ 各频道播放最高 5 条 → 用 YouTube API 拉数据，人工/LLM 归纳：标题公式、前 30 秒结构、节奏（画面切换频率）、章节用法、缩略图（人脸/大字/对比）、时长分布、结尾 CTA、系列化。
2. **产出** `docs/best-practices.md`：可核对的清单，每条附例子。
3. **反哺软件**：
   - 第 1 步：**钩子检查**（第一段 ≤ 30 秒、含问题/数字/反差），**节奏检查**（一段 > 25 秒没换画面 → 黄标），标题公式生成器；
   - 第 2 步：语速建议（英文 150–170 wpm，中文 220–260 字/分），过快过慢提示；
   - 第 3 步：每 8–12 秒一次画面变化的提示；封面页：大字 ≤ 4 词、高对比、人脸/主体占 1/3；
   - 第 5 步：标题 A/B、标签建议、简介模板（前两行含关键词）。

**任务清单**
- [ ] 研究脚本 `tools/channel_study.py`（YouTube API → CSV）
- [ ] `docs/best-practices.md`（中英）
- [ ] 上述四处页面检查器（纯前端规则，读 `best-practices.json`）
- **验收**：规范文档 + 页面出现至少 5 条自动检查提示。

### 5.3 画中画（PiP）：说到某事时叠一张图/一段无声视频 🆕

**方案**：段内新增 `overlays`（叠加层），与主画面片段独立：
```jsonc
"overlays": [
  { "image": "assets/commons/map.jpg", "at": 3.0, "duration": 6, "position": "top-right", "size": 0.35,
    "border": true, "animate": "slide-in" },
  { "video": "assets/pexels/lava.mp4", "in": 2, "out": 8, "at": 9.5, "position": "bottom-left", "size": 0.4 }
]
```
- `at` 相对段开始（秒），可从字幕词时间戳**点选"说到这个词时出现"**（我们有逐词时间）；`size` 为画面宽度比例；位置 9 宫格或自定义 x/y；圆角/描边/阴影；进出动画（滑入、淡入、缩放）。
- 实现：ffmpeg `overlay` + `enable='between(t,at,at+dur)'`，叠加视频一律 `-an`；在段渲染的最后一步叠加（主画面 → 叠层 → 配音）。
- UI：片段编辑区下方"叠加层"条 + 在字幕文本上点词设 `at` + 位置九宫格 + 大小滑块 + 预览。

**任务清单**
- [ ] schema + 校验；渲染滤镜链；缓存
- [ ] UI：叠加层条、词级定位、九宫格、预览
- [ ] e2e：一段主视频 + 两个叠层
- **验收**：讲到"坦博拉"时右上角滑入地图 6 秒。

### 5.4 真人出镜：美化、换脸/数字人、变声 🧪⚠️

**如实评估**
- **声音美化（低沉/浑厚/磁性）**：ffmpeg 就能做一版专业级链路——高通去底噪 → 均衡（80–120 Hz 提 2–3 dB 增厚，2–4 kHz 微提清晰，去 6–8 kHz 齿音）→ 压缩器（比 3:1）→ 轻混响 → 响度归一。加为"人声预设"（新闻/播音/低沉磁性），成本一天。真变声（改变音色）用 **RVC**（开源，需 GPU 或耐心），归 5.5。
- **画面美化（磨皮、亮眼、瘦脸）**：静态可用 GFPGAN/CodeFormer；视频逐帧太慢。实用路径：录制时用 OBS + 美颜插件 / 手机相机美颜；后期只做调色（LUT）+ 轻磨皮（ffmpeg `bilateral`/`gblur` 局部）。
- **换头/AI 帅气形象、口型同步**：开源 **LivePortrait**（表情迁移）、**MuseTalk / SadTalker**（口型）、**FaceFusion**（换脸）——都需要 NVIDIA GPU，16 GB Mac 上分钟级/帧；商业 **HeyGen / D-ID / Synthesia** 数字人质量最好，$24–89/月，API 可接入 vidforge 作为"数字人段"。
- ⚠️ **平台规则**：YouTube 2024 起要求对"看似真实的合成/改动内容"打**披露标签**，未披露可被下架/限流；换成"看不出是 AI 的真人脸"正是要披露的情形。**用自己的脸做美化不需要披露；换成他人的/虚构的逼真脸需要。** 建议：形象设计成**明显风格化**的主持人（半写实/插画风），既不需要披露，也更有品牌辨识度。
- **法律**：不得使用真实他人的脸/声音。

**分阶段**
- 阶段 A（可以立刻做）：人声预设链路（3 档）+ 调色 LUT + 真人段类型 `{"video": "assets/me.mp4", "keep_audio": true}` 支持"我出镜说话"的段（保留原声、走同一字幕/归一链路）。
- 阶段 B：HeyGen/D-ID API 数字人段（付费，可选）。
- 阶段 C（🧪 独立项目）：LivePortrait/MuseTalk 本地流水线，需要 GPU 机器或云 GPU。

### 5.5 专属声音：采样 → 分析 → 合成频道独有音色 🧪（建议独立工具 voiceforge）

**思路**
1. **采样**：给一批参考视频/音频 → ffmpeg 抽音轨 → 用 whisper 切成带文本的 5–15 秒片段 → 去 BGM（Demucs 分离人声）。
2. **分析**：librosa/pyworld 提取基频均值与范围（低沉度）、语速、能量包络、频谱质心（明亮/温暖）→ 给每个样本一张"声音画像"，你对比挑"想要的特质"。
3. **合成**三条路：
   - **ElevenLabs Voice Design**（文字描述音色生成新声音，不依赖真人样本 → 无侵权问题）+ 微调参数；或 Professional Voice Clone（**只能克隆你自己的声音**，需授权声明）；
   - 开源 **CosyVoice 2 / F5-TTS**：零样本克隆，且 CosyVoice 支持 speaker embedding，可以把几段参考的 embedding **加权平均**得到一个"合成音色"——这就是"提取精华融合"在技术上的实现；GPT-SoVITS 可训练（含方言）；
   - 声音一旦确定，导出为 vidforge 的一个 provider（`voiceforge:` 本地服务），所有视频统一用它。
- ⚠️ 不克隆真实他人的声音（法律 + 平台）；融合多个真人样本在法律上仍是灰区，**优先 Voice Design / 自己的声音 / 明显合成的音色**。
- 16 GB Mac：F5-TTS/CosyVoice2 可跑（慢），训练建议云 GPU（$0.5/小时）。

**任务清单（voiceforge）**
- [ ] `extract`：视频→音轨→whisper 切片→Demucs 去伴奏
- [ ] `profile`：声音画像 JSON + 对比页面
- [ ] `design`：ElevenLabs Voice Design 封装 / CosyVoice embedding 融合实验
- [ ] `serve`：本地 HTTP TTS 服务 + vidforge provider
- **验收**：同一段文字，3 个候选音色 A/B 试听，选定后全项目切换。

### 5.6 品牌包：logo、slogan、片头片尾、专属音乐 🆕📖

**⚠️ 音乐版权是第一位**：AI 生成音乐里 **Suno/Udio 付费版**才有商用许可；**MusicGen（Meta）是 CC-BY-NC，不能用于变现频道**；Stable Audio Open 的许可对商业有限制。可靠来源：Suno Pro、YouTube 音频库（免费可商用）、Pixabay Music（免费）、Artlist/Epidemic（订阅）、或找作曲者定制。**片头音乐会出现在每一条视频里，一定要用有书面许可的。**

**方案（最佳实践引导，分四步）**
1. **研究**：找 12 个参考——中文：央视《新闻联播》《天气预报》（渔舟唱晚）、《国家宝藏》、《中国通史》、《河西走廊》（雅尼配乐）、李永乐、回形针；英文：BBC 纪录片、Kings and Generals、Kurzgesagt、Fall of Civilizations、Vox、Veritasium。每个记录：logo 形式（字标/图标/动效）、slogan、片头时长（数据：**5–8 秒**是留存最优；超过 10 秒跳出率明显上升）、片头音乐配器与调式、色彩、片尾结构（下集预告/订阅提示/致谢）。产出 `docs/brand-study.md`。
2. **生成候选**（每类 3–5 个供你挑）：
   - **命名 + slogan**：LLM 按定位（历史/科普、双语）各 10 条 → 你圈 3 → 再打磨；
   - **logo**：两路——SVG 字标（Remotion 直接可动画化，可控、清晰）+ AI 生图（Flux）图形标；风格：中文频道可用印章/篆书/山水留白，英文频道用衬线字标 + 单一符号（沙漏/地图/罗盘）；
   - **片头动画**：Remotion 组件 `Intro`（logo 入场 + slogan + 音效 sting，5–7 秒）、`Outro`（订阅/下集/致谢 8–10 秒，留 20 秒给 YouTube 片尾卡）；参数化颜色/字体/音效；
   - **音乐**：
     - 中国古代/历史：**古琴**（基底，泛音起手）+ **埙**（旋律，苍凉）+ **箫/笛**（副旋律）+ **古筝**（点缀刮奏）；五声调式（宫/羽）；慢速 60–72 bpm；片头 6 秒一个古琴泛音 + 埙一句即可；
     - 中国现代/科技：钢琴 + 电子 pad + 弦乐，加一件民乐点缀（笛或古筝）做辨识度；
     - 英美古代/中世纪：**风笛/爱尔兰哨笛**（凯尔特）、**竖琴**、**鲁特琴**、**羽管键琴**、**管风琴**（宗教/庄严）、弦乐四重奏；多利亚/自然小调；史诗感加定音鼓；
     - 欧美现代/科普：钢琴动机 + 弦乐 + 低音脉冲 + 轻电子（Kurzgesagt/Vox 风）；110–120 bpm，明亮大调。
     - 生成方式：Suno Pro 用上述配器描述生成 10 版 → 挑 → 在 vidforge 里作为 `intro/outro` 音乐；或 YouTube 音频库按乐器筛。
3. **落地**：`brand.json`（颜色、字体、logo 路径、slogan、片头/片尾音乐、专属声音）→ 项目继承；第 4 步"品牌片头/片尾"开关；封面模板用品牌色与字标。
4. **验收**：一条视频从片头到片尾用同一套视觉/听觉标识；片头 ≤ 7 秒。

**任务清单**
- [ ] `docs/brand-study.md`（12 个参考的拆解表）
- [ ] 命名/slogan 候选各 10（中/英）；logo 候选 SVG 5 + 生图 5；音乐配器描述 4 套 → Suno/音频库获取
- [ ] Remotion `Intro` / `Outro` 组件（参数化）；`brand.json` + 项目继承 + 第 4 步开关
- [ ] 封面模板（品牌色 + 字标 + 大字 ≤ 4 词）

---

## 依赖与成本一览

| 能力 | 需要 | 费用 |
|---|---|---|
| 1.1 / 5.1 / 5.2 LLM | 任一 API key（DeepSeek / Qwen / Gemini / OpenAI / Claude）或剪贴板模式 | ¥0.1–$0.3 / 篇；剪贴板 0 |
| 5.1 / 5.2 YouTube 数据 | 已有的 Google Cloud 项目启用 YouTube Data API | 免费配额内 |
| 3.2 Openverse / Internet Archive | 无 | 0 |
| 3.2 Google CSE (CC) / Unsplash | key | 免费额度内 |
| 5.4 数字人 | HeyGen/D-ID（可选） | $24–89/月 |
| 5.5 声音 | ElevenLabs Voice Design 或云 GPU | $5–22/月 或 $0.5/小时 |
| 5.6 音乐 | Suno Pro 或 YouTube 音频库 | $10/月 或 0 |
