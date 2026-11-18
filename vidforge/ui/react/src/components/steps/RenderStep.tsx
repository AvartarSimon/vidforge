import { Alert, Stack, Typography } from '@mui/material'
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

  // what is pressed most goes first: the render button, its progress and the result used to sit
  // under six settings cards, a long scroll away on every visit
  const missing = raw.segments.filter((sg) => !(sg.clips || []).length && !(raw.auto_title_cards && sg.label)).map((sg) => sg.id)
  return (
    <Stack spacing={2}>
      <RetentionBanner />
      {missing.length > 0 && (
        <Alert severity="info">
          {missing.length === raw.segments.length ? '所有段落都还没有画面' : `有 ${missing.length} 段还没有画面`}（{missing.slice(0, 8).join('、')}
          {missing.length > 8 ? ' 等' : ''}）：照样可以渲染——用你自己录的视频全屏，或者把小窗放大成全屏，都没有就用配色的纯色底写上章节名。
          想配图随时去第 3 步「画面」（「一键配图」是可选的）。
        </Alert>
      )}
      <BuildPanel onFinished={reload} />
      <ResultCard />
      <Typography variant="overline" color="text.secondary" sx={{ pt: 1 }}>
        渲染设置
      </Typography>
      <ThemePicker />
      <SubtitleCard />
      <BrandCard />
      <RenderSettingsCard />
      <LearningEditionCard />
      <PresenterCard />
    </Stack>
  )
}
