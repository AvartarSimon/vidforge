import { useEffect, useMemo, useState } from 'react'
import { Alert, Box, Button, Card, CardContent, FormControlLabel, LinearProgress, MenuItem, Slider, Stack, Switch, TextField, Typography } from '@mui/material'
import { apiPost } from '../../../api/client'
import { useProject } from '../../../state/ProjectContext'
import { fileUrl } from '../../../utils'
import ContentCutIcon from '@mui/icons-material/ContentCut'
import { PanelTitle } from '../../shared/ui'

type Plan = { total: number; kept: number; removed: number; cuts: number; keep: [number, number][]; fillers?: { word: string; start: number; end: number }[]; fillers_unsure?: number }

/** 智能剪口播: cut the pauses out of a talking-head take, picture and voice together. */
export function JumpCut() {
  const { raw, reload } = useProject()
  const [video, setVideo] = useState('')
  const [threshold, setThreshold] = useState(-38)
  const [minGap, setMinGap] = useState(0.45)
  const [pad, setPad] = useState(0.12)
  const [replace, setReplace] = useState(true)
  const [fillers, setFillers] = useState(false)
  const [plan, setPlan] = useState<Plan | null>(null)
  const [busy, setBusy] = useState(false)
  const [status, setStatus] = useState('')
  const [error, setError] = useState<string | null>(null)

  const videos = useMemo(() => {
    const out = new Set<string>()
    for (const s of raw?.segments || []) {
      for (const c of [...s.clips, ...(s.overlays || [])]) if (typeof c.video === 'string') out.add(c.video)
      if (s.narration && /\.(mp4|mov|webm|mkv|m4v)$/i.test(s.narration)) out.add(s.narration)
    }
    return [...out]
  }, [raw])

  // re-plan as the sliders move, so the bar answers "what will this cut" before anything is written
  useEffect(() => {
    if (!video) return setPlan(null)
    const t = setTimeout(() => {
      apiPost<Plan>('/api/video/jumpcut/plan', { video, threshold, min_gap: minGap, pad, fillers })
        .then((p) => {
          setPlan(p)
          setError(null)
        })
        .catch((e) => setError(e instanceof Error ? e.message : String(e)))
    }, 350)
    return () => clearTimeout(t)
  }, [video, threshold, minGap, pad, fillers])

  const apply = async () => {
    setBusy(true)
    setStatus('')
    setError(null)
    try {
      const r = await apiPost<Plan & { path: string; replaced: string[] }>('/api/video/jumpcut', { video, threshold, min_gap: minGap, pad, fillers, replace })
      await reload()
      setStatus(`剪掉 ${r.removed.toFixed(1)} 秒（${r.cuts} 处${r.fillers?.length ? `，含语气词 ${r.fillers.length} 个` : ''}），${r.total.toFixed(1)}s → ${r.kept.toFixed(1)}s。${r.replaced.length ? `已替换 ${r.replaced.length} 段的画面和旁白。` : `新文件：${r.path}`}`)
      setVideo(r.path)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
    setBusy(false)
  }

  return (
    <Card variant="outlined">
      <CardContent>
        <PanelTitle icon={<ContentCutIcon />} tone="violet" mb={1} title={<>智能剪口播</>} />
        <Typography variant="body2" color="text.secondary" gutterBottom>
          自动剪掉说话中间的停顿和气口。画面和声音按同一组切点一起剪，口型不会错位；原文件不动，生成一个 _cut.mp4。
        </Typography>
        <TextField size="small" select label="选视频" value={video} onChange={(e) => setVideo(e.target.value)} sx={{ minWidth: 320, my: 1.5 }}>
          {videos.length === 0 && <MenuItem disabled>项目里还没有视频（先在录制棚录一条）</MenuItem>}
          {videos.map((v) => (
            <MenuItem key={v} value={v}>
              {v.split('/').pop()}
            </MenuItem>
          ))}
        </TextField>
        <Stack direction={{ xs: 'column', md: 'row' }} spacing={3}>
          <Box sx={{ flex: 1 }}>
            <Typography variant="caption" color="text.secondary">
              静音阈值 {threshold} dB（房间吵就调高到 -32）
            </Typography>
            <Slider size="small" min={-55} max={-25} value={threshold} onChange={(_, v) => setThreshold(v as number)} />
          </Box>
          <Box sx={{ flex: 1 }}>
            <Typography variant="caption" color="text.secondary">
              只剪长于 {minGap.toFixed(2)} 秒的停顿
            </Typography>
            <Slider size="small" min={0.2} max={2} step={0.05} value={minGap} onChange={(_, v) => setMinGap(v as number)} />
          </Box>
          <Box sx={{ flex: 1 }}>
            <Typography variant="caption" color="text.secondary">
              切点两边各留 {pad.toFixed(2)} 秒
            </Typography>
            <Slider size="small" min={0} max={0.4} step={0.01} value={pad} onChange={(_, v) => setPad(v as number)} />
          </Box>
        </Stack>
        {plan && (
          <Box sx={{ mt: 1 }}>
            {/* kept speech in colour, what goes in grey — the whole take to scale */}
            <Box sx={{ position: 'relative', height: 18, bgcolor: 'action.disabledBackground', borderRadius: 1, overflow: 'hidden' }}>
              {plan.keep.map(([a, b], i) => (
                <Box key={i} sx={{ position: 'absolute', top: 0, bottom: 0, left: `${(a / plan.total) * 100}%`, width: `${((b - a) / plan.total) * 100}%`, bgcolor: 'primary.main' }} />
              ))}
              {plan.fillers?.map((f, i) => (
                <Box key={`f${i}`} title={f.word} sx={{ position: 'absolute', top: 0, bottom: 0, left: `${(f.start / plan.total) * 100}%`, width: `${Math.max(0.4, ((f.end - f.start) / plan.total) * 100)}%`, bgcolor: 'warning.main' }} />
              ))}
            </Box>
            <Typography variant="caption" color="text.secondary">
              {plan.total.toFixed(1)}s → {plan.kept.toFixed(1)}s，剪掉 {plan.removed.toFixed(1)} 秒（{plan.cuts} 处）
              {plan.fillers && `；语气词 ${plan.fillers.length} 个（橙色）`}
              {!!plan.fillers_unsure && `，另有 ${plan.fillers_unsure} 个贴着别的字，不剪`}
            </Typography>
          </Box>
        )}
        <Stack direction="row" spacing={2} alignItems="center" sx={{ mt: 1.5 }}>
          <Button variant="contained" onClick={apply} disabled={!video || busy || !plan || plan.removed < 0.05}>
            剪
          </Button>
          <FormControlLabel
            control={<Switch size="small" checked={fillers} onChange={(e) => setFillers(e.target.checked)} />}
            label={<Typography variant="body2">也剪掉「嗯」「呃」（第一次要听几秒）</Typography>}
          />
          <FormControlLabel control={<Switch size="small" checked={replace} onChange={(e) => setReplace(e.target.checked)} />} label={<Typography variant="body2">替换项目里用到它的段落</Typography>} />
          {video && (
            <Button size="small" href={fileUrl(video) || ""} target="_blank">
              看原片
            </Button>
          )}
        </Stack>
        {busy && <LinearProgress sx={{ mt: 1 }} />}
        {status && (
          <Alert severity="success" sx={{ mt: 1 }}>
            {status}
          </Alert>
        )}
        {error && (
          <Alert severity="warning" sx={{ mt: 1 }}>
            {error}
          </Alert>
        )}
      </CardContent>
    </Card>
  )
}
