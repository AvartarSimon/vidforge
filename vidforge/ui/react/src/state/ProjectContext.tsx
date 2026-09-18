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
  saveNow: (snapshot?: boolean) => Promise<boolean>
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

  const save = useCallback(async (snapshot = false): Promise<boolean> => {
    if (saveTimer.current) clearTimeout(saveTimer.current)
    if (!rawRef.current) return true
    setSaveState('saving')
    try {
      await apiPost('/api/project', { raw: rawRef.current, snapshot })
      setSaveState('saved')
      setSavedAt(new Date())
      return true
    } catch (e) {
      setSaveState('error')
      setError(e instanceof Error ? e.message : String(e))
      return false
    }
  }, [])

  // `loading` drives the full-page spinner in App.tsx, which unmounts the current step while it's
  // true — fine for the very first load, but a refresh *after* an already-open project (e.g. a
  // step re-fetching server-computed fields post-save) must not do that, or every such refresh
  // would blow away in-progress UI state (open dialogs, a picker's selected source/tab, …) even
  // though nothing about the currently-open project actually changed identity.
  const reload = useCallback(async () => {
    const isInitialLoad = rawRef.current === null
    if (isInitialLoad) setLoading(true)
    setError(null)
    // a reload always replaces `raw` wholesale with whatever the server has — if there's an
    // edit still sitting in the 700ms autosave debounce, flush it first or it gets silently
    // discarded (e.g. build/segment-history/project-switch flows all call reload()).
    if (saveTimer.current) await save()
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
  }, [save])

  useEffect(() => {
    reload()
  }, [reload])

  const markDirty = useCallback(() => {
    setSaveState('dirty')
    if (saveTimer.current) clearTimeout(saveTimer.current)
    saveTimer.current = setTimeout(save, SAVE_DEBOUNCE_MS)
  }, [save])

  // mutate raw in place (mirrors the old app's direct-mutation style) then trigger a re-render + autosave.
  // The mutation happens directly on rawRef.current, so if fn() throws partway through, whatever
  // it already changed is real — surfacing the error AND still committing that partial state (via
  // setRaw + markDirty) beats silently discarding it or leaving the UI showing stale data.
  const patch = useCallback(
    (fn: (raw: RawProject) => void) => {
      if (!rawRef.current) return
      try {
        fn(rawRef.current)
      } catch (e) {
        console.error('patch() callback threw', e)
        setError(e instanceof Error ? e.message : String(e))
      }
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
