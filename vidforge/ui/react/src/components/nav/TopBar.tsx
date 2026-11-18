import { useState } from 'react'
import { Avatar, Box, Button, ButtonBase, Dialog, DialogContent, MenuItem, Stack, TextField, Typography } from '@mui/material'
import AspectRatioIcon from '@mui/icons-material/AspectRatio'
import IosShareIcon from '@mui/icons-material/IosShare'
import ExpandMoreIcon from '@mui/icons-material/ExpandMore'
import { useProject } from '../../state/ProjectContext'
import { ProjectSwitcher } from './ProjectSwitcher'
import { BackgroundJobs } from './BackgroundJobs'
import { STEPS, stepDone } from './NavRail'
import { FRAME_INFO, ThemePicker } from '../shared/ThemePicker'
import { DialogHeader } from '../shared/ui'

const PALETTE_NAMES: Record<string, string> = { sunny: '暖阳橙', mint: '薄荷绿', sky: '天空蓝', coral: '珊瑚粉', lemon: '柠檬黄', violet: '活力紫' }

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
  const { raw, view, saveState, savedAt, lang, setLang } = useProject()
  const [switcherOpen, setSwitcherOpen] = useState(false)
  const [frameOpen, setFrameOpen] = useState(false)
  // the frame decides everything downstream (pictures, charts, platforms): always in sight, one click to change
  const ratio = (() => {
    const w = raw?.width || 1920
    const h = raw?.height || 1080
    const g = (a: number, b: number): number => (b ? g(b, a % b) : a)
    const k = g(w, h)
    return `${w / k}:${h / k}`
  })()
  const frameLabel = `${FRAME_INFO[ratio]?.label || ratio}${raw?.theme?.palette ? ` · ${PALETTE_NAMES[raw.theme.palette] || raw.theme.palette}` : ''}`
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
        <Button size="small" color="inherit" startIcon={<AspectRatioIcon fontSize="small" />} onClick={() => setFrameOpen(true)} sx={{ color: 'text.secondary', whiteSpace: 'nowrap' }} title="画幅与风格">
          {frameLabel}
        </Button>
      )}
      {raw && view && view.langs?.length > 1 && (
        // a project with language variants: which one the steps edit, voice and render
        <TextField
          select
          size="small"
          value={lang || view.base_lang}
          onChange={(e) => setLang(e.target.value)}
          title="编辑哪个语言版本（project.json 的 variants）"
          sx={{ '& .MuiInputBase-input': { py: 0.5, fontSize: 13 } }}
        >
          {view.langs.map((l) => (
            <MenuItem key={l} value={l}>
              {l === view.base_lang ? `${l}（原版）` : l}
            </MenuItem>
          ))}
        </TextField>
      )}
      <BackgroundJobs onStep={onStep} />
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
      <Dialog open={frameOpen} onClose={() => setFrameOpen(false)} maxWidth="md" fullWidth>
        <DialogHeader icon={<AspectRatioIcon />} tone="pink" title="画幅与风格" sub="发哪个平台就选哪个画幅；配色管字幕、角标、图表和小窗边框" onClose={() => setFrameOpen(false)} />
        <DialogContent>{frameOpen && <ThemePicker bare onApplied={() => setFrameOpen(false)} />}</DialogContent>
      </Dialog>
    </Box>
  )
}
