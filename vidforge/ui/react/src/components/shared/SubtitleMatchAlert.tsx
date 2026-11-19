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
  if (raw.narration_mode === 'free') {
    // spoken in your own words: the subtitles are the recording's — the question is only
    // whether anyone has looked at what Whisper heard
    const unchecked = own.filter((s) => view?.resolved?.[s.id]?.spoken !== 'checked').map((s) => s.id)
    return (
      <>
        {unchecked.length > 0 && (
          <Alert
            severity="info"
            action={
              <Button color="inherit" size="small" onClick={() => setOpen(true)}>
                核对字幕
              </Button>
            }
          >
            {unchecked.join('、')} 的字幕是按录音自动识别的，还没核对——人名、术语、数字最容易听错，看一眼标黄的词就行。
          </Alert>
        )}
        <RecognizeDialog open={open} onClose={() => setOpen(false)} />
      </>
    )
  }
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
export function RecognizeButton({ only, label }: { only?: string[]; label?: string }) {
  const { raw } = useProject()
  label = label || (raw?.narration_mode === 'free' ? '核对字幕' : '字幕对不上？按录音识别文字')
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
