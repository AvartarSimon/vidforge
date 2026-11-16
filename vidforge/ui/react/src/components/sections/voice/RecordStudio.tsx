import { useEffect, useRef, useState } from 'react'
import {
  Alert,
  Box,
  Button,
  Chip,
  Divider,
  FormControlLabel,
  IconButton,
  LinearProgress,
  MenuItem,
  Paper,
  Slider,
  Stack,
  Switch,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Tooltip,
  Typography,
} from '@mui/material'
import FiberManualRecordIcon from '@mui/icons-material/FiberManualRecord'
import StopIcon from '@mui/icons-material/Stop'
import PauseIcon from '@mui/icons-material/Pause'
import PlayArrowIcon from '@mui/icons-material/PlayArrow'
import ReplayIcon from '@mui/icons-material/Replay'
import CompareIcon from '@mui/icons-material/Compare'
import SaveIcon from '@mui/icons-material/Save'
import NavigateBeforeIcon from '@mui/icons-material/NavigateBefore'
import NavigateNextIcon from '@mui/icons-material/NavigateNext'
import { apiPost } from '../../../api/client'
import { useProject } from '../../../state/ProjectContext'
import { FxPanel } from '../../../fx/FxPanel'
import { Teleprompter, type PrompterPlace } from '../../../fx/Teleprompter'
import { loadFx, saveFx, type FxSettings } from '../../../fx/settings'
import { useFxEngine } from '../../../fx/useFxEngine'

type Device = { deviceId: string; label: string }

// what MediaRecorder can write here, best first: mp4/h264 skips a transcode on the way in
function pickMime(video: boolean): { mime: string; ext: string } {
  const opts = video
    ? [
        ['video/mp4;codecs=avc1.640028,mp4a.40.2', 'mp4'],
        ['video/mp4', 'mp4'],
        ['video/webm;codecs=vp9,opus', 'webm'],
        ['video/webm', 'webm'],
      ]
    : [
        ['audio/webm;codecs=opus', 'webm'],
        ['audio/mp4', 'm4a'],
        ['audio/webm', 'webm'],
      ]
  for (const [mime, ext] of opts) if (typeof MediaRecorder !== 'undefined' && MediaRecorder.isTypeSupported(mime)) return { mime, ext }
  return { mime: '', ext: video ? 'webm' : 'webm' }
}

const PREFS = 'vf.studio.v1'
type Prefs = { cpm: number; fontSize: number; place: PrompterPlace; mirrorText: boolean; mirrorPreview: boolean }
function loadPrefs(): Prefs {
  const d: Prefs = { cpm: 240, fontSize: 34, place: 'top', mirrorText: false, mirrorPreview: true }
  try {
    return { ...d, ...JSON.parse(localStorage.getItem(PREFS) || '{}') }
  } catch {
    return d
  }
}

/**
 * 录制棚：提词器 + 实时美颜/换背景 + 一条录像喂三样东西。
 *
 * What is recorded is the processed canvas, so the take is exactly what the preview showed. The
 * script scrolls by itself at the speed you read (字/分钟), on the preview near the lens, because a
 * teleprompter beside the camera makes the eyes visibly drift off it.
 *
 * One take can land as this segment's picture, its narration (the same file, cut at the first and
 * last sound so lips and voice stay locked) and a clip in the own-footage library — asking someone
 * to perform the same paragraph twice is how a channel dies.
 */
export function RecordStudio() {
  const { raw, reload } = useProject()
  const [cams, setCams] = useState<Device[]>([])
  const [mics, setMics] = useState<Device[]>([])
  const [cam, setCam] = useState('')
  const [mic, setMic] = useState('')
  const [withVideo, setWithVideo] = useState(true)
  // the editor's 去录制棚 hands over which segment it was on
  const [segId, setSegId] = useState(() => {
    try {
      return sessionStorage.getItem('vf.studio.seg') || ''
    } catch {
      return ''
    }
  })
  const [prefs, setPrefs] = useState<Prefs>(loadPrefs)
  const [fx, setFx] = useState<FxSettings>(loadFx)
  const [level, setLevel] = useState(0)
  const [peak, setPeak] = useState(0)
  const [live, setLive] = useState(false)
  const [recording, setRecording] = useState(false)
  const [scrolling, setScrolling] = useState(false)
  const [resetKey, setResetKey] = useState(0)
  const [countdown, setCountdown] = useState(0)
  const [elapsed, setElapsed] = useState(0)
  const [take, setTake] = useState<{ blob: Blob; url: string; ext: string; seconds: number } | null>(null)
  const [asVisual, setAsVisual] = useState(true)
  const [asNarration, setAsNarration] = useState(true)
  const [asFootage, setAsFootage] = useState(false)
  const [jumpcut, setJumpcut] = useState(true)
  const [busy, setBusy] = useState(false)
  const [status, setStatus] = useState('')
  const [error, setError] = useState<string | null>(null)

  const videoRef = useRef<HTMLVideoElement | null>(null)
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const recorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const audioCtxRef = useRef<AudioContext | null>(null)
  const rafRef = useRef<number | null>(null)
  const startedRef = useRef(0)
  const { engineRef, status: fxStatus } = useFxEngine(canvasRef, videoRef, fx)

  useEffect(() => saveFx(fx), [fx])
  useEffect(() => {
    try {
      localStorage.setItem(PREFS, JSON.stringify(prefs))
    } catch {
      // ignore
    }
  }, [prefs])
  useEffect(() => () => stopEverything(), []) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (raw?.segments.length && !raw.segments.some((s) => s.id === segId)) setSegId(raw.segments[0].id)
  }, [raw?.segments.length, segId, raw])

  // keyboard: space = pause/resume the scroll, ↑/↓ = faster/slower, R = rewind the script
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement
      if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)) return
      if (e.code === 'Space') {
        e.preventDefault()
        setScrolling((s) => !s)
      } else if (e.code === 'ArrowUp') {
        e.preventDefault()
        setPrefs((p) => ({ ...p, cpm: Math.min(420, p.cpm + 10) }))
      } else if (e.code === 'ArrowDown') {
        e.preventDefault()
        setPrefs((p) => ({ ...p, cpm: Math.max(120, p.cpm - 10) }))
      } else if (e.key === 'r' || e.key === 'R') {
        setResetKey((k) => k + 1)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  if (!raw) return null
  const segIndex = raw.segments.findIndex((s) => s.id === segId)
  const seg = raw.segments[segIndex]
  const canRecord = typeof navigator !== 'undefined' && !!navigator.mediaDevices?.getUserMedia
  const useCanvas = withVideo && !!fxStatus?.gl

  function stopEverything() {
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
      all.filter((d) => d.kind === kind).map((d, i) => ({ deviceId: d.deviceId, label: d.label || `${kind} ${i + 1}` }))
    setCams(pick('videoinput'))
    setMics(pick('audioinput'))
  }

  const openPreview = async () => {
    setError(null)
    stopEverything()
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: withVideo
          ? { deviceId: cam ? { exact: cam } : undefined, width: { ideal: 1920 }, height: { ideal: 1080 }, frameRate: { ideal: 30 } }
          : false,
        audio: {
          deviceId: mic ? { exact: mic } : undefined,
          // the browser's own cleanup is free and happens before anything reaches us
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      })
      streamRef.current = stream
      if (videoRef.current && withVideo) {
        videoRef.current.srcObject = stream
        await videoRef.current.play().catch(() => {})
        engineRef.current?.setSource(videoRef.current)
      }
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
    setStatus('')
    discardTake()
    setResetKey((k) => k + 1)
    for (let n = 3; n > 0; n--) {
      setCountdown(n)
      await new Promise((r) => setTimeout(r, 700))
    }
    setCountdown(0)
    chunksRef.current = []
    const tracks = useCanvas && canvasRef.current
      ? [...canvasRef.current.captureStream(30).getVideoTracks(), ...stream.getAudioTracks()]
      : stream.getTracks()
    const { mime, ext } = pickMime(withVideo)
    const mr = new MediaRecorder(new MediaStream(tracks), {
      ...(mime ? { mimeType: mime } : {}),
      videoBitsPerSecond: 10_000_000,
      audioBitsPerSecond: 192_000,
    })
    mr.ondataavailable = (e) => e.data.size && chunksRef.current.push(e.data)
    mr.onstop = () => {
      const blob = new Blob(chunksRef.current, { type: mr.mimeType || (withVideo ? 'video/webm' : 'audio/webm') })
      const seconds = (Date.now() - startedRef.current) / 1000
      setTake({ blob, url: URL.createObjectURL(blob), ext, seconds })
    }
    recorderRef.current = mr
    startedRef.current = Date.now()
    mr.start(1000)
    setRecording(true)
    setScrolling(true)
    const tick = setInterval(() => {
      if (!recorderRef.current || recorderRef.current.state !== 'recording') return clearInterval(tick)
      setElapsed((Date.now() - startedRef.current) / 1000)
    }, 200)
  }

  const stop = () => {
    recorderRef.current?.stop()
    setRecording(false)
    setScrolling(false)
  }

  const discardTake = () => {
    if (take) URL.revokeObjectURL(take.url)
    setTake(null)
  }

  const save = async () => {
    if (!take) return
    setBusy(true)
    setStatus('')
    setError(null)
    try {
      const buf = new Uint8Array(await take.blob.arrayBuffer())
      let bin = ''
      for (let i = 0; i < buf.length; i += 0x8000) bin += String.fromCharCode(...buf.subarray(i, i + 0x8000))
      const j = await apiPost<{ seconds: number; narration?: string; footage?: string; visual?: string; trimmed?: number[]; jumpcut?: { removed: number; cuts: number } }>(
        '/api/record/save',
        {
          segment: segId,
          data: btoa(bin),
          ext: take.ext,
          as_narration: asNarration,
          as_visual: withVideo && asVisual,
          as_footage: withVideo && asFootage,
          jumpcut: withVideo && asVisual && jumpcut,
          // the look is already baked in by the live effects
          look: 'none',
          name: `${segId || 'take'}_talking.mp4`,
          tags: 'studio',
          talking: true,
        },
      )
      await reload()
      const parts = [`录了 ${j.seconds.toFixed(1)} 秒`]
      if (j.trimmed && (j.trimmed[0] > 0.05 || j.trimmed[1] > 0.05)) parts.push(`掐掉首尾静音 ${j.trimmed[0]}s / ${j.trimmed[1]}s`)
      if (j.jumpcut && j.jumpcut.removed > 0.05) parts.push(`剪口播剪掉 ${j.jumpcut.removed.toFixed(1)}s（${j.jumpcut.cuts} 处）`)
      if (j.visual) parts.push('已设为这一段的画面')
      if (j.narration) parts.push('已设为这一段的旁白（字幕会自动对齐）')
      if (j.footage) parts.push(`已存进素材库：${j.footage}`)
      setStatus(parts.join('　·　'))
      discardTake()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
    setBusy(false)
  }

  const go = (d: number) => {
    const next = raw.segments[segIndex + d]
    if (next) {
      setSegId(next.id)
      discardTake()
      setStatus('')
    }
  }

  const text = seg?.text || ''
  const chars = text.replace(/\s/g, '').length
  const expected = (chars / prefs.cpm) * 60
  const mirrorCss = prefs.mirrorPreview ? 'scaleX(-1)' : undefined

  return (
    <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', lg: 'minmax(0,1fr) 340px' }, gap: 2 }}>
      {/* stage */}
      <Box>
        <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
          <IconButton size="small" disabled={segIndex <= 0 || recording} onClick={() => go(-1)} aria-label="上一段">
            <NavigateBeforeIcon />
          </IconButton>
          <TextField size="small" select value={segId} onChange={(e) => setSegId(e.target.value)} sx={{ minWidth: 220, flexGrow: 1, maxWidth: 420 }} disabled={recording}>
            {raw.segments.map((s, i) => (
              <MenuItem key={s.id} value={s.id}>
                {i + 1}. {s.label || s.id}
                {s.narration ? '　🎙' : ''}
              </MenuItem>
            ))}
          </TextField>
          <IconButton size="small" disabled={segIndex >= raw.segments.length - 1 || recording} onClick={() => go(1)} aria-label="下一段">
            <NavigateNextIcon />
          </IconButton>
          <Box sx={{ flexGrow: 1 }} />
          <Chip size="small" label={live ? '设备已打开' : '未打开'} color={live ? 'success' : 'default'} variant="outlined" />
        </Stack>

        <Box
          sx={{
            position: 'relative',
            bgcolor: '#000',
            borderRadius: 2,
            overflow: 'hidden',
            aspectRatio: withVideo ? (fx.aspect === '9:16' ? '9 / 16' : fx.aspect === '1:1' ? '1' : fx.aspect === '3:4' ? '3 / 4' : '16 / 9') : '16 / 6',
            maxHeight: '72vh',
            mx: 'auto',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          {/* the camera feeds the engine; it stays in the DOM (some browsers stop decoding a detached video) */}
          <Box
            component="video"
            ref={videoRef}
            autoPlay
            muted
            playsInline
            sx={
              useCanvas
                ? { position: 'absolute', width: 2, height: 2, opacity: 0, pointerEvents: 'none' }
                : { width: '100%', height: '100%', objectFit: 'cover', transform: mirrorCss, display: withVideo ? 'block' : 'none' }
            }
          />
          <Box
            component="canvas"
            ref={canvasRef}
            sx={{ width: '100%', height: '100%', objectFit: 'contain', transform: mirrorCss, display: useCanvas && live ? 'block' : 'none' }}
          />
          {!live && (
            <Stack alignItems="center" spacing={1.5} sx={{ position: 'absolute', inset: 0, justifyContent: 'center', color: '#fff' }}>
              <Button variant="contained" onClick={openPreview} disabled={!canRecord}>
                打开摄像头 / 麦克风
              </Button>
              <Typography variant="caption" sx={{ opacity: 0.7 }}>
                画面只在这台电脑上处理，不会上传
              </Typography>
            </Stack>
          )}
          {live && <Teleprompter text={text || '这一段还没有文字——先在第 1 步写脚本。'} fontSize={prefs.fontSize} cpm={prefs.cpm} running={scrolling} mirror={prefs.mirrorText} place={withVideo ? prefs.place : 'full'} resetKey={resetKey} />}
          {countdown > 0 && (
            <Box sx={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', bgcolor: 'rgba(0,0,0,.3)' }}>
              <Typography sx={{ fontSize: 140, color: '#fff', fontWeight: 700, textShadow: '0 4px 20px #000' }}>{countdown}</Typography>
            </Box>
          )}
          {recording && (
            <Chip size="small" color="error" icon={<FiberManualRecordIcon />} label={`${elapsed.toFixed(1)}s / 约 ${expected.toFixed(0)}s`} sx={{ position: 'absolute', bottom: 10, left: 10 }} />
          )}
          {live && useCanvas && (
            <Tooltip title="按住看原图">
              <IconButton
                size="small"
                onPointerDown={() => engineRef.current?.setBypass(true)}
                onPointerUp={() => engineRef.current?.setBypass(false)}
                onPointerLeave={() => engineRef.current?.setBypass(false)}
                sx={{ position: 'absolute', bottom: 8, right: 8, bgcolor: 'rgba(0,0,0,.5)', color: '#fff', '&:hover': { bgcolor: 'rgba(0,0,0,.7)' } }}
              >
                <CompareIcon fontSize="small" />
              </IconButton>
            </Tooltip>
          )}
        </Box>

        {/* level meter */}
        <Stack direction="row" spacing={1} alignItems="center" sx={{ mt: 1 }}>
          <Typography variant="caption" color="text.secondary" sx={{ minWidth: 30 }}>
            电平
          </Typography>
          <LinearProgress
            variant="determinate"
            value={Math.min(100, level * 100)}
            color={peak > 0.97 ? 'error' : level > 0.08 ? 'success' : 'inherit'}
            sx={{ flexGrow: 1, height: 6, borderRadius: 1 }}
          />
          <Typography variant="caption" sx={{ minWidth: 110 }} color={peak > 0.97 ? 'error' : 'text.secondary'}>
            {!live ? '未打开' : peak > 0.97 ? '削波了，调小输入' : level > 0.08 ? '正常' : '太小／没进声音'}
          </Typography>
        </Stack>

        {/* transport */}
        <Stack direction="row" spacing={1.5} alignItems="center" justifyContent="center" flexWrap="wrap" useFlexGap sx={{ mt: 1.5 }}>
          <Tooltip title="提词器回到开头（R）">
            <span>
              <IconButton onClick={() => setResetKey((k) => k + 1)} disabled={!live}>
                <ReplayIcon />
              </IconButton>
            </span>
          </Tooltip>
          {recording ? (
            <Button variant="contained" color="error" size="large" startIcon={<StopIcon />} onClick={stop} sx={{ minWidth: 160, borderRadius: 99 }}>
              停止
            </Button>
          ) : (
            <Button
              variant="contained"
              color="error"
              size="large"
              startIcon={<FiberManualRecordIcon />}
              onClick={start}
              disabled={!canRecord || busy || !text}
              sx={{ minWidth: 160, borderRadius: 99 }}
            >
              开始录制
            </Button>
          )}
          <Tooltip title="提词器暂停/继续（空格）">
            <span>
              <IconButton onClick={() => setScrolling((s) => !s)} disabled={!live}>
                {scrolling ? <PauseIcon /> : <PlayArrowIcon />}
              </IconButton>
            </span>
          </Tooltip>
        </Stack>
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', textAlign: 'center', mt: 0.5 }}>
          这一段 {chars} 字，按 {prefs.cpm} 字/分钟约 {expected.toFixed(0)} 秒 · 空格暂停提词器 · ↑↓ 调速度 · R 回到开头
        </Typography>

        {take && (
          <Paper variant="outlined" sx={{ mt: 2, p: 2 }}>
            <Typography variant="subtitle2" gutterBottom>
              回看这一条（{take.seconds.toFixed(1)} 秒）
            </Typography>
            {withVideo ? (
              <Box component="video" src={take.url} controls sx={{ width: '100%', maxHeight: 360, bgcolor: '#000', borderRadius: 1 }} />
            ) : (
              <Box component="audio" src={take.url} controls sx={{ width: '100%' }} />
            )}
            <Stack direction="row" spacing={2} flexWrap="wrap" useFlexGap sx={{ mt: 1 }}>
              {withVideo && (
                <FormControlLabel control={<Switch size="small" checked={asVisual} onChange={(e) => setAsVisual(e.target.checked)} />} label={<Typography variant="body2">当这一段的画面</Typography>} />
              )}
              {withVideo && asVisual && (
                <FormControlLabel control={<Switch size="small" checked={jumpcut} onChange={(e) => setJumpcut(e.target.checked)} />} label={<Typography variant="body2">剪掉中间的停顿（剪口播）</Typography>} />
              )}
              <FormControlLabel control={<Switch size="small" checked={asNarration} onChange={(e) => setAsNarration(e.target.checked)} />} label={<Typography variant="body2">当这一段的旁白</Typography>} />
              {withVideo && (
                <FormControlLabel control={<Switch size="small" checked={asFootage} onChange={(e) => setAsFootage(e.target.checked)} />} label={<Typography variant="body2">存进「我的镜头」</Typography>} />
              )}
            </Stack>
            <Stack direction="row" spacing={1} sx={{ mt: 1 }}>
              <Button variant="contained" startIcon={<SaveIcon />} onClick={save} disabled={busy}>
                用这一条
              </Button>
              <Button onClick={start} disabled={busy} startIcon={<ReplayIcon />}>
                重录
              </Button>
              <Button color="inherit" onClick={discardTake} disabled={busy}>
                丢掉
              </Button>
            </Stack>
            {busy && <LinearProgress sx={{ mt: 1 }} />}
          </Paper>
        )}
        {status && (
          <Alert severity="success" sx={{ mt: 1.5 }} action={segIndex < raw.segments.length - 1 ? <Button size="small" onClick={() => go(1)}>录下一段 →</Button> : undefined}>
            {status}
          </Alert>
        )}
        {error && (
          <Alert severity="warning" sx={{ mt: 1.5 }}>
            {error}
          </Alert>
        )}
        {!canRecord && (
          <Alert severity="warning" sx={{ mt: 1.5 }}>
            这个浏览器不给录（需要 https 或 localhost）。
          </Alert>
        )}
      </Box>

      {/* inspector */}
      <Paper variant="outlined" sx={{ p: 2, alignSelf: 'start', position: { lg: 'sticky' }, top: { lg: 80 } }}>
        <FormControlLabel
          control={<Switch size="small" checked={withVideo} onChange={(e) => setWithVideo(e.target.checked)} disabled={recording} />}
          label={<Typography variant="body2">连画面一起录</Typography>}
        />
        {withVideo && (
          <>
            <Divider sx={{ my: 1.5 }} />
            <FxPanel fx={fx} onChange={setFx} status={fxStatus} />
          </>
        )}
        <Divider sx={{ my: 1.5 }} />
        <Typography variant="body2" fontWeight={600} gutterBottom>
          提词器
        </Typography>
        <Stack spacing={0.5}>
          <Box>
            <Typography variant="caption" color="text.secondary">
              速度 {prefs.cpm} 字/分钟
            </Typography>
            <Slider size="small" min={120} max={420} step={10} value={prefs.cpm} onChange={(_, v) => setPrefs({ ...prefs, cpm: v as number })} />
          </Box>
          <Box>
            <Typography variant="caption" color="text.secondary">
              字号 {prefs.fontSize}
            </Typography>
            <Slider size="small" min={18} max={72} value={prefs.fontSize} onChange={(_, v) => setPrefs({ ...prefs, fontSize: v as number })} />
          </Box>
          {withVideo && (
            <ToggleButtonGroup size="small" exclusive value={prefs.place} onChange={(_, v: PrompterPlace | null) => v && setPrefs({ ...prefs, place: v })}>
              <ToggleButton value="top">靠上（贴近镜头）</ToggleButton>
              <ToggleButton value="full">满屏</ToggleButton>
              <ToggleButton value="bottom">靠下</ToggleButton>
            </ToggleButtonGroup>
          )}
          <FormControlLabel control={<Switch size="small" checked={prefs.mirrorPreview} onChange={(e) => setPrefs({ ...prefs, mirrorPreview: e.target.checked })} />} label={<Typography variant="body2">预览镜像（录出来不镜像）</Typography>} />
          <FormControlLabel control={<Switch size="small" checked={prefs.mirrorText} onChange={(e) => setPrefs({ ...prefs, mirrorText: e.target.checked })} />} label={<Typography variant="body2">文字镜像（配提词器玻璃用）</Typography>} />
        </Stack>
        {live && (
          <>
            <Divider sx={{ my: 1.5 }} />
            <Typography variant="body2" fontWeight={600} gutterBottom>
              设备
            </Typography>
            <Stack spacing={1}>
              {withVideo && (
                <TextField size="small" select label="摄像头" value={cam} onChange={(e) => setCam(e.target.value)}>
                  <MenuItem value="">默认</MenuItem>
                  {cams.map((d) => (
                    <MenuItem key={d.deviceId} value={d.deviceId}>
                      {d.label}
                    </MenuItem>
                  ))}
                </TextField>
              )}
              <TextField size="small" select label="麦克风" value={mic} onChange={(e) => setMic(e.target.value)}>
                <MenuItem value="">默认</MenuItem>
                {mics.map((d) => (
                  <MenuItem key={d.deviceId} value={d.deviceId}>
                    {d.label}
                  </MenuItem>
                ))}
              </TextField>
              <Button size="small" variant="outlined" onClick={openPreview} disabled={recording}>
                换设备后点这里重开
              </Button>
            </Stack>
          </>
        )}
      </Paper>
    </Box>
  )
}
