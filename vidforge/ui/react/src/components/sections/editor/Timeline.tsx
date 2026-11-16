import { useMemo, useRef, useState } from 'react'
import { Box, Typography } from '@mui/material'
import type { ProjectView, RawProject, Segment } from '../../../api/types'
import { fileUrl } from '../../../utils'

export type Span = { id: string; start: number; end: number }

/** Where each segment sits in time: the rendered timeline when there is one (true lengths,
 * brand clips included), otherwise the narration estimates laid end to end. */
export function layout(raw: RawProject, view: ProjectView | null): { spans: Span[]; total: number; offset: number } {
  const tl = view?.outputs?.timeline
  const ids = new Set(raw.segments.map((s) => s.id))
  if (tl && tl.length && raw.segments.every((s) => tl.some((t) => t.id === s.id))) {
    const spans = tl.filter((t) => ids.has(t.id)).map((t) => ({ id: t.id, start: t.start, end: t.end }))
    // keep the project's order even if the render is older than a reorder
    spans.sort((a, b) => raw.segments.findIndex((s) => s.id === a.id) - raw.segments.findIndex((s) => s.id === b.id))
    const total = Math.max(...tl.map((t) => t.end))
    return { spans, total, offset: 0 }
  }
  let t = 0
  const spans = raw.segments.map((s) => {
    const r = view?.resolved?.[s.id]
    const len = Math.max(1, (r?.duration || r?.need || (s.text || '').length / 4) + (s.pause_after ?? 0.5))
    const span = { id: s.id, start: t, end: t + len }
    t += len
    return span
  })
  return { spans, total: t, offset: 0 }
}

function thumb(seg: Segment, view: ProjectView | null): string | null {
  const c = view?.resolved?.[seg.id]?.clips?.[0]
  if (!c?.path) return null
  return c.kind === 'video' ? `/api/poster/${encodeURIComponent(seg.id)}/0` : fileUrl(c.path)
}

const fmt = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`
const TRACK_H = 40
const LABEL_W = 64

/**
 * The bottom timeline, read the way 剪映's is: a ruler, then 画面 / 画中画 / 配音 / 字幕 tracks,
 * one block per segment, the playhead across all of them. Click a block to select its segment
 * (and seek there); drag a picture block onto another to move the segment in front of it.
 */
export function Timeline({
  raw,
  view,
  selId,
  time,
  zoom,
  onSelect,
  onSeek,
  onMove,
}: {
  raw: RawProject
  view: ProjectView | null
  selId: string | null
  time: number
  zoom: number // px per second
  onSelect: (id: string) => void
  onSeek: (t: number) => void
  onMove: (id: string, beforeId: string | null) => void
}) {
  const { spans, total } = useMemo(() => layout(raw, view), [raw, view])
  const scrollRef = useRef<HTMLDivElement | null>(null)
  const [dragOver, setDragOver] = useState<string | null>(null)
  const width = Math.max(600, total * zoom + 80)
  const byId = Object.fromEntries(raw.segments.map((s) => [s.id, s]))
  const step = zoom > 40 ? 1 : zoom > 16 ? 5 : zoom > 6 ? 10 : 30

  const seekFromEvent = (e: React.MouseEvent) => {
    const el = scrollRef.current
    if (!el) return
    const x = e.clientX - el.getBoundingClientRect().left + el.scrollLeft - LABEL_W
    onSeek(Math.max(0, Math.min(total, x / zoom)))
  }

  const track = (label: string, children: React.ReactNode) => (
    <Box sx={{ position: 'relative', height: TRACK_H, borderBottom: '1px solid', borderColor: 'divider' }}>
      <Box sx={{ position: 'sticky', left: 0, zIndex: 2, width: LABEL_W, height: '100%', display: 'flex', alignItems: 'center', px: 1, bgcolor: 'background.paper', borderRight: '1px solid', borderColor: 'divider', float: 'left' }}>
        <Typography sx={{ fontSize: 11.5, color: 'text.secondary', fontWeight: 600 }}>{label}</Typography>
      </Box>
      <Box sx={{ position: 'absolute', left: LABEL_W, top: 0, bottom: 0, right: 0 }}>{children}</Box>
    </Box>
  )

  return (
    <Box ref={scrollRef} sx={{ overflowX: 'auto', overflowY: 'hidden', position: 'relative', userSelect: 'none', height: '100%' }}>
      <Box sx={{ width: width + LABEL_W, position: 'relative' }}>
        {/* ruler */}
        <Box onClick={seekFromEvent} sx={{ position: 'relative', height: 24, borderBottom: '1px solid', borderColor: 'divider', cursor: 'pointer', ml: `${LABEL_W}px` }}>
          {Array.from({ length: Math.floor(total / step) + 1 }, (_, i) => i * step).map((t) => (
            <Box key={t} sx={{ position: 'absolute', left: t * zoom, top: 0, bottom: 0, borderLeft: '1px solid', borderColor: 'divider', pl: 0.5 }}>
              <Typography sx={{ fontSize: 10.5, color: 'text.secondary', lineHeight: '22px' }}>{fmt(t)}</Typography>
            </Box>
          ))}
        </Box>

        {track(
          '画面',
          spans.map((sp) => {
            const s = byId[sp.id]
            const img = thumb(s, view)
            const sel = sp.id === selId
            return (
              <Box
                key={sp.id}
                draggable
                onDragStart={(e) => e.dataTransfer.setData('text/x-seg', sp.id)}
                onDragOver={(e) => {
                  e.preventDefault()
                  setDragOver(sp.id)
                }}
                onDragLeave={() => setDragOver(null)}
                onDrop={(e) => {
                  e.preventDefault()
                  setDragOver(null)
                  const id = e.dataTransfer.getData('text/x-seg')
                  if (id && id !== sp.id) onMove(id, sp.id)
                }}
                onClick={(e) => {
                  e.stopPropagation()
                  onSelect(sp.id)
                  onSeek(sp.start)
                }}
                title={`${s.label || s.id} · ${(sp.end - sp.start).toFixed(1)}s`}
                sx={{
                  position: 'absolute',
                  left: sp.start * zoom + 1,
                  width: Math.max(4, (sp.end - sp.start) * zoom - 2),
                  top: 3,
                  bottom: 3,
                  borderRadius: 1,
                  overflow: 'hidden',
                  cursor: 'grab',
                  bgcolor: s.clips.length ? '#2b3a40' : 'rgba(240,84,79,.25)',
                  backgroundImage: img ? `url("${img}")` : undefined,
                  backgroundSize: 'auto 100%',
                  backgroundRepeat: 'repeat-x',
                  outline: sel ? '2px solid' : dragOver === sp.id ? '2px dashed' : '1px solid rgba(255,255,255,.12)',
                  outlineColor: sel || dragOver === sp.id ? 'primary.main' : undefined,
                  outlineOffset: -1,
                }}
              >
                <Typography noWrap sx={{ fontSize: 11, color: '#fff', px: 0.75, lineHeight: '16px', bgcolor: 'rgba(0,0,0,.55)', display: 'inline-block', maxWidth: '100%', borderBottomRightRadius: 4 }}>
                  {s.label || s.id}
                  {s.clips.length > 1 ? ` · ${s.clips.length}` : ''}
                  {!s.clips.length ? ' · 没画面' : ''}
                </Typography>
              </Box>
            )
          }),
        )}

        {track(
          '画中画',
          spans.flatMap((sp) =>
            (byId[sp.id].overlays || []).map((o, i) => {
              const a = sp.start + (o.at || 0)
              const b = o.duration ? Math.min(sp.end, a + o.duration) : sp.end
              return (
                <Box
                  key={`${sp.id}-${i}`}
                  onClick={(e) => {
                    e.stopPropagation()
                    onSelect(sp.id)
                  }}
                  title={`${o.avatar ? '主持人' : o.video ? '视频' : '图片'}${o.shape === 'circle' ? '（圆）' : ''}`}
                  sx={{ position: 'absolute', left: a * zoom + 1, width: Math.max(4, (b - a) * zoom - 2), top: 8 + (i % 2) * 6, height: 18, borderRadius: 1, bgcolor: 'rgba(127,179,255,.35)', border: '1px solid rgba(127,179,255,.7)', cursor: 'pointer' }}
                />
              )
            }),
          ),
        )}

        {track(
          '配音',
          spans.map((sp) => {
            const s = byId[sp.id]
            const own = Boolean(s.narration)
            const fresh = view?.resolved?.[sp.id]?.audio_fresh
            return (
              <Box
                key={sp.id}
                onClick={(e) => {
                  e.stopPropagation()
                  onSelect(sp.id)
                  onSeek(sp.start)
                }}
                title={own ? '我自己的录音' : fresh ? 'AI 配音（已生成）' : 'AI 配音（还没生成）'}
                sx={{
                  position: 'absolute',
                  left: sp.start * zoom + 1,
                  width: Math.max(4, (sp.end - sp.start - (s.pause_after ?? 0.5)) * zoom - 2),
                  top: 8,
                  bottom: 8,
                  borderRadius: 1,
                  cursor: 'pointer',
                  // a fake waveform: enough to tell speech blocks apart at a glance
                  background: own
                    ? 'repeating-linear-gradient(90deg, rgba(231,111,81,.85) 0 2px, rgba(231,111,81,.35) 2px 4px)'
                    : `repeating-linear-gradient(90deg, rgba(31,200,200,${fresh ? 0.75 : 0.3}) 0 2px, rgba(31,200,200,${fresh ? 0.3 : 0.12}) 2px 4px)`,
                }}
              />
            )
          }),
        )}

        {track(
          '字幕',
          spans.map((sp) => (
            <Box
              key={sp.id}
              onClick={(e) => {
                e.stopPropagation()
                onSelect(sp.id)
                onSeek(sp.start)
              }}
              sx={{ position: 'absolute', left: sp.start * zoom + 1, width: Math.max(4, (sp.end - sp.start) * zoom - 2), top: 9, bottom: 9, borderRadius: 1, bgcolor: 'action.hover', overflow: 'hidden', cursor: 'pointer' }}
            >
              <Typography noWrap sx={{ fontSize: 11, px: 0.75, lineHeight: '22px', color: 'text.secondary' }}>
                {byId[sp.id].text}
              </Typography>
            </Box>
          )),
        )}

        {/* playhead */}
        <Box sx={{ position: 'absolute', top: 0, bottom: 0, left: LABEL_W + time * zoom, width: 2, bgcolor: 'primary.main', pointerEvents: 'none', zIndex: 3 }}>
          <Box sx={{ position: 'absolute', top: 0, left: -5, width: 12, height: 10, bgcolor: 'primary.main', clipPath: 'polygon(0 0, 100% 0, 50% 100%)' }} />
        </Box>
      </Box>
    </Box>
  )
}
