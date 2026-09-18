import { useState } from 'react'
import {
  Box,
  Button,
  Card,
  CardContent,
  Checkbox,
  FormControlLabel,
  Link,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from '@mui/material'
import { apiPost } from '../../api/client'
import type { RawProject } from '../../api/types'
import { useProject } from '../../state/ProjectContext'

const CATEGORIES = [
  [27, 'Education'],
  [28, 'Science & Technology'],
  [22, 'People & Blogs'],
  [24, 'Entertainment'],
  [25, 'News & Politics'],
] as const

const PRIVACY = ['private', 'unlisted', 'public']

function chaptersText(tl: { start: number; label?: string; id: string }[] | null | undefined) {
  return (tl || [])
    .map((t) => {
      const s = Math.floor(t.start)
      return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')} ${t.label || t.id}`
    })
    .join('\n')
}

export function PublishStep() {
  const { raw, view, patch, saveNow, reload } = useProject()
  const [uploading, setUploading] = useState(false)
  const [log, setLog] = useState<string | null>(null)

  if (!raw) return null
  const o = view?.outputs
  const yt = raw.youtube || {}
  const disclosure = yt.disclosure || { ai_voice: true }
  const presenterProvider = (raw.presenter as { provider?: string } | undefined)?.provider
  const synthFlag = disclosure.realistic_presenter || disclosure.ai_visuals || presenterProvider === 'heygen'

  const setYt = (fn: (y: NonNullable<RawProject['youtube']>) => void) =>
    patch((r) => {
      r.youtube = r.youtube || {}
      fn(r.youtube)
    })
  const setDisclosure = (fn: (d: NonNullable<RawProject['youtube']>['disclosure']) => void) =>
    setYt((y) => {
      y.disclosure = y.disclosure || { ai_voice: true }
      fn(y.disclosure)
    })

  const upload = async () => {
    if (!(await saveNow())) return
    setUploading(true)
    setLog('上传中…（第一次会打开浏览器要求授权）')
    try {
      const j = await apiPost<{ lines?: string[] }>('/api/upload', {})
      setLog((j.lines || []).join('\n'))
      await reload()
    } catch (e) {
      setLog('ERROR: ' + (e instanceof Error ? e.message : String(e)))
    }
    setUploading(false)
  }

  return (
    <Stack spacing={2}>
      <Card variant="outlined">
        <CardContent>
          <Stack direction="row" spacing={2} flexWrap="wrap" useFlexGap>
            <TextField
              size="small"
              label="YouTube 标题（默认用视频标题）"
              value={yt.title || ''}
              onChange={(e) => setYt((y) => (y.title = e.target.value || undefined))}
              placeholder={raw.title || ''}
              sx={{ minWidth: 280, flexGrow: 1 }}
            />
            <TextField
              size="small"
              label="标签（逗号分隔）"
              value={(yt.tags || []).join(', ')}
              onChange={(e) =>
                setYt((y) => {
                  y.tags = e.target.value
                    .split(',')
                    .map((s) => s.trim())
                    .filter(Boolean)
                })
              }
              sx={{ minWidth: 240 }}
            />
            <TextField
              select
              size="small"
              label="可见性"
              value={yt.privacy || 'private'}
              onChange={(e) => setYt((y) => (y.privacy = e.target.value))}
              sx={{ width: 160 }}
            >
              {PRIVACY.map((p) => (
                <MenuItem key={p} value={p}>
                  {p}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              select
              size="small"
              label="分类"
              value={yt.category_id ?? 27}
              onChange={(e) => setYt((y) => (y.category_id = +e.target.value))}
              sx={{ width: 220 }}
            >
              {CATEGORIES.map(([n, l]) => (
                <MenuItem key={n} value={n}>
                  {l}
                </MenuItem>
              ))}
            </TextField>
          </Stack>

          <Box sx={{ mt: 1.5 }}>
            <Typography variant="caption" fontWeight={600}>
              AI 使用声明
            </Typography>
            <Stack direction="row" spacing={2} alignItems="center" flexWrap="wrap" useFlexGap>
              <FormControlLabel
                control={<Checkbox checked={disclosure.ai_voice ?? true} onChange={(e) => setDisclosure((d) => (d!.ai_voice = e.target.checked))} />}
                label="AI 配音"
              />
              <FormControlLabel
                control={<Checkbox checked={!!disclosure.ai_visuals} onChange={(e) => setDisclosure((d) => (d!.ai_visuals = e.target.checked))} />}
                label="AI 生成画面"
              />
              <FormControlLabel
                disabled={presenterProvider === 'heygen'}
                control={
                  <Checkbox
                    checked={!!disclosure.realistic_presenter || presenterProvider === 'heygen'}
                    onChange={(e) => setDisclosure((d) => (d!.realistic_presenter = e.target.checked))}
                  />
                }
                label="逼真合成主持人/换脸"
              />
              <Typography variant="caption" color="text.secondary">
                {synthFlag
                  ? 'YouTube「合成内容」标签：会自动勾选（含逼真合成人物/画面）。'
                  : 'YouTube「合成内容」标签：不需要（纯 AI 配音的解说不在披露范围）。国内平台：简介会附"本视频包含人工智能生成内容"。'}
              </Typography>
            </Stack>
          </Box>

          <TextField
            label="简介（章节、素材署名和 AI 声明会自动追加在后面）"
            value={yt.description || ''}
            onChange={(e) => setYt((y) => (y.description = e.target.value))}
            multiline
            minRows={6}
            fullWidth
            sx={{ mt: 1.5 }}
          />
          <Box component="pre" sx={{ fontSize: 12, mt: 1, color: 'text.secondary' }}>
            {chaptersText(o?.timeline)}
            {'\n\n'}
            {o?.credits || ''}
          </Box>

          <Stack direction="row" spacing={2} alignItems="center" sx={{ mt: 1.5 }}>
            <Button variant="contained" onClick={upload} disabled={!o?.final || uploading}>
              ⬆ 上传到 YouTube（{yt.privacy || 'private'}）
            </Button>
            {o?.youtube?.url && (
              <Typography variant="body2" color="success.main">
                已上传：
                <Link href={o.youtube.url} target="_blank" rel="noreferrer">
                  {o.youtube.url}
                </Link>
                （再点会更新元数据）
              </Typography>
            )}
            {!o?.final && (
              <Typography variant="caption" color="text.secondary">
                先完成第 4 步渲染
              </Typography>
            )}
          </Stack>
          {log && (
            <Box component="pre" sx={{ mt: 1, fontSize: 12, bgcolor: 'action.hover', p: 1, borderRadius: 1, whiteSpace: 'pre-wrap' }}>
              {log}
            </Box>
          )}
        </CardContent>
      </Card>
    </Stack>
  )
}
