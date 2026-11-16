import { FaceLandmarker, FilesetResolver, ImageSegmenter } from '@mediapipe/tasks-vision'
import type { FxSettings } from './settings'
import { needsFace, needsSegmentation } from './settings'
import { BILATERAL, BLUR, COMPOSITE, VERT, WARP } from './shaders'

/**
 * Live camera effects: a video element in, a processed canvas out, ~30 fps on an M-series Mac.
 *
 * Why in the browser and not in Python: the recording studio records this canvas, so the take is
 * exactly what the preview showed — there is no "it looked fine before export". Nothing about the
 * picture leaves the machine; only the two model files come down once (see vidforge/webmodels.py).
 *
 * Models load lazily and independently: background/beauty need the segmenter, 瘦脸/大眼 need the
 * face mesh. Until a model is ready its effects are simply skipped, so the preview never stalls.
 */

export type ModelState = 'off' | 'loading' | 'ready' | 'error'
export interface FxStatus {
  gl: boolean
  seg: ModelState
  face: ModelState
  fps: number
  faces: number
  error?: string
}

let filesetPromise: ReturnType<typeof FilesetResolver.forVisionTasks> | null = null
const fileset = () => (filesetPromise ??= FilesetResolver.forVisionTasks('/mediapipe/wasm'))

// GPU first (WebGL inside the WASM runtime); some machines refuse it, and CPU still works there.
async function create<T>(make: (delegate: 'GPU' | 'CPU') => Promise<T>): Promise<T> {
  try {
    return await make('GPU')
  } catch {
    return await make('CPU')
  }
}

// face-mesh indices (MediaPipe's 478-point topology)
const IRIS_L = 468
const IRIS_R = 473
const EYE_L = [33, 133]
const EYE_R = [362, 263]
const JAW_L = [132, 58, 172]
const JAW_R = [361, 288, 397]
const CHEEK_L = 234
const CHEEK_R = 454
const NOSE = 1
const CHIN = 152

function hex(c: string): [number, number, number] {
  const m = /^#?([0-9a-f]{6})$/i.exec(c.trim())
  if (!m) return [0, 0, 0]
  const n = parseInt(m[1], 16)
  return [((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255]
}

type Target = { fb: WebGLFramebuffer; tex: WebGLTexture; w: number; h: number }

export class FxEngine {
  readonly canvas: HTMLCanvasElement
  private gl: WebGL2RenderingContext | null
  private progs: Record<string, WebGLProgram> = {}
  private loc = new Map<WebGLProgram, Map<string, WebGLUniformLocation | null>>()
  private srcTex: WebGLTexture | null = null
  private maskTex: WebGLTexture | null = null
  private bgTex: WebGLTexture | null = null
  private targets: Record<string, Target> = {}
  private source: HTMLVideoElement | null = null
  private bgEl: HTMLImageElement | HTMLVideoElement | null = null
  private settings: FxSettings
  private seg: ImageSegmenter | null = null
  private face: FaceLandmarker | null = null
  private mask: Float32Array | null = null
  private maskBytes: Uint8Array | null = null
  private maskSize = [0, 0]
  private landmarks: { x: number; y: number }[] | null = null
  private lastTs = 0
  private raf = 0
  private frames = 0
  private fpsStart = 0
  private running = false
  private bypass = false
  status: FxStatus
  onStatus?: (s: FxStatus) => void

  constructor(canvas: HTMLCanvasElement, settings: FxSettings) {
    this.canvas = canvas
    this.settings = settings
    // preserveDrawingBuffer keeps the last frame for captureStream between paints
    this.gl = canvas.getContext('webgl2', { premultipliedAlpha: false, preserveDrawingBuffer: true, antialias: false })
    this.status = { gl: !!this.gl, seg: 'off', face: 'off', fps: 0, faces: 0 }
    if (!this.gl) {
      this.status.error = '这个浏览器不支持 WebGL2，特效不可用（录像仍然可以）'
      return
    }
    this.setup()
  }

  private setStatus(p: Partial<FxStatus>) {
    this.status = { ...this.status, ...p }
    this.onStatus?.(this.status)
  }

  private setup() {
    const gl = this.gl!
    const compile = (type: number, src: string) => {
      const s = gl.createShader(type)!
      gl.shaderSource(s, src)
      gl.compileShader(s)
      if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s) || 'shader')
      return s
    }
    const vs = compile(gl.VERTEX_SHADER, VERT)
    for (const [name, fs] of Object.entries({ warp: WARP, bilateral: BILATERAL, blur: BLUR, composite: COMPOSITE })) {
      const p = gl.createProgram()!
      gl.attachShader(p, vs)
      gl.attachShader(p, compile(gl.FRAGMENT_SHADER, fs))
      gl.bindAttribLocation(p, 0, 'a_pos')
      gl.linkProgram(p)
      if (!gl.getProgramParameter(p, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(p) || 'link')
      this.progs[name] = p
    }
    const buf = gl.createBuffer()
    gl.bindBuffer(gl.ARRAY_BUFFER, buf)
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW)
    gl.enableVertexAttribArray(0)
    gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0)
    this.srcTex = this.texture()
    this.maskTex = this.texture()
    this.bgTex = this.texture()
  }

  private texture() {
    const gl = this.gl!
    const t = gl.createTexture()!
    gl.bindTexture(gl.TEXTURE_2D, t)
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR)
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR)
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE)
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE)
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, 1, 1, 0, gl.RGBA, gl.UNSIGNED_BYTE, new Uint8Array([0, 0, 0, 255]))
    return t
  }

  private target(name: string, w: number, h: number): Target {
    const gl = this.gl!
    const t = this.targets[name]
    if (t && t.w === w && t.h === h) return t
    if (t) {
      gl.deleteFramebuffer(t.fb)
      gl.deleteTexture(t.tex)
    }
    const tex = this.texture()
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, w, h, 0, gl.RGBA, gl.UNSIGNED_BYTE, null)
    const fb = gl.createFramebuffer()!
    gl.bindFramebuffer(gl.FRAMEBUFFER, fb)
    gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, tex, 0)
    return (this.targets[name] = { fb, tex, w, h })
  }

  private u(p: WebGLProgram, name: string) {
    let m = this.loc.get(p)
    if (!m) this.loc.set(p, (m = new Map()))
    if (!m.has(name)) m.set(name, this.gl!.getUniformLocation(p, name))
    return m.get(name)!
  }

  private pass(name: string, out: Target | null, textures: [string, WebGLTexture | null][], set: (u: (n: string) => WebGLUniformLocation | null) => void) {
    const gl = this.gl!
    const p = this.progs[name]
    gl.useProgram(p)
    gl.bindFramebuffer(gl.FRAMEBUFFER, out ? out.fb : null)
    gl.viewport(0, 0, out ? out.w : this.canvas.width, out ? out.h : this.canvas.height)
    textures.forEach(([uname, tex], i) => {
      gl.activeTexture(gl.TEXTURE0 + i)
      gl.bindTexture(gl.TEXTURE_2D, tex)
      gl.uniform1i(this.u(p, uname), i)
    })
    gl.uniform1f(this.u(p, 'u_flip'), out ? 0 : 1)
    set((n) => this.u(p, n))
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4)
  }

  // -- public -----------------------------------------------------------------------------------
  setSource(v: HTMLVideoElement | null) {
    this.source = v
  }

  setBackground(el: HTMLImageElement | HTMLVideoElement | null) {
    this.bgEl = el
  }

  setBypass(on: boolean) {
    this.bypass = on // the 对比 button: show the untouched picture while held
  }

  update(s: FxSettings) {
    this.settings = s
    this.ensureModels()
  }

  private ensureModels() {
    const s = this.settings
    if (needsSegmentation(s) && this.status.seg === 'off') {
      this.setStatus({ seg: 'loading' })
      fileset()
        .then((fs) =>
          create((delegate) =>
            ImageSegmenter.createFromOptions(fs, {
              baseOptions: { modelAssetPath: '/api/models/selfie_multiclass_256x256.tflite', delegate },
              runningMode: 'VIDEO',
              outputConfidenceMasks: true,
              outputCategoryMask: false,
            }),
          ),
        )
        .then((seg) => {
          this.seg = seg
          this.setStatus({ seg: 'ready' })
        })
        .catch((e) => this.setStatus({ seg: 'error', error: `人像分割模型加载失败：${e?.message || e}` }))
    }
    if (needsFace(s) && this.status.face === 'off') {
      this.setStatus({ face: 'loading' })
      fileset()
        .then((fs) =>
          create((delegate) =>
            FaceLandmarker.createFromOptions(fs, {
              baseOptions: { modelAssetPath: '/api/models/face_landmarker.task', delegate },
              runningMode: 'VIDEO',
              numFaces: 1,
            }),
          ),
        )
        .then((face) => {
          this.face = face
          this.setStatus({ face: 'ready' })
        })
        .catch((e) => this.setStatus({ face: 'error', error: `人脸模型加载失败：${e?.message || e}` }))
    }
  }

  start() {
    if (this.running || !this.gl) return
    this.running = true
    this.fpsStart = performance.now()
    this.ensureModels()
    const loop = () => {
      if (!this.running) return
      try {
        this.frame()
      } catch (e) {
        this.setStatus({ error: `特效出错：${e instanceof Error ? e.message : String(e)}` })
      }
      this.raf = requestAnimationFrame(loop)
    }
    this.raf = requestAnimationFrame(loop)
  }

  stop() {
    this.running = false
    cancelAnimationFrame(this.raf)
  }

  dispose() {
    this.stop()
    this.seg?.close()
    this.face?.close()
    this.seg = null
    this.face = null
  }

  // -- per frame ----------------------------------------------------------------------------------
  private frame() {
    const v = this.source
    const gl = this.gl!
    if (!v || v.readyState < 2 || !v.videoWidth) return
    const W = v.videoWidth
    const H = v.videoHeight
    const s = this.settings
    const fx = s.enabled && !this.bypass

    // output size follows the chosen frame shape (9:16 for 抖音/快手, …), cut from the centre
    const crop = this.crop(W, H, s.aspect)
    const outW = Math.round(W * crop[2])
    const outH = Math.round(H * crop[3])
    if (this.canvas.width !== outW || this.canvas.height !== outH) {
      this.canvas.width = outW
      this.canvas.height = outH
    }

    gl.bindTexture(gl.TEXTURE_2D, this.srcTex)
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, v)

    let ts = performance.now()
    if (ts <= this.lastTs) ts = this.lastTs + 1
    this.lastTs = ts
    const hasMask = fx && needsSegmentation(s) && !!this.seg && this.runSegmenter(v, ts)
    const hasFace = fx && needsFace(s) && !!this.face && this.runFace(v, ts)

    // 1. warp (美型)
    const warp = this.target('warp', W, H)
    this.pass('warp', warp, [['u_src', this.srcTex]], (u) => {
      gl.uniform2f(u('u_res'), W, H)
      gl.uniform1f(u('u_on'), hasFace ? 1 : 0)
      if (hasFace) this.faceUniforms(u, W, H)
    })

    // 2. bilateral (磨皮) — only worth running when it will be used
    let smoothTex: WebGLTexture | null = warp.tex
    if (fx && s.smooth > 0 && hasMask) {
      const sm = this.target('smooth', W, H)
      const scale = Math.max(W, H) / 1280
      this.pass('bilateral', sm, [['u_tex', warp.tex]], (u) => {
        gl.uniform2f(u('u_px'), 1 / W, 1 / H)
        gl.uniform1f(u('u_radius'), (3 + 7 * s.smooth) * scale)
        gl.uniform1f(u('u_sigma'), 0.06 + 0.1 * s.smooth)
      })
      smoothTex = sm.tex
    }

    // 3. background blur at quarter size, ping-ponged; more passes = softer
    let blurTex: WebGLTexture | null = warp.tex
    if (fx && hasMask && s.bg === 'blur') {
      const bw = Math.max(16, Math.round(W / 4))
      const bh = Math.max(16, Math.round(H / 4))
      const a = this.target('blurA', bw, bh)
      const b = this.target('blurB', bw, bh)
      let src: WebGLTexture = warp.tex
      const passes = 1 + Math.round(s.bgBlur * 4)
      for (let i = 0; i < passes; i++) {
        const step = 1 + s.bgBlur * 1.5
        this.pass('blur', a, [['u_tex', src]], (u) => gl.uniform2f(u('u_dir'), step / bw, 0))
        this.pass('blur', b, [['u_tex', a.tex]], (u) => gl.uniform2f(u('u_dir'), 0, step / bh))
        src = b.tex
      }
      blurTex = b.tex
    }

    let bgMode = 0
    if (fx && hasMask) {
      if (s.bg === 'blur') bgMode = 1
      else if ((s.bg === 'image' || s.bg === 'video') && this.uploadBackground()) bgMode = 2
      else if (s.bg === 'color') bgMode = 3
    }

    // 4. composite to the canvas
    this.pass(
      'composite',
      null,
      [
        ['u_warp', warp.tex],
        ['u_smooth', smoothTex],
        ['u_mask', this.maskTex],
        ['u_blur', blurTex],
        ['u_bg', this.bgTex],
      ],
      (u) => {
        const on = fx ? 1 : 0
        gl.uniform2f(u('u_px'), 1 / W, 1 / H)
        gl.uniform4f(u('u_crop'), crop[0], crop[1], crop[2], crop[3])
        gl.uniform4fv(u('u_bgX'), this.bgTransform(outW, outH))
        gl.uniform1i(u('u_bgMode'), bgMode)
        gl.uniform3fv(u('u_bgColor'), hex(s.bgColor))
        gl.uniform1f(u('u_hasMask'), hasMask ? 1 : 0)
        gl.uniform2f(u('u_maskPx'), 1 / Math.max(1, this.maskSize[0]), 1 / Math.max(1, this.maskSize[1]))
        gl.uniform1f(u('u_smoothAmt'), hasMask ? s.smooth * on : 0)
        gl.uniform1f(u('u_whiten'), s.whiten * on)
        gl.uniform1f(u('u_rosy'), s.rosy * on)
        gl.uniform1f(u('u_sharpen'), s.sharpen * on)
        gl.uniform1f(u('u_bright'), s.bright * on)
        gl.uniform1f(u('u_contrast'), s.contrast * on)
        gl.uniform1f(u('u_sat'), s.saturation * on)
        gl.uniform1f(u('u_warm'), s.warmth * on)
        gl.uniform1f(u('u_edge'), s.edge)
        gl.uniform1f(u('u_clothes'), hasMask ? s.clothes * on : 0)
        gl.uniform1f(u('u_hair'), hasMask ? s.hair * on : 0)
        gl.uniform3fv(u('u_clothesC'), hex(s.clothesColor))
        gl.uniform3fv(u('u_hairC'), hex(s.hairColor))
      },
    )

    this.frames++
    const now = performance.now()
    if (now - this.fpsStart > 1000) {
      this.setStatus({ fps: Math.round((this.frames * 1000) / (now - this.fpsStart)), faces: this.landmarks ? 1 : 0 })
      this.frames = 0
      this.fpsStart = now
    }
  }

  private crop(W: number, H: number, aspect: FxSettings['aspect']): [number, number, number, number] {
    const want = { source: W / H, '16:9': 16 / 9, '9:16': 9 / 16, '1:1': 1, '3:4': 3 / 4 }[aspect] || W / H
    const have = W / H
    if (Math.abs(want - have) < 0.01) return [0, 0, 1, 1]
    if (want < have) {
      const sx = want / have
      return [(1 - sx) / 2, 0, sx, 1]
    }
    const sy = have / want
    return [0, (1 - sy) / 2, 1, sy]
  }

  // cover-fit the replacement background to the output frame, like CSS object-fit: cover
  private bgTransform(outW: number, outH: number): number[] {
    const el = this.bgEl
    const bw = el instanceof HTMLVideoElement ? el.videoWidth : el?.naturalWidth || 0
    const bh = el instanceof HTMLVideoElement ? el.videoHeight : el?.naturalHeight || 0
    if (!bw || !bh) return [0, 0, 1, 1]
    const out = outW / outH
    const bg = bw / bh
    if (bg > out) {
      const sx = out / bg
      return [(1 - sx) / 2, 0, sx, 1]
    }
    const sy = bg / out
    return [0, (1 - sy) / 2, 1, sy]
  }

  private uploadBackground(): boolean {
    const el = this.bgEl
    const gl = this.gl!
    if (!el) return false
    if (el instanceof HTMLVideoElement ? el.readyState < 2 : !el.complete || !el.naturalWidth) return false
    gl.bindTexture(gl.TEXTURE_2D, this.bgTex)
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, el)
    return true
  }

  private runSegmenter(v: HTMLVideoElement, ts: number): boolean {
    const r = this.seg!.segmentForVideo(v, ts)
    try {
      const masks = r.confidenceMasks
      if (!masks || masks.length < 5) return false
      const w = masks[0].width
      const h = masks[0].height
      const n = w * h
      // categories: 0 background, 1 hair, 2 body skin, 3 face skin, 4 clothes, 5 other
      const bg = masks[0].getAsFloat32Array()
      const hair = masks[1].getAsFloat32Array()
      const body = masks[2].getAsFloat32Array()
      const faceSkin = masks[3].getAsFloat32Array()
      const clothes = masks[4].getAsFloat32Array()
      // "other" (glasses, hats, a mic) belongs to the person, but it is also the class the model
      // falls back to for flat things it cannot place — a grey wall, a door — so it counts half
      const other = masks.length > 5 ? masks[5].getAsFloat32Array() : null
      if (!this.mask || this.mask.length !== n * 4) {
        this.mask = new Float32Array(n * 4)
        this.maskBytes = new Uint8Array(n * 4)
        this.maskSize = [w, h]
      }
      const m = this.mask
      const out = this.maskBytes!
      // a little temporal smoothing: per-frame masks flicker at the hairline, and flicker is the
      // tell that a background is fake
      const k = 0.55
      for (let i = 0; i < n; i++) {
        const j = i * 4
        const person = other ? Math.min(1, hair[i] + body[i] + faceSkin[i] + clothes[i] + other[i] * 0.5) : 1 - bg[i]
        m[j] = m[j] * (1 - k) + person * k
        m[j + 1] = m[j + 1] * (1 - k) + Math.min(1, body[i] + faceSkin[i]) * k
        m[j + 2] = m[j + 2] * (1 - k) + clothes[i] * k
        m[j + 3] = m[j + 3] * (1 - k) + hair[i] * k
        out[j] = m[j] * 255
        out[j + 1] = m[j + 1] * 255
        out[j + 2] = m[j + 2] * 255
        out[j + 3] = m[j + 3] * 255
      }
      const gl = this.gl!
      gl.bindTexture(gl.TEXTURE_2D, this.maskTex)
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, this.maskSize[0], this.maskSize[1], 0, gl.RGBA, gl.UNSIGNED_BYTE, out)
      return true
    } finally {
      r.close()
    }
  }

  private runFace(v: HTMLVideoElement, ts: number): boolean {
    const r = this.face!.detectForVideo(v, ts)
    const pts = r.faceLandmarks?.[0]
    if (!pts || pts.length < 474) {
      this.landmarks = null
      return false
    }
    // smoothed so the warp does not shimmer with landmark jitter
    if (!this.landmarks || this.landmarks.length !== pts.length) this.landmarks = pts.map((p) => ({ x: p.x, y: p.y }))
    else
      for (let i = 0; i < pts.length; i++) {
        this.landmarks[i].x += (pts[i].x - this.landmarks[i].x) * 0.6
        this.landmarks[i].y += (pts[i].y - this.landmarks[i].y) * 0.6
      }
    return true
  }

  private faceUniforms(u: (n: string) => WebGLUniformLocation | null, W: number, H: number) {
    const gl = this.gl!
    const s = this.settings
    const L = this.landmarks!
    const px = (i: number) => [L[i].x * W, L[i].y * H] as const
    const dist = (a: number, b: number) => Math.hypot(L[a].x * W - L[b].x * W, L[a].y * H - L[b].y * H)
    const faceW = dist(CHEEK_L, CHEEK_R)

    const eyeK = s.eyes * 0.18
    const eye = (iris: number, corners: number[]) => [...px(iris), dist(corners[0], corners[1]) * 1.15, eyeK]
    gl.uniform4fv(u('u_eye[0]'), [...eye(IRIS_L, EYE_L), ...eye(IRIS_R, EYE_R)])

    // pull the lower jaw toward the centre of the lower face; at most ~4.5 % of the face width
    const [cx, cy] = [(L[NOSE].x + L[CHIN].x) * 0.5 * W, (L[NOSE].y + L[CHIN].y) * 0.5 * H]
    const amount = s.slim * faceW * 0.045
    const pts: number[] = []
    for (const i of [...JAW_L, ...JAW_R]) {
      const [x, y] = px(i)
      const dx = cx - x
      const dy = cy - y
      const len = Math.hypot(dx, dy) || 1
      pts.push(x, y, (dx / len) * amount, (dy / len) * amount)
    }
    gl.uniform4fv(u('u_pt[0]'), pts)
    gl.uniform1f(u('u_ptR'), faceW * 0.24)
  }
}
