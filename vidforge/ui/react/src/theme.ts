import { createTheme } from '@mui/material/styles'

// Palette mirrors the existing vanilla-JS frontend's CSS tokens (vidforge/ui/static/style.css)
// so the two frontends read as the same product, not unrelated ones.
export const theme = createTheme({
  palette: {
    primary: { main: '#e76f51' },
    secondary: { main: '#f4a261' },
    success: { main: '#2a9d8f' },
    error: { main: '#d14343' },
    warning: { main: '#b7791f' },
  },
  shape: { borderRadius: 12 },
  typography: {
    fontFamily: '"Inter", "Noto Sans SC", system-ui, sans-serif',
  },
})
