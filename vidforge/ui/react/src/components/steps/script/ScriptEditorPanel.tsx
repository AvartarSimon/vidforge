import { useState } from 'react'
import {
  Box,
  Button,
  Card,
  CardContent,
  IconButton,
  Stack,
  TextField,
  Typography,
} from '@mui/material'
import ArrowUpwardIcon from '@mui/icons-material/ArrowUpward'
import ArrowDownwardIcon from '@mui/icons-material/ArrowDownward'
import DeleteIcon from '@mui/icons-material/Delete'
import HistoryIcon from '@mui/icons-material/History'
import { useProject } from '../../../state/ProjectContext'
import type { Segment } from '../../../api/types'
import { SegmentHistoryDialog } from '../../shared/SegmentHistoryDialog'
import FormatListNumberedIcon from '@mui/icons-material/FormatListNumbered'
import { PanelTitle } from '../../shared/ui'

function newId(segments: Segment[]) {
  let n = segments.length + 1
  let id = `seg${n}`
  while (segments.some((s) => s.id === id)) id = `seg${++n}`
  return id
}

export function ScriptEditorPanel() {
  const { raw, patch, lang } = useProject()
  const [historyFor, setHistoryFor] = useState<string | null>(null)
  if (!raw) return null
  const segments = raw.segments || []
  // on a language variant the same fields are text_<lang> / label_<lang>; the original text stays
  // visible as the placeholder, which is what a translator works from
  const textKey = lang ? `text_${lang}` : 'text'
  const labelKey = lang ? `label_${lang}` : 'label'

  const updateSegment = (i: number, key: string, value: string) => {
    patch((r) => {
      const s = r.segments[i] as Segment
      if (key === 'id') {
        const cleaned = value.trim().replace(/[^A-Za-z0-9_\-一-鿿]+/g, '_')
        if (!cleaned) return
        s.id = cleaned
        return
      }
      if (value === '') delete s[key]
      else (s as Record<string, unknown>)[key] = value
    })
  }

  const move = (i: number, dir: -1 | 1) => {
    patch((r) => {
      const arr = r.segments
      const [item] = arr.splice(i, 1)
      arr.splice(i + dir, 0, item)
    })
  }

  const remove = (i: number) => {
    if (!window.confirm(`删除段「${segments[i].id}」？`)) return
    patch((r) => {
      r.segments.splice(i, 1)
    })
  }

  const add = () => {
    patch((r) => {
      r.segments.push({ id: newId(r.segments), text: '', clips: [] })
    })
  }

  return (
    <Card variant="outlined">
      <CardContent>
        <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
          <PanelTitle icon={<FormatListNumberedIcon />} tone="indigo" mb={0} title={<>段落（{segments.length}）</>} />
          <Button size="small" onClick={add}>
            ＋ 添加一段
          </Button>
        </Stack>
        <Stack spacing={1}>
          {segments.map((s, i) => (
            <Stack
              key={i}
              direction="row"
              spacing={1}
              alignItems="flex-start"
              sx={{ p: 1, border: '1px solid', borderColor: 'divider', borderRadius: 2 }}
            >
              <TextField
                size="small"
                label="id"
                value={s.id}
                onChange={(e) => updateSegment(i, 'id', e.target.value)}
                sx={{ width: 110, flexShrink: 0 }}
              />
              <TextField
                size="small"
                label={lang ? `章节名（${lang}）` : '章节名（可选）'}
                value={String(s[labelKey] || '')}
                placeholder={lang ? s.label || '' : undefined}
                onChange={(e) => updateSegment(i, labelKey, e.target.value)}
                sx={{ width: 160, flexShrink: 0 }}
              />
              <TextField
                size="small"
                label={lang ? `旁白（${lang}）` : '旁白'}
                value={String(s[textKey] || '')}
                placeholder={lang ? s.text || '' : undefined}
                onChange={(e) => updateSegment(i, textKey, e.target.value)}
                multiline
                minRows={2}
                fullWidth
                error={!String(s[textKey] || '').trim()}
              />
              <Stack spacing={0.5}>
                <IconButton size="small" disabled={i === 0} onClick={() => move(i, -1)}>
                  <ArrowUpwardIcon fontSize="small" />
                </IconButton>
                <IconButton size="small" disabled={i === segments.length - 1} onClick={() => move(i, 1)}>
                  <ArrowDownwardIcon fontSize="small" />
                </IconButton>
                <IconButton size="small" onClick={() => remove(i)}>
                  <DeleteIcon fontSize="small" />
                </IconButton>
                <IconButton size="small" title="历史版本" onClick={() => setHistoryFor(s.id)}>
                  <HistoryIcon fontSize="small" />
                </IconButton>
              </Stack>
            </Stack>
          ))}
          {!segments.length && (
            <Box sx={{ py: 3, textAlign: 'center' }}>
              <Typography variant="body2" color="text.secondary">
                还没有段落——用上面的 AI 生成或粘贴脚本后「拆成段落」，或点「＋ 添加一段」手动写。
              </Typography>
            </Box>
          )}
        </Stack>
      </CardContent>
      <SegmentHistoryDialog segId={historyFor} open={!!historyFor} onClose={() => setHistoryFor(null)} />
    </Card>
  )
}
