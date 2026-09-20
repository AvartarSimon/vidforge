import { useEffect, useState } from 'react'
import { Box, Button, Chip, Link, MenuItem, Stack, TextField, Typography } from '@mui/material'
import { apiGet, apiPost, ApiError } from '../../../api/client'
import type { Segment, SearchCandidate } from '../../../api/types'
import { useProject } from '../../../state/ProjectContext'
import { fmtDuration } from '../../../utils'
import { TrimDialog, type TrimRange } from './TrimDialog'

// Commons/Openverse/Google/Baidu are image-only — video search only ever offered those as a
// confusing "0 results" dead end (worse, the default source used to be one of them, so video
// search silently never worked at all unless you also knew to change source). Split each source
// into the kind(s) it actually supports and only ever offer kind-appropriate ones.
const SOURCES: { value: string; label: string; kinds: ('image' | 'video')[] }[] = [
  { value: 'commons', label: 'Wikimedia Commons（公有领域/CC，无需 key）', kinds: ['image'] },
  { value: 'openverse', label: 'Openverse（CC 聚合：Flickr/博物馆，无需 key）', kinds: ['image'] },
  { value: 'archive', label: 'Internet Archive（公有领域老照片/影像，无需 key）', kinds: ['image', 'video'] },
  { value: 'pexels', label: 'Pexels（需免费 key）', kinds: ['image', 'video'] },
  { value: 'pixabay', label: 'Pixabay（需免费 key）', kinds: ['image', 'video'] },
  { value: 'google', label: 'Google 图片 · 仅 CC 许可（用我的浏览器）', kinds: ['image'] },
  { value: 'google_all', label: 'Google 图片 · 全部 ⚠ 版权未知', kinds: ['image'] },
  { value: 'baidu', label: '百度图片 ⚠ 版权未知', kinds: ['image'] },
]

const DEFAULT_SOURCE = { image: 'commons', video: 'archive' } as const

const KEY_SIGNUP_URL: Record<string, string> = {
  PEXELS_API_KEY: 'https://www.pexels.com/api/',
  PIXABAY_API_KEY: 'https://pixabay.com/api/docs/',
}

export function SearchTab({ seg, segId, kind, onAdded }: { seg: Segment; segId: string; kind: 'image' | 'video'; onAdded: () => void }) {
  const { view, patch, saveNow } = useProject()
  const sources = SOURCES.filter((s) => s.kinds.includes(kind))
  const [source, setSource] = useState<string>(DEFAULT_SOURCE[kind])
  const [q, setQ] = useState('')
  const [cands, setCands] = useState<SearchCandidate[]>([])
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [needsKey, setNeedsKey] = useState<string | null>(null)
  const [adding, setAdding] = useState(false)
  const [trimming, setTrimming] = useState<SearchCandidate | null>(null)

  const keywords = view?.resolved[segId]?.keywords || []
  const resolvedClips = view?.resolved[segId]?.clips
  const segFixed = seg.clips.reduce((a, c, i) => {
    const rc = resolvedClips?.[i]
    const secs = c.video && c.out != null ? c.out - (c.in || 0) : c.image && c.duration ? c.duration : rc?.natural || 0
    return a + (secs || 0)
  }, 0)

  // reset the search box (but not source, that's a sticky preference) whenever the selected
  // segment changes — mirrors the old frontend's picker.cands = [] on storyboard click
  useEffect(() => {
    setCands([])
    setError(null)
    setQ(seg.visual_hint || keywords[0] || '')
    setPage(1)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [segId])

  const doSearch = async (p: number, query = q, src = source) => {
    setLoading(true)
    setError(null)
    setNeedsKey(null)
    try {
      const j = await apiGet<{ candidates: SearchCandidate[] }>(
        `/api/search?source=${src}&kind=${kind}&q=${encodeURIComponent(query)}&page=${p}`,
      )
      setCands((prev) => (p > 1 ? [...prev, ...j.candidates] : j.candidates))
      if (!j.candidates.length && p === 1) setError('没有结果，换个关键词（英文）试试。')
      setPage(p)
    } catch (e) {
      if (e instanceof ApiError && typeof e.data.needs_key === 'string') {
        setNeedsKey(e.data.needs_key)
      } else {
        setError(e instanceof Error ? e.message : String(e))
      }
    }
    setLoading(false)
  }

  const switchToFreeSource = () => {
    const free = DEFAULT_SOURCE[kind]
    setSource(free)
    doSearch(1, q, free)
  }

  const addCandidate = async (c: SearchCandidate, ranges: TrimRange[] | null) => {
    setAdding(true)
    try {
      const j = await apiPost<{ path: string; credit: string; duration: number | null; kind: string }>('/api/assets/fetch', {
        candidate: c,
      })
      patch((raw) => {
        const s = raw.segments.find((x) => x.id === segId)
        if (!s) return
        if (j.kind === 'video' && ranges) {
          for (const r of ranges) s.clips.push({ video: j.path, in: +r.in.toFixed(2), out: +(r.out ?? r.in).toFixed(2), credit: j.credit })
        } else {
          s.clips.push({ image: j.path, motion: 'zoom_in', credit: j.credit })
        }
      })
      if (await saveNow()) onAdded()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
    setAdding(false)
  }

  const clickCandidate = (c: SearchCandidate) => {
    if (adding) return
    if (c.kind === 'video') {
      setTrimming(c)
      return
    }
    if (/版权未知/.test(c.license || '')) {
      if (!window.confirm(`这张图来自网页，版权未知：\n${c.page_url}\n\n用于变现视频可能收到版权投诉。确定加入？（来源会记入 credits.txt）`)) return
    }
    addCandidate(c, null)
  }

  return (
    <Stack spacing={1.5}>
      <Stack direction="row" spacing={1}>
        <TextField
          select
          size="small"
          label="来源"
          value={source}
          onChange={(e) => {
            setSource(e.target.value)
            doSearch(1, q, e.target.value)
          }}
          sx={{ minWidth: 260 }}
        >
          {sources.map((s) => (
            <MenuItem key={s.value} value={s.value}>
              {s.label}
            </MenuItem>
          ))}
        </TextField>
        <TextField
          size="small"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && doSearch(1)}
          placeholder="英文关键词效果最好"
          fullWidth
        />
        <Button variant="contained" onClick={() => doSearch(1)}>
          搜索
        </Button>
      </Stack>
      {!!keywords.length && (
        <Stack direction="row" spacing={0.5} alignItems="center" flexWrap="wrap" useFlexGap>
          <Typography variant="caption" color="text.secondary">
            建议：
          </Typography>
          {keywords.map((k) => (
            <Chip
              key={k}
              label={k}
              size="small"
              onClick={() => {
                setQ(k)
                doSearch(1, k)
              }}
            />
          ))}
        </Stack>
      )}
      {error && (
        <Typography variant="body2" color="error">
          {error}
        </Typography>
      )}
      {needsKey && (
        <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap sx={{ p: 1, bgcolor: 'action.hover', borderRadius: 2 }}>
          <Typography variant="body2" color="error">
            缺 {needsKey}：项目文件夹里建个 .env 文件写一行 {needsKey}=你的key（或去左侧"系统状态"里直接粘贴保存）。
          </Typography>
          {KEY_SIGNUP_URL[needsKey] && (
            <Link href={KEY_SIGNUP_URL[needsKey]} target="_blank" rel="noreferrer" variant="body2">
              去免费申请…
            </Link>
          )}
          <Button size="small" variant="outlined" onClick={switchToFreeSource}>
            先换成{kind === 'video' ? ' Internet Archive' : ' Wikimedia Commons'}（不需要 key）
          </Button>
        </Stack>
      )}
      <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))', gap: 1 }}>
        {cands.map((c, i) => (
          <Box
            key={`${c.provider}-${c.id}-${i}`}
            onClick={() => clickCandidate(c)}
            title={`${c.title || ''} · ${c.author} · ${c.license}`}
            sx={{ cursor: adding ? 'default' : 'pointer', border: '1px solid', borderColor: 'divider', borderRadius: 2, overflow: 'hidden' }}
          >
            <Box sx={{ height: 90, bgcolor: 'action.hover' }}>
              <img src={c.thumb_url} alt="" loading="lazy" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
            </Box>
            <Stack direction="row" justifyContent="space-between" sx={{ px: 0.5 }}>
              <Typography variant="caption" noWrap sx={{ maxWidth: '60%' }}>
                {c.author || c.title}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                {c.kind === 'video' ? fmtDuration(c.duration) : `${c.width}×${c.height}`}
              </Typography>
            </Stack>
          </Box>
        ))}
      </Box>
      {loading && (
        <Typography variant="body2" color="text.secondary">
          搜索中…
        </Typography>
      )}
      {!!cands.length && (
        <Button size="small" onClick={() => doSearch(page + 1)} sx={{ alignSelf: 'center' }}>
          更多结果
        </Button>
      )}
      {trimming && (
        <TrimDialog
          open
          url={trimming.preview_url}
          duration={trimming.duration}
          ranges={[{ in: 0, out: Math.min(trimming.duration || 10, Math.max(3, Math.ceil((view?.resolved[segId]?.need || 8) - segFixed))) }]}
          onClose={() => setTrimming(null)}
          onDone={(ranges) => {
            const c = trimming
            setTrimming(null)
            addCandidate(c, ranges)
          }}
        />
      )}
    </Stack>
  )
}
