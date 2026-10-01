import { useEffect, useState } from 'react'
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
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
import { ApiError, apiGet, apiPost } from '../../../api/client'
import type { StructureIssue, StructureRow, StructureTemplate } from '../../../api/types'
import { useProject } from '../../../state/ProjectContext'

/**
 * 结构模板 + 留存体检. Retention is decided here, before a word is written: where the promise lands,
 * what is on screen at 0:30, how long a segment is allowed to run. The skeleton goes into the AI
 * prompt (the panel above), and the same rules are run back over whatever script ends up in the
 * project — so the check also works on a script that was written by hand or pasted in.
 */
export function StructurePanel({
  template,
  onTemplate,
}: {
  template: string
  onTemplate: (v: string) => void
}) {
  const { raw, reload } = useProject()
  const [templates, setTemplates] = useState<StructureTemplate[]>([])
  const [rows, setRows] = useState<StructureRow[]>([])
  const [issues, setIssues] = useState<StructureIssue[] | null>(null)
  const [measured, setMeasured] = useState(false)
  const [status, setStatus] = useState('')
  const minutes = raw?.target_minutes || 10

  useEffect(() => {
    apiGet<{ templates: StructureTemplate[] }>('/api/structure/templates')
      .then((j) => setTemplates(j.templates))
      .catch(() => setTemplates([]))
  }, [])

  useEffect(() => {
    if (!template) return setRows([])
    apiGet<{ rows: StructureRow[] }>(`/api/structure/outline?template=${template}&minutes=${minutes}`)
      .then((j) => setRows(j.rows))
      .catch(() => setRows([]))
  }, [template, minutes])

  if (!raw) return null
  const zh = (raw.language || 'en').startsWith('zh')

  const runCheck = async () => {
    setStatus('')
    try {
      const j = await apiGet<{ issues: StructureIssue[]; measured: boolean }>('/api/structure/check')
      setIssues(j.issues)
      setMeasured(j.measured)
    } catch (e) {
      setStatus(e instanceof Error ? e.message : String(e))
    }
  }

  // Writing the beats in as empty segments: useful when writing by hand, destructive otherwise,
  // so an existing script has to be confirmed (the backend refuses the first, unflagged call).
  const applySkeleton = async (replace = false) => {
    setStatus('')
    try {
      const j = await apiPost<{ segments: unknown[] }>('/api/structure/apply', { template, minutes, replace })
      await reload()
      setStatus(`已写入 ${j.segments.length} 个空段落，按每段的章节名和提示往里填。`)
      setIssues(null)
    } catch (e) {
      if (e instanceof ApiError && e.data.has_segments) {
        setStatus(`${e.message}（现有 ${raw.segments.length} 段会被清空）`)
        return
      }
      setStatus(e instanceof Error ? e.message : String(e))
    }
  }

  const problems = (issues || []).filter((i) => i.level === 'problem')

  return (
    <Accordion defaultExpanded={!raw.segments.length}>
      <AccordionSummary expandIcon={<ExpandMoreIcon />}>
        <Typography variant="subtitle1">
          🦴 段落骨架与留存体检
          {issues && (
            <Chip
              size="small"
              sx={{ ml: 1 }}
              color={problems.length ? 'warning' : 'success'}
              label={problems.length ? `${problems.length} 个要改` : '没发现问题'}
            />
          )}
        </Typography>
      </AccordionSummary>
      <AccordionDetails>
        <Stack spacing={1.5}>
          <Typography variant="body2" color="text.secondary">
            完播率是在这里决定的，不在后期：问题要在前 15 秒落地，25–35 秒是流失最高的位置，
            一个段落不要超过 45 秒（画面跟着段落换）。选一个骨架，上面生成脚本时会按它来写。
          </Typography>
          <Stack direction="row" spacing={1.5} alignItems="center" flexWrap="wrap" useFlexGap>
            <TextField
              size="small"
              select
              label="结构骨架"
              value={template}
              onChange={(e) => onTemplate(e.target.value)}
              sx={{ minWidth: 300 }}
            >
              <MenuItem value="">不用骨架（AI 自己分段）</MenuItem>
              {templates.map((t) => (
                <MenuItem key={t.id} value={t.id}>
                  {t.name}
                </MenuItem>
              ))}
            </TextField>
            <Button size="small" onClick={runCheck}>
              给现在的脚本做留存体检
            </Button>
            {template && (
              <Button size="small" onClick={() => applySkeleton(false)}>
                写成空段落（自己手写时用）
              </Button>
            )}
            {status.includes('已经有段落') && (
              <Button size="small" color="warning" onClick={() => applySkeleton(true)}>
                确认覆盖
              </Button>
            )}
          </Stack>
          {template && (
            <Typography variant="caption" color="text.secondary">
              {templates.find((t) => t.id === template)?.about}
            </Typography>
          )}
          {!!rows.length && (
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>块</TableCell>
                  <TableCell align="right">时长</TableCell>
                  <TableCell align="right">{zh ? '字数' : 'words'}</TableCell>
                  <TableCell align="right">段数</TableCell>
                  <TableCell>要做到什么</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {rows.map((r) => (
                  <TableRow key={r.id}>
                    <TableCell sx={{ whiteSpace: 'nowrap' }}>{r.label}</TableCell>
                    <TableCell align="right">{r.seconds}s</TableCell>
                    <TableCell align="right">{zh ? r.zh_words : r.en_words}</TableCell>
                    <TableCell align="right">{r.segments}</TableCell>
                    <TableCell sx={{ fontSize: 12, color: 'text.secondary' }}>{r.role}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
          {status && <Alert severity="info">{status}</Alert>}
          {issues && !issues.length && (
            <Alert severity="success">结构上没发现问题{measured ? '（按渲染出来的真实时长算）' : '（按字数估的时长）'}。</Alert>
          )}
          {!!issues?.length && (
            <Stack spacing={1}>
              <Typography variant="caption" color="text.secondary">
                {measured ? '按渲染出来的真实段落时长算。' : '还没渲染过，时长是按字数估的——渲染一次后再体检会更准。'}
              </Typography>
              {issues.map((i, n) => (
                <Alert key={n} severity={i.level === 'problem' ? 'warning' : 'info'}>
                  <Box sx={{ fontWeight: 500 }}>
                    {i.where ? `${i.where}：` : ''}
                    {i.what}
                  </Box>
                  <Box sx={{ fontSize: 13, color: 'text.secondary' }}>→ {i.fix}</Box>
                </Alert>
              ))}
            </Stack>
          )}
        </Stack>
      </AccordionDetails>
    </Accordion>
  )
}
