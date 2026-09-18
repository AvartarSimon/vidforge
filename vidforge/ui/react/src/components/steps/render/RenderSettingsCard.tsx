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
import type { RawProject } from '../../../api/types'
import { useProject } from '../../../state/ProjectContext'

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
  const burn = !!raw.subtitles?.burn
  const subStyle = raw.subtitles?.style || 'outline'
  const [w, h] = [raw.width || 1920, raw.height || 1080]

  const setSub = (fn: (s: NonNullable<RawProject['subtitles']>) => void) =>
    patch((r) => {
      r.subtitles = r.subtitles || {}
      fn(r.subtitles)
    })

  return (
    <Card variant="outlined">
      <CardContent>
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
          <Stack spacing={0.5}>
            <TextField
              select
              size="small"
              label="字幕"
              value={burn ? 'true' : 'false'}
              onChange={(e) => setSub((s) => (s.burn = e.target.value === 'true'))}
              sx={{ minWidth: 220 }}
            >
              <MenuItem value="false">只出 .srt（上传时作字幕轨）</MenuItem>
              <MenuItem value="true">烧进画面</MenuItem>
            </TextField>
            <TextField
              select
              size="small"
              value={subStyle}
              onChange={(e) => setSub((s) => (s.style = e.target.value))}
              sx={{ minWidth: 220 }}
            >
              <MenuItem value="outline">白字黑边</MenuItem>
              <MenuItem value="box">白字 + 半透明底框</MenuItem>
            </TextField>
          </Stack>
          <TextField
            size="small"
            type="number"
            label="片段间转场（秒，0 = 硬切）"
            value={raw.transition ?? 0}
            onChange={(e) => patch((r) => (r.transition = parseFloat(e.target.value) || 0))}
            sx={{ width: 220 }}
          />
          <TextField
            size="small"
            label="背景音乐"
            value={raw.bgm?.file || ''}
            onChange={(e) => {
              const f = e.target.value.trim()
              patch((r) => {
                r.bgm = f ? { ...(r.bgm || {}), file: f, volume_db: r.bgm?.volume_db ?? -18, fade_out: r.bgm?.fade_out ?? 3 } : null
              })
            }}
            placeholder="assets/bgm.mp3（留空则无）"
            sx={{ minWidth: 220 }}
          />
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
            <Typography variant="body2">高级参数（编码器 / 并行 / 超采样 / 运镜幅度 / 分辨率）</Typography>
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
