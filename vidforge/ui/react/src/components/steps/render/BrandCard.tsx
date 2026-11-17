import { useEffect, useRef, useState } from 'react'
import { Alert, Box, Button, Card, CardContent, Chip, LinearProgress, MenuItem, Slider, Stack, Switch, FormControlLabel, TextField, Typography } from '@mui/material'
import MovieCreationIcon from '@mui/icons-material/MovieCreation'
import { apiGet, apiPost } from '../../../api/client'
import { useProject } from '../../../state/ProjectContext'
import { fileUrl, takeFiles } from '../../../utils'
import { PanelTitle } from '../../shared/ui'

type Kit = {
  name: string
  slogan: string
  en_name: string
  mark: string
  intro: boolean
  outro: boolean
  intro_seconds: number
  outro_seconds: number
  subscribe: string
  next_hint: string
  sting: string
  outro_music: string
}
type BrandView = {
  kit: Kit
  project: { intro?: boolean; outro?: boolean }
  bgm: { file: string; volume_db?: number; fade_out?: number; duck?: boolean } | null
  stings: string[]
  slogans: string[]
  has: { sting: boolean; outro_music: boolean }
  remotion: boolean
  file: string
}

const STING_NAMES: Record<string, string> = { rise: '上扬（三个音）', settle: '落定（三个音）', two: '两个音（最轻）' }

function readAsBase64(f: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const rd = new FileReader()
    rd.onload = () => resolve((rd.result as string).split(',')[1])
    rd.onerror = reject
    rd.readAsDataURL(f)
  })
}

/**
 * 片头、片尾、音乐和 slogan in one place. The channel's kit is shared by every video (one file in
 * ~/.vidforge/brand); this video only says whether it uses the opener and the end card, and which
 * background music it has.
 */
export function BrandCard() {
  const { raw, patch, reload } = useProject()
  const [v, setV] = useState<BrandView | null>(null)
  const [kit, setKit] = useState<Kit | null>(null)
  const [busy, setBusy] = useState('')
  const [msg, setMsg] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [preview, setPreview] = useState<{ intro: string; outro: string } | null>(null)
  const files = { sting: useRef<HTMLInputElement>(null), outro_music: useRef<HTMLInputElement>(null), bgm: useRef<HTMLInputElement>(null) }

  const load = (j: BrandView) => {
    setV(j)
    setKit(j.kit)
  }
  useEffect(() => {
    apiGet<BrandView>('/api/brand').then(load).catch((e) => setError(String(e)))
  }, [])

  if (!raw || !v || !kit) return null

  const run = async (label: string, fn: () => Promise<void>) => {
    setBusy(label)
    setError(null)
    setMsg('')
    try {
      await fn()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
    setBusy('')
  }
  const saveKit = () =>
    run('保存', async () => {
      load(await apiPost<BrandView>('/api/brand', { kit }))
      setMsg('已保存，以后每条视频都用这一套。')
    })
  const setSting = (style: string) => run('音效', async () => load(await apiPost<BrandView>('/api/brand/sting', { style })))
  const upload = (kind: 'sting' | 'outro_music' | 'bgm', f: File) =>
    run('上传', async () => {
      const j = await apiPost<BrandView & { seconds: number }>('/api/audio/upload', { kind, name: f.name, data_b64: await readAsBase64(f) })
      load(j)
      if (kind === 'bgm') await reload()
      setMsg(`已上传 ${f.name}（${j.seconds.toFixed(1)} 秒）`)
    })
  const setOwn = (k: 'intro' | 'outro', on: boolean) =>
    run('', async () => {
      const own = { ...v.project, [k]: on === kit[k] ? undefined : on }
      load(await apiPost<BrandView>('/api/brand/project', own))
      await reload()
    })
  const makePreview = () =>
    run('预览', async () => {
      await apiPost('/api/brand', { kit })
      setPreview(await apiPost<{ intro: string; outro: string }>('/api/brand/preview', {}))
    })

  const introOn = v.project.intro ?? kit.intro
  const outroOn = v.project.outro ?? kit.outro
  const bgm = raw.bgm
  const set = (k: keyof Kit, value: unknown) => setKit({ ...kit, [k]: value })
  const hidden = (kind: 'sting' | 'outro_music' | 'bgm') => (
    <input ref={files[kind]} type="file" hidden accept="audio/*,.mp3,.m4a,.wav,.aac" onChange={(e) => takeFiles(e).slice(0, 1).forEach((f) => upload(kind, f))} />
  )

  return (
    <Card>
      <CardContent>
        <PanelTitle
          icon={<MovieCreationIcon />}
          tone="orange"
          title="片头、片尾和音乐"
          sub="频道名和 slogan 在片头（约 1 秒）和片尾（约 6 秒，YouTube 片尾画面要 5 秒以上才能点）出现。这一套所有视频共用；背景音乐每条视频自己选。"
        />

        <Typography variant="subtitle2" sx={{ mt: 1 }}>
          频道
        </Typography>
        <Stack direction="row" spacing={1.5} flexWrap="wrap" useFlexGap sx={{ mt: 1 }}>
          <TextField size="small" label="频道名" value={kit.name} onChange={(e) => set('name', e.target.value)} sx={{ width: 180 }} helperText="空着就不加片头片尾" />
          <TextField
            size="small"
            label="slogan"
            value={kit.slogan}
            onChange={(e) => set('slogan', e.target.value)}
            sx={{ width: 260 }}
            helperText={kit.slogan.length > 12 ? `${kit.slogan.length} 字，片头只有 1 秒，12 字以内最好` : '一句话，12 字以内'}
            error={kit.slogan.length > 12}
          />
          <TextField size="small" label="英文名（可选）" value={kit.en_name} onChange={(e) => set('en_name', e.target.value)} sx={{ width: 180 }} />
        </Stack>
        <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap sx={{ mt: 0.5 }} alignItems="center">
          <Typography variant="caption" color="text.secondary">
            换一句：
          </Typography>
          {v.slogans.map((s) => (
            <Chip key={s} size="small" label={s} onClick={() => set('slogan', s)} variant={kit.slogan === s ? 'filled' : 'outlined'} />
          ))}
        </Stack>

        <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: '1fr 1fr' }, gap: 2, mt: 2 }}>
          <Box sx={{ p: 1.5, border: '1px solid', borderColor: 'divider', borderRadius: 2 }}>
            <FormControlLabel control={<Switch checked={introOn} onChange={(e) => setOwn('intro', e.target.checked)} />} label={<Typography variant="subtitle2">片头（这条视频）</Typography>} />
            <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap sx={{ mt: 1 }}>
              <TextField size="small" type="number" label="秒" value={kit.intro_seconds} onChange={(e) => set('intro_seconds', parseFloat(e.target.value) || 1.2)} sx={{ width: 80 }} slotProps={{ htmlInput: { step: 0.1, min: 0.6, max: 3 } }} />
              <TextField size="small" select label="片头音效" value={v.has.sting ? '__current' : 'none'} onChange={(e) => (e.target.value === '__upload' ? files.sting.current?.click() : e.target.value !== '__current' && setSting(e.target.value))} sx={{ minWidth: 200 }}>
                <MenuItem value="none">不加</MenuItem>
                {v.has.sting && <MenuItem value="__current">现在的：{kit.sting.split(/[\\/]/).pop()}</MenuItem>}
                {v.stings.map((s) => (
                  <MenuItem key={s} value={s}>
                    合成：{STING_NAMES[s] || s}
                  </MenuItem>
                ))}
                <MenuItem value="__upload">上传自己的…</MenuItem>
              </TextField>
              {v.has.sting && <Box component="audio" controls src={`/api/brand/file?kind=sting&t=${encodeURIComponent(kit.sting)}`} sx={{ height: 32 }} />}
              {hidden('sting')}
            </Stack>
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5 }}>
              片头超过 5 秒会让 30 秒时还在看的人明显变少，所以只有一秒左右。合成音效是程序生成的，没有版权问题。
            </Typography>
          </Box>
          <Box sx={{ p: 1.5, border: '1px solid', borderColor: 'divider', borderRadius: 2 }}>
            <FormControlLabel control={<Switch checked={outroOn} onChange={(e) => setOwn('outro', e.target.checked)} />} label={<Typography variant="subtitle2">片尾（这条视频）</Typography>} />
            <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap sx={{ mt: 1 }}>
              <TextField size="small" type="number" label="秒" value={kit.outro_seconds} onChange={(e) => set('outro_seconds', parseFloat(e.target.value) || 6)} sx={{ width: 80 }} slotProps={{ htmlInput: { step: 0.5, min: 5, max: 20 } }} />
              <TextField size="small" label="订阅语" value={kit.subscribe} onChange={(e) => set('subscribe', e.target.value)} sx={{ width: 160 }} />
              <TextField size="small" label="下期预告" value={kit.next_hint} onChange={(e) => set('next_hint', e.target.value)} sx={{ width: 180 }} placeholder="下期：…" />
            </Stack>
            <Stack direction="row" spacing={1} alignItems="center" sx={{ mt: 1 }}>
              <Button size="small" onClick={() => files.outro_music.current?.click()}>
                {v.has.outro_music ? '换片尾音乐…' : '上传片尾音乐…'}
              </Button>
              {v.has.outro_music && <Box component="audio" controls src={`/api/brand/file?kind=outro_music&t=${encodeURIComponent(kit.outro_music)}`} sx={{ height: 32 }} />}
              {hidden('outro_music')}
            </Stack>
          </Box>
        </Box>

        <Stack direction="row" spacing={1} alignItems="center" sx={{ mt: 1.5 }}>
          <Button variant="contained" onClick={saveKit} disabled={!!busy}>
            保存频道设置
          </Button>
          <Button onClick={makePreview} disabled={!!busy || !kit.name || !v.remotion} title={v.remotion ? '' : '要先装好动画组件（vidforge remotion setup）'}>
            预览片头片尾
          </Button>
          <Typography variant="caption" color="text.secondary">
            保存在 {v.file}
          </Typography>
        </Stack>
        {preview && (
          <Stack direction="row" spacing={1.5} sx={{ mt: 1.5 }}>
            {(['intro', 'outro'] as const).map((k) => (
              <Box key={k} sx={{ flex: 1, maxWidth: 360 }}>
                <Typography variant="caption">{k === 'intro' ? '片头' : '片尾'}</Typography>
                <Box component="video" src={`${fileUrl(preview[k])}?t=${Date.now()}`} controls sx={{ width: '100%', borderRadius: 1, bgcolor: '#000' }} />
              </Box>
            ))}
          </Stack>
        )}

        <Typography variant="subtitle2" sx={{ mt: 2.5 }}>
          背景音乐（这条视频）
        </Typography>
        <Stack direction="row" spacing={1.5} alignItems="center" flexWrap="wrap" useFlexGap sx={{ mt: 1 }}>
          <Button size="small" variant="outlined" onClick={() => files.bgm.current?.click()}>
            {bgm?.file ? '换一首…' : '选一首音乐…'}
          </Button>
          {hidden('bgm')}
          {bgm?.file && (
            <>
              <Box component="audio" controls src={fileUrl(bgm.file) || ''} sx={{ height: 32 }} />
              <Button size="small" color="inherit" onClick={() => patch((r) => (r.bgm = null))}>
                不要背景音乐
              </Button>
            </>
          )}
        </Stack>
        {bgm?.file && (
          <Stack direction="row" spacing={3} alignItems="center" flexWrap="wrap" useFlexGap sx={{ mt: 1 }}>
            <Box sx={{ width: 260 }}>
              <Typography variant="caption" color="text.secondary">
                音量 {bgm.volume_db ?? -18} dB（-18 左右在旁白下面刚好听得见）
              </Typography>
              <Slider size="small" min={-32} max={-6} value={bgm.volume_db ?? -18} onChange={(_, x) => patch((r) => r.bgm && (r.bgm.volume_db = x as number))} />
            </Box>
            <FormControlLabel
              control={<Switch size="small" checked={bgm.duck !== false} onChange={(e) => patch((r) => r.bgm && (r.bgm.duck = e.target.checked))} />}
              label={<Typography variant="body2">说话时自动压低音乐</Typography>}
            />
            <TextField size="small" type="number" label="结尾淡出（秒）" value={bgm.fade_out ?? 3} onChange={(e) => patch((r) => r.bgm && (r.bgm.fade_out = parseFloat(e.target.value) || 3))} sx={{ width: 140 }} />
          </Stack>
        )}
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5 }}>
          音乐要用有授权的：YouTube 音频库、剪映商用音乐或自己买的曲库；AI 生成的音乐大多不允许商用。
        </Typography>

        {busy && <LinearProgress sx={{ mt: 1.5 }} />}
        {msg && (
          <Alert severity="success" sx={{ mt: 1.5 }}>
            {msg}
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
