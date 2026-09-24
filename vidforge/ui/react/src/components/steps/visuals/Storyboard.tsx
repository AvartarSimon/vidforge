import { useEffect, useRef, useState } from 'react'
import {
  Box,
  Button,
  Checkbox,
  FormControlLabel,
  LinearProgress,
  MenuItem,
  Select,
  Slider,
  Stack,
  Typography,
} from '@mui/material'
import { apiGet, apiPost } from '../../../api/client'
import { useProject } from '../../../state/ProjectContext'
import { fileUrl, fmtDuration } from '../../../utils'

type AutofillStatus = {
  state: 'idle' | 'running' | 'done'
  done: number
  total: number
  pictures: number
  project: string
  title: string
  lines: string[]
  result: {
    filled: number
    resolved: number
    segments_with_pictures: number
    failed: { id: string; query: string }[]
    source: string
    kind: string
    llm: boolean
    site: string
    generic: string[]
    topic_pool: string[]
    vision: string | null
  } | null
}

// same list as the picker's 搜索 tab (SearchTab.tsx) — autofill should be able to reach every
// source you can reach by hand, videos included
const SOURCES: { id: string; label: string; kinds: ('image' | 'video')[] }[] = [
  { id: 'commons', label: 'Wikimedia Commons（历史画/地图/老照片）', kinds: ['image'] },
  { id: 'openverse', label: 'Openverse（CC 聚合：Flickr/博物馆）', kinds: ['image'] },
  { id: 'archive', label: 'Internet Archive（公有领域老照片/影像）', kinds: ['image', 'video'] },
  { id: 'pexels', label: 'Pexels（需要 key）', kinds: ['image', 'video'] },
  { id: 'pixabay', label: 'Pixabay（需要 key）', kinds: ['image', 'video'] },
  { id: 'google', label: 'Google 图片 · 仅 CC（用我的浏览器，较慢）', kinds: ['image'] },
  { id: 'google_all', label: 'Google 图片 · 全部 ⚠ 版权未知', kinds: ['image'] },
  { id: 'baidu', label: '百度图片 ⚠ 版权未知', kinds: ['image'] },
]
const DEFAULT_SOURCE = { image: 'commons', video: 'archive' } as const

// "3/22 段 · 11 张 · 已用 40 秒，约还需 4 分 10 秒" — a bare count looks stalled on a long run
function fmtSecs(s: number): string {
  s = Math.max(0, Math.round(s))
  return s < 60 ? `${s} 秒` : `${Math.floor(s / 60)} 分 ${String(s % 60).padStart(2, '0')} 秒`
}

function etaText(p: { done: number; total: number; pictures: number; started: number }): string {
  const elapsed = (Date.now() - p.started) / 1000
  const pics = p.pictures ? ` · ${p.pictures} 张` : ''
  if (!p.done || elapsed < 3) return `${pics}　已用 ${fmtSecs(elapsed)}`
  const left = (elapsed / p.done) * (p.total - p.done)
  return `${pics}　已用 ${fmtSecs(elapsed)}${left > 1 ? `，约还需 ${fmtSecs(left)}` : ''}`
}

export function Storyboard({ selId, onSelect }: { selId: string | null; onSelect: (id: string) => void }) {
  const { raw, view, reload, saveNow } = useProject()
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<string | null>(null)
  const [kind, setKind] = useState<'image' | 'video'>('image')
  const [source, setSource] = useState<string>(DEFAULT_SOURCE.image)
  const [overwrite, setOverwrite] = useState(false)
  // The vision check costs about a minute per picture on a machine without a GPU, and a run now
  // fetches dozens of them — so it is off by default and the text filters do the work.
  const [vision, setVision] = useState(false)
  const [perSeg, setPerSeg] = useState<[number, number]>([3, 10])
  // who writes the search phrases: the local 3B model is instant but weak on abstract narration,
  // a full-size model in the user's own browser is much better (one question, 30-120 s)
  const [site, setSite] = useState('')
  const [sites, setSites] = useState<{ id: string; label: string }[]>([])
  useEffect(() => {
    apiGet<{ sites: { id: string; label: string }[] }>('/api/chat/sites')
      .then((j) => setSites(j.sites))
      .catch(() => setSites([]))
  }, [])
  const [progress, setProgress] = useState<{ done: number; total: number; pictures: number; started: number } | null>(null)
  const progressStart = useRef(0)

  if (!raw) return null
  const segments = raw.segments
  const resolved = view?.resolved || {}
  // "needs a picture" = no clips, or only unresolved provider:query specs (the old autofill wrote
  // those without downloading anything, so such segments look filled but have nothing to show)
  const missing = segments.filter(
    (s) =>
      !s.remotion &&
      (!s.clips.length || (resolved[s.id]?.clips || []).every((c) => !c.path && !!c.source)),
  ).length

  const pickKind = (k: 'image' | 'video') => {
    setKind(k)
    if (!SOURCES.find((o) => o.id === source)?.kinds.includes(k)) setSource(DEFAULT_SOURCE[k])
  }

  // the server searches + downloads one picture per segment in a thread; poll until it is done
  const autofill = async () => {
    if (!(await saveNow())) return
    setBusy(true)
    setMsg(null)
    progressStart.current = Date.now()
    try {
      const start = await apiPost<{ started: boolean; total: number }>('/api/autofill', {
        source,
        kind,
        overwrite,
        vision,
        site,
        min_per_segment: perSeg[0],
        max_per_segment: perSeg[1],
      })
      if (!start.total) {
        setMsg('没有需要配图的段落。勾上「已有画面的段也重配」可以全部重来。')
        setBusy(false)
        return
      }
      setProgress({ done: 0, total: start.total, pictures: 0, started: Date.now() })
      let st: AutofillStatus
      let ticks = 0
      do {
        await new Promise((r) => setTimeout(r, 1000))
        st = await apiGet<AutofillStatus>('/api/autofill')
        setProgress({ done: st.done, total: st.total, pictures: st.pictures ?? 0, started: progressStart.current })
        // the server saves each segment as it finishes, so refresh the storyboard while it runs —
        // a run with the vision check on takes about a minute per picture and used to look frozen
        if (++ticks % 4 === 0) await reload()
      } while (st.state === 'running')
      const r = st.result
      if (r) {
        const unit = r.kind === 'video' ? '段视频' : '张图'
        const failed = r.failed.length
          ? `；${r.failed.length} 段没有准确的素材，留空了（${r.failed.map((f) => f.id).join('、')}），点开手动选`
          : ''
        const who = r.site ? `搜索词来自 ${r.site}` : r.llm ? '搜索词来自本地模型' : '搜索词来自关键词提取'
        const how = `${r.source}，${who}${r.vision ? `，${r.vision} 已核对水印和内容` : ''}`
        // segments whose narration is abstract got a picture of the video's subject instead —
        // on-topic but generic, so say which ones deserve a look
        const generic = r.generic?.length
          ? `；其中 ${r.generic.length} 段旁白太抽象或搜不到，用主题素材补足（${r.topic_pool.join('、')}），建议自己换`
          : ''
        setMsg(
          `已为 ${r.segments_with_pictures}/${r.filled} 段配好 ${r.resolved} ${unit}（${how}）${generic}${failed}。不满意的段点开重选。`,
        )
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
          ✨ 一键配{kind === 'video' ? '视频' : '图'}
          {overwrite ? '（全部重配）' : missing ? `（${missing} 段没画面）` : ''}
        </Button>
        <Select size="small" value={kind} onChange={(e) => pickKind(e.target.value as 'image' | 'video')} disabled={busy} sx={{ fontSize: 12 }}>
          <MenuItem value="image" sx={{ fontSize: 12 }}>图片</MenuItem>
          <MenuItem value="video" sx={{ fontSize: 12 }}>视频</MenuItem>
        </Select>
        <Select size="small" value={source} onChange={(e) => setSource(e.target.value)} disabled={busy} sx={{ fontSize: 12, minWidth: 150 }}>
          {SOURCES.filter((o) => o.kinds.includes(kind)).map((o) => (
            <MenuItem key={o.id} value={o.id} sx={{ fontSize: 12 }}>
              {o.label}
            </MenuItem>
          ))}
        </Select>
        <FormControlLabel
          control={<Checkbox size="small" checked={overwrite} onChange={(e) => setOverwrite(e.target.checked)} disabled={busy} />}
          label={<Typography variant="caption">已有画面的段也重配</Typography>}
        />
        <Box sx={{ width: 210 }}>
          <Typography variant="caption">
            每段 {perSeg[0]}–{perSeg[1]} 张（约每 5 秒旁白一张）
          </Typography>
          <Slider
            size="small"
            min={1}
            max={15}
            step={1}
            value={perSeg}
            disabled={busy}
            onChange={(_, v) => setPerSeg(v as [number, number])}
            valueLabelDisplay="auto"
          />
        </Box>
        <FormControlLabel
          control={<Checkbox size="small" checked={vision} onChange={(e) => setVision(e.target.checked)} disabled={busy} />}
          label={<Typography variant="caption">逐段视觉核对（本地模型，每段约 1 分钟，慢）</Typography>}
        />
        <Select size="small" value={site} onChange={(e) => setSite(e.target.value)} disabled={busy} sx={{ fontSize: 12, minWidth: 170 }}>
          <MenuItem value="" sx={{ fontSize: 12 }}>
            搜索词：本地模型（快）
          </MenuItem>
          {sites.map((o) => (
            <MenuItem key={o.id} value={o.id} sx={{ fontSize: 12 }}>
              搜索词：{o.label}（更准，需登录）
            </MenuItem>
          ))}
        </Select>
      </Stack>
      {progress && (
        <Box>
          <LinearProgress variant={progress.total ? 'determinate' : 'indeterminate'} value={progress.total ? (100 * progress.done) / progress.total : 0} />
          <Stack direction="row" spacing={1} alignItems="center">
            <Typography variant="caption" color="text.secondary">
              正在搜图{vision ? '、核对' : ''}并下载… {progress.done}/{progress.total} 段
              {etaText(progress)}　可以切到别的项目，它会继续在后台跑完。
            </Typography>
            <Button size="small" color="warning" onClick={() => apiPost('/api/autofill/cancel', {})}>
              停止
            </Button>
          </Stack>
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
