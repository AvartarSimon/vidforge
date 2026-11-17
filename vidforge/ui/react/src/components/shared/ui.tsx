import type { ReactNode } from 'react'
import { Box, DialogTitle, IconButton, Stack, Typography } from '@mui/material'
import { alpha } from '@mui/material/styles'
import CloseIcon from '@mui/icons-material/Close'

// One colour per area of the app, used for its icon everywhere it appears — the rail, the page
// header, the cards and the pop-ups that belong to it — so a colour tells you where you are
// before the words do (剪映 / CapCut colour their tool icons the same way). Mid-saturation hues
// that read on both the light and the dark workspace.
export const TONES = {
  teal: '#14a3a3',
  coral: '#ef5a4c',
  orange: '#f08a24',
  violet: '#8b5cf6',
  blue: '#3b82f6',
  green: '#22a06b',
  pink: '#e5487f',
  amber: '#d49b12',
  indigo: '#5b6ee1',
  slate: '#64748b',
} as const
export type Tone = keyof typeof TONES

/** An icon on a tinted rounded square; `solid` for the selected / headline form. */
export function IconTile({ icon, tone, size = 30, solid = false }: { icon: ReactNode; tone: Tone; size?: number; solid?: boolean }) {
  const c = TONES[tone]
  return (
    <Box
      sx={{
        width: size,
        height: size,
        flex: 'none',
        borderRadius: size > 34 ? 2.5 : 2,
        display: 'grid',
        placeItems: 'center',
        color: solid ? '#fff' : c,
        bgcolor: solid ? c : alpha(c, 0.13),
        boxShadow: solid ? `0 4px 10px ${alpha(c, 0.35)}` : 'none',
        '& svg': { fontSize: size * 0.6 },
        transition: 'background-color .15s, color .15s',
      }}
    >
      {icon}
    </Box>
  )
}

/** A card's title row: icon, title, an optional line under it, and actions on the right. */
export function PanelTitle({ icon, tone, title, sub, action, mb = 1.5 }: { icon: ReactNode; tone: Tone; title: ReactNode; sub?: ReactNode; action?: ReactNode; mb?: number }) {
  return (
    <Stack direction="row" spacing={1.25} alignItems={sub ? 'flex-start' : 'center'} sx={{ mb }}>
      <IconTile icon={icon} tone={tone} />
      <Box sx={{ flex: 1, minWidth: 0, pt: sub ? 0.25 : 0 }}>
        <Typography variant="subtitle1" component="div" sx={{ lineHeight: 1.3, display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
          {title}
        </Typography>
        {sub && (
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.25 }}>
            {sub}
          </Typography>
        )}
      </Box>
      {action}
    </Stack>
  )
}

/** The title bar every pop-up uses: icon, title, an optional line under it, close on the right. */
export function DialogHeader({ icon, tone, title, sub, onClose }: { icon: ReactNode; tone: Tone; title: ReactNode; sub?: ReactNode; onClose?: () => void }) {
  return (
    <DialogTitle component="div" sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
      <IconTile icon={icon} tone={tone} size={34} />
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Typography variant="h6" component="h2" sx={{ fontSize: 16.5, lineHeight: 1.3 }}>
          {title}
        </Typography>
        {sub && (
          <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
            {sub}
          </Typography>
        )}
      </Box>
      {onClose && (
        <IconButton size="small" onClick={onClose} aria-label="关闭" sx={{ color: 'text.secondary' }}>
          <CloseIcon fontSize="small" />
        </IconButton>
      )}
    </DialogTitle>
  )
}

/** The heading over a whole page (a wizard step or a rail section). */
export function PageHeader({ icon, tone, title, sub }: { icon: ReactNode; tone: Tone; title: ReactNode; sub?: ReactNode }) {
  return (
    <Stack direction="row" spacing={1.5} alignItems="center">
      <IconTile icon={icon} tone={tone} size={38} solid />
      <Box>
        <Typography variant="h6" sx={{ lineHeight: 1.25 }}>
          {title}
        </Typography>
        {sub && (
          <Typography variant="body2" color="text.secondary">
            {sub}
          </Typography>
        )}
      </Box>
    </Stack>
  )
}
