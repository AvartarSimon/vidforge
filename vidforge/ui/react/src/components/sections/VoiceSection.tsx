import { useEffect, useState } from 'react'
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  IconButton,
  MenuItem,
  Select,
  Stack,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material'
import ContentCopyIcon from '@mui/icons-material/ContentCopy'
import { apiGet, apiPost } from '../../api/client'
import { useProject } from '../../state/ProjectContext'

type Voice = { name: string; locale?: string; gender?: string; personality?: string; desc?: string }

const PROVIDERS = [
  { id: 'edge', label: 'Edge 神经网络声音（免费，无需 key）' },
  { id: 'voxcpm', label: 'VoxCPM2 设计的声音（本地保存）' },
  { id: 'elevenlabs', label: 'ElevenLabs（需要 key）' },
]

// All voice work in one place: which voices exist, what the project uses, and how to try one.
export function VoiceSection() {
  const { raw, patch, saveNow } = useProject()
  const [provider, setProvider] = useState('edge')
  const [lang, setLang] = useState('zh')
  const [voices, setVoices] = useState<Voice[]>([])
  const [error, setError] = useState<string | null>(null)
  const [sample, setSample] = useState('这是一段试听，用来判断语速和音色是否合适。')
  const [audio, setAudio] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    setError(null)
    apiGet<Voice[]>(`/api/voices?provider=${provider}&lang=${provider === 'edge' ? lang : ''}`)
      .then(setVoices)
      .catch((e) => {
        setVoices([])
        setError(e instanceof Error ? e.message : String(e))
      })
  }, [provider, lang])

  const use = async (name: string) => {
    patch((r) => {
      r.voice = name
    })
    await saveNow()
  }

  const preview = async (name: string) => {
    setBusy(true)
    setError(null)
    try {
      const j = await apiPost<{ audio: string }>('/api/voices/preview', { voice: name, provider, text: sample })
      setAudio(`/files/${j.audio}?t=${Date.now()}`)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
    setBusy(false)
  }

  return (
    <Stack spacing={2}>
      <Typography variant="h6">声音</Typography>
      <Typography variant="body2" color="text.secondary">
        项目当前的声音：<code>{raw?.voice || '(未设置)'}</code>
        {raw?.rate ? `　语速 ${raw.rate}` : ''}
      </Typography>

      <Card variant="outlined">
        <CardContent>
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap alignItems="center">
            <Select size="small" value={provider} onChange={(e) => setProvider(e.target.value)} sx={{ minWidth: 300 }}>
              {PROVIDERS.map((p) => (
                <MenuItem key={p.id} value={p.id}>
                  {p.label}
                </MenuItem>
              ))}
            </Select>
            {provider === 'edge' && (
              <TextField size="small" label="语言前缀" value={lang} onChange={(e) => setLang(e.target.value)} sx={{ width: 120 }} />
            )}
            <TextField
              size="small"
              label="试听文字"
              value={sample}
              onChange={(e) => setSample(e.target.value)}
              sx={{ flexGrow: 1, minWidth: 260 }}
            />
          </Stack>
          {error && (
            <Alert severity="warning" sx={{ mt: 1 }}>
              {error}
            </Alert>
          )}
          {audio && <Box component="audio" src={audio} controls sx={{ mt: 1, width: '100%' }} />}
        </CardContent>
      </Card>

      <Card variant="outlined">
        <CardContent>
          <Typography variant="subtitle1" gutterBottom>
            {provider === 'voxcpm' ? '我设计的声音' : '可用声音'}（{voices.length}）
          </Typography>
          {provider === 'voxcpm' && (
            <Typography variant="body2" color="text.secondary" gutterBottom>
              VoxCPM2 的声音 = 一段描述 + 一个随机种子，保存在 <code>~/.vidforge/voices/voxcpm/&lt;名字&gt;.json</code>。
              把那个文件拷到别的电脑就能用同一个声音；脱离 vidforge 用 <code>tools/say.py</code>。
            </Typography>
          )}
          <Stack spacing={0.5} sx={{ maxHeight: '55vh', overflowY: 'auto' }}>
            {voices.map((v) => (
              <Stack key={v.name} direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                <Typography variant="body2" sx={{ minWidth: 220, fontWeight: raw?.voice === v.name ? 700 : 400 }}>
                  {v.name}
                </Typography>
                {v.locale && <Chip size="small" label={v.locale} variant="outlined" />}
                {v.gender && <Chip size="small" label={v.gender === 'Female' ? '女' : '男'} variant="outlined" />}
                <Typography variant="caption" color="text.secondary" sx={{ flexGrow: 1 }}>
                  {v.personality || v.desc || ''}
                </Typography>
                <Tooltip title="复制名字">
                  <IconButton size="small" onClick={() => navigator.clipboard?.writeText(v.name)}>
                    <ContentCopyIcon fontSize="inherit" />
                  </IconButton>
                </Tooltip>
                <Button size="small" onClick={() => preview(v.name)} disabled={busy}>
                  试听
                </Button>
                <Button size="small" variant={raw?.voice === v.name ? 'contained' : 'outlined'} onClick={() => use(v.name)}>
                  {raw?.voice === v.name ? '正在用' : '设为本项目声音'}
                </Button>
              </Stack>
            ))}
            {!voices.length && !error && (
              <Typography variant="body2" color="text.secondary">
                这个引擎下还没有声音。VoxCPM2 的声音在第 2 步「✨ 设计品牌声音…」里创建。
              </Typography>
            )}
          </Stack>
        </CardContent>
      </Card>
    </Stack>
  )
}
