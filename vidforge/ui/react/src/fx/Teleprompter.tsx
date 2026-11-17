import { useEffect, useMemo, useRef, useState } from 'react'
import { Box } from '@mui/material'

export type PrompterPlace = 'line' | 'top' | 'full' | 'bottom'

/**
 * Scrolling script for reading to camera. The speed is in 字/分钟 because that is the number a
 * Chinese narrator actually knows about themselves (the project's own figure is 240), and the
 * reading line sits in the upper third, near the lens, so the eyes do not drift down the screen.
 */
export function Teleprompter({
  text,
  fontSize,
  cpm,
  running,
  mirror,
  place,
  resetKey,
}: {
  text: string
  fontSize: number
  cpm: number
  running: boolean
  mirror: boolean
  place: PrompterPlace
  resetKey: number
}) {
  const boxRef = useRef<HTMLDivElement | null>(null)
  const posRef = useRef(0)

  useEffect(() => {
    posRef.current = 0
    if (boxRef.current) boxRef.current.scrollTop = 0
  }, [resetKey, text])

  useEffect(() => {
    if (!running) return
    let raf = 0
    let last = performance.now()
    const chars = Math.max(1, text.replace(/\s/g, '').length)
    const tick = (now: number) => {
      const el = boxRef.current
      if (el) {
        // the whole text should pass the reading line in the time it takes to say it
        const travel = Math.max(1, el.scrollHeight - el.clientHeight * 0.35)
        const seconds = (chars / cpm) * 60
        posRef.current = Math.min(travel, posRef.current + (travel / seconds) * ((now - last) / 1000))
        el.scrollTop = posRef.current
      }
      last = now
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [running, cpm, text])

  const height = place === 'full' ? '100%' : '42%'
  return (
    <Box
      sx={{
        position: 'absolute',
        left: 0,
        right: 0,
        top: place === 'bottom' ? 'auto' : 0,
        bottom: place === 'bottom' ? 0 : 'auto',
        height,
        background: 'linear-gradient(rgba(0,0,0,.72), rgba(0,0,0,.45))',
        pointerEvents: 'auto',
      }}
    >
      <Box
        ref={boxRef}
        // the user can always grab it and scroll by hand; the auto-scroll picks up from there
        onScroll={(e) => {
          if (!running) posRef.current = (e.target as HTMLDivElement).scrollTop
        }}
        sx={{
          height: '100%',
          overflowY: 'auto',
          px: 4,
          scrollbarWidth: 'none',
          transform: mirror ? 'scaleX(-1)' : undefined,
          maskImage: 'linear-gradient(transparent, #000 18%, #000 70%, transparent)',
        }}
      >
        <Box sx={{ height: '22%' }} />
        <Box
          sx={{
            color: '#fff',
            fontSize: `${fontSize}px`,
            lineHeight: 1.65,
            fontWeight: 500,
            textAlign: 'center',
            textShadow: '0 2px 6px rgba(0,0,0,.9)',
            whiteSpace: 'pre-wrap',
          }}
        >
          {text}
        </Box>
        <Box sx={{ height: '70%' }} />
      </Box>
      {/* reading line */}
      <Box sx={{ position: 'absolute', left: 8, right: 8, top: '30%', height: 2, bgcolor: 'primary.main', opacity: 0.55, pointerEvents: 'none' }} />
    </Box>
  )
}

/** The script cut into the pieces a reader takes in one glance: clauses, long ones halved. */
export function promptLines(text: string, max?: number): string[] {
  // a Latin letter is about half a Chinese glyph wide: the same strip holds twice as many
  max = max ?? (/[\u4e00-\u9fff]/.test(text) ? 24 : 44)
  const out: string[] = []
  for (const clause of text.replace(/\s+/g, ' ').split(/(?<=[，。！？；：,.!?;:])/)) {
    const c = clause.trim()
    if (!c) continue
    // a long clause is cut into equal parts: cutting at the limit left 「人。」 alone on a line
    const parts = Math.ceil(c.length / max)
    const size = Math.ceil(c.length / parts)
    for (let i = 0; i < c.length; i += size) {
      let piece = c.slice(i, i + size)
      // Latin text: move the cut back to the last space, so no word is split
      if (i + size < c.length && /[A-Za-z]$/.test(piece) && /^[A-Za-z]/.test(c.slice(i + size)) && piece.lastIndexOf(' ') > size / 2) {
        piece = piece.slice(0, piece.lastIndexOf(' '))
        out.push(piece.trim())
        i -= size - piece.length
        continue
      }
      out.push(piece.trim())
    }
  }
  return out.filter(Boolean)
}

/**
 * 单独一行: the line being read, on a strip above the picture instead of over it — the face stays
 * in view, and the strip sits at the top of the screen, right under a laptop's camera. What has
 * been read turns the accent colour at the chosen pace; the next line waits, dimmer, beside it.
 */
export function PrompterLine({ text, fontSize, cpm, running, mirror, resetKey }: { text: string; fontSize: number; cpm: number; running: boolean; mirror: boolean; resetKey: number }) {
  const lines = useMemo(() => promptLines(text), [text])
  const [done, setDone] = useState(0) // characters read so far
  const doneRef = useRef(0)

  useEffect(() => {
    doneRef.current = 0
    setDone(0)
  }, [resetKey, text])

  useEffect(() => {
    if (!running) return
    let raf = 0
    let last = performance.now()
    const tick = (now: number) => {
      doneRef.current += (cpm / 60) * ((now - last) / 1000)
      last = now
      setDone(doneRef.current)
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [running, cpm])

  // which line the reader is on, and how far into it
  let left = done
  let i = 0
  while (i < lines.length - 1 && left >= lines[i].replace(/\s/g, '').length) {
    left -= lines[i].replace(/\s/g, '').length
    i++
  }
  const cur = lines[i] || ''
  let shown = 0
  let readPart = ''
  for (const ch of cur) {
    if (shown >= left) break
    readPart += ch
    if (!/\s/.test(ch)) shown++
  }
  return (
    <Box
      sx={{
        bgcolor: '#111418',
        color: '#fff',
        borderRadius: 2,
        px: 2.5,
        py: 1.25,
        mb: 1,
        minHeight: fontSize * 1.6 + 30,
        display: 'flex',
        alignItems: 'baseline',
        gap: 2,
        overflow: 'hidden',
        transform: mirror ? 'scaleX(-1)' : undefined,
      }}
    >
      <Box sx={{ fontSize, fontWeight: 600, lineHeight: 1.5, whiteSpace: 'nowrap' }}>
        <Box component="span" sx={{ color: 'primary.main' }}>
          {readPart}
        </Box>
        {cur.slice(readPart.length)}
      </Box>
      <Box sx={{ fontSize: fontSize * 0.6, color: 'rgba(255,255,255,.45)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', minWidth: 0 }}>
        {lines[i + 1] || ''}
      </Box>
    </Box>
  )
}
