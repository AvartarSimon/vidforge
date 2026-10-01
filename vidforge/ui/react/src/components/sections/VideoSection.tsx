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
import { useProject } from '../../state/ProjectContext'
import { fileUrl } from '../../utils'

type MeItem = { name: string; tags?: string[]; talking?: boolean; duration?: number; uses?: number }
type ShortCut = { ids: string[]; label: string; start: number; seconds: number }
type HeadsJob = {
  state: 'idle' | 'running' | 'done'
  lines: string[]
  error: string | null
  result: { path: string; faces: number; frames: number; covered: number } | null
}

// Everything that takes a finished clip and gives a clip back lives here, so video work does not
// have to be done segment by segment inside the 5-step wizard.
export function VideoSection() {
  const { raw } = useProject()
  const [items, setItems] = useState<MeItem[]>([])
  const [folder, setFolder] = useState('')
  const [video, setVideo] = useState('')
  const [image, setImage] = useState('')
  const [coverVideo, setCoverVideo] = useState('')
  const [photo, setPhoto] = useState('')
  const [segment, setSegment] = useState('')
  const [provider, setProvider] = useState<'motion' | 'cmd'>('motion')
  const [cuts, setCuts] = useState<ShortCut[]>([])
  const [cutIds, setCutIds] = useState<string[]>([])
  const [ratio, setRatio] = useState('9:16')
  const [shortMode, setShortMode] = useState<'blur' | 'crop'>('blur')
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
        await apiPost('/api/video/heads/cover', {
          video,
          image: coverVideo ? null : image || null,
          cover_video: coverVideo || null,
          scale,
          y_offset: yOffset,
          every,
        })
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

  // photo + this segment's narration -> a head that talks, ready to paste onto tracked heads
  const makeHead = async () => {
    setError(null)
    setBusy(true)
    try {
      await apiPost('/api/video/face', { image: photo, segment: segment || null, provider })
      let s: HeadsJob
      do {
        await new Promise((r) => setTimeout(r, 1500))
        s = await apiGet<HeadsJob>('/api/video/heads')
        setJob(s)
      } while (s.state === 'running')
      if (s.result?.path) setCoverVideo(s.result.path)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
    setBusy(false)
  }

  // One topic, two platforms: the long video is already rendered and its subtitles already have
  // the timings, so a vertical cut is a trim and a reframe rather than another render.
  const loadCuts = async () => {
    setError(null)
    try {
      const j = await apiGet<{ cuts: ShortCut[] }>('/api/short/suggest?seconds=55')
      setCuts(j.cuts)
      if (j.cuts.length && !cutIds.length) setCutIds(j.cuts[0].ids)
    } catch (e) {
      setCuts([])
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  const makeShort = async () => {
    setError(null)
    setBusy(true)
    try {
      await apiPost('/api/short', { segments: cutIds, ratio, mode: shortMode })
      let s2: HeadsJob
      do {
        await new Promise((r) => setTimeout(r, 1200))
        s2 = await apiGet<HeadsJob>('/api/video/heads')
        setJob(s2)
      } while (s2.state === 'running')
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
    setBusy(false)
  }

  const videos = items.map((i) => i.name)
  const segments = raw?.segments || []

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

            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
              <TextField
                size="small"
                label="遮挡图片（留空 = 半透明圆形）"
                value={image}
                onChange={(e) => setImage(e.target.value)}
                placeholder="assets/avatar.png"
                disabled={!!coverVideo}
                sx={{ minWidth: 320 }}
              />
              <TextField
                size="small"
                label="或：会说话的头（换头，优先于图片）"
                value={coverVideo}
                onChange={(e) => setCoverVideo(e.target.value)}
                placeholder="assets/heads/xxx-talking.mp4"
                sx={{ minWidth: 340 }}
                helperText="用下面「照片变成会说话的头」生成，身体动作还是你自己的"
              />
            </Stack>

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
            📱 切一条竖版（小红书 / 抖音 / Shorts）
          </Typography>
          <Typography variant="body2" color="text.secondary" gutterBottom>
            从已经渲染好的长视频里剪，不重新渲染：字幕按切点重新计时并加大、上移（手机拇指会挡住最下面一条）。
            一个段落就是一个完整的意思，所以候选直接按段落给。
          </Typography>
          <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap sx={{ mt: 1 }}>
            <Button size="small" onClick={loadCuts} disabled={busy}>
              找可切的片段
            </Button>
            <Select
              size="small"
              value={cuts.findIndex((c) => c.ids.join() === cutIds.join())}
              onChange={(e) => setCutIds(cuts[Number(e.target.value)]?.ids || [])}
              displayEmpty
              sx={{ minWidth: 300, fontSize: 13 }}
            >
              <MenuItem value={-1} sx={{ fontSize: 13 }}>
                先点「找可切的片段」
              </MenuItem>
              {cuts.map((c, i) => (
                <MenuItem key={c.ids.join()} value={i} sx={{ fontSize: 13 }}>
                  {c.seconds.toFixed(0)}s · {c.label}
                </MenuItem>
              ))}
            </Select>
            <Select size="small" value={ratio} onChange={(e) => setRatio(e.target.value)} sx={{ fontSize: 13 }}>
              <MenuItem value="9:16" sx={{ fontSize: 13 }}>9:16 竖版</MenuItem>
              <MenuItem value="4:5" sx={{ fontSize: 13 }}>4:5</MenuItem>
              <MenuItem value="1:1" sx={{ fontSize: 13 }}>1:1 方形</MenuItem>
            </Select>
            <Select
              size="small"
              value={shortMode}
              onChange={(e) => setShortMode(e.target.value as 'blur' | 'crop')}
              sx={{ minWidth: 190, fontSize: 13 }}
            >
              <MenuItem value="blur" sx={{ fontSize: 13 }}>留全画面（图表不被切）</MenuItem>
              <MenuItem value="crop" sx={{ fontSize: 13 }}>裁满屏（两侧会丢）</MenuItem>
            </Select>
            <Button size="small" variant="contained" onClick={makeShort} disabled={!cutIds.length || busy}>
              生成竖版
            </Button>
          </Stack>
        </CardContent>
      </Card>

      <Card variant="outlined">
        <CardContent>
          <Typography variant="subtitle1" gutterBottom>
            🗣 照片变成会说话的头
          </Typography>
          <Typography variant="body2" color="text.secondary" gutterBottom>
            一张正面照 + 某一段的旁白 → 一段会开口、会点头眨眼的头部视频。生成后会自动填进上面的「换头」框，
            再对你自己的镜头跑一次遮挡，就得到「身体动作是我的、脸不是我的」的画面。
            <br />
            <b>内置「动态」引擎</b>不需要显卡：按语音的响度驱动嘴和头，对的是说话节奏而不是每个音节。
            <b>开源模型</b>（SadTalker / EchoMimic / Hallo）能真正对上音节，但要 NVIDIA 显卡，装好后把命令写进环境变量{' '}
            <code>PHOTO_TALK_CMD</code>（占位符 {'{image} {audio} {out} {outdir}'}）。
          </Typography>
          <Stack spacing={1.5} sx={{ mt: 1 }}>
            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
              <TextField
                size="small"
                label="照片（项目内路径）"
                value={photo}
                onChange={(e) => setPhoto(e.target.value)}
                placeholder="assets/local/me.jpg"
                sx={{ minWidth: 300 }}
                helperText="会自动裁成头部特写"
              />
              <Select size="small" value={segment} displayEmpty onChange={(e) => setSegment(e.target.value)} sx={{ minWidth: 220 }}>
                <MenuItem value="">用哪一段的旁白…</MenuItem>
                {segments.map((sg) => (
                  <MenuItem key={sg.id} value={sg.id}>
                    {sg.id}
                  </MenuItem>
                ))}
              </Select>
              <Select size="small" value={provider} onChange={(e) => setProvider(e.target.value as 'motion' | 'cmd')} sx={{ minWidth: 200 }}>
                <MenuItem value="motion">动态（内置，无需显卡）</MenuItem>
                <MenuItem value="cmd">开源模型（PHOTO_TALK_CMD）</MenuItem>
              </Select>
              <Button size="small" variant="contained" onClick={makeHead} disabled={!photo || !segment || busy}>
                生成会说话的头
              </Button>
            </Stack>
            <Typography variant="caption" color="text.secondary">
              这一段要先在第 2 步试听过（需要已经生成的配音文件）。用真人照片做的说话头属于合成内容，
              发布时按平台要求声明。
            </Typography>
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
