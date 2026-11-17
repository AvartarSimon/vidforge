import { useState } from 'react'
import { Alert, Box, Button, Card, CardContent, Chip, LinearProgress, Stack, Typography } from '@mui/material'
import { apiPost } from '../../../api/client'
import type { RawProject } from '../../../api/types'
import { useProject } from '../../../state/ProjectContext'

type Suggestion = { titles: string[]; description: string; tags: string[]; dropped: string[]; lengths: Record<string, number> }

// the apps whose title limit is short enough to matter when picking (platforms.py title_max)
const TIGHT = [
  ['shipinhao', '视频号'],
  ['toutiao', '头条'],
  ['kuaishou', '快手'],
]

/**
 * 标题 / 简介 / 话题 drafted by the local model from the narration. Nothing is used unseen: a title
 * is set by clicking it, the description and tags by their own buttons.
 */
export function TitleSuggest() {
  const { raw, patch } = useProject()
  const [busy, setBusy] = useState(false)
  const [s, setS] = useState<Suggestion | null>(null)
  const [error, setError] = useState<string | null>(null)

  if (!raw) return null
  const yt = raw.youtube || {}

  const run = async () => {
    setBusy(true)
    setError(null)
    try {
      setS(await apiPost<Suggestion>('/api/platforms/suggest', {}))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
    setBusy(false)
  }

  const setYt = (fn: (y: NonNullable<RawProject['youtube']>) => void) =>
    patch((r) => {
      r.youtube = r.youtube || {}
      fn(r.youtube)
    })

  return (
    <Card variant="outlined">
      <CardContent>
        <Stack direction="row" spacing={2} alignItems="center" flexWrap="wrap" useFlexGap>
          <Typography variant="subtitle1">✨ 标题、简介和话题</Typography>
          <Button variant="outlined" size="small" onClick={run} disabled={busy}>
            {s ? '再写一组' : '用本地 AI 从旁白里写'}
          </Button>
          <Typography variant="caption" color="text.secondary">
            点一个标题就用它；数字只用旁白里有的，带别的数字的标题直接去掉。事实还要你自己核对一遍。
          </Typography>
        </Stack>
        {busy && <LinearProgress sx={{ mt: 1.5 }} />}
        {error && (
          <Alert severity="warning" sx={{ mt: 1.5 }}>
            {error}
          </Alert>
        )}
        {s && (
          <Stack spacing={1.5} sx={{ mt: 1.5 }}>
            <Box>
              {s.titles.map((t) => {
                const tooLong = TIGHT.filter(([id]) => t.length > (s.lengths[id] || 999)).map(([, n]) => n)
                return (
                  <Box key={t} sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5, flexWrap: 'wrap' }}>
                    <Chip
                      label={t}
                      color={yt.title === t ? 'primary' : 'default'}
                      variant={yt.title === t ? 'filled' : 'outlined'}
                      onClick={() => setYt((y) => (y.title = t))}
                    />
                    <Typography variant="caption" color={tooLong.length ? 'warning.main' : 'text.secondary'}>
                      {t.length} 字{tooLong.length ? `，${tooLong.join('、')}放不下` : ''}
                    </Typography>
                  </Box>
                )
              })}
              {s.titles.length === 0 && (
                <Typography variant="body2" color="text.secondary">
                  这一组标题都带了旁白里没有的数字，全去掉了——再写一组试试。
                </Typography>
              )}
              {s.dropped.length > 0 && (
                <Typography variant="caption" color="text.secondary">
                  去掉了 {s.dropped.length} 个带旁白里没有的数字的标题。
                </Typography>
              )}
            </Box>
            {s.description && (
              <Box>
                <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap' }}>
                  {s.description}
                </Typography>
                <Button size="small" onClick={() => setYt((y) => (y.description = s.description))}>
                  {yt.description ? '用这段替换现在的简介' : '用这段简介'}
                </Button>
              </Box>
            )}
            {s.tags.length > 0 && (
              <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                {s.tags.map((t) => (
                  <Chip key={t} size="small" label={`#${t}`} />
                ))}
                <Button size="small" onClick={() => setYt((y) => (y.tags = s.tags))}>
                  {yt.tags?.length ? '用这些替换现在的标签' : '用这些话题'}
                </Button>
              </Stack>
            )}
          </Stack>
        )}
      </CardContent>
    </Card>
  )
}
