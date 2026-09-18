import { useEffect, useState } from 'react'
import {
  Avatar,
  Button,
  Dialog,
  DialogContent,
  DialogTitle,
  IconButton,
  List,
  ListItem,
  ListItemAvatar,
  ListItemText,
  Stack,
  TextField,
  Typography,
} from '@mui/material'
import CloseIcon from '@mui/icons-material/Close'
import { apiGet, apiPost } from '../../api/client'
import type { Category } from '../../api/types'

function avatarLetter(name: string) {
  return [...(name || '?')][0]?.toUpperCase() || '?'
}

export function CategoryManagerDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [categories, setCategories] = useState<Category[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [editing, setEditing] = useState<Category | null>(null) // null = list view, {} = new, Category = edit existing
  const [editName, setEditName] = useState('')
  const [editJson, setEditJson] = useState('')
  const [editError, setEditError] = useState<string | null>(null)

  const load = () => {
    setLoading(true)
    apiGet<{ categories: Category[] }>('/api/categories')
      .then((j) => setCategories(j.categories))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    if (open) {
      setEditing(null)
      load()
    }
  }, [open])

  const startEdit = (c: Category | null) => {
    const { name, id, ...rest } = c || ({} as Category)
    void id
    setEditName(name || '')
    setEditJson(JSON.stringify(rest, null, 2))
    setEditError(null)
    setEditing(c || ({} as Category))
  }

  const saveEdit = async () => {
    let rest: Record<string, unknown>
    try {
      rest = JSON.parse(editJson || '{}')
    } catch (e) {
      setEditError('JSON 有误：' + (e instanceof Error ? e.message : String(e)))
      return
    }
    if (!editName.trim()) {
      setEditError('需要一个名字')
      return
    }
    try {
      await apiPost('/api/categories', { ...rest, id: editing?.id, name: editName.trim() })
      setEditing(null)
      load()
    } catch (e) {
      setEditError(e instanceof Error ? e.message : String(e))
    }
  }

  const del = async (c: Category) => {
    if (!window.confirm(`删除分类「${c.name}」？（不影响已经用它建过的项目）`)) return
    try {
      const j = await apiPost<{ categories: Category[] }>('/api/categories/delete', { id: c.id })
      setCategories(j.categories)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        {editing === null ? '分类管理' : editing.id ? '编辑分类' : '新建分类'}
        <IconButton onClick={onClose} size="small">
          <CloseIcon fontSize="small" />
        </IconButton>
      </DialogTitle>
      <DialogContent dividers>
        {editing === null ? (
          <>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
              一个分类 = 一套写脚本/发布的设置和参考资料，跨项目复用。存成普通 JSON 文件（
              <code>~/.vidforge/categories/</code>），不是数据库。
            </Typography>
            <Button variant="contained" size="small" onClick={() => startEdit(null)} sx={{ mb: 1.5 }}>
              ＋ 新建分类
            </Button>
            {error && (
              <Typography color="error" variant="body2" sx={{ mb: 1 }}>
                {error}
              </Typography>
            )}
            {loading ? (
              <Typography variant="body2" color="text.secondary">
                加载中…
              </Typography>
            ) : (
              <List dense>
                {categories.map((c) => (
                  <ListItem
                    key={c.id}
                    sx={{ borderRadius: 2, mb: 0.5, border: '1px solid', borderColor: 'divider' }}
                    secondaryAction={
                      <Stack direction="row" spacing={0.5}>
                        <IconButton size="small" title="编辑" onClick={() => startEdit(c)}>
                          ✎
                        </IconButton>
                        <IconButton size="small" title="删除" onClick={() => del(c)}>
                          🗑
                        </IconButton>
                      </Stack>
                    }
                  >
                    <ListItemAvatar>
                      <Avatar sx={{ bgcolor: 'secondary.main' }}>{avatarLetter(c.name)}</Avatar>
                    </ListItemAvatar>
                    <ListItemText primary={c.name} secondary={c.id} />
                  </ListItem>
                ))}
                {!categories.length && (
                  <Typography variant="body2" color="text.secondary">
                    还没有分类。
                  </Typography>
                )}
              </List>
            )}
          </>
        ) : (
          <Stack spacing={1.5}>
            <TextField
              label="名字"
              size="small"
              value={editName}
              onChange={(e) => setEditName(e.target.value)}
              placeholder="例：中国古代历史人文 / FND"
            />
            <Typography variant="caption" color="text.secondary">
              其余设置（JSON——平台、参考账号、资料源、标签、心得、禁用关键词/平台把关规则、默认声音等，字段自己按需增减）
            </Typography>
            <TextField
              value={editJson}
              onChange={(e) => setEditJson(e.target.value)}
              multiline
              minRows={12}
              slotProps={{ htmlInput: { style: { fontFamily: 'ui-monospace,Consolas,monospace', fontSize: 12 } } }}
            />
            {editError && (
              <Typography color="error" variant="body2">
                {editError}
              </Typography>
            )}
            <Stack direction="row" spacing={1} justifyContent="flex-end">
              <Button onClick={() => setEditing(null)}>取消</Button>
              <Button variant="contained" onClick={saveEdit}>
                保存
              </Button>
            </Stack>
          </Stack>
        )}
      </DialogContent>
    </Dialog>
  )
}
