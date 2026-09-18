import { Box, Card, CardContent, Link, Stack, Typography } from '@mui/material'
import { useProject } from '../../../state/ProjectContext'
import { fileUrl } from '../../../utils'

function chaptersText(tl: { start: number; label?: string; id: string }[] | null | undefined) {
  return (tl || [])
    .map((t) => {
      const s = Math.floor(t.start)
      return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')} ${t.label || t.id}`
    })
    .join('\n')
}

export function ResultCard() {
  const { view } = useProject()
  const o = view?.outputs
  if (!o?.final) return null

  const total = o.timeline?.length ? o.timeline[o.timeline.length - 1].end : 0

  return (
    <Card variant="outlined">
      <CardContent>
        <Stack direction="row" justifyContent="space-between">
          <Typography variant="subtitle1" fontWeight={600}>
            成片
          </Typography>
          <Typography variant="caption" color="text.secondary">
            {Math.round(total)} s{o.final_mtime ? ` · ${new Date(o.final_mtime * 1000).toLocaleString()}` : ''}
          </Typography>
        </Stack>
        <video controls playsInline style={{ width: '100%', maxWidth: 640, marginTop: 8 }} src={fileUrl(o.final, o.final_mtime) || undefined} />
        <Stack direction="row" spacing={2} sx={{ mt: 1 }}>
          <Link href={fileUrl(o.final) || '#'} download>
            final.mp4
          </Link>
          <Link href={fileUrl(o.srt) || '#'} download>
            final.srt
          </Link>
          <Link href={fileUrl(o.thumbnail) || '#'} target="_blank" rel="noreferrer">
            thumbnail.jpg
          </Link>
        </Stack>
        <Stack direction="row" spacing={2} sx={{ mt: 1 }}>
          {o.thumbnail && (
            <Box component="img" src={fileUrl(o.thumbnail, o.final_mtime) || undefined} sx={{ width: 200, borderRadius: 1 }} />
          )}
          <Box component="pre" sx={{ fontSize: 12, m: 0 }}>
            {chaptersText(o.timeline)}
          </Box>
        </Stack>
      </CardContent>
    </Card>
  )
}
