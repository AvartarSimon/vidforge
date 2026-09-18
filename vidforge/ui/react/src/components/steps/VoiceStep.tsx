import { useState } from 'react'
import { Stack, Typography } from '@mui/material'
import { useProject } from '../../state/ProjectContext'
import { SegmentVoiceList } from './voice/SegmentVoiceList'
import { VoiceSettingsCard } from './voice/VoiceSettingsCard'

interface AudioInfo {
  audio: string | null
  duration: number | null
  fresh: boolean
}

export function VoiceStep() {
  const { raw } = useProject()
  const [overrides, setOverrides] = useState<Record<string, AudioInfo>>({})
  const [progress, setProgress] = useState('')

  const setOverride = (segId: string, info: AudioInfo) => setOverrides((m) => ({ ...m, [segId]: info }))

  if (!raw) return null
  if (!raw.segments.length) {
    return (
      <Typography color="text.secondary">
        先在第 1 步写脚本。
      </Typography>
    )
  }

  return (
    <Stack spacing={2}>
      <VoiceSettingsCard
        onFirstDone={(segId, audio, duration) => setOverride(segId, { audio, duration, fresh: true })}
        onAllProgress={setProgress}
        onAllDone={() => setOverrides({})} // reload() (triggered by the caller) refreshes view.resolved for all segments
      />
      {progress && (
        <Typography variant="body2" color="text.secondary">
          {progress}
        </Typography>
      )}
      <SegmentVoiceList overrides={overrides} setOverride={setOverride} />
    </Stack>
  )
}
