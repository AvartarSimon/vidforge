import { useEffect, useMemo, useRef, useState } from 'react'
import { Box, Button, Divider, IconButton, Paper, Slider, Stack, Tab, Tabs, TextField, Tooltip, Typography } from '@mui/material'
import PlayArrowIcon from '@mui/icons-material/PlayArrow'
import PauseIcon from '@mui/icons-material/Pause'
import ContentCopyIcon from '@mui/icons-material/ContentCopy'
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline'
import AddIcon from '@mui/icons-material/Add'
import ChevronLeftIcon from '@mui/icons-material/ChevronLeft'
import ChevronRightIcon from '@mui/icons-material/ChevronRight'
import ZoomInIcon from '@mui/icons-material/ZoomIn'
import MovieIcon from '@mui/icons-material/Movie'
import VideocamIcon from '@mui/icons-material/Videocam'
import { apiPost } from '../../api/client'
import type { Segment } from '../../api/types'
import { useProject } from '../../state/ProjectContext'
import { fileUrl } from '../../utils'
import { ClipStrip } from '../steps/visuals/ClipStrip'
import { PickerPanel } from '../steps/visuals/PickerPanel'
import { RenderSettingsCard } from '../steps/render/RenderSettingsCard'
import { ThemePicker } from '../shared/ThemePicker'
import { Timeline, layout } from './editor/Timeline'

const fmt = (s: number) => `${Math.floor(s / 60)}:${(s % 60).toFixed(1).padStart(4, '0')}`

/**
 * 剪辑台: the 剪映 layout over the same project.json the wizard edits — materials on the left,
 * the player in the middle, the selected segment's properties on the right, the timeline along the
 * bottom. Nothing here is a second model of the video: every block is a segment, every edit is a
 * patch to project.json, so the wizard and this page can never disagree.
 *
 * The player shows the last full render (with the playhead following it) and, for a segment you
 * are working on, a fast draft preview of just that segment.
 */
export function EditorSection({ onOpen }: { onOpen: (where: 'studio' | 'render') => void }) {
  const { raw, view, patch, reload } = useProject()
  const [selId, setSelId] = useState<string | null>(raw?.segments[0]?.id ?? null)
  const [time, setTime] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [zoom, setZoom] = useState(14)
  const [leftTab, setLeftTab] = useState(0)
  const [rightTab, setRightTab] = useState(0)
  const [segPreview, setSegPreview] = useState<{ id: string; url: string } | null>(null)
  const [previewing, setPreviewing] = useState(false)
  const videoRef = useRef<HTMLVideoElement | null>(null)

  useEffect(() => {
    if (raw && (!selId || !raw.segments.some((s) => s.id === selId))) setSelId(raw.segments[0]?.id ?? null)
  }, [raw, selId])

  const spans = useMemo(() => (raw ? layout(raw, view).spans : []), [raw, view])
  if (!raw) return null
  const seg = raw.segments.find((s) => s.id === selId) || null
  const segIndex = raw.segments.findIndex((s) => s.id === selId)
  const final = view?.outputs?.final ? fileUrl(view.outputs.final, view.outputs.final_mtime) : null
  const playerSrc = segPreview && segPreview.id === selId ? segPreview.url : final
  const usingFinal = playerSrc === final
  const total = spans.length ? spans[spans.length - 1].end : 0

  // follow the playhead into whichever segment it is over
  const onTime = (t: number) => {
    setTime(t)
    if (!usingFinal) return
    const sp = spans.find((x) => t >= x.start && t < x.end)
    if (sp && sp.id !== selId) setSelId(sp.id)
  }

  const seek = (t: number) => {
    setTime(t)
    if (videoRef.current && usingFinal) videoRef.current.currentTime = t
  }

  const select = (id: string) => {
    setSelId(id)
    if (segPreview && segPreview.id !== id) setSegPreview(null)
  }

  const togglePlay = () => {
    const v = videoRef.current
    if (!v) return
    if (v.paused) v.play().catch(() => {})
    else v.pause()
  }

  const previewSeg = async () => {
    if (!seg) return
    setPreviewing(true)
    try {
      const j = await apiPost<{ video: string; stamp: number }>('/api/preview', { id: seg.id })
      setSegPreview({ id: seg.id, url: fileUrl(j.video, j.stamp) || '' })
    } catch (e) {
      window.alert(e instanceof Error ? e.message : String(e))
    }
    setPreviewing(false)
  }

  const move = (id: string, beforeId: string | null) =>
    patch((r) => {
      const from = r.segments.findIndex((s) => s.id === id)
      const [s] = r.segments.splice(from, 1)
      const to = beforeId ? r.segments.findIndex((x) => x.id === beforeId) : r.segments.length
      r.segments.splice(to, 0, s)
    })

  const shift = (d: number) =>
    patch((r) => {
      const i = r.segments.findIndex((s) => s.id === selId)
      const j = i + d
      if (i < 0 || j < 0 || j >= r.segments.length) return
      ;[r.segments[i], r.segments[j]] = [r.segments[j], r.segments[i]]
    })

  const addSeg = () => {
    const id = `seg${Date.now() % 100000}`
    patch((r) => {
      const i = r.segments.findIndex((s) => s.id === selId)
      const s: Segment = { id, text: '', clips: [] }
      r.segments.splice(i < 0 ? r.segments.length : i + 1, 0, s)
    })
    setSelId(id)
    setRightTab(0)
  }

  const duplicate = () =>
    patch((r) => {
      const i = r.segments.findIndex((s) => s.id === selId)
      if (i < 0) return
      const copy: Segment = JSON.parse(JSON.stringify(r.segments[i]))
      copy.id = `${copy.id}_copy${Date.now() % 10000}`
      r.segments.splice(i + 1, 0, copy)
    })

  const remove = () => {
    if (!seg || !window.confirm(`删除「${seg.label || seg.id}」？（可以在历史版本里找回）`)) return
    patch((r) => {
      r.segments = r.segments.filter((s) => s.id !== selId)
    })
  }

  const setField = (k: keyof Segment, v: unknown) =>
    patch((r) => {
      const s = r.segments.find((x) => x.id === selId)
      if (s) (s as Record<string, unknown>)[k] = v
    })

  const panel = { bgcolor: 'background.paper', border: '1px solid', borderColor: 'divider', borderRadius: 2, overflow: 'hidden', minHeight: 0 }

  return (
    <Box
      sx={{
        display: 'grid',
        gridTemplateColumns: { xs: '1fr', lg: '320px minmax(0,1fr) 380px' },
        gridTemplateRows: { lg: 'minmax(0,1fr) 230px' },
        gap: 1,
        height: { lg: 'calc(100vh - 48px - 16px)' },
        p: 1,
      }}
    >
      {/* materials */}
      <Box sx={{ ...panel, display: 'flex', flexDirection: 'column' }}>
        <Tabs value={leftTab} onChange={(_, v) => setLeftTab(v)} variant="fullWidth" sx={{ m: 1 }}>
          <Tab label="素材" />
          <Tab label="录制" />
        </Tabs>
        <Box sx={{ p: 1.5, overflowY: 'auto', flexGrow: 1 }}>
          {leftTab === 0 && seg && <PickerPanel seg={seg} segId={seg.id} onAdded={reload} />}
          {leftTab === 0 && !seg && <Typography color="text.secondary">先在时间线上选一段</Typography>}
          {leftTab === 1 && (
            <Stack spacing={1.5}>
              <Typography variant="body2" color="text.secondary">
                对着提词器录这一段：实时美颜、换背景，录完自动当这一段的画面和旁白，还可以剪掉停顿。
              </Typography>
              <Button
                variant="contained"
                startIcon={<VideocamIcon />}
                onClick={() => {
                  try {
                    sessionStorage.setItem('vf.studio.seg', selId || '')
                  } catch {
                    // ignore
                  }
                  onOpen('studio')
                }}
              >
                去录制棚录「{seg?.label || seg?.id || ''}」
              </Button>
            </Stack>
          )}
        </Box>
      </Box>

      {/* player */}
      <Box sx={{ ...panel, display: 'flex', flexDirection: 'column', bgcolor: '#000' }}>
        <Box sx={{ flexGrow: 1, minHeight: 240, display: 'flex', alignItems: 'center', justifyContent: 'center', position: 'relative' }}>
          {playerSrc ? (
            <Box
              component="video"
              ref={videoRef}
              key={playerSrc}
              src={playerSrc}
              onTimeUpdate={(e) => onTime((e.target as HTMLVideoElement).currentTime)}
              onPlay={() => setPlaying(true)}
              onPause={() => setPlaying(false)}
              onLoadedMetadata={() => {
                if (usingFinal && videoRef.current) videoRef.current.currentTime = time
              }}
              onClick={togglePlay}
              sx={{ maxWidth: '100%', maxHeight: '100%', width: '100%', height: '100%', objectFit: 'contain', cursor: 'pointer' }}
            />
          ) : (
            <Stack alignItems="center" spacing={1.5} sx={{ color: 'rgba(255,255,255,.7)', p: 3, textAlign: 'center' }}>
              <MovieIcon sx={{ fontSize: 48, opacity: 0.4 }} />
              <Typography>还没有渲染过整片。可以先预览单独一段，或者去渲染。</Typography>
              <Stack direction="row" spacing={1}>
                <Button variant="outlined" onClick={previewSeg} disabled={!seg || previewing || !seg.clips.length}>
                  {previewing ? '生成中…' : '预览这一段'}
                </Button>
                <Button variant="contained" onClick={() => onOpen('render')}>
                  去渲染整片
                </Button>
              </Stack>
            </Stack>
          )}
          {seg && playerSrc && !usingFinal && (
            <Typography sx={{ position: 'absolute', top: 8, left: 10, fontSize: 12, color: '#fff', bgcolor: 'rgba(0,0,0,.55)', px: 1, borderRadius: 1 }}>
              单段预览 · {seg.label || seg.id}
            </Typography>
          )}
        </Box>
        <Stack direction="row" alignItems="center" spacing={1} sx={{ px: 1.5, py: 0.75, bgcolor: 'background.paper', borderTop: '1px solid', borderColor: 'divider' }}>
          <IconButton size="small" onClick={togglePlay} disabled={!playerSrc}>
            {playing ? <PauseIcon /> : <PlayArrowIcon />}
          </IconButton>
          <Typography variant="caption" sx={{ fontVariantNumeric: 'tabular-nums', minWidth: 100 }}>
            {fmt(time)} / {fmt(total)}
          </Typography>
          <Box sx={{ flexGrow: 1 }} />
          {final && segPreview && segPreview.id === selId && (
            <Button size="small" onClick={() => setSegPreview(null)}>
              回到整片
            </Button>
          )}
          <Button size="small" onClick={previewSeg} disabled={!seg || previewing || !seg?.clips.length}>
            {previewing ? '生成中…' : '预览这一段'}
          </Button>
        </Stack>
      </Box>

      {/* inspector */}
      <Box sx={{ ...panel, display: 'flex', flexDirection: 'column', gridRow: { lg: 'span 1' } }}>
        <Tabs value={rightTab} onChange={(_, v) => setRightTab(v)} variant="fullWidth" sx={{ m: 1 }}>
          <Tab label="段落" />
          <Tab label="画面" />
          <Tab label="全局" />
        </Tabs>
        <Box sx={{ p: 1.5, overflowY: 'auto', flexGrow: 1 }}>
          {!seg && rightTab < 2 && <Typography color="text.secondary">先在时间线上选一段</Typography>}
          {seg && rightTab === 0 && (
            <Stack spacing={1.5}>
              <TextField size="small" label="章节名" value={seg.label || ''} onChange={(e) => setField('label', e.target.value || null)} />
              <TextField
                size="small"
                label={`旁白（${(seg.text || '').length} 字）`}
                multiline
                minRows={6}
                maxRows={16}
                value={seg.text || ''}
                onChange={(e) => setField('text', e.target.value)}
                helperText={seg.narration ? '这一段用的是你自己的录音：改了文字只影响字幕，要重录才会改声音。' : '改了文字，下次渲染会重新配音。'}
              />
              <TextField size="small" type="number" label="说完停顿（秒）" value={seg.pause_after ?? 0.5} onChange={(e) => setField('pause_after', Math.max(0, parseFloat(e.target.value) || 0))} inputProps={{ step: 0.1 }} />
              <Divider />
              <Typography variant="caption" color="text.secondary">
                {seg.narration ? `🎙 旁白：${seg.narration.split('/').pop()}` : '🔊 旁白：AI 配音'} · 画面 {seg.clips.length} 个 · 画中画 {(seg.overlays || []).length} 个
              </Typography>
            </Stack>
          )}
          {seg && rightTab === 1 && <ClipStrip seg={seg} segId={seg.id} />}
          {rightTab === 2 && (
            <Stack spacing={1.5}>
              <ThemePicker />
              <RenderSettingsCard />
            </Stack>
          )}
        </Box>
      </Box>

      {/* timeline */}
      <Box sx={{ ...panel, gridColumn: { lg: '1 / -1' }, display: 'flex', flexDirection: 'column' }}>
        <Stack direction="row" alignItems="center" spacing={0.5} sx={{ px: 1, py: 0.5, borderBottom: '1px solid', borderColor: 'divider' }}>
          <Tooltip title="在后面加一段">
            <IconButton size="small" onClick={addSeg}>
              <AddIcon fontSize="small" />
            </IconButton>
          </Tooltip>
          <Tooltip title="复制这一段">
            <span>
              <IconButton size="small" onClick={duplicate} disabled={!seg}>
                <ContentCopyIcon fontSize="small" />
              </IconButton>
            </span>
          </Tooltip>
          <Tooltip title="删除这一段">
            <span>
              <IconButton size="small" onClick={remove} disabled={!seg}>
                <DeleteOutlineIcon fontSize="small" />
              </IconButton>
            </span>
          </Tooltip>
          <Divider orientation="vertical" flexItem sx={{ mx: 0.5 }} />
          <Tooltip title="往前挪">
            <span>
              <IconButton size="small" onClick={() => shift(-1)} disabled={segIndex <= 0}>
                <ChevronLeftIcon fontSize="small" />
              </IconButton>
            </span>
          </Tooltip>
          <Tooltip title="往后挪">
            <span>
              <IconButton size="small" onClick={() => shift(1)} disabled={segIndex < 0 || segIndex >= raw.segments.length - 1}>
                <ChevronRightIcon fontSize="small" />
              </IconButton>
            </span>
          </Tooltip>
          <Typography variant="caption" color="text.secondary" sx={{ ml: 1 }}>
            {raw.segments.length} 段 · 约 {fmt(total)} · 拖动画面块可以调整顺序
            {view?.outputs?.final ? '' : ' · 时长是估算，渲染后按真实长度显示'}
          </Typography>
          <Box sx={{ flexGrow: 1 }} />
          <ZoomInIcon fontSize="small" sx={{ color: 'text.secondary' }} />
          <Slider size="small" min={3} max={80} value={zoom} onChange={(_, v) => setZoom(v as number)} sx={{ width: 140, mx: 1 }} />
        </Stack>
        <Box sx={{ flexGrow: 1, minHeight: 0 }}>
          <Paper elevation={0} sx={{ height: '100%', bgcolor: 'transparent' }}>
            <Timeline raw={raw} view={view} selId={selId} time={time} zoom={zoom} onSelect={select} onSeek={seek} onMove={move} />
          </Paper>
        </Box>
      </Box>
    </Box>
  )
}
