import { useEffect, useRef, useState } from 'react'
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
import { useProject } from '../../state/ProjectContext'
import { CategoryEditorForm } from './CategoryEditorForm'

function avatarLetter(name: string) {
  return [...(name || '?')][0]?.toUpperCase() || '?'
}

export function CategoryManagerDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { reload } = useProject()
  const [categories, setCategories] = useState<Category[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [editing, setEditing] = useState<Category | null | undefined>(undefined) // undefined = list, null = new, Category = edit existing
  const [creatingFrom, setCreatingFrom] = useState<Category | null>(null) // "＋ 新建项目" from this category
  const [newName, setNewName] = useState('')
  const [newTitle, setNewTitle] = useState('')
  const [creating, setCreating] = useState(false)
  const importRef = useRef<HTMLInputElement>(null)

  const load = () => {
    setLoading(true)
    apiGet<{ categories: Category[] }>('/api/categories')
      .then((j) => setCategories(j.categories))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    if (open) {
      setEditing(undefined)
      setCreatingFrom(null)
      load()
    }
  }, [open])

  const saveEdit = async (rec: Category) => {
    await apiPost('/api/categories', rec)
    setEditing(undefined)
    load()
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

  const exportAll = async () => {
    const j = await apiGet<unknown>('/api/categories/export')
    await navigator.clipboard.writeText(JSON.stringify(j, null, 2))
    window.alert('已复制到剪贴板（JSON），粘贴到一个 .json 文件保存即可；导入时选择这个文件。')
  }

  const importFile = async (f: File) => {
    let data: unknown
    try {
      data = JSON.parse(await f.text())
    } catch {
      window.alert('不是有效的 JSON 文件')
      return
    }
    const merge = window.confirm('合并到现有分类？（确定 = 合并/按 id 覆盖同名分类，取消 = 替换全部现有分类）')
    try {
      const j = await apiPost<{ categories: Category[]; imported: number }>('/api/categories/import', { data, merge })
      window.alert(`导入了 ${j.imported} 个分类。`)
      setCategories(j.categories)
    } catch (e) {
      window.alert(e instanceof Error ? e.message : String(e))
    }
  }

  const startCreate = (c: Category) => {
    setCreatingFrom(c)
    setNewName('')
    setNewTitle('')
  }

  const submitCreate = async () => {
    if (!creatingFrom) return
    setCreating(true)
    try {
      await apiPost('/api/new', { name: newName, title: newTitle, category: creatingFrom.id })
      await reload()
      onClose()
    } catch (e) {
      window.alert(e instanceof Error ? e.message : String(e))
    }
    setCreating(false)
  }

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        {editing === undefined ? (creatingFrom ? `用「${creatingFrom.name}」新建项目` : '分类管理') : editing === null ? '新建分类' : '编辑分类'}
        <IconButton onClick={onClose} size="small" aria-label="关闭">
          <CloseIcon fontSize="small" />
        </IconButton>
      </DialogTitle>
      <DialogContent dividers>
        {creatingFrom ? (
          <Stack spacing={1.5}>
            <Typography variant="body2" color="text.secondary">
              会带入这个分类的默认声音/语言/字幕等设置，写脚本时也会把分类的参考资料一起给 AI。
            </Typography>
            <TextField size="small" label="项目文件夹名" value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="例：year-without-a-summer" />
            <TextField size="small" label="视频标题（可后改）" value={newTitle} onChange={(e) => setNewTitle(e.target.value)} />
            <Stack direction="row" spacing={1} justifyContent="flex-end">
              <Button onClick={() => setCreatingFrom(null)}>取消</Button>
              <Button variant="contained" disabled={creating} onClick={submitCreate}>
                创建并打开
              </Button>
            </Stack>
          </Stack>
        ) : editing === undefined ? (
          <>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
              一个分类 = 一套写脚本/发布的设置和参考资料，跨项目复用。存成普通 JSON 文件（
              <code>~/.vidforge/categories/</code>），不是数据库——所以可以直接拷文件备份，或用导出/导入在两台机器间同步。
            </Typography>
            <Stack direction="row" spacing={1} sx={{ mb: 1.5 }}>
              <Button variant="contained" size="small" onClick={() => setEditing(null)}>
                ＋ 新建分类
              </Button>
              <Button size="small" onClick={exportAll}>
                导出全部…
              </Button>
              <Button size="small" onClick={() => importRef.current?.click()}>
                导入…
              </Button>
              <input
                ref={importRef}
                type="file"
                hidden
                accept="application/json"
                onChange={(e) => e.target.files?.[0] && importFile(e.target.files[0])}
              />
            </Stack>
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
                        <Button size="small" variant="outlined" onClick={() => startCreate(c)}>
                          ＋ 新建项目
                        </Button>
                        <IconButton size="small" title="编辑" onClick={() => setEditing(c)}>
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
                    <ListItemText primary={c.name} secondary={`${c.id}${c.updated ? ' · 更新于 ' + c.updated : ''}`} />
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
          <CategoryEditorForm initial={editing} onCancel={() => setEditing(undefined)} onSave={saveEdit} />
        )}
      </DialogContent>
    </Dialog>
  )
}
