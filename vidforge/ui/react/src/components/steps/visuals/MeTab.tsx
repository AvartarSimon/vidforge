import { useEffect, useRef, useState } from 'react'
import { Box, Button, Checkbox, FormControlLabel, MenuItem, Stack, TextField, Typography } from '@mui/material'
import { apiGet, apiPost } from '../../../api/client'
import type { MeItem } from '../../../api/types'
import { useProject } from '../../../state/ProjectContext'
import { fmtDuration } from '../../../utils'

function readAsBase64(f: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const rd = new FileReader()
    rd.onload = () => resolve((rd.result as string).split(',')[1])
    rd.onerror = reject
    rd.readAsDataURL(f)
  })
}

// personal footage library ("我的镜头"): your own takes, tagged by file name; add by tag so the
// least-used matching take is auto-picked at render time — every video looks freshly recorded.
export function MeTab({ segId, onAdded }: { segId: string; onAdded: () => void }) {
  const { patch, saveNow } = useProject()
  const [folder, setFolder] = useState('')
  const [items, setItems] = useState<MeItem[]>([])
  const [allTags, setAllTags] = useState<string[]>([])
  const [tagFilter, setTagFilter] = useState('')
  const [talkFilter, setTalkFilter] = useState<'any' | 'true' | 'false'>('any')
  const [talkingForAdd, setTalkingForAdd] = useState(false)
  const [loading, setLoading] = useState(true)
  const fileRef = useRef<HTMLInputElement>(null)

  const load = (scan = false) => {
    setLoading(true)
    apiGet<{ folder: string; items: MeItem[]; tags: string[] }>(`/api/me${scan ? '?scan=1' : ''}`)
      .then((j) => {
        setFolder(j.folder)
        setItems(j.items)
        setAllTags(j.tags)
      })
      .finally(() => setLoading(false))
  }

  useEffect(load, [])

  const filtered = items.filter(
    (i) => (!tagFilter || (i.tags || []).includes(tagFilter)) && (talkFilter === 'any' || String(!!i.talking) === talkFilter),
  )

  const addMain = () => {
    patch((raw) => {
      const s = raw.segments.find((x) => x.id === segId)
      if (s) s.clips.push({ me: { tags: tagFilter ? [tagFilter] : [], talking: talkingForAdd } })
    })
    saveNow().then((ok) => ok && onAdded())
  }
  const addPip = () => {
    patch((raw) => {
      const s = raw.segments.find((x) => x.id === segId)
      if (!s) return
      s.overlays = s.overlays || []
      s.overlays.push({ me: { tags: tagFilter ? [tagFilter] : [], talking: talkingForAdd }, position: 'bottom-right', size: 0.3, animate: 'fade' })
    })
    saveNow().then((ok) => ok && onAdded())
  }

  const upload = async (f: File) => {
    const tags = window.prompt(`「${f.name}」的标签（逗号分隔，例：backyard, glasses；文件名里的词已自动算标签）`, '') ?? ''
    const talking = window.confirm('这是"说话"镜头吗？（确定 = 说话，取消 = 沉默 B-roll）')
    const b64 = await readAsBase64(f)
    try {
      const j = await apiPost<{ items: MeItem[] }>('/api/me/upload', { name: f.name, data_b64: b64, tags, talking })
      setItems(j.items)
      setAllTags([...new Set(j.items.flatMap((i) => i.tags || []))].sort())
    } catch (e) {
      window.alert(e instanceof Error ? e.message : String(e))
    }
  }

  const retag = async (item: MeItem) => {
    const t = window.prompt('改标签（逗号分隔）', (item.tags || []).join(', '))
    if (t === null) return
    const j = await apiPost<{ items: MeItem[] }>('/api/me/tags', {
      name: item.name,
      tags: t.split(/[,，]/).map((x) => x.trim()).filter(Boolean),
    })
    setItems(j.items)
    setAllTags([...new Set(j.items.flatMap((i) => i.tags || []))].sort())
  }

  if (loading) return <Typography color="text.secondary">读取素材库…</Typography>

  return (
    <Stack spacing={1.5}>
      <Typography variant="caption" color="text.secondary">
        素材库：<code>{folder}</code>（所有项目共用）。文件名就是标签；含 talking/说话 的是说话镜头。加入时选标签而不是具体文件，渲染时自动挑用得最少的匹配镜头。
      </Typography>
      <Stack direction="row" spacing={1} alignItems="center">
        <TextField select size="small" label="标签" value={tagFilter} onChange={(e) => setTagFilter(e.target.value)} sx={{ minWidth: 160 }}>
          <MenuItem value="">全部标签</MenuItem>
          {allTags.map((t) => (
            <MenuItem key={t} value={t}>
              {t}
            </MenuItem>
          ))}
        </TextField>
        <TextField
          select
          size="small"
          label="镜头类型"
          value={talkFilter}
          onChange={(e) => setTalkFilter(e.target.value as typeof talkFilter)}
          sx={{ minWidth: 180 }}
        >
          <MenuItem value="any">沉默+说话</MenuItem>
          <MenuItem value="false">沉默镜头（推荐，零风险）</MenuItem>
          <MenuItem value="true">说话镜头（需口型同步）</MenuItem>
        </TextField>
        <Button size="small" onClick={() => load(true)}>
          重新扫描
        </Button>
        <Button size="small" onClick={() => fileRef.current?.click()}>
          上传镜头…
        </Button>
        <input ref={fileRef} type="file" hidden accept="video/*" multiple onChange={(e) => e.target.files && Array.from(e.target.files).forEach(upload)} />
        <Typography variant="caption" color="text.secondary">
          {filtered.length} 个
        </Typography>
      </Stack>
      <Stack direction="row" spacing={1} alignItems="center">
        <Button variant="contained" size="small" onClick={addMain}>
          ＋ 作为本段主画面（按当前标签筛选）
        </Button>
        <Button size="small" onClick={addPip}>
          ＋ 作为画中画
        </Button>
        <FormControlLabel
          control={<Checkbox checked={talkingForAdd} onChange={(e) => setTalkingForAdd(e.target.checked)} />}
          label="说话镜头（口型同步）"
        />
      </Stack>
      <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))', gap: 1 }}>
        {filtered.map((it) => (
          <Box
            key={it.name}
            onClick={() => retag(it)}
            sx={{ cursor: 'pointer', border: '1px solid', borderColor: 'divider', borderRadius: 2, overflow: 'hidden' }}
          >
            <Box sx={{ height: 90, bgcolor: 'action.hover' }}>
              <img src={`/api/me/poster/${encodeURIComponent(it.name)}`} alt="" loading="lazy" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
            </Box>
            <Stack sx={{ px: 0.5 }}>
              <Typography variant="caption" noWrap title={it.name}>
                {(it.tags || []).join(' · ') || it.name}
                {it.talking ? ' 🗣' : ''}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                {it.duration ? fmtDuration(it.duration) : ''} · 用过 {it.uses || 0}
              </Typography>
            </Stack>
          </Box>
        ))}
        {!filtered.length && (
          <Typography variant="body2" color="text.secondary">
            还没有镜头。录一批各场景的你：书房、后院、海边……每段 30–60 秒，沉默镜头为主。
          </Typography>
        )}
      </Box>
    </Stack>
  )
}
