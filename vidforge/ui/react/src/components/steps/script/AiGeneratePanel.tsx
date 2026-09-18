import { useEffect, useRef, useState } from 'react'
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Box,
  Button,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from '@mui/material'
import ExpandMoreIcon from '@mui/icons-material/ExpandMore'
import { apiGet, apiPost } from '../../../api/client'
import type { Category, ChatSite, SplitSegment } from '../../../api/types'
import { useProject } from '../../../state/ProjectContext'
import { pollLoginStatus } from '../../../utils'
import { SplitPreviewDialog } from './SplitPreviewDialog'

function categoryNote(categories: Category[], categoryId?: string | null) {
  const c = categories.find((x) => x.id === categoryId)
  if (!c) return ''
  const bits: string[] = []
  if (c.topic_notes) bits.push(`定位/要讲什么：${c.topic_notes}`)
  if (c.sources?.length) bits.push(`可参考的资料源：${c.sources.map((s) => s.name + (s.url ? `(${s.url})` : '')).join('；')}`)
  if (c.insights) bits.push(`过往心得：${c.insights}`)
  if (c.banned_keywords?.length) bits.push(`⚠ 禁止出现以下关键词，如涉及请换种说法：${c.banned_keywords.join('、')}`)
  if (c.platform_restrictions) bits.push(`⚠ 平台限制/把关要求：${c.platform_restrictions}`)
  return bits.length ? `\n\n分类「${c.name}」的设定（请遵守）：\n- ` + bits.join('\n- ') : ''
}

// same prompt template as the old vanilla-JS frontend's buildPrompt() (vidforge/ui/static/app.js)
function buildPrompt(opts: {
  zh: boolean
  topic: string
  mins: number
  audience: string
  points: string
  note: string
}) {
  const { zh, topic, mins, audience, points, note } = opts
  const words = Math.round(mins * (zh ? 240 : 150))
  const body = zh
    ? `请为一条约 ${mins} 分钟的讲解类视频写完整旁白脚本。主题：${topic}。${audience ? '受众/语气：' + audience + '。' : ''}${points ? '\n必须覆盖的要点/参考：\n' + points + '\n' : ''}
要求：
1. 总字数约 ${words} 字，口语化、短句、标点齐全（标点决定字幕断行和停顿）。
2. 前 30 秒是钩子：用一个反差、问题或具体数字抓住观众。
3. 按内容分成 8–15 个段落，每个段落一个意思、2–4 句；每个段落前单独一行写"第N段 章节名"（N 从 1 开始递增，纯文字，不要用 # 或加粗——网页里读出来的回答是渲染后的纯文字，格式符号会丢）。
4. 每个段落标题下面先写一行 "画面：" 给出适合的画面/素材描述（英文关键词 2–4 个，便于搜图），再写旁白正文。
5. 数字和年份用汉字读法或明确写法；涉及具体史实处如不确定请标注 [核实]。
6. 结尾一段是简短总结 + 引出下一集。只输出脚本本身，不要前言和解释。`
    : `Write the complete narration script for a ~${mins}-minute explainer video. Topic: ${topic}. ${audience ? 'Audience/tone: ' + audience + '.' : ''}${points ? '\nPoints/sources that must be covered:\n' + points + '\n' : ''}
Requirements:
1. About ${words} words, spoken style, short sentences, full punctuation (it drives subtitle breaks and pauses).
2. The first 30 seconds are a hook: a contrast, a question or a concrete number.
3. Split into 8-15 segments, one idea each, 2-4 sentences; put "Chapter N:" before each title on its own line (N counting up from 1), plain text — not "##" or **bold**, since the answer gets read back as rendered text and formatting characters don't survive that.
4. Under each heading first write one line "Visual: <2-4 English search keywords for stock footage>", then the narration.
5. Spell out numbers the way they should be read aloud; mark uncertain facts with [verify].
6. End with a short recap and a teaser for the next episode. Output only the script, no preamble.`
  return body + note
}

export function AiGeneratePanel({
  categories,
  points,
  onPointsChange,
}: {
  categories: Category[]
  points: string
  onPointsChange: (v: string) => void
}) {
  const { raw, patch } = useProject()
  const [sites, setSites] = useState<ChatSite[]>([])
  const [site, setSite] = useState(() => localStorage.getItem('vf.site') || 'deepseek')
  const [topic, setTopic] = useState(raw?.title || '')
  const [mins, setMins] = useState(raw?.target_minutes || 10)
  const [audience, setAudience] = useState('')
  const [script, setScript] = useState('')
  const [status, setStatus] = useState('')
  const [busy, setBusy] = useState(false)
  const [loginWall, setLoginWall] = useState(false)
  const [splitPieces, setSplitPieces] = useState<SplitSegment[] | null>(null)
  const cancelledRef = useRef(false)

  useEffect(() => {
    apiGet<{ sites: ChatSite[] }>('/api/chat/sites')
      .then((j) => setSites(j.sites))
      .catch(() => setSites([]))
    return () => {
      cancelledRef.current = true
    }
  }, [])

  if (!raw) return null
  const zh = (raw.language || 'en').startsWith('zh')

  const applyMinutes = (v: number) => {
    setMins(v)
    patch((r) => {
      r.target_minutes = v
    })
  }

  const doGenerate = async (retry = false) => {
    localStorage.setItem('vf.site', site)
    setBusy(true)
    setLoginWall(false)
    setStatus(`正在 ${sites.find((s) => s.id === site)?.label || site} 里提问并等待回答（通常 30–120 秒）…`)
    try {
      const prompt = buildPrompt({ zh, topic, mins, audience, points, note: categoryNote(categories, raw.category) })
      const j = await apiPost<{ text: string }>('/api/chat', { site, prompt })
      setScript(j.text)
      setStatus(`收到 ${j.text.length} 字，点「拆成段落」。`)
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e)
      setStatus(message)
      setLoginWall(!retry && /登录|验证|verify|log ?in/i.test(message))
    }
    setBusy(false)
  }

  const copyPrompt = async () => {
    const prompt = buildPrompt({ zh, topic, mins, audience, points, note: categoryNote(categories, raw.category) })
    await navigator.clipboard.writeText(prompt)
    setStatus('提示词已复制，贴到任意 AI，再把回答贴回下面的框。')
  }

  const startLogin = async (only?: string[]) => {
    setStatus(only ? '已打开浏览器窗口，登录这个网站后关闭窗口…' : '已打开浏览器窗口：8 个标签页逐个登录，全部登录后关闭窗口…')
    try {
      await apiPost('/api/chat', { login: true, sites: only })
    } catch (e) {
      setStatus(e instanceof Error ? e.message : String(e))
      return
    }
    await pollLoginStatus(setStatus, () => cancelledRef.current)
  }

  const retryAfterLogin = async () => {
    await startLogin([site])
    await doGenerate(true)
  }

  const doSplit = async () => {
    const text = script.trim()
    if (!text) return
    const j = await apiPost<{ segments: SplitSegment[] }>('/api/script/split', { text })
    if (j.segments.length) setSplitPieces(j.segments)
  }

  return (
    <Accordion defaultExpanded={!raw.segments.length}>
      <AccordionSummary expandIcon={<ExpandMoreIcon />}>
        <Typography variant="subtitle1">
          ✨ 用我的浏览器里的 AI 生成脚本（ChatGPT / Claude / Gemini / DeepSeek / Grok / 千问 / Kimi / 文心）
        </Typography>
      </AccordionSummary>
      <AccordionDetails>
        <Stack spacing={1.5}>
          <Stack direction="row" spacing={1.5} flexWrap="wrap" useFlexGap>
            <TextField size="small" label="主题 / 标题" value={topic} onChange={(e) => setTopic(e.target.value)} sx={{ minWidth: 220 }} />
            <TextField
              size="small"
              type="number"
              label="目标时长（分钟）"
              value={mins}
              onChange={(e) => applyMinutes(parseInt(e.target.value, 10) || 10)}
              sx={{ width: 160 }}
            />
            <TextField
              size="small"
              label="受众 / 语气"
              value={audience}
              onChange={(e) => setAudience(e.target.value)}
              sx={{ minWidth: 220 }}
            />
            <TextField
              size="small"
              select
              label="用哪个网站"
              value={site}
              onChange={(e) => setSite(e.target.value)}
              sx={{ width: 160 }}
            >
              {sites.map((s) => (
                <MenuItem key={s.id} value={s.id}>
                  {s.label}
                </MenuItem>
              ))}
            </TextField>
          </Stack>
          <TextField
            label="要点 / 参考资料（可选，越具体越好）"
            value={points}
            onChange={(e) => onPointsChange(e.target.value)}
            multiline
            minRows={3}
            placeholder={'- 1815 年 4 月坦博拉喷发\n- 1816 年欧洲北美夏季异常\n- 玛丽·雪莱与《弗兰肯斯坦》'}
          />
          <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
            <Button variant="contained" disabled={busy} onClick={() => doGenerate(false)}>
              在我的浏览器里生成
            </Button>
            <Button onClick={copyPrompt}>只复制提示词（我自己去贴）</Button>
            <Button size="small" onClick={() => startLogin()}>
              登录各站点…
            </Button>
            <Button size="small" title="只打开当前选中的网站登录，比较不容易漏掉" onClick={() => startLogin([site])}>
              只登录当前网站
            </Button>
            {loginWall && (
              <Button size="small" color="warning" onClick={retryAfterLogin}>
                先登录再重试
              </Button>
            )}
          </Stack>
          {status && (
            <Typography variant="body2" color="text.secondary">
              {status}
            </Typography>
          )}
          <TextField
            label="脚本"
            value={script}
            onChange={(e) => setScript(e.target.value)}
            multiline
            minRows={10}
            placeholder="把整篇脚本贴在这里，一段一空行；每段 2–4 句最合适。"
          />
          <Box>
            <Button variant="contained" onClick={doSplit} disabled={!script.trim()}>
              拆成段落
            </Button>
          </Box>
        </Stack>
      </AccordionDetails>
      <SplitPreviewDialog open={!!splitPieces} pieces={splitPieces || []} onClose={() => setSplitPieces(null)} />
    </Accordion>
  )
}
