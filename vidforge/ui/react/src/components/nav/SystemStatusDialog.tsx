import { useEffect, useState } from 'react'
import { Chip, Dialog, DialogContent, DialogTitle, IconButton, List, ListItem, ListItemText, Typography } from '@mui/material'
import CloseIcon from '@mui/icons-material/Close'
import { apiGet } from '../../api/client'

interface Health {
  ffmpeg: { ok: boolean; path: string }
  encoder: string
  encoders: string[]
  node: boolean
  remotion: boolean
  keys: Record<string, boolean>
  youtube_secret: boolean
  cpus: number
  llm: { model: string; models: string[] } | null
}

function StatusRow({ label, ok, detail }: { label: string; ok: boolean; detail?: string }) {
  return (
    <ListItem>
      <ListItemText primary={label} secondary={detail} />
      <Chip size="small" label={ok ? '正常' : '缺失'} color={ok ? 'success' : 'default'} variant={ok ? 'filled' : 'outlined'} />
    </ListItem>
  )
}

function InfoRow({ label, detail }: { label: string; detail: string }) {
  return <ListItem><ListItemText primary={label} secondary={detail} /></ListItem>
}

export function SystemStatusDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [h, setH] = useState<Health | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return
    apiGet<Health>('/api/health')
      .then(setH)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
  }, [open])

  return (
    <Dialog open={open} onClose={onClose} maxWidth="xs" fullWidth>
      <DialogTitle sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        系统状态
        <IconButton size="small" onClick={onClose} aria-label="关闭">
          <CloseIcon fontSize="small" />
        </IconButton>
      </DialogTitle>
      <DialogContent dividers>
        {error && <Typography color="error">{error}</Typography>}
        {!h && !error && <Typography color="text.secondary">检查中…</Typography>}
        {h && (
          <List dense>
            <StatusRow label="ffmpeg" ok={h.ffmpeg.ok} detail={h.ffmpeg.path} />
            <InfoRow label="视频编码器" detail={`当前：${h.encoder} · 可选：${h.encoders.join(', ')}`} />
            <StatusRow label="Node.js（Remotion 动画）" ok={h.node} />
            <StatusRow label="Remotion" ok={h.remotion} />
            <StatusRow label="本地大模型" ok={!!h.llm} detail={h.llm?.model} />
            <StatusRow label="Pexels API key" ok={!!h.keys.PEXELS_API_KEY} />
            <StatusRow label="Pixabay API key" ok={!!h.keys.PIXABAY_API_KEY} />
            <StatusRow label="ElevenLabs API key" ok={!!h.keys.ELEVENLABS_API_KEY} />
            <StatusRow label="YouTube 上传授权" ok={h.youtube_secret} />
            <InfoRow label="CPU 核数" detail={String(h.cpus)} />
          </List>
        )}
      </DialogContent>
    </Dialog>
  )
}
