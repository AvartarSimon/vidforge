import { useEffect, useRef, useState, type RefObject } from 'react'
import { FxEngine, type FxStatus } from './engine'
import type { FxSettings } from './settings'

/** One FxEngine bound to a <canvas> and a <video>, kept in sync with the settings object. */
export function useFxEngine(
  canvasRef: RefObject<HTMLCanvasElement | null>,
  videoRef: RefObject<HTMLVideoElement | null>,
  settings: FxSettings,
) {
  const engineRef = useRef<FxEngine | null>(null)
  const [status, setStatus] = useState<FxStatus | null>(null)

  useEffect(() => {
    if (!canvasRef.current) return
    const e = new FxEngine(canvasRef.current, settings)
    e.onStatus = setStatus
    setStatus(e.status)
    e.setSource(videoRef.current)
    e.start()
    engineRef.current = e
    return () => {
      e.dispose()
      engineRef.current = null
    }
    // the engine lives as long as the canvas; settings flow in through the effect below
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    engineRef.current?.update(settings)
  }, [settings])

  // the replacement background is a DOM element the engine uploads each frame
  useEffect(() => {
    const e = engineRef.current
    if (!e) return
    if (!settings.bgSrc || (settings.bg !== 'image' && settings.bg !== 'video')) {
      e.setBackground(null)
      return
    }
    if (settings.bg === 'video') {
      const v = document.createElement('video')
      v.src = settings.bgSrc
      v.muted = true
      v.loop = true
      v.playsInline = true
      v.crossOrigin = 'anonymous'
      v.play().catch(() => {})
      e.setBackground(v)
      return () => {
        v.pause()
        v.removeAttribute('src')
        v.load()
      }
    }
    const img = new Image()
    img.crossOrigin = 'anonymous'
    img.src = settings.bgSrc
    e.setBackground(img)
  }, [settings.bg, settings.bgSrc])

  return { engineRef, status }
}
