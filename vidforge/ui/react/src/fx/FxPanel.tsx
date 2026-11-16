import { useEffect, useRef, useState } from 'react'
import { Box, Button, Chip, Slider, Stack, Switch, Tab, Tabs, ToggleButton, ToggleButtonGroup, Tooltip, Typography } from '@mui/material'
import UploadIcon from '@mui/icons-material/Upload'
import RestartAltIcon from '@mui/icons-material/RestartAlt'
import { apiGet, apiPost } from '../api/client'
import { ROOMS, roomUrl } from './backdrops'
import type { FxStatus } from './engine'
import { DEFAULT_FX, FX_PRESETS, type Aspect, type BgMode, type FxSettings } from './settings'

// Generated backdrops, so "换背景" works before anyone has a photo of a nice room. Each is drawn
// once into a data URL; plain gradients never look like a fake room, which is the point.
const BACKDROPS: { id: string; name: string; draw: (g: CanvasRenderingContext2D, w: number, h: number) => void }[] = [
  ...(
    [
      ['studio', '明亮演播室', '#f4f8fc', '#c9d8e8'],
      ['sunny', '暖阳', '#fff1d6', '#ffb27a'],
      ['mint', '薄荷', '#e6fbf3', '#8fdcc0'],
      ['sky', '晴空', '#e8f3ff', '#7fb6ff'],
    ] as const
  ).map(([id, name, a, b]) => ({
    id,
    name,
    draw: (g: CanvasRenderingContext2D, w: number, h: number) => {
      const r = g.createRadialGradient(w * 0.5, h * 0.4, h * 0.05, w / 2, h / 2, h * 1.05)
      r.addColorStop(0, a)
      r.addColorStop(1, b)
      g.fillStyle = r
      g.fillRect(0, 0, w, h)
    },
  })),
  {
    id: 'bokeh',
    name: '光斑',
    draw: (g, w, h) => {
      g.fillStyle = '#fbeee0'
      g.fillRect(0, 0, w, h)
      let seed = 7
      const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647)
      for (let i = 0; i < 46; i++) {
        const x = rnd() * w
        const y = rnd() * h
        const r = 30 + rnd() * 110
        const c = g.createRadialGradient(x, y, 0, x, y, r)
        const hue = 20 + rnd() * 50
        c.addColorStop(0, `hsla(${hue},95%,72%,0.55)`)
        c.addColorStop(1, `hsla(${hue},95%,72%,0)`)
        g.fillStyle = c
        g.fillRect(x - r, y - r, r * 2, r * 2)
      }
    },
  },
]

function backdropUrl(id: string): string {
  const b = BACKDROPS.find((x) => x.id === id)
  if (!b) return ''
  const c = document.createElement('canvas')
  c.width = 1280
  c.height = 720
  b.draw(c.getContext('2d')!, c.width, c.height)
  return c.toDataURL('image/jpeg', 0.9)
}

function Row({ label, value, min = 0, max = 1, step = 0.01, onChange }: { label: string; value: number; min?: number; max?: number; step?: number; onChange: (v: number) => void }) {
  return (
    <Stack direction="row" spacing={1.5} alignItems="center" sx={{ py: 0.25 }}>
      <Typography variant="body2" sx={{ width: 44, flexShrink: 0, color: 'text.secondary' }}>
        {label}
      </Typography>
      <Slider size="small" min={min} max={max} step={step} value={value} onChange={(_, v) => onChange(v as number)} sx={{ flexGrow: 1 }} />
      <Typography variant="caption" sx={{ width: 30, textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>
        {Math.round(value * 100)}
      </Typography>
    </Stack>
  )
}

function Swatches({ value, onChange, colours }: { value: string; onChange: (c: string) => void; colours: string[] }) {
  return (
    <Stack direction="row" spacing={0.75} alignItems="center" flexWrap="wrap" useFlexGap>
      {colours.map((c) => (
        <Box
          key={c}
          onClick={() => onChange(c)}
          sx={{
            width: 22,
            height: 22,
            borderRadius: '50%',
            bgcolor: c,
            cursor: 'pointer',
            outline: value === c ? '2px solid' : '1px solid',
            outlineColor: value === c ? 'primary.main' : 'divider',
            outlineOffset: 2,
          }}
        />
      ))}
      <Box component="input" type="color" value={value} onChange={(e) => onChange((e.target as HTMLInputElement).value)} sx={{ width: 28, height: 24, border: 0, p: 0, bgcolor: 'transparent', cursor: 'pointer' }} />
    </Stack>
  )
}

type ProjectImage = { path: string; kind: string; title?: string }
type Candidate = { provider: string; id: string; thumb_url: string; title?: string; [k: string]: unknown }

// real photos of rooms with books, from the openly licensed sources (no key needed)
const STUDY_QUERIES = ['home library bookshelf', 'bookshelf room interior', 'study room books']

/** The 美颜 / 美型 / 背景 / 换装 / 画幅 controls — shared by the recording studio and 视频美化. */
export function FxPanel({ fx, onChange, status, showAspect = true }: { fx: FxSettings; onChange: (f: FxSettings) => void; status: FxStatus | null; showAspect?: boolean }) {
  const [tab, setTab] = useState(0)
  const [images, setImages] = useState<ProjectImage[]>([])
  const [room, setRoom] = useState<{ id: string; seed: number } | null>(null)
  const [photos, setPhotos] = useState<Candidate[] | null>(null)
  const [photoBusy, setPhotoBusy] = useState(false)
  const [photoErr, setPhotoErr] = useState('')
  const fileRef = useRef<HTMLInputElement>(null)
  const set = (p: Partial<FxSettings>) => onChange({ ...fx, ...p })
  const preset = FX_PRESETS.find((p) => Object.entries(p.values).every(([k, v]) => Math.abs((fx[k as keyof FxSettings] as number) - (v as number)) < 0.005))

  useEffect(() => {
    if (tab !== 2) return
    apiGet<{ items: ProjectImage[] }>('/api/assets/library')
      .then((j) => setImages(j.items.filter((i) => i.kind === 'image').slice(0, 24)))
      .catch(() => setImages([]))
  }, [tab])

  const pickRoom = (id: string, seed = 7) => {
    setRoom({ id, seed })
    set({ bg: 'image', bgSrc: roomUrl(id, seed) })
  }

  const searchPhotos = async () => {
    setPhotoBusy(true)
    setPhotoErr('')
    const found: Candidate[] = []
    for (const q of STUDY_QUERIES) {
      try {
        const j = await apiGet<{ candidates: Candidate[] }>(`/api/search?source=openverse&kind=image&q=${encodeURIComponent(q)}`)
        for (const c of j.candidates) if (!found.some((x) => x.id === c.id)) found.push(c)
      } catch (e) {
        setPhotoErr(e instanceof Error ? e.message : String(e))
      }
      if (found.length >= 18) break
    }
    setPhotos(found.slice(0, 24))
    setPhotoBusy(false)
  }

  const usePhoto = async (c: Candidate) => {
    setPhotoBusy(true)
    try {
      const j = await apiPost<{ path: string }>('/api/assets/fetch', { candidate: c })
      set({ bg: 'image', bgSrc: `/files/${j.path}` })
    } catch (e) {
      setPhotoErr(e instanceof Error ? e.message : String(e))
    }
    setPhotoBusy(false)
  }

  const pickFile = (f: File) => {
    const url = URL.createObjectURL(f)
    set({ bg: f.type.startsWith('video') ? 'video' : 'image', bgSrc: url })
  }

  const modelHint = (state: string | undefined, what: string) =>
    state === 'loading' ? `${what}模型加载中（第一次要下载）…` : state === 'error' ? `${what}模型没加载上` : ''

  return (
    <Box>
      <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 0.5 }}>
        <Stack direction="row" spacing={1} alignItems="center">
          <Switch size="small" checked={fx.enabled} onChange={(e) => set({ enabled: e.target.checked })} />
          <Typography variant="body2" fontWeight={600}>
            特效
          </Typography>
          {status && (
            <Typography variant="caption" color="text.secondary">
              {status.fps ? `${status.fps} fps` : ''}
            </Typography>
          )}
        </Stack>
        <Tooltip title="全部恢复默认">
          <Button size="small" startIcon={<RestartAltIcon />} onClick={() => onChange({ ...DEFAULT_FX, bgSrc: '' })}>
            重置
          </Button>
        </Tooltip>
      </Stack>
      <Tabs value={tab} onChange={(_, v) => setTab(v)} variant="scrollable" sx={{ minHeight: 36, '& .MuiTab-root': { minHeight: 36, minWidth: 0, px: 1.5 } }}>
        <Tab label="美颜" />
        <Tab label="美型" />
        <Tab label="背景" />
        <Tab label="换装" />
        {showAspect && <Tab label="画幅" />}
      </Tabs>
      <Box sx={{ pt: 1.5, opacity: fx.enabled ? 1 : 0.5, pointerEvents: fx.enabled ? 'auto' : 'none' }}>
        {tab === 0 && (
          <>
            <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap sx={{ mb: 1 }}>
              {FX_PRESETS.map((p) => (
                <Tooltip key={p.id} title={p.about}>
                  <Chip size="small" label={p.name} color={preset?.id === p.id ? 'primary' : 'default'} onClick={() => set(p.values)} />
                </Tooltip>
              ))}
            </Stack>
            <Row label="磨皮" value={fx.smooth} onChange={(v) => set({ smooth: v })} />
            <Row label="美白" value={fx.whiten} onChange={(v) => set({ whiten: v })} />
            <Row label="红润" value={fx.rosy} onChange={(v) => set({ rosy: v })} />
            <Row label="清晰" value={fx.sharpen} onChange={(v) => set({ sharpen: v })} />
            <Row label="亮度" value={fx.bright} min={-1} max={1} onChange={(v) => set({ bright: v })} />
            <Row label="对比" value={fx.contrast} min={-1} max={1} onChange={(v) => set({ contrast: v })} />
            <Row label="饱和" value={fx.saturation} min={-1} max={1} onChange={(v) => set({ saturation: v })} />
            <Row label="色温" value={fx.warmth} min={-1} max={1} onChange={(v) => set({ warmth: v })} />
            <Typography variant="caption" color="text.secondary">
              {modelHint(status?.seg, '人像') || '磨皮只作用在皮肤上（人像分割给出的皮肤区域），背景和头发不会被抹平。'}
            </Typography>
          </>
        )}
        {tab === 1 && (
          <>
            <Row label="瘦脸" value={fx.slim} onChange={(v) => set({ slim: v })} />
            <Row label="大眼" value={fx.eyes} onChange={(v) => set({ eyes: v })} />
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5 }}>
              {modelHint(status?.face, '人脸') ||
                (status?.face === 'ready' && !status.faces ? '没检测到脸——正对镜头、光线亮一点。' : '幅度上限故意压得很低：拉满也只是「上镜一点」，不会变成另一个人。')}
            </Typography>
          </>
        )}
        {tab === 2 && (
          <>
            <ToggleButtonGroup size="small" exclusive value={fx.bg} onChange={(_, v: BgMode | null) => v && set({ bg: v })} sx={{ mb: 1.5, flexWrap: 'wrap' }}>
              <ToggleButton value="none">原背景</ToggleButton>
              <ToggleButton value="blur">虚化</ToggleButton>
              <ToggleButton value="image">图片</ToggleButton>
              <ToggleButton value="video">视频</ToggleButton>
              <ToggleButton value="color">纯色</ToggleButton>
            </ToggleButtonGroup>
            {fx.bg === 'blur' && <Row label="虚化" value={fx.bgBlur} onChange={(v) => set({ bgBlur: v })} />}
            {fx.bg === 'color' && <Swatches value={fx.bgColor} onChange={(c) => set({ bgColor: c })} colours={['#ffd166', '#ff8a3d', '#14c38e', '#2f8cff', '#ff5c7a', '#f1ece4', '#ffffff', '#00b140']} />}
            {(fx.bg === 'image' || fx.bg === 'video') && (
              <>
                {fx.bg === 'image' && (
                  <>
                    <Typography variant="caption" color="text.secondary">
                      书房（带景深虚化，像真的房间）
                    </Typography>
                    <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap sx={{ mt: 0.5, mb: 1 }}>
                      {ROOMS.map((r) => (
                        <Chip key={r.id} size="small" label={r.name} color={room?.id === r.id ? 'primary' : 'default'} onClick={() => pickRoom(r.id)} />
                      ))}
                      {room && <Chip size="small" variant="outlined" label="换一种摆法" onClick={() => pickRoom(room.id, room.seed + 11)} />}
                    </Stack>
                    <Button size="small" variant="outlined" onClick={searchPhotos} disabled={photoBusy} sx={{ mb: 1 }}>
                      {photoBusy ? '搜索中…' : '搜真实书房照片（免费授权）'}
                    </Button>
                    {photoErr && (
                      <Typography variant="caption" color="warning.main" sx={{ display: 'block' }}>
                        {photoErr}
                      </Typography>
                    )}
                    {photos && (
                      <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 0.5, mb: 1, maxHeight: 170, overflowY: 'auto' }}>
                        {photos.length === 0 && <Typography variant="caption">没搜到</Typography>}
                        {photos.map((c) => (
                          <Box key={c.id} component="img" src={c.thumb_url} title={c.title} loading="lazy" onClick={() => usePhoto(c)} sx={{ width: '100%', aspectRatio: '16/9', objectFit: 'cover', borderRadius: 0.5, cursor: 'pointer' }} />
                        ))}
                      </Box>
                    )}
                    <Typography variant="caption" color="text.secondary">
                      其他
                    </Typography>
                  </>
                )}
                <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ mb: 1, mt: 0.5 }}>
                  {fx.bg === 'image' &&
                    BACKDROPS.map((b) => (
                      <Chip key={b.id} size="small" label={b.name} onClick={() => set({ bgSrc: backdropUrl(b.id) })} />
                    ))}
                  <Button size="small" variant="outlined" startIcon={<UploadIcon />} onClick={() => fileRef.current?.click()}>
                    {fx.bg === 'video' ? '选视频' : '选图片'}
                  </Button>
                  <input ref={fileRef} type="file" hidden accept={fx.bg === 'video' ? 'video/*' : 'image/*'} onChange={(e) => e.target.files?.[0] && pickFile(e.target.files[0])} />
                </Stack>
                {fx.bg === 'image' && images.length > 0 && (
                  <>
                    <Typography variant="caption" color="text.secondary">
                      这个项目里的图片
                    </Typography>
                    <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 0.5, mt: 0.5, maxHeight: 150, overflowY: 'auto' }}>
                      {images.map((i) => (
                        <Box
                          key={i.path}
                          component="img"
                          src={`/files/${i.path}`}
                          loading="lazy"
                          onClick={() => set({ bgSrc: `/files/${i.path}` })}
                          sx={{ width: '100%', aspectRatio: '16/9', objectFit: 'cover', borderRadius: 0.5, cursor: 'pointer', outline: fx.bgSrc === `/files/${i.path}` ? '2px solid' : 'none', outlineColor: 'primary.main' }}
                        />
                      ))}
                    </Box>
                  </>
                )}
                {!fx.bgSrc && (
                  <Typography variant="caption" color="warning.main" sx={{ display: 'block' }}>
                    还没选{fx.bg === 'video' ? '视频' : '图片'}
                  </Typography>
                )}
              </>
            )}
            {fx.bg !== 'none' && <Row label="边缘" value={fx.edge} onChange={(v) => set({ edge: v })} />}
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5 }}>
              {modelHint(status?.seg, '人像') || '不需要绿幕。边缘越柔越自然；头发边上有闪烁就把「边缘」调大一点。'}
            </Typography>
          </>
        )}
        {tab === 3 && (
          <>
            <Typography variant="body2" sx={{ mb: 0.5 }}>
              衣服换色
            </Typography>
            <Row label="强度" value={fx.clothes} onChange={(v) => set({ clothes: v })} />
            <Swatches value={fx.clothesColor} onChange={(c) => set({ clothesColor: c, clothes: fx.clothes || 0.85 })} colours={['#2c3e50', '#1d1d1d', '#f5f5f5', '#8b1e3f', '#2f5d50', '#c9a227', '#3a6ea5']} />
            <Typography variant="body2" sx={{ mt: 1.5, mb: 0.5 }}>
              头发换色
            </Typography>
            <Row label="强度" value={fx.hair} onChange={(v) => set({ hair: v })} />
            <Swatches value={fx.hairColor} onChange={(c) => set({ hairColor: c, hair: fx.hair || 0.6 })} colours={['#3b2416', '#111111', '#6b4423', '#a0522d', '#c0c0c0']} />
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
              只换颜色、保留原来的褶皱和光影，所以不假。整件换成另一件衣服需要 GPU 生成模型，没有做（见说明）。
            </Typography>
          </>
        )}
        {tab === 4 && showAspect && (
          <>
            <ToggleButtonGroup size="small" exclusive value={fx.aspect} onChange={(_, v: Aspect | null) => v && set({ aspect: v })} sx={{ flexWrap: 'wrap' }}>
              <ToggleButton value="source">原始</ToggleButton>
              <ToggleButton value="16:9">16:9 横屏</ToggleButton>
              <ToggleButton value="9:16">9:16 竖屏</ToggleButton>
              <ToggleButton value="3:4">3:4</ToggleButton>
              <ToggleButton value="1:1">1:1</ToggleButton>
            </ToggleButtonGroup>
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
              9:16 给抖音 / 快手 / TikTok / 视频号；16:9 给 YouTube / 西瓜 / 头条横版。从画面中间裁，录出来的文件就是这个比例。
            </Typography>
          </>
        )}
      </Box>
      {status?.error && (
        <Typography variant="caption" color="warning.main" sx={{ display: 'block', mt: 1 }}>
          {status.error}
        </Typography>
      )}
    </Box>
  )
}
