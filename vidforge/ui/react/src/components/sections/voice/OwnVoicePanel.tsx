import { useEffect, useRef, useState } from 'react'
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  IconButton,
  Stack,
  Tooltip,
  Typography,
} from '@mui/material'
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline'
import FiberManualRecordIcon from '@mui/icons-material/FiberManualRecord'
import StopIcon from '@mui/icons-material/Stop'
import UploadFileIcon from '@mui/icons-material/UploadFile'
import { apiGet, apiPost } from '../../../api/client'
import type { AlignResult, VoiceFxState } from '../../../api/types'
import { useProject } from '../../../state/ProjectContext'

/**
 * 用我自己的声音. Record a segment here, or drop in a file you recorded on your phone; the backend
 * force-aligns it to that segment's script (align.py) so the subtitles, the keyword highlighting
 * and the chapter marks stay exactly as accurate as they are with TTS.
 *
 * Recording happens per segment rather than for the whole video on purpose: a segment is one idea
 * and two to four sentences, which is about as much as anyone reads cleanly in one take — and a
 * fluffed line costs you that segment, not the whole script.
 */
export function OwnVoicePanel() {
  const { raw, reload } = useProject()
  const [state, setState] = useState<VoiceFxState | null>(null)
  const [recording, setRecording] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [aligned, setAligned] = useState<Record<string, AlignResult>>({})
  const [error, setError] = useState<string | null>(null)
  const recorder = useRef<MediaRecorder | null>(null)
  const chunks = useRef<Blob[]>([])

  const load = () => apiGet<VoiceFxState>('/api/voicefx').then(setState).catch(() => setState(null))

  useEffect(() => {
    load()
    return () => recorder.current?.stream.getTracks().forEach((t) => t.stop())
  }, [])

  if (!raw) return null
  const canRecord = typeof navigator !== 'undefined' && !!navigator.mediaDevices?.getUserMedia

  const upload = async (segId: string, blob: Blob, ext: string) => {
    setBusy(segId)
    setError(null)
    try {
      const buf = new Uint8Array(await blob.arrayBuffer())
      let bin = ''
      // chunked so a long take does not blow the argument limit of String.fromCharCode
      for (let i = 0; i < buf.length; i += 0x8000) bin += String.fromCharCode(...buf.subarray(i, i + 0x8000))
      await apiPost('/api/narration/upload', { segment: segId, data: btoa(bin), ext })
      await reload()
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
    setBusy(null)
  }

  const start = async (segId: string) => {
    setError(null)
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        // the browser's own cleanup is free and happens before anything reaches us
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      })
      const mr = new MediaRecorder(stream)
      chunks.current = []
      mr.ondataavailable = (e) => e.data.size && chunks.current.push(e.data)
      mr.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop())
        const blob = new Blob(chunks.current, { type: mr.mimeType || 'audio/webm' })
        setRecording(null)
        if (blob.size) await upload(segId, blob, 'webm')
      }
      recorder.current = mr
      mr.start()
      setRecording(segId)
    } catch (e) {
      setError(`拿不到麦克风：${e instanceof Error ? e.message : String(e)}`)
    }
  }

  const stop = () => recorder.current?.stop()

  const pick = (segId: string) => {
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = 'audio/*,video/*'
    input.onchange = async () => {
      const f = input.files?.[0]
      if (f) await upload(segId, f, f.name.split('.').pop() || 'mp3')
    }
    input.click()
  }

  const clear = async (segId: string) => {
    setBusy(segId)
    try {
      await apiPost('/api/narration/clear', { segment: segId })
      await reload()
      await load()
      setAligned((a) => {
        const { [segId]: _gone, ...rest } = a
        return rest
      })
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
    setBusy(null)
  }

  const align = async (segId: string) => {
    setBusy(segId)
    setError(null)
    try {
      const j = await apiPost<AlignResult>('/api/narration/align', { segment: segId })
      setAligned((a) => ({ ...a, [segId]: j }))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
    setBusy(null)
  }

  const own = raw.segments.filter((s) => s.narration).length

  return (
    <Card variant="outlined">
      <CardContent>
        <Typography variant="subtitle1" gutterBottom>
          🎙 用我自己的声音
          <Chip
            size="small"
            sx={{ ml: 1 }}
            color={own ? 'primary' : 'default'}
            label={own ? `${own}/${raw.segments.length} 段` : '全部是合成声音'}
          />
        </Typography>
        <Typography variant="body2" color="text.secondary">
          按段录，不是整条录：一个段落就是一个意思、两到四句，念错只重录这一段。
          录完会和这一段的脚本<b>强制对齐</b>，所以字幕、关键词高亮、章节点和竖版切片照旧准确。
        </Typography>

        {state && !state.whisper && (
          <Alert severity="info" sx={{ mt: 1 }}>
            还没装 <code>faster-whisper</code>，字幕时间会按时长平均摊（正常语速下接近，但不是帧级准确）。
            装一次就好：<code>pip install faster-whisper</code>（模型下到 <code>~/.vidforge/models/whisper/</code>，CPU 够用）。
          </Alert>
        )}
        {own > 0 && (
          <Alert severity="success" sx={{ mt: 1 }}>
            旁白换成你自己的声音之后，<code>disclosure.ai_voice</code> 可以关掉——简介里就不必再写
            「配音由 AI 合成」。
          </Alert>
        )}
        {!canRecord && (
          <Alert severity="warning" sx={{ mt: 1 }}>
            这个浏览器不给录音（需要 https 或 localhost）。可以用「选文件」把手机录的传进来。
          </Alert>
        )}
        {error && (
          <Alert severity="warning" sx={{ mt: 1 }}>
            {error}
          </Alert>
        )}

        <Stack spacing={1} sx={{ mt: 1.5, maxHeight: '55vh', overflowY: 'auto' }}>
          {raw.segments.map((seg) => {
            const info = aligned[seg.id]
            const working = busy === seg.id
            return (
              <Box key={seg.id} sx={{ borderTop: 1, borderColor: 'divider', pt: 1 }}>
                <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                  <Typography variant="body2" sx={{ minWidth: 90, fontWeight: 600 }}>
                    {seg.label || seg.id}
                  </Typography>
                  <Chip size="small" variant="outlined" label={seg.narration ? '我的声音' : 'TTS'} />
                  {recording === seg.id ? (
                    <Button size="small" color="error" variant="contained" startIcon={<StopIcon />} onClick={stop}>
                      停止并保存
                    </Button>
                  ) : (
                    <Button
                      size="small"
                      startIcon={<FiberManualRecordIcon color="error" fontSize="small" />}
                      onClick={() => start(seg.id)}
                      disabled={!canRecord || !!recording || working}
                    >
                      录这一段
                    </Button>
                  )}
                  <Tooltip title="用手机/录音笔录好的文件（音频或视频都行）">
                    <IconButton size="small" onClick={() => pick(seg.id)} disabled={!!recording || working}>
                      <UploadFileIcon fontSize="inherit" />
                    </IconButton>
                  </Tooltip>
                  {seg.narration && (
                    <>
                      <Button size="small" onClick={() => align(seg.id)} disabled={working}>
                        {working ? '对齐中…' : '对齐并试听'}
                      </Button>
                      <Tooltip title="改回合成声音">
                        <IconButton size="small" onClick={() => clear(seg.id)} disabled={working}>
                          <DeleteOutlineIcon fontSize="inherit" />
                        </IconButton>
                      </Tooltip>
                    </>
                  )}
                </Stack>
                <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5 }}>
                  {(seg.text || '').slice(0, 90) || '(这一段还没有文字)'}
                </Typography>
                {info && (
                  <Box sx={{ mt: 0.5 }}>
                    <Typography variant="caption" color="text.secondary">
                      {info.seconds.toFixed(1)}s · {info.words} 个词已定位
                      {!info.whisper && '（平均摊，未装 faster-whisper）'}
                    </Typography>
                    <Box component="audio" src={`/files/${info.audio}?t=${Date.now()}`} controls sx={{ width: '100%' }} />
                  </Box>
                )}
              </Box>
            )
          })}
        </Stack>
      </CardContent>
    </Card>
  )
}
