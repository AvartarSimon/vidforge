import { useEffect, useState } from 'react'
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Card,
  CardContent,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from '@mui/material'
import ExpandMoreIcon from '@mui/icons-material/ExpandMore'
import { apiGet } from '../../../api/client'
import { useProject } from '../../../state/ProjectContext'
import SettingsIcon from '@mui/icons-material/Settings'
import TuneIcon from '@mui/icons-material/Tune'
import { PanelTitle, IconTile } from '../../shared/ui'

const RESOLUTIONS = [
  { value: '1920x1080', label: '1080p 横屏（YouTube）' },
  { value: '3840x2160', label: '4K 横屏（渲染 ×4）' },
  { value: '1080x1920', label: '竖屏 1080×1920（Shorts / 抖音）' },
  { value: '1280x720', label: '720p（快速）' },
]

export function RenderSettingsCard() {
  const { raw, patch } = useProject()
  const [encoders, setEncoders] = useState<string[]>(['libx264'])

  useEffect(() => {
    apiGet<{ encoders: string[] }>('/api/health')
      .then((h) => setEncoders(h.encoders))
      .catch(() => {})
  }, [])

  if (!raw) return null
  const quality = raw.quality || 'final'
  const [w, h] = [raw.width || 1920, raw.height || 1080]

  return (
    <Card variant="outlined">
      <CardContent>
        <PanelTitle icon={<TuneIcon />} tone="teal" title="渲染设置" sub="质量、转场、调色、音效、进度条" />
        <Stack direction="row" spacing={2} flexWrap="wrap" useFlexGap>
          <TextField
            select
            size="small"
            label="质量"
            value={quality}
            onChange={(e) => patch((r) => (r.quality = e.target.value as 'draft' | 'final'))}
            sx={{ minWidth: 220 }}
          >
            <MenuItem value="draft">草稿（快 3 倍，看效果）</MenuItem>
            <MenuItem value="final">成片（CRF 18，2× 超采样）</MenuItem>
          </TextField>
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
            <TextField
              size="small"
              type="number"
              label="段内片段转场（秒，0 = 硬切）"
              value={raw.transition ?? 0}
              onChange={(e) => patch((r) => (r.transition = parseFloat(e.target.value) || 0))}
              sx={{ width: 210 }}
            />
            <TextField
              size="small"
              select
              label="转场方式"
              value={raw.transition_style ?? 'fade'}
              onChange={(e) => patch((r) => (r.transition_style = e.target.value))}
              sx={{ width: 170 }}
            >
              {[
                ['fade', '淡入淡出'],
                ['dissolve', '溶解'],
                ['fadeblack', '黑场过渡'],
                ['fadewhite', '白场过渡'],
                ['slideleft', '左滑'],
                ['slideright', '右滑'],
                ['wipeleft', '擦除'],
                ['circleopen', '圆形打开'],
              ].map(([v, label]) => (
                <MenuItem key={v} value={v}>
                  {label}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              size="small"
              type="number"
              label="段与段之间黑场（秒）"
              value={raw.segment_fade ?? 0}
              onChange={(e) => patch((r) => (r.segment_fade = parseFloat(e.target.value) || 0))}
              sx={{ width: 190 }}
              helperText="不改变时长，字幕不会错位"
            />
          </Stack>
          <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
            <TextField
              size="small"
              select
              label="统一调色"
              value={raw.look ?? 'none'}
              onChange={(e) => patch((r) => (r.look = e.target.value))}
              sx={{ width: 170 }}
            >
              {[
                ['none', '不调色'],
                ['film', '胶片（低饱和高反差）'],
                ['warm', '暖调'],
                ['cool', '冷调'],
                ['mono', '黑白'],
              ].map(([v, label]) => (
                <MenuItem key={v} value={v}>
                  {label}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              size="small"
              type="number"
              label="调色强度"
              value={raw.look_strength ?? 1}
              onChange={(e) => patch((r) => (r.look_strength = parseFloat(e.target.value) || 1))}
              sx={{ width: 130 }}
              slotProps={{ htmlInput: { step: 0.1, min: 0, max: 2 } }}
            />
            <Typography variant="caption" color="text.secondary" sx={{ maxWidth: 420 }}>
              一键配图会从 Commons、Openverse、Internet Archive 各取一些，色调差别很大；
              统一调色让它们看起来像同一条片子。
            </Typography>
          </Stack>
          <TextField
            select
            size="small"
            label="章节标题卡"
            value={raw.auto_title_cards ? 'true' : 'false'}
            onChange={(e) => patch((r) => (r.auto_title_cards = e.target.value === 'true'))}
            sx={{ minWidth: 260 }}
          >
            <MenuItem value="false">不加</MenuItem>
            <MenuItem value="true">有章节名的段前加 3 秒标题卡（需 Remotion）</MenuItem>
          </TextField>
          <TextField
            select
            size="small"
            label="进度条"
            value={raw.progress_bar ? 'true' : 'false'}
            onChange={(e) => patch((r) => (r.progress_bar = e.target.value === 'true'))}
            sx={{ minWidth: 200 }}
            helperText="横屏在底边，竖屏在顶边"
          >
            <MenuItem value="false">不加</MenuItem>
            <MenuItem value="true">加一条细进度条</MenuItem>
          </TextField>
          <TextField
            select
            size="small"
            label="转场音效"
            value={raw.transition_sfx ?? 'none'}
            onChange={(e) => patch((r) => (r.transition_sfx = e.target.value))}
            sx={{ minWidth: 200 }}
            helperText="段与段之间，压在旁白下面"
          >
            <MenuItem value="none">不加</MenuItem>
            <MenuItem value="whoosh">嗖（轻）</MenuItem>
            <MenuItem value="tick">嗒（短）</MenuItem>
          </TextField>
          <TextField
            select
            size="small"
            label="口播镜头推近"
            value={raw.punch_in ? 'true' : 'false'}
            onChange={(e) => patch((r) => (r.punch_in = e.target.value === 'true'))}
            sx={{ minWidth: 260 }}
            helperText="只对录制棚和「我的镜头」里的真人镜头"
          >
            <MenuItem value="false">不推近</MenuItem>
            <MenuItem value="true">每句话在全景和近景之间切换</MenuItem>
          </TextField>
          <TextField
            select
            size="small"
            label="旁白响度归一"
            value={raw.normalize_audio === false ? 'false' : 'true'}
            onChange={(e) => patch((r) => (r.normalize_audio = e.target.value === 'true'))}
            sx={{ minWidth: 220 }}
          >
            <MenuItem value="true">开（-16 LUFS，推荐）</MenuItem>
            <MenuItem value="false">关</MenuItem>
          </TextField>
        </Stack>

        <Accordion sx={{ mt: 2 }} elevation={0} variant="outlined">
          <AccordionSummary expandIcon={<ExpandMoreIcon />}>
            <Stack direction="row" spacing={1} alignItems="center">
              <IconTile icon={<SettingsIcon />} tone="slate" size={24} />
              <Typography variant="body2">高级参数（编码器 / 并行 / 超采样 / 运镜幅度 / 分辨率）</Typography>
            </Stack>
          </AccordionSummary>
          <AccordionDetails>
            <Stack direction="row" spacing={2} flexWrap="wrap" useFlexGap>
              <TextField
                select
                size="small"
                label="视频编码器"
                value={raw.encoder || 'auto'}
                onChange={(e) => patch((r) => (r.encoder = e.target.value))}
                sx={{ minWidth: 200 }}
              >
                <MenuItem value="auto">auto（有显卡硬编就用）</MenuItem>
                {encoders.map((e) => (
                  <MenuItem key={e} value={e}>
                    {e}
                  </MenuItem>
                ))}
              </TextField>
              <TextField
                size="small"
                type="number"
                label="并行渲染段数（0 = 核数/2）"
                value={raw.parallel ?? 0}
                onChange={(e) => patch((r) => (r.parallel = parseInt(e.target.value, 10) || 0))}
                sx={{ width: 220 }}
              />
              <TextField
                size="small"
                type="number"
                label="运镜超采样（空 = 按质量）"
                value={raw.supersample ?? ''}
                onChange={(e) => {
                  const v = parseInt(e.target.value, 10)
                  patch((r) => {
                    if (v >= 1) r.supersample = v
                    else delete r.supersample
                  })
                }}
                sx={{ width: 220 }}
              />
              <TextField
                size="small"
                type="number"
                label="运镜幅度"
                value={raw.motion_amount ?? 0.15}
                slotProps={{ htmlInput: { step: 0.01, min: 0, max: 0.5 } }}
                onChange={(e) => patch((r) => (r.motion_amount = parseFloat(e.target.value) || 0.15))}
                sx={{ width: 160 }}
              />
              <TextField
                select
                size="small"
                label="画幅"
                value={`${w}x${h}`}
                onChange={(e) => {
                  const [nw, nh] = e.target.value.split('x').map(Number)
                  patch((r) => {
                    r.width = nw
                    r.height = nh
                  })
                }}
                sx={{ minWidth: 220 }}
              >
                {RESOLUTIONS.map((r) => (
                  <MenuItem key={r.value} value={r.value}>
                    {r.label}
                  </MenuItem>
                ))}
              </TextField>
              <TextField
                select
                size="small"
                label="帧率"
                value={raw.fps || 30}
                onChange={(e) => patch((r) => (r.fps = parseInt(e.target.value, 10)))}
                sx={{ width: 120 }}
              >
                {[24, 25, 30, 60].map((f) => (
                  <MenuItem key={f} value={f}>
                    {f}
                  </MenuItem>
                ))}
              </TextField>
            </Stack>
          </AccordionDetails>
        </Accordion>
      </CardContent>
    </Card>
  )
}
