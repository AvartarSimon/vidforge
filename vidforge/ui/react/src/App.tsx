import { useEffect, useMemo, useState } from 'react'
import { Alert, Box, CircularProgress, CssBaseline, Stack, ThemeProvider, Toolbar, Typography } from '@mui/material'
import type { PaletteMode } from '@mui/material'
import { apiGet } from './api/client'
import { NavRail, DRAWER_WIDTH } from './components/nav/NavRail'
import { ScriptStep } from './components/steps/ScriptStep'
import { VoiceStep } from './components/steps/VoiceStep'
import { VisualsStep } from './components/steps/VisualsStep'
import { RenderStep } from './components/steps/RenderStep'
import { PublishStep } from './components/steps/PublishStep'
import { getTheme } from './theme'
import { ProjectProvider, useProject } from './state/ProjectContext'

const STEP_LABELS: Record<number, string> = { 1: '脚本', 2: '配音', 3: '画面', 4: '渲染', 5: '发布' }

const SAVE_LABEL: Record<string, string> = {
  saved: '已保存',
  dirty: '有改动，稍后自动保存…',
  saving: '保存中…',
  error: '未保存',
}

function readStoredMode(): PaletteMode {
  try {
    const v = localStorage.getItem('vf.react.theme')
    if (v === 'light' || v === 'dark') return v
  } catch {
    // ignore (private browsing etc.)
  }
  // video-editing tools default to dark; fall back to it unless the OS explicitly asks for light
  return window.matchMedia?.('(prefers-color-scheme: light)').matches ? 'light' : 'dark'
}

function Shell({ mode, onToggleMode }: { mode: PaletteMode; onToggleMode: () => void }) {
  const { raw, view, loading, error, saveState, savedAt } = useProject()
  // steps keep their own local UI state (draft text, picker filters, …) that must not survive a
  // project switch — remounting the active step whenever the open project's path changes is
  // simpler and more thorough than hunting down every piece of that state individually.
  const stepKey = view?.root || 'none'
  const [step, setStep] = useState<number>(() => {
    try {
      return parseInt(localStorage.getItem('vf.react.step') || '1', 10) || 1
    } catch {
      return 1
    }
  })

  // The backend serves this page from disk on every request, so an instance started before an
  // update hands you today's UI while still answering yesterday's routes ("not found" on a button
  // you can see). Builds older than that have no `stamp` in /api/health.
  const [staleBackend, setStaleBackend] = useState(false)
  useEffect(() => {
    apiGet<{ stamp?: string }>('/api/health')
      .then((h) => setStaleBackend(!h.stamp))
      .catch(() => setStaleBackend(false))
  }, [])

  useEffect(() => {
    try {
      localStorage.setItem('vf.react.step', String(step))
    } catch {
      // ignore (private browsing etc.)
    }
  }, [step])

  return (
    <Box sx={{ display: 'flex' }}>
      <NavRail activeStep={step} onStep={setStep} mode={mode} onToggleMode={onToggleMode} />
      <Box component="main" sx={{ flexGrow: 1, minHeight: '100vh', bgcolor: 'background.default' }}>
        <Toolbar sx={{ justifyContent: 'space-between', borderBottom: '1px solid', borderColor: 'divider' }}>
          <Typography variant="subtitle1" fontWeight={600}>
            {raw ? `${raw.title || '(未命名)'} · 第 ${step} 步 · ${STEP_LABELS[step]}` : 'vidforge'}
          </Typography>
          {raw && (
            <Typography
              variant="body2"
              color={saveState === 'error' ? 'error' : saveState === 'dirty' ? 'warning.main' : 'text.secondary'}
            >
              {SAVE_LABEL[saveState]}
              {saveState === 'saved' && savedAt ? ` ${savedAt.toLocaleTimeString()}` : ''}
            </Typography>
          )}
        </Toolbar>
        <Box sx={{ p: 3 }}>
          {staleBackend && (
            <Alert severity="error" sx={{ mb: 2 }}>
              后端是旧版本（在这次更新之前启动的），新功能会报 “not found”。关掉 vidforge 的黑窗口，重新双击 start-vidforge 即可（新版会自动替换旧进程）。
            </Alert>
          )}
          {loading && (
            <Stack alignItems="center" sx={{ py: 8 }}>
              <CircularProgress />
            </Stack>
          )}
          {!loading && error && (
            <Typography color="error">{error}</Typography>
          )}
          {!loading && !error && !raw && (
            <Typography color="text.secondary">
              还没有打开项目——点左上角的项目卡片，新建或打开一个。
            </Typography>
          )}
          {!loading && !error && raw && step === 1 && <ScriptStep key={stepKey} />}
          {!loading && !error && raw && step === 2 && <VoiceStep key={stepKey} />}
          {!loading && !error && raw && step === 3 && <VisualsStep key={stepKey} />}
          {!loading && !error && raw && step === 4 && <RenderStep key={stepKey} />}
          {!loading && !error && raw && step === 5 && <PublishStep key={stepKey} />}
        </Box>
      </Box>
    </Box>
  )
}

export default function App() {
  const [mode, setMode] = useState<PaletteMode>(readStoredMode)
  const theme = useMemo(() => getTheme(mode), [mode])

  const toggleMode = () => {
    setMode((m) => {
      const next = m === 'dark' ? 'light' : 'dark'
      try {
        localStorage.setItem('vf.react.theme', next)
      } catch {
        // ignore (private browsing etc.)
      }
      return next
    })
  }

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <ProjectProvider>
        <Shell mode={mode} onToggleMode={toggleMode} />
      </ProjectProvider>
    </ThemeProvider>
  )
}

// re-export for callers that only need the layout constant (e.g. future top-level pages)
export { DRAWER_WIDTH }
