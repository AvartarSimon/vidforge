import { createTheme } from '@mui/material/styles'

// Palette mirrors the existing vanilla-JS frontend's CSS tokens (vidforge/ui/static/style.css),
// which are drawn from a well-known five-colour set (terracotta/sandy-orange/persian-green/
// charcoal/saffron — one of colorhunt.co's most-saved palettes) so the two frontends read as
// the same product. `warning` deliberately stays a darker amber rather than the palette's own
// saffron (#e9c46a): several places in this app use warning.main as plain TEXT on a white
// background (save-state, stale-audio hints, clip-length warnings), and saffron's contrast
// ratio there is well under WCAG AA — legible-as-text wins over strict palette purity here.
const CHARCOAL = '#264653'

export const theme = createTheme({
  palette: {
    primary: { main: '#e76f51' }, // terracotta
    secondary: { main: '#f4a261' }, // sandy orange
    success: { main: '#2a9d8f' }, // persian green
    error: { main: '#d14343' },
    warning: { main: '#b7791f' },
    info: { main: CHARCOAL },
    text: { primary: CHARCOAL },
  },
  shape: { borderRadius: 12 },
  typography: {
    fontFamily: '"Inter", "Noto Sans SC", system-ui, sans-serif',
  },
})
