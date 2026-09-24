import { useEffect, useState } from 'react'
import {
  Avatar,
  Button,
  Dialog,
  DialogContent,
  DialogTitle,
  Divider,
  IconButton,
  List,
  ListItem,
  ListItemAvatar,
  ListItemText,
  Stack,
  TextField,
  Typography,
  Chip,
} from '@mui/material'
import CloseIcon from '@mui/icons-material/Close'
import OpenInNewIcon from '@mui/icons-material/OpenInNew'
import { apiGet, apiPost } from '../../api/client'
import type { RecentProject } from '../../api/types'
import { useProject } from '../../state/ProjectContext'

export function ProjectSwitcher({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { view, saveState, reload } = useProject()
  const [projects, setProjects] = useState<RecentProject[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [newName, setNewName] = useState('')
  const [newTitle, setNewTitle] = useState('')
  const [filter, setFilter] = useState('')
  const [job, setJob] = useState<{ state: string; project: string; title: string; done: number; total: number } | null>(null)

  useEffect(() => {
    if (!open) return
    setLoading(true)
    apiGet<{ projects: RecentProject[] }>('/api/projects')
      .then((j) => setProjects(j.projects))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
    // a picture run takes minutes and keeps going after a switch — say so instead of letting the
    // user wonder whether leaving the page kills it
    apiGet<{ state: string; project: string; title: string; done: number; total: number }>('/api/autofill')
      .then(setJob)
      .catch(() => setJob(null))
  }, [open])

  const shown = projects.filter((p) => {
    const q = filter.trim().toLowerCase()
    return !q || `${p.title || ''} ${p.path}`.toLowerCase().includes(q)
  })

  const switchTo = async (path: string) => {
    if (saveState === 'dirty' || saveState === 'saving') {
      if (!window.confirm('当前项目有未保存的改动，切换会丢失。确定切换吗？')) return
    }
    // the autofill job writes to the project it started on, so switching never disturbs it
    try {
      await apiPost('/api/open', { path })
      onClose()
      await reload()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  const openParallel = async (path: string) => {
    try {
      const j = await apiPost<{ url: string }>('/api/instances/spawn', { path })
      window.open(j.url, '_blank')
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  const createNew = async () => {
    try {
      await apiPost('/api/new', { name: newName, title: newTitle })
      setNewName('')
      setNewTitle('')
      onClose()
      await reload()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        项目
        <IconButton onClick={onClose} size="small" aria-label="关闭">
          <CloseIcon fontSize="small" />
        </IconButton>
      </DialogTitle>
      <DialogContent dividers>
        <TextField
          size="small"
          fullWidth
          autoFocus
          placeholder="搜索项目（名字或路径）"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          sx={{ mb: 1.5 }}
        />
        {job?.state === 'running' && (
          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1 }}>
            ⏳「{job.title || job.project.split(/[\\/]/).pop()}」正在后台配图（{job.done}/{job.total} 段）——
            切换项目不会打断它，它只写回自己的项目。
          </Typography>
        )}

        {error && (
          <Typography color="error" variant="body2" sx={{ mb: 1 }}>
            {error}
          </Typography>
        )}
        <Typography variant="subtitle2" gutterBottom>
          新建项目
        </Typography>
        <Stack direction="row" spacing={1} sx={{ mb: 2 }}>
          <TextField
            size="small"
            placeholder="项目文件夹名"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            fullWidth
          />
          <TextField
            size="small"
            placeholder="视频标题（可后改）"
            value={newTitle}
            onChange={(e) => setNewTitle(e.target.value)}
            fullWidth
          />
          <Button variant="contained" onClick={createNew} sx={{ whiteSpace: 'nowrap' }}>
            创建
          </Button>
        </Stack>
        <Divider sx={{ mb: 1 }} />
        <Typography variant="subtitle2" gutterBottom>
          最近的项目
        </Typography>
        {loading ? (
          <Typography variant="body2" color="text.secondary">
            加载中…
          </Typography>
        ) : (
          <List dense>
            {shown.map((pr) => {
              const current = view?.root === pr.path
              return (
                <ListItem
                  key={pr.path}
                  sx={{ borderRadius: 2, mb: 0.5, border: '1px solid', borderColor: 'divider' }}
                  secondaryAction={
                    <Stack direction="row" spacing={1}>
                      {current && <Chip label="当前" size="small" color="primary" variant="outlined" />}
                      <Button size="small" onClick={() => switchTo(pr.path)} disabled={current}>
                        切换
                      </Button>
                      <IconButton size="small" title="并行开一个新窗口" onClick={() => openParallel(pr.path)}>
                        <OpenInNewIcon fontSize="small" />
                      </IconButton>
                    </Stack>
                  }
                >
                  <ListItemAvatar>
                    <Avatar sx={{ bgcolor: 'secondary.main' }}>{[...pr.title][0]?.toUpperCase() || '?'}</Avatar>
                  </ListItemAvatar>
                  <ListItemText
                    primary={pr.title}
                    secondary={pr.path}
                    slotProps={{ primary: { noWrap: true }, secondary: { noWrap: true, fontSize: 11 } }}
                  />
                </ListItem>
              )
            })}
            {!projects.length && (
              <Typography variant="body2" color="text.secondary">
                还没有项目。
              </Typography>
            )}
          </List>
        )}
      </DialogContent>
    </Dialog>
  )
}
