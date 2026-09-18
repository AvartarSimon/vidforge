import { useEffect, useState } from 'react'
import { Box, CircularProgress, Stack, Toolbar, Typography } from '@mui/material'
import { NavRail, DRAWER_WIDTH } from './components/nav/NavRail'
import { ScriptStep } from './components/steps/ScriptStep'
import { VoiceStep } from './components/steps/VoiceStep'
import { VisualsStep } from './components/steps/VisualsStep'
import { RenderStep } from './components/steps/RenderStep'
import { PublishStep } from './components/steps/PublishStep'
import { ProjectProvider, useProject } from './state/ProjectContext'

const STEP_LABELS: Record<number, string> = { 1: '脚本', 2: '配音', 3: '画面', 4: '渲染', 5: '发布' }

const SAVE_LABEL: Record<string, string> = {
  saved: '已保存',
  dirty: '有改动，稍后自动保存…',
  saving: '保存中…',
  error: '未保存',
}

function Shell() {
  const { raw, loading, error, saveState, savedAt } = useProject()
  const [step, setStep] = useState<number>(() => {
    try {
      return parseInt(localStorage.getItem('vf.react.step') || '1', 10) || 1
    } catch {
      return 1
    }
  })

  useEffect(() => {
    try {
      localStorage.setItem('vf.react.step', String(step))
    } catch {
      // ignore (private browsing etc.)
    }
  }, [step])

  return (
    <Box sx={{ display: 'flex' }}>
      <NavRail activeStep={step} onStep={setStep} />
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
          {!loading && !error && raw && step === 1 && <ScriptStep />}
          {!loading && !error && raw && step === 2 && <VoiceStep />}
          {!loading && !error && raw && step === 3 && <VisualsStep />}
          {!loading && !error && raw && step === 4 && <RenderStep />}
          {!loading && !error && raw && step === 5 && <PublishStep />}
        </Box>
      </Box>
    </Box>
  )
}

export default function App() {
  return (
    <ProjectProvider>
      <Shell />
    </ProjectProvider>
  )
}

// re-export for callers that only need the layout constant (e.g. future top-level pages)
export { DRAWER_WIDTH }
