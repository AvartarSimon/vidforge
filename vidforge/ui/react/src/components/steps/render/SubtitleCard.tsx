import { useEffect, useState } from 'react'
import { Box, Button, Card, CardContent, MenuItem, Slider, Stack, TextField, Typography } from '@mui/material'
import { apiGet } from '../../../api/client'
import type { RawProject } from '../../../api/types'
import { useProject } from '../../../state/ProjectContext'
import SubtitlesIcon from '@mui/icons-material/Subtitles'
import { PanelTitle } from '../../shared/ui'

type Palette = { id: string; box: string; text: string; accent: string }

// subtitles.SCRIPT_LINES: font_size and margin_v are counted on a script this many lines tall
const SCRIPT_LINES = 288

const HIGHLIGHTS = [
  ['word', '逐词高亮（正在说的字变色放大，短视频常用）'],
  ['keywords', '数字高亮（整句里的数字一直亮）'],
  ['karaoke', '数字随读亮起'],
  ['none', '不高亮'],
]

/**
 * hook.py's layout, measured in the browser: greedy lines that fit 82% of the frame, at most three,
 * the type shrunk by 12% steps until they do. Returns the lines and the size it settled on.
 */
function layoutHook(text: string, size: number, maxW: number): { lines: string[]; size: number } {
  const ctx = document.createElement('canvas').getContext('2d')
  const wrap = (s: number) => {
    if (!ctx) return text.split('\n')
    ctx.font = `800 ${s}px sans-serif`
    const out: string[] = []
    for (const para of text.split('\n').map((p) => p.trim()).filter(Boolean)) {
      const sep = para.includes(' ') ? ' ' : ''
      let line = ''
      for (const t of sep ? para.split(' ') : Array.from(para)) {
        const cand = line ? line + sep + t : t
        if (line && ctx.measureText(cand).width > maxW) {
          out.push(line)
          line = t
        } else line = cand
      }
      if (line) out.push(line)
    }
    return out
  }
  let s = size
  let lines = wrap(s)
  while (lines.length > 3 && s > size * 0.3) {
    s *= 0.88
    lines = wrap(s)
  }
  return { lines: lines.slice(0, 3), size: s }
}

/** The first sentence of the script, as a starting point the user then shortens. */
function firstSentence(raw: RawProject): string {
  const text = String(raw.segments?.[0]?.text || '').trim()
  const m = text.match(/^.+?[。！？!?.]/)
  return (m ? m[0] : text).replace(/[。.]$/, '').slice(0, 40)
}

/**
 * 字幕和开场大字: size, height and highlighting of the burned subtitles, and the hook card over the
 * first seconds — with a frame-shaped preview that uses the renderer's own proportions, so what
 * is set here is where it lands.
 */
export function SubtitleCard() {
  const { raw, patch } = useProject()
  const [palettes, setPalettes] = useState<Palette[]>([])

  useEffect(() => {
    apiGet<{ palettes: Palette[] }>('/api/theme')
      .then((j) => setPalettes(j.palettes))
      .catch(() => {})
  }, [])

  if (!raw) return null
  const sub = raw.subtitles || {}
  const burn = !!sub.burn
  const style = (sub.style as string) || 'outline'
  const highlight = (sub.highlight as string) || 'keywords'
  const fontSize = Number(sub.font_size ?? 22)
  const marginV = Number(sub.margin_v ?? 48)
  const hook = raw.hook || {}
  const [W, H] = [raw.width || 1920, raw.height || 1080]
  const tall = H > W
  const zh = (raw.language || 'en').startsWith('zh')
  const pal = palettes.find((p) => p.id === raw.theme?.palette)
  const accent = (sub.highlight_colour as string) || pal?.accent || raw.brand?.accent || '#d4793a'

  const setSub = (fn: (s: NonNullable<RawProject['subtitles']>) => void) =>
    patch((r) => {
      r.subtitles = r.subtitles || {}
      fn(r.subtitles)
    })
  const setHook = (fn: (h: NonNullable<RawProject['hook']>) => void) =>
    patch((r) => {
      r.hook = r.hook || {}
      fn(r.hook)
      if (!r.hook.text) delete r.hook
    })

  // preview: the frame at a fixed width, everything placed by the same fractions the renderer uses
  const pw = tall ? 190 : 360
  const ph = (pw * H) / W
  const words = zh ? ['中国', '人口', '去年', '减少', '85万人'] : ['The', 'population', 'fell', 'by', '850,000']
  const lit = highlight === 'word' ? 1 : -1
  const { lines: hookLines, size: hookSize } = layoutHook(String(hook.text || ''), tall ? pw * 0.075 : ph * 0.085, pw * 0.82)

  return (
    <Card variant="outlined">
      <CardContent>
        <PanelTitle icon={<SubtitlesIcon />} tone="teal" mb={1} title={<>字幕和开场大字</>} />
        <Stack direction={{ xs: 'column', md: 'row' }} spacing={3} alignItems="flex-start">
          <Box
            sx={{
              position: 'relative',
              flex: 'none',
              width: pw,
              height: ph,
              borderRadius: 1,
              overflow: 'hidden',
              background: 'linear-gradient(160deg, #5d7b8a 0%, #c9b8a6 60%, #8a5a3c 100%)',
            }}
          >
            {hookLines.length > 0 && (
              <Box
                sx={{
                  position: 'absolute',
                  left: '50%',
                  top: `${(tall ? 0.4 : 0.36) * 100}%`,
                  transform: 'translate(-50%, -50%)',
                  whiteSpace: 'nowrap',
                  px: `${hookSize * 0.55}px`,
                  py: `${hookSize * 0.38}px`,
                  borderRadius: `${hookSize * 0.32}px`,
                  bgcolor: pal ? pal.box : 'rgba(0,0,0,.78)',
                  textAlign: 'center',
                  fontWeight: 800,
                  fontSize: hookSize,
                  lineHeight: 1.28,
                }}
              >
                {hookLines.slice(0, 3).map((l, i) => (
                  <div key={i} style={{ color: i === 0 ? pal?.text || '#fff' : accent }}>
                    {l}
                  </div>
                ))}
              </Box>
            )}
            {burn && (
              <Box sx={{ position: 'absolute', left: 0, right: 0, bottom: `${(marginV / SCRIPT_LINES) * 100}%`, textAlign: 'center' }}>
                <Box
                  component="span"
                  sx={{
                    fontSize: (fontSize / SCRIPT_LINES) * ph,
                    lineHeight: 1.2,
                    color: (sub.text_colour as string) || '#fff',
                    fontWeight: sub.box_colour ? 700 : 400,
                    px: 0.5,
                    ...(style === 'box'
                      ? { bgcolor: (sub.box_colour as string) || 'rgba(0,0,0,.6)' }
                      : { textShadow: '0 0 2px #000, 0 0 2px #000, 0 0 3px #000' }),
                  }}
                >
                  {words.map((w, i) => {
                    // the moment drawn is the second word being said: the figure is lit only where keywords keeps it lit all along
                    const on = i === lit || (highlight === 'keywords' && i === words.length - 1)
                    return (
                      <span key={i} style={{ color: on ? accent : undefined, fontSize: i === lit ? '112%' : undefined }}>
                        {w}
                        {zh ? '' : ' '}
                      </span>
                    )
                  })}
                </Box>
              </Box>
            )}
          </Box>

          <Stack spacing={2} sx={{ flex: 1, minWidth: 260, maxWidth: 520 }}>
            <Stack direction="row" spacing={1.5} flexWrap="wrap" useFlexGap>
              <TextField
                select
                size="small"
                label="字幕"
                value={burn ? 'true' : 'false'}
                onChange={(e) => setSub((s) => (s.burn = e.target.value === 'true'))}
                sx={{ minWidth: 200 }}
              >
                <MenuItem value="false">只出 .srt（上传时作字幕轨）</MenuItem>
                <MenuItem value="true">烧进画面</MenuItem>
              </TextField>
              <TextField
                select
                size="small"
                label="样式"
                value={style}
                disabled={!burn}
                onChange={(e) => setSub((s) => (s.style = e.target.value))}
                sx={{ minWidth: 160 }}
              >
                <MenuItem value="outline">白字黑边</MenuItem>
                <MenuItem value="box">白字 + 底框</MenuItem>
              </TextField>
            </Stack>
            <TextField
              select
              size="small"
              label="高亮"
              value={highlight}
              disabled={!burn}
              onChange={(e) => setSub((s) => (s.highlight = e.target.value))}
            >
              {HIGHLIGHTS.map(([v, label]) => (
                <MenuItem key={v} value={v}>
                  {label}
                </MenuItem>
              ))}
            </TextField>
            <Box>
              <Typography variant="body2" color={burn ? 'text.primary' : 'text.disabled'}>
                字号 {fontSize}
              </Typography>
              <Slider
                size="small"
                disabled={!burn}
                min={6}
                max={32}
                value={fontSize}
                onChange={(_, v) => setSub((s) => (s.font_size = v as number))}
              />
              <Typography variant="body2" color={burn ? 'text.primary' : 'text.disabled'}>
                离底部 {Math.round((marginV / SCRIPT_LINES) * 100)}%
              </Typography>
              <Slider
                size="small"
                disabled={!burn}
                min={0}
                max={110}
                value={marginV}
                onChange={(_, v) => setSub((s) => (s.margin_v = v as number))}
              />
              <Typography variant="caption" color={burn && tall && marginV / SCRIPT_LINES < 0.2 ? 'warning.main' : 'text.secondary'}>
                {burn
                  ? tall
                    ? marginV / SCRIPT_LINES < 0.2
                      ? '低于 20% 了：抖音/快手/TikTok 底部是平台的文案和按钮，字幕会被挡住。'
                      : '抖音/快手/TikTok 底部约 20% 是平台的文案和按钮，字幕放在它上面。'
                    : '左边的小图按成片比例画，字号和位置就是成片里的样子。'
                  : '只出 .srt 时，字幕的样子由平台播放器决定。'}
              </Typography>
            </Box>
            <Stack direction="row" spacing={1} alignItems="flex-start" flexWrap="wrap" useFlexGap>
              <TextField
                size="small"
                multiline
                minRows={2}
                label="开场大字"
                placeholder={zh ? '中国人口61年来\n第一次减少了' : 'Why did the population\nfall for the first time?'}
                value={hook.text || ''}
                onChange={(e) => setHook((h) => (h.text = e.target.value))}
                helperText="前几秒压在画面中上部，回车分行，第二行用强调色；空着就不加"
                sx={{ flex: 1, minWidth: 220 }}
              />
              <TextField
                size="small"
                type="number"
                label="秒"
                value={hook.seconds ?? 3}
                disabled={!hook.text}
                onChange={(e) => setHook((h) => (h.seconds = parseFloat(e.target.value) || 3))}
                slotProps={{ htmlInput: { step: 0.5, min: 1, max: 6 } }}
                sx={{ width: 80 }}
              />
              <Button size="small" onClick={() => setHook((h) => (h.text = firstSentence(raw)))} disabled={!raw.segments?.length}>
                用第一句
              </Button>
            </Stack>
          </Stack>
        </Stack>
      </CardContent>
    </Card>
  )
}
