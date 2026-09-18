import { useEffect, useRef, useState } from 'react'
import { Box, Button, Card, CardContent, Chip, LinearProgress, Stack, Typography } from '@mui/material'
import { apiGet, apiPost } from '../../../api/client'
import type { BuildStatus } from '../../../api/types'
import { useProject } from '../../../state/ProjectContext'
import { fmtDuration } from '../../../utils'

const STATE_LABEL: Record<string, string> = { idle: '空闲', running: '渲染中', done: '完成', error: '失败', cancelled: '已停止' }
const STATE_COLOR: Record<string, 'default' | 'warning' | 'success' | 'error'> = {
  running: 'warning',
  done: 'success',
  error: 'error',
  cancelled: 'warning',
}
const PHASE_LABEL: Record<string, string> = { tts: '配音', assets: '取素材', remotion: '动画', render: '渲染', assemble: '合成' }

// colour/label per log line, same classification as the old frontend's logLine() (app.js)
function logLineClass(l: string): { emoji: string; text: string; color: string } {
  const t = l.replace(/^\[vidforge\] /, '')
  if (/^ERROR/.test(l) || /ERROR:/.test(l)) return { emoji: '✖', text: t, color: '#d14343' }
  if (/warning:/.test(l)) return { emoji: '⚠', text: t, color: '#b7791f' }
  if (/^\[vidforge\]\s+tts /.test(l)) return { emoji: '🎙', text: t.replace(/^tts\s+/, ''), color: '#888' }
  if (/^\[vidforge\]\s+asset /.test(l)) return { emoji: '🖼', text: t.replace(/^asset\s+/, ''), color: '#888' }
  if (/\[remotion\]/.test(l)) return { emoji: '✨', text: t.replace('[remotion] ', ''), color: '#888' }
  if (/^\[vidforge\]\s+clip /.test(l)) return { emoji: '🎬', text: t.replace(/^clip\s+/, ''), color: '#2a9d8f' }
  if (/^\[vidforge\] done in/.test(l)) return { emoji: '✔', text: t.replace('done in', '用时'), color: '#2a9d8f' }
  return { emoji: '', text: t, color: '#888' }
}

export function BuildPanel({ onFinished }: { onFinished: () => void }) {
  const { saveNow } = useProject()
  const [status, setStatus] = useState<BuildStatus | null>(null)
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const reloadedRef = useRef(false)

  const poll = async () => {
    const st = await apiGet<BuildStatus>('/api/build/status').catch(() => null)
    if (!st) return
    setStatus(st)
    if (st.state === 'running') {
      timer.current = setTimeout(poll, 1000)
    } else if (st.finished && Date.now() / 1000 - st.finished < 4 && !reloadedRef.current) {
      reloadedRef.current = true
      onFinished()
      setTimeout(() => (reloadedRef.current = false), 5000)
    }
  }

  useEffect(() => {
    poll()
    return () => {
      if (timer.current) clearTimeout(timer.current)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const build = async () => {
    if (!(await saveNow())) return
    try {
      await apiPost('/api/build', {})
    } catch (e) {
      window.alert(e instanceof Error ? e.message : String(e))
      return
    }
    poll()
  }

  const cancel = () => apiPost('/api/build/cancel', {})

  const running = status?.state === 'running'

  return (
    <Card variant="outlined">
      <CardContent>
        <Stack direction="row" spacing={1.5} alignItems="center">
          <Button variant="contained" onClick={build} disabled={running}>
            ▶ 渲染
          </Button>
          {running && (
            <Button onClick={cancel} color="warning">
              停止
            </Button>
          )}
          {status && <Chip size="small" label={STATE_LABEL[status.state]} color={STATE_COLOR[status.state]} />}
          {status?.started && <Typography variant="caption" color="text.secondary">{Math.round(status.elapsed)} s</Typography>}
        </Stack>
        {status && (status.state === 'running' || status.state === 'done') && (
          <Box sx={{ mt: 1.5 }}>
            <LinearProgress variant="determinate" value={status.progress || 0} />
            <Typography variant="caption" color="text.secondary">
              {status.state === 'running'
                ? `${status.progress || 0}% · ${PHASE_LABEL[status.phase] || ''}${
                    status.segments_total ? ` ${status.segments_done}/${status.segments_total} 段` : ''
                  }${status.eta ? ` · 预计还需 ${fmtDuration(status.eta)}` : ''}`
                : '完成'}
            </Typography>
          </Box>
        )}
        {!!status?.lines.length && (
          <Box
            component="pre"
            sx={{
              mt: 1.5,
              maxHeight: 240,
              overflow: 'auto',
              bgcolor: 'action.hover',
              p: 1,
              borderRadius: 1,
              fontSize: 12,
              whiteSpace: 'pre-wrap',
            }}
          >
            {status.lines.map((l, i) => {
              const { emoji, text, color } = logLineClass(l)
              return (
                <div key={i} style={{ color }}>
                  {emoji} {text}
                </div>
              )
            })}
          </Box>
        )}
      </CardContent>
    </Card>
  )
}
