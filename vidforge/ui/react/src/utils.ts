// small helpers shared across step components.

import { apiGet } from './api/client'
import type { ChatLoginStatus, Clip, RawProject, Segment } from './api/types'

// Older/hand-written project.json files (and vidforge's own `demo`/`init` templates) may still
// use the pre-`clips[]` single-visual shape: {image|video|remotion, motion} directly on the
// segment. Every component here assumes `segment.clips` is always an array — migrate in place.
export function normalizeSegments(raw: RawProject): void {
  for (const s of raw.segments) {
    if (Array.isArray(s.clips)) continue
    const c: Clip = {}
    for (const k of ['image', 'video', 'remotion'] as const) if (k in s) (c as Record<string, unknown>)[k] = s[k]
    const legacy: Segment & { image?: unknown; video?: unknown; remotion?: unknown; motion?: unknown } = s
    if (legacy.motion) c.motion = legacy.motion as string
    s.clips = Object.keys(c).length ? [c] : []
    delete legacy.image
    delete legacy.video
    delete legacy.remotion
    delete legacy.motion
  }
}

export function fileUrl(rel: string | null | undefined, bust?: number | string | null): string | null {
  if (!rel) return null
  const path = rel.split('/').map(encodeURIComponent).join('/')
  return `/files/${path}${bust ? `?t=${bust}` : ''}`
}

/**
 * A link that saves the file instead of playing it. The server answers it as an attachment, named
 * `name` (the video's title, not "final.mp4"); `bust` keeps a re-render from coming out of the cache.
 */
export function downloadUrl(rel: string | null | undefined, name: string, bust?: number | string | null): string | null {
  const url = fileUrl(rel)
  if (!url) return null
  const clean = name.replace(/[\\/:*?"<>|]+/g, ' ').trim() || (rel || '').split('/').pop() || 'video'
  return `${url}?download=${encodeURIComponent(clean)}${bust ? `&t=${bust}` : ''}`
}

export function fmtDuration(s: number | null | undefined): string {
  if (s == null) return '–'
  return s >= 60 ? `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, '0')}` : `${s.toFixed(1)} s`
}

// Shared by the AI drawer and the script-generation panel's browser-login flow — polls up to
// 5 minutes for the dedicated login profile's window to close. `isCancelled` is checked between
// ticks so a closed dialog / unmounted component stops polling instead of leaking a loop that
// keeps hitting the backend for up to 5 minutes after nobody's watching it anymore.
export async function pollLoginStatus(setStatus: (s: string) => void, isCancelled: () => boolean) {
  for (let i = 0; i < 150; i++) {
    await new Promise((r) => setTimeout(r, 2000))
    if (isCancelled()) return
    let j: ChatLoginStatus
    try {
      j = await apiGet<ChatLoginStatus>('/api/chat/login/status')
    } catch {
      continue
    }
    if (isCancelled()) return
    if (!j.running) {
      const entries = Object.entries(j.status || {})
      setStatus(entries.length ? '窗口已关闭：' + entries.map(([k, ok]) => `${ok ? '✓' : '✗'} ${k}`).join(' ') : '窗口已关闭。')
      return
    }
  }
  setStatus('登录窗口还开着（5 分钟已到，继续登录不影响，关闭窗口后刷新页面看结果）。')
}

// The files a file input was given — and the input emptied. Left holding its value, the input fires
// no change event when the same file is picked again, so uploading one picture to a second
// segment silently did nothing.
export function takeFiles(e: { target: HTMLInputElement }): File[] {
  const files = Array.from(e.target.files || [])
  e.target.value = ''
  return files
}

// -- microphone -----------------------------------------------------------------------------------
// The browser's call processing (echo cancellation, noise suppression, auto gain) is tuned for
// video calls, and a voiceover is the opposite case: the gain pumps between sentences, and the
// suppressor takes the low end and the overtones — the 浑厚 and 磁性 — with the hiss. Measured on
// a real studio take, the room was already at -76 dB, so nothing was left for it to save. Off by
// default; the voice presets clean up afterwards, and only the take itself is kept unprocessed.
const MIC_KEY = 'vf.mic.natural'

export function micNatural(): boolean {
  try {
    return localStorage.getItem(MIC_KEY) !== '0'
  } catch {
    return true
  }
}

export function setMicNatural(on: boolean) {
  try {
    localStorage.setItem(MIC_KEY, on ? '1' : '0')
  } catch {
    // private browsing: the default stands
  }
}

export function micConstraints(deviceId?: string): MediaTrackConstraints {
  const call = !micNatural()
  return {
    ...(deviceId ? { deviceId: { exact: deviceId } } : {}),
    echoCancellation: call,
    noiseSuppression: call,
    autoGainControl: call,
    sampleRate: { ideal: 48000 },
  }
}
