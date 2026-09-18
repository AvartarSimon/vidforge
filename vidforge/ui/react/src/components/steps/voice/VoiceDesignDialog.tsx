import { useState } from 'react'
import {
  Button,
  Dialog,
  DialogContent,
  DialogTitle,
  IconButton,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from '@mui/material'
import CloseIcon from '@mui/icons-material/Close'
import { apiPost } from '../../../api/client'
import { useProject } from '../../../state/ProjectContext'
import { fileUrl } from '../../../utils'

const VD_HINT: Record<string, string> = {
  elevenlabs:
    '⚠ 需要 .env 里配置 ELEVENLABS_API_KEY——没配的话点「生成」会在下面显示这一条报错，不是卡住或"找不到"。Voice Design 免费版账号（每月约 1 万 credits）应该就能试。',
  voxcpm:
    '⚠ 免费开源（Apache-2.0，可商用），但要你自己先在实际渲染的那台机器上装好：pip install voxcpm soundfile。没有独立显卡的话非常慢——实测纯 CPU 生成约 13 秒试听要 8.5 分钟。纯 CPU 默认只生成 1 个候选。',
}

interface Preview {
  id: string
  audio: string
}

export function VoiceDesignDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { patch } = useProject()
  const [provider, setProvider] = useState(() => (localStorage.getItem('vf.vd_provider') === 'voxcpm' ? 'voxcpm' : 'elevenlabs'))
  const [desc, setDesc] = useState(() => localStorage.getItem('vf.vd_desc') || '')
  const [sampleText, setSampleText] = useState('')
  const [busy, setBusy] = useState(false)
  const [status, setStatus] = useState('')
  const [previews, setPreviews] = useState<Preview[]>([])
  const [names, setNames] = useState<Record<string, string>>({})
  const [keeping, setKeeping] = useState<string | null>(null)

  const generate = async () => {
    if (!desc.trim()) return
    localStorage.setItem('vf.vd_desc', desc)
    localStorage.setItem('vf.vd_provider', provider)
    setBusy(true)
    setPreviews([])
    setStatus(provider === 'voxcpm' ? '本地生成中（比云端慢，可能几分钟）…' : '合成中（约 20–40 秒）…')
    try {
      const j = await apiPost<{ previews: Preview[] }>('/api/voice/design', { provider, desc, text: sampleText })
      setPreviews(j.previews)
      setStatus('')
    } catch (e) {
      setStatus(e instanceof Error ? e.message : String(e))
    }
    setBusy(false)
  }

  const keep = async (pv: Preview, i: number) => {
    setKeeping(pv.id)
    try {
      const name = names[pv.id] || `品牌旁白 ${i + 1}`
      const j = await apiPost<{ voice_id: string }>('/api/voice/keep', { provider, id: pv.id, name, desc })
      patch((r) => {
        r.voice = j.voice_id
        r.tts = r.tts || {}
        r.tts.provider = provider
      })
      onClose()
    } catch (e) {
      window.alert(e instanceof Error ? e.message : String(e))
    }
    setKeeping(null)
  }

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        设计品牌声音
        <IconButton size="small" onClick={onClose} aria-label="关闭">
          <CloseIcon fontSize="small" />
        </IconButton>
      </DialogTitle>
      <DialogContent dividers>
        <Stack spacing={1.5}>
          <Typography variant="caption" color="text.secondary">
            用文字描述想要的声音，合成几个候选（不克隆任何真人）。
          </Typography>
          <TextField select size="small" label="用哪个引擎" value={provider} onChange={(e) => setProvider(e.target.value)}>
            <MenuItem value="elevenlabs">ElevenLabs（云端，付费为主，更快更稳）</MenuItem>
            <MenuItem value="voxcpm">VoxCPM2（本地免费，需自己装，较慢）</MenuItem>
          </TextField>
          <Typography variant="caption" color="text.secondary">
            {VD_HINT[provider]}
          </Typography>
          <TextField
            label="声音描述"
            multiline
            minRows={3}
            value={desc}
            onChange={(e) => setDesc(e.target.value)}
            placeholder="例：四十岁左右的男声，低沉、温暖、有磁性，语速从容，像纪录片解说，带一点英式口音"
          />
          <TextField
            label="试听文本（可空，默认用一段解说样例；≥100 字符）"
            multiline
            minRows={2}
            value={sampleText}
            onChange={(e) => setSampleText(e.target.value)}
          />
          <Stack direction="row" spacing={1} alignItems="center">
            <Button variant="contained" onClick={generate} disabled={busy}>
              生成 {provider === 'voxcpm' ? 1 : 3} 个候选
            </Button>
            <Typography variant="caption" color="text.secondary">
              {status}
            </Typography>
          </Stack>
          {previews.map((pv, i) => (
            <Stack key={pv.id} direction="row" spacing={1} alignItems="center">
              <Typography variant="body2" fontWeight={600}>
                候选 {i + 1}
              </Typography>
              <audio controls src={fileUrl(pv.audio) || undefined} style={{ height: 32 }} />
              <TextField
                size="small"
                placeholder={`品牌旁白 ${i + 1}`}
                value={names[pv.id] || ''}
                onChange={(e) => setNames((n) => ({ ...n, [pv.id]: e.target.value }))}
              />
              <Button size="small" variant="contained" disabled={keeping === pv.id} onClick={() => keep(pv, i)}>
                保存并选用
              </Button>
            </Stack>
          ))}
        </Stack>
      </DialogContent>
    </Dialog>
  )
}
