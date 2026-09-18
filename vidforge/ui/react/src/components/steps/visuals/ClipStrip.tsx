import { useState } from 'react'
import {
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  IconButton,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from '@mui/material'
import ArrowBackIcon from '@mui/icons-material/ArrowBack'
import ArrowForwardIcon from '@mui/icons-material/ArrowForward'
import DeleteIcon from '@mui/icons-material/Delete'
import { apiPost } from '../../../api/client'
import type { Clip, Overlay, ResolvedClip, ResolvedSegment, Segment } from '../../../api/types'
import { useProject } from '../../../state/ProjectContext'
import { fileUrl, fmtDuration } from '../../../utils'
import { SegmentHistoryDialog } from '../../shared/SegmentHistoryDialog'
import { OverlayDialog } from './OverlayDialog'
import { TrimDialog, type TrimRange } from './TrimDialog'

const MOTIONS = ['zoom_in', 'zoom_out', 'pan_left', 'pan_right', 'none']

function clipSeconds(c: Clip, r?: ResolvedClip) {
  if (c.video && c.out != null) return c.out - (c.in || 0)
  if (c.image && c.duration) return c.duration
  return r?.natural || null
}

function clipThumb(c: Clip, r?: ResolvedClip) {
  if (c.me) return { kind: 'text' as const, text: `🎥 我的镜头 (${(c.me.tags || []).join(' ') || '任意'})` }
  if (c.remotion) return { kind: 'text' as const, text: c.remotion.composition }
  if (r?.path && r.kind === 'video') return { kind: 'poster' as const, seg: r.index }
  if (r?.path) return { kind: 'img' as const, src: fileUrl(r.path) }
  return { kind: 'text' as const, text: '未设置' }
}

export function ClipStrip({ seg, segId }: { seg: Segment; segId: string }) {
  const { view, patch, saveNow } = useProject()
  const [previewing, setPreviewing] = useState(false)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [previewInfo, setPreviewInfo] = useState('')
  const [historyOpen, setHistoryOpen] = useState(false)
  const [overlayEditor, setOverlayEditor] = useState<{ index: number | null } | null>(null) // index null = adding
  const [trimTarget, setTrimTarget] = useState<{ index: number; mode: 'replace' | 'more' } | null>(null)

  const r: Partial<ResolvedSegment> = view?.resolved[segId] || {}
  const need = r.need || 0
  const fixed = seg.clips.reduce((a, c, i) => a + (clipSeconds(c, r.clips?.[i]) || 0), 0)
  const flex = seg.clips.filter((c, i) => !clipSeconds(c, r.clips?.[i])).length

  let status: { text: string; color: 'error.main' | 'warning.main' | 'success.main' }
  if (!seg.clips.length) status = { text: '还没有画面', color: 'error.main' }
  else if (fixed > need + 0.5) status = { text: `已选 ${fmtDuration(fixed)}，超出旁白 ${fmtDuration(fixed - need)}，末尾会被裁掉`, color: 'warning.main' }
  else if (flex) status = { text: `固定 ${fmtDuration(fixed)} + ${flex} 个自适应片段补满 ${fmtDuration(need)}`, color: 'success.main' }
  else if (fixed < need - 0.5)
    status = {
      text: `已选 ${fmtDuration(fixed)} / 需要 ${fmtDuration(need)}，最后一个片段会${seg.clips[seg.clips.length - 1]?.video ? '循环' : '延长'}补齐`,
      color: 'warning.main',
    }
  else status = { text: `已选 ${fmtDuration(fixed)} ≈ 需要 ${fmtDuration(need)}`, color: 'success.main' }

  const mutateClips = (fn: (clips: Clip[]) => void) =>
    patch((raw) => {
      const s = raw.segments.find((x) => x.id === segId)
      if (s) fn(s.clips)
    })

  const move = (i: number, dir: -1 | 1) =>
    mutateClips((clips) => {
      const [item] = clips.splice(i, 1)
      clips.splice(i + dir, 0, item)
    })
  const remove = (i: number) => mutateClips((clips) => clips.splice(i, 1))
  const setMotion = (i: number, motion: string) => mutateClips((clips) => (clips[i].motion = motion))
  const setDuration = (i: number, v: string) =>
    mutateClips((clips) => {
      const d = parseFloat(v)
      if (d > 0) clips[i].duration = d
      else delete clips[i].duration
    })

  const applyTrim = (ranges: TrimRange[]) => {
    if (!trimTarget) return
    const { index, mode } = trimTarget
    mutateClips((clips) => {
      const c = clips[index]
      if (mode === 'replace') {
        c.in = ranges[0].in
        c.out = ranges[0].out
        ranges.slice(1).forEach((r, k) => clips.splice(index + 1 + k, 0, { video: c.video, in: r.in, out: r.out, credit: c.credit }))
      } else {
        ranges.forEach((r, k) => clips.splice(index + 1 + k, 0, { video: c.video, in: r.in, out: r.out, credit: c.credit }))
      }
    })
    setTrimTarget(null)
  }

  const duplicate = () =>
    patch((raw) => {
      const i = raw.segments.findIndex((x) => x.id === segId)
      const copy: Segment = JSON.parse(JSON.stringify(raw.segments[i]))
      copy.id = `${segId}_copy${Date.now() % 10000}`
      raw.segments.splice(i + 1, 0, copy)
    })

  const setPause = (v: string) =>
    patch((raw) => {
      const s = raw.segments.find((x) => x.id === segId)
      if (s) s.pause_after = parseFloat(v) || 0
    })
  const setFit = (v: string) =>
    patch((raw) => {
      const s = raw.segments.find((x) => x.id === segId)
      if (s) s.fit = v
    })

  const mutateOverlays = (fn: (overlays: Overlay[]) => void) =>
    patch((raw) => {
      const s = raw.segments.find((x) => x.id === segId)
      if (!s) return
      s.overlays = s.overlays || []
      fn(s.overlays)
    })
  const addAvatarOverlay = () =>
    mutateOverlays((overlays) => overlays.push({ avatar: true, position: 'bottom-right', size: 0.28 }))
  const removeOverlay = (i: number) => mutateOverlays((overlays) => overlays.splice(i, 1))
  const saveOverlay = (o: Overlay) => {
    mutateOverlays((overlays) => {
      if (overlayEditor?.index != null) overlays[overlayEditor.index] = o
      else overlays.push(o)
    })
    setOverlayEditor(null)
  }
  const overlayLabel = (o: Overlay) =>
    `${o.avatar ? '主持人' : o.me ? '🎥 我' : o.video ? '视频' : '图片'} · ${o.position || 'bottom-right'} · ${Math.round((o.size || 0.3) * 100)}% · ${o.at || 0}s${o.duration ? `→${(o.at || 0) + o.duration}s` : '→末'}`

  const preview = async () => {
    if (!seg.clips.length) {
      window.alert('先给这一段加画面')
      return
    }
    if (!(await saveNow())) return
    setPreviewing(true)
    setPreviewInfo('渲染中（配音 + 画面，通常 5–30 秒）…')
    try {
      const j = await apiPost<{ video: string; duration: number; stamp: number }>('/api/preview', { id: segId })
      setPreviewUrl(fileUrl(j.video, j.stamp))
      setPreviewInfo(`${fmtDuration(j.duration)} · 草稿质量，成片会更清晰`)
    } catch (e) {
      setPreviewInfo(e instanceof Error ? e.message : String(e))
    }
    setPreviewing(false)
  }

  return (
    <Card variant="outlined">
      <CardContent>
        <Stack direction="row" justifyContent="space-between">
          <Typography variant="subtitle1" fontWeight={600}>
            {segId}
          </Typography>
          <Typography variant="body2" color={status.color}>
            {status.text}
          </Typography>
        </Stack>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
          {seg.text}
        </Typography>
        <Stack direction="row" spacing={1} sx={{ overflowX: 'auto', pb: 1 }}>
          {seg.clips.map((c, i) => {
            const rc = r.clips?.[i]
            const thumb = clipThumb(c, rc)
            return (
              <Box
                key={i}
                sx={{ width: 160, flexShrink: 0, border: '1px solid', borderColor: 'divider', borderRadius: 2, p: 1 }}
              >
                <Box
                  sx={{
                    height: 70,
                    bgcolor: 'action.hover',
                    borderRadius: 1,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontSize: 11,
                    overflow: 'hidden',
                    mb: 0.5,
                  }}
                >
                  {thumb.kind === 'img' && thumb.src ? (
                    <img src={thumb.src} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                  ) : thumb.kind === 'poster' ? (
                    <img
                      src={`/api/poster/${encodeURIComponent(segId)}/${thumb.seg}`}
                      alt=""
                      style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                    />
                  ) : (
                    <span>{'text' in thumb ? thumb.text : ''}</span>
                  )}
                </Box>
                <Chip
                  size="small"
                  label={c.me ? '我' : c.remotion ? '动画' : c.video ? '视频' : '图片'}
                  sx={{ mb: 0.5 }}
                />
                <Stack direction="row" justifyContent="space-between">
                  <IconButton size="small" disabled={i === 0} onClick={() => move(i, -1)}>
                    <ArrowBackIcon fontSize="inherit" />
                  </IconButton>
                  <IconButton size="small" disabled={i === seg.clips.length - 1} onClick={() => move(i, 1)}>
                    <ArrowForwardIcon fontSize="inherit" />
                  </IconButton>
                  <IconButton size="small" onClick={() => remove(i)}>
                    <DeleteIcon fontSize="inherit" />
                  </IconButton>
                </Stack>
                {c.image && (
                  <Stack spacing={0.5} sx={{ mt: 0.5 }}>
                    <TextField
                      select
                      size="small"
                      value={c.motion || 'zoom_in'}
                      onChange={(e) => setMotion(i, e.target.value)}
                    >
                      {MOTIONS.map((m) => (
                        <MenuItem key={m} value={m}>
                          {m}
                        </MenuItem>
                      ))}
                    </TextField>
                    <TextField
                      size="small"
                      type="number"
                      placeholder="自适应"
                      value={c.duration ?? ''}
                      onChange={(e) => setDuration(i, e.target.value)}
                    />
                  </Stack>
                )}
                {c.video && (
                  <Stack spacing={0.25} sx={{ mt: 0.5 }}>
                    <Typography variant="caption" color="text.secondary">
                      {c.out != null ? `${(c.in || 0).toFixed(1)}→${c.out.toFixed(1)}s` : '整段'}
                    </Typography>
                    <Stack direction="row" spacing={0.5}>
                      <Button size="small" onClick={() => setTrimTarget({ index: i, mode: 'replace' })}>
                        选段
                      </Button>
                      <Button size="small" title="用同一个视频再选几段" onClick={() => setTrimTarget({ index: i, mode: 'more' })}>
                        再选
                      </Button>
                    </Stack>
                  </Stack>
                )}
              </Box>
            )
          })}
        </Stack>
        <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap sx={{ mt: 1 }}>
          <Typography variant="caption" fontWeight={600}>
            画中画
          </Typography>
          {(seg.overlays || []).map((o, i) => (
            <Chip
              key={i}
              size="small"
              label={overlayLabel(o)}
              onClick={o.avatar || o.me ? undefined : () => setOverlayEditor({ index: i })}
              onDelete={() => removeOverlay(i)}
            />
          ))}
          <Button size="small" onClick={() => setOverlayEditor({ index: null })}>
            ＋ 图片/视频
          </Button>
          <Button size="small" onClick={addAvatarOverlay} title="这一段加数字主持人（第 4 步可设外观）">
            ＋ 主持人
          </Button>
        </Stack>
        <Stack direction="row" spacing={2} alignItems="center" sx={{ mt: 1 }}>
          <TextField select size="small" label="片段不够长时" value={seg.fit === 'trim' ? 'trim' : 'stretch'} onChange={(e) => setFit(e.target.value)} sx={{ minWidth: 220 }}>
            <MenuItem value="stretch">延长/循环最后一个片段</MenuItem>
            <MenuItem value="trim">同上（保留字段）</MenuItem>
          </TextField>
          <TextField
            size="small"
            type="number"
            label="说完停顿 (s)"
            value={seg.pause_after ?? 0.5}
            onChange={(e) => setPause(e.target.value)}
            sx={{ width: 140 }}
          />
        </Stack>
        <Stack direction="row" spacing={1} alignItems="center" sx={{ mt: 1 }}>
          <Button onClick={preview} disabled={previewing}>
            ▶ 预览这一段（草稿质量）
          </Button>
          <Button size="small" onClick={duplicate} title="复制这一段到后面">
            复制一段
          </Button>
          <Button size="small" title="这一段的历史版本" onClick={() => setHistoryOpen(true)}>
            版本
          </Button>
          <Typography variant="caption" color="text.secondary">
            {previewInfo}
          </Typography>
        </Stack>
        {previewUrl && (
          <Box sx={{ mt: 1 }}>
            <video controls autoPlay style={{ maxWidth: 480 }} src={previewUrl} />
          </Box>
        )}
        <SegmentHistoryDialog segId={segId} open={historyOpen} onClose={() => setHistoryOpen(false)} />
        {overlayEditor && (
          <OverlayDialog
            open
            seg={seg}
            existing={overlayEditor.index != null ? seg.overlays?.[overlayEditor.index] || null : null}
            need={need}
            onClose={() => setOverlayEditor(null)}
            onSave={saveOverlay}
          />
        )}
        {trimTarget && (
          <TrimDialog
            open
            url={fileUrl(r.clips?.[trimTarget.index]?.path) || ''}
            duration={null}
            ranges={
              trimTarget.mode === 'replace'
                ? [{ in: seg.clips[trimTarget.index].in || 0, out: seg.clips[trimTarget.index].out ?? 0 }]
                : [{ in: seg.clips[trimTarget.index].out || 0, out: (seg.clips[trimTarget.index].out || 0) + 5 }]
            }
            onClose={() => setTrimTarget(null)}
            onDone={applyTrim}
          />
        )}
      </CardContent>
    </Card>
  )
}
