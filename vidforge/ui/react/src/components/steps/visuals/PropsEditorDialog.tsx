import { useState } from 'react'
import { Button, Dialog, DialogActions, DialogContent, DialogTitle, IconButton, TextField, Typography } from '@mui/material'
import CloseIcon from '@mui/icons-material/Close'
import type { Clip } from '../../../api/types'

// Remotion clip props vary entirely by composition (TitleCard: title/subtitle, Timeline:
// title/events[], BarChart: title/items[]/source) — a JSON editor is the right fit here, same
// as the old frontend's openProps(), rather than three bespoke structured forms.
export function PropsEditorDialog({ clip, onClose, onSave }: { clip: Clip; onClose: () => void; onSave: (props: Record<string, unknown>) => void }) {
  const [text, setText] = useState(JSON.stringify(clip.remotion?.props || {}, null, 2))
  const [error, setError] = useState<string | null>(null)

  const save = () => {
    try {
      onSave(JSON.parse(text))
    } catch (e) {
      setError('JSON 有误：' + (e instanceof Error ? e.message : String(e)))
    }
  }

  return (
    <Dialog open onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        {clip.remotion?.composition} 的内容
        <IconButton size="small" onClick={onClose}>
          <CloseIcon fontSize="small" />
        </IconButton>
      </DialogTitle>
      <DialogContent dividers>
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1 }}>
          JSON。文字可以写成 {'{'}"en": "...", "zh": "..."{'}'} 供多语言使用。
        </Typography>
        <TextField
          value={text}
          onChange={(e) => setText(e.target.value)}
          multiline
          minRows={14}
          fullWidth
          slotProps={{ htmlInput: { style: { fontFamily: 'ui-monospace,Consolas,monospace', fontSize: 12 } } }}
        />
        {error && <Typography color="error">{error}</Typography>}
      </DialogContent>
      <DialogActions>
        <Button variant="contained" onClick={save}>
          保存
        </Button>
      </DialogActions>
    </Dialog>
  )
}
