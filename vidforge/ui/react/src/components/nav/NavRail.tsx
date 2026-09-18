import { useState } from 'react'
import {
  Avatar,
  Box,
  Chip,
  Drawer,
  List,
  ListItemButton,
  ListItemAvatar,
  ListItemIcon,
  ListItemText,
  Toolbar,
  Typography,
  Divider,
} from '@mui/material'
import CategoryIcon from '@mui/icons-material/Category'
import { useProject } from '../../state/ProjectContext'
import { ProjectSwitcher } from './ProjectSwitcher'
import { CategoryManagerDialog } from './CategoryManagerDialog'

export const DRAWER_WIDTH = 272

const STEPS = [
  { n: 1, label: '脚本', sub: '写或生成旁白' },
  { n: 2, label: '配音', sub: '声音与试听' },
  { n: 3, label: '画面', sub: '每段挑素材' },
  { n: 4, label: '渲染', sub: '出片与主持人' },
  { n: 5, label: '发布', sub: '上传与声明' },
]

// steps built out so far in this React frontend — the rest still show as "即将推出" placeholders
const IMPLEMENTED = new Set([1, 2, 3])

export function NavRail({ activeStep, onStep }: { activeStep: number; onStep: (n: number) => void }) {
  const { view, raw } = useProject()
  const [switcherOpen, setSwitcherOpen] = useState(false)
  const [categoryOpen, setCategoryOpen] = useState(false)

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
        <List sx={{ flexGrow: 1 }}>
          {STEPS.map((s) => (
            <ListItemButton
              key={s.n}
              selected={activeStep === s.n}
              disabled={!IMPLEMENTED.has(s.n) || !raw}
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
              {!IMPLEMENTED.has(s.n) && <Chip label="即将推出" size="small" variant="outlined" />}
            </ListItemButton>
          ))}
        </List>
        <Divider />
        <ListItemButton onClick={() => setCategoryOpen(true)} sx={{ m: 1, borderRadius: 2 }}>
          <ListItemIcon>
            <CategoryIcon fontSize="small" />
          </ListItemIcon>
          <ListItemText primary="分类管理" />
        </ListItemButton>
      </Drawer>
      <ProjectSwitcher open={switcherOpen} onClose={() => setSwitcherOpen(false)} />
      <CategoryManagerDialog open={categoryOpen} onClose={() => setCategoryOpen(false)} />
    </>
  )
}
