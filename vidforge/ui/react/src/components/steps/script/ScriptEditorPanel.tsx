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
import { useProject } from '../../../state/ProjectContext'
import type { Segment } from '../../../api/types'

function newId(segments: Segment[]) {
  let n = segments.length + 1
  let id = `seg${n}`
  while (segments.some((s) => s.id === id)) id = `seg${++n}`
  return id
}

export function ScriptEditorPanel() {
  const { raw, patch } = useProject()
  if (!raw) return null
  const segments = raw.segments || []

  const updateSegment = (i: number, key: 'id' | 'label' | 'text', value: string) => {
    patch((r) => {
      const s = r.segments[i] as Segment
      if (key === 'id') {
        const cleaned = value.trim().replace(/[^A-Za-z0-9_\-一-鿿]+/g, '_')
        if (!cleaned) return
        s.id = cleaned
        return
      }
      if (value === '') delete s[key]
      else s[key] = value
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
          <Typography variant="subtitle1" fontWeight={600}>
            段落（{segments.length}）
          </Typography>
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
                label="章节名（可选）"
                value={s.label || ''}
                onChange={(e) => updateSegment(i, 'label', e.target.value)}
                sx={{ width: 160, flexShrink: 0 }}
              />
              <TextField
                size="small"
                label="旁白"
                value={s.text || ''}
                onChange={(e) => updateSegment(i, 'text', e.target.value)}
                multiline
                minRows={2}
                fullWidth
                error={!(s.text || '').trim()}
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
    </Card>
  )
}
