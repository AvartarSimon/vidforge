import { useEffect, useState } from 'react'
import { Alert, Box, Button, Card, CardContent, Chip, Stack, Typography } from '@mui/material'
import VideoFileIcon from '@mui/icons-material/VideoFile'
import { apiGet, apiPost } from '../../../api/client'
import { useProject } from '../../../state/ProjectContext'
import { fileUrl } from '../../../utils'
import { PanelTitle } from '../../shared/ui'

type Take = { path: string; name: string; seconds: number | null; mb: number; time: string; video: boolean; used_by: string[]; source_of?: string }

/**
 * 这个项目录过的视频: every recording in the project, newest first, with the segments using it.
 * Nothing recorded is ever deleted, so a take the project lost track of is one click from coming
 * back — as the segment's picture, as its small window, or only as its voice.
 */
export function TakesLibrary({ segId, refreshKey }: { segId: string; refreshKey?: number }) {
  const { reload, saveNow } = useProject()
  const [takes, setTakes] = useState<Take[] | null>(null)
  const [open, setOpen] = useState<string | null>(null)
  const [msg, setMsg] = useState('')
  const [error, setError] = useState<string | null>(null)

  const load = () =>
    apiGet<{ takes: Take[] }>('/api/takes')
      .then((j) => setTakes(j.takes))
      .catch((e) => setError(String(e)))
  useEffect(() => {
    load()
  }, [refreshKey])

  const use = async (t: Take, as: 'visual' | 'window' | 'narration') => {
    setError(null)
    try {
      if (!(await saveNow())) return
      await apiPost('/api/takes/use', { path: t.path, segment: segId, as })
      await reload()
      await load()
      setMsg(`已放进 ${segId}：${as === 'visual' ? '全屏画面 + 旁白' : as === 'window' ? '小窗 + 旁白' : '旁白'}`)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  if (!takes?.length) return null
  const unused = takes.filter((t) => !t.used_by.length && !t.source_of).length

  return (
    <Card>
      <CardContent>
        <PanelTitle
          icon={<VideoFileIcon />}
          tone="coral"
          title={`这个项目录过的视频（${takes.length}）`}
          sub={`录过的都留在项目里，不会删。${unused ? `有 ${unused} 条没被任何段落用上——` : ''}点一条可以放进当前段（${segId}）。`}
        />
        <Stack spacing={1}>
          {takes.map((t) => (
            <Box key={t.path} sx={{ border: '1px solid', borderColor: 'divider', borderRadius: 2, p: 1 }}>
              <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                <Button size="small" onClick={() => setOpen(open === t.path ? null : t.path)}>
                  {open === t.path ? '收起' : t.video ? '看' : '听'}
                </Button>
                <Typography variant="body2" sx={{ fontWeight: 600 }}>
                  {t.time}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  {t.video ? '录像' : '录音'} · {t.seconds != null ? `${t.seconds}s` : '?'} · {t.mb} MB · {t.name}
                </Typography>
                {t.used_by.length ? (
                  t.used_by.map((s) => <Chip key={s} size="small" color="success" variant="outlined" label={`用在 ${s}`} />)
                ) : t.source_of ? (
                  <Chip size="small" variant="outlined" label="原始文件" title={`剪好的是 ${t.source_of}`} />
                ) : (
                  <Chip size="small" color="warning" variant="outlined" label="没被用上" />
                )}
                <Box sx={{ flex: 1 }} />
                {t.video && (
                  <>
                    <Button size="small" onClick={() => use(t, 'visual')}>
                      当全屏画面
                    </Button>
                    <Button size="small" onClick={() => use(t, 'window')}>
                      当小窗
                    </Button>
                  </>
                )}
                <Button size="small" onClick={() => use(t, 'narration')}>
                  只当旁白
                </Button>
              </Stack>
              {open === t.path && (
                <Box component={t.video ? 'video' : 'audio'} src={fileUrl(t.path) || ''} controls sx={{ width: t.video ? 360 : '100%', maxWidth: '100%', mt: 1, borderRadius: 1 }} />
              )}
            </Box>
          ))}
        </Stack>
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
