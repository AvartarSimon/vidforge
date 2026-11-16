import { useState } from 'react'
import { Avatar, Box, Button, ButtonBase, Stack, Typography } from '@mui/material'
import IosShareIcon from '@mui/icons-material/IosShare'
import ExpandMoreIcon from '@mui/icons-material/ExpandMore'
import { useProject } from '../../state/ProjectContext'
import { ProjectSwitcher } from './ProjectSwitcher'
import { STEPS, stepDone } from './NavRail'

const SAVE_LABEL: Record<string, string> = {
  saved: '已保存',
  dirty: '有改动…',
  saving: '保存中…',
  error: '未保存',
}

/**
 * The bar across the top, laid out like CapCut's: the project on the left (click to switch), the
 * five steps in the middle as a progress strip, save state and 导出 on the right. 导出 is the one
 * button every editor has in the same place, so it is here too: it goes to 发布 when there is a
 * finished video and to 渲染 when there is not.
 */
export function TopBar({ step, inWizard, onStep }: { step: number; inWizard: boolean; onStep: (n: number) => void }) {
  const { raw, view, saveState, savedAt } = useProject()
  const [switcherOpen, setSwitcherOpen] = useState(false)
  const title = raw?.title || (view?.root ? view.root.split(/[\\/]/).pop() : null) || '未打开项目'
  const hasFinal = Boolean(view?.outputs?.final)

  return (
    <Box
      component="header"
      sx={{
        position: 'sticky',
        top: 0,
        zIndex: 10,
        height: 48,
        display: 'flex',
        alignItems: 'center',
        gap: 1.5,
        px: 1.5,
        bgcolor: 'background.paper',
        borderBottom: '1px solid',
        borderColor: 'divider',
      }}
    >
      <Typography sx={{ fontWeight: 800, fontSize: 16, letterSpacing: 0.2, color: 'primary.main', width: 64, textAlign: 'center' }}>vidforge</Typography>
      <ButtonBase onClick={() => setSwitcherOpen(true)} sx={{ borderRadius: 2, px: 1, py: 0.5, gap: 1, maxWidth: 320, '&:hover': { bgcolor: 'action.hover' } }} title={view?.root || ''}>
        <Avatar sx={{ width: 24, height: 24, fontSize: 13, bgcolor: 'secondary.main' }}>{[...title][0]?.toUpperCase() || '?'}</Avatar>
        <Typography noWrap sx={{ fontWeight: 600, fontSize: 13.5 }}>
          {title}
        </Typography>
        <ExpandMoreIcon fontSize="small" sx={{ color: 'text.secondary' }} />
      </ButtonBase>

      <Stack direction="row" alignItems="center" sx={{ flexGrow: 1, justifyContent: 'center', display: { xs: 'none', md: 'flex' } }}>
        {STEPS.map((s, i) => {
          const done = stepDone(s.n, raw, view)
          const active = inWizard && step === s.n
          return (
            <Stack key={s.n} direction="row" alignItems="center">
              {i > 0 && <Box sx={{ width: 18, height: 1, bgcolor: 'divider' }} />}
              <ButtonBase
                disabled={!raw}
                onClick={() => onStep(s.n)}
                title={s.sub}
                sx={{
                  px: 1.25,
                  py: 0.5,
                  borderRadius: 99,
                  gap: 0.75,
                  bgcolor: active ? 'action.selected' : 'transparent',
                  '&:hover': { bgcolor: active ? 'action.selected' : 'action.hover' },
                }}
              >
                <Box
                  sx={{
                    width: 18,
                    height: 18,
                    borderRadius: '50%',
                    fontSize: 11,
                    fontWeight: 700,
                    display: 'grid',
                    placeItems: 'center',
                    bgcolor: active ? 'primary.main' : done ? 'success.main' : 'action.disabledBackground',
                    color: active || done ? '#0b1214' : 'text.secondary',
                  }}
                >
                  {done && !active ? '✓' : s.n}
                </Box>
                <Typography sx={{ fontSize: 13, fontWeight: active ? 700 : 500, color: active ? 'text.primary' : 'text.secondary' }}>{s.label}</Typography>
              </ButtonBase>
            </Stack>
          )
        })}
      </Stack>

      {raw && (
        <Typography variant="caption" sx={{ color: saveState === 'error' ? 'error.main' : saveState === 'dirty' ? 'warning.main' : 'text.secondary', whiteSpace: 'nowrap' }}>
          {SAVE_LABEL[saveState]}
          {saveState === 'saved' && savedAt ? ` ${savedAt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}` : ''}
        </Typography>
      )}
      <Button variant="contained" size="small" startIcon={<IosShareIcon fontSize="small" />} disabled={!raw} onClick={() => onStep(hasFinal ? 5 : 4)} sx={{ px: 2 }}>
        导出
      </Button>
      <ProjectSwitcher open={switcherOpen} onClose={() => setSwitcherOpen(false)} />
    </Box>
  )
}
