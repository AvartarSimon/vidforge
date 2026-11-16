import { Stack } from '@mui/material'
import { useProject } from '../../state/ProjectContext'
import { RetentionBanner } from '../shared/RetentionBanner'
import { ThemePicker } from '../shared/ThemePicker'
import { BuildPanel } from './render/BuildPanel'
import { LearningEditionCard } from './render/LearningEditionCard'
import { PresenterCard } from './render/PresenterCard'
import { RenderSettingsCard } from './render/RenderSettingsCard'
import { ResultCard } from './render/ResultCard'
import { SubtitleCard } from './render/SubtitleCard'

export function RenderStep() {
  const { raw, reload } = useProject()
  if (!raw) return null

  return (
    <Stack spacing={2}>
      <RetentionBanner />
      <ThemePicker />
      <SubtitleCard />
      <RenderSettingsCard />
      <LearningEditionCard />
      <PresenterCard />
      <BuildPanel onFinished={reload} />
      <ResultCard />
    </Stack>
  )
}
