import { useEffect, useState } from 'react'
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  LinearProgress,
  MenuItem,
  Select,
  Slider,
  Stack,
  TextField,
  Typography,
} from '@mui/material'
import { apiGet, apiPost } from '../../api/client'
import { fileUrl } from '../../utils'

type MeItem = { name: string; tags?: string[]; talking?: boolean; duration?: number; uses?: number }
type HeadsJob = {
  state: 'idle' | 'running' | 'done'
  lines: string[]
  error: string | null
  result: { path: string; faces: number; frames: number; covered: number } | null
}

// Everything that takes a finished clip and gives a clip back lives here, so video work does not
// have to be done segment by segment inside the 5-step wizard.
export function VideoSection() {
  const [items, setItems] = useState<MeItem[]>([])
  const [folder, setFolder] = useState('')
  const [video, setVideo] = useState('')
  const [image, setImage] = useState('')
  const [scale, setScale] = useState(1.5)
  const [yOffset, setYOffset] = useState(-0.08)
  const [every, setEvery] = useState(1)
  const [at, setAt] = useState(1)
  const [detectPng, setDetectPng] = useState<string | null>(null)
  const [job, setJob] = useState<HeadsJob | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = () =>
    apiGet<{ folder: string; items: MeItem[] }>('/api/me')
      .then((j) => {
        setItems(j.items)
        setFolder(j.folder)
      })
      .catch(() => setItems([]))
  useEffect(() => {
    load()
  }, [])

  const run = async (what: 'detect' | 'cover') => {
    setError(null)
    setBusy(true)
    try {
      if (what === 'detect') {
        const j = await apiPost<{ path: string }>('/api/video/heads/detect', { video, at })
        setDetectPng(`${fileUrl(j.path)}?t=${Date.now()}`)
      } else {
        await apiPost('/api/video/heads/cover', { video, image: image || null, scale, y_offset: yOffset, every })
        let s: HeadsJob
        do {
          await new Promise((r) => setTimeout(r, 1500))
          s = await apiGet<HeadsJob>('/api/video/heads')
          setJob(s)
        } while (s.state === 'running')
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
    setBusy(false)
  }

  const videos = items.map((i) => i.name)

  return (
    <Stack spacing={2}>
      <Typography variant="h6">视频</Typography>
      <Typography variant="body2" color="text.secondary">
        对整段视频做处理的工具都放在这里，不需要先把它放进某一段。
      </Typography>

      <Card variant="outlined">
        <CardContent>
          <Typography variant="subtitle1" gutterBottom>
            🙈 用头像盖住视频里的人脸
          </Typography>
          <Typography variant="body2" color="text.secondary" gutterBottom>
            逐帧找出人脸并跟踪，把你给的图片（卡通头像、logo，建议 PNG 透明背景）贴上去，跟着人头移动和缩放；
            不给图片就用一块半透明圆形遮挡。自己出镜能明显降低被平台判定为「批量 AI 内容」的风险，又不必露脸。
          </Typography>

          <Stack spacing={1.5} sx={{ mt: 2 }}>
            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap alignItems="center">
              <Select
                size="small"
                value={videos.includes(video) ? video : ''}
                displayEmpty
                onChange={(e) => setVideo(e.target.value)}
                sx={{ minWidth: 240 }}
              >
                <MenuItem value="">从「我的镜头」里选…</MenuItem>
                {videos.map((n) => (
                  <MenuItem key={n} value={n}>
                    {n}
                  </MenuItem>
                ))}
              </Select>
              <TextField
                size="small"
                label="或直接填路径"
                value={video}
                onChange={(e) => setVideo(e.target.value)}
                sx={{ minWidth: 320 }}
                helperText={`项目内相对路径，或素材库 ${folder} 里的文件名`}
              />
            </Stack>

            <TextField
              size="small"
              label="遮挡图片（留空 = 半透明圆形）"
              value={image}
              onChange={(e) => setImage(e.target.value)}
              placeholder="assets/avatar.png"
              sx={{ maxWidth: 480 }}
            />

            <Stack direction="row" spacing={3} flexWrap="wrap" useFlexGap>
              <Box sx={{ width: 200 }}>
                <Typography variant="caption">大小 ×{scale.toFixed(2)}</Typography>
                <Slider size="small" min={0.8} max={3} step={0.05} value={scale} onChange={(_, v) => setScale(v as number)} />
              </Box>
              <Box sx={{ width: 200 }}>
                <Typography variant="caption">上下位置 {yOffset.toFixed(2)}</Typography>
                <Slider size="small" min={-0.6} max={0.3} step={0.01} value={yOffset} onChange={(_, v) => setYOffset(v as number)} />
              </Box>
              <Box sx={{ width: 200 }}>
                <Typography variant="caption">每 {every} 帧检测一次（越大越快）</Typography>
                <Slider size="small" min={1} max={5} step={1} marks value={every} onChange={(_, v) => setEvery(v as number)} />
              </Box>
            </Stack>

            <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
              <TextField
                size="small"
                type="number"
                label="预览第几秒"
                value={at}
                onChange={(e) => setAt(Number(e.target.value))}
                sx={{ width: 130 }}
              />
              <Button size="small" onClick={() => run('detect')} disabled={!video || busy}>
                先看检测结果
              </Button>
              <Button size="small" variant="contained" onClick={() => run('cover')} disabled={!video || busy}>
                生成遮挡后的视频
              </Button>
            </Stack>

            {busy && <LinearProgress />}
            {error && <Alert severity="error">{error}</Alert>}

            {detectPng && (
              <Box>
                <Typography variant="caption" color="text.secondary">
                  红框 = 会被盖住（灰框 = 置信度不够，忽略）
                </Typography>
                <Box component="img" src={detectPng} alt="" sx={{ display: 'block', maxWidth: '100%', borderRadius: 1, mt: 0.5 }} />
              </Box>
            )}

            {job?.lines?.length ? (
              <Box sx={{ bgcolor: 'action.hover', borderRadius: 1, p: 1, fontFamily: 'monospace', fontSize: 12 }}>
                {job.lines.map((l, i) => (
                  <div key={i}>{l}</div>
                ))}
              </Box>
            ) : null}
            {job?.error && <Alert severity="error">{job.error}</Alert>}
            {job?.result && (
              <Box>
                <Alert severity="success" sx={{ mb: 1 }}>
                  完成：{job.result.faces} 张脸，{job.result.covered}/{job.result.frames} 帧盖住 →{' '}
                  <code>{job.result.path}</code>（在第 3 步可以直接当素材用）
                </Alert>
                <Box component="video" src={fileUrl(job.result.path) || undefined} controls sx={{ maxWidth: '100%', borderRadius: 1 }} />
              </Box>
            )}
          </Stack>
        </CardContent>
      </Card>

      <Card variant="outlined">
        <CardContent>
          <Typography variant="subtitle1" gutterBottom>
            🎥 我的镜头（{items.length}）
          </Typography>
          <Typography variant="body2" color="text.secondary">
            文件名就是标签：<code>backyard_glasses_talking_01.mp4</code> → 标签 backyard、glasses，含 talking 即视为说话镜头。
            目录：<code>{folder}</code>
          </Typography>
          <Stack spacing={0.5} sx={{ mt: 1.5 }}>
            {items.map((i) => (
              <Stack key={i.name} direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                <Typography variant="body2" sx={{ minWidth: 260 }}>
                  {i.name}
                </Typography>
                <Chip size="small" label={i.talking ? '说话' : '沉默'} color={i.talking ? 'primary' : 'default'} />
                {(i.tags || []).map((t) => (
                  <Chip key={t} size="small" variant="outlined" label={t} />
                ))}
                <Typography variant="caption" color="text.secondary">
                  {i.duration ? `${i.duration.toFixed(1)}s` : ''} {i.uses ? `· 用过 ${i.uses} 次` : ''}
                </Typography>
                <Button size="small" onClick={() => setVideo(i.name)}>
                  用它做遮挡
                </Button>
              </Stack>
            ))}
            {!items.length && (
              <Typography variant="body2" color="text.secondary">
                还没有素材。把自己录的片段放进上面的目录即可，或在第 3 步「🎥 我的镜头」里上传。
              </Typography>
            )}
          </Stack>
        </CardContent>
      </Card>
    </Stack>
  )
}
