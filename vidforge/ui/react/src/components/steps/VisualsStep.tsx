import { useEffect, useState } from 'react'
import { Box, Stack, Typography } from '@mui/material'
import { useProject } from '../../state/ProjectContext'
import { ClipStrip } from './visuals/ClipStrip'
import { PickerPanel } from './visuals/PickerPanel'
import { Storyboard } from './visuals/Storyboard'

export function VisualsStep() {
  const { raw, reload } = useProject()
  const [selId, setSelId] = useState<string | null>(null)

  useEffect(() => {
    if (!raw) return
    if (selId && raw.segments.some((s) => s.id === selId)) return
    setSelId((raw.segments.find((s) => !s.clips.length) || raw.segments[0])?.id ?? null)
  }, [raw, selId])

  if (!raw) return null
  if (!raw.segments.length) return <Typography color="text.secondary">先在第 1 步写脚本。</Typography>

  const seg = raw.segments.find((s) => s.id === selId)

  return (
    <Box sx={{ display: 'grid', gridTemplateColumns: '280px 1fr', gap: 2 }}>
      <Storyboard selId={selId} onSelect={setSelId} />
      {seg && (
        <Stack spacing={2}>
          <ClipStrip seg={seg} segId={seg.id} />
          <PickerPanel seg={seg} segId={seg.id} onAdded={reload} />
        </Stack>
      )}
    </Box>
  )
}
