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
  // second- and third-level navigation (tabs, toggle groups) share one segmented look: a grey
  // track with the chosen item lifted onto the paper colour, as in macOS / 剪映 settings panels
  const track = dark ? '#222428' : '#eceef1'
  const lifted = dark ? '0 1px 2px rgba(0,0,0,.55)' : '0 1px 3px rgba(16,24,40,.14)'
  const primary = dark ? CYAN : '#0f9a9a'
  const muted = dark ? '#9a9ea6' : '#5d6670'
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
        styleOverrides: { root: { borderColor: line, borderRadius: 14, boxShadow: dark ? 'none' : '0 1px 2px rgba(16,24,40,.04)' } },
      },
      MuiAccordion: {
        defaultProps: { disableGutters: true, elevation: 0 },
        styleOverrides: {
          root: {
            border: `1px solid ${line}`,
            borderRadius: '14px !important',
            overflow: 'hidden',
            backgroundColor: paper,
            boxShadow: dark ? 'none' : '0 1px 2px rgba(16,24,40,.04)',
            '&::before': { display: 'none' },
          },
        },
      },
      MuiAccordionSummary: { styleOverrides: { root: { minHeight: 60, padding: '0 20px' }, content: { margin: '12px 0' } } },
      MuiAccordionDetails: { styleOverrides: { root: { padding: '4px 20px 20px' } } },
      MuiCardContent: { styleOverrides: { root: { padding: 20, '&:last-child': { paddingBottom: 20 } } } },
      MuiButton: {
        defaultProps: { disableElevation: true },
        styleOverrides: { root: { borderRadius: 8 }, sizeSmall: { padding: '3px 10px' } },
      },
      MuiToggleButtonGroup: {
        styleOverrides: {
          root: { backgroundColor: track, padding: 3, borderRadius: 10, gap: 2 },
          grouped: { border: 0, borderRadius: '8px !important', margin: '0 !important' },
        },
      },
      MuiToggleButton: {
        styleOverrides: {
          root: {
            textTransform: 'none',
            padding: '4px 12px',
            fontSize: 12.5,
            fontWeight: 600,
            border: 0,
            color: muted,
            '&.Mui-selected, &.Mui-selected:hover': { backgroundColor: paper, color: primary, boxShadow: lifted },
          },
        },
      },
      MuiChip: { styleOverrides: { root: { borderRadius: 6, fontWeight: 500 } } },
      MuiTab: {
        styleOverrides: {
          root: {
            textTransform: 'none',
            fontWeight: 600,
            minHeight: 32,
            minWidth: 0,
            padding: '5px 14px',
            borderRadius: 8,
            color: muted,
            '&.Mui-selected': { backgroundColor: paper, color: primary, boxShadow: lifted },
            '&:hover:not(.Mui-selected)': { color: dark ? '#e8e9eb' : CHARCOAL },
          },
        },
      },
      MuiTabs: {
        styleOverrides: {
          root: { minHeight: 38, padding: 3, borderRadius: 10, backgroundColor: track },
          flexContainer: { gap: 2 },
          indicator: { display: 'none' },
        },
      },
      MuiSlider: { styleOverrides: { thumb: { width: 12, height: 12 }, rail: { opacity: 0.25 } } },
      MuiTooltip: { styleOverrides: { tooltip: { fontSize: 12, backgroundColor: dark ? '#2b2e33' : '#2b2e33' } } },
      MuiDialog: {
        styleOverrides: {
          paper: { borderRadius: 16, border: `1px solid ${line}`, boxShadow: dark ? '0 24px 64px rgba(0,0,0,.6)' : '0 24px 64px rgba(16,24,40,.18)' },
        },
      },
      MuiBackdrop: {
        styleOverrides: {
          root: { backgroundColor: dark ? 'rgba(0,0,0,.6)' : 'rgba(15,23,42,.32)', backdropFilter: 'blur(3px)' },
          invisible: { backgroundColor: 'transparent', backdropFilter: 'none' },
        },
      },
      MuiDialogTitle: { styleOverrides: { root: { padding: '14px 16px 12px 20px', borderBottom: `1px solid ${line}` } } },
      // MUI drops the content's top padding after a title; with the title's rule above it, it needs it
      MuiDialogContent: { styleOverrides: { root: { padding: '16px 20px', '.MuiDialogTitle-root + &': { paddingTop: 16 } } } },
      MuiDialogActions: { styleOverrides: { root: { padding: '12px 20px', borderTop: `1px solid ${line}`, gap: 4 } } },
      MuiDrawer: { styleOverrides: { paper: { borderLeft: `1px solid ${line}` } } },
      MuiPopover: {
        styleOverrides: { paper: { borderRadius: 10, border: `1px solid ${line}`, boxShadow: dark ? '0 12px 32px rgba(0,0,0,.5)' : '0 12px 32px rgba(16,24,40,.14)' } },
      },
      MuiMenu: { styleOverrides: { list: { padding: 4 } } },
      MuiMenuItem: { styleOverrides: { root: { borderRadius: 6, margin: '1px 0', fontSize: 13.5 } } },
      MuiOutlinedInput: { styleOverrides: { root: { borderRadius: 8 } } },
      MuiAlert: { styleOverrides: { root: { borderRadius: 8 } } },
      MuiListItemButton: { styleOverrides: { root: { borderRadius: 8 } } },
    },
  })
}
