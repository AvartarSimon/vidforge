import { useState } from 'react'
import { Box, Button, Card, CardContent, MenuItem, Slider, Stack, TextField, Typography } from '@mui/material'
import { apiPost } from '../../../api/client'
import { useProject } from '../../../state/ProjectContext'
import { VoiceBrowserDialog } from './VoiceBrowserDialog'

const PROVIDERS = [
  { value: 'edge', label: 'edge（免费，微软神经语音）' },
  { value: 'elevenlabs', label: 'ElevenLabs（付费，需 key）' },
  { value: 'voxcpm', label: 'VoxCPM2（免费开源，本地跑，需自己装）' },
  { value: 'silent', label: '静音占位（只看画面，不联网）' },
]

export function VoiceSettingsCard({
  onFirstDone,
  onAllProgress,
  onAllDone,
}: {
  onFirstDone: (segId: string, audio: string, duration: number) => void
  onAllProgress: (text: string) => void
  onAllDone: () => void
}) {
  const { raw, patch, reload, saveNow } = useProject()
  const [browserOpen, setBrowserOpen] = useState(false)
  const [busyAll, setBusyAll] = useState(false)

  if (!raw) return null
  const provider = raw.tts?.provider || 'edge'
  const voice = raw.voice || ''
  const rate = parseInt(raw.rate || '+0%', 10) || 0
  const segments = raw.segments || []

  const setProvider = (v: string) =>
    patch((r) => {
      r.tts = r.tts || {}
      r.tts.provider = v
    })
  const setVoice = (v: string) =>
    patch((r) => {
      r.voice = v
    })
  const setRate = (v: number) =>
    patch((r) => {
      r.rate = `${v >= 0 ? '+' : ''}${v}%`
    })

  const ttsFirst = async () => {
    if (!segments.length) return
    if (!(await saveNow())) return // the backend synthesizes from the saved project.json, not in-memory edits
    const j = await apiPost<{ audio: string; duration: number }>(`/api/tts`, { id: segments[0].id })
    onFirstDone(segments[0].id, j.audio, j.duration)
  }

  const ttsAll = async () => {
    if (!(await saveNow())) return
    setBusyAll(true)
    for (let i = 0; i < segments.length; i++) {
      onAllProgress(`配音中 ${i + 1}/${segments.length}：${segments[i].id}`)
      try {
        await apiPost('/api/tts', { id: segments[i].id })
      } catch (e) {
        onAllProgress(`${segments[i].id}: ${e instanceof Error ? e.message : String(e)}`)
        break
      }
    }
    onAllProgress('')
    setBusyAll(false)
    onAllDone()
    await reload()
  }

  return (
    <Card variant="outlined">
      <CardContent>
        <Stack direction="row" spacing={2} flexWrap="wrap" useFlexGap>
          <TextField
            size="small"
            select
            label="配音服务"
            value={provider}
            onChange={(e) => setProvider(e.target.value)}
            sx={{ minWidth: 260 }}
          >
            {PROVIDERS.map((p) => (
              <MenuItem key={p.value} value={p.value}>
                {p.label}
              </MenuItem>
            ))}
          </TextField>
          <Box sx={{ minWidth: 280, flexGrow: 1 }}>
            <Stack direction="row" spacing={1}>
              <TextField
                size="small"
                label="声音"
                value={voice}
                onChange={(e) => setVoice(e.target.value)}
                placeholder="点「浏览」按口音/性别挑"
                fullWidth
              />
              <Button size="small" onClick={() => setBrowserOpen(true)}>
                浏览…
              </Button>
            </Stack>
          </Box>
        </Stack>
        <Box sx={{ mt: 2, maxWidth: 320 }}>
          <Typography variant="caption" color="text.secondary">
            语速 {rate >= 0 ? '+' : ''}
            {rate}%
          </Typography>
          <Slider size="small" min={-30} max={30} value={rate} onChange={(_, v) => setRate(v as number)} />
        </Box>
        <Stack direction="row" spacing={1} sx={{ mt: 1 }}>
          <Button onClick={ttsFirst} disabled={!segments.length}>
            ▶ 用第一段试听这个声音
          </Button>
          <Button variant="contained" onClick={ttsAll} disabled={busyAll || !segments.length}>
            全部配音
          </Button>
        </Stack>
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
          改了声音或语速后，所有段的配音都要重做（缓存按声音+文字区分，不会重复扣费同一段）。
        </Typography>
      </CardContent>
      <VoiceBrowserDialog
        open={browserOpen}
        provider={provider}
        sampleText={segments[0]?.text}
        onClose={() => setBrowserOpen(false)}
        onPick={(v) => {
          setVoice(v)
          setBrowserOpen(false)
        }}
      />
    </Card>
  )
}
