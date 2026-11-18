import { useEffect, useRef, useState } from 'react'
import { Alert, Box, Button, ButtonBase, CircularProgress, LinearProgress, Popover, Snackbar, Stack, Typography } from '@mui/material'
import CloudUploadIcon from '@mui/icons-material/CloudUpload'
import MovieIcon from '@mui/icons-material/Movie'
import { apiGet } from '../../api/client'
import type { BuildStatus } from '../../api/types'
import { useProject } from '../../state/ProjectContext'
import { onTakeSaved, useSaveQueue } from '../../state/saveQueue'
import { fmtDuration } from '../../utils'
import { SaveQueueList } from '../shared/SaveQueueList'

/**
 * What is running in the background, visible from every page: takes on their way into the
 * project, and the render. Both used to be watched only by the page that started them — leave
 * the render step and a finished video went unannounced, the project unreloaded.
 */
export function BackgroundJobs({ onStep }: { onStep: (n: number) => void }) {
  const { reload, raw } = useProject()
  const jobs = useSaveQueue()
  const [anchor, setAnchor] = useState<HTMLElement | null>(null)
  const [build, setBuild] = useState<BuildStatus | null>(null)
  const [toast, setToast] = useState<{ ok: boolean; text: string } | null>(null)
  const sawRunning = useRef(false)

  // every take that lands changes project.json on the server: the page picks it up
  useEffect(() => onTakeSaved(() => void reload()), [reload])

  useEffect(() => {
    if (!raw) return
    let stop = false
    let t: ReturnType<typeof setTimeout>
    const poll = async () => {
      const st = await apiGet<BuildStatus>('/api/build/status').catch(() => null)
      if (stop) return
      if (st) {
        setBuild(st)
        if (st.state === 'running') sawRunning.current = true
        else if (sawRunning.current) {
          sawRunning.current = false
          if (st.state === 'done') {
            setToast({ ok: true, text: `渲染完成，用时 ${fmtDuration(st.elapsed)}` })
            void reload()
          } else if (st.state === 'error') setToast({ ok: false, text: `渲染失败：${st.error || ''}` })
        }
      }
      // a render is followed closely; otherwise just often enough to notice one started elsewhere
      t = setTimeout(poll, st?.state === 'running' ? 1500 : 5000)
    }
    poll()
    return () => {
      stop = true
      clearTimeout(t)
    }
  }, [raw ? 1 : 0, reload]) // eslint-disable-line react-hooks/exhaustive-deps

  const active = jobs.filter((j) => j.status === 'waiting' || j.status === 'saving').length
  const failed = jobs.filter((j) => j.status === 'error').length
  const rendering = build?.state === 'running'

  return (
    <>
      {rendering && (
        <ButtonBase onClick={() => onStep(4)} sx={{ borderRadius: 2, px: 1, py: 0.5, '&:hover': { bgcolor: 'action.hover' } }}>
          <Stack spacing={0.25} sx={{ width: 150 }}>
            <Stack direction="row" spacing={0.5} alignItems="center">
              <MovieIcon sx={{ fontSize: 15 }} color="warning" />
              <Typography variant="caption" fontWeight={700}>
                渲染 {Math.round(build?.progress || 0)}%
              </Typography>
              <Typography variant="caption" color="text.secondary">
                {build?.eta ? `约 ${fmtDuration(build.eta)}` : ''}
              </Typography>
            </Stack>
            <LinearProgress variant="determinate" value={build?.progress || 0} sx={{ height: 3, borderRadius: 2 }} />
          </Stack>
        </ButtonBase>
      )}
      {(active > 0 || failed > 0 || jobs.length > 0) && (
        <ButtonBase onClick={(e) => setAnchor(e.currentTarget)} sx={{ borderRadius: 2, px: 1, py: 0.5, '&:hover': { bgcolor: 'action.hover' } }}>
          <Stack direction="row" spacing={0.5} alignItems="center">
            {active > 0 ? <CircularProgress size={13} /> : <CloudUploadIcon sx={{ fontSize: 16 }} color={failed ? 'error' : 'success'} />}
            <Typography variant="caption" fontWeight={700} color={failed ? 'error.main' : 'text.primary'}>
              {failed ? `${failed} 条没存上` : active ? `保存录像 ${active}` : '录像已保存'}
            </Typography>
          </Stack>
        </ButtonBase>
      )}
      <Popover open={!!anchor} anchorEl={anchor} onClose={() => setAnchor(null)} anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }} transformOrigin={{ vertical: 'top', horizontal: 'right' }}>
        <Box sx={{ p: 1, width: 420 }}>
          <SaveQueueList max={12} sx={{ border: 0 }} />
        </Box>
      </Popover>
      <Snackbar open={!!toast} autoHideDuration={8000} onClose={() => setToast(null)} anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}>
        <Alert
          severity={toast?.ok ? 'success' : 'error'}
          variant="filled"
          onClose={() => setToast(null)}
          action={
            toast?.ok ? (
              <Button color="inherit" size="small" onClick={() => (setToast(null), onStep(5))}>
                看成片
              </Button>
            ) : undefined
          }
        >
          {toast?.text}
        </Alert>
      </Snackbar>
    </>
  )
}
