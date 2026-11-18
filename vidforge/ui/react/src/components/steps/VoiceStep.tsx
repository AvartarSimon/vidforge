import { useState } from 'react'
import { Accordion, AccordionDetails, AccordionSummary, Alert, Stack, Typography } from '@mui/material'
import ExpandMoreIcon from '@mui/icons-material/ExpandMore'
import { useProject } from '../../state/ProjectContext'
import { OwnVoicePanel } from '../sections/voice/OwnVoicePanel'
import { RecordStudio } from '../sections/voice/RecordStudio'
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

  const own = raw.segments.filter((s) => s.narration).length
  const all = own === raw.segments.length
  const tts = (
    <>
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
    </>
  )

  // A project read in your own voice does not need the synthesised-voice settings first: they
  // only apply to segments without a recording. The studio leads, the TTS card folds away.
  return (
    <Stack spacing={2}>
      {own > 0 && (
        <Alert severity={all ? 'success' : 'info'}>
          {all
            ? `${own} 段全部用你自己的录音——不需要合成配音。重录哪一段就在下面选它再录。`
            : `${own}/${raw.segments.length} 段用你自己的录音，其余 ${raw.segments.length - own} 段用合成配音。`}
        </Alert>
      )}
      {!all && tts}
      <RecordStudio />
      <OwnVoicePanel />
      {all && (
        <Accordion disableGutters variant="outlined" sx={{ borderRadius: 2, '&:before': { display: 'none' } }}>
          <AccordionSummary expandIcon={<ExpandMoreIcon />}>
            <Typography variant="body2" fontWeight={600}>
              合成配音（AI 声音）
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ ml: 1 }}>
              只给没有录音的段落用
            </Typography>
          </AccordionSummary>
          <AccordionDetails>
            <Stack spacing={2}>{tts}</Stack>
          </AccordionDetails>
        </Accordion>
      )}
      <SegmentVoiceList overrides={overrides} setOverride={setOverride} />
    </Stack>
  )
}
