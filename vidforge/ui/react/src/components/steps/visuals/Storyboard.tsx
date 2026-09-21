import { useState } from 'react'
import { Box, Button, Checkbox, FormControlLabel, LinearProgress, MenuItem, Select, Stack, Typography } from '@mui/material'
import { apiGet, apiPost } from '../../../api/client'
import { useProject } from '../../../state/ProjectContext'
import { fileUrl, fmtDuration } from '../../../utils'

type AutofillStatus = {
  state: 'idle' | 'running' | 'done'
  done: number
  total: number
  lines: string[]
  result: { filled: number; resolved: number; failed: { id: string; query: string }[]; source: string; llm: boolean; vision: string | null } | null
}

// where the first rough cut comes from: Commons = paintings/maps/old photos (history), stock = modern footage
const SOURCES = [
  { id: 'commons', label: 'Wikimedia Commons（历史画/地图/老照片）' },
  { id: 'pexels', label: 'Pexels（需要 key）' },
  { id: 'pixabay', label: 'Pixabay（需要 key）' },
]

export function Storyboard({ selId, onSelect }: { selId: string | null; onSelect: (id: string) => void }) {
  const { raw, view, reload, saveNow } = useProject()
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<string | null>(null)
  const [source, setSource] = useState('commons')
  const [overwrite, setOverwrite] = useState(false)
  const [vision, setVision] = useState(true)
  const [progress, setProgress] = useState<{ done: number; total: number } | null>(null)

  if (!raw) return null
  const segments = raw.segments
  const resolved = view?.resolved || {}
  const missing = segments.filter((s) => !s.clips.length && !s.remotion).length

  // the server searches + downloads one picture per segment in a thread; poll until it is done
  const autofill = async () => {
    if (!(await saveNow())) return
    setBusy(true)
    setMsg(null)
    try {
      const start = await apiPost<{ started: boolean; total: number }>('/api/autofill', { source, overwrite, vision })
      setProgress({ done: 0, total: start.total })
      let st: AutofillStatus
      do {
        await new Promise((r) => setTimeout(r, 800))
        st = await apiGet<AutofillStatus>('/api/autofill')
        setProgress({ done: st.done, total: st.total })
      } while (st.state === 'running')
      const r = st.result
      if (r) {
        const failed = r.failed.length ? `；${r.failed.length} 段没有准确的图，留空了（${r.failed.map((f) => f.id).join('、')}），点开手动选` : ''
        const how = `${r.source}${r.llm ? '，搜索词来自本地模型' : '，搜索词来自关键词提取'}${r.vision ? `，${r.vision} 已核对水印和内容` : '，未装视觉模型（ollama pull qwen2.5vl:3b 可自动识别水印）'}`
        setMsg(`已为 ${r.filled} 段配好 ${r.resolved} 张图（${how}）${failed}。不满意的段点开重选。`)
      }
      await reload()
    } catch (e) {
      const m = e instanceof Error ? e.message : String(e)
      // a backend started before the last update has no GET /api/autofill -> "not found"
      setMsg(/not found/i.test(m) ? '后端是旧版本（没有这个接口）：关掉 vidforge 的黑窗口，重新双击 start-vidforge 再试。' : m)
    }
    setProgress(null)
    setBusy(false)
  }

  return (
    <Stack spacing={1}>
      <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
        <Button size="small" variant="contained" onClick={autofill} disabled={busy || (!overwrite && missing === 0)}>
          ✨ 一键配图{overwrite ? '（全部重配）' : missing ? `（${missing} 段没画面）` : ''}
        </Button>
        <Select size="small" value={source} onChange={(e) => setSource(e.target.value)} disabled={busy} sx={{ fontSize: 12, minWidth: 150 }}>
          {SOURCES.map((o) => (
            <MenuItem key={o.id} value={o.id} sx={{ fontSize: 12 }}>
              {o.label}
            </MenuItem>
          ))}
        </Select>
        <FormControlLabel
          control={<Checkbox size="small" checked={overwrite} onChange={(e) => setOverwrite(e.target.checked)} disabled={busy} />}
          label={<Typography variant="caption">已有画面的段也重配</Typography>}
        />
        <FormControlLabel
          control={<Checkbox size="small" checked={vision} onChange={(e) => setVision(e.target.checked)} disabled={busy} />}
          label={<Typography variant="caption">视觉核对水印/内容（本地模型，每张约 1 分钟）</Typography>}
        />
      </Stack>
      {progress && (
        <Box>
          <LinearProgress variant={progress.total ? 'determinate' : 'indeterminate'} value={progress.total ? (100 * progress.done) / progress.total : 0} />
          <Typography variant="caption" color="text.secondary">
            正在搜图{vision ? '、核对' : ''}并下载… {progress.done}/{progress.total}
          </Typography>
        </Box>
      )}
      {msg && (
        <Typography variant="caption" color="text.secondary">
          {msg}
        </Typography>
      )}
      <Stack spacing={1} sx={{ maxHeight: '75vh', overflowY: 'auto', pr: 0.5 }}>
        {segments.map((s) => {
          const r = resolved[s.id] || {}
          const c0 = s.clips[0]
          const p0 = r.clips?.[0]?.path
          const thumb = !c0
            ? '缺'
            : c0.me
              ? '🎥'
              : c0.remotion
                ? c0.remotion.composition
                : p0
                  ? r.clips?.[0]?.kind === 'video'
                    ? { poster: `/api/poster/${encodeURIComponent(s.id)}/0` }
                    : { img: fileUrl(p0) }
                  : '自动'
          return (
            <Box
              key={s.id}
              onClick={() => onSelect(s.id)}
              sx={{
                display: 'flex',
                gap: 1,
                p: 1,
                border: '2px solid',
                borderColor: s.id === selId ? 'primary.main' : 'divider',
                borderRadius: 2,
                cursor: 'pointer',
                bgcolor: s.id === selId ? 'action.selected' : 'transparent',
              }}
            >
              <Box
                sx={{
                  width: 64,
                  height: 40,
                  flexShrink: 0,
                  bgcolor: 'action.hover',
                  borderRadius: 1,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: 11,
                  overflow: 'hidden',
                  color: !c0 ? 'error.main' : 'text.secondary',
                }}
              >
                {typeof thumb === 'string' ? (
                  thumb
                ) : 'img' in thumb ? (
                  <img src={thumb.img || undefined} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                ) : (
                  <img src={thumb.poster} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                )}
              </Box>
              <Box sx={{ minWidth: 0, flexGrow: 1 }}>
                <Typography variant="caption" fontWeight={600}>
                  {s.id} <span style={{ color: 'inherit', opacity: 0.6 }}>{fmtDuration(r.need)}</span>
                </Typography>
                <Typography variant="caption" color="text.secondary" noWrap sx={{ display: 'block' }}>
                  {s.text || s.label}
                </Typography>
                <Typography variant="caption" color={s.clips.length ? 'text.secondary' : 'error.main'} sx={{ display: 'block' }}>
                  {s.clips.length ? `${s.clips.length} 个片段` : '● 需要画面'}
                  {r.clips?.some((c) => c.warning) && (
                    <span style={{ color: '#ed6c02' }} title={r.clips.filter((c) => c.warning).map((c) => c.warning).join('；')}>
                      {' '}⚠ 水印/标注
                    </span>
                  )}
                  {r.clips?.some((c) => c.checking) && <span style={{ opacity: 0.6 }}> · 核对中…</span>}
                </Typography>
              </Box>
            </Box>
          )
        })}
      </Stack>
    </Stack>
  )
}
