import { useEffect, useRef } from 'react'
import { Box } from '@mui/material'

export type PrompterPlace = 'top' | 'full' | 'bottom'

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
