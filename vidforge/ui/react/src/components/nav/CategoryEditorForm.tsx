import { useState } from 'react'
import {
  Autocomplete,
  Box,
  Button,
  Checkbox,
  Chip,
  Divider,
  FormControlLabel,
  IconButton,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from '@mui/material'
import AddIcon from '@mui/icons-material/Add'
import DeleteIcon from '@mui/icons-material/Delete'
import type { Category, CategorySource } from '../../api/types'

const PLATFORM_OPTIONS = ['YouTube', 'B站', '抖音', '头条', '西瓜', 'TikTok', 'Instagram']
const TTS_PROVIDERS = ['edge', 'elevenlabs', 'voxcpm', 'silent']
const LANGUAGES = [
  { value: 'en', label: '英文' },
  { value: 'zh', label: '中文' },
]

function ChipListField({
  label,
  value,
  onChange,
  options,
  hint,
}: {
  label: string
  value: string[]
  onChange: (v: string[]) => void
  options?: string[]
  hint?: string
}) {
  return (
    <Autocomplete
      multiple
      freeSolo
      size="small"
      options={options || []}
      value={value}
      onChange={(_, v) => onChange(v as string[])}
      renderTags={(tags, getTagProps) =>
        tags.map((tag, i) => {
          const { key, ...rest } = getTagProps({ index: i })
          return <Chip key={key} label={tag} size="small" {...rest} />
        })
      }
      renderInput={(params) => <TextField {...params} label={label} placeholder="回车添加" helperText={hint} />}
    />
  )
}

function SourcesEditor({ value, onChange }: { value: CategorySource[]; onChange: (v: CategorySource[]) => void }) {
  const update = (i: number, key: keyof CategorySource, v: string) => {
    const next = value.slice()
    next[i] = { ...next[i], [key]: v }
    onChange(next)
  }
  return (
    <Box>
      <Typography variant="caption" color="text.secondary">
        参考资料源
      </Typography>
      <Stack spacing={1} sx={{ mt: 0.5 }}>
        {value.map((s, i) => (
          <Stack key={i} direction="row" spacing={1}>
            <TextField size="small" placeholder="名字" value={s.name || ''} onChange={(e) => update(i, 'name', e.target.value)} sx={{ width: 180 }} />
            <TextField
              size="small"
              placeholder="链接（可选）"
              value={s.url || ''}
              onChange={(e) => update(i, 'url', e.target.value)}
              fullWidth
            />
            <IconButton size="small" onClick={() => onChange(value.filter((_, idx) => idx !== i))}>
              <DeleteIcon fontSize="small" />
            </IconButton>
          </Stack>
        ))}
        <Button size="small" startIcon={<AddIcon />} onClick={() => onChange([...value, { name: '', url: '' }])} sx={{ alignSelf: 'flex-start' }}>
          加一条
        </Button>
      </Stack>
    </Box>
  )
}

export function CategoryEditorForm({
  initial,
  onCancel,
  onSave,
}: {
  initial: Category | null // null = new
  onCancel: () => void
  onSave: (rec: Category) => Promise<void>
}) {
  const [rec, setRec] = useState<Category>(
    initial || { id: '', name: '', platforms: [], tags: [], sources: [], banned_keywords: [], defaults: {} },
  )
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  const patch = (fn: (r: Category) => void) => setRec((r) => { const n = { ...r }; fn(n); return n })

  const save = async () => {
    if (!rec.name.trim()) {
      setError('需要一个名字')
      return
    }
    setSaving(true)
    setError(null)
    try {
      await onSave(rec)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
    setSaving(false)
  }

  return (
    <Stack spacing={2}>
      <TextField
        label="名字"
        size="small"
        value={rec.name}
        onChange={(e) => patch((r) => (r.name = e.target.value))}
        placeholder="例：中国古代历史人文 / FND"
      />
      <TextField
        label="定位 / 要讲什么"
        multiline
        minRows={2}
        value={rec.topic_notes || ''}
        onChange={(e) => patch((r) => (r.topic_notes = e.target.value))}
      />
      <TextField
        label="心得（写脚本/发布时的经验）"
        multiline
        minRows={2}
        value={rec.insights || ''}
        onChange={(e) => patch((r) => (r.insights = e.target.value))}
      />
      <ChipListField label="发布平台" value={rec.platforms || []} options={PLATFORM_OPTIONS} onChange={(v) => patch((r) => (r.platforms = v))} />
      <ChipListField label="标签" value={rec.tags || []} onChange={(v) => patch((r) => (r.tags = v))} />
      <SourcesEditor value={rec.sources || []} onChange={(v) => patch((r) => (r.sources = v))} />
      <ChipListField
        label="禁用关键词"
        value={rec.banned_keywords || []}
        onChange={(v) => patch((r) => (r.banned_keywords = v))}
        hint="涉及时会在生成脚本的提示词里提醒 AI 换种说法"
      />
      <TextField
        label="平台限制 / 把关规则"
        multiline
        minRows={2}
        value={rec.platform_restrictions || ''}
        onChange={(e) => patch((r) => (r.platform_restrictions = e.target.value))}
      />

      <Divider />
      <Typography variant="subtitle2">新建项目时的默认设置</Typography>
      <Stack direction="row" spacing={2} flexWrap="wrap" useFlexGap>
        <TextField
          size="small"
          label="默认声音"
          value={rec.defaults?.voice || ''}
          onChange={(e) => patch((r) => (r.defaults = { ...r.defaults, voice: e.target.value }))}
          sx={{ minWidth: 200 }}
        />
        <TextField
          size="small"
          select
          label="配音服务"
          value={rec.defaults?.tts_provider || 'edge'}
          onChange={(e) => patch((r) => (r.defaults = { ...r.defaults, tts_provider: e.target.value }))}
          sx={{ width: 160 }}
        >
          {TTS_PROVIDERS.map((p) => (
            <MenuItem key={p} value={p}>
              {p}
            </MenuItem>
          ))}
        </TextField>
        <TextField
          size="small"
          select
          label="语言"
          value={rec.defaults?.language || 'en'}
          onChange={(e) => patch((r) => (r.defaults = { ...r.defaults, language: e.target.value }))}
          sx={{ width: 140 }}
        >
          {LANGUAGES.map((l) => (
            <MenuItem key={l.value} value={l.value}>
              {l.label}
            </MenuItem>
          ))}
        </TextField>
        <TextField
          size="small"
          type="number"
          label="片尾词汇卡（词数）"
          value={rec.defaults?.outro_vocab ?? 0}
          onChange={(e) => patch((r) => (r.defaults = { ...r.defaults, outro_vocab: parseInt(e.target.value, 10) || 0 }))}
          sx={{ width: 160 }}
        />
        <FormControlLabel
          control={
            <Checkbox
              checked={!!rec.defaults?.subtitles_bilingual}
              onChange={(e) => patch((r) => (r.defaults = { ...r.defaults, subtitles_bilingual: e.target.checked }))}
            />
          }
          label="默认双语字幕"
        />
      </Stack>

      {error && (
        <Typography color="error" variant="body2">
          {error}
        </Typography>
      )}
      <Stack direction="row" spacing={1} justifyContent="flex-end">
        <Button onClick={onCancel}>取消</Button>
        <Button variant="contained" onClick={save} disabled={saving}>
          保存
        </Button>
      </Stack>
    </Stack>
  )
}
