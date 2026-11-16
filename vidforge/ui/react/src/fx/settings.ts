// Settings for the live camera effects (美颜 / 美型 / 背景 / 换装). One flat object so a preset is
// just a partial of it, and so the whole thing can sit in localStorage between sessions.

export type BgMode = 'none' | 'blur' | 'image' | 'video' | 'color'
export type Aspect = 'source' | '16:9' | '9:16' | '1:1' | '3:4'

export interface FxSettings {
  enabled: boolean
  // 美颜 — 0..1 unless noted
  smooth: number // 磨皮: bilateral on skin pixels only
  whiten: number // 美白
  rosy: number // 红润
  sharpen: number // 清晰
  bright: number // 亮度 -1..1
  contrast: number // 对比 -1..1
  saturation: number // 饱和 -1..1
  warmth: number // 色温 -1..1
  // 美型 — kept small on purpose: past ~0.6 a face stops looking like the person
  slim: number // 瘦脸
  eyes: number // 大眼
  // 背景
  bg: BgMode
  bgBlur: number
  bgColor: string
  bgSrc: string // URL of the replacement image / video
  edge: number // how soft the cut-out edge is
  // 换装: recolour keeps the original shading, so creases and light stay real
  clothes: number
  clothesColor: string
  hair: number
  hairColor: string
  aspect: Aspect
}

export const DEFAULT_FX: FxSettings = {
  enabled: true,
  smooth: 0.45,
  whiten: 0.2,
  rosy: 0.15,
  sharpen: 0.25,
  bright: 0,
  contrast: 0,
  saturation: 0,
  warmth: 0,
  slim: 0.15,
  eyes: 0.1,
  bg: 'none',
  bgBlur: 0.6,
  bgColor: '#ffd166',
  bgSrc: '',
  edge: 0.4,
  clothes: 0,
  clothesColor: '#2c3e50',
  hair: 0,
  hairColor: '#3b2416',
  aspect: 'source',
}

// The 美颜 presets. "自然" is the default because the brief was 不假: on a talking-head channel
// an over-smoothed face is the first thing commenters notice.
export const FX_PRESETS: { id: string; name: string; about: string; values: Partial<FxSettings> }[] = [
  { id: 'off', name: '原图', about: '不做任何美颜', values: { smooth: 0, whiten: 0, rosy: 0, sharpen: 0, slim: 0, eyes: 0, bright: 0, contrast: 0, saturation: 0, warmth: 0 } },
  { id: 'natural', name: '自然', about: '看不出修过，但皮肤干净、气色好', values: { smooth: 0.45, whiten: 0.2, rosy: 0.15, sharpen: 0.25, slim: 0.15, eyes: 0.1, bright: 0, contrast: 0, saturation: 0, warmth: 0 } },
  { id: 'clear', name: '清透', about: '更白更亮，适合室内光线差的时候', values: { smooth: 0.6, whiten: 0.45, rosy: 0.2, sharpen: 0.2, slim: 0.25, eyes: 0.2, bright: 0.12, contrast: 0.05, saturation: 0.05, warmth: 0.05 } },
  { id: 'texture', name: '质感', about: '保留皮肤纹理，提清晰度和对比，适合男生/知识类', values: { smooth: 0.25, whiten: 0.05, rosy: 0.05, sharpen: 0.5, slim: 0.1, eyes: 0, bright: 0.02, contrast: 0.12, saturation: -0.05, warmth: -0.05 } },
  { id: 'glow', name: '元气', about: '红润暖色，像抖音的默认美颜', values: { smooth: 0.65, whiten: 0.35, rosy: 0.45, sharpen: 0.2, slim: 0.35, eyes: 0.3, bright: 0.08, contrast: 0.03, saturation: 0.12, warmth: 0.15 } },
]

const KEY = 'vf.fx.v1'

export function loadFx(): FxSettings {
  try {
    const raw = localStorage.getItem(KEY)
    if (raw) return { ...DEFAULT_FX, ...JSON.parse(raw) }
  } catch {
    // ignore (private browsing etc.)
  }
  return { ...DEFAULT_FX }
}

export function saveFx(s: FxSettings) {
  try {
    // a blob: URL dies with the page, so it must not come back next session as a broken background
    localStorage.setItem(KEY, JSON.stringify({ ...s, bgSrc: s.bgSrc.startsWith('blob:') ? '' : s.bgSrc }))
  } catch {
    // ignore
  }
}

export function needsSegmentation(s: FxSettings) {
  return s.enabled && (s.bg !== 'none' || s.smooth > 0 || s.whiten > 0 || s.rosy > 0 || s.clothes > 0 || s.hair > 0)
}

export function needsFace(s: FxSettings) {
  return s.enabled && (s.slim > 0 || s.eyes > 0)
}
