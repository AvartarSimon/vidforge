import { Button, Stack, Typography } from '@mui/material'
import type { Segment } from '../../../api/types'
import { useProject } from '../../../state/ProjectContext'

const COMPOSITIONS = ['TitleCard', 'Timeline', 'BarChart'] as const

const DEFAULT_PROPS: Record<(typeof COMPOSITIONS)[number], Record<string, unknown>> = {
  TitleCard: { title: '', subtitle: '' },
  Timeline: {
    title: '',
    events: [
      { date: '1815', text: '…' },
      { date: '1816', text: '…' },
    ],
  },
  BarChart: {
    title: '',
    items: [
      { label: 'A', value: 3 },
      { label: 'B', value: 5 },
    ],
  },
}

export function AnimTab({ seg, segId }: { seg: Segment; segId: string }) {
  const { patch } = useProject()

  const add = (composition: (typeof COMPOSITIONS)[number]) => {
    const defaults = { ...DEFAULT_PROPS[composition] }
    if (composition === 'TitleCard') defaults.title = seg.label || seg.id
    patch((raw) => {
      const s = raw.segments.find((x) => x.id === segId)
      if (s) s.clips.push({ remotion: { composition, props: defaults } })
    })
  }

  return (
    <Stack spacing={1}>
      <Typography variant="caption" color="text.secondary">
        动画段：时长自动等于它在本段的份额。TitleCard：章节标题卡 · Timeline：时间轴逐条出现 · BarChart：动画柱状对比。加入后点片段上的「编辑」改文字。
      </Typography>
      <Stack direction="row" spacing={1}>
        {COMPOSITIONS.map((c) => (
          <Button key={c} variant="outlined" onClick={() => add(c)}>
            ＋ {c}
          </Button>
        ))}
      </Stack>
    </Stack>
  )
}
