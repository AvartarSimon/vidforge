import { useEffect, useMemo, useRef, useState } from 'react'
import {
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  FormControlLabel,
  IconButton,
  MenuItem,
  Slider,
  Stack,
  Switch,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Tooltip,
  Typography,
} from '@mui/material'
import CloseIcon from '@mui/icons-material/Close'
import DeleteIcon from '@mui/icons-material/Delete'
import ArrowUpwardIcon from '@mui/icons-material/ArrowUpward'
import ArrowDownwardIcon from '@mui/icons-material/ArrowDownward'
import UploadIcon from '@mui/icons-material/Upload'
import { apiGet, apiPost } from '../../../api/client'
import type { Overlay, Segment } from '../../../api/types'
import { useProject } from '../../../state/ProjectContext'
import { fileUrl } from '../../../utils'

const NAMED: Record<string, [number, number]> = {
  'top-left': [0, 0],
  top: [0.5, 0],
  'top-right': [1, 0],
  left: [0, 0.5],
  center: [0.5, 0.5],
  right: [1, 0.5],
  'bottom-left': [0, 1],
  bottom: [0.5, 1],
  'bottom-right': [1, 1],
}

// "x,y" in the backend means a fraction of the *free* space ((W-w)*x), so 0 and 1 are flush with
// the edges whatever the layer's size; named positions keep a small margin, as render.py does.
function toFrac(position: string | undefined): [number, number] {
  const p = position || 'bottom-right'
  if (p.includes(',')) {
    const [x, y] = p.split(',').map((v) => parseFloat(v))
    return [isFinite(x) ? x : 1, isFinite(y) ? y : 1]
  }
  const [x, y] = NAMED[p] || [1, 1]
  const m = 0.03
  return [x === 0 ? m : x === 1 ? 1 - m : x, y === 0 ? m * 1.6 : y === 1 ? 1 - m * 1.6 : y]
}

const snap = (v: number) => {
  for (const t of [0, 0.5, 1]) if (Math.abs(v - t) < 0.025) return t
  return Math.round(v * 1000) / 1000
}

type Layout = { id: string; name: string; slots: Partial<Overlay>[] }
// Split screens are boxes filled edge to edge (`height` set); the base picture still shows through
// wherever no layer sits, so a two-way split with one layer keeps the segment's own visual on the left.
const LAYOUTS: Layout[] = [
  { id: 'circle', name: '圆形小窗', slots: [{ shape: 'circle', size: 0.22, position: '0.97,0.95', height: undefined, border: true }] },
  { id: 'corner', name: '角落小窗', slots: [{ shape: 'rounded', size: 0.32, position: '0.97,0.95', height: undefined, border: true }] },
  { id: 'lr', name: '左右分屏', slots: [{ shape: 'rect', size: 0.5, height: 1, position: '1,0', border: false }, { shape: 'rect', size: 0.5, height: 1, position: '0,0', border: false }] },
  { id: 'tb', name: '上下分屏', slots: [{ shape: 'rect', size: 1, height: 0.5, position: '0,1', border: false }, { shape: 'rect', size: 1, height: 0.5, position: '0,0', border: false }] },
  {
    id: 'three',
    name: '三分屏',
    slots: [
      { shape: 'rect', size: 1 / 3, height: 1, position: '0,0', border: false },
      { shape: 'rect', size: 1 / 3, height: 1, position: '0.5,0', border: false },
      { shape: 'rect', size: 1 / 3, height: 1, position: '1,0', border: false },
    ],
  },
  {
    id: 'grid',
    name: '四宫格',
    slots: [
      { shape: 'rect', size: 0.5, height: 0.5, position: '0,0', border: false },
      { shape: 'rect', size: 0.5, height: 0.5, position: '1,0', border: false },
      { shape: 'rect', size: 0.5, height: 0.5, position: '0,1', border: false },
      { shape: 'rect', size: 0.5, height: 0.5, position: '1,1', border: false },
    ],
  },
  {
    id: 'main-side',
    name: '一大两小',
    slots: [
      { shape: 'rect', size: 0.66, height: 1, position: '0,0', border: false },
      { shape: 'rect', size: 0.34, height: 0.5, position: '1,0', border: false },
      { shape: 'rect', size: 0.34, height: 0.5, position: '1,1', border: false },
    ],
  },
]

function readAsBase64(f: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const rd = new FileReader()
    rd.onload = () => resolve((rd.result as string).split(',')[1])
    rd.onerror = reject
    rd.readAsDataURL(f)
  })
}

const isVideo = (p: string) => /\.(mp4|mov|mkv|webm|m4v)$/i.test(p)
const src = (o: Overlay) => (o.image || o.video || '') as string

/**
 * 画中画编辑器: every layer of a segment on one stage, moved by dragging and sized by the corner
 * handle, the way CapCut's canvas works. What is saved is exactly what render.py draws: position
 * as free-space fractions, size as a width fraction, `height` for filled boxes, `shape` for the
 * round window.
 */
export function PipEditor({
  open,
  seg,
  segId,
  need,
  background,
  initial,
  onClose,
}: {
  open: boolean
  seg: Segment
  segId: string
  need: number
  background: string | null
  initial: number | null
  onClose: () => void
}) {
  const { raw, patch } = useProject()
  const [layers, setLayers] = useState<Overlay[]>(() => JSON.parse(JSON.stringify(seg.overlays || [])))
  const [sel, setSel] = useState<number | null>(initial)
  const [assets, setAssets] = useState<string[]>([])
  const [aspects, setAspects] = useState<Record<string, number>>({})
  const [error, setError] = useState<string | null>(null)
  const stageRef = useRef<HTMLDivElement | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const W = raw?.width || 1920
  const H = raw?.height || 1080

  useEffect(() => {
    apiGet<{ items: { path: string; kind: string }[] }>('/api/assets/library')
      .then((j) => setAssets(j.items.map((i) => i.path)))
      .catch(() => setAssets([]))
  }, [])

  // everything already in the project, this segment first
  const candidates = useMemo(() => {
    const seen = new Set<string>()
    const out: string[] = []
    const add = (p: unknown) => {
      if (typeof p === 'string' && p && !seen.has(p) && !p.includes(':')) {
        seen.add(p)
        out.push(p)
      }
    }
    seg.clips.forEach((c) => add(c.image || c.video))
    raw?.segments.forEach((s) => s.clips.forEach((c) => add(c.image || c.video)))
    assets.forEach(add)
    return out
  }, [seg, raw, assets])

  const update = (i: number, p: Partial<Overlay>) =>
    setLayers((ls) =>
      ls.map((l, j) => {
        if (j !== i) return l
        const n = { ...l, ...p }
        for (const k of Object.keys(p)) if ((p as Record<string, unknown>)[k] === undefined) delete (n as Record<string, unknown>)[k]
        return n
      }),
    )

  const add = (path: string) => {
    const o: Overlay = { [isVideo(path) ? 'video' : 'image']: path, at: 0, position: '0.97,0.95', size: 0.3, shape: 'rounded', border: true, animate: 'fade' }
    setLayers((ls) => [...ls, o])
    setSel(layers.length)
  }

  const upload = async (f: File) => {
    try {
      const j = await apiPost<{ path: string }>('/api/assets/upload', { name: f.name, data_b64: await readAsBase64(f) })
      add(j.path)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  const applyLayout = (l: Layout) => {
    setLayers((ls) => {
      const media = ls.map((x, i) => ({ x, i })).filter(({ x }) => !x.avatar && !x.me)
      const next = [...ls]
      l.slots.forEach((slot, k) => {
        const target = media[k] ?? (k === 0 ? undefined : undefined)
        if (!target) return
        const n: Overlay = { ...target.x, ...slot }
        if (slot.height === undefined) delete n.height
        next[target.i] = n
      })
      return next
    })
    if (layers.filter((x) => !x.avatar && !x.me).length < l.slots.length)
      setError(`「${l.name}」有 ${l.slots.length} 个位置，现在只有 ${layers.filter((x) => !x.avatar && !x.me).length} 个画面——多加几个，空着的位置会露出这一段本来的画面。`)
    else setError(null)
  }

  // layer box in stage fractions
  const box = (o: Overlay) => {
    const w = o.size || 0.3
    const aspect = aspects[src(o)] || (o.video ? 16 / 9 : 4 / 3)
    const h = typeof o.height === 'number' ? o.height : o.shape === 'circle' ? (w * W) / H : (w * W) / aspect / H
    const [fx, fy] = toFrac(o.position)
    return { x: (1 - w) * fx, y: (1 - h) * fy, w, h }
  }

  const drag = (i: number, mode: 'move' | 'resize', e: React.PointerEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setSel(i)
    const stage = stageRef.current!.getBoundingClientRect()
    const start = { x: e.clientX, y: e.clientY }
    const o = layers[i]
    const b = box(o)
    const move = (ev: PointerEvent) => {
      const dx = (ev.clientX - start.x) / stage.width
      const dy = (ev.clientY - start.y) / stage.height
      if (mode === 'move') {
        const fx = b.w >= 0.999 ? 0 : snap(Math.min(1, Math.max(0, (b.x + dx) / (1 - b.w))))
        const fy = b.h >= 0.999 ? 0 : snap(Math.min(1, Math.max(0, (b.y + dy) / (1 - b.h))))
        update(i, { position: `${fx},${fy}` })
      } else {
        const w = Math.min(1, Math.max(0.05, b.w + dx))
        const p: Partial<Overlay> = { size: Math.round(w * 1000) / 1000 }
        if (typeof o.height === 'number') p.height = Math.round(Math.min(1, Math.max(0.05, b.h + dy)) * 1000) / 1000
        update(i, p)
      }
    }
    const up = () => {
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerup', up)
    }
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', up)
  }

  const save = () => {
    patch((r) => {
      const s = r.segments.find((x) => x.id === segId)
      if (s) s.overlays = layers
    })
    onClose()
  }

  const o = sel != null ? layers[sel] : null

  return (
    <Dialog open={open} onClose={onClose} maxWidth="xl" fullWidth>
      <DialogTitle sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', py: 1.5 }}>
        画中画 · {seg.label || segId}
        <IconButton size="small" onClick={onClose} aria-label="关闭">
          <CloseIcon fontSize="small" />
        </IconButton>
      </DialogTitle>
      <DialogContent dividers sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: 'minmax(0,1fr) 320px' }, gap: 2 }}>
        <Box>
          <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap sx={{ mb: 1.5 }}>
            {LAYOUTS.map((l) => (
              <Button key={l.id} size="small" variant="outlined" onClick={() => applyLayout(l)}>
                {l.name}
              </Button>
            ))}
          </Stack>
          <Box
            ref={stageRef}
            onPointerDown={() => setSel(null)}
            sx={{
              position: 'relative',
              width: '100%',
              maxHeight: '64vh',
              aspectRatio: `${W} / ${H}`,
              mx: 'auto',
              bgcolor: '#111',
              backgroundImage: background ? `url("${background}")` : undefined,
              backgroundSize: 'cover',
              backgroundPosition: 'center',
              borderRadius: 1,
              overflow: 'hidden',
              userSelect: 'none',
              touchAction: 'none',
            }}
          >
            {/* centre guides: where the snap lands */}
            <Box sx={{ position: 'absolute', left: '50%', top: 0, bottom: 0, borderLeft: '1px dashed rgba(255,255,255,.15)' }} />
            <Box sx={{ position: 'absolute', top: '50%', left: 0, right: 0, borderTop: '1px dashed rgba(255,255,255,.15)' }} />
            {layers.map((l, i) => {
              const b = box(l)
              const url = l.avatar || l.me ? null : fileUrl(src(l))
              const radius = l.shape === 'circle' ? '50%' : l.shape === 'rounded' ? '8%' : 0
              return (
                <Box
                  key={i}
                  onPointerDown={(e) => drag(i, 'move', e)}
                  sx={{
                    position: 'absolute',
                    left: `${b.x * 100}%`,
                    top: `${b.y * 100}%`,
                    width: `${b.w * 100}%`,
                    height: `${b.h * 100}%`,
                    cursor: 'move',
                    outline: sel === i ? '2px solid' : '1px dashed rgba(255,255,255,.4)',
                    outlineColor: sel === i ? 'primary.main' : undefined,
                    outlineOffset: 2,
                  }}
                >
                  <Box sx={{ width: '100%', height: '100%', borderRadius: radius, overflow: 'hidden', border: l.border ? `2px solid ${(l.border_color as string) || '#fff'}` : 'none', bgcolor: '#333', boxSizing: 'border-box' }}>
                    {url && l.video ? (
                      <Box
                        component="video"
                        src={url}
                        muted
                        autoPlay
                        loop
                        playsInline
                        onLoadedMetadata={(e) => {
                          const v = e.target as HTMLVideoElement
                          if (v.videoWidth) setAspects((a) => ({ ...a, [src(l)]: v.videoWidth / v.videoHeight }))
                        }}
                        sx={{ width: '100%', height: '100%', objectFit: 'cover', pointerEvents: 'none' }}
                      />
                    ) : url ? (
                      <Box
                        component="img"
                        src={url}
                        draggable={false}
                        onLoad={(e) => {
                          const im = e.target as HTMLImageElement
                          if (im.naturalWidth) setAspects((a) => ({ ...a, [src(l)]: im.naturalWidth / im.naturalHeight }))
                        }}
                        sx={{ width: '100%', height: '100%', objectFit: 'cover', pointerEvents: 'none' }}
                      />
                    ) : (
                      <Stack alignItems="center" justifyContent="center" sx={{ height: '100%', color: '#fff', fontSize: 13 }}>
                        {l.avatar ? '主持人' : '🎥 我的镜头'}
                      </Stack>
                    )}
                  </Box>
                  {sel === i && (
                    <Box
                      onPointerDown={(e) => drag(i, 'resize', e)}
                      sx={{ position: 'absolute', right: -7, bottom: -7, width: 14, height: 14, bgcolor: 'primary.main', borderRadius: '50%', border: '2px solid #fff', cursor: 'nwse-resize' }}
                    />
                  )}
                </Box>
              )
            })}
          </Box>
          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
            拖动画面移动位置，拖右下角圆点改大小；靠近边缘和中线会自动吸附。后加的画面在上层。
          </Typography>
        </Box>

        <Box>
          <Typography variant="body2" fontWeight={600} gutterBottom>
            加画面
          </Typography>
          <Stack direction="row" spacing={1}>
            <TextField select size="small" label="从项目里选" value="" onChange={(e) => e.target.value && add(e.target.value)} sx={{ flexGrow: 1 }}>
              {candidates.length === 0 && <MenuItem disabled>项目里还没有素材</MenuItem>}
              {candidates.map((p) => (
                <MenuItem key={p} value={p}>
                  {isVideo(p) ? '🎞 ' : '🖼 '}
                  {p.split('/').pop()}
                </MenuItem>
              ))}
            </TextField>
            <Tooltip title="上传图片或视频">
              <IconButton onClick={() => fileRef.current?.click()}>
                <UploadIcon />
              </IconButton>
            </Tooltip>
            <input ref={fileRef} type="file" hidden accept="image/*,video/*" onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} />
          </Stack>

          <Divider sx={{ my: 1.5 }} />
          <Typography variant="body2" fontWeight={600} gutterBottom>
            图层（{layers.length}）
          </Typography>
          <Stack spacing={0.5} sx={{ mb: 1.5 }}>
            {layers.map((l, i) => (
              <Stack
                key={i}
                direction="row"
                alignItems="center"
                spacing={0.5}
                onClick={() => setSel(i)}
                sx={{ px: 1, py: 0.25, borderRadius: 1, cursor: 'pointer', bgcolor: sel === i ? 'action.selected' : 'transparent' }}
              >
                <Typography variant="body2" sx={{ flexGrow: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {i + 1}. {l.avatar ? '主持人' : l.me ? '我的镜头' : src(l).split('/').pop()}
                </Typography>
                <IconButton size="small" disabled={i === 0} onClick={() => setLayers((ls) => { const n = [...ls]; [n[i - 1], n[i]] = [n[i], n[i - 1]]; return n })}>
                  <ArrowDownwardIcon fontSize="inherit" />
                </IconButton>
                <IconButton size="small" disabled={i === layers.length - 1} onClick={() => setLayers((ls) => { const n = [...ls]; [n[i + 1], n[i]] = [n[i], n[i + 1]]; return n })}>
                  <ArrowUpwardIcon fontSize="inherit" />
                </IconButton>
                <IconButton size="small" onClick={() => { setLayers((ls) => ls.filter((_, j) => j !== i)); setSel(null) }}>
                  <DeleteIcon fontSize="inherit" />
                </IconButton>
              </Stack>
            ))}
          </Stack>

          {o && sel != null && (
            <>
              <Divider sx={{ mb: 1.5 }} />
              <Typography variant="body2" fontWeight={600} gutterBottom>
                第 {sel + 1} 层
              </Typography>
              <Stack spacing={1.25}>
                {!o.avatar && !o.me && (
                  <ToggleButtonGroup size="small" exclusive value={(o.shape as string) || 'rect'} onChange={(_, v) => v && update(sel, { shape: v })}>
                    <ToggleButton value="rect">方形</ToggleButton>
                    <ToggleButton value="rounded">圆角</ToggleButton>
                    <ToggleButton value="circle">圆形</ToggleButton>
                  </ToggleButtonGroup>
                )}
                <Box>
                  <Typography variant="caption" color="text.secondary">
                    宽度 {Math.round((o.size || 0.3) * 100)}%
                  </Typography>
                  <Slider size="small" min={5} max={100} value={Math.round((o.size || 0.3) * 100)} onChange={(_, v) => update(sel, { size: (v as number) / 100 })} />
                </Box>
                {!o.avatar && !o.me && (
                  <FormControlLabel
                    control={<Switch size="small" checked={typeof o.height === 'number'} onChange={(e) => update(sel, { height: e.target.checked ? Math.round(box(o).h * 1000) / 1000 : undefined })} />}
                    label={<Typography variant="body2">固定框（裁切铺满，做分屏用）</Typography>}
                  />
                )}
                {typeof o.height === 'number' && (
                  <Box>
                    <Typography variant="caption" color="text.secondary">
                      高度 {Math.round(o.height * 100)}%
                    </Typography>
                    <Slider size="small" min={5} max={100} value={Math.round(o.height * 100)} onChange={(_, v) => update(sel, { height: (v as number) / 100 })} />
                  </Box>
                )}
                <Stack direction="row" spacing={1} alignItems="center">
                  <FormControlLabel control={<Switch size="small" checked={o.border !== false} onChange={(e) => update(sel, { border: e.target.checked })} />} label={<Typography variant="body2">描边</Typography>} />
                  {o.border !== false && !o.avatar && (
                    <Box component="input" type="color" value={(o.border_color as string) || '#ffffff'} onChange={(e) => update(sel, { border_color: (e.target as HTMLInputElement).value })} sx={{ width: 32, height: 24, border: 0, p: 0, bgcolor: 'transparent' }} />
                  )}
                </Stack>
                <Stack direction="row" spacing={1}>
                  <TextField size="small" type="number" label="出现于 (s)" value={o.at ?? 0} onChange={(e) => update(sel, { at: Math.max(0, parseFloat(e.target.value) || 0) })} inputProps={{ step: 0.1 }} />
                  <TextField size="small" type="number" label="持续 (s，空=到段末)" value={o.duration ?? ''} onChange={(e) => update(sel, { duration: parseFloat(e.target.value) > 0 ? parseFloat(e.target.value) : undefined })} inputProps={{ step: 0.1 }} />
                </Stack>
                <Typography variant="caption" color="text.secondary">
                  这一段旁白约 {need.toFixed(1)} 秒
                </Typography>
                <TextField select size="small" label="进场" value={o.animate || 'slide'} onChange={(e) => update(sel, { animate: e.target.value })}>
                  <MenuItem value="fade">淡入</MenuItem>
                  <MenuItem value="slide">滑入</MenuItem>
                  <MenuItem value="none">直接出现</MenuItem>
                </TextField>
              </Stack>
            </>
          )}
          {error && (
            <Typography variant="caption" color="warning.main" sx={{ display: 'block', mt: 1 }}>
              {error}
            </Typography>
          )}
        </Box>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>取消</Button>
        <Button variant="contained" onClick={save}>
          保存
        </Button>
      </DialogActions>
    </Dialog>
  )
}
