import { useEffect, useState } from 'react'
import {
  Alert,
  Button,
  Dialog,
  DialogContent,
  DialogTitle,
  IconButton,
  List,
  ListItem,
  ListItemText,
  Stack,
  Typography,
} from '@mui/material'
import CloseIcon from '@mui/icons-material/Close'
import { apiGet, apiPost } from '../../api/client'
import { useProject } from '../../state/ProjectContext'

type Snapshot = { name: string; time: string; size: number }

// Whole-project undo, as opposed to the per-segment history in SegmentHistoryDialog: this puts
// every segment back to how it was at one moment. Restoring takes a snapshot of the current state
// first, so changing your mind again is always possible.
const pretty = (stamp: string) => {
  const m = /^(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})(\d{2})/.exec(stamp)
  return m ? `${m[2]}-${m[3]} ${m[4]}:${m[5]}:${m[6]}` : stamp
}

export function ProjectHistoryDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { reload } = useProject()
  const [items, setItems] = useState<Snapshot[]>([])
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!open) return
    setError(null)
    apiGet<{ history: Snapshot[] }>('/api/history')
      .then((j) => setItems(j.history))
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
  }, [open])

  const restore = async (snap: Snapshot) => {
    if (!window.confirm(`回到 ${pretty(snap.time)} 的版本？当前内容会先存成一份新的历史，可以再退回来。`)) return
    setBusy(true)
    try {
      await apiPost('/api/history/restore', { name: snap.name })
      await reload()
      onClose()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
    setBusy(false)
  }

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        历史版本（整份项目）
        <IconButton onClick={onClose} size="small">
          <CloseIcon />
        </IconButton>
      </DialogTitle>
      <DialogContent>
        <Typography variant="caption" color="text.secondary">
          每次改动后自动留档（最多 30 份），保存在项目下的 <code>.history/</code>。
          只想回退某一段的话，用段落行上的「版本」。
        </Typography>
        {error && <Alert severity="error" sx={{ mt: 1 }}>{error}</Alert>}
        <List dense>
          {items.map((h) => (
            <ListItem
              key={h.name}
              secondaryAction={
                <Button size="small" disabled={busy} onClick={() => restore(h)}>
                  回到这一版
                </Button>
              }
            >
              <ListItemText primary={pretty(h.time)} secondary={`${(h.size / 1024).toFixed(1)} KB`} />
            </ListItem>
          ))}
        </List>
        {!items.length && !error && (
          <Stack sx={{ py: 2 }}>
            <Typography variant="body2" color="text.secondary">
              还没有历史版本——改动并保存之后就会出现。
            </Typography>
          </Stack>
        )}
      </DialogContent>
    </Dialog>
  )
}
