import { useEffect, useState } from 'react'
import { Alert, Box, Button, Card, CardContent, Stack, TextField, ToggleButton, ToggleButtonGroup, Typography } from '@mui/material'
import AspectRatioIcon from '@mui/icons-material/AspectRatio'
import { apiGet, apiPost } from '../../api/client'
import { useProject } from '../../state/ProjectContext'
import { PanelTitle } from './ui'

type Palette = { id: string; name: string; box: string; text: string; accent: string; badge_bg: string; badge_text: string; frame: string; page: string }
type ThemeState = { palettes: Palette[]; current: { palette: string; badge: string; side: string } | null; frames: Record<string, [number, number]>; frame: string }

export const FRAME_INFO: Record<string, { label: string; where: string }> = {
  '16:9': { label: '横屏 16:9', where: 'YouTube · B站 · 头条/西瓜' },
  '9:16': { label: '竖屏 9:16', where: '抖音 · 快手 · TikTok · Shorts · 视频号' },
  '3:4': { label: '竖图 3:4', where: '小红书' },
  '1:1': { label: '方形 1:1', where: '两种方向都显示的信息流' },
}
const NEUTRAL: Palette = { id: '', name: '不套配色', box: 'rgba(0,0,0,.6)', text: '#ffffff', accent: '#e9a23b', badge_bg: '#ffffff', badge_text: '#1f2a30', frame: '#ffffff', page: '#dfe3e8' }

/** A small picture of the frame in one palette: where the window, badge and subtitles land. */
function Mock({ p, ratio, badge, side, selected, onClick }: { p: Palette; ratio: [number, number]; badge: string; side: string; selected: boolean; onClick: () => void }) {
  const [w, h] = ratio
  const tall = h > w
  const win = (
    <Box
      sx={{
        position: 'absolute',
        top: tall ? '7.5%' : '5%',
        [side === 'left' ? 'left' : 'right']: tall ? '4.5%' : '3%',
        width: tall ? '24%' : '22%',
        aspectRatio: tall ? '3 / 4' : '4 / 3',
        borderRadius: '10%',
        border: `2px solid ${p.frame}`,
        overflow: 'hidden',
        bgcolor: '#c9b8a6',
        boxShadow: '0 2px 8px rgba(0,0,0,.25)',
      }}
    >
      <Box sx={{ position: 'absolute', inset: 0, background: 'repeating-linear-gradient(90deg,#8a5a3c 0 6px,#b98b5e 6px 9px,#5d7b8a 9px 13px,#d9b26f 13px 16px)', opacity: 0.55 }} />
      <Box sx={{ position: 'absolute', left: '30%', top: '22%', width: '40%', aspectRatio: '1', borderRadius: '50%', bgcolor: '#e9c3a5' }} />
      <Box sx={{ position: 'absolute', left: '12%', right: '12%', bottom: 0, height: '35%', borderRadius: '50% 50% 0 0', bgcolor: p.id ? p.box : '#5d7b8a' }} />
    </Box>
  )
  return (
    <Box onClick={onClick} sx={{ cursor: 'pointer', textAlign: 'center' }}>
      <Box
        sx={{
          position: 'relative',
          width: '100%',
          aspectRatio: `${w} / ${h}`,
          borderRadius: 2,
          overflow: 'hidden',
          outline: selected ? '3px solid' : '1px solid',
          outlineColor: selected ? 'primary.main' : 'divider',
          outlineOffset: 2,
          background: `linear-gradient(160deg, ${p.page} 0%, #ffffff 55%, ${p.page} 100%)`,
        }}
      >
        <Box sx={{ position: 'absolute', left: '8%', right: '8%', top: tall ? '38%' : '30%', height: '22%', borderRadius: 1, background: `linear-gradient(120deg, ${p.id ? p.box : '#9aa5b1'}55, ${p.accent}66)` }} />
        {win}
        {badge && p.id && (
          <Box sx={{ position: 'absolute', top: tall ? '8.5%' : '6%', [side === 'left' ? 'right' : 'left']: '4.5%', bgcolor: p.badge_bg, color: p.badge_text, fontSize: 7, fontWeight: 700, px: 0.6, py: 0.2, borderRadius: 99, whiteSpace: 'nowrap' }}>{badge}</Box>
        )}
        <Box sx={{ position: 'absolute', left: '12%', right: '12%', bottom: tall ? '22%' : '8%', bgcolor: p.box, borderRadius: 1, py: 0.35 }}>
          <Typography sx={{ fontSize: 9, fontWeight: 800, color: p.text, lineHeight: 1.35 }}>
            每天睡九个小时<span style={{ color: p.accent }}>为什么</span>还累
          </Typography>
        </Box>
        {/* the platform's own bottom area on a phone, which nothing of ours may sit under */}
        {tall && <Box sx={{ position: 'absolute', left: 0, right: 0, bottom: 0, height: '16%', background: 'repeating-linear-gradient(45deg, rgba(0,0,0,.06) 0 4px, transparent 4px 8px)' }} />}
      </Box>
      <Typography variant="caption" sx={{ fontWeight: selected ? 700 : 500 }}>
        {p.name}
      </Typography>
    </Box>
  )
}

/**
 * 画幅与风格: the frame (16:9 / 9:16 / 3:4 / 1:1) and one of the bright palettes, for any frame.
 * Applying writes it all into project.json (size, subtitle colours and position, the presenter
 * windows), so every part stays editable afterwards.
 */
export function ThemePicker({ onApplied, bare = false }: { onApplied?: () => void; bare?: boolean }) {
  const { reload } = useProject()
  const [data, setData] = useState<ThemeState | null>(null)
  const [frame, setFrame] = useState('16:9')
  const [palette, setPalette] = useState('')
  const [badge, setBadge] = useState('')
  const [side, setSide] = useState('left')
  const [status, setStatus] = useState('')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    apiGet<ThemeState>('/api/theme')
      .then((j) => {
        setData(j)
        setFrame(j.frames[j.frame] ? j.frame : '16:9')
        if (j.current) {
          setPalette(j.current.palette)
          setBadge(j.current.badge)
          setSide(j.current.side || 'left')
        }
      })
      .catch((e) => setError(String(e)))
  }, [])

  const apply = async () => {
    setError(null)
    try {
      await apiPost('/api/theme/apply', palette ? { frame, palette, badge, side } : { off: true, frame })
      await reload()
      setStatus(`已应用：${FRAME_INFO[frame]?.label || frame}${palette ? ` · ${data?.palettes.find((p) => p.id === palette)?.name}` : ''}。重新渲染后生效。`)
      onApplied?.()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  const ratio = (data?.frames[frame] || [1920, 1080]) as [number, number]
  const tall = ratio[1] > ratio[0]
  const options = [NEUTRAL, ...(data?.palettes || [])]

  const body = (
    <>
      {!bare && (
        <PanelTitle
          icon={<AspectRatioIcon />}
          tone="pink"
          title="画幅与风格"
          sub="先定画幅（发哪个平台），再选一套配色：字幕底框、高亮字、角标、图表和真人小窗的边框都跟着它。"
        />
      )}
      <ToggleButtonGroup exclusive value={frame} onChange={(_, v) => v && setFrame(v)} sx={{ flexWrap: 'wrap' }}>
        {Object.keys(data?.frames || FRAME_INFO).map((f) => (
          <ToggleButton key={f} value={f} sx={{ flexDirection: 'column', alignItems: 'flex-start', px: 1.5, py: 0.75 }}>
            <span>{FRAME_INFO[f]?.label || f}</span>
            <Typography component="span" variant="caption" color="text.secondary" sx={{ fontWeight: 400 }}>
              {FRAME_INFO[f]?.where}
            </Typography>
          </ToggleButton>
        ))}
      </ToggleButtonGroup>
      <Box sx={{ display: 'grid', gridTemplateColumns: `repeat(auto-fill, minmax(${tall ? 112 : 168}px, 1fr))`, gap: 1.5, my: 2 }}>
        {options.map((p) => (
          <Mock key={p.id || 'none'} p={p} ratio={ratio} badge={badge} side={side} selected={palette === p.id} onClick={() => setPalette(p.id)} />
        ))}
      </Box>
      <Stack direction="row" spacing={1.5} alignItems="center" flexWrap="wrap" useFlexGap>
        <TextField size="small" label="系列角标" value={badge} onChange={(e) => setBadge(e.target.value)} placeholder="RESTART · 001" sx={{ width: 200 }} helperText={palette ? '空着就不显示' : '选了配色才有角标'} disabled={!palette} />
        <ToggleButtonGroup size="small" exclusive value={side} onChange={(_, v) => v && setSide(v)}>
          <ToggleButton value="left">小窗在左上</ToggleButton>
          <ToggleButton value="right">小窗在右上</ToggleButton>
        </ToggleButtonGroup>
        <Button variant="contained" onClick={apply}>
          应用到这个项目
        </Button>
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
    </>
  )
  return bare ? body : (
    <Card>
      <CardContent>{body}</CardContent>
    </Card>
  )
}
