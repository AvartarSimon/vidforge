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
  quality?: 'draft' | 'final'
  subtitles?: { burn?: boolean; style?: string; bilingual?: boolean; bilingual_lang?: string; [key: string]: unknown }
  transition?: number
  bgm?: { file: string; volume_db?: number; fade_out?: number } | null
  auto_title_cards?: boolean
  normalize_audio?: boolean
  encoder?: string
  parallel?: number
  supersample?: number
  motion_amount?: number
  width?: number
  height?: number
  fps?: number
  youtube?: {
    title?: string
    tags?: string[]
    privacy?: string
    category_id?: number
    description?: string
    disclosure?: { ai_voice?: boolean; ai_visuals?: boolean; realistic_presenter?: boolean }
    [key: string]: unknown
  }
  [key: string]: unknown
}

export interface Outputs {
  final: string | null
  final_mtime: number | null
  srt: string | null
  thumbnail: string | null
  credits: string | null
  timeline: { start: number; end: number; label?: string; id: string }[] | null
  youtube: { url?: string; [key: string]: unknown } | null
}

export interface BuildStatus {
  state: 'idle' | 'running' | 'done' | 'error' | 'cancelled'
  lines: string[]
  lang: string | null
  started: number | null
  finished: number | null
  error: string | null
  elapsed: number
  progress: number
  phase: string
  eta: number | null
  segments_done: number | null
  segments_total: number | null
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
  build_dir?: string
  outputs?: Outputs
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

export interface CategoryDefaults {
  voice?: string
  tts_provider?: string
  language?: string
  subtitles_bilingual?: boolean
  outro_vocab?: number
  [key: string]: unknown
}

export interface Category {
  id: string
  name: string
  topic_notes?: string
  insights?: string
  sources?: CategorySource[]
  platforms?: string[]
  tags?: string[]
  banned_keywords?: string[]
  platform_restrictions?: string
  defaults?: CategoryDefaults
  updated?: string
  [key: string]: unknown
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

export interface YoutubeVideo {
  video_id: string
  title: string
  channel: string
  views: number
  published: string
  age_days: number | null
  duration_s: number | null
  likes: number | null
  comments: number | null
  source: string
  url: string
  views_per_day: number | null
}

export interface YoutubeSummary {
  count: number
  median_views?: number
  max_views?: number
  recent_12m?: number
  recent_median_views?: number
  long_form_share?: number
  median_duration_min?: number
  channels?: number
  top_titles?: string[]
}

export interface AnalyzeResult {
  raw?: boolean
  why?: string
  verdict?: 'do' | 'do_with_angle' | 'skip' | string
  saturation?: string
  angles?: ({ title: string; why?: string } | string)[]
  titles?: string[]
  hooks?: string[]
  strengths_of_top?: string[]
  gaps?: string[]
  thumbnail_text?: string[]
  risks?: string[]
}

export interface MeItem {
  name: string
  tags?: string[]
  talking?: boolean
  duration?: number | null
  uses?: number
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
