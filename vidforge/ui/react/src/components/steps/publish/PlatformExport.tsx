import { useEffect, useRef, useState } from 'react'
import { Alert, Box, Button, Card, CardContent, Checkbox, Chip, IconButton, LinearProgress, Stack, ToggleButton, ToggleButtonGroup, Tooltip, Typography } from '@mui/material'
import ContentCopyIcon from '@mui/icons-material/ContentCopy'
import { apiGet, apiPost } from '../../../api/client'
import { downloadUrl, fileUrl } from '../../../utils'
import { useProject } from '../../../state/ProjectContext'
import IosShareIcon from '@mui/icons-material/IosShare'
import { PanelTitle } from '../../shared/ui'

type Platform = { id: string; name: string; ratio: string; width: number; height: number; best: number[]; max_seconds: number | null; tips: string }
type Exported = { id: string; name: string; path: string; seconds: number; mb: number; warnings: string[]; copy?: string; covers?: string[]; mtime?: number }
type Job = { state: string; lines: string[]; results: Exported[]; error: string | null }

const KEY = 'vf.platforms.v1'

/** 多平台导出: one finished video, a correctly shaped copy and the upload text for each app. */
export function PlatformExport() {
  const { raw } = useProject()
  const [list, setList] = useState<Platform[]>([])
  const [done, setDone] = useState<Exported[]>([])
  const [job, setJob] = useState<Job | null>(null)
  const [chosen, setChosen] = useState<string[]>(() => {
    try {
      return JSON.parse(localStorage.getItem(KEY) || '["douyin","kuaishou","toutiao","youtube"]')
    } catch {
      return ['douyin', 'kuaishou', 'toutiao', 'youtube']
    }
  })
  const [mode, setMode] = useState<'blur' | 'crop'>('blur')
  const [error, setError] = useState<string | null>(null)
  const timer = useRef<ReturnType<typeof setInterval> | null>(null)

  const load = () =>
    apiGet<{ platforms: Platform[]; exported: Exported[]; job: Job }>('/api/platforms').then((j) => {
      setList(j.platforms)
      setDone(j.exported)
      setJob(j.job)
      return j.job
    })

  // An export runs for minutes. The page used to poll only from the click, so leaving and coming
  // back found it "导出中…" for good — the job had finished, nobody asked. Polling now follows
  // the job's state, whoever started it.
  const poll = () => {
    if (timer.current) return
    timer.current = setInterval(async () => {
      try {
        const j = await load()
        if (j.state !== 'running' && timer.current) {
          clearInterval(timer.current)
          timer.current = null
        }
      } catch {
        // the server restarted mid-export: try again on the next tick
      }
    }, 1200)
  }

  useEffect(() => {
    load()
      .then((j) => j.state === 'running' && poll())
      .catch((e) => setError(String(e)))
    return () => {
      if (timer.current) clearInterval(timer.current)
    }
  }, [])
  useEffect(() => {
    try {
      localStorage.setItem(KEY, JSON.stringify(chosen))
    } catch {
      // ignore
    }
  }, [chosen])

  const start = async () => {
    setError(null)
    try {
      await apiPost('/api/platforms/export', { platforms: chosen, mode })
      await load()
      poll()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  const running = job?.state === 'running'
  const toggle = (id: string) => setChosen((c) => (c.includes(id) ? c.filter((x) => x !== id) : [...c, id]))

  return (
    <Card variant="outlined">
      <CardContent>
        <PanelTitle icon={<IosShareIcon />} tone="orange" mb={1} title={<>多平台导出</>} />
        <Typography variant="body2" color="text.secondary" gutterBottom>
          一条成片，给每个平台导出正确的画幅和码率，并生成可以直接粘贴的标题 / 简介 / 话题 / AI 声明。横版成片转竖版时不用重新渲染。
        </Typography>
        <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', sm: '1fr 1fr', lg: 'repeat(4, 1fr)' }, gap: 1, my: 1.5 }}>
          {list.map((p) => (
            <Box
              key={p.id}
              onClick={() => toggle(p.id)}
              sx={{ p: 1.25, borderRadius: 1.5, border: '1px solid', borderColor: chosen.includes(p.id) ? 'primary.main' : 'divider', cursor: 'pointer', bgcolor: chosen.includes(p.id) ? 'action.selected' : 'transparent' }}
            >
              <Stack direction="row" alignItems="center" spacing={0.5}>
                <Checkbox size="small" checked={chosen.includes(p.id)} sx={{ p: 0.25 }} />
                <Typography variant="body2" fontWeight={600}>
                  {p.name}
                </Typography>
                <Chip size="small" label={p.ratio} sx={{ ml: 'auto', height: 20 }} />
              </Stack>
              <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5 }}>
                {p.width}×{p.height} · 常见 {p.best[0]}–{p.best[1]} 秒{p.max_seconds ? ` · 最长 ${Math.round(p.max_seconds / 60)} 分钟` : ''}
              </Typography>
            </Box>
          ))}
        </Box>
        <Stack direction="row" spacing={2} alignItems="center" flexWrap="wrap" useFlexGap>
          <ToggleButtonGroup size="small" exclusive value={mode} onChange={(_, v) => v && setMode(v)}>
            <Tooltip title="整个画面保留，上下用模糊的放大画面填满——图表和文字不会被切掉">
              <ToggleButton value="blur">横转竖：保留全画面</ToggleButton>
            </Tooltip>
            <Tooltip title="从中间裁满屏——适合人像，图表两边会被切掉">
              <ToggleButton value="crop">横转竖：裁满屏</ToggleButton>
            </Tooltip>
          </ToggleButtonGroup>
          <Button variant="contained" onClick={start} disabled={running || !chosen.length}>
            {running ? '导出中…' : `导出 ${chosen.length} 个平台`}
          </Button>
        </Stack>
        {running && (
          <Box sx={{ mt: 1 }}>
            <LinearProgress />
            <Typography variant="caption" color="text.secondary">
              {job?.lines.slice(-1)[0]}
            </Typography>
          </Box>
        )}
        {(error || job?.error) && (
          <Alert severity="warning" sx={{ mt: 1 }}>
            {error || job?.error}
          </Alert>
        )}
        {done.length > 0 && (
          <Stack spacing={1} sx={{ mt: 2 }}>
            {done.map((d) => (
              <Box key={d.id} sx={{ p: 1.25, borderRadius: 1.5, border: '1px solid', borderColor: 'divider' }}>
                <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                  <Typography variant="body2" fontWeight={600} sx={{ minWidth: 110 }}>
                    {d.name}
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    {d.seconds.toFixed(1)}s · {d.mb} MB
                  </Typography>
                  <Button size="small" href={fileUrl(d.path, d.mtime) || ''} target="_blank">
                    播放
                  </Button>
                  <Button size="small" href={downloadUrl(d.path, `${raw?.title || 'video'}-${d.name}.mp4`, d.mtime) || ''}>
                    下载
                  </Button>
                  {d.copy && (
                    <Tooltip title="复制标题/简介/话题/AI 声明">
                      <IconButton size="small" onClick={() => navigator.clipboard?.writeText(d.copy || '')}>
                        <ContentCopyIcon fontSize="inherit" />
                      </IconButton>
                    </Tooltip>
                  )}
                </Stack>
                {!!d.covers?.length && (
                  <Stack direction="row" spacing={1} alignItems="flex-end" sx={{ mt: 1 }}>
                    {d.covers.map((c) => (
                      <Tooltip key={c} title={`封面 ${c.split('_cover_').pop()?.replace('.jpg', '')}，点一下下载`}>
                        <Box component="a" href={downloadUrl(c, `${raw?.title || 'video'}-${d.name}-${c.split('_cover_').pop()}`, d.mtime) || ''} sx={{ display: 'block', lineHeight: 0 }}>
                          <Box component="img" src={fileUrl(c, d.mtime) || ''} alt="封面" sx={{ height: 72, borderRadius: 0.5, border: '1px solid', borderColor: 'divider' }} />
                        </Box>
                      </Tooltip>
                    ))}
                  </Stack>
                )}
                {d.warnings.map((w) => (
                  <Typography key={w} variant="caption" color="warning.main" sx={{ display: 'block' }}>
                    ⚠ {w}
                  </Typography>
                ))}
              </Box>
            ))}
          </Stack>
        )}
      </CardContent>
    </Card>
  )
}
