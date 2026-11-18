import { useEffect, useRef, useState } from 'react'
import {
  Alert,
  Box,
  Button,
  Checkbox,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  LinearProgress,
  Stack,
  TextField,
  Typography,
} from '@mui/material'
import SubtitlesIcon from '@mui/icons-material/Subtitles'
import { apiPost } from '../../api/client'
import { useProject } from '../../state/ProjectContext'
import { DialogHeader } from './ui'

type Row = {
  segId: string
  state: 'waiting' | 'working' | 'ready' | 'error'
  script: string
  text: string
  hits?: number
  total?: number
  use: boolean
  error?: string
}

/** How much of the script a take was heard saying, as a share; null when unknown. */
export function matchShare(a?: { hits: number; total: number } | null): number | null {
  return a && a.total ? a.hits / a.total : null
}

/**
 * Character diff of the script against what was heard: the script's characters that were not
 * said are struck through, the words that were said instead are marked. Longest common
 * subsequence over characters — a segment is a couple of hundred, so the table stays small.
 */
function Diff({ script, heard }: { script: string; heard: string }) {
  const a = [...script]
  const b = [...heard]
  const n = a.length
  const m = b.length
  const dp = Array.from({ length: n + 1 }, () => new Uint16Array(m + 1))
  for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--) dp[i][j] = a[i] === b[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1])
  const out: { t: string; k: 'same' | 'gone' | 'new' }[] = []
  let i = 0
  let j = 0
  const push = (t: string, k: 'same' | 'gone' | 'new') => {
    const last = out[out.length - 1]
    if (last && last.k === k) last.t += t
    else out.push({ t, k })
  }
  while (i < n && j < m) {
    if (a[i] === b[j]) push(a[i++], (j++, 'same'))
    else if (dp[i + 1][j] >= dp[i][j + 1]) push(a[i++], 'gone')
    else push(b[j++], 'new')
  }
  while (i < n) push(a[i++], 'gone')
  while (j < m) push(b[j++], 'new')
  // a mark that differs (，vs 。, one missing) is not a word that changed: shown plain, not flagged
  const marks = /^[\s，。、；：！？,.;:!?…“”"'（）()《》—-]+$/
  return (
    <Typography variant="body2" component="div" sx={{ lineHeight: 1.9 }}>
      {out.map((p, k) =>
        p.k !== 'same' && marks.test(p.t) ? (
          p.k === 'new' ? <span key={k}>{p.t}</span> : null
        ) : p.k === 'same' ? (
          <span key={k}>{p.t}</span>
        ) : p.k === 'gone' ? (
          <Box key={k} component="span" sx={{ color: 'error.main', textDecoration: 'line-through', opacity: 0.75 }}>
            {p.t}
          </Box>
        ) : (
          <Box key={k} component="span" sx={{ color: 'success.dark', bgcolor: 'success.light', borderRadius: 0.5, px: 0.25 }}>
            {p.t}
          </Box>
        ),
      )}
    </Typography>
  )
}

/**
 * 按录音识别文字. When a take strays from its script, the subtitles show words that were never
 * said, timed by guesswork in between. This hears each take, shows it against the script, and
 * makes the chosen ones the script — which the take then matches word for word. Never applied
 * unseen: Whisper mishears names, so the text is editable first.
 */
export function RecognizeDialog({ open, onClose, only }: { open: boolean; onClose: () => void; only?: string[] }) {
  const { raw, view, reload, saveNow } = useProject()
  const [rows, setRows] = useState<Row[]>([])
  const [applying, setApplying] = useState(false)
  const [done, setDone] = useState<string | null>(null)
  const run = useRef(0)

  useEffect(() => {
    if (!open || !raw) return
    const id = ++run.current
    const segs = raw.segments.filter((s) => s.narration && (!only || only.includes(s.id)))
    setDone(null)
    setRows(segs.map((s) => ({ segId: s.id, state: 'waiting', script: s.text || '', text: '', use: false })))
    ;(async () => {
      if (!(await saveNow())) return
      for (const s of segs) {
        if (run.current !== id) return // closed or reopened: stop hearing for the old one
        setRows((rs) => rs.map((r) => (r.segId === s.id ? { ...r, state: 'working' } : r)))
        try {
          const j = await apiPost<{ text: string; script: string; hits?: number; total?: number }>('/api/narration/recognize', { segment: s.id })
          const share = j.total ? (j.hits || 0) / j.total : 0
          setRows((rs) =>
            rs.map((r) =>
              r.segId === s.id
                ? { ...r, state: 'ready', text: j.text, script: j.script, hits: j.hits, total: j.total, use: !!j.text && share < 0.95 && j.text !== j.script }
                : r,
            ),
          )
        } catch (e) {
          setRows((rs) => rs.map((r) => (r.segId === s.id ? { ...r, state: 'error', error: e instanceof Error ? e.message : String(e) } : r)))
        }
      }
    })()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  const close = () => {
    run.current++
    onClose()
  }

  const chosen = rows.filter((r) => r.use && r.state === 'ready' && r.text.trim())
  const working = rows.some((r) => r.state === 'waiting' || r.state === 'working')

  const apply = async () => {
    setApplying(true)
    try {
      for (const r of chosen) await apiPost('/api/narration/recognize', { segment: r.segId, apply: r.text.trim() })
      await reload()
      setDone(`已替换 ${chosen.length} 段的文字。字幕会按你实际说的显示，下次渲染时重新对齐（后台已经开始做了）。原来的脚本在「历史」里能找回。`)
      setRows((rs) => rs.map((r) => (r.use ? { ...r, use: false, script: r.text.trim() } : r)))
    } catch (e) {
      setDone(`替换失败：${e instanceof Error ? e.message : String(e)}`)
    }
    setApplying(false)
  }

  const own = raw?.segments.filter((s) => s.narration).length || 0

  return (
    <Dialog open={open} onClose={close} maxWidth="lg" fullWidth>
      <DialogHeader
        icon={<SubtitlesIcon />}
        tone="blue"
        title="按录音识别文字"
        sub="录的时候没照稿念，字幕就会显示没说过的话。这里把每段录音听写出来，和脚本对比；勾上的段落用识别的文字替换脚本，字幕就和声音一致了。"
        onClose={close}
      />
      <DialogContent>
        {!own && <Alert severity="info">这个项目还没有用自己录音的段落——合成配音的字幕本来就是逐字对齐的。</Alert>}
        <Stack spacing={1.5}>
          {rows.map((r) => {
            const share = r.total ? (r.hits || 0) / r.total : null
            const resolvedShare = matchShare(view?.resolved?.[r.segId]?.align)
            const pct = share ?? resolvedShare
            return (
              <Box key={r.segId} sx={{ border: '1px solid', borderColor: r.use ? 'primary.main' : 'divider', borderRadius: 2, p: 1.5 }}>
                <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
                  <Checkbox size="small" checked={r.use} disabled={r.state !== 'ready' || !r.text} onChange={(e) => setRows((rs) => rs.map((x) => (x.segId === r.segId ? { ...x, use: e.target.checked } : x)))} sx={{ p: 0.25 }} />
                  <Typography fontWeight={700}>{r.segId}</Typography>
                  {pct != null && (
                    <Chip size="small" color={pct < 0.8 ? 'error' : pct < 0.95 ? 'warning' : 'success'} variant="outlined" label={`录音对上脚本 ${Math.round(pct * 100)}%`} />
                  )}
                  {r.state === 'working' && <Typography variant="caption" color="text.secondary">正在听写…</Typography>}
                  {r.state === 'waiting' && <Typography variant="caption" color="text.secondary">排队中</Typography>}
                  {r.state === 'error' && <Typography variant="caption" color="error.main">{r.error}</Typography>}
                </Stack>
                {r.state === 'working' && <LinearProgress sx={{ mb: 1 }} />}
                {r.state === 'ready' && !r.text && (
                  <Typography variant="body2" color="text.secondary">
                    这段录音里没听到说话（或者太小声）——脚本保持原样。
                  </Typography>
                )}
                {r.state === 'ready' && !!r.text && (
                  <>
                    <Typography variant="caption" color="text.secondary">
                      和脚本的差别（<Box component="span" sx={{ color: 'error.main', textDecoration: 'line-through' }}>划掉</Box>的是脚本里没说的，
                      <Box component="span" sx={{ color: 'success.dark' }}>绿色</Box>的是实际说的）
                    </Typography>
                    <Box sx={{ bgcolor: 'action.hover', borderRadius: 1, p: 1, mb: 1 }}>
                      <Diff script={r.script} heard={r.text} />
                    </Box>
                    <TextField
                      size="small"
                      fullWidth
                      multiline
                      minRows={2}
                      label="替换后的文字（人名、术语听错了就在这里改）"
                      value={r.text}
                      onChange={(e) => setRows((rs) => rs.map((x) => (x.segId === r.segId ? { ...x, text: e.target.value, use: true } : x)))}
                    />
                  </>
                )}
              </Box>
            )
          })}
        </Stack>
        {done && (
          <Alert severity={done.startsWith('替换失败') ? 'warning' : 'success'} sx={{ mt: 1.5 }}>
            {done}
          </Alert>
        )}
      </DialogContent>
      <DialogActions>
        <Typography variant="caption" color="text.secondary" sx={{ mr: 'auto', pl: 2 }}>
          默认勾上对得不好的段落（低于 95%）；没勾的保持原样。
        </Typography>
        <Button onClick={close}>关闭</Button>
        <Button variant="contained" onClick={apply} disabled={applying || working || !chosen.length}>
          {working ? '识别中…' : `用识别的文字替换 ${chosen.length} 段`}
        </Button>
      </DialogActions>
    </Dialog>
  )
}
