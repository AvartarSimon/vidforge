import { useEffect, useState } from 'react'
import { Alert, Box, Button, Card, CardContent, Stack, TextField, ToggleButton, ToggleButtonGroup, Typography } from '@mui/material'
import { apiGet, apiPost } from '../../api/client'
import { useProject } from '../../state/ProjectContext'

type Palette = { id: string; name: string; box: string; text: string; accent: string; badge_bg: string; badge_text: string; frame: string; page: string }
type ThemeState = { palettes: Palette[]; current: { palette: string; badge: string; side: string } | null; window: { size: number; height: number } }

/** A phone-shaped mock of the template in one palette — what the frame will look like. */
function Mock({ p, badge, side, selected, onClick }: { p: Palette; badge: string; side: string; selected: boolean; onClick: () => void }) {
  const win = (
    <Box sx={{ position: 'absolute', top: '7.5%', [side === 'left' ? 'left' : 'right']: '4.5%', width: '24%', aspectRatio: '3 / 4', borderRadius: '10%', border: `2px solid ${p.frame}`, overflow: 'hidden', bgcolor: '#c9b8a6', boxShadow: '0 2px 8px rgba(0,0,0,.25)' }}>
      {/* a person in front of a bookshelf, drawn in two shapes */}
      <Box sx={{ position: 'absolute', inset: 0, background: 'repeating-linear-gradient(90deg,#8a5a3c 0 6px,#b98b5e 6px 9px,#5d7b8a 9px 13px,#d9b26f 13px 16px)', opacity: 0.55 }} />
      <Box sx={{ position: 'absolute', left: '30%', top: '22%', width: '40%', aspectRatio: '1', borderRadius: '50%', bgcolor: '#e9c3a5' }} />
      <Box sx={{ position: 'absolute', left: '12%', right: '12%', bottom: 0, height: '35%', borderRadius: '50% 50% 0 0', bgcolor: p.box }} />
    </Box>
  )
  return (
    <Box onClick={onClick} sx={{ cursor: 'pointer', textAlign: 'center' }}>
      <Box
        sx={{
          position: 'relative',
          width: '100%',
          aspectRatio: '9 / 16',
          borderRadius: 2,
          overflow: 'hidden',
          outline: selected ? '3px solid' : '1px solid',
          outlineColor: selected ? 'primary.main' : 'divider',
          outlineOffset: 2,
          // stands in for the segment's own pictures: bright, like the real thing should be
          background: `linear-gradient(160deg, ${p.page} 0%, #ffffff 55%, ${p.page} 100%)`,
        }}
      >
        <Box sx={{ position: 'absolute', left: '8%', right: '8%', top: '38%', height: '22%', borderRadius: 1, background: `linear-gradient(120deg, ${p.box}55, ${p.accent}66)` }} />
        {win}
        {badge && (
          <Box sx={{ position: 'absolute', top: '8.5%', [side === 'left' ? 'right' : 'left']: '4.5%', bgcolor: p.badge_bg, color: p.badge_text, fontSize: 7.5, fontWeight: 700, px: 0.6, py: 0.25, borderRadius: 99, whiteSpace: 'nowrap' }}>{badge}</Box>
        )}
        <Box sx={{ position: 'absolute', left: '9%', right: '9%', bottom: '22%', bgcolor: p.box, borderRadius: 1, py: 0.5 }}>
          <Typography sx={{ fontSize: 10, fontWeight: 800, color: p.text, lineHeight: 1.35 }}>每天睡九个小时</Typography>
          <Typography sx={{ fontSize: 10, fontWeight: 800, color: p.accent, lineHeight: 1.35 }}>为什么还是这么累？</Typography>
        </Box>
        {/* the platform's own bottom area, which nothing of ours may sit under */}
        <Box sx={{ position: 'absolute', left: 0, right: 0, bottom: 0, height: '16%', background: 'repeating-linear-gradient(45deg, rgba(0,0,0,.06) 0 4px, transparent 4px 8px)' }} />
      </Box>
      <Typography variant="caption" sx={{ fontWeight: selected ? 700 : 500 }}>
        {p.name}
      </Typography>
    </Box>
  )
}

/**
 * 竖屏主题模板: pick a palette, name the series, choose the window side, apply. Applying writes it
 * all into project.json (1080x1920, subtitle box and position, the presenter windows), so every
 * part stays editable afterwards.
 */
export function ThemePicker() {
  const { reload } = useProject()
  const [data, setData] = useState<ThemeState | null>(null)
  const [palette, setPalette] = useState('sunny')
  const [badge, setBadge] = useState('RESTART · 001')
  const [side, setSide] = useState('left')
  const [status, setStatus] = useState('')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    apiGet<ThemeState>('/api/theme')
      .then((j) => {
        setData(j)
        if (j.current) {
          setPalette(j.current.palette)
          setBadge(j.current.badge)
          setSide(j.current.side || 'left')
        }
      })
      .catch((e) => setError(String(e)))
  }, [])

  const apply = async (off = false) => {
    setError(null)
    try {
      await apiPost('/api/theme/apply', off ? { off: true } : { palette, badge, side })
      await reload()
      setStatus(off ? '已取消模板（画幅和字幕设置保留，可以在「全局」里改回）' : '已应用：1080×1920 竖屏、字幕在中下部、讲解段落的真人小窗放到位。重新渲染后生效。')
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  return (
    <Card>
      <CardContent>
        <Typography variant="subtitle1" gutterBottom>
          🎨 竖屏主题模板
        </Typography>
        <Typography variant="body2" color="text.secondary">
          主画面铺满竖屏；真人小窗占宽度 24%、3:4 圆角，放在上方；只在讲解段落出现（录制棚里选「当小窗」）；字幕在中下部，避开底部平台信息区。
        </Typography>
        <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(124px, 1fr))', gap: 1.5, my: 2 }}>
          {data?.palettes.map((p) => (
            <Mock key={p.id} p={p} badge={badge} side={side} selected={palette === p.id} onClick={() => setPalette(p.id)} />
          ))}
        </Box>
        <Stack direction="row" spacing={1.5} alignItems="center" flexWrap="wrap" useFlexGap>
          <TextField size="small" label="系列角标" value={badge} onChange={(e) => setBadge(e.target.value)} placeholder="RESTART · 001" sx={{ width: 200 }} helperText="空着就不显示" />
          <ToggleButtonGroup size="small" exclusive value={side} onChange={(_, v) => v && setSide(v)}>
            <ToggleButton value="left">小窗左上</ToggleButton>
            <ToggleButton value="right">小窗右上</ToggleButton>
          </ToggleButtonGroup>
          <Button variant="contained" onClick={() => apply()}>
            {data?.current ? '更新模板' : '应用到这个项目'}
          </Button>
          {data?.current && (
            <Button color="inherit" onClick={() => apply(true)}>
              取消模板
            </Button>
          )}
        </Stack>
        {status && (
          <Alert severity="success" sx={{ mt: 1.5 }}>
            {status}
          </Alert>
        )}
        {error && (
          <Alert severity="warning" sx={{ mt: 1.5 }}>
            {error}
          </Alert>
        )}
      </CardContent>
    </Card>
  )
}
