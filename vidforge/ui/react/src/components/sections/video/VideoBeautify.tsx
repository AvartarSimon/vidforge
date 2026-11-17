import { useEffect, useMemo, useRef, useState } from 'react'
import { Alert, Box, Button, Card, CardContent, FormControlLabel, IconButton, LinearProgress, MenuItem, Stack, Switch, TextField, Typography } from '@mui/material'
import PlayArrowIcon from '@mui/icons-material/PlayArrow'
import PauseIcon from '@mui/icons-material/Pause'
import CompareIcon from '@mui/icons-material/Compare'
import UploadIcon from '@mui/icons-material/Upload'
import { apiGet, apiPost } from '../../../api/client'
import { useProject } from '../../../state/ProjectContext'
import { fileUrl, takeFiles } from '../../../utils'
import { FxPanel } from '../../../fx/FxPanel'
import { loadFx, saveFx, type FxSettings } from '../../../fx/settings'
import { useFxEngine } from '../../../fx/useFxEngine'

type Source = { label: string; url: string; rel?: string; name: string }

function readAsBase64(f: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const rd = new FileReader()
    rd.onload = () => resolve((rd.result as string).split(',')[1])
    rd.onerror = reject
    rd.readAsDataURL(f)
  })
}

/**
 * 视频美化 / 后期换背景: a finished video through the same live effects as the recording studio.
 *
 * It is replayed in real time and the processed canvas re-recorded, so a one-minute clip takes a
 * minute — the price of using one engine for both, which is that what you tuned on the preview is
 * exactly what comes out. "替换原视频" swaps the result in wherever a segment shows the original.
 */
export function VideoBeautify() {
  const { raw, reload } = useProject()
  const [me, setMe] = useState<{ name: string }[]>([])
  const [uploaded, setUploaded] = useState<Source[]>([])
  const [src, setSrc] = useState<Source | null>(null)
  const [fx, setFx] = useState<FxSettings>(() => ({ ...loadFx(), aspect: 'source' }))
  const [playing, setPlaying] = useState(false)
  const [progress, setProgress] = useState(0)
  const [exporting, setExporting] = useState(false)
  const [replace, setReplace] = useState(true)
  const [toMe, setToMe] = useState(false)
  const [status, setStatus] = useState('')
  const [error, setError] = useState<string | null>(null)
  const videoRef = useRef<HTMLVideoElement | null>(null)
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const audioRef = useRef<{ ctx: AudioContext; dest: MediaStreamAudioDestinationNode } | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const { engineRef, status: fxStatus } = useFxEngine(canvasRef, videoRef, fx)

  useEffect(() => saveFx({ ...fx, aspect: loadFx().aspect }), [fx])
  useEffect(() => {
    apiGet<{ items: { name: string }[] }>('/api/me')
      .then((j) => setMe(j.items))
      .catch(() => setMe([]))
  }, [])

  // every video this project already uses, then the footage library, then uploads
  const sources = useMemo(() => {
    const seen = new Set<string>()
    const out: Source[] = []
    for (const s of raw?.segments || [])
      for (const c of [...s.clips, ...(s.overlays || [])]) {
        const v = typeof c.video === 'string' ? c.video : ''
        if (v && !seen.has(v)) {
          seen.add(v)
          out.push({ label: `${s.label || s.id} · ${v.split('/').pop()}`, url: fileUrl(v) || '', rel: v, name: v.split('/').pop() || 'video' })
        }
      }
    for (const m of me) out.push({ label: `我的镜头 · ${m.name}`, url: `/api/me/file/${encodeURIComponent(m.name)}`, name: m.name })
    return [...out, ...uploaded]
  }, [raw, me, uploaded])

  const pick = (s: Source | null) => {
    setSrc(s)
    setPlaying(false)
    setProgress(0)
    setStatus('')
  }

  const upload = async (f: File) => {
    setError(null)
    try {
      const j = await apiPost<{ path: string }>('/api/assets/upload', { name: f.name, data_b64: await readAsBase64(f) })
      const s = { label: `上传 · ${f.name}`, url: fileUrl(j.path) || '', rel: j.path, name: f.name }
      setUploaded((u) => [...u, s])
      pick(s)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  const toggle = () => {
    const v = videoRef.current
    if (!v) return
    if (v.paused) v.play().catch(() => {})
    else v.pause()
  }

  // a MediaElementSource takes the element's sound over, so it is routed to both the recording
  // and the speakers (you can still hear what is being exported)
  const audioStream = () => {
    if (!audioRef.current) {
      const ctx = new AudioContext()
      const node = ctx.createMediaElementSource(videoRef.current!)
      const dest = ctx.createMediaStreamDestination()
      node.connect(dest)
      node.connect(ctx.destination)
      audioRef.current = { ctx, dest }
    }
    return audioRef.current.dest.stream
  }

  const exportIt = async () => {
    const v = videoRef.current
    const c = canvasRef.current
    if (!v || !c || !src) return
    setError(null)
    setStatus('')
    setExporting(true)
    try {
      v.pause()
      v.currentTime = 0
      await new Promise((r) => setTimeout(r, 300))
      const tracks = [...c.captureStream(30).getVideoTracks(), ...audioStream().getAudioTracks()]
      const mime = ['video/mp4;codecs=avc1.640028,mp4a.40.2', 'video/webm;codecs=vp9,opus', 'video/webm'].find((m) => MediaRecorder.isTypeSupported(m)) || ''
      const mr = new MediaRecorder(new MediaStream(tracks), { ...(mime ? { mimeType: mime } : {}), videoBitsPerSecond: 12_000_000 })
      const chunks: Blob[] = []
      mr.ondataavailable = (e) => e.data.size && chunks.push(e.data)
      const done = new Promise<Blob>((resolve) => (mr.onstop = () => resolve(new Blob(chunks, { type: mr.mimeType }))))
      v.muted = false
      v.loop = false
      mr.start(1000)
      await v.play()
      await new Promise<void>((resolve) => {
        v.onended = () => resolve()
      })
      mr.stop()
      const blob = await done
      const ext = (mr.mimeType || '').includes('mp4') ? 'mp4' : 'webm'
      const qs = new URLSearchParams({ ext, name: src.name })
      if (replace && src.rel) qs.set('replace', src.rel)
      if (toMe) qs.set('to_me', '1')
      const res = await fetch(`/api/fx/save?${qs}`, { method: 'POST', headers: { 'Content-Type': 'application/octet-stream' }, body: blob })
      const j = await res.json()
      if (!res.ok) throw new Error(j.error || res.statusText)
      await reload()
      const parts = [`已保存 ${j.path}（${j.seconds.toFixed(1)} 秒）`]
      if (j.replaced?.length) parts.push(`已替换 ${j.replaced.length} 处用到原视频的段落`)
      if (j.footage) parts.push('已存进「我的镜头」')
      setStatus(parts.join('　·　'))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
    setExporting(false)
  }

  return (
    <Card variant="outlined">
      <CardContent>
        <Typography variant="subtitle1" gutterBottom>
          ✨ 视频美化 / 换背景
        </Typography>
        <Typography variant="body2" color="text.secondary" gutterBottom>
          已经录好的视频也能用录制棚那一套：美颜、瘦脸、换背景、衣服换色。调好后按原速播放一遍并重新录下来（1 分钟的视频要 1 分钟）。
        </Typography>
        <Stack direction="row" spacing={1} alignItems="center" sx={{ my: 1.5 }} flexWrap="wrap" useFlexGap>
          <TextField size="small" select label="选视频" value={src?.url || ''} onChange={(e) => pick(sources.find((s) => s.url === e.target.value) || null)} sx={{ minWidth: 320 }}>
            {sources.length === 0 && <MenuItem disabled>项目里还没有视频</MenuItem>}
            {sources.map((s) => (
              <MenuItem key={s.url} value={s.url}>
                {s.label}
              </MenuItem>
            ))}
          </TextField>
          <Button size="small" variant="outlined" startIcon={<UploadIcon />} onClick={() => fileRef.current?.click()}>
            上传
          </Button>
          <input ref={fileRef} type="file" hidden accept="video/*" onChange={(e) => takeFiles(e).slice(0, 1).forEach(upload)} />
        </Stack>
        <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: 'minmax(0,1fr) 320px' }, gap: 2 }}>
          <Box>
            <Box sx={{ position: 'relative', bgcolor: '#000', borderRadius: 2, overflow: 'hidden', aspectRatio: '16 / 9', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Box
                component="video"
                ref={videoRef}
                src={src?.url}
                playsInline
                crossOrigin="anonymous"
                onPlay={() => setPlaying(true)}
                onPause={() => setPlaying(false)}
                onTimeUpdate={(e) => {
                  const v = e.target as HTMLVideoElement
                  setProgress(v.duration ? v.currentTime / v.duration : 0)
                }}
                onLoadedData={() => engineRef.current?.setSource(videoRef.current)}
                sx={{ position: 'absolute', width: 2, height: 2, opacity: 0, pointerEvents: 'none' }}
              />
              <Box component="canvas" ref={canvasRef} sx={{ width: '100%', height: '100%', objectFit: 'contain', display: src ? 'block' : 'none' }} />
              {!src && <Typography sx={{ color: 'rgba(255,255,255,.6)' }}>先选一个视频</Typography>}
              {src && (
                <IconButton
                  size="small"
                  onPointerDown={() => engineRef.current?.setBypass(true)}
                  onPointerUp={() => engineRef.current?.setBypass(false)}
                  onPointerLeave={() => engineRef.current?.setBypass(false)}
                  sx={{ position: 'absolute', bottom: 8, right: 8, bgcolor: 'rgba(0,0,0,.5)', color: '#fff' }}
                  title="按住看原图"
                >
                  <CompareIcon fontSize="small" />
                </IconButton>
              )}
            </Box>
            <Stack direction="row" spacing={1} alignItems="center" sx={{ mt: 1 }}>
              <IconButton onClick={toggle} disabled={!src || exporting}>
                {playing ? <PauseIcon /> : <PlayArrowIcon />}
              </IconButton>
              <LinearProgress variant="determinate" value={progress * 100} sx={{ flexGrow: 1, height: 6, borderRadius: 1 }} />
            </Stack>
            <Stack direction="row" spacing={2} alignItems="center" flexWrap="wrap" useFlexGap sx={{ mt: 1 }}>
              <Button variant="contained" onClick={exportIt} disabled={!src || exporting}>
                {exporting ? `处理中 ${Math.round(progress * 100)}%…` : '导出美化后的视频'}
              </Button>
              {src?.rel && <FormControlLabel control={<Switch size="small" checked={replace} onChange={(e) => setReplace(e.target.checked)} />} label={<Typography variant="body2">替换项目里用到原视频的地方</Typography>} />}
              <FormControlLabel control={<Switch size="small" checked={toMe} onChange={(e) => setToMe(e.target.checked)} />} label={<Typography variant="body2">同时存进「我的镜头」</Typography>} />
            </Stack>
            {exporting && (
              <Typography variant="caption" color="text.secondary">
                导出时别切走这个页面——浏览器在后台标签页里会降帧。
              </Typography>
            )}
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
          </Box>
          <Box>
            <FxPanel fx={fx} onChange={setFx} status={fxStatus} showAspect={false} />
          </Box>
        </Box>
      </CardContent>
    </Card>
  )
}
