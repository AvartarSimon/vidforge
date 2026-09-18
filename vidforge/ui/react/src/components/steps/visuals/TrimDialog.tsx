import { useRef, useState } from 'react'
import {
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  IconButton,
  Slider,
  Stack,
  Typography,
} from '@mui/material'
import CloseIcon from '@mui/icons-material/Close'
import DeleteIcon from '@mui/icons-material/Delete'

export interface TrimRange {
  in: number
  out: number
}

// one or more [in,out] ranges over a preview player; each range becomes its own clip on "加入".
// Mirrors vidforge/ui/static/app.js's openTrim() — same range-list + two-thumb-slider approach.
export function TrimDialog({
  open,
  url,
  duration: initialDuration,
  ranges: initialRanges,
  onClose,
  onDone,
}: {
  open: boolean
  url: string
  duration?: number | null
  ranges?: TrimRange[]
  onClose: () => void
  onDone: (ranges: TrimRange[]) => void
}) {
  const [duration, setDuration] = useState(initialDuration || 0)
  const [ranges, setRanges] = useState<TrimRange[]>(
    (initialRanges && initialRanges.length ? initialRanges : [{ in: 0, out: null as unknown as number }]).map((r) => ({
      in: r.in || 0,
      out: r.out ?? Math.min((initialDuration || 0) || 10, (r.in || 0) + 5),
    })),
  )
  const [cur, setCur] = useState(0)
  const videoRef = useRef<HTMLVideoElement>(null)
  const stopAtRef = useRef<number | null>(null)

  const r = ranges[cur] || ranges[0]

  const update = (i: number, patch: Partial<TrimRange>) => setRanges((rs) => rs.map((x, idx) => (idx === i ? { ...x, ...patch } : x)))

  const onLoadedMetadata = () => {
    if (!initialDuration && videoRef.current) {
      const d = videoRef.current.duration
      setDuration(d)
      setRanges((rs) => rs.map((x) => ({ ...x, out: x.out || Math.min(d, x.in + 5) })))
    }
  }

  const addRange = () => {
    const last = ranges[ranges.length - 1]
    const start = Math.min(last.out ?? 0, (duration || 1e9) - 0.5)
    setRanges((rs) => [...rs, { in: start, out: Math.min(duration || start + 5, start + 5) }])
    setCur(ranges.length)
  }

  const delRange = (i: number) => {
    setRanges((rs) => rs.filter((_, idx) => idx !== i))
    // keep pointing at the same logical range: shift left by one if the deleted range was
    // before (or was) the selected one, then clamp to the new (shorter) list.
    setCur((c) => Math.max(0, Math.min(i <= c ? c - 1 : c, ranges.length - 2)))
  }

  const playSelected = () => {
    const v = videoRef.current
    if (!v) return
    v.currentTime = r.in
    stopAtRef.current = r.out
    v.play()
  }

  const onTimeUpdate = () => {
    const v = videoRef.current
    if (!v || stopAtRef.current == null) return
    if (v.currentTime >= stopAtRef.current) {
      v.pause()
      stopAtRef.current = null
    }
  }

  const total = ranges.reduce((t, x) => t + ((x.out ?? x.in) - x.in), 0)

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        选择片段范围
        <IconButton size="small" onClick={onClose} aria-label="关闭">
          <CloseIcon fontSize="small" />
        </IconButton>
      </DialogTitle>
      <DialogContent dividers>
        <Stack spacing={1.5}>
          <video ref={videoRef} src={url} controls muted playsInline style={{ width: '100%' }} onLoadedMetadata={onLoadedMetadata} onTimeUpdate={onTimeUpdate} />
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
            {ranges.map((x, i) => (
              <Button key={i} size="small" variant={i === cur ? 'contained' : 'outlined'} onClick={() => setCur(i)} endIcon={
                ranges.length > 1 ? (
                  <DeleteIcon fontSize="inherit" onClick={(e) => { e.stopPropagation(); delRange(i) }} />
                ) : undefined
              }>
                段 {i + 1}: {x.in.toFixed(1)}–{(x.out ?? 0).toFixed(1)} s
              </Button>
            ))}
          </Stack>
          <div>
            <Typography variant="caption" color="text.secondary">
              第 {cur + 1} 段：{r.in.toFixed(1)} – {(r.out ?? 0).toFixed(1)} s
            </Typography>
            <Slider
              value={[r.in, r.out ?? Math.min(duration || r.in + 5, r.in + 5)]}
              min={0}
              max={duration || 60}
              step={0.1}
              onChange={(_, v) => {
                const [lo, hi] = v as number[]
                update(cur, { in: lo, out: Math.max(hi, lo + 0.2) })
              }}
            />
          </div>
          <Typography variant="caption" color="text.secondary">
            共 {ranges.length} 段 · 已选 {total.toFixed(1)} s{duration ? ` / 素材 ${duration.toFixed(1)} s` : ''}
          </Typography>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={addRange}>＋ 再加一段</Button>
        <Button onClick={playSelected}>▶ 播放所选</Button>
        <Button variant="contained" onClick={() => onDone(ranges.map((x) => ({ in: x.in, out: x.out })))}>
          加入
        </Button>
      </DialogActions>
    </Dialog>
  )
}
