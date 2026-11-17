import { useEffect, useRef, useState } from 'react'
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  LinearProgress,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from '@mui/material'
import TravelExploreIcon from '@mui/icons-material/TravelExplore'
import VideoLibraryIcon from '@mui/icons-material/VideoLibrary'
import AccountTreeIcon from '@mui/icons-material/AccountTree'
import { apiGet, apiPost } from '../../api/client'
import { useProject } from '../../state/ProjectContext'
import { takeFiles } from '../../utils'
import { PanelTitle, TONES } from '../shared/ui'

type Candidate = { url: string; title: string; author: string; views: number | null; seconds: number | null; site: string; thumb: string }
type Ref = { id: string; title: string; author: string; platform: string; url: string; views: number | null; seconds: number; added: string; has_framework: boolean }
type Beat = { name: string; start: number; end: number; seconds: number; role: string; technique: string; excerpt: string }
type Framework = {
  name: string
  about: string
  made_by: 'llm' | 'time'
  template: string
  metrics: { seconds: number; pace: number; pace_unit: string; shots: number; shot_seconds: number; cuts_first_15s: number; first_line_seconds: number; question_up_front: boolean; number_up_front: boolean }
  beats: Beat[]
}
type Job = { state: string; lines: string[]; result: unknown; error: string | null }

const PLATFORM: Record<string, string> = { youtube: 'YouTube', bilibili: 'B站', douyin: '抖音', tiktok: 'TikTok', kuaishou: '快手', xiaohongshu: '小红书', web: '网页', local: '本地文件' }
const BEAT_TONES = [TONES.coral, TONES.orange, TONES.amber, TONES.green, TONES.teal, TONES.blue, TONES.indigo, TONES.violet]

const views = (n: number | null) => (n == null ? '' : n >= 1e8 ? `${(n / 1e8).toFixed(1)} 亿次` : n >= 1e4 ? `${(n / 1e4).toFixed(1)} 万次` : `${n} 次`)
const mmss = (s: number | null) => (s == null ? '' : `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, '0')}`)

function readAsBase64(f: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const rd = new FileReader()
    rd.onload = () => resolve((rd.result as string).split(',')[1])
    rd.onerror = reject
    rd.readAsDataURL(f)
  })
}

/**
 * 参考视频：找到、下载、观看别人做得好的视频，并把其中一条拆成框架——拆出来的框架进「脚本 → 段落骨架」，
 * 和内置模板一样直接套用。视频只在这台电脑上，只用来学结构，不会进成片。
 */
export function ReferencesSection({ onUse }: { onUse: (templateId: string) => void }) {
  const { raw } = useProject()
  const [site, setSite] = useState('bilibili')
  const [query, setQuery] = useState(raw?.title || '')
  const [cands, setCands] = useState<Candidate[] | null>(null)
  const [searching, setSearching] = useState(false)
  const [link, setLink] = useState('')
  const [items, setItems] = useState<Ref[]>([])
  const [job, setJob] = useState<Job | null>(null)
  const [sel, setSel] = useState<string | null>(null)
  const [fw, setFw] = useState<Framework | null>(null)
  const [error, setError] = useState<string | null>(null)
  const timer = useRef<ReturnType<typeof setInterval> | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  const refresh = async () => {
    const j = await apiGet<{ items: Ref[]; job: Job }>('/api/refs')
    setItems(j.items)
    setJob(j.job)
    return j
  }
  useEffect(() => {
    refresh().catch((e) => setError(String(e)))
    return () => {
      if (timer.current) clearInterval(timer.current)
    }
  }, [])
  useEffect(() => {
    if (!sel) return setFw(null)
    apiGet<{ framework: Framework | null }>(`/api/refs/framework?id=${encodeURIComponent(sel)}`)
      .then((j) => setFw(j.framework))
      .catch(() => setFw(null))
  }, [sel])

  const watchJob = (after?: (j: Job) => void) => {
    if (timer.current) clearInterval(timer.current)
    timer.current = setInterval(async () => {
      const j = await apiGet<Job>('/api/refs/job')
      setJob(j)
      if (j.state !== 'running' && timer.current) {
        clearInterval(timer.current)
        timer.current = null
        await refresh()
        after?.(j)
      }
    }, 1500)
  }
  const start = async (path: string, body: object, after?: (j: Job) => void) => {
    setError(null)
    try {
      await apiPost(path, body)
      setJob({ state: 'running', lines: [], result: null, error: null })
      watchJob(after)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }
  const download = (url: string) => start('/api/refs/download', { url }, (j) => j.result && setSel((j.result as Ref).id))
  const extract = (id: string) => start('/api/refs/extract', { id }, (j) => j.result && setFw(j.result as Framework))
  const search = async () => {
    setSearching(true)
    setError(null)
    try {
      setCands((await apiGet<{ candidates: Candidate[] }>(`/api/refs/search?site=${site}&q=${encodeURIComponent(query)}`)).candidates)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
    setSearching(false)
  }
  const importFile = async (f: File) => {
    setError(null)
    try {
      const j = await apiPost<{ item: Ref }>('/api/refs/import', { name: f.name, data_b64: await readAsBase64(f) })
      await refresh()
      setSel(j.item.id)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }
  const remove = async (id: string) => {
    if (!window.confirm('从参考库里删掉这条视频？（拆出来的框架会留在「段落骨架」里）')) return
    await apiPost('/api/refs/delete', { id })
    setSel(null)
    await refresh()
  }
  const dropFramework = async (tid: string) => {
    if (!window.confirm('删掉这个框架？「段落骨架」里就没有它了。视频还在。')) return
    await apiPost('/api/structure/templates/delete', { id: tid })
    setFw(null)
  }

  const running = job?.state === 'running'
  const cur = items.find((i) => i.id === sel)

  return (
    <Stack spacing={2}>
      <Card>
        <CardContent>
          <PanelTitle
            icon={<TravelExploreIcon />}
            tone="pink"
            title="找参考视频"
            sub="YouTube 和 B站可以按主题搜，按播放量排；抖音、TikTok、快手、小红书没法从外面搜，在 App 里找到后粘贴链接，下载不了就保存下来导入。"
          />
          <Stack direction="row" spacing={1.5} alignItems="center" flexWrap="wrap" useFlexGap>
            <ToggleButtonGroup size="small" exclusive value={site} onChange={(_, v) => v && setSite(v)}>
              <ToggleButton value="bilibili">B站</ToggleButton>
              <ToggleButton value="youtube">YouTube</ToggleButton>
            </ToggleButtonGroup>
            <TextField size="small" label="主题" value={query} onChange={(e) => setQuery(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && search()} sx={{ minWidth: 280, flex: 1 }} />
            <Button variant="contained" onClick={search} disabled={searching || !query.trim()}>
              搜索
            </Button>
          </Stack>
          {searching && <LinearProgress sx={{ mt: 1.5 }} />}
          {cands && (
            <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 1.5, mt: 2 }}>
              {cands.map((c) => (
                <Box key={c.url} sx={{ border: '1px solid', borderColor: 'divider', borderRadius: 2, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
                  <Box component="img" src={c.thumb ? `/api/refs/thumb?u=${encodeURIComponent(c.thumb)}` : ''} alt="" sx={{ width: '100%', aspectRatio: '16 / 9', objectFit: 'cover', bgcolor: 'action.hover' }} />
                  <Box sx={{ p: 1, flex: 1, display: 'flex', flexDirection: 'column', gap: 0.5 }}>
                    <Typography variant="body2" sx={{ fontWeight: 600, lineHeight: 1.35, display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
                      {c.title}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      {c.author} · {views(c.views)} · {mmss(c.seconds)}
                    </Typography>
                    <Stack direction="row" spacing={1} sx={{ mt: 'auto' }}>
                      <Button size="small" variant="outlined" onClick={() => download(c.url)} disabled={running}>
                        下载
                      </Button>
                      <Button size="small" href={c.url} target="_blank">
                        原页面
                      </Button>
                    </Stack>
                  </Box>
                </Box>
              ))}
              {!cands.length && <Typography color="text.secondary">没搜到，换个说法试试。</Typography>}
            </Box>
          )}
          <Stack direction="row" spacing={1.5} alignItems="center" flexWrap="wrap" useFlexGap sx={{ mt: 2 }}>
            <TextField size="small" label="粘贴链接（任何平台）" value={link} onChange={(e) => setLink(e.target.value)} placeholder="https://v.douyin.com/… / https://www.bilibili.com/video/BV…" sx={{ minWidth: 360, flex: 1 }} />
            <Button variant="outlined" onClick={() => download(link)} disabled={running || !/^https?:\/\//.test(link.trim())}>
              下载
            </Button>
            <Button onClick={() => fileRef.current?.click()}>导入本地文件…</Button>
            <input ref={fileRef} type="file" hidden accept="video/*" onChange={(e) => takeFiles(e).slice(0, 1).forEach(importFile)} />
          </Stack>
          {running && (
            <Box sx={{ mt: 1.5 }}>
              <LinearProgress />
              <Typography variant="caption" color="text.secondary">
                {job?.lines.slice(-1)[0] || '处理中…'}
              </Typography>
            </Box>
          )}
          {(error || (job?.state === 'done' && job.error)) && (
            <Alert severity="warning" sx={{ mt: 1.5 }}>
              {error || job?.error}
            </Alert>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardContent>
          <PanelTitle
            icon={<VideoLibraryIcon />}
            tone="violet"
            title={`我的参考视频（${items.length}）`}
            sub="只在这台电脑上（~/.vidforge/references/），用来看和学结构；别把别人的画面和台词用进自己的视频。"
          />
          <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 1.5 }}>
            {items.map((i) => (
              <Box
                key={i.id}
                onClick={() => setSel(i.id)}
                sx={{ cursor: 'pointer', border: '2px solid', borderColor: sel === i.id ? 'primary.main' : 'divider', borderRadius: 2, overflow: 'hidden' }}
              >
                <Box component="img" src={`/api/refs/file/${encodeURIComponent(i.id)}/thumb.jpg`} alt="" sx={{ width: '100%', aspectRatio: '16 / 9', objectFit: 'cover', display: 'block', bgcolor: '#000' }} />
                <Box sx={{ p: 1 }}>
                  <Typography variant="body2" sx={{ fontWeight: 600, lineHeight: 1.35, display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
                    {i.title}
                  </Typography>
                  <Stack direction="row" spacing={0.5} alignItems="center" sx={{ mt: 0.5 }} flexWrap="wrap" useFlexGap>
                    <Chip size="small" label={PLATFORM[i.platform] || i.platform} />
                    <Typography variant="caption" color="text.secondary">
                      {mmss(i.seconds)} {views(i.views)}
                    </Typography>
                    {i.has_framework && <Chip size="small" color="success" variant="outlined" label="已拆框架" />}
                  </Stack>
                </Box>
              </Box>
            ))}
          </Box>
          {!items.length && <Typography color="text.secondary">还没有参考视频：在上面搜一个主题，或者粘贴链接。</Typography>}
        </CardContent>
      </Card>

      {cur && (
        <Card>
          <CardContent>
            <PanelTitle
              icon={<AccountTreeIcon />}
              tone="indigo"
              title={cur.title}
              sub={`${PLATFORM[cur.platform] || cur.platform}${cur.author ? ` · ${cur.author}` : ''}${cur.views ? ` · ${views(cur.views)}` : ''} · ${mmss(cur.seconds)}`}
              action={
                <Stack direction="row" spacing={1}>
                  {cur.url && (
                    <Button size="small" href={cur.url} target="_blank">
                      原页面
                    </Button>
                  )}
                  <Button size="small" color="inherit" onClick={() => remove(cur.id)}>
                    删除
                  </Button>
                </Stack>
              }
            />
            <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', lg: 'minmax(0, 420px) 1fr' }, gap: 2, alignItems: 'start' }}>
              <Box component="video" key={cur.id} src={`/api/refs/file/${encodeURIComponent(cur.id)}/video.mp4`} controls sx={{ width: '100%', borderRadius: 2, bgcolor: '#000', maxHeight: '60vh' }} />
              <Box>
                {!fw && (
                  <Stack spacing={1}>
                    <Typography variant="body2" color="text.secondary">
                      拆框架：听出台词、数镜头，再让本地模型把它分成几块（钩子、背景、数据、转折……），每块写清楚在做什么、用了什么手法。
                      一条 5 分钟的视频大约要 1 分钟。拆出来的框架会出现在「脚本 → 段落骨架」里。
                    </Typography>
                    <Box>
                      <Button variant="contained" onClick={() => extract(cur.id)} disabled={running}>
                        提取框架
                      </Button>
                    </Box>
                  </Stack>
                )}
                {fw && (
                  <Stack spacing={1.25}>
                    <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                      <Typography variant="subtitle1">{fw.name}</Typography>
                      {fw.made_by === 'time' && <Chip size="small" color="warning" variant="outlined" label="没有本地模型，按时间粗分" />}
                    </Stack>
                    {fw.about && (
                      <Typography variant="body2" color="text.secondary">
                        {fw.about}
                      </Typography>
                    )}
                    <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
                      <Chip size="small" label={`${fw.metrics.pace} ${fw.metrics.pace_unit}`} />
                      <Chip size="small" label={`平均 ${fw.metrics.shot_seconds} 秒一个镜头（共 ${fw.metrics.shots} 个）`} />
                      <Chip size="small" label={`前 15 秒切了 ${fw.metrics.cuts_first_15s} 次`} />
                      <Chip size="small" label={`第一句 ${fw.metrics.first_line_seconds} 秒说完`} />
                      {fw.metrics.question_up_front && <Chip size="small" color="success" variant="outlined" label="开头就抛问题" />}
                      {fw.metrics.number_up_front && <Chip size="small" color="success" variant="outlined" label="开头有数字" />}
                    </Stack>
                    {/* the blocks to scale, so the proportions read at a glance */}
                    <Box sx={{ display: 'flex', height: 22, borderRadius: 1, overflow: 'hidden' }}>
                      {fw.beats.map((b, k) => (
                        <Box key={k} title={`${b.name} ${b.seconds}s`} sx={{ flex: b.seconds, bgcolor: BEAT_TONES[k % BEAT_TONES.length], color: '#fff', fontSize: 11, fontWeight: 700, display: 'grid', placeItems: 'center', overflow: 'hidden', whiteSpace: 'nowrap' }}>
                          {b.name}
                        </Box>
                      ))}
                    </Box>
                    <Table size="small">
                      <TableHead>
                        <TableRow>
                          <TableCell>块</TableCell>
                          <TableCell>时间</TableCell>
                          <TableCell>要做到什么</TableCell>
                          <TableCell>手法</TableCell>
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {fw.beats.map((b, k) => (
                          <TableRow key={k} title={b.excerpt}>
                            <TableCell sx={{ whiteSpace: 'nowrap', fontWeight: 600, color: BEAT_TONES[k % BEAT_TONES.length] }}>{b.name}</TableCell>
                            <TableCell sx={{ whiteSpace: 'nowrap', fontSize: 12 }}>
                              {mmss(b.start)}–{mmss(b.end)}（{Math.round(b.seconds)}s）
                            </TableCell>
                            <TableCell sx={{ fontSize: 12.5 }}>{b.role}</TableCell>
                            <TableCell sx={{ fontSize: 12, color: 'text.secondary' }}>{b.technique}</TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                    <Stack direction="row" spacing={1}>
                      <Button variant="contained" onClick={() => onUse(fw.template)}>
                        在脚本里用这个框架
                      </Button>
                      <Button onClick={() => extract(cur.id)} disabled={running}>
                        重新提取
                      </Button>
                      <Button color="inherit" onClick={() => dropFramework(fw.template)}>
                        删掉这个框架
                      </Button>
                    </Stack>
                  </Stack>
                )}
              </Box>
            </Box>
          </CardContent>
        </Card>
      )}
    </Stack>
  )
}
