import { useEffect, useState } from 'react'
import {
  Button,
  Dialog,
  DialogContent,
  DialogTitle,
  IconButton,
  List,
  ListItem,
  ListItemText,
  Typography,
} from '@mui/material'
import CloseIcon from '@mui/icons-material/Close'
import { apiGet, apiPost } from '../../api/client'
import { useProject } from '../../state/ProjectContext'

interface Version {
  name: string
  time: string
  preview: string
  clips: number
  label: string | null
}

// shared by step 1 (script) and step 3 (visuals) — "版本" button next to a segment. Every save
// that actually changed this segment leaves one snapshot; restoring only touches this segment.
export function SegmentHistoryDialog({ segId, open, onClose }: { segId: string | null; open: boolean; onClose: () => void }) {
  const { saveNow, reload } = useProject()
  const [versions, setVersions] = useState<Version[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [restoring, setRestoring] = useState<string | null>(null)

  useEffect(() => {
    if (!open || !segId) return
    setLoading(true)
    setError(null)
    // snapshot the current state first, so "now" also shows up as a version to come back to
    saveNow(true)
      .then(() => apiGet<{ versions: Version[] }>(`/api/segment/history?id=${encodeURIComponent(segId)}`))
      .then((j) => setVersions(j.versions))
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, segId])

  const restore = async (name: string) => {
    if (!segId) return
    setRestoring(name)
    try {
      await apiPost('/api/segment/restore', { id: segId, name })
      await reload()
      onClose()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
    setRestoring(null)
  }

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        「{segId}」的版本（{versions.length}）
        <IconButton size="small" onClick={onClose} aria-label="关闭">
          <CloseIcon fontSize="small" />
        </IconButton>
      </DialogTitle>
      <DialogContent dividers>
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1 }}>
          每次保存时这一段有变化就会留一份；回到某一版只改这一段，其他段不动。
        </Typography>
        {error && <Typography color="error">{error}</Typography>}
        {loading && <Typography color="text.secondary">加载中…</Typography>}
        <List dense>
          {versions.map((v) => (
            <ListItem
              key={v.name}
              sx={{ borderRadius: 2, mb: 0.5, border: '1px solid', borderColor: 'divider' }}
              secondaryAction={
                <Button size="small" disabled={restoring === v.name} onClick={() => restore(v.name)}>
                  恢复到这一版
                </Button>
              }
            >
              <ListItemText
                primary={`${v.time}${v.label ? ' · ' + v.label : ''}`}
                secondary={`${v.preview}${v.clips ? ` · ${v.clips} 个片段` : ''}`}
              />
            </ListItem>
          ))}
          {!loading && !versions.length && <Typography color="text.secondary">还没有历史版本。</Typography>}
        </List>
      </DialogContent>
    </Dialog>
  )
}
