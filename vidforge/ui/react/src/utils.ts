// small helpers shared across step components — mirrors the equivalent one-liners in
// vidforge/ui/static/app.js so behaviour matches the old frontend exactly.

import type { Clip, RawProject, Segment } from './api/types'

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
