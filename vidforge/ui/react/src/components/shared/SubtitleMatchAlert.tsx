import { useState } from 'react'
import { Alert, Button } from '@mui/material'
import { useProject } from '../../state/ProjectContext'
import { matchShare, RecognizeDialog } from './RecognizeDialog'

/**
 * 字幕和声音对不上: the segments whose own take strayed from the script (under 80 % of it heard),
 * said before the render rather than found in the finished video — with the one-click fix.
 */
export function SubtitleMatchAlert() {
  const { raw, view } = useProject()
  const [open, setOpen] = useState(false)
  if (!raw) return null
  const own = raw.segments.filter((s) => s.narration)
  if (!own.length) return null
  const low = own
    .map((s) => ({ id: s.id, share: matchShare(view?.resolved?.[s.id]?.align) }))
    .filter((x) => x.share != null && x.share < 0.8)
  return (
    <>
      {low.length > 0 && (
        <Alert
          severity="warning"
          action={
            <Button color="inherit" size="small" onClick={() => setOpen(true)}>
              按录音识别文字
            </Button>
          }
        >
          {low.map((x) => `${x.id}（${Math.round((x.share || 0) * 100)}%）`).join('、')} 录的时候和脚本说得不一样：字幕显示的是脚本，会和声音对不上。
          一键按录音识别，核对后替换脚本，字幕就和你说的一致了。
        </Alert>
      )}
      <RecognizeDialog open={open} onClose={() => setOpen(false)} />
    </>
  )
}

/** The plain button, for places that always offer it (the subtitle settings). */
export function RecognizeButton({ only, label = '字幕对不上？按录音识别文字' }: { only?: string[]; label?: string }) {
  const { raw } = useProject()
  const [open, setOpen] = useState(false)
  if (!raw?.segments.some((s) => s.narration && (!only || only.includes(s.id)))) return null
  return (
    <>
      <Button size="small" onClick={() => setOpen(true)}>
        {label}
      </Button>
      <RecognizeDialog open={open} onClose={() => setOpen(false)} only={only} />
    </>
  )
}
