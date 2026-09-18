import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react'
import { apiGet, apiPost } from '../api/client'
import type { ProjectView, RawProject } from '../api/types'
import { normalizeSegments } from '../utils'

type SaveState = 'saved' | 'dirty' | 'saving' | 'error'

interface ProjectContextValue {
  view: ProjectView | null
  raw: RawProject | null
  loading: boolean
  error: string | null
  saveState: SaveState
  savedAt: Date | null
  reload: () => Promise<void>
  markDirty: () => void
  patch: (fn: (raw: RawProject) => void) => void
  saveNow: () => Promise<boolean>
}

const ProjectContext = createContext<ProjectContextValue | null>(null)

const SAVE_DEBOUNCE_MS = 700

export function ProjectProvider({ children }: { children: ReactNode }) {
  const [view, setView] = useState<ProjectView | null>(null)
  const [raw, setRaw] = useState<RawProject | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [saveState, setSaveState] = useState<SaveState>('saved')
  const [savedAt, setSavedAt] = useState<Date | null>(null)
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const rawRef = useRef<RawProject | null>(null)
  rawRef.current = raw

  // `loading` drives the full-page spinner in App.tsx, which unmounts the current step while it's
  // true — fine for the very first load, but a refresh *after* an already-open project (e.g. a
  // step re-fetching server-computed fields post-save) must not do that, or every such refresh
  // would blow away in-progress UI state (open dialogs, a picker's selected source/tab, …) even
  // though nothing about the currently-open project actually changed identity.
  const reload = useCallback(async () => {
    const isInitialLoad = rawRef.current === null
    if (isInitialLoad) setLoading(true)
    setError(null)
    try {
      const v = await apiGet<ProjectView>('/api/project')
      if (!v.home) normalizeSegments(v.raw)
      setView(v)
      setRaw(v.home ? null : v.raw)
      setSaveState('saved')
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      if (isInitialLoad) setLoading(false)
    }
  }, [])

  useEffect(() => {
    reload()
  }, [reload])

  const save = useCallback(async (): Promise<boolean> => {
    if (saveTimer.current) clearTimeout(saveTimer.current)
    if (!rawRef.current) return true
    setSaveState('saving')
    try {
      await apiPost('/api/project', { raw: rawRef.current })
      setSaveState('saved')
      setSavedAt(new Date())
      return true
    } catch (e) {
      setSaveState('error')
      setError(e instanceof Error ? e.message : String(e))
      return false
    }
  }, [])

  const markDirty = useCallback(() => {
    setSaveState('dirty')
    if (saveTimer.current) clearTimeout(saveTimer.current)
    saveTimer.current = setTimeout(save, SAVE_DEBOUNCE_MS)
  }, [save])

  // mutate raw in place (mirrors the old app's direct-mutation style) then trigger a re-render + autosave
  const patch = useCallback(
    (fn: (raw: RawProject) => void) => {
      if (!rawRef.current) return
      fn(rawRef.current)
      setRaw({ ...rawRef.current })
      markDirty()
    },
    [markDirty],
  )

  return (
    <ProjectContext.Provider
      value={{ view, raw, loading, error, saveState, savedAt, reload, markDirty, patch, saveNow: save }}
    >
      {children}
    </ProjectContext.Provider>
  )
}

export function useProject() {
  const ctx = useContext(ProjectContext)
  if (!ctx) throw new Error('useProject() must be used inside a ProjectProvider')
  return ctx
}
