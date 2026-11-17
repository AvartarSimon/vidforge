import { useEffect, useMemo, useState } from 'react'
import { Alert, Box, Button, CircularProgress, CssBaseline, Stack, ThemeProvider, Typography } from '@mui/material'
import type { PaletteMode } from '@mui/material'
import { apiGet } from './api/client'
import { NavRail, DRAWER_WIDTH, SECTIONS, STEPS, stepDone } from './components/nav/NavRail'
import { PageHeader } from './components/shared/ui'
import { TopBar } from './components/nav/TopBar'
import type { SectionId } from './components/nav/NavRail'
import { TrendsSection } from './components/sections/TrendsSection'
import { ReferencesSection } from './components/sections/ReferencesSection'
import { EditorSection } from './components/sections/EditorSection'
import { RecordStudio } from './components/sections/voice/RecordStudio'
import { VideoSection } from './components/sections/VideoSection'
import { VoiceSection } from './components/sections/VoiceSection'
import { ImagesSection } from './components/sections/ImagesSection'
import { ScriptStep } from './components/steps/ScriptStep'
import { VoiceStep } from './components/steps/VoiceStep'
import { VisualsStep } from './components/steps/VisualsStep'
import { RenderStep } from './components/steps/RenderStep'
import { PublishStep } from './components/steps/PublishStep'
import { getTheme } from './theme'
import { ProjectProvider, useProject } from './state/ProjectContext'

const STEP_LABELS: Record<number, string> = { 1: '脚本', 2: '配音', 3: '画面', 4: '渲染', 5: '发布' }

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
  const { raw, view, loading, error } = useProject()
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
  // null = the wizard is showing; otherwise one of the material sections (视频 / 声音 / 图片)
  const [section, setSection] = useState<SectionId | null>(() => {
    try {
      const v = localStorage.getItem('vf.react.section')
      return SECTIONS.some((x) => x.id === v) ? (v as SectionId) : null
    } catch {
      return null
    }
  })
  useEffect(() => {
    try {
      localStorage.setItem('vf.react.section', section || '')
    } catch {
      // ignore (private browsing etc.)
    }
  }, [section])

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

  const goStep = (n: number) => {
    setSection(null)
    setStep(n)
  }
  const fullBleed = section === 'editor'

  return (
    <Box>
      <TopBar step={step} inWizard={section === null} onStep={goStep} />
      <Box sx={{ display: 'flex' }}>
      <NavRail activeSection={section} onSection={setSection} mode={mode} onToggleMode={onToggleMode} />
      <Box component="main" sx={{ flexGrow: 1, minWidth: 0, minHeight: 'calc(100vh - 48px)', bgcolor: 'background.default' }}>
        {!fullBleed && raw && (
          <Box sx={{ px: 3, pt: 2.5, pb: 0.5, maxWidth: 1480, mx: 'auto' }}>
            {(() => {
              const sec = section ? SECTIONS.find((x) => x.id === section) : null
              const st = STEPS.find((x) => x.n === step) || STEPS[0]
              const Icon = sec ? sec.icon : st.icon
              return (
                <PageHeader
                  icon={<Icon />}
                  tone={sec ? sec.tone : st.tone}
                  title={sec ? sec.label : `第 ${step} 步 · ${st.label}`}
                  sub={sec ? sec.sub : st.sub}
                />
              )
            })()}
          </Box>
        )}
        <Box sx={fullBleed ? {} : { p: 3, pt: 1.5, maxWidth: 1480, mx: 'auto' }}>
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
          {!loading && !error && raw && section === 'editor' && <EditorSection key={`${stepKey}-editor`} onOpen={(w) => (w === 'studio' ? setSection('studio') : goStep(4))} />}
          {!loading && !error && raw && section === 'studio' && <RecordStudio key={`${stepKey}-studio`} />}
          {!loading && !error && raw && section === 'trends' && <TrendsSection key={`${stepKey}-trends`} />}
          {!loading && !error && raw && section === 'refs' && (
            <ReferencesSection
              key={`${stepKey}-refs`}
              onUse={(tid) => {
                // the script step reads its skeleton from here when it opens
                try {
                  localStorage.setItem('vf.structure', tid)
                } catch {
                  // private window: the choice is made again in the step
                }
                goStep(1)
              }}
            />
          )}
          {!loading && !error && raw && section === 'video' && <VideoSection key={`${stepKey}-video`} />}
          {!loading && !error && raw && section === 'voice' && <VoiceSection key={`${stepKey}-voice`} />}
          {!loading && !error && raw && section === 'images' && <ImagesSection key={`${stepKey}-images`} />}
          {!loading && !error && raw && !section && step === 1 && <ScriptStep key={stepKey} />}
          {!loading && !error && raw && !section && step === 2 && <VoiceStep key={stepKey} />}
          {!loading && !error && raw && !section && step === 3 && <VisualsStep key={stepKey} />}
          {!loading && !error && raw && !section && step === 4 && <RenderStep key={stepKey} />}
          {!loading && !error && raw && !section && step === 5 && <PublishStep key={stepKey} onRender={() => goStep(4)} />}

          {/* The wizard is a sequence, so it needs a way forward that is not "find it in the
              sidebar". The hint says what the next step expects, which is the question people
              actually have at the bottom of a step. */}
          {!loading && !error && raw && !section && (
            <Stack
              direction="row"
              spacing={1}
              alignItems="center"
              sx={{ mt: 4, pt: 2, borderTop: '1px solid', borderColor: 'divider' }}
            >
              <Button size="small" disabled={step <= 1} onClick={() => goStep(step - 1)}>
                ← 上一步
              </Button>
              <Typography variant="caption" color="text.secondary" sx={{ flexGrow: 1 }}>
                {step < 5
                  ? `${stepDone(step, raw, view) ? '这一步完成了。' : ''}下一步：${STEP_LABELS[step + 1]}`
                  : '最后一步'}
              </Typography>
              <Button
                size="small"
                variant={stepDone(step, raw, view) ? 'contained' : 'outlined'}
                disabled={step >= 5}
                onClick={() => goStep(step + 1)}
              >
                下一步：{STEP_LABELS[step + 1] || ''} →
              </Button>
            </Stack>
          )}
        </Box>
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
