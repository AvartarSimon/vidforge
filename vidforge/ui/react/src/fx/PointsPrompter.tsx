import { Box, Typography } from '@mui/material'
import type { PrompterPlace } from './Teleprompter'

/** The script's own sentences — the points when none were written or condensed (points.sentences). */
export function sentencePoints(text: string): string[] {
  return text
    .split(/(?<=[。！？!?；;])\s*/)
    .map((p) => p.trim().replace(/^[，,、]+|[，,、]+$/g, ''))
    .filter(Boolean)
    .slice(0, 12)
}

/**
 * 要点模式的提词器: the points to make, still, a glance each — nothing scrolls, because nobody is
 * reading along. Above the picture in its own line (eyes near the lens) or laid over it.
 */
export function PointsPrompter({ points, fontSize, mirror, place }: { points: string[]; fontSize: number; mirror: boolean; place: PrompterPlace | 'full' }) {
  const above = place === 'line'
  const size = Math.round(fontSize * (above ? 0.7 : 0.8))
  const list = (
    <Box component="ol" sx={{ m: 0, pl: 3, transform: mirror ? 'scaleX(-1)' : undefined }}>
      {points.map((p, i) => (
        <Typography key={i} component="li" sx={{ fontSize: size, fontWeight: 700, lineHeight: 1.35, color: above ? 'text.primary' : '#fff', textShadow: above ? undefined : '0 2px 6px #000' }}>
          {p}
        </Typography>
      ))}
    </Box>
  )
  if (above) {
    return <Box sx={{ mb: 1, p: 1.5, borderRadius: 2, bgcolor: 'action.hover', maxHeight: '28vh', overflow: 'auto' }}>{list}</Box>
  }
  return (
    <Box
      sx={{
        position: 'absolute',
        left: 16,
        right: 16,
        ...(place === 'bottom' ? { bottom: 56 } : { top: 16 }),
        p: 1.5,
        borderRadius: 2,
        bgcolor: 'rgba(0,0,0,.45)',
        maxHeight: place === 'full' ? 'calc(100% - 32px)' : '45%',
        overflow: 'auto',
        pointerEvents: 'none',
      }}
    >
      {list}
    </Box>
  )
}
