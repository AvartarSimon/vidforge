import { Box, Button, CircularProgress, Stack, Typography } from '@mui/material'
import type { SxProps, Theme } from '@mui/material'
import CheckCircleIcon from '@mui/icons-material/CheckCircle'
import ErrorIcon from '@mui/icons-material/Error'
import ScheduleIcon from '@mui/icons-material/Schedule'
import { clearFinished, dismissTake, retryTake, useSaveQueue } from '../../state/saveQueue'

/** The takes on their way into the project: waiting, saving, done, or failed with 重试. */
export function SaveQueueList({ sx, max = 6 }: { sx?: SxProps<Theme>; max?: number }) {
  const jobs = useSaveQueue()
  if (!jobs.length) return null
  const shown = jobs.slice(-max).reverse()
  const done = jobs.filter((j) => j.status === 'done').length
  return (
    <Box sx={{ border: '1px solid', borderColor: 'divider', borderRadius: 2, p: 1, ...sx }}>
      <Stack direction="row" alignItems="center" sx={{ mb: 0.5 }}>
        <Typography variant="caption" fontWeight={700} color="text.secondary">
          后台保存
        </Typography>
        <Box sx={{ flex: 1 }} />
        {done > 0 && (
          <Button size="small" color="inherit" onClick={clearFinished} sx={{ minWidth: 0, py: 0 }}>
            清掉已完成
          </Button>
        )}
      </Stack>
      <Stack spacing={0.5}>
        {shown.map((j) => (
          <Stack key={j.id} direction="row" spacing={1} alignItems="center">
            {j.status === 'saving' ? (
              <CircularProgress size={14} />
            ) : j.status === 'done' ? (
              <CheckCircleIcon color="success" sx={{ fontSize: 16 }} />
            ) : j.status === 'error' ? (
              <ErrorIcon color="error" sx={{ fontSize: 16 }} />
            ) : (
              <ScheduleIcon color="disabled" sx={{ fontSize: 16 }} />
            )}
            <Typography variant="body2" sx={{ fontWeight: 600, minWidth: 48 }}>
              {j.segId}
            </Typography>
            <Typography variant="caption" color={j.status === 'error' ? 'error.main' : 'text.secondary'} sx={{ flex: 1, minWidth: 0 }} noWrap>
              {j.status === 'waiting'
                ? '排队中'
                : j.status === 'saving'
                  ? j.kind === 'keep'
                    ? '存进录像列表…'
                    : '上传、剪辑中…'
                  : j.status === 'done'
                    ? j.summary
                    : j.error}
            </Typography>
            {j.status === 'error' && (
              <>
                <Button size="small" onClick={() => retryTake(j.id)} sx={{ minWidth: 0, py: 0 }}>
                  重试
                </Button>
                <Button size="small" color="inherit" onClick={() => dismissTake(j.id)} sx={{ minWidth: 0, py: 0 }}>
                  不要了
                </Button>
              </>
            )}
          </Stack>
        ))}
      </Stack>
    </Box>
  )
}
