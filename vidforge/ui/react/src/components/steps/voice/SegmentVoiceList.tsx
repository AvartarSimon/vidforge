import { useState } from 'react'
import { Box, Button, Card, CardContent, Stack, Typography } from '@mui/material'
import { apiPost } from '../../../api/client'
import { useProject } from '../../../state/ProjectContext'
import { fileUrl, fmtDuration } from '../../../utils'
import { VoiceBrowserDialog } from './VoiceBrowserDialog'

interface AudioInfo {
  audio: string | null
  duration: number | null
  fresh: boolean
}

export function SegmentVoiceList({
  overrides,
  setOverride,
}: {
  overrides: Record<string, AudioInfo>
  setOverride: (segId: string, info: AudioInfo) => void
}) {
  const { raw, view, patch, saveNow } = useProject()
  const [busy, setBusy] = useState<string | null>(null)
  const [browserFor, setBrowserFor] = useState<string | null>(null)

  if (!raw) return null
  const segments = raw.segments || []
  const resolved = view?.resolved || {}
  const provider = raw.tts?.provider || 'edge'

  const ttsOne = async (segId: string) => {
    if (!(await saveNow())) return
    setBusy(segId)
    try {
      const j = await apiPost<{ audio: string; duration: number }>('/api/tts', { id: segId })
      setOverride(segId, { audio: j.audio, duration: j.duration, fresh: true })
    } catch (e) {
      window.alert(e instanceof Error ? e.message : String(e))
    }
    setBusy(null)
  }

  const clearVoice = (segId: string) => {
    patch((r) => {
      const s = r.segments.find((x) => x.id === segId)
      if (s) delete s.voice
    })
  }

  return (
    <Card variant="outlined">
      <CardContent>
        <Stack spacing={1}>
          {segments.map((s) => {
            const r = resolved[s.id] || {}
            const info = overrides[s.id] || { audio: r.audio ?? null, duration: r.duration ?? null, fresh: r.audio_fresh ?? true }
            return (
              <Stack
                key={s.id}
                direction="row"
                spacing={2}
                alignItems="center"
                sx={{ p: 1, border: '1px solid', borderColor: 'divider', borderRadius: 2 }}
              >
                <Typography variant="body2" fontWeight={600} sx={{ width: 80, flexShrink: 0 }}>
                  {s.id}
                </Typography>
                <Typography variant="body2" color="text.secondary" sx={{ flexGrow: 1, minWidth: 0 }} noWrap>
                  {s.text}
                </Typography>
                {info.audio ? (
                  <audio controls preload="none" src={fileUrl(info.audio, info.duration) || undefined} style={{ height: 32 }} />
                ) : (
                  <Typography variant="caption" color="text.secondary">
                    尚未配音
                  </Typography>
                )}
                <Typography
                  variant="caption"
                  color={info.fresh ? 'text.secondary' : 'warning.main'}
                  title={info.fresh ? '' : '文字改过，需重新配音'}
                  sx={{ width: 60, flexShrink: 0 }}
                >
                  {fmtDuration(info.duration)}
                  {info.audio && !info.fresh ? ' ⟳' : ''}
                </Typography>
                {s.voice && (
                  <Typography variant="caption" color="text.secondary">
                    声音：{s.voice}{' '}
                    <Button size="small" onClick={() => clearVoice(s.id)} title="恢复全局声音">
                      ×
                    </Button>
                  </Typography>
                )}
                <Box sx={{ flexShrink: 0 }}>
                  <Button size="small" disabled={busy === s.id} onClick={() => ttsOne(s.id)}>
                    ▶ 试听
                  </Button>
                  <Button size="small" title="只给这一段换声音（引用、对话）" onClick={() => setBrowserFor(s.id)}>
                    换声
                  </Button>
                </Box>
              </Stack>
            )
          })}
        </Stack>
      </CardContent>
      <VoiceBrowserDialog
        open={!!browserFor}
        provider={provider}
        sampleText={segments.find((s) => s.id === browserFor)?.text}
        onClose={() => setBrowserFor(null)}
        onPick={(v) => {
          const segId = browserFor
          patch((r) => {
            const s = r.segments.find((x) => x.id === segId)
            if (s) s.voice = v
          })
          setBrowserFor(null)
        }}
      />
    </Card>
  )
}
