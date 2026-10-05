import { useEffect, useRef, useState } from 'react'
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  FormControlLabel,
  LinearProgress,
  MenuItem,
  Slider,
  Stack,
  Switch,
  TextField,
  Typography,
} from '@mui/material'
import FiberManualRecordIcon from '@mui/icons-material/FiberManualRecord'
import StopIcon from '@mui/icons-material/Stop'
import { apiGet, apiPost } from '../../../api/client'
import type { VideoLook } from '../../../api/types'
import { useProject } from '../../../state/ProjectContext'

type Device = { deviceId: string; label: string }

/**
 * 录音棚：提词器 + 设备选择 + 电平表，一条录像同时喂三样东西。
 *
 * Reading a paragraph off a page while watching the lens is the part people underestimate, so the
 * script sits *on* the preview rather than beside it. The level meter is there because the usual
 * way a take is lost is discovering afterwards that the wrong input was selected and the file is
 * silence; the picker is there because "the PC's audio port" is almost never the browser default.
 *
 * One take can land as this segment's narration (audio pulled out of the video by narration.py)
 * and as a clip in the own-footage library at the same time — asking someone to perform the same
 * paragraph twice is how a channel dies.
 */
export function RecordStudio() {
  const { raw, reload } = useProject()
  const [cams, setCams] = useState<Device[]>([])
  const [mics, setMics] = useState<Device[]>([])
  const [cam, setCam] = useState('')
  const [mic, setMic] = useState('')
  const [withVideo, setWithVideo] = useState(true)
  const [segId, setSegId] = useState('')
  const [fontSize, setFontSize] = useState(30)
  const [level, setLevel] = useState(0)
  const [peak, setPeak] = useState(0)
  const [live, setLive] = useState(false)
  const [recording, setRecording] = useState(false)
  const [countdown, setCountdown] = useState(0)
  const [elapsed, setElapsed] = useState(0)
  const [asNarration, setAsNarration] = useState(true)
  const [asFootage, setAsFootage] = useState(false)
  const [looks, setLooks] = useState<VideoLook[]>([])
  const [look, setLook] = useState('clean')
  const [busy, setBusy] = useState(false)
  const [status, setStatus] = useState('')
  const [error, setError] = useState<string | null>(null)

  const videoRef = useRef<HTMLVideoElement | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const recorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const audioCtxRef = useRef<AudioContext | null>(null)
  const rafRef = useRef<number | null>(null)
  const startedRef = useRef(0)

  useEffect(() => {
    apiGet<{ looks: VideoLook[]; current: string }>('/api/videofx')
      .then((j) => {
        setLooks(j.looks)
        setLook(j.current)
      })
      .catch(() => setLooks([]))
    return () => stopEverything()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (raw?.segments.length && !segId) setSegId(raw.segments[0].id)
  }, [raw?.segments.length, segId, raw])

  if (!raw) return null
  const seg = raw.segments.find((s) => s.id === segId)
  const canRecord = typeof navigator !== 'undefined' && !!navigator.mediaDevices?.getUserMedia

  const stopEverything = () => {
    if (rafRef.current) cancelAnimationFrame(rafRef.current)
    rafRef.current = null
    audioCtxRef.current?.close().catch(() => {})
    audioCtxRef.current = null
    streamRef.current?.getTracks().forEach((t) => t.stop())
    streamRef.current = null
    setLive(false)
    setLevel(0)
  }

  // Device labels are blank until permission has been granted once, so the picker is only
  // populated after the first getUserMedia call.
  const listDevices = async () => {
    const all = await navigator.mediaDevices.enumerateDevices()
    const pick = (kind: string) =>
      all
        .filter((d) => d.kind === kind)
        .map((d, i) => ({ deviceId: d.deviceId, label: d.label || `${kind} ${i + 1}` }))
    setCams(pick('videoinput'))
    setMics(pick('audioinput'))
  }

  const openPreview = async () => {
    setError(null)
    stopEverything()
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: withVideo ? { deviceId: cam ? { exact: cam } : undefined, width: 1280, height: 720 } : false,
        audio: {
          deviceId: mic ? { exact: mic } : undefined,
          // the browser's own cleanup is free and happens before anything reaches us
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      })
      streamRef.current = stream
      if (videoRef.current && withVideo) videoRef.current.srcObject = stream
      await listDevices()
      meter(stream)
      setLive(true)
    } catch (e) {
      setError(`打不开设备：${e instanceof Error ? e.message : String(e)}`)
    }
  }

  // A take lost to the wrong input is the most expensive kind, so the level is always on screen.
  const meter = (stream: MediaStream) => {
    const ctx = new AudioContext()
    audioCtxRef.current = ctx
    const node = ctx.createAnalyser()
    node.fftSize = 1024
    ctx.createMediaStreamSource(stream).connect(node)
    const buf = new Float32Array(node.fftSize)
    const tick = () => {
      node.getFloatTimeDomainData(buf)
      let sum = 0
      let hi = 0
      for (const v of buf) {
        sum += v * v
        hi = Math.max(hi, Math.abs(v))
      }
      setLevel(Math.min(1, Math.sqrt(sum / buf.length) * 4))
      setPeak((p) => Math.max(p * 0.97, hi))
      rafRef.current = requestAnimationFrame(tick)
    }
    tick()
  }

  const start = async () => {
    if (!streamRef.current) await openPreview()
    const stream = streamRef.current
    if (!stream) return
    setError(null)
    for (let n = 3; n > 0; n--) {
      setCountdown(n)
      await new Promise((r) => setTimeout(r, 700))
    }
    setCountdown(0)
    chunksRef.current = []
    const mr = new MediaRecorder(stream)
    mr.ondataavailable = (e) => e.data.size && chunksRef.current.push(e.data)
    mr.onstop = () => save(new Blob(chunksRef.current, { type: mr.mimeType || 'video/webm' }))
    recorderRef.current = mr
    startedRef.current = Date.now()
    mr.start()
    setRecording(true)
    const tick = setInterval(() => {
      if (!recorderRef.current || recorderRef.current.state !== 'recording') return clearInterval(tick)
      setElapsed((Date.now() - startedRef.current) / 1000)
    }, 200)
  }

  const stop = () => {
    recorderRef.current?.stop()
    setRecording(false)
  }

  const save = async (blob: Blob) => {
    setBusy(true)
    setStatus('')
    try {
      const buf = new Uint8Array(await blob.arrayBuffer())
      let bin = ''
      for (let i = 0; i < buf.length; i += 0x8000) bin += String.fromCharCode(...buf.subarray(i, i + 0x8000))
      const j = await apiPost<{ seconds: number; narration?: string; footage?: string }>('/api/record/save', {
        segment: segId,
        data: btoa(bin),
        ext: 'webm',
        as_narration: asNarration,
        as_footage: withVideo && asFootage,
        look,
        remember_look: true,
        name: `${segId || 'take'}_talking.mp4`,
        tags: 'studio',
        talking: true,
      })
      await reload()
      const parts = [`录了 ${j.seconds.toFixed(1)} 秒`]
      if (j.narration) parts.push(`已设为「${segId}」的旁白`)
      if (j.footage) parts.push(`已存进素材库：${j.footage}`)
      setStatus(parts.join('　·　'))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
    setBusy(false)
  }

  const words = (seg?.text || '').length
  const expected = words / 4 // 240 字/分钟 is the project's own figure

  return (
    <Card variant="outlined">
      <CardContent>
        <Typography variant="subtitle1" gutterBottom>
          🎬 录音棚
          <Chip size="small" sx={{ ml: 1 }} label={live ? '设备已打开' : '未打开'} color={live ? 'success' : 'default'} />
        </Typography>
        <Typography variant="body2" color="text.secondary">
          提词器在画面<b>上面</b>，不是旁边——念稿的时候眼睛要能看着镜头。
          一条录像可以同时当这一段的旁白<b>和</b>素材库里的出镜镜头，不用把同一段话演两遍。
        </Typography>

        {!canRecord && (
          <Alert severity="warning" sx={{ mt: 1 }}>
            这个浏览器不给录（需要 https 或 localhost）。
          </Alert>
        )}

        <Stack direction="row" spacing={1.5} alignItems="center" flexWrap="wrap" useFlexGap sx={{ mt: 1.5 }}>
          <TextField
            size="small"
            select
            label="录哪一段"
            value={segId}
            onChange={(e) => setSegId(e.target.value)}
            sx={{ minWidth: 200 }}
          >
            {raw.segments.map((s) => (
              <MenuItem key={s.id} value={s.id}>
                {s.label || s.id}
                {s.narration ? '（已有录音）' : ''}
              </MenuItem>
            ))}
          </TextField>
          <FormControlLabel
            control={<Switch size="small" checked={withVideo} onChange={(e) => setWithVideo(e.target.checked)} />}
            label={<Typography variant="body2">连画面一起录</Typography>}
          />
          <Button size="small" variant="outlined" onClick={openPreview} disabled={!canRecord || recording}>
            {live ? '重开设备' : '打开摄像头/麦克风'}
          </Button>
        </Stack>

        {live && (
          <Stack direction="row" spacing={1.5} alignItems="center" flexWrap="wrap" useFlexGap sx={{ mt: 1 }}>
            {withVideo && (
              <TextField size="small" select label="摄像头" value={cam} onChange={(e) => setCam(e.target.value)} sx={{ minWidth: 200 }}>
                <MenuItem value="">默认</MenuItem>
                {cams.map((d) => (
                  <MenuItem key={d.deviceId} value={d.deviceId}>
                    {d.label}
                  </MenuItem>
                ))}
              </TextField>
            )}
            <TextField size="small" select label="麦克风 / 音频输入" value={mic} onChange={(e) => setMic(e.target.value)} sx={{ minWidth: 240 }}>
              <MenuItem value="">默认</MenuItem>
              {mics.map((d) => (
                <MenuItem key={d.deviceId} value={d.deviceId}>
                  {d.label}
                </MenuItem>
              ))}
            </TextField>
            <Typography variant="caption" color="text.secondary">
              换了设备要点「重开设备」才生效
            </Typography>
          </Stack>
        )}

        {/* preview + teleprompter */}
        <Box
          sx={{
            position: 'relative',
            mt: 1.5,
            bgcolor: 'black',
            borderRadius: 1,
            overflow: 'hidden',
            minHeight: withVideo ? 320 : 180,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          {withVideo && (
            <Box
              component="video"
              ref={videoRef}
              autoPlay
              muted
              playsInline
              sx={{ width: '100%', display: 'block', transform: 'scaleX(-1)' }}
            />
          )}
          <Box
            sx={{
              position: withVideo ? 'absolute' : 'static',
              inset: 0,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              p: 3,
              // a scrim, so white text stays readable over any footage
              background: withVideo ? 'linear-gradient(transparent, rgba(0,0,0,.55) 25%)' : 'transparent',
            }}
          >
            <Typography
              sx={{
                color: '#fff',
                fontSize: `${fontSize}px`,
                lineHeight: 1.6,
                textAlign: 'center',
                maxHeight: '100%',
                overflowY: 'auto',
                textShadow: '0 2px 8px rgba(0,0,0,.9)',
              }}
            >
              {seg?.text || '这一段还没有文字——先在第 1 步写脚本。'}
            </Typography>
          </Box>
          {countdown > 0 && (
            <Box sx={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Typography sx={{ fontSize: 120, color: '#fff', fontWeight: 700, textShadow: '0 4px 20px #000' }}>
                {countdown}
              </Typography>
            </Box>
          )}
          {recording && (
            <Chip
              size="small"
              color="error"
              icon={<FiberManualRecordIcon />}
              label={`${elapsed.toFixed(1)}s`}
              sx={{ position: 'absolute', top: 8, left: 8 }}
            />
          )}
        </Box>

        {/* level meter */}
        <Box sx={{ mt: 1 }}>
          <Stack direction="row" spacing={1} alignItems="center">
            <Typography variant="caption" color="text.secondary" sx={{ minWidth: 48 }}>
              电平
            </Typography>
            <LinearProgress
              variant="determinate"
              value={Math.min(100, level * 100)}
              color={peak > 0.97 ? 'error' : level > 0.08 ? 'success' : 'inherit'}
              sx={{ flexGrow: 1, height: 10, borderRadius: 1 }}
            />
            <Typography variant="caption" sx={{ minWidth: 120 }} color={peak > 0.97 ? 'error' : 'text.secondary'}>
              {!live ? '未打开' : peak > 0.97 ? '削波了，调小输入' : level > 0.08 ? '正常' : '太小／没进声音'}
            </Typography>
          </Stack>
        </Box>

        <Stack direction="row" spacing={1.5} alignItems="center" flexWrap="wrap" useFlexGap sx={{ mt: 1.5 }}>
          {recording ? (
            <Button variant="contained" color="error" startIcon={<StopIcon />} onClick={stop}>
              停止并保存
            </Button>
          ) : (
            <Button
              variant="contained"
              startIcon={<FiberManualRecordIcon />}
              onClick={start}
              disabled={!canRecord || busy || !seg?.text}
            >
              开始录（3 秒倒数）
            </Button>
          )}
          <Typography variant="caption" color="text.secondary">
            这一段 {words} 字，正常语速约 {expected.toFixed(0)} 秒
          </Typography>
          <Box sx={{ width: 200 }}>
            <Typography variant="caption" color="text.secondary">
              提词器字号 {fontSize}
            </Typography>
            <Slider size="small" min={16} max={64} value={fontSize} onChange={(_, v) => setFontSize(v as number)} />
          </Box>
        </Stack>

        <Stack direction="row" spacing={2} alignItems="center" flexWrap="wrap" useFlexGap sx={{ mt: 1 }}>
          <FormControlLabel
            control={<Switch size="small" checked={asNarration} onChange={(e) => setAsNarration(e.target.checked)} />}
            label={<Typography variant="body2">当这一段的旁白（会自动对齐字幕）</Typography>}
          />
          {withVideo && (
            <FormControlLabel
              control={<Switch size="small" checked={asFootage} onChange={(e) => setAsFootage(e.target.checked)} />}
              label={<Typography variant="body2">同时存进「我的镜头」素材库</Typography>}
            />
          )}
          {withVideo && asFootage && (
            <TextField size="small" select label="画面预设" value={look} onChange={(e) => setLook(e.target.value)} sx={{ minWidth: 160 }}>
              {looks.map((l) => (
                <MenuItem key={l.id} value={l.id}>
                  {l.name}
                </MenuItem>
              ))}
            </TextField>
          )}
        </Stack>
        {withVideo && asFootage && (
          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5 }}>
            {looks.find((l) => l.id === look)?.about}
          </Typography>
        )}

        {busy && <LinearProgress sx={{ mt: 1 }} />}
        {status && (
          <Alert severity="success" sx={{ mt: 1 }}>
            {status}
          </Alert>
        )}
        {error && (
          <Alert severity="warning" sx={{ mt: 1 }}>
            {error}
          </Alert>
        )}
      </CardContent>
    </Card>
  )
}
