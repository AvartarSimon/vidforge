import { useState } from 'react'
import { Box, ButtonBase, Dialog, DialogContent, Divider, IconButton, Tooltip, Typography } from '@mui/material'
import type { PaletteMode } from '@mui/material'
import CategoryIcon from '@mui/icons-material/Category'
import HistoryIcon from '@mui/icons-material/History'
import PowerSettingsNewIcon from '@mui/icons-material/PowerSettingsNew'
import WhatshotIcon from '@mui/icons-material/Whatshot'
import MovieFilterIcon from '@mui/icons-material/MovieFilter'
import ViewTimelineIcon from '@mui/icons-material/ViewTimeline'
import VideocamIcon from '@mui/icons-material/Videocam'
import GraphicEqIcon from '@mui/icons-material/GraphicEq'
import PhotoLibraryIcon from '@mui/icons-material/PhotoLibrary'
import AutoAwesomeIcon from '@mui/icons-material/AutoAwesome'
import MonitorHeartIcon from '@mui/icons-material/MonitorHeart'
import DarkModeIcon from '@mui/icons-material/DarkMode'
import LightModeIcon from '@mui/icons-material/LightMode'
import { ApiError, apiPost } from '../../api/client'
import type { ProjectView, RawProject } from '../../api/types'
import { useProject } from '../../state/ProjectContext'
import { ProjectHistoryDialog } from './ProjectHistoryDialog'
import { CategoryManagerDialog } from './CategoryManagerDialog'
import { AiAssistantDrawer } from './AiAssistantDrawer'
import { SystemStatusDialog } from './SystemStatusDialog'

export const DRAWER_WIDTH = 76

export const STEPS = [
  { n: 1, label: '脚本', sub: '写或生成旁白' },
  { n: 2, label: '配音', sub: '声音与试听' },
  { n: 3, label: '画面', sub: '每段挑素材' },
  { n: 4, label: '渲染', sub: '出片与主持人' },
  { n: 5, label: '发布', sub: '上传与声明' },
]

// Work that is about one kind of material rather than about one step of this video: covering
// faces in a clip, managing voices, reviewing everything that was downloaded. Kept out of the
// wizard so it can be reached at any time and grown independently.
export const SECTIONS = [
  { id: 'editor', label: '剪辑台', sub: '时间线、预览、属性', icon: ViewTimelineIcon },
  { id: 'studio', label: '录制', sub: '提词器、美颜、换背景', icon: VideocamIcon },
  { id: 'trends', label: '热点', sub: '现在什么在火', icon: WhatshotIcon },
  { id: 'video', label: '视频', sub: '剪口播、美化、遮脸', icon: MovieFilterIcon },
  { id: 'voice', label: '声音', sub: '声音库与试听', icon: GraphicEqIcon },
  { id: 'images', label: '图片', sub: '素材与授权', icon: PhotoLibraryIcon },
] as const

export type SectionId = (typeof SECTIONS)[number]['id']

// Which steps are finished, judged from the project itself rather than from a flag someone has
// to remember to set. Without this the five steps look identical whether or not you have done
// them, and on a project picked up a week later there is no way to tell where you stopped.
export function stepDone(step: number, raw: RawProject | null, view: ProjectView | null): boolean {
  const segs = raw?.segments || []
  if (!segs.length) return false
  const resolved = view?.resolved || {}
  switch (step) {
    case 1:
      return segs.every((s) => (s.text || '').trim().length > 0)
    case 2:
      return segs.every((s) => resolved[s.id]?.audio_fresh)
    case 3:
      return segs.every((s) => s.remotion || (resolved[s.id]?.clips || []).some((c) => c.path || c.remotion))
    case 4:
      return Boolean(view?.outputs?.final)
    case 5:
      return Boolean(view?.outputs?.youtube)
    default:
      return false
  }
}

// The slim left rail, as in 剪映 / CapCut: one icon per workspace with its name under it, and the
// tools that are about the whole app (history, AI, categories, status, theme, quit) at the bottom.
// The five-step wizard lives in the top bar instead, where it reads as the progress it is.
function RailButton({ label, icon, active, disabled, onClick }: { label: string; icon: React.ReactNode; active?: boolean; disabled?: boolean; onClick: () => void }) {
  return (
    <ButtonBase
      onClick={onClick}
      disabled={disabled}
      sx={{
        width: 64,
        py: 0.9,
        borderRadius: 2,
        flexDirection: 'column',
        gap: 0.25,
        color: active ? 'primary.main' : 'text.secondary',
        bgcolor: active ? 'action.selected' : 'transparent',
        opacity: disabled ? 0.4 : 1,
        '&:hover': { bgcolor: active ? 'action.selected' : 'action.hover', color: active ? 'primary.main' : 'text.primary' },
      }}
    >
      {icon}
      <Typography sx={{ fontSize: 11.5, fontWeight: active ? 700 : 500, lineHeight: 1.2 }}>{label}</Typography>
    </ButtonBase>
  )
}

export function NavRail({
  activeSection,
  onSection,
  mode,
  onToggleMode,
}: {
  activeSection: SectionId | null
  onSection: (id: SectionId) => void
  mode: PaletteMode
  onToggleMode: () => void
}) {
  const { raw } = useProject()
  const [categoryOpen, setCategoryOpen] = useState(false)
  const [aiOpen, setAiOpen] = useState(false)
  const [statusOpen, setStatusOpen] = useState(false)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [quitting, setQuitting] = useState(false)

  // Closing the browser tab leaves the server running — which is how an instance from days ago
  // ends up serving today's page over yesterday's routes. Give it an explicit off switch.
  const quit = async (force = false) => {
    if (!force && !window.confirm('退出 vidforge？（关网页不会停止它，从这里停）')) return
    try {
      await apiPost('/api/shutdown', force ? { force: true } : {})
      setQuitting(true)
    } catch (e) {
      if (e instanceof ApiError && e.data.busy) {
        if (window.confirm(`${e.message}`)) return quit(true)
        return
      }
      setQuitting(true) // the server closed the connection on its way out: that is a success
    }
  }

  const tool = (title: string, icon: React.ReactNode, onClick: () => void, disabled = false) => (
    <Tooltip title={title} placement="right">
      <span>
        <IconButton size="small" onClick={onClick} disabled={disabled} sx={{ color: 'text.secondary' }}>
          {icon}
        </IconButton>
      </span>
    </Tooltip>
  )

  return (
    <>
      <Box
        component="nav"
        sx={{
          width: DRAWER_WIDTH,
          flexShrink: 0,
          position: 'sticky',
          top: 48,
          height: 'calc(100vh - 48px)',
          borderRight: '1px solid',
          borderColor: 'divider',
          bgcolor: 'background.paper',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          py: 1,
          gap: 0.5,
          overflowY: 'auto',
        }}
      >
        {SECTIONS.map((sec) => {
          const Icon = sec.icon
          return (
            <Tooltip key={sec.id} title={sec.sub} placement="right">
              <span>
                <RailButton label={sec.label} icon={<Icon fontSize="small" />} active={activeSection === sec.id} disabled={!raw} onClick={() => onSection(sec.id)} />
              </span>
            </Tooltip>
          )
        })}
        <Box sx={{ flexGrow: 1 }} />
        <Divider flexItem sx={{ mx: 1.5, my: 0.5 }} />
        {tool('历史版本：整份项目回到某一刻', <HistoryIcon fontSize="small" />, () => setHistoryOpen(true), !raw)}
        {tool('AI 助手', <AutoAwesomeIcon fontSize="small" />, () => setAiOpen(true))}
        {tool('分类管理', <CategoryIcon fontSize="small" />, () => setCategoryOpen(true))}
        {tool('系统状态', <MonitorHeartIcon fontSize="small" />, () => setStatusOpen(true))}
        {tool(mode === 'dark' ? '切换到浅色' : '切换到深色', mode === 'dark' ? <LightModeIcon fontSize="small" /> : <DarkModeIcon fontSize="small" />, onToggleMode)}
        {tool('退出 vidforge', <PowerSettingsNewIcon fontSize="small" />, () => quit())}
      </Box>
      <Dialog open={quitting}>
        <DialogContent>
          <Typography>vidforge 已退出，可以关掉这个页面了。再次使用请双击桌面的 vidforge 图标。</Typography>
        </DialogContent>
      </Dialog>
      <ProjectHistoryDialog open={historyOpen} onClose={() => setHistoryOpen(false)} />
      <CategoryManagerDialog open={categoryOpen} onClose={() => setCategoryOpen(false)} />
      <AiAssistantDrawer open={aiOpen} onClose={() => setAiOpen(false)} />
      <SystemStatusDialog open={statusOpen} onClose={() => setStatusOpen(false)} />
    </>
  )
}
