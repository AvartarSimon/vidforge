import { useState } from 'react'
import { Box, Button, Stack, Typography } from '@mui/material'
import { apiPost } from '../../../api/client'
import { useProject } from '../../../state/ProjectContext'
import { fileUrl, fmtDuration } from '../../../utils'

export function Storyboard({ selId, onSelect }: { selId: string | null; onSelect: (id: string) => void }) {
  const { raw, view, reload, saveNow } = useProject()
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<string | null>(null)

  if (!raw) return null
  const segments = raw.segments
  const resolved = view?.resolved || {}

  const autofill = async () => {
    if (!(await saveNow())) return
    setBusy(true)
    try {
      const j = await apiPost<{ filled: number; source: string }>('/api/autofill', {})
      setMsg(`已为 ${j.filled} 段生成 ${j.source} 搜索片段，渲染时自动取第一张；不满意的段点开重选。`)
      await reload()
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e))
    }
    setBusy(false)
  }

  return (
    <Stack spacing={1}>
      <Button size="small" onClick={autofill} disabled={busy} sx={{ alignSelf: 'flex-start' }}>
        ✨ 没画面的段一键自动配图
      </Button>
      {msg && (
        <Typography variant="caption" color="text.secondary">
          {msg}
        </Typography>
      )}
      <Stack spacing={1} sx={{ maxHeight: '75vh', overflowY: 'auto', pr: 0.5 }}>
        {segments.map((s) => {
          const r = resolved[s.id] || {}
          const c0 = s.clips[0]
          const p0 = r.clips?.[0]?.path
          const thumb = !c0
            ? '缺'
            : c0.me
              ? '🎥'
              : c0.remotion
                ? c0.remotion.composition
                : p0
                  ? r.clips?.[0]?.kind === 'video'
                    ? { poster: `/api/poster/${encodeURIComponent(s.id)}/0` }
                    : { img: fileUrl(p0) }
                  : '自动'
          return (
            <Box
              key={s.id}
              onClick={() => onSelect(s.id)}
              sx={{
                display: 'flex',
                gap: 1,
                p: 1,
                border: '2px solid',
                borderColor: s.id === selId ? 'primary.main' : 'divider',
                borderRadius: 2,
                cursor: 'pointer',
                bgcolor: s.id === selId ? 'action.selected' : 'transparent',
              }}
            >
              <Box
                sx={{
                  width: 64,
                  height: 40,
                  flexShrink: 0,
                  bgcolor: 'action.hover',
                  borderRadius: 1,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: 11,
                  overflow: 'hidden',
                  color: !c0 ? 'error.main' : 'text.secondary',
                }}
              >
                {typeof thumb === 'string' ? (
                  thumb
                ) : 'img' in thumb ? (
                  <img src={thumb.img || undefined} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                ) : (
                  <img src={thumb.poster} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                )}
              </Box>
              <Box sx={{ minWidth: 0, flexGrow: 1 }}>
                <Typography variant="caption" fontWeight={600}>
                  {s.id} <span style={{ color: 'inherit', opacity: 0.6 }}>{fmtDuration(r.need)}</span>
                </Typography>
                <Typography variant="caption" color="text.secondary" noWrap sx={{ display: 'block' }}>
                  {s.text || s.label}
                </Typography>
                <Typography variant="caption" color={s.clips.length ? 'text.secondary' : 'error.main'} sx={{ display: 'block' }}>
                  {s.clips.length ? `${s.clips.length} 个片段` : '● 需要画面'}
                </Typography>
              </Box>
            </Box>
          )
        })}
      </Stack>
    </Stack>
  )
}
