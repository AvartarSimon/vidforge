// small helpers shared across step components — mirrors the equivalent one-liners in
// vidforge/ui/static/app.js so behaviour matches the old frontend exactly.

export function fileUrl(rel: string | null | undefined, bust?: number | string | null): string | null {
  if (!rel) return null
  const path = rel.split('/').map(encodeURIComponent).join('/')
  return `/files/${path}${bust ? `?t=${bust}` : ''}`
}

export function fmtDuration(s: number | null | undefined): string {
  if (s == null) return '–'
  return s >= 60 ? `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, '0')}` : `${s.toFixed(1)} s`
}
