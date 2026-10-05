import { useEffect, useState } from 'react'
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  FormControlLabel,
  MenuItem,
  Slider,
  Stack,
  Switch,
  TextField,
  Typography,
} from '@mui/material'
import { apiGet, apiPost } from '../../../api/client'
import type { VoiceFxState } from '../../../api/types'
import { useProject } from '../../../state/ProjectContext'

/**
 * 人声处理. A preset is a matter of taste, so the panel's whole job is to let you *hear* the
 * difference: it renders the same sentence twice, once untouched and once through the chain, and
 * puts the two players side by side. Nothing is applied until you pick one.
 */
export function VoiceFxPanel({ onChanged }: { onChanged?: () => void }) {
  const { raw, patch, saveNow } = useProject()
  const [state, setState] = useState<VoiceFxState | null>(null)
  const [pair, setPair] = useState<{ before: string; after: string; preset: string } | null>(null)
  const [trying, setTrying] = useState('warm')
  const [busy, setBusy] = useState(false)
  const [pitch, setPitch] = useState(0)
  const [error, setError] = useState<string | null>(null)

  const load = () =>
    apiGet<VoiceFxState>('/api/voicefx')
      .then((j) => {
        setState(j)
        if (j.current !== 'none') setTrying(j.current)
      })
      .catch(() => setState(null))

  useEffect(() => {
    load()
  }, [])

  useEffect(() => {
    if (raw) setPitch(raw.voice_pitch ?? 0)
  }, [raw?.voice_pitch])

  if (!raw || !state) return null
  const current = raw.voice_fx || 'none'
  // a real take beats a synthesised sample: the point of a preset is what it does to *your* voice
  const source = state.own_segments[0]

  const preview = async () => {
    setBusy(true)
    setError(null)
    try {
      const j = await apiPost<{ before: string; after: string; preset: string }>('/api/voicefx/preview', {
        preset: trying,
        source,
      })
      setPair({
        before: `/files/${j.before}?t=${Date.now()}`,
        after: `/files/${j.after}?t=${Date.now()}`,
        preset: j.preset,
      })
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
    setBusy(false)
  }

  const apply = async (id: string) => {
    patch((r) => {
      r.voice_fx = id
    })
    await saveNow()
    await load()
    onChanged?.()
  }

  const applyPitch = async (v: number) => {
    patch((r) => {
      r.voice_pitch = v
    })
    await saveNow()
  }

  const toggleTrim = async (on: boolean) => {
    patch((r) => {
      r.narration_trim = on
    })
    await saveNow()
    await load()
  }

  return (
    <Card variant="outlined">
      <CardContent>
        <Typography variant="subtitle1" gutterBottom>
          🎛 人声处理
          <Chip
            size="small"
            sx={{ ml: 1 }}
            color={current === 'none' ? 'default' : 'primary'}
            label={state.presets.find((p) => p.id === current)?.name || current}
          />
        </Typography>
        <Typography variant="body2" color="text.secondary" gutterBottom>
          几条 ffmpeg 滤镜，不是机器学习：去低频轰鸣、降底噪、压缩让音量稳住，再按口味加一点低频或咬字。
          自己录的和合成的声音都会过这一层，响度统一（loudnorm）永远排在最后。
          {source ? '　试听用的是你自己的录音。' : '　还没有录音，试听会用当前 TTS 声音念一句。'}
        </Typography>

        <Stack direction="row" spacing={1.5} alignItems="center" flexWrap="wrap" useFlexGap sx={{ mt: 1 }}>
          <TextField
            size="small"
            select
            label="试听哪个预设"
            value={trying}
            onChange={(e) => setTrying(e.target.value)}
            sx={{ minWidth: 220 }}
          >
            {state.presets.map((p) => (
              <MenuItem key={p.id} value={p.id}>
                {p.name}
              </MenuItem>
            ))}
          </TextField>
          <Button size="small" onClick={preview} disabled={busy}>
            {busy ? '正在渲染…' : '试听对比'}
          </Button>
          <Button
            size="small"
            variant={current === trying ? 'contained' : 'outlined'}
            onClick={() => apply(trying)}
            disabled={current === trying}
          >
            {current === trying ? '正在用' : '用这个'}
          </Button>
          {current !== 'none' && (
            <Button size="small" color="inherit" onClick={() => apply('none')}>
              不处理
            </Button>
          )}
        </Stack>

        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
          {state.presets.find((p) => p.id === trying)?.about}
        </Typography>

        {pair && (
          <Stack direction="row" spacing={2} sx={{ mt: 1.5 }} flexWrap="wrap" useFlexGap>
            <Box sx={{ flex: '1 1 260px' }}>
              <Typography variant="caption" color="text.secondary">
                原声
              </Typography>
              <Box component="audio" src={pair.before} controls sx={{ width: '100%' }} />
            </Box>
            <Box sx={{ flex: '1 1 260px' }}>
              <Typography variant="caption" color="text.secondary">
                {state.presets.find((p) => p.id === pair.preset)?.name}
              </Typography>
              <Box component="audio" src={pair.after} controls sx={{ width: '100%' }} />
            </Box>
          </Stack>
        )}

        <Box sx={{ mt: 2, maxWidth: 420 }}>
          <Typography variant="body2" color="text.secondary">
            音高 {pitch > 0 ? '+' : ''}
            {pitch} 半音
            {pitch < 0 && '（更低沉）'}
            {pitch > 0 && '（更明亮）'}
          </Typography>
          <Slider
            size="small"
            value={pitch}
            min={-4}
            max={4}
            step={0.5}
            marks={[
              { value: -4, label: '-4' },
              { value: 0, label: '0' },
              { value: 4, label: '+4' },
            ]}
            onChange={(_, v) => setPitch(v as number)}
            onChangeCommitted={(_, v) => applyPitch(v as number)}
          />
          <Typography variant="caption" color="text.secondary">
            只改音高，<b>不改时长</b>（rubberband）——字幕的逐词时间是按这段音频量出来的，
            会拉伸时长的滤镜会把整条字幕轨推偏。实测 −1 半音得到 −0.97 半音。
            自己的声音偏年轻时，−1 到 −2 最有效；超过 ±4 就不像人声了。
          </Typography>
        </Box>

        <FormControlLabel
          sx={{ mt: 1 }}
          control={<Switch size="small" checked={state.trim} onChange={(e) => toggleTrim(e.target.checked)} />}
          label={
            <Typography variant="body2" color="text.secondary">
              自动掐掉录音首尾的静音（按下录音到开口说话那几秒）
            </Typography>
          }
        />

        {error && (
          <Alert severity="warning" sx={{ mt: 1 }}>
            {error}
          </Alert>
        )}
      </CardContent>
    </Card>
  )
}
