import { useEffect, useMemo, useState } from 'react'
import {
  Button,
  Dialog,
  DialogContent,
  DialogTitle,
  IconButton,
  List,
  ListItem,
  ListItemText,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from '@mui/material'
import CloseIcon from '@mui/icons-material/Close'
import { apiGet, apiPost } from '../../../api/client'
import type { VoiceOption } from '../../../api/types'
import { fileUrl } from '../../../utils'

// same region-name lookup as the old frontend's voice browser (vidforge/ui/static/app.js)
const REGION: Record<string, string> = {
  'en-US': '美国', 'en-GB': '英国（伦敦）', 'en-AU': '澳大利亚', 'en-NZ': '新西兰', 'en-IE': '爱尔兰',
  'en-CA': '加拿大', 'en-IN': '印度', 'en-ZA': '南非', 'en-SG': '新加坡', 'en-HK': '香港英语',
  'en-PH': '菲律宾', 'en-NG': '尼日利亚', 'en-KE': '肯尼亚', 'en-TZ': '坦桑尼亚',
  'zh-CN': '普通话', 'zh-CN-liaoning': '东北话', 'zh-CN-shaanxi': '陕西关中话', 'zh-HK': '粤语',
  'zh-TW': '台湾国语', 'ja-JP': '日语', 'ko-KR': '韩语', 'de-DE': '德语', 'fr-FR': '法语', 'es-ES': '西班牙语',
}
const regionOf = (v: VoiceOption) => {
  const m = v.name.match(/^([a-z]{2}-[A-Z]{2}(?:-[a-z]+)?)/)
  return m ? m[1] : v.locale
}

export function VoiceBrowserDialog({
  open,
  provider,
  sampleText,
  onClose,
  onPick,
}: {
  open: boolean
  provider: string
  sampleText?: string
  onClose: () => void
  onPick: (voice: string) => void
}) {
  const [all, setAll] = useState<VoiceOption[]>([])
  const [error, setError] = useState<string | null>(null)
  const [langFilter, setLangFilter] = useState('')
  const [region, setRegion] = useState('')
  const [gender, setGender] = useState('')
  const [previewing, setPreviewing] = useState<string | null>(null)
  const [previewAudio, setPreviewAudio] = useState<Record<string, string>>({})

  useEffect(() => {
    if (!open) return
    setAll([])
    setError(null)
    apiGet<VoiceOption[]>(`/api/voices?provider=${provider}`)
      .then(setAll)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
  }, [open, provider])

  const regions = useMemo(() => [...new Set(all.map(regionOf))].sort(), [all])
  const rows = useMemo(
    () =>
      all.filter(
        (v) =>
          (!langFilter || v.locale.toLowerCase().startsWith(langFilter.toLowerCase())) &&
          (!region || regionOf(v) === region) &&
          (!gender || v.gender === gender),
      ),
    [all, langFilter, region, gender],
  )

  const preview = async (v: VoiceOption) => {
    setPreviewing(v.name)
    try {
      const j = await apiPost<{ audio: string }>('/api/voices/preview', {
        voice: v.name,
        provider,
        text: (sampleText || '').slice(0, 160),
      })
      setPreviewAudio((m) => ({ ...m, [v.name]: fileUrl(j.audio) || '' }))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
    setPreviewing(null)
  }

  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth>
      <DialogTitle sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        选择声音
        <IconButton onClick={onClose} size="small" aria-label="关闭">
          <CloseIcon fontSize="small" />
        </IconButton>
      </DialogTitle>
      <DialogContent dividers sx={{ maxHeight: '70vh' }}>
        <Stack direction="row" spacing={1.5} sx={{ mb: 1.5 }}>
          <TextField size="small" select label="地区筛选" value={region} onChange={(e) => setRegion(e.target.value)} sx={{ minWidth: 180 }}>
            <MenuItem value="">全部语言/地区</MenuItem>
            {regions.map((r) => (
              <MenuItem key={r} value={r}>
                {REGION[r] || r} ({r})
              </MenuItem>
            ))}
          </TextField>
          <TextField size="small" select label="性别" value={gender} onChange={(e) => setGender(e.target.value)} sx={{ minWidth: 140 }}>
            <MenuItem value="">男女都看</MenuItem>
            <MenuItem value="Female">女声</MenuItem>
            <MenuItem value="Male">男声</MenuItem>
          </TextField>
          <TextField
            size="small"
            label="语言前缀（如 en / zh）"
            value={langFilter}
            onChange={(e) => setLangFilter(e.target.value)}
            sx={{ minWidth: 160 }}
          />
          <Typography variant="body2" color="text.secondary" sx={{ alignSelf: 'center' }}>
            {rows.length} 个
          </Typography>
        </Stack>
        {error && (
          <Typography color="error" variant="body2" sx={{ mb: 1 }}>
            {error}
          </Typography>
        )}
        <List dense>
          {rows.map((v) => (
            <ListItem
              key={v.name}
              sx={{ borderRadius: 2, mb: 0.5, border: '1px solid', borderColor: 'divider' }}
              secondaryAction={
                <Stack direction="row" spacing={1} alignItems="center">
                  {previewAudio[v.name] && <audio controls src={previewAudio[v.name]} style={{ height: 30 }} />}
                  <Button size="small" disabled={previewing === v.name} onClick={() => preview(v)}>
                    ▶ 试听
                  </Button>
                  <Button size="small" variant="contained" onClick={() => onPick(v.name)}>
                    选用
                  </Button>
                </Stack>
              }
            >
              <ListItemText
                primary={v.name.replace(/Neural$/, '')}
                secondary={[REGION[regionOf(v)] || v.locale, v.gender === 'Female' ? '女' : v.gender === 'Male' ? '男' : '', (v.personalities || []).join(', ')]
                  .filter(Boolean)
                  .join(' · ')}
              />
            </ListItem>
          ))}
          {!rows.length && !error && (
            <Typography variant="body2" color="text.secondary">
              {all.length ? '没有匹配的声音' : '加载中…'}
            </Typography>
          )}
        </List>
      </DialogContent>
    </Dialog>
  )
}
