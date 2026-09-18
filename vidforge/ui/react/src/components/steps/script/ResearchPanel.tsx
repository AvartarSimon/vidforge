import { useState } from 'react'
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Box,
  Button,
  Chip,
  MenuItem,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material'
import ExpandMoreIcon from '@mui/icons-material/ExpandMore'
import { apiGet, apiPost } from '../../../api/client'
import type { AnalyzeResult, ChatSite, YoutubeSummary, YoutubeVideo } from '../../../api/types'
import { useProject } from '../../../state/ProjectContext'
import { fmtDuration } from '../../../utils'

const VERDICT_LABEL: Record<string, string> = { do: '值得做', do_with_angle: '换视角做', skip: '跳过' }
const VERDICT_COLOR: Record<string, 'success' | 'error' | 'warning'> = { do: 'success', skip: 'error', do_with_angle: 'warning' }

export function ResearchPanel({ onUseAngle }: { onUseAngle: (angle: string) => void }) {
  const { raw, patch } = useProject()
  const [q, setQ] = useState(raw?.title || '')
  const [positioning, setPositioning] = useState('')
  const [videos, setVideos] = useState<YoutubeVideo[] | null>(null)
  const [summary, setSummary] = useState<YoutubeSummary | null>(null)
  const [source, setSource] = useState<string | null>(null)
  const [searching, setSearching] = useState(false)
  const [searchError, setSearchError] = useState<string | null>(null)
  const [sites, setSites] = useState<ChatSite[]>([])
  const [site, setSite] = useState(() => localStorage.getItem('vf.site') || 'deepseek')
  const [analyzing, setAnalyzing] = useState(false)
  const [analyzeStatus, setAnalyzeStatus] = useState('')
  const [result, setResult] = useState<AnalyzeResult | null>(null)
  const [rawAnswer, setRawAnswer] = useState('')

  const search = async () => {
    if (!q.trim()) return
    setSearching(true)
    setSearchError(null)
    try {
      const j = await apiGet<{ videos: YoutubeVideo[]; summary: YoutubeSummary; source: string | null }>(
        `/api/research/youtube?q=${encodeURIComponent(q.trim())}&n=20`,
      )
      setVideos(j.videos.slice().sort((a, b) => b.views - a.views))
      setSummary(j.summary)
      setSource(j.source)
      if (!sites.length) {
        const st = await apiGet<{ sites: ChatSite[] }>('/api/chat/sites').catch(() => ({ sites: [] }))
        setSites(st.sites)
      }
    } catch (e) {
      setSearchError(e instanceof Error ? e.message : String(e))
    }
    setSearching(false)
  }

  const copyPrompt = async () => {
    const j = await apiPost<{ prompt: string }>('/api/research/analyze', { q: q.trim(), positioning, site, prompt_only: true })
    await navigator.clipboard.writeText(j.prompt)
    setAnalyzeStatus('提示词已复制（含同类视频数据），贴到任意 AI。')
  }

  const analyze = async () => {
    localStorage.setItem('vf.site', site)
    setAnalyzing(true)
    setAnalyzeStatus('正在浏览器里提问，通常 30–90 秒…')
    setResult(null)
    try {
      const j = await apiPost<{ result: AnalyzeResult; raw: string }>('/api/research/analyze', {
        q: q.trim(),
        positioning,
        site,
      })
      setResult(j.result)
      setRawAnswer(j.raw)
      setAnalyzeStatus('')
    } catch (e) {
      setAnalyzeStatus(e instanceof Error ? e.message : String(e))
    }
    setAnalyzing(false)
  }

  return (
    <Accordion>
      <AccordionSummary expandIcon={<ExpandMoreIcon />}>
        <Typography variant="subtitle1">🔎 选题助手：看 YouTube 上同类视频的数据，让 AI 判断值不值得做、用什么视角</Typography>
      </AccordionSummary>
      <AccordionDetails>
        <Stack spacing={1.5}>
          <Stack direction="row" spacing={1}>
            <TextField size="small" label="候选主题" value={q} onChange={(e) => setQ(e.target.value)} sx={{ flexGrow: 1 }} />
            <TextField
              size="small"
              label="频道定位（可选）"
              value={positioning}
              onChange={(e) => setPositioning(e.target.value)}
              sx={{ flexGrow: 1 }}
              placeholder="例：英文历史解说，15 分钟长视频"
            />
            <Button variant="contained" onClick={search} disabled={searching}>
              看同类视频
            </Button>
          </Stack>
          {searchError && <Typography color="error">{searchError}</Typography>}
          {summary && summary.count > 0 && (
            <>
              <Typography variant="caption" color="text.secondary">
                {source === 'api' ? '数据来自 YouTube Data API' : '数据来自 YouTube 搜索页（无 key，近似值；设 YOUTUBE_API_KEY 可得精确统计）'} ·{' '}
                {summary.count} 条 · 中位播放 {(summary.median_views || 0).toLocaleString()} · 近 12 个月新发 {summary.recent_12m}{' '}
                条（中位 {(summary.recent_median_views || 0).toLocaleString()}） · ≥8 分钟占 {Math.round((summary.long_form_share || 0) * 100)}% ·
                中位时长 {summary.median_duration_min} 分
              </Typography>
              <Box sx={{ maxHeight: 260, overflow: 'auto' }}>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>播放</TableCell>
                      <TableCell>每天</TableCell>
                      <TableCell>年龄</TableCell>
                      <TableCell>时长</TableCell>
                      <TableCell>频道</TableCell>
                      <TableCell>标题</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {(videos || []).map((v) => (
                      <TableRow key={v.video_id}>
                        <TableCell>{v.views.toLocaleString()}</TableCell>
                        <TableCell>{v.views_per_day ?? '–'}</TableCell>
                        <TableCell>{v.age_days != null ? `${Math.round(v.age_days / 30)} 月` : '–'}</TableCell>
                        <TableCell>{v.duration_s ? fmtDuration(v.duration_s) : '–'}</TableCell>
                        <TableCell>{v.channel}</TableCell>
                        <TableCell>
                          <a href={v.url} target="_blank" rel="noreferrer">
                            {v.title}
                          </a>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </Box>
              <Stack direction="row" spacing={1} alignItems="center">
                <TextField select size="small" label="用哪个网站" value={site} onChange={(e) => setSite(e.target.value)} sx={{ minWidth: 160 }}>
                  {sites.map((s) => (
                    <MenuItem key={s.id} value={s.id}>
                      {s.label}
                    </MenuItem>
                  ))}
                </TextField>
                <Button variant="contained" onClick={analyze} disabled={analyzing}>
                  让 AI 评估（我的浏览器）
                </Button>
                <Button onClick={copyPrompt}>只复制提示词</Button>
                <Typography variant="caption" color="text.secondary">
                  {analyzeStatus}
                </Typography>
              </Stack>
            </>
          )}
          {result && (
            <Box sx={{ p: 1.5, border: '1px solid', borderColor: 'divider', borderRadius: 2 }}>
              {result.raw ? (
                <Typography component="pre" variant="body2" sx={{ whiteSpace: 'pre-wrap' }}>
                  {rawAnswer}
                </Typography>
              ) : (
                <Stack spacing={1}>
                  <Stack direction="row" spacing={1} alignItems="center">
                    {result.verdict && (
                      <Chip size="small" label={VERDICT_LABEL[result.verdict] || result.verdict} color={VERDICT_COLOR[result.verdict] || 'default'} />
                    )}
                    <Typography variant="caption" color="text.secondary">
                      饱和度：{result.saturation}
                    </Typography>
                  </Stack>
                  <Typography variant="body2">{result.why}</Typography>
                  {!!result.angles?.length && (
                    <Box>
                      <Typography variant="subtitle2">差异化视角</Typography>
                      {result.angles.map((a, i) => {
                        const title = typeof a === 'string' ? a : a.title
                        const why = typeof a === 'string' ? undefined : a.why
                        return (
                          <Stack key={i} direction="row" spacing={1} alignItems="center">
                            <Typography variant="body2">
                              <b>{title}</b>
                              {why ? ` — ${why}` : ''}
                            </Typography>
                            <Button size="small" onClick={() => onUseAngle(title)}>
                              用这个视角
                            </Button>
                          </Stack>
                        )
                      })}
                    </Box>
                  )}
                  <Stack direction="row" spacing={4} flexWrap="wrap" useFlexGap>
                    {!!result.titles?.length && (
                      <Box>
                        <Typography variant="subtitle2">标题候选</Typography>
                        {result.titles.map((t, i) => (
                          <Stack key={i} direction="row" spacing={1}>
                            <Typography variant="body2">{t}</Typography>
                            <Button size="small" onClick={() => patch((r) => (r.title = t))}>
                              用
                            </Button>
                          </Stack>
                        ))}
                      </Box>
                    )}
                    {!!result.hooks?.length && (
                      <Box>
                        <Typography variant="subtitle2">开场钩子</Typography>
                        {result.hooks.map((h, i) => (
                          <Typography key={i} variant="body2">
                            {h}
                          </Typography>
                        ))}
                      </Box>
                    )}
                    {!!result.strengths_of_top?.length && (
                      <Box>
                        <Typography variant="subtitle2">头部视频的优点</Typography>
                        {result.strengths_of_top.map((s, i) => (
                          <Typography key={i} variant="body2">
                            {s}
                          </Typography>
                        ))}
                      </Box>
                    )}
                    {!!result.gaps?.length && (
                      <Box>
                        <Typography variant="subtitle2">没人讲的空白</Typography>
                        {result.gaps.map((s, i) => (
                          <Typography key={i} variant="body2">
                            {s}
                          </Typography>
                        ))}
                      </Box>
                    )}
                    {!!result.thumbnail_text?.length && (
                      <Box>
                        <Typography variant="subtitle2">封面大字</Typography>
                        {result.thumbnail_text.map((t, i) => (
                          <Stack key={i} direction="row" spacing={1}>
                            <Typography variant="body2">{t}</Typography>
                            <Button size="small" onClick={() => patch((r) => (r.thumbnail_text = t))}>
                              用
                            </Button>
                          </Stack>
                        ))}
                      </Box>
                    )}
                    {!!result.risks?.length && (
                      <Box>
                        <Typography variant="subtitle2">风险</Typography>
                        {result.risks.map((s, i) => (
                          <Typography key={i} variant="body2">
                            {s}
                          </Typography>
                        ))}
                      </Box>
                    )}
                  </Stack>
                </Stack>
              )}
            </Box>
          )}
        </Stack>
      </AccordionDetails>
    </Accordion>
  )
}
