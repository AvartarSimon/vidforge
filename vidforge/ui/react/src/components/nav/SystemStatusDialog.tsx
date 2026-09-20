import { useEffect, useState } from 'react'
import {
  Button,
  Chip,
  Dialog,
  DialogContent,
  DialogTitle,
  Divider,
  IconButton,
  List,
  ListItem,
  ListItemText,
  Stack,
  TextField,
  Typography,
} from '@mui/material'
import CloseIcon from '@mui/icons-material/Close'
import { apiGet, apiPost } from '../../api/client'

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

// lets a key be pasted in and written straight to the *open project's* .env, instead of the
// user having to go find/create that file by hand — still never touches project.json or memory,
// same storage vidforge always used for keys (vidforge/env.py), just a friendlier way to fill it.
function ApiKeyRow({ name, description, set, onSaved }: { name: string; description: string; set: boolean; onSaved: () => void }) {
  const [value, setValue] = useState('')
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  const save = async () => {
    if (!value.trim()) return
    setSaving(true)
    setErr(null)
    try {
      await apiPost('/api/env', { key: name, value: value.trim() })
      setValue('')
      onSaved()
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e))
    }
    setSaving(false)
  }

  return (
    <Stack spacing={0.5} sx={{ py: 0.75 }}>
      <Stack direction="row" spacing={1} alignItems="center">
        <Typography variant="body2" sx={{ minWidth: 160 }}>
          {name}
        </Typography>
        <Chip size="small" label={set ? '已配置' : '未配置'} color={set ? 'success' : 'default'} variant={set ? 'filled' : 'outlined'} />
      </Stack>
      <Typography variant="caption" color="text.secondary">
        {description}
      </Typography>
      <Stack direction="row" spacing={1}>
        <TextField
          size="small"
          type="password"
          placeholder={set ? '重新粘贴以覆盖…' : '粘贴 key…'}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          fullWidth
        />
        <Button size="small" variant="outlined" disabled={saving || !value.trim()} onClick={save}>
          保存
        </Button>
      </Stack>
      {err && (
        <Typography variant="caption" color="error">
          {err}
        </Typography>
      )}
    </Stack>
  )
}

export function SystemStatusDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [h, setH] = useState<Health | null>(null)
  const [keyDescriptions, setKeyDescriptions] = useState<Record<string, string>>({})
  const [error, setError] = useState<string | null>(null)

  const loadHealth = () => apiGet<Health>('/api/health').then(setH).catch((e) => setError(e instanceof Error ? e.message : String(e)))

  useEffect(() => {
    if (!open) return
    loadHealth()
    apiGet<{ keys: Record<string, string> }>('/api/env/keys')
      .then((j) => setKeyDescriptions(j.keys))
      .catch(() => setKeyDescriptions({}))
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
            <StatusRow label="YouTube 上传授权" ok={h.youtube_secret} />
            <InfoRow label="CPU 核数" detail={String(h.cpus)} />
          </List>
        )}
        {h && (
          <>
            <Divider sx={{ my: 1.5 }} />
            <Typography variant="subtitle2" gutterBottom>
              API Keys（写入当前项目文件夹的 .env，不会进 project.json）
            </Typography>
            {Object.entries(keyDescriptions).map(([name, desc], i) => (
              <div key={name}>
                {i > 0 && <Divider />}
                <ApiKeyRow name={name} description={desc} set={!!h.keys[name]} onSaved={loadHealth} />
              </div>
            ))}
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}
