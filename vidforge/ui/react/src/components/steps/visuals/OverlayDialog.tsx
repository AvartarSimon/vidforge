import { useRef, useState } from 'react'
import {
  Button,
  Checkbox,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  IconButton,
  MenuItem,
  Slider,
  Stack,
  TextField,
  Typography,
} from '@mui/material'
import CloseIcon from '@mui/icons-material/Close'
import { apiPost } from '../../../api/client'
import type { Overlay, Segment } from '../../../api/types'

const POSITIONS = ['top-left', 'top', 'top-right', 'left', 'center', 'right', 'bottom-left', 'bottom', 'bottom-right']
const ANIMATIONS = [
  { value: 'slide', label: '滑入' },
  { value: 'fade', label: '淡入' },
  { value: 'none', label: '直接出现' },
]

function readAsBase64(f: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const rd = new FileReader()
    rd.onload = () => resolve((rd.result as string).split(',')[1])
    rd.onerror = reject
    rd.readAsDataURL(f)
  })
}

export function OverlayDialog({
  open,
  seg,
  existing,
  need,
  onClose,
  onSave,
}: {
  open: boolean
  seg: Segment
  existing: Overlay | null // null = adding a new one
  need: number
  onClose: () => void
  onSave: (o: Overlay) => void
}) {
  const base: Overlay = existing || { image: undefined, at: 0, position: 'bottom-right', size: 0.3, animate: 'slide', border: true }
  const [src, setSrc] = useState(base.image || base.video || '')
  const [position, setPosition] = useState(base.position || 'bottom-right')
  const [at, setAt] = useState(base.at ?? 0)
  const [duration, setDuration] = useState(base.duration)
  const [size, setSize] = useState(Math.round((base.size || 0.3) * 100))
  const [animate, setAnimate] = useState(base.animate || 'slide')
  const [border, setBorder] = useState(base.border !== false)
  const [uploaded, setUploaded] = useState<{ path: string; name: string }[]>([])
  const [error, setError] = useState<string | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  const candidates = [
    ...seg.clips.filter((c) => c.image || c.video).map((c) => (c.image || c.video) as string),
    ...uploaded.map((u) => u.path),
  ]

  const upload = async (f: File) => {
    try {
      const b64 = await readAsBase64(f)
      const j = await apiPost<{ path: string }>('/api/assets/upload', { name: f.name, data_b64: b64 })
      setUploaded((u) => [...u, { path: j.path, name: f.name }])
      setSrc(j.path)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  const save = () => {
    if (!src) {
      setError('先选素材')
      return
    }
    const isVideo = /\.(mp4|mov|mkv|webm|m4v)$/i.test(src)
    const nv: Overlay = { [isVideo ? 'video' : 'image']: src, at, position, size: size / 100, animate, border }
    if (duration && duration > 0) nv.duration = duration
    onSave(nv)
  }

  return (
    <Dialog open={open} onClose={onClose} maxWidth="xs" fullWidth>
      <DialogTitle sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        画中画
        <IconButton size="small" onClick={onClose} aria-label="关闭">
          <CloseIcon fontSize="small" />
        </IconButton>
      </DialogTitle>
      <DialogContent dividers>
        <Stack spacing={2}>
          <TextField select size="small" label="素材" value={src} onChange={(e) => (e.target.value === '__upload' ? fileRef.current?.click() : setSrc(e.target.value))}>
            {candidates.map((p) => (
              <MenuItem key={p} value={p}>
                {p.split('/').pop()}
              </MenuItem>
            ))}
            <MenuItem value="__upload">上传新文件…</MenuItem>
          </TextField>
          <input ref={fileRef} type="file" hidden accept="image/*,video/*" onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} />
          <TextField select size="small" label="位置" value={position} onChange={(e) => setPosition(e.target.value)}>
            {POSITIONS.map((p) => (
              <MenuItem key={p} value={p}>
                {p}
              </MenuItem>
            ))}
          </TextField>
          <TextField
            size="small"
            type="number"
            label={`出现于（秒，旁白约 ${need.toFixed(1)}s）`}
            value={at}
            onChange={(e) => setAt(parseFloat(e.target.value) || 0)}
          />
          <TextField
            size="small"
            type="number"
            label="持续（秒，空 = 到段末）"
            value={duration ?? ''}
            onChange={(e) => setDuration(parseFloat(e.target.value) || undefined)}
          />
          <div>
            <Typography variant="caption" color="text.secondary">
              宽度（画面的 {size}%）
            </Typography>
            <Slider size="small" min={10} max={60} value={size} onChange={(_, v) => setSize(v as number)} />
          </div>
          <TextField select size="small" label="进场" value={animate} onChange={(e) => setAnimate(e.target.value)}>
            {ANIMATIONS.map((a) => (
              <MenuItem key={a.value} value={a.value}>
                {a.label}
              </MenuItem>
            ))}
          </TextField>
          <FormControlLabel control={<Checkbox checked={border} onChange={(e) => setBorder(e.target.checked)} />} label="白边" />
          {error && <Typography color="error">{error}</Typography>}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button variant="contained" onClick={save}>
          {existing ? '保存' : '加入'}
        </Button>
      </DialogActions>
    </Dialog>
  )
}
