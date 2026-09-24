import { useState } from 'react'
import {
  Avatar,
  Box,
  Drawer,
  List,
  ListItemButton,
  ListItemAvatar,
  ListItemIcon,
  ListItemText,
  Toolbar,
  Typography,
  Divider,
  Dialog,
  DialogContent,
} from '@mui/material'
import type { PaletteMode } from '@mui/material'
import CategoryIcon from '@mui/icons-material/Category'
import FolderOpenIcon from '@mui/icons-material/FolderOpen'
import PowerSettingsNewIcon from '@mui/icons-material/PowerSettingsNew'
import MovieFilterIcon from '@mui/icons-material/MovieFilter'
import GraphicEqIcon from '@mui/icons-material/GraphicEq'
import PhotoLibraryIcon from '@mui/icons-material/PhotoLibrary'
import AutoAwesomeIcon from '@mui/icons-material/AutoAwesome'
import MonitorHeartIcon from '@mui/icons-material/MonitorHeart'
import DarkModeIcon from '@mui/icons-material/DarkMode'
import LightModeIcon from '@mui/icons-material/LightMode'
import { ApiError, apiPost } from '../../api/client'
import { useProject } from '../../state/ProjectContext'
import { ProjectSwitcher } from './ProjectSwitcher'
import { CategoryManagerDialog } from './CategoryManagerDialog'
import { AiAssistantDrawer } from './AiAssistantDrawer'
import { SystemStatusDialog } from './SystemStatusDialog'

export const DRAWER_WIDTH = 272

const STEPS = [
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
  { id: 'video', label: '视频', sub: '遮脸、我的镜头', icon: MovieFilterIcon },
  { id: 'voice', label: '声音', sub: '声音库与试听', icon: GraphicEqIcon },
  { id: 'images', label: '图片', sub: '素材与授权', icon: PhotoLibraryIcon },
] as const

export type SectionId = (typeof SECTIONS)[number]['id']

export function NavRail({
  activeStep,
  onStep,
  activeSection,
  onSection,
  mode,
  onToggleMode,
}: {
  activeStep: number
  onStep: (n: number) => void
  activeSection: SectionId | null
  onSection: (id: SectionId) => void
  mode: PaletteMode
  onToggleMode: () => void
}) {
  const { view, raw } = useProject()
  const [switcherOpen, setSwitcherOpen] = useState(false)
  const [categoryOpen, setCategoryOpen] = useState(false)
  const [aiOpen, setAiOpen] = useState(false)
  const [statusOpen, setStatusOpen] = useState(false)
  const [quitting, setQuitting] = useState(false)

  // Closing the browser tab leaves the server running — which is how an instance from days ago
  // ends up serving today's page over yesterday's routes. Give it an explicit off switch.
  const quit = async (force = false) => {
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

  const title = raw?.title || (view?.root ? view.root.split(/[\\/]/).pop() : null) || '未打开项目'
  const path = view?.root || ''

  return (
    <>
      <Drawer
        variant="permanent"
        sx={{
          width: DRAWER_WIDTH,
          flexShrink: 0,
          [`& .MuiDrawer-paper`]: { width: DRAWER_WIDTH, boxSizing: 'border-box' },
        }}
      >
        <Toolbar sx={{ px: 2 }}>
          <Typography variant="h6" fontWeight={700} color="primary">
            vidforge
          </Typography>
        </Toolbar>
        <Divider />
        <Box sx={{ p: 1.5 }}>
          <ListItemButton
            onClick={() => setSwitcherOpen(true)}
            sx={{ borderRadius: 2, border: '1px solid', borderColor: 'divider' }}
          >
            <ListItemAvatar>
              <Avatar sx={{ bgcolor: 'primary.main' }}>{[...title][0]?.toUpperCase() || '?'}</Avatar>
            </ListItemAvatar>
            <ListItemText
              primary={title}
              secondary={path}
              slotProps={{
                primary: { noWrap: true, fontWeight: 600 },
                secondary: { noWrap: true, fontSize: 12 },
              }}
            />
          </ListItemButton>
        </Box>
        <Divider />
        <List>
          {STEPS.map((s) => (
            <ListItemButton
              key={s.n}
              selected={activeSection === null && activeStep === s.n}
              disabled={!raw}
              onClick={() => onStep(s.n)}
            >
              <ListItemAvatar>
                <Avatar
                  sx={{
                    width: 30,
                    height: 30,
                    fontSize: 14,
                    bgcolor: activeStep === s.n ? 'primary.main' : 'action.selected',
                    color: activeStep === s.n ? 'primary.contrastText' : 'text.secondary',
                  }}
                >
                  {s.n}
                </Avatar>
              </ListItemAvatar>
              <ListItemText primary={s.label} secondary={s.sub} />
            </ListItemButton>
          ))}
        </List>
        <Divider />
        <List>
          {SECTIONS.map((sec) => {
            const Icon = sec.icon
            return (
              <ListItemButton
                key={sec.id}
                selected={activeSection === sec.id}
                disabled={!raw}
                onClick={() => onSection(sec.id)}
                sx={{ mx: 1, borderRadius: 2 }}
              >
                <ListItemIcon>
                  <Icon fontSize="small" />
                </ListItemIcon>
                <ListItemText primary={sec.label} secondary={sec.sub} />
              </ListItemButton>
            )
          })}
        </List>
        <Divider />
        <List sx={{ flexGrow: 1 }}>
          <ListItemButton onClick={() => setSwitcherOpen(true)} sx={{ mx: 1, borderRadius: 2 }}>
            <ListItemIcon>
              <FolderOpenIcon fontSize="small" />
            </ListItemIcon>
            <ListItemText primary="切换 / 新建项目" secondary="项目之间互不影响" />
          </ListItemButton>
          <ListItemButton onClick={() => setAiOpen(true)} sx={{ mx: 1, borderRadius: 2 }}>
            <ListItemIcon>
              <AutoAwesomeIcon fontSize="small" />
            </ListItemIcon>
            <ListItemText primary="AI 助手" />
          </ListItemButton>
          <ListItemButton onClick={() => setCategoryOpen(true)} sx={{ mx: 1, borderRadius: 2 }}>
            <ListItemIcon>
              <CategoryIcon fontSize="small" />
            </ListItemIcon>
            <ListItemText primary="分类管理" />
          </ListItemButton>
          <ListItemButton onClick={() => setStatusOpen(true)} sx={{ mx: 1, borderRadius: 2 }}>
            <ListItemIcon>
              <MonitorHeartIcon fontSize="small" />
            </ListItemIcon>
            <ListItemText primary="系统状态" />
          </ListItemButton>
        </List>
        <Divider />
        <ListItemButton onClick={() => quit()} sx={{ mx: 1, borderRadius: 2 }}>
          <ListItemIcon>
            <PowerSettingsNewIcon fontSize="small" />
          </ListItemIcon>
          <ListItemText primary="退出 vidforge" secondary="关网页不会停，从这里停" />
        </ListItemButton>
        <ListItemButton onClick={onToggleMode} sx={{ m: 1, borderRadius: 2 }}>
          <ListItemIcon>{mode === 'dark' ? <LightModeIcon fontSize="small" /> : <DarkModeIcon fontSize="small" />}</ListItemIcon>
          <ListItemText primary={mode === 'dark' ? '切换到浅色' : '切换到深色'} />
        </ListItemButton>
      </Drawer>
      <Dialog open={quitting}>
        <DialogContent>
          <Typography>vidforge 已退出，可以关掉这个页面了。再次使用请双击桌面的 vidforge 图标。</Typography>
        </DialogContent>
      </Dialog>
      <ProjectSwitcher open={switcherOpen} onClose={() => setSwitcherOpen(false)} />
      <CategoryManagerDialog open={categoryOpen} onClose={() => setCategoryOpen(false)} />
      <AiAssistantDrawer open={aiOpen} onClose={() => setAiOpen(false)} />
      <SystemStatusDialog open={statusOpen} onClose={() => setStatusOpen(false)} />
    </>
  )
}
