import { useState } from 'react'
import { Alert, Box, Button, Card, CardContent, Stack, Typography } from '@mui/material'
import { apiPost } from '../../../api/client'
import { useProject } from '../../../state/ProjectContext'
import { downloadUrl, fileUrl } from '../../../utils'
import MovieIcon from '@mui/icons-material/Movie'
import DownloadIcon from '@mui/icons-material/Download'
import FolderOpenIcon from '@mui/icons-material/FolderOpen'
import { PanelTitle } from '../../shared/ui'

function chaptersText(tl: { start: number; label?: string; id: string }[] | null | undefined) {
  return (tl || [])
    .map((t) => {
      const s = Math.floor(t.start)
      return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')} ${t.label || t.id}`
    })
    .join('\n')
}

/**
 * 成片. Shown at the end of 渲染 and at the top of 发布 (where 导出 lands): the finished video is
 * what "export" means first; the per-platform copies come after. Every link carries the render's
 * mtime — the files keep their names across renders and the browser would hand back the old one.
 */
export function ResultCard() {
  const { raw, view } = useProject()
  const [error, setError] = useState<string | null>(null)
  const o = view?.outputs
  if (!o?.final) return null

  const total = o.timeline?.length ? o.timeline[o.timeline.length - 1].end : 0
  const bust = o.final_mtime
  const title = raw?.title || 'final'
  const reveal = async () => {
    setError(null)
    try {
      await apiPost('/api/reveal', { path: o.final })
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  return (
    <Card variant="outlined">
      <CardContent>
        <Stack direction="row" justifyContent="space-between">
          <PanelTitle icon={<MovieIcon />} tone="violet" mb={0} title={<>成片</>} />
          <Typography variant="caption" color="text.secondary">
            {Math.round(total)} s{o.final_mtime ? ` · ${new Date(o.final_mtime * 1000).toLocaleString()}` : ''}
          </Typography>
        </Stack>
        <video controls playsInline style={{ width: '100%', maxWidth: 640, marginTop: 8 }} src={fileUrl(o.final, bust) || undefined} />
        <Stack direction="row" spacing={1} sx={{ mt: 1 }} flexWrap="wrap" useFlexGap>
          <Button variant="contained" size="small" startIcon={<DownloadIcon />} href={downloadUrl(o.final, `${title}.mp4`, bust) || ''}>
            下载成片
          </Button>
          {o.srt && (
            <Button size="small" startIcon={<DownloadIcon />} href={downloadUrl(o.srt, `${title}.srt`, bust) || ''}>
              字幕 .srt
            </Button>
          )}
          {o.thumbnail && (
            <Button size="small" startIcon={<DownloadIcon />} href={downloadUrl(o.thumbnail, `${title}-封面.jpg`, bust) || ''}>
              封面
            </Button>
          )}
          <Button size="small" startIcon={<FolderOpenIcon />} onClick={reveal}>
            在文件夹中显示
          </Button>
        </Stack>
        {error && (
          <Alert severity="warning" sx={{ mt: 1 }}>
            {error}
          </Alert>
        )}
        <Stack direction="row" spacing={2} sx={{ mt: 1 }}>
          {o.thumbnail && (
            <Box component="img" src={fileUrl(o.thumbnail, bust) || undefined} sx={{ width: 200, borderRadius: 1 }} />
          )}
          <Box component="pre" sx={{ fontSize: 12, m: 0 }}>
            {chaptersText(o.timeline)}
          </Box>
        </Stack>
      </CardContent>
    </Card>
  )
}
