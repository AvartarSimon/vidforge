import { Alert, Stack } from '@mui/material'
import { useProject } from '../../state/ProjectContext'
import { RetentionBanner } from '../shared/RetentionBanner'
import { ThemePicker } from '../shared/ThemePicker'
import { BuildPanel } from './render/BuildPanel'
import { LearningEditionCard } from './render/LearningEditionCard'
import { PresenterCard } from './render/PresenterCard'
import { RenderSettingsCard } from './render/RenderSettingsCard'
import { ResultCard } from './render/ResultCard'
import { SubtitleCard } from './render/SubtitleCard'
import { BrandCard } from './render/BrandCard'

export function RenderStep() {
  const { raw, reload } = useProject()
  if (!raw) return null

  return (
    <Stack spacing={2}>
      <RetentionBanner />
      <ThemePicker />
      <SubtitleCard />
      <BrandCard />
      <RenderSettingsCard />
      <LearningEditionCard />
      <PresenterCard />
      {(() => {
        // said here, before the button: the build would only find it after making all the narration
        const missing = raw.segments.filter((sg) => !(sg.clips || []).length && !(raw.auto_title_cards && sg.label)).map((sg) => sg.id)
        if (!missing.length) return null
        return (
          <Alert severity="warning">
            {missing.length === raw.segments.length ? '所有段落都还没有画面' : `有 ${missing.length} 段还没有画面`}（{missing.slice(0, 8).join('、')}
            {missing.length > 8 ? ' 等' : ''}），现在渲染会停下来。到顶部第 3 步「画面」点「一键配图」，或者给这几段选图、上传、放一个动画图表。
          </Alert>
        )
      })()}
      <BuildPanel onFinished={reload} />
      <ResultCard />
    </Stack>
  )
}
