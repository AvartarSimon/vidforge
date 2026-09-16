# MTTW all-team 评估：vidforge 怎么做得更好用

日期：2026-09-16 · 模式：`mttw all-team`（7 视角独立分析 → 共识/分歧 → 整合建议）
对象：vidforge 0.1（commit e128292）
触发：用户反馈 ①「UI 有点复杂，不知道怎么用」 ②「按关键词在网上找图片/视频供我选择；视频可选某几秒到几秒；最后拼接」

---

## 0. 现状事实（所有视角共同的输入）

- 用户是**一个人**做频道，不是开发团队；目标是尽快稳定出片，不是维护软件。
- 现有 UI 把 `project.json` 的**全部字段**摊在一页上（id/章节名/运镜/停顿/画面类型/路径/props JSON/声音/语速/provider/字幕…），没有"第一步做什么"的引导。
- 素材：Pexels 只取搜索结果的**第一张**，用户看不到候选；视频整段循环/裁到旁白长度，不能选几秒到几秒；一段只能配一个画面。
- 页面 JS 没有自动化测试（只有 API 测试 + 一次无头截图）。
- 依赖：Python + ffmpeg 必装；Node + Remotion 可选但安装重（Chrome 150 MB）。

---

## 1. PM（产品）

**用户真正要完成的任务**：脚本 → 每段配上"合适的画面" → 出片 → 发布。①和②其实是同一个问题：**"配画面"这一步现在既不可见（候选看不到）又不可控（不能选、不能裁）**，所以整个 UI 显得"不知道从哪下手"。

**优先级**
- **P0 引导式流程**：把一页表单改成 5 步向导（脚本 → 配音 → 画面 → 渲染 → 发布），每步一个主按钮；高级字段折叠。没有这一步，后面所有功能用户都找不到。
- **P0 素材挑选器**：关键词 → 网格展示候选图/视频 → 点选 → 视频可拖选起止点 → 一段可放多个片段。这是用户明确提出的需求，也是出片质量的决定因素。
- **P1 多来源**：Pexels 之外加 Pixabay（免费 API）和 **Wikimedia Commons**（历史频道的核心来源：古画、地图、老照片，公有领域），一律记录许可。
- **P2**：跨项目素材库、更多 Remotion 组件、Azure TTS。

**不做**：任意网页图片抓取（版权风险直接威胁频道变现，见 Q&A Q1 的 inauthentic content / Content ID 风险）；时间线式剪辑器。

**成功标准**：用户不看文档，30 分钟内用向导做出第一条 3 分钟视频；每段挑画面平均 < 1 分钟。

---

## 2. Architect（架构）

**保持的原则**：`project.json` 仍是唯一真相；UI 只是它的编辑器；命令行永远能做 UI 能做的一切。

**Schema 演进（向后兼容）**：段的画面从"一个 image/video"扩展为**片段列表**：

```jsonc
{ "id": "eruption", "text": "…",
  "clips": [
    { "video": "assets/pexels/lava-123.mp4", "in": 4.0, "out": 9.5 },      // 选段：4.0–9.5 s
    { "image": "assets/commons/tambora-1815.jpg", "motion": "zoom_in", "duration": 4 },
    { "video": "pexels:volcanic ash cloud", "in": 0, "out": 6 }
  ],
  "fit": "stretch"      // 片段总长 vs 旁白：stretch=最后一段延长/循环补齐 | trim=超出裁掉 | loop
}
```
旧写法 `image` / `video` / `remotion` 继续有效（loader 归一化为单元素 `clips`）。

**素材来源抽象**：`assets/providers/{pexels,pixabay,wikimedia}.py` 实现同一接口 `search(query, kind) -> [Candidate{id, thumb_url, preview_url, width, height, duration, author, license, page_url}]` 和 `fetch(candidate) -> Path`。UI 挑选器只依赖 Candidate，不知道来源细节。

**候选缓存**：`assets/<provider>/search-cache/<hash>.json`（24 h），避免重复请求消耗 200 次/小时的配额；用户的**选择**写进 `project.json`（片段的具体文件），不是写进缓存。

**风险**：一段多片段让"时长由旁白决定"的简单模型变复杂 → 用 `fit` 策略明确规则，默认 `stretch`（最后一个片段补齐），不引入手动时间线。

---

## 3. Backend（Python / ffmpeg）

**片段渲染**：
- 视频选段：`-ss in -to out -i file`（输入侧 seek，快）→ 缩放裁切到画幅 → 统一 fps/像素格式；
- 图片片段：现有 zoompan 路径，`duration` 由用户指定或按剩余时长均分；
- 段内多片段：每片段先渲成同参数的中间 mp4，再 concat demuxer 无损拼接（复用现有 `concat()`），最后与配音 mux；比 `filter_complex` 的 `concat` 滤镜简单且可缓存（每个片段按 (源, in, out, 尺寸) 哈希缓存）。
- `fit=stretch`：总长 < 旁白时，最后一个片段若是视频则 `-stream_loop`，若是图片则延长 `duration`。

**搜索接口**：`GET /api/search?q=&kind=photo|video&source=pexels|pixabay|wikimedia&page=` → Candidate 列表（含缩略图 URL，浏览器直接加载 CDN 图，不经过本地）；`POST /api/clips/pick` → 下载所选并写入段的 `clips`。视频预览：Pexels/Pixabay 给直链 mp4，`<video src=直链>` 即可在浏览器里拖看，**不用先下载**；选定后才下载。

**Wikimedia Commons**：`action=query&generator=search&gsrnamespace=6&prop=imageinfo&iiprop=url|extmetadata` 拿到图片、作者、许可（`LicenseShortName`）；只保留 PD / CC0 / CC-BY / CC-BY-SA，并把署名写进 `credits.txt`（CC-BY 系列**必须**署名）。

**工作量**：clips schema + 渲染 2 天；搜索 provider 三个 2 天；API 1 天。

---

## 4. Frontend（UI/UX）

**诊断**：现在的页面是"数据库表单"，不是"工作流"。用户的心智是"我在做第 3 段的画面"，页面却让他同时看见 6 段 × 15 个字段。

**改法：向导 + 故事板**
```
[1 脚本] → [2 配音] → [3 画面] → [4 渲染] → [5 发布]      ← 顶部步骤条，当前步高亮，可回退
```
- **1 脚本**：一个大文本框，一段一空行，自动切成 segments（或粘贴我给的 JSON）。只此一个操作。
- **2 配音**：选声音（带"试听 3 秒"）、语速；一个"全部配音"按钮；每段一行播放条 + 时长。停顿/单段换声音在"高级"里。
- **3 画面**（核心）：左侧**故事板**——每段一张卡片（缩略图 + 前 6 个字 + 时长），点选进入右侧**挑选器**：
  - 搜索框（默认填该段的关键词，由旁白自动提取 2–3 个名词）+ 来源 tab（Pexels / Pixabay / Commons / 本地上传 / 动画）
  - 候选网格（图片直接显示；视频卡片悬停播放，显示时长）
  - 点一个视频 → 弹出**选段条**：预览播放器 + 双滑块 in/out，显示"已选 5.5 s / 本段旁白 11.7 s"，「加入」按钮；可加多个片段，段内片段条显示占比
  - 图片 → 直接加入（可再设运镜）
  - 每段卡片显示"画面 ✓ / 缺 3.2 s"的状态，缺的段红点提示
- **4 渲染**：只有一个按钮 + 进度日志 + 完成后播放器。
- **5 发布**：标题/简介/标签/封面预览/章节 → "上传到 YouTube（私有）"；中文版一键切换。
- **首次打开**：3 步气泡引导（"这里写脚本 → 这里点配音 → 这里选画面"），可跳过。

**技术**：继续零依赖的原生 JS 可行，但页面会到 1500+ 行；建议拆成几个 `<script>` 文件或引入 Preact（3 KB，CDN 引用）管理状态。不上 React 构建链（保持 `pip install` 即用）。

**可达性/键盘**：挑选器支持 ←→ 切候选、空格预览、Enter 加入。

---

## 5. Database（数据）

vidforge 没有数据库，也**不应该有**——单人本地工具，文件即状态，可 git、可复制、可手改。但有三处"数据"值得规范化：

1. **候选缓存**：`assets/<provider>/search-cache/<sha1(q,kind,page)>.json`，含时间戳，24 h 过期；体积小，随项目走。
2. **素材索引升级**：现在的 `assets/pexels/index.json` 只记 `by_spec`；改为**每个文件一条记录**：`{file, provider, id, author, license, page_url, downloaded_at, used_in: [seg ids]}`，`credits.txt` 从这里生成，删段时能知道文件是否还被引用。
3. **跨项目素材库（P2）**：`~/.vidforge/library/`，同样的索引格式；挑选器加一个"我的素材"tab。到那一步如果索引超过几千条再考虑 SQLite（Python 内置，仍然零依赖），现在不需要。

**一致性规则**：`project.json` 引用文件路径；索引是派生数据，丢了可以从文件名 + provider 重建（文件名已含 provider id）。

---

## 6. QA（质量）

**现在的缺口**：页面 JS 没有测试；`build()` 没有集成测试；"文字改了配音过期"这类状态只靠人眼。

**必须补的**：
1. **浏览器端 e2e**：用已在机器上的 Edge/Chrome headless + Playwright（`pip install playwright`，或用 Remotion 已下载的 Chrome），覆盖 5 条路径：新建项目→写脚本→配音→为一段选视频并裁 3–8 s→渲染→final.mp4 时长符合预期。每次改 UI 必跑。
2. **裁切数学单测**：in/out 边界（in≥out、out>源时长、负数）、`fit` 三种策略、片段总长与旁白的补齐逻辑——这里最容易出"最后一帧黑屏 / 音画不同步"。
3. **许可断言**：Commons provider 的过滤测试——一张 "Fair use" 或无许可的图必须被拒绝。
4. **可用性测试**（非自动化）：用户本人不看文档做一条视频，记录卡住的每一处，这是 P0 的验收方式。

**回归风险**：`clips` 归一化必须让现有 demo（image/video/remotion 三种写法）渲染结果**逐字节相同**的 timeline —— 用现有 demo 的 `timeline.json` 做黄金文件。

---

## 7. DevOps（交付/运行）

**安装路径太长**：现在要 Python、pip、ffmpeg、（Node、npm、Chrome）。对"一个做视频的人"来说每一步都是流失点。
- 短期：`start-vidforge.cmd` / `.command`（Mac）双击脚本：检查 ffmpeg，没有就提示一条安装命令；启动 UI；打开浏览器。
- 中期：`pipx install vidforge`；`vidforge doctor --fix` 自动 winget/brew 装 ffmpeg。
- Remotion 保持**按需**：只有用户在 UI 里第一次选"动画"时才提示安装，安装进度显示在页面里，而不是命令行。

**运行**：
- UI 服务器加一个 `/api/health`；页面顶部显示 ffmpeg/Node/各 key 的状态点（现在藏在 `doctor` 命令里）。
- 长渲染要**可取消**（现在只能 Ctrl+C 服务器）：build 线程检查取消标志，杀掉当前 ffmpeg 子进程。
- 日志落盘 `build/build.log`，出错时页面给"复制日志"按钮，方便贴给我排查。

**Mac 对齐**：用户真正的制作机是 16 GB Mac，所有新功能在 Mac 上跑一遍再算完成；ffmpeg 滤镜路径转义、字体名（PingFang）、`open` vs `start` 三处是历史上最常出问题的地方。

---

## 8. 整合

### 共识（7/7）
1. 问题①和②是一件事：**"配画面"是核心工作流，却是现在最弱、最不可见的一步**。修好它，UI 自然就"知道怎么用"。
2. 用**向导 + 故事板 + 挑选器**替代表单页；`project.json` 仍是唯一真相，命令行能力不减。
3. 只接**许可清晰**的来源（Pexels、Pixabay、Wikimedia Commons PD/CC），不做任意网页抓图；署名自动进简介。
4. 不引入数据库、不引入前端构建链。

### 分歧与裁决
| 分歧 | 双方 | 裁决 |
|---|---|---|
| 前端要不要引入 Preact | Frontend：状态复杂了，需要；DevOps：多一个 CDN 依赖 | 允许 Preact **单文件 CDN**（无构建），页面拆成 `static/*.js` 多文件；仍是 `pip install` 即用 |
| 段内多片段的时长规则 | Backend：想给用户完全手控；Architect：会滑向时间线编辑器 | 用 `fit` 三策略 + 挑选器里的"已选 / 需要"计数，**不做**拖拽时间线 |
| Remotion 是否默认安装 | Frontend：动画是差异化；DevOps：安装太重 | 按需，首次选"动画"时页面内引导安装 |
| e2e 用什么跑 | QA：Playwright；DevOps：再多一个依赖 | Playwright 只作为 **dev 依赖**（`pip install -e .[dev]`），用户安装不带 |

### 建议的路线（v0.2 → v0.3）

| 阶段 | 内容 | 工作量 | 验收 |
|---|---|---|---|
| **A. 挑选器 + 选段 + 拼接**（先做——用户明确要的） | `clips` schema 与渲染；Pexels 候选网格；视频 in/out 选段；段内多片段；Pixabay + Commons provider；索引升级 + 署名 | 4–5 天 | 用户为 demo 的每段各选 1–2 个片段并渲出成片；裁切/许可单测绿 |
| **B. 向导化 UI** | 5 步流程、故事板、高级字段折叠、首次引导、健康状态点、渲染可取消、复制日志 | 3–4 天 | 用户不看文档 30 分钟做出第一条 3 分钟视频 |
| **C. 交付** | 双击启动脚本（Win/Mac）、Playwright e2e 5 条、Mac 全流程验证 | 2 天 | Mac 上从零安装到出片一次通过 |

A 在 B 前：挑选器是 B 中"第 3 步"的核心组件，先把它做对，向导只是把它摆到正确的位置。

### 风险
- Pexels 200 次/小时配额：候选缓存 + 每次搜索取 30 条一页；Pixabay 5000 次/小时可作兜底。
- Commons 图片尺寸参差、常有透明背景/竖图：挑选器显示尺寸并默认按宽度 ≥ 1280 过滤，渲染时铺底色。
- 多片段 + 多语言：`clips` 与语言无关（画面共用），只有 Remotion props 有 `{en,zh}`——不变。
