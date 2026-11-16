import { alpha, createTheme, type PaletteMode } from '@mui/material/styles'

// Modelled on the editors people already know — 剪映 / CapCut, DaVinci Resolve, Descript: a
// neutral near-black workspace so the picture is the brightest thing on screen, one cool accent
// for "this is selected / this is the action", and dense controls because an editor shows many
// panels at once. The warm terracotta of the old palette stays as `secondary` (brand, highlights);
// the accent moved to cyan because on footage — mostly skin tones and warm interiors — a warm
// accent disappears and a cyan one does not.
//
// `warning` stays a darker amber: several places use warning.main as plain text, and the light
// palette's saffron fails WCAG AA there.
const CYAN = '#1fc8c8'
const CHARCOAL = '#1f2a30'

export function getTheme(mode: PaletteMode) {
  const dark = mode === 'dark'
  const bg = dark ? '#0f1012' : '#f4f5f7'
  const paper = dark ? '#18191c' : '#ffffff'
  const line = dark ? '#2a2c31' : '#e2e4e8'
  return createTheme({
    palette: {
      mode,
      primary: { main: dark ? CYAN : '#0f9a9a', contrastText: dark ? '#071414' : '#ffffff' },
      secondary: { main: '#e76f51' },
      success: { main: '#2fb380' },
      error: { main: '#f0544f' },
      warning: { main: dark ? '#e0a33a' : '#a86a12' },
      info: { main: dark ? '#7fb3ff' : '#2463c4' },
      background: { default: bg, paper },
      divider: line,
      text: dark ? { primary: '#e8e9eb', secondary: '#9a9ea6' } : { primary: CHARCOAL, secondary: '#5d6670' },
      action: dark ? { selected: alpha(CYAN, 0.14), hover: 'rgba(255,255,255,0.05)' } : { selected: alpha('#0f9a9a', 0.1) },
    },
    shape: { borderRadius: 8 },
    typography: {
      fontFamily: '"Inter", "PingFang SC", "Noto Sans SC", system-ui, sans-serif',
      fontSize: 13,
      h6: { fontSize: 17, fontWeight: 650 },
      subtitle1: { fontSize: 15, fontWeight: 600 },
      subtitle2: { fontWeight: 600 },
      button: { textTransform: 'none', fontWeight: 600 },
    },
    components: {
      MuiCssBaseline: {
        styleOverrides: {
          body: { backgroundColor: bg },
          '*::-webkit-scrollbar': { width: 10, height: 10 },
          '*::-webkit-scrollbar-thumb': { backgroundColor: dark ? '#33363c' : '#c9ccd2', borderRadius: 8, border: `2px solid ${bg}` },
          '*::-webkit-scrollbar-track': { background: 'transparent' },
        },
      },
      MuiPaper: { styleOverrides: { root: { backgroundImage: 'none' } } },
      MuiCard: {
        defaultProps: { variant: 'outlined' },
        styleOverrides: { root: { borderColor: line, borderRadius: 12 } },
      },
      MuiCardContent: { styleOverrides: { root: { padding: 20, '&:last-child': { paddingBottom: 20 } } } },
      MuiButton: {
        defaultProps: { disableElevation: true },
        styleOverrides: { root: { borderRadius: 8 }, sizeSmall: { padding: '3px 10px' } },
      },
      MuiToggleButton: { styleOverrides: { root: { textTransform: 'none', padding: '4px 10px', fontSize: 12.5 } } },
      MuiChip: { styleOverrides: { root: { borderRadius: 6, fontWeight: 500 } } },
      MuiTab: { styleOverrides: { root: { textTransform: 'none', fontWeight: 600, minHeight: 40 } } },
      MuiTabs: { styleOverrides: { root: { minHeight: 40 }, indicator: { height: 2, borderRadius: 2 } } },
      MuiSlider: { styleOverrides: { thumb: { width: 12, height: 12 }, rail: { opacity: 0.25 } } },
      MuiTooltip: { styleOverrides: { tooltip: { fontSize: 12, backgroundColor: dark ? '#2b2e33' : '#2b2e33' } } },
      MuiDialog: { styleOverrides: { paper: { borderRadius: 12, border: `1px solid ${line}` } } },
      MuiOutlinedInput: { styleOverrides: { root: { borderRadius: 8 } } },
      MuiAlert: { styleOverrides: { root: { borderRadius: 8 } } },
      MuiListItemButton: { styleOverrides: { root: { borderRadius: 8 } } },
    },
  })
}
