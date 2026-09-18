// Shapes mirror vidforge/ui/__init__.py's JSON responses (see project_view()) and
// vidforge/ui/static/app.js's usage of them — kept intentionally loose (most fields optional)
// since the Python side is a dynamically-typed dict, not a schema.

export interface Segment {
  id: string
  text?: string
  label?: string | null
  visual_hint?: string | null
  clips?: unknown[]
  pause_after?: number
  [key: string]: unknown // text_<lang> / label_<lang> variant keys
}

export interface RawProject {
  title?: string
  thumbnail_text?: string
  target_minutes?: number
  category?: string | null
  language?: string
  segments: Segment[]
  variants?: Record<string, Record<string, unknown>>
  [key: string]: unknown
}

export interface ResolvedSegment {
  text: string
  label: string | null
  duration: number | null
  need: number
  keywords: string[]
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
