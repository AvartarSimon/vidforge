// small helpers shared across step components — mirrors the equivalent one-liners in
// vidforge/ui/static/app.js so behaviour matches the old frontend exactly.

import { apiGet } from './api/client'
import type { ChatLoginStatus, Clip, RawProject, Segment } from './api/types'

// Older/hand-written project.json files (and vidforge's own `demo`/`init` templates) may still
// use the pre-`clips[]` single-visual shape: {image|video|remotion, motion} directly on the
// segment. Every component here assumes `segment.clips` is always an array — migrate in place,
// same as the old frontend's normalizeSeg()/segClips() in vidforge/ui/static/app.js.
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
