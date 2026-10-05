import { useEffect, useState } from 'react'
import { Alert, AlertTitle, Box, Button, Stack } from '@mui/material'
import { apiGet } from '../../api/client'
import type { StructureIssue } from '../../api/types'
import { useProject } from '../../state/ProjectContext'

/**
 * 留存体检，自动跑。
 *
 * The hook rules are easy to agree with and easy to forget three weeks later, so they are not
 * behind a button: this runs itself wherever it is mounted, and says nothing when the script is
 * clean. The same `check()` also runs on every build (see pipeline._stage_retention), so the
 * decision to ship a 41-second opening can be made — but not by accident.
 */
export function RetentionBanner({ compact = false }: { compact?: boolean }) {
  const { raw } = useProject()
  const [issues, setIssues] = useState<StructureIssue[] | null>(null)
  const [open, setOpen] = useState(false)
  const count = raw?.segments.length ?? 0

  useEffect(() => {
    if (!count) return setIssues(null)
    apiGet<{ issues: StructureIssue[] }>('/api/structure/check')
      .then((j) => setIssues(j.issues))
      .catch(() => setIssues(null))
    // re-check whenever the script changes shape, which is when the answer can change
  }, [count, raw?.segments.map((s) => (s.text || '').length).join(',')])

  if (!issues?.length) return null
  const problems = issues.filter((i) => i.level === 'problem')
  const advice = issues.filter((i) => i.level !== 'problem')
  const shown = open ? issues : problems.length ? problems : issues.slice(0, 1)

  return (
    <Alert
      severity={problems.length ? 'warning' : 'info'}
      action={
        issues.length > shown.length || open ? (
          <Button size="small" color="inherit" onClick={() => setOpen((o) => !o)}>
            {open ? '收起' : `全部 ${issues.length} 条`}
          </Button>
        ) : undefined
      }
    >
      <AlertTitle sx={{ mb: 0.5 }}>
        留存体检：
        {problems.length ? `${problems.length} 个要改` : '没有硬问题'}
        {advice.length ? `，${advice.length} 个建议` : ''}
      </AlertTitle>
      <Stack spacing={0.5}>
        {shown.map((i, n) => (
          <Box key={n} sx={{ fontSize: compact ? 12 : 13 }}>
            <b>{i.where || '整体'}</b>　{i.what}
            <Box component="span" sx={{ color: 'text.secondary' }}>
              　→ {i.fix}
            </Box>
          </Box>
        ))}
      </Stack>
    </Alert>
  )
}
