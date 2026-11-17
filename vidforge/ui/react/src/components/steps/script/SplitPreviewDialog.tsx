import { useEffect, useState } from 'react'
import {
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  Stack,
  TextField,
  Typography,
} from '@mui/material'
import { useProject } from '../../../state/ProjectContext'
import type { SplitSegment, Segment } from '../../../api/types'
import CallSplitIcon from '@mui/icons-material/CallSplit'
import { DialogHeader } from '../../shared/ui'

// estimate spoken duration: CJK text ~3.8 chars/sec, Latin text ~2.6 words/sec (tts/silent.py uses the same).
function estSeconds(text: string) {
  const cjk = (text.match(/[一-鿿]/g) || []).length
  return cjk > text.length * 0.3 ? cjk / 3.8 : text.split(/\s+/).length / 2.6
}

function fmtSeconds(s: number) {
  return s >= 60 ? `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, '0')}` : `${s.toFixed(1)} s`
}

export function SplitPreviewDialog({
  open,
  pieces,
  onClose,
}: {
  open: boolean
  pieces: SplitSegment[]
  onClose: () => void
}) {
  const { raw, patch } = useProject()
  // local editable copy, reset to the freshly-split pieces each time the dialog opens
  const [rows, setRows] = useState<SplitSegment[]>(pieces)
  useEffect(() => {
    if (open) setRows(pieces)
  }, [open, pieces])

  const setRow = (i: number, key: 'label' | 'text', value: string) => {
    setRows((r) => r.map((row, idx) => (idx === i ? { ...row, [key]: value } : row)))
  }

  const total = rows.reduce((a, p) => a + estSeconds(p.text), 0)
  const existingCount = raw?.segments.length || 0

  const accept = () => {
    if (existingCount > 0) {
      const hasWork = (raw?.segments || []).some((s) => s.clips.length || s.overlays?.length || s.voice)
      const msg = hasWork
        ? `现有 ${existingCount} 段里已经有配好的画面/声音了，替换成新拆的 ${rows.length} 段会全部丢掉。确定替换吗？`
        : `确定用这 ${rows.length} 段替换现有的 ${existingCount} 段吗？`
      if (!window.confirm(msg)) return
    }
    const cleaned = rows.filter((p) => p.text.trim())
    patch((r) => {
      // A Chinese script pasted into a project that is still English: it is a Chinese video.
      // Left alone, an American voice reads it and the subtitles are set in a Latin typeface.
      const chinese = cleaned.filter((p) => /[\u4e00-\u9fff]/.test(p.text)).length > cleaned.length / 2
      if (chinese && !(r.language || 'en').startsWith('zh')) {
        const zh = (r.variants?.zh || {}) as { voice?: string; rate?: string; subtitles?: Record<string, unknown> }
        r.language = 'zh'
        if (!r.voice || r.voice.startsWith('en-')) {
          r.voice = zh.voice || 'zh-CN-YunxiNeural'
          if (zh.rate) r.rate = zh.rate
        }
        if (zh.subtitles) r.subtitles = { ...r.subtitles, ...zh.subtitles }
        // both described translations of the English original, which no longer exists
        if (r.variants) {
          delete r.variants.zh
          if (r.variants['en-zh']?.text_from === 'en') delete r.variants['en-zh']
        }
      }
      r.segments = cleaned.map((pc, i): Segment => {
        const s: Segment = { id: `seg${i + 1}`, text: pc.text.trim(), clips: [] }
        if (pc.label) s.label = pc.label.trim()
        if (pc.visual_hint) s.visual_hint = pc.visual_hint
        return s
      })
    })
    onClose()
  }

  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth>
      <DialogHeader icon={<CallSplitIcon />} tone="indigo" title={<>拆分预览：{rows.length} 段 · 预计 {fmtSeconds(total)}</>} sub="看一眼每段的长度，再决定用不用" onClose={onClose} />
      <DialogContent dividers>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
          识别到的章节名在第一列；每段字数/预计时长在右侧。可以在这里直接改，或取消后调整原文再拆。
        </Typography>
        <Stack spacing={1}>
          {rows.map((p, i) => (
            <Stack key={i} direction="row" spacing={1} alignItems="flex-start">
              <TextField
                size="small"
                label="章节名"
                value={p.label || ''}
                onChange={(e) => setRow(i, 'label', e.target.value)}
                sx={{ width: 160, flexShrink: 0 }}
              />
              <TextField
                size="small"
                value={p.text}
                onChange={(e) => setRow(i, 'text', e.target.value)}
                multiline
                minRows={2}
                fullWidth
              />
              <Typography variant="caption" color="text.secondary" sx={{ width: 90, flexShrink: 0, pt: 1 }}>
                {p.text.split(/\s+/).length} 词
                <br />
                {fmtSeconds(estSeconds(p.text))}
                {p.visual_hint ? (
                  <>
                    <br />
                    <span title={p.visual_hint}>🖼 画面提示</span>
                  </>
                ) : null}
              </Typography>
            </Stack>
          ))}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>取消</Button>
        <Button variant="contained" onClick={accept}>
          采用这 {rows.length} 段{existingCount ? `（替换现有 ${existingCount} 段）` : ''}
        </Button>
      </DialogActions>
    </Dialog>
  )
}
