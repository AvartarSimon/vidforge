import { createTheme, type PaletteMode } from '@mui/material/styles'

// Palette mirrors the existing vanilla-JS frontend's CSS tokens (vidforge/ui/static/style.css),
// which are drawn from a well-known five-colour set (terracotta/sandy-orange/persian-green/
// charcoal/saffron — one of colorhunt.co's most-saved palettes) so the two frontends read as
// the same product. `warning` deliberately stays a darker amber rather than the palette's own
// saffron (#e9c46a): several places in this app use warning.main as plain TEXT on a white
// background (save-state, stale-audio hints, clip-length warnings), and saffron's contrast
// ratio there is well under WCAG AA — legible-as-text wins over strict palette purity here.
const CHARCOAL = '#264653'

// Dark mode isn't a nicety here — it's the *expected* look for this category of tool. Every
// mainstream video editor (Premiere, DaVinci Resolve, Final Cut, CapCut, Descript) defaults to
// a dark UI; a light-only editor reads as unfinished/wrong to anyone who's used one of those.
export function getTheme(mode: PaletteMode) {
  return createTheme({
    palette: {
      mode,
      primary: { main: '#e76f51' }, // terracotta
      secondary: { main: '#f4a261' }, // sandy orange
      success: { main: '#2a9d8f' }, // persian green
      error: { main: '#d14343' },
      warning: { main: '#b7791f' },
      info: { main: mode === 'dark' ? '#8fb8c4' : CHARCOAL },
      ...(mode === 'light'
        ? { text: { primary: CHARCOAL } }
        : { background: { default: '#14181b', paper: '#1c2125' } }),
    },
    shape: { borderRadius: 12 },
    typography: {
      fontFamily: '"Inter", "Noto Sans SC", system-ui, sans-serif',
    },
  })
}
