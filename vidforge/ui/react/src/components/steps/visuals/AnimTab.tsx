import { useState } from 'react'
import { Alert, Box, Button, Divider, MenuItem, Select, Stack, TextField, Typography } from '@mui/material'
import { apiGet, apiPost } from '../../../api/client'
import type { Segment } from '../../../api/types'
import { useProject } from '../../../state/ProjectContext'

const COMPOSITIONS = ['TitleCard', 'Timeline', 'BarChart'] as const

const CHARTS = [
  { id: 'line', label: '折线（看趋势）' },
  { id: 'bar', label: '横条（看排名）' },
  { id: 'big', label: '大数字（开场钩子）' },
  { id: 'compare', label: '对比（两方）' },
] as const

type Indicator = { id: string; name: string }
type ChartReply = { composition: string; props: Record<string, unknown>; source: string; labels: string[] }

const DEFAULT_PROPS: Record<(typeof COMPOSITIONS)[number], Record<string, unknown>> = {
  TitleCard: { title: '', subtitle: '' },
  Timeline: {
    title: '',
    events: [
      { date: '1815', text: '…' },
      { date: '1816', text: '…' },
    ],
  },
  BarChart: {
    title: '',
    items: [
      { label: 'A', value: 3 },
      { label: 'B', value: 5 },
    ],
  },
}

export function AnimTab({ seg, segId }: { seg: Segment; segId: string }) {
  const { patch } = useProject()
  const [q, setQ] = useState('')
  const [hits, setHits] = useState<Indicator[]>([])
  const [indicator, setIndicator] = useState('')
  const [countries, setCountries] = useState('CHN,USA')
  const [chart, setChart] = useState<(typeof CHARTS)[number]['id']>('line')
  const [years, setYears] = useState('2000-')
  const [preview, setPreview] = useState<ChartReply | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const find = async () => {
    setError(null)
    setBusy(true)
    try {
      const j = await apiGet<{ indicators: Indicator[] }>(`/api/data/search?q=${encodeURIComponent(q)}`)
      setHits(j.indicators)
      if (j.indicators.length && !indicator) setIndicator(j.indicators[0].id)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
    setBusy(false)
  }

  const build = async () => {
    setError(null)
    setBusy(true)
    try {
      const [start, end] = years.split(/[-~～]/).map((v) => parseInt(v.trim(), 10))
      const j = await apiPost<ChartReply>('/api/data/chart', {
        indicator,
        countries: countries.replace(/，/g, ',').split(',').map((c) => c.trim()).filter(Boolean),
        chart,
        start: Number.isFinite(start) ? start : null,
        end: Number.isFinite(end) ? end : null,
      })
      setPreview(j)
    } catch (e) {
      setPreview(null)
      setError(e instanceof Error ? e.message : String(e))
    }
    setBusy(false)
  }

  const addChart = () => {
    if (!preview) return
    patch((raw) => {
      const s2 = raw.segments.find((x) => x.id === segId)
      if (s2) s2.clips.push({ remotion: { composition: preview.composition, props: preview.props } })
    })
    setPreview(null)
  }

  const add = (composition: (typeof COMPOSITIONS)[number]) => {
    const defaults = { ...DEFAULT_PROPS[composition] }
    if (composition === 'TitleCard') defaults.title = seg.label || seg.id
    patch((raw) => {
      const s = raw.segments.find((x) => x.id === segId)
      if (s) s.clips.push({ remotion: { composition, props: defaults } })
    })
  }

  return (
    <Stack spacing={1}>
      <Typography variant="caption" color="text.secondary">
        动画段：时长自动等于它在本段的份额。TitleCard：章节标题卡 · Timeline：时间轴逐条出现 · BarChart：动画柱状对比。加入后点片段上的「编辑」改文字。
      </Typography>
      <Stack direction="row" spacing={1}>
        {COMPOSITIONS.map((c) => (
          <Button key={c} variant="outlined" onClick={() => add(c)}>
            ＋ {c}
          </Button>
        ))}
      </Stack>
    
      <Divider sx={{ my: 1 }} />
      <Typography variant="subtitle2">📊 用真实数据做图（世界银行公开数据，免 key）</Typography>
      <Typography variant="caption" color="text.secondary">
        选指标和国家，直接生成带「数据来源」角标的图表段。GDP、人口、城镇化、能源、债务、军费等约一万六千个指标。
      </Typography>
      <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
        <TextField
          size="small"
          label="找指标"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && find()}
          placeholder="人口 / GDP / energy"
          sx={{ width: 180 }}
        />
        <Button size="small" onClick={find} disabled={busy}>
          搜索
        </Button>
        <Select
          size="small"
          value={indicator}
          displayEmpty
          onChange={(e) => setIndicator(e.target.value)}
          sx={{ minWidth: 260, fontSize: 13 }}
        >
          <MenuItem value="">选一个指标…</MenuItem>
          {hits.map((h) => (
            <MenuItem key={h.id} value={h.id} sx={{ fontSize: 13 }}>
              {h.name}（{h.id}）
            </MenuItem>
          ))}
        </Select>
      </Stack>
      <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
        <TextField size="small" label="国家（ISO3）" value={countries} onChange={(e) => setCountries(e.target.value)} sx={{ width: 170 }} />
        <TextField size="small" label="年份区间" value={years} onChange={(e) => setYears(e.target.value)} sx={{ width: 130 }} />
        <Select size="small" value={chart} onChange={(e) => setChart(e.target.value as typeof chart)} sx={{ minWidth: 170, fontSize: 13 }}>
          {CHARTS.map((c) => (
            <MenuItem key={c.id} value={c.id} sx={{ fontSize: 13 }}>
              {c.label}
            </MenuItem>
          ))}
        </Select>
        <Button size="small" variant="outlined" onClick={build} disabled={!indicator || busy}>
          取数据
        </Button>
      </Stack>
      {error && <Alert severity="warning">{error}</Alert>}
      {preview && (
        <Box sx={{ p: 1, bgcolor: 'action.hover', borderRadius: 1 }}>
          <Typography variant="caption" sx={{ display: 'block' }}>
            {preview.composition} · {preview.labels.join(' / ')} · {preview.source}
          </Typography>
          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', fontFamily: 'monospace', fontSize: 11 }}>
            {JSON.stringify(preview.props).slice(0, 220)}…
          </Typography>
          <Button size="small" variant="contained" sx={{ mt: 1 }} onClick={addChart}>
            ＋ 加入这一段
          </Button>
        </Box>
      )}
    </Stack>
  )
}
