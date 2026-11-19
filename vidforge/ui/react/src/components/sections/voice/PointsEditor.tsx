import { useState } from 'react'
import { Alert, Box, Button, Chip, Stack, TextField, Typography } from '@mui/material'
import { apiPost } from '../../../api/client'
import { useProject } from '../../../state/ProjectContext'
import { sentencePoints } from '../../../fx/PointsPrompter'

/** The points of one segment: condensed by the local model, written by hand, or its sentences. */
export function PointsEditor({ segId }: { segId: string }) {
  const { raw, patch } = useProject()
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState<string | null>(null)
  const seg = raw?.segments.find((s) => s.id === segId)
  if (!seg) return null
  const own = seg.points && seg.points.length > 0
  const points = own ? seg.points! : sentencePoints(seg.text || '')

  const save = (list: string[]) =>
    patch((r) => {
      const s = r.segments.find((x) => x.id === segId)
      if (s) s.points = list.length ? list : undefined
    })

  const condense = async () => {
    setBusy(true)
    setNote(null)
    try {
      const j = await apiPost<{ points: string[]; by: string }>('/api/narration/points', { segment: segId })
      save(j.points)
      setNote(j.by === 'llm' ? '本地模型提炼的要点，数字都来自脚本。不顺手就点「改」。' : '本地模型没在运行，先用脚本的句子当要点（装 Ollama 后能提炼得更短）。')
    } catch (e) {
      setNote(e instanceof Error ? e.message : String(e))
    }
    setBusy(false)
  }

  return (
    <Box sx={{ border: '1px solid', borderColor: 'divider', borderRadius: 2, p: 1.25 }}>
      <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
        <Typography variant="body2" fontWeight={700}>
          要点（{segId}）
        </Typography>
        <Chip size="small" variant="outlined" label={own ? '自己定的' : '脚本的句子'} />
        <Box sx={{ flex: 1 }} />
        <Button size="small" onClick={condense} disabled={busy}>
          {busy ? '提炼中…' : 'AI 提炼要点'}
        </Button>
        <Button
          size="small"
          onClick={() => {
            setDraft(points.join('\n'))
            setEditing(!editing)
          }}
        >
          {editing ? '收起' : '改'}
        </Button>
        {own && (
          <Button size="small" color="inherit" onClick={() => save([])}>
            用回脚本句子
          </Button>
        )}
      </Stack>
      {editing ? (
        <TextField
          size="small"
          fullWidth
          multiline
          minRows={3}
          sx={{ mt: 1 }}
          label="一行一条"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={() => save(draft.split('\n').map((x) => x.trim()).filter(Boolean))}
        />
      ) : (
        <Box component="ol" sx={{ m: 0, mt: 0.75, pl: 2.5 }}>
          {points.map((p, i) => (
            <Typography key={i} component="li" variant="body2">
              {p}
            </Typography>
          ))}
        </Box>
      )}
      {note && (
        <Alert severity="info" sx={{ mt: 1 }}>
          {note}
        </Alert>
      )}
    </Box>
  )
}
