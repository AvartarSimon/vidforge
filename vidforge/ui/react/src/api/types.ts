// Shapes mirror vidforge/ui/__init__.py's JSON responses (see project_view()) and
// vidforge/ui/static/app.js's usage of them — kept intentionally loose (most fields optional)
// since the Python side is a dynamically-typed dict, not a schema.

export interface Clip {
  image?: string
  video?: string
  remotion?: { composition: string; props?: Record<string, unknown> }
  me?: { tags?: string[]; talking?: boolean }
  in?: number
  out?: number
  duration?: number
  motion?: string
  credit?: string
  [key: string]: unknown
}

export interface Overlay {
  avatar?: boolean
  image?: string
  video?: string
  me?: { tags?: string[]; talking?: boolean }
  position?: string
  size?: number
  at?: number
  duration?: number
  animate?: string
  [key: string]: unknown
}

export interface Segment {
  id: string
  text?: string
  label?: string | null
  visual_hint?: string | null
  clips: Clip[]
  overlays?: Overlay[]
  pause_after?: number
  fit?: string
  voice?: string // per-segment override of the project's global voice
  [key: string]: unknown // text_<lang> / label_<lang> variant keys
}

export interface RawProject {
  title?: string
  thumbnail_text?: string
  target_minutes?: number
  category?: string | null
  language?: string
  voice?: string
  rate?: string
  tts?: { provider?: string; [key: string]: unknown }
  segments: Segment[]
  variants?: Record<string, Record<string, unknown>>
  [key: string]: unknown
}

export interface ResolvedClip {
  kind: 'me' | 'remotion' | 'video' | 'image'
  me?: unknown
  path: string | null
  source: string | null
  in: number | null
  out: number | null
  duration: number | null
  motion: string | null
  remotion: string | null
  natural: number | null
  index: number
}

export interface ResolvedSegment {
  text: string
  label: string | null
  duration: number | null
  need: number
  fixed_total: number
  keywords: string[]
  audio?: string | null
  audio_fresh?: boolean
  clips?: ResolvedClip[]
  [key: string]: unknown
}

export interface ProjectView {
  home?: boolean
  projects?: RecentProject[]
  workspace?: string
  raw: RawProject
  lang: string
  base_lang: string
  langs: string[]
  issues: string | null
  resolved: Record<string, ResolvedSegment>
  root: string
  [key: string]: unknown
}

export interface RecentProject {
  path: string
  title: string
  opened: number
  final: boolean
}

export interface CategorySource {
  name: string
  url?: string
}

export interface Category {
  id: string
  name: string
  topic_notes?: string
  insights?: string
  sources?: CategorySource[]
  platforms?: string[]
  banned_keywords?: string[]
  platform_restrictions?: string
  defaults?: Record<string, unknown>
}

export interface ChatSite {
  id: string
  label: string
  url: string
}

export interface SplitSegment {
  label: string | null
  text: string
  visual_hint: string | null
}

export interface ChatLoginStatus {
  status: Record<string, boolean>
  running: boolean
}

export interface VoiceOption {
  name: string
  locale: string
  gender: string
  personalities: string[]
  friendly: string
}

export interface SearchCandidate {
  provider: string
  id: string
  kind: 'image' | 'video'
  thumb_url: string
  preview_url: string
  download_url: string
  width: number
  height: number
  duration: number | null
  author: string
  license: string
  page_url: string
  title: string
  ext: string
  desc: string
}
