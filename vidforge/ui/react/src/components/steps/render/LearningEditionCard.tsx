import { Accordion, AccordionDetails, AccordionSummary, Button, MenuItem, Stack, TextField, Typography } from '@mui/material'
import ExpandMoreIcon from '@mui/icons-material/ExpandMore'
import type { RawProject } from '../../../api/types'
import { useProject } from '../../../state/ProjectContext'

// bilingual subtitles + a vocab outro, for a channel's English-learning cut. Building the actual
// per-language text (text_zh etc.) still happens in the old frontend's language switcher — this
// card only toggles the render-time settings and can create the en-zh variant scaffold, same as
// vidforge/ui/static/app.js's viewRender() "学习版" section.
export function LearningEditionCard() {
  const { raw, patch } = useProject()
  if (!raw) return null

  const bilingual = !!raw.subtitles?.bilingual
  const hasEnZh = !!raw.variants?.['en-zh']

  const setSub = (fn: (s: NonNullable<RawProject['subtitles']>) => void) =>
    patch((r) => {
      r.subtitles = r.subtitles || {}
      fn(r.subtitles)
    })

  const makeVariant = () => {
    patch((r) => {
      r.variants = r.variants || {}
      r.variants['en-zh'] = {
        text_from: 'en',
        title: `${r.title || ''}（双语学习版）`,
        outro_vocab: 8,
        subtitles: { burn: true, bilingual: true, bilingual_lang: 'zh', style: 'box', font: 'Microsoft YaHei', font_size: 22 },
        youtube: { description: '英文原声 + 中英双语字幕 + 本集词汇。', tags: ['英语学习', 'English'] },
      }
    })
  }

  return (
    <Accordion defaultExpanded={bilingual || !!raw.outro_vocab}>
      <AccordionSummary expandIcon={<ExpandMoreIcon />}>
        <Typography variant="subtitle1">学习版（双语字幕 + 片尾词汇卡，发国内英语学习区）</Typography>
      </AccordionSummary>
      <AccordionDetails>
        <Stack direction="row" spacing={2} flexWrap="wrap" useFlexGap alignItems="flex-start">
          <TextField
            select
            size="small"
            label="双语字幕"
            value={bilingual ? 'true' : 'false'}
            onChange={(e) => setSub((s) => (s.bilingual = e.target.value === 'true'))}
            sx={{ minWidth: 260 }}
            helperText={bilingual ? `字幕第二行显示 ${raw.subtitles?.bilingual_lang || 'zh'} 版旁白（需该语言的文本）` : undefined}
          >
            <MenuItem value="false">关</MenuItem>
            <MenuItem value="true">开</MenuItem>
          </TextField>
          <TextField
            size="small"
            type="number"
            label="片尾词汇卡（词数，0 = 不加）"
            value={raw.outro_vocab ?? 0}
            onChange={(e) => patch((r) => (r.outro_vocab = parseInt(e.target.value, 10) || 0))}
            sx={{ width: 220 }}
            helperText="内容由本地模型（Ollama）从脚本提取；没装则只列出单词"
          />
        </Stack>
        <Stack direction="row" sx={{ mt: 1.5 }}>
          {hasEnZh ? (
            <Typography variant="caption" color="text.secondary">
              已有 en-zh 学习版变体——渲染前先在旧版里把语言切到 en-zh，输出到 build_en-zh/。
            </Typography>
          ) : (
            <Button size="small" onClick={makeVariant}>
              ＋ 一键创建 en-zh 学习版变体
            </Button>
          )}
        </Stack>
      </AccordionDetails>
    </Accordion>
  )
}
