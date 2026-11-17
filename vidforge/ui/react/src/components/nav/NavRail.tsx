import { useState } from 'react'
import { Box, ButtonBase, Dialog, DialogContent, Divider, Tooltip, Typography } from '@mui/material'
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
import EditNoteIcon from '@mui/icons-material/EditNote'
import RecordVoiceOverIcon from '@mui/icons-material/RecordVoiceOver'
import ImageIcon from '@mui/icons-material/Image'
import MovieIcon from '@mui/icons-material/Movie'
import IosShareIcon from '@mui/icons-material/IosShare'
import { ApiError, apiPost } from '../../api/client'
import type { ProjectView, RawProject } from '../../api/types'
import { useProject } from '../../state/ProjectContext'
import { ProjectHistoryDialog } from './ProjectHistoryDialog'
import { CategoryManagerDialog } from './CategoryManagerDialog'
import { AiAssistantDrawer } from './AiAssistantDrawer'
import { SystemStatusDialog } from './SystemStatusDialog'
import { IconTile, type Tone } from '../shared/ui'

export const DRAWER_WIDTH = 76

export const STEPS = [
  { n: 1, label: '脚本', sub: '写或生成旁白', icon: EditNoteIcon, tone: 'indigo' as Tone },
  { n: 2, label: '配音', sub: '声音与试听', icon: RecordVoiceOverIcon, tone: 'blue' as Tone },
  { n: 3, label: '画面', sub: '每段挑素材', icon: ImageIcon, tone: 'green' as Tone },
  { n: 4, label: '渲染', sub: '出片与主持人', icon: MovieIcon, tone: 'violet' as Tone },
  { n: 5, label: '发布', sub: '上传与声明', icon: IosShareIcon, tone: 'orange' as Tone },
]

// Work that is about one kind of material rather than about one step of this video: covering
// faces in a clip, managing voices, reviewing everything that was downloaded. Kept out of the
// wizard so it can be reached at any time and grown independently.
export const SECTIONS = [
  { id: 'editor', label: '剪辑台', sub: '时间线、预览、属性', icon: ViewTimelineIcon, tone: 'teal' as Tone },
  { id: 'studio', label: '录制', sub: '提词器、美颜、换背景', icon: VideocamIcon, tone: 'coral' as Tone },
  { id: 'trends', label: '热点', sub: '现在什么在火', icon: WhatshotIcon, tone: 'orange' as Tone },
  { id: 'video', label: '视频', sub: '剪口播、美化、遮脸', icon: MovieFilterIcon, tone: 'violet' as Tone },
  { id: 'voice', label: '声音', sub: '声音库与试听', icon: GraphicEqIcon, tone: 'blue' as Tone },
  { id: 'images', label: '图片', sub: '素材与授权', icon: PhotoLibraryIcon, tone: 'green' as Tone },
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
function RailButton({ label, icon, tone, active, disabled, small, onClick }: { label: string; icon: React.ReactNode; tone: Tone; active?: boolean; disabled?: boolean; small?: boolean; onClick: () => void }) {
  return (
    <ButtonBase
      onClick={onClick}
      disabled={disabled}
      sx={{
        width: 64,
        py: small ? 0.5 : 0.75,
        borderRadius: 2.5,
        flexDirection: 'column',
        gap: 0.4,
        color: active ? 'text.primary' : 'text.secondary',
        opacity: disabled ? 0.4 : 1,
        '&:hover': { bgcolor: 'action.hover', color: 'text.primary' },
      }}
    >
      <IconTile icon={icon} tone={tone} size={small ? 26 : 34} solid={active} />
      <Typography sx={{ fontSize: small ? 10.5 : 11.5, fontWeight: active ? 700 : 500, lineHeight: 1.2 }}>{label}</Typography>
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

  // the whole-app tools, each with its colour and a short name under it: six grey glyphs with
  // only a hover hint was the part of the rail nobody could read
  const tool = (label: string, title: string, icon: React.ReactNode, tone: Tone, onClick: () => void, disabled = false) => (
    <Tooltip title={title} placement="right">
      <span>
        <RailButton small label={label} icon={icon} tone={tone} disabled={disabled} onClick={onClick} />
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
                <RailButton label={sec.label} icon={<Icon />} tone={sec.tone} active={activeSection === sec.id} disabled={!raw} onClick={() => onSection(sec.id)} />
              </span>
            </Tooltip>
          )
        })}
        <Box sx={{ flexGrow: 1 }} />
        <Divider flexItem sx={{ mx: 1.5, my: 0.5 }} />
        {tool('历史', '历史版本：整份项目回到某一刻', <HistoryIcon />, 'slate', () => setHistoryOpen(true), !raw)}
        {tool('AI', 'AI 助手', <AutoAwesomeIcon />, 'violet', () => setAiOpen(true))}
        {tool('分类', '分类管理', <CategoryIcon />, 'amber', () => setCategoryOpen(true))}
        {tool('状态', '系统状态', <MonitorHeartIcon />, 'green', () => setStatusOpen(true))}
        {tool(mode === 'dark' ? '浅色' : '深色', mode === 'dark' ? '切换到浅色' : '切换到深色', mode === 'dark' ? <LightModeIcon /> : <DarkModeIcon />, 'indigo', onToggleMode)}
        {tool('退出', '退出 vidforge', <PowerSettingsNewIcon />, 'coral', () => quit())}
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
