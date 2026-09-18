import { Accordion, AccordionDetails, AccordionSummary, Checkbox, FormControlLabel, MenuItem, Stack, TextField, Typography } from '@mui/material'
import ExpandMoreIcon from '@mui/icons-material/ExpandMore'
import type { RawProject } from '../../../api/types'
import { useProject } from '../../../state/ProjectContext'

const POSITIONS = ['bottom-right', 'bottom-left', 'top-right', 'top-left', 'right', 'left']
const HAIR_STYLES = [
  { value: 'side', label: '侧分' },
  { value: 'short', label: '短发' },
  { value: 'long', label: '长发' },
  { value: 'bald', label: '光头' },
]

export function PresenterCard() {
  const { raw, patch } = useProject()
  if (!raw) return null
  const p = raw.presenter || {}
  const style = p.style || {}
  const open = !!p.provider && p.provider !== 'none' && p.where !== 'none'

  const setP = (fn: (pp: NonNullable<RawProject['presenter']>) => void) =>
    patch((r) => {
      r.presenter = r.presenter || {}
      fn(r.presenter)
    })
  const setStyle = (fn: (s: NonNullable<NonNullable<RawProject['presenter']>['style']>) => void) =>
    setP((pp) => {
      pp.style = pp.style || {}
      fn(pp.style)
    })

  return (
    <Accordion defaultExpanded={open}>
      <AccordionSummary expandIcon={<ExpandMoreIcon />}>
        <Typography variant="subtitle1">数字主持人（画中画里"你"的形象）</Typography>
      </AccordionSummary>
      <AccordionDetails>
        <Stack direction="row" spacing={2} flexWrap="wrap" useFlexGap alignItems="flex-start">
          <TextField
            select
            size="small"
            label="类型"
            value={p.provider || 'host'}
            onChange={(e) => setP((pp) => (pp.provider = e.target.value as typeof pp.provider))}
            sx={{ minWidth: 300 }}
            helperText="插画主持人口型由配音音量驱动；逼真分身会自动勾选合成内容披露"
          >
            <MenuItem value="host">风格化插画主持人（本地生成，免费，无需披露）</MenuItem>
            <MenuItem value="heygen">HeyGen 逼真数字分身（需 key + 你的 avatar）</MenuItem>
            <MenuItem value="none">不用</MenuItem>
          </TextField>
          <TextField
            select
            size="small"
            label="出现在"
            value={p.where || 'none'}
            onChange={(e) => setP((pp) => (pp.where = e.target.value as typeof pp.where))}
            sx={{ minWidth: 220 }}
          >
            <MenuItem value="none">不自动加（在第 3 步按段添加）</MenuItem>
            <MenuItem value="first_last">开场段 + 收尾段</MenuItem>
            <MenuItem value="all">每一段</MenuItem>
          </TextField>
          <TextField select size="small" label="位置" value={p.position || 'bottom-right'} onChange={(e) => setP((pp) => (pp.position = e.target.value))} sx={{ minWidth: 160 }}>
            {POSITIONS.map((pos) => (
              <MenuItem key={pos} value={pos}>
                {pos}
              </MenuItem>
            ))}
          </TextField>
          <TextField
            size="small"
            type="number"
            label="大小（画面宽的 %）"
            value={Math.round((p.size || 0.28) * 100)}
            onChange={(e) => setP((pp) => (pp.size = (parseInt(e.target.value, 10) || 28) / 100))}
            sx={{ width: 180 }}
          />
          <TextField
            select
            size="small"
            label="发型"
            value={style.hairStyle || 'side'}
            onChange={(e) => setStyle((s) => (s.hairStyle = e.target.value))}
            sx={{ minWidth: 140 }}
          >
            {HAIR_STYLES.map((h) => (
              <MenuItem key={h.value} value={h.value}>
                {h.label}
              </MenuItem>
            ))}
          </TextField>
          <Stack direction="row" spacing={1} alignItems="center">
            <Typography variant="caption" color="text.secondary">
              肤色/发色/衣服/背景
            </Typography>
            <input type="color" value={style.skin || '#e8b98f'} onChange={(e) => setStyle((s) => (s.skin = e.target.value))} />
            <input type="color" value={style.hair || '#2b2118'} onChange={(e) => setStyle((s) => (s.hair = e.target.value))} />
            <input type="color" value={style.shirt || '#264653'} onChange={(e) => setStyle((s) => (s.shirt = e.target.value))} />
            <input type="color" value={style.bg || '#0f1115'} onChange={(e) => setStyle((s) => (s.bg = e.target.value))} />
          </Stack>
          <TextField
            size="small"
            label="署名（角落小字）"
            value={style.name || ''}
            onChange={(e) => setStyle((s) => (s.name = e.target.value))}
            placeholder="频道名或你的名字"
            sx={{ minWidth: 200 }}
          />
          <FormControlLabel
            control={<Checkbox checked={!!style.glasses} onChange={(e) => setStyle((s) => (s.glasses = e.target.checked))} />}
            label="眼镜"
          />
          <FormControlLabel
            control={<Checkbox checked={!!style.beard} onChange={(e) => setStyle((s) => (s.beard = e.target.checked))} />}
            label="胡须"
          />
          {p.provider === 'heygen' && (
            <TextField
              size="small"
              label="HeyGen avatar id"
              value={p.heygen_avatar_id || ''}
              onChange={(e) => setP((pp) => (pp.heygen_avatar_id = e.target.value.trim() || null))}
              sx={{ minWidth: 240 }}
            />
          )}
        </Stack>
      </AccordionDetails>
    </Accordion>
  )
}
