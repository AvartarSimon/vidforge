import { Stack, Typography } from '@mui/material'
import { useProject } from '../../state/ProjectContext'
import { BuildPanel } from './render/BuildPanel'
import { RenderSettingsCard } from './render/RenderSettingsCard'
import { ResultCard } from './render/ResultCard'

export function RenderStep() {
  const { raw, reload } = useProject()
  if (!raw) return null

  return (
    <Stack spacing={2}>
      <RenderSettingsCard />
      {/* 学习版（双语字幕+词汇卡+en-zh 变体）和数字主持人配置依赖这个 React 前端还没做的多语言
          变体切换/画中画体系，本期先不做——不影响"配好参数直接渲染"这条主线。 */}
      <Typography variant="caption" color="text.secondary">
        学习版（双语字幕/词汇卡）、数字主持人配置：即将推出，可以先在旧版里设置好，这里渲染同样会生效。
      </Typography>
      <BuildPanel onFinished={reload} />
      <ResultCard />
    </Stack>
  )
}
