import { useEffect, useMemo, useState } from 'react'
import { Alert, Box, Card, CardContent, Chip, MenuItem, Select, Stack, TextField, Typography } from '@mui/material'
import { apiGet } from '../../api/client'
import { fileUrl } from '../../utils'

type Asset = {
  path: string
  kind: string
  provider: string
  title: string
  author: string
  license: string
  page_url: string
  width?: number
  height?: number
  warning: string | null
  used_by: string[]
  exists: boolean
}

// One place to see everything this project has downloaded: what it is, whether it may be used,
// whether the vision check flagged it, and which segments it appears in.
export function ImagesSection() {
  const [items, setItems] = useState<Asset[]>([])
  const [root, setRoot] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [filter, setFilter] = useState('')
  const [show, setShow] = useState<'all' | 'unused' | 'warned'>('all')

  useEffect(() => {
    apiGet<{ items: Asset[]; root: string }>('/api/assets/library')
      .then((j) => {
        setItems(j.items)
        setRoot(j.root)
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
  }, [])

  const shown = useMemo(() => {
    const q = filter.trim().toLowerCase()
    return items.filter((i) => {
      if (show === 'unused' && i.used_by.length) return false
      if (show === 'warned' && !i.warning) return false
      if (!q) return true
      return `${i.title} ${i.author} ${i.provider} ${i.path}`.toLowerCase().includes(q)
    })
  }, [items, filter, show])

  const warned = items.filter((i) => i.warning).length
  const unused = items.filter((i) => !i.used_by.length).length

  return (
    <Stack spacing={2}>
      <Typography variant="h6">图片</Typography>
      <Typography variant="body2" color="text.secondary">
        这个项目下载过的全部素材（<code>{root}</code>），包含授权、出处、视觉核对结果和被哪些段落用到。
        删除文件请直接在资源管理器里操作——没有被任何段落引用的可以安全删掉。
      </Typography>

      <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
        <TextField size="small" label="搜索标题/作者/来源" value={filter} onChange={(e) => setFilter(e.target.value)} sx={{ minWidth: 260 }} />
        <Select size="small" value={show} onChange={(e) => setShow(e.target.value as typeof show)}>
          <MenuItem value="all">全部（{items.length}）</MenuItem>
          <MenuItem value="unused">没被用到（{unused}）</MenuItem>
          <MenuItem value="warned">有水印/标注警告（{warned}）</MenuItem>
        </Select>
      </Stack>

      {error && <Alert severity="error">{error}</Alert>}

      <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))', gap: 1.5 }}>
        {shown.map((i) => (
          <Card key={i.path} variant="outlined">
            <Box
              sx={{
                height: 140,
                bgcolor: 'action.hover',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                overflow: 'hidden',
              }}
            >
              {i.exists && i.kind === 'image' ? (
                <Box component="img" src={fileUrl(i.path) || undefined} alt="" sx={{ width: '100%', height: '100%', objectFit: 'cover' }} />
              ) : (
                <Typography variant="caption" color="text.secondary">
                  {i.exists ? '视频' : '文件已不在'}
                </Typography>
              )}
            </Box>
            <CardContent sx={{ py: 1.25 }}>
              <Typography variant="caption" fontWeight={600} noWrap sx={{ display: 'block' }} title={i.title}>
                {i.title || i.path.split('/').pop()}
              </Typography>
              <Typography variant="caption" color="text.secondary" noWrap sx={{ display: 'block' }}>
                {i.provider} · {i.license || '授权未知'}
              </Typography>
              <Typography variant="caption" color="text.secondary" noWrap sx={{ display: 'block' }}>
                {i.author || '—'} {i.width ? `· ${i.width}×${i.height}` : ''}
              </Typography>
              <Stack direction="row" spacing={0.5} sx={{ mt: 0.5 }} flexWrap="wrap" useFlexGap>
                {i.warning && <Chip size="small" color="warning" label={i.warning} />}
                {i.used_by.length ? (
                  <Chip size="small" variant="outlined" label={`用于 ${i.used_by.join('、')}`} />
                ) : (
                  <Chip size="small" variant="outlined" color="default" label="未使用" />
                )}
                {i.page_url && (
                  <Chip
                    size="small"
                    variant="outlined"
                    label="出处"
                    component="a"
                    href={i.page_url}
                    target="_blank"
                    clickable
                  />
                )}
              </Stack>
            </CardContent>
          </Card>
        ))}
      </Box>
      {!shown.length && !error && (
        <Typography variant="body2" color="text.secondary">
          没有符合条件的素材。
        </Typography>
      )}
    </Stack>
  )
}
