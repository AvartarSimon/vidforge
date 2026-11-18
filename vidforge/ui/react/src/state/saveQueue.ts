import { useSyncExternalStore } from 'react'
import { apiPostBytes } from '../api/client'

/**
 * 后台保存: takes leave the studio the moment you choose them, and the next one can be recorded
 * while they upload, get cut and land in the project. Saving one took 3–15 s (transcode, 剪口播,
 * Whisper for 嗯/呃), with the whole page waiting.
 *
 * Module-level on purpose: switching to another section unmounts the studio, and a queue living
 * in its state would be dropped with the takes in it. One at a time, in order — the server does
 * the heavy part, and two takes transcoding at once only finish later each.
 */

export type SaveResult = {
  seconds: number
  narration?: string
  footage?: string
  visual?: string
  kept?: string
  trimmed?: number[]
  jumpcut?: { removed: number; cuts: number; fillers?: number }
}

export type SaveJob = {
  id: number
  segId: string
  kind: 'use' | 'keep'
  window: boolean
  status: 'waiting' | 'saving' | 'done' | 'error'
  summary?: string
  error?: string
  at: number
  blob: Blob | null
  opts: Record<string, unknown>
}

let jobs: SaveJob[] = []
let seq = 0
let running = false
const listeners = new Set<() => void>()
const savedHooks = new Set<(job: SaveJob) => void>()

function emit() {
  jobs = [...jobs]
  listeners.forEach((l) => l())
}

function summarise(j: SaveResult, window: boolean): string {
  const parts = [`${j.seconds.toFixed(1)} 秒`]
  if (j.trimmed && (j.trimmed[0] > 0.05 || j.trimmed[1] > 0.05)) parts.push(`掐掉首尾静音 ${j.trimmed[0]}s / ${j.trimmed[1]}s`)
  if (j.jumpcut && j.jumpcut.removed > 0.05)
    parts.push(`剪口播剪掉 ${j.jumpcut.removed.toFixed(1)}s（${j.jumpcut.cuts} 处${j.jumpcut.fillers ? `，含「嗯」「呃」${j.jumpcut.fillers} 个` : ''}）`)
  if (j.visual) parts.push(window ? '真人小窗' : '画面')
  if (j.narration) parts.push('旁白')
  if (j.footage) parts.push(`素材库 ${j.footage}`)
  if (j.kept) parts.push('没被用上，留在录像列表里')
  return parts.join(' · ')
}

async function pump() {
  if (running) return
  running = true
  try {
    for (;;) {
      const job = jobs.find((j) => j.status === 'waiting')
      if (!job || !job.blob) break
      job.status = 'saving'
      emit()
      try {
        const q = encodeURIComponent(JSON.stringify({ ...job.opts, segment: job.segId }))
        const r = await apiPostBytes<SaveResult>(`/api/record/save?o=${q}`, job.blob)
        job.status = 'done'
        job.summary = summarise(r, job.window)
        job.blob = null // a minute of 1080p is ~100 MB of memory
        emit()
        savedHooks.forEach((h) => h(job))
      } catch (e) {
        // the blob stays, so 重试 sends the very same take
        job.status = 'error'
        job.error = e instanceof Error ? e.message : String(e)
        emit()
      }
    }
  } finally {
    running = false
  }
}

export function enqueueTake(segId: string, blob: Blob, ext: string, opts: Record<string, unknown>, kind: 'use' | 'keep' = 'use') {
  jobs.push({ id: ++seq, segId, kind, window: !!opts.as_window, status: 'waiting', at: Date.now(), blob, opts: { ...opts, ext } })
  emit()
  void pump()
}

export function retryTake(id: number) {
  const j = jobs.find((x) => x.id === id)
  if (j && j.status === 'error' && j.blob) {
    j.status = 'waiting'
    j.error = undefined
    emit()
    void pump()
  }
}

export function dismissTake(id: number) {
  jobs = jobs.filter((x) => x.id !== id || x.status === 'saving' || x.status === 'waiting')
  emit()
}

export function clearFinished() {
  jobs = jobs.filter((x) => x.status !== 'done')
  emit()
}

export function pendingTakes(): number {
  return jobs.filter((j) => j.status === 'waiting' || j.status === 'saving' || j.status === 'error').length
}

/** Called after each take lands — the project context reloads, lists refresh. */
export function onTakeSaved(fn: (job: SaveJob) => void): () => void {
  savedHooks.add(fn)
  return () => savedHooks.delete(fn)
}

const subscribe = (l: () => void) => {
  listeners.add(l)
  return () => listeners.delete(l)
}

export function useSaveQueue(): SaveJob[] {
  return useSyncExternalStore(subscribe, () => jobs)
}

// closing the tab with takes still uploading (or failed and not yet retried) would lose them
if (typeof window !== 'undefined') {
  window.addEventListener('beforeunload', (e) => {
    if (pendingTakes()) e.preventDefault()
  })
}
