# vidforge 交接文档：在 Mac 上继续开发

日期：2026-09-22 · 仓库：`git@github.com:AvartarSimon/vidforge.git`（分支 `main`）· 版本 0.4.0
用途：① 在 MacBook 上装起来、跑起来；② 喂给 Mac 上的 AI 助手，让它知道项目现状、已做的决定和未完成的事。
项目级 `CLAUDE.md` 是它的精简版，Claude Code 会自动读。

---

## 1. 先说清楚：没有 Docker，没有数据库

vidforge 是一个 **Python 包 + ffmpeg**，所有状态都是文件：

| 东西 | 在哪 | 进不进 git |
|---|---|---|
| 代码 | 仓库 | ✅ |
| 项目（脚本、分段、选的图） | `~/vidforge-projects/<名字>/project.json`（`VIDFORGE_WORKSPACE` 可改），或 `examples/demo/` | 只有 `examples/demo/project.json` 进 git；`assets/`、`build*/`、`.history/` 都被 `.gitignore` 排除 |
| 下载的素材、渲染缓存 | 项目里的 `assets/`、`build/clips/` | ❌ 需要就用 U 盘/网盘拷 |
| 用户级数据 | `~/.vidforge/`：`browser-profile/`（各 AI 网站登录态）、`me/`（真人素材库）、`categories/`、`voices/`、`client_secret.json`（YouTube） | ❌ |
| 密钥 | `.env`（仓库根或项目目录）：`PEXELS_API_KEY`、`PIXABAY_API_KEY`、`ELEVENLABS_API_KEY`、`SYNC_API_KEY` | ❌ 手动拷 |
| 本地模型 | Ollama 自己管理 | ❌ 在 Mac 上重新 pull |

所以"数据库/后端/前端"对应的是：**后端** = `vidforge ui` 这个 Python 进程（8765 端口，stdlib HTTP server）；**前端** = 它直接托管的 `vidforge/ui/static/`（双击启动器打开的就是这个）以及一个并行的 React 版（`vidforge/ui/react/`，开发时单独 `npm run dev`）。

---

## 2. Mac 安装（一次）

```bash
# 0) 基础工具
xcode-select --install                      # git 等
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
brew install python@3.12 ffmpeg node        # 系统自带 python3 通常太老；项目要求 >= 3.10
brew install --cask google-chrome           # 浏览器桥（Playwright 驱动本机 Chrome；Edge 也行）
brew install --cask ollama                  # 本地小模型（可选但推荐）；装完打开一次 Ollama.app

# 1) 代码
git clone git@github.com:AvartarSimon/vidforge.git ~/Projects/vidforge   # 先在 GitHub 加 Mac 的 SSH key，或用 https
cd ~/Projects/vidforge

# 2) Python 环境（推荐 venv，避免污染系统 python）
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"                     # dev 包含 playwright（不下载浏览器，用本机 Chrome）
vidforge doctor                             # 检查 ffmpeg + edge-tts

# 3) 本地模型（Apple Silicon 的 GPU 会被 Ollama 用上，比 Windows 那台 CPU 机快得多）
ollama pull qwen2.5:3b                      # 文本：搜索词、翻译、章节名（2 GB）
ollama pull qwen2.5vl:3b                    # 视觉：识别水印/文字标注、核对图片内容（3 GB）

# 4) 动画段（可选，需要 node）
vidforge remotion setup

# 5) 密钥（可选）：从 Windows 机拷 .env 过来，或 cp .env.example .env 再填
```

## 3. 启动

```bash
source ~/Projects/vidforge/.venv/bin/activate
vidforge start                              # 打开上次的项目；没有就进项目页新建
# 或
vidforge ui examples/demo                   # 先跑 demo 看整条链路
vidforge demo demo1 && vidforge build demo1 # 纯命令行验证渲染
```

双击方式：Finder 里 `start-vidforge.command`（第一次右键 → 打开）。它用 `python3` 命令——如果那是系统旧版本，要么 `brew link python@3.12`，要么先激活 venv 再双击。`vidforge shortcut` 可以在桌面生成快捷方式。

React 前端（只在改前端时需要，两个进程）：
```bash
vidforge ui <项目> --port 8765 --no-browser          # 终端 1：后端
cd vidforge/ui/react && npm install && npm run dev  # 终端 2：http://127.0.0.1:5175，/api 代理到 8765
```
提交前：`npx tsc -b`（在 `vidforge/ui/react`）+ `python -m unittest discover -s tests`（115 个，离线）。

Mac 特有的行为：
- 编码器自动选 `h264_videotoolbox`（`render.pick_encoder`）；
- 浏览器桥 `browser/__init__.py` 先试 `msedge` 再 `chrome`，没装 Edge 会打印一句然后用 Chrome；`VIDFORGE_BROWSER_CHANNEL=chrome` 可强制；
- 启动时若发现 8765 上跑着**旧代码**的 vidforge（`/api/health` 的 `stamp` 不同），会 `POST /api/shutdown` 让它退出再接管。

---

## 4. 现状：已经做完的（按五步向导）

### 第 1 步 脚本
- 三种来路：手写/粘贴；「用我浏览器里的 AI 生成」（Playwright 在你登录过的 ChatGPT/Claude/DeepSeek/千问/Kimi… 网页里输入提示词、读回答，无 API key）；「复制提示词」到任意 AI 再贴回来。
- 提示词模板在 `ui/static/app.js` 的 `buildPrompt()` 和 `ui/react/.../AiGeneratePanel.tsx`（两份必须同步）。**主题含中文即用中文提示**；要求单一语言（唯一允许英文的是"画面："行）、不要前言/备注/舞台提示/字数统计。
- 分类（`categories.py`，`~/.vidforge/categories/`）：每个选题方向一套设定（定位、资料源、心得、禁词、平台限制），会拼进提示词。
- `script_parser.parse()`：识别 `第N段`/`Chapter N:`/`##`/加粗标题/`画面：`/`旁白：`，丢掉 AI 寒暄、`注：`、整行括号舞台提示，去掉行内 `（注：…）` 和 `**`。`language_issues()` 标出中文项目里混入的英文句子，`/api/script/split` 返回 `issues`，前端提示。
- 每段独立版本历史；整份项目 `.history/` 保 30 份。

### 第 2 步 配音
- 默认 edge-tts（免费）；ElevenLabs；VoxCPM（本地声音设计，见 `docs/custom-voice-guide.md`）。逐段试听、逐段换声、按缓存 key 判断是否需要重合成。

### 第 3 步 画面（改动最多）
- 来源：Pexels / Pixabay（需 key）、Wikimedia Commons（无 key，只收 PD/CC0/CC-BY/CC-BY-SA，历史频道主力）、Openverse、Internet Archive、Google 图片（经浏览器，默认 CC 筛选）、百度图片（版权未知，加入前确认）。
- **一键配图**（`/api/autofill`，后台线程 + `GET /api/autofill` 进度）：给没画面的段生成搜索词（Ollama 在线时 `llm.keywords_batch()` 一次给全部段落出英文短语，专有名词 + 年份；否则 `keywords.suggest()` 启发式），立刻搜图下载，故事板出缩略图。选项：来源、"已有画面的段也重配"、"视觉核对"。
- **宁缺毋滥**（用户明确要求：宁愿少也不混进不相关或带水印的图）：
  1. `assets.relevant()`：查询的专有名词/数字必须真的出现在标题或描述里；
  2. Commons 搜索排除 `Images with watermarks` 分类，标题/描述含 watermark/logo/screenshot/collage 的跳过；Google/百度结果剔除 `BLOCKED_HOSTS`（Shutterstock、Getty、Alamy、视觉中国、千图…）；
  3. `llm.vision_check()`：视觉模型看图判"水印 / 文字标注 / 是否画的就是查询对象"；
  4. `pick_for_spec(strict=True)` 最多看 4 个候选，都不过就**留空**（不写 spec 占位）。
- 手选图：付费图库域名直接 409（可 force）；其它图加入后**后台**视觉核对（`State.enqueue_check`），结果存在 `assets/index.json` 的 `check` 字段，`project_view` 给 clip 加 `warning`/`checking`，故事板显示「⚠ 水印/标注」。
- Commons 限流：`download()` 对 429/503 退避重试；原图首次 429 立刻改取 1920px 缩略图；每次取图间隔 1 秒。
- 真人素材库（`me.py`，`~/.vidforge/me/`，文件名即标签）+ 画中画 + 口型同步 provider（synclabs / musetalk），用了口型同步会自动加 AI 披露。
- Remotion 动画段：TitleCard / Timeline / BarChart。

### 第 4 步 渲染
- 分阶段构建、结构化进度、每段成片缓存只重渲改过的段、响度归一、锐化、带框字幕、章节卡。
- 长视频正确性已过六轮 six-hats 审查（`docs/six-hats-rounds-2026-09-17.md`）。

### 第 5 步 发布
- `vidforge upload`：视频 + 简介（章节 + 素材 credits）+ 缩略图 + 字幕 + 播放列表 + 定时发布；i18n 导出/导入做多语言版本。

---

## 5. 已知问题 / 未做的事

- **两套前端并存**：`ui/static/app.js`（启动器打开的）和 `ui/react/`。每个 UI 改动要改两处；长期应让 React 版取代旧版并由后端托管 `dist/`（目前后端不托管 dist）。
- 视觉核对在无独显机器上每张约 1 分钟（Windows 那台是 Intel Ultra 5 125U，CPU 推理）；Mac 上应快很多，可以考虑把"手选图"的核对改回同步。
- 小模型（qwen2.5:3b）偶尔给出句子式或夹中文的搜索词，已做过滤/回退，但历史类冷门条目的命中率仍靠 Commons 标题质量；`relevant()` 的 60% 阈值可调。
- `examples/demo/project.json` 常有本地改动未提交（demo 被当试验田）；`examples/demo/.history/` 未加入 `.gitignore`（可以加）。
- 路线图 `docs/roadmap-v0.4-plan.md` 里未完成：LLM 直接生成脚本（API 路径，目前只有浏览器桥和本地小模型）、品牌包、专属声音工具化、真人出镜美化/数字人。
- 测试 115 个全部离线；e2e 浏览器测试需要 playwright + 本机浏览器。

---

## 6. 产品/内容层面的决定（避免 AI 助手再从头讨论）

- 平台政策是设计前提：YouTube 2025-07 的 inauthentic content 政策、中国 2025-09-01 AI 内容标识办法。应对是**自己的声音 + 自己的镜头 + 自己画的图表**，不是绕检测。
- 内容方向（见 `docs/creator-business-qa.md`，Q1–Q14）：FND 家属账号（心的项目）、澳洲家庭电池/太阳能决策工具（钱的项目）、美国历史频道走事件线 + "工程师看制度" + "同一年中国在干什么"；不做泛 AI 工具测评、不做 TTS 批量解说。
- 图片准确性优先于数量；中文项目必须纯中文旁白。

---

## 7. 把 Windows 上的工作带过来

```bash
# Windows 上打包（PowerShell）
Compress-Archive -Path $HOME\vidforge-projects, $HOME\.vidforge, C:\Simon\Projects\vidforge\.env -DestinationPath $HOME\Desktop\vidforge-data.zip
# Mac 上解压到 ~/vidforge-projects、~/.vidforge、仓库根目录的 .env
```
`~/.vidforge/browser-profile/` 里是 Chrome/Edge 的登录态，跨平台一般能用，不行就 `vidforge browser login` 重新登一次。
