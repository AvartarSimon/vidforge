import { useState } from 'react'
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  FormControlLabel,
  IconButton,
  Link,
  Stack,
  Switch,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material'
import ContentCopyIcon from '@mui/icons-material/ContentCopy'
import OpenInNewIcon from '@mui/icons-material/OpenInNew'
import SearchIcon from '@mui/icons-material/Search'
import { apiGet } from '../../api/client'
import type { TrendGroup, TrendSource, YoutubeVideo } from '../../api/types'

/**
 * 热点：现在什么在被讨论，以及其中哪些适合这个频道。
 *
 * The upstream half that was missing: `research/` could say whether a topic was worth making, but
 * nothing said which topic to look at today. Two groups rather than one table, because "what is
 * everyone watching" (hot lists) and "what happened in my field" (keyword news) are different
 * questions — put them together and the larger one buries the smaller.
 *
 * Every row carries *why* it scored what it scored, so a wrong ranking is debuggable instead of
 * mysterious. 「查同类视频」 hands the title straight to the existing research endpoint.
 */
export function TrendsSection() {
  const [groups, setGroups] = useState<TrendGroup[]>([])
  const [sources, setSources] = useState<TrendSource[]>([])
  const [notes, setNotes] = useState<string[]>([])
  const [queries, setQueries] = useState('')
  const [onDomain, setOnDomain] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [checking, setChecking] = useState<string | null>(null)
  const [checked, setChecked] = useState<Record<string, YoutubeVideo[]>>({})

  const load = async () => {
    setBusy(true)
    setError(null)
    try {
      const [t, s] = await Promise.all([
        apiGet<{ groups: TrendGroup[]; notes: string[] }>(
          `/api/trends?all=${onDomain ? 0 : 1}&limit=20${queries ? `&queries=${encodeURIComponent(queries)}` : ''}`,
        ),
        apiGet<{ sources: TrendSource[] }>('/api/trends/sources'),
      ])
      setGroups(t.groups)
      setNotes(t.notes || [])
      setSources(s.sources)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
    setBusy(false)
  }

  // the title goes straight to the research endpoint that already exists
  const check = async (title: string) => {
    setChecking(title)
    try {
      const j = await apiGet<{ videos: YoutubeVideo[] }>(
        `/api/research/youtube?q=${encodeURIComponent(title)}&n=12`,
      )
      setChecked((c) => ({ ...c, [title]: j.videos }))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
    setChecking(null)
  }

  const blocked = sources.filter((s) => !s.ok)

  return (
    <Stack spacing={2}>
      <Typography variant="h6">热点</Typography>
      <Typography variant="body2" color="text.secondary">
        热榜告诉你大家在看什么，领域新闻告诉你你关心的方向今天发生了什么。
        打分用的全是本地能算的信号：平台权重 × 榜位、是否落在频道的九个方向、标题里有没有数字（能不能配图表）、
        有没有时间/历史线索。每一行都写了<b>为什么</b>得这个分。
      </Typography>

      <Card variant="outlined">
        <CardContent>
          <Stack direction="row" spacing={1.5} alignItems="center" flexWrap="wrap" useFlexGap>
            <Button variant="contained" onClick={load} disabled={busy}>
              {busy ? '正在取…' : '取一次热点'}
            </Button>
            <TextField
              size="small"
              label="领域新闻的关键词（逗号分隔，留空用九个方向）"
              value={queries}
              onChange={(e) => setQueries(e.target.value)}
              sx={{ minWidth: 320, flexGrow: 1 }}
            />
            <FormControlLabel
              control={<Switch size="small" checked={onDomain} onChange={(e) => setOnDomain(e.target.checked)} />}
              label={<Typography variant="body2">只看频道方向内的</Typography>}
            />
          </Stack>
          {!!notes.length && (
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
              {notes.join('　')}
            </Typography>
          )}
          {!!blocked.length && (
            <Alert severity="info" sx={{ mt: 1 }}>
              抓不到的源：
              {blocked.map((b) => (
                <Box key={b.id} sx={{ fontSize: 12, mt: 0.5 }}>
                  <b>{b.id}</b> — {b.why}
                </Box>
              ))}
              <Box sx={{ fontSize: 12, mt: 0.5, color: 'text.secondary' }}>
                这三个短视频平台锁得最死，而且它们榜上热的多是娱乐和剧情，和这个频道形态本来就不匹配。
                长视频/资讯那几个（YouTube、B 站、头条）恰好都拿得到。
              </Box>
            </Alert>
          )}
          {error && (
            <Alert severity="warning" sx={{ mt: 1 }}>
              {error}
            </Alert>
          )}
        </CardContent>
      </Card>

      {groups.map((g) => (
        <Card key={g.kind} variant="outlined">
          <CardContent>
            <Typography variant="subtitle1" gutterBottom>
              {g.label}
              <Chip size="small" sx={{ ml: 1 }} label={`取回 ${g.fetched} 条 · 入选 ${g.items.length}`} />
            </Typography>
            {!g.items.length && (
              <Typography variant="body2" color="text.secondary">
                这一组里没有落在频道九个方向里的选题。
              </Typography>
            )}
            <Stack spacing={1}>
              {g.items.map((it) => (
                <Box key={it.title} sx={{ borderTop: 1, borderColor: 'divider', pt: 1 }}>
                  <Stack direction="row" spacing={1} alignItems="flex-start" flexWrap="wrap" useFlexGap>
                    <Chip size="small" color="primary" label={it.score.toFixed(1)} sx={{ minWidth: 52 }} />
                    <Box sx={{ flexGrow: 1, minWidth: 240 }}>
                      <Typography variant="body2" sx={{ fontWeight: 500 }}>
                        {it.title}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        {it.reasons.join(' · ')}
                      </Typography>
                    </Box>
                    <Tooltip title="复制标题">
                      <IconButton size="small" onClick={() => navigator.clipboard?.writeText(it.title)}>
                        <ContentCopyIcon fontSize="inherit" />
                      </IconButton>
                    </Tooltip>
                    {it.url && (
                      <Tooltip title="打开原文">
                        <IconButton size="small" component={Link} href={it.url} target="_blank" rel="noreferrer">
                          <OpenInNewIcon fontSize="inherit" />
                        </IconButton>
                      </Tooltip>
                    )}
                    <Button
                      size="small"
                      startIcon={<SearchIcon />}
                      onClick={() => check(it.title)}
                      disabled={checking === it.title}
                    >
                      {checking === it.title ? '查询中…' : '查同类视频'}
                    </Button>
                  </Stack>
                  {checked[it.title] && (
                    <Box sx={{ mt: 0.5, pl: 7 }}>
                      {!checked[it.title].length && (
                        <Typography variant="caption" color="text.secondary">
                          YouTube 上没搜到同类视频——可能是空白，也可能是没人关心。
                        </Typography>
                      )}
                      {checked[it.title].slice(0, 5).map((v) => (
                        <Typography key={v.video_id} variant="caption" sx={{ display: 'block', color: 'text.secondary' }}>
                          {v.views.toLocaleString()} 播放
                          {v.views_per_day ? ` · ${v.views_per_day}/天` : ''} · {v.channel} ·{' '}
                          <Link href={`https://www.youtube.com/watch?v=${v.video_id}`} target="_blank" rel="noreferrer">
                            {v.title.slice(0, 48)}
                          </Link>
                        </Typography>
                      ))}
                    </Box>
                  )}
                </Box>
              ))}
            </Stack>
          </CardContent>
        </Card>
      ))}
    </Stack>
  )
}
