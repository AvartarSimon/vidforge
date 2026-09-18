// Thin fetch wrapper mirroring vidforge/ui/static/app.js's `api()` helper: GET when no body,
// POST + JSON when a body is given; server errors come back as {error: string, ...extra}.

export class ApiError extends Error {
  data: Record<string, unknown>
  constructor(message: string, data: Record<string, unknown>) {
    super(message)
    this.data = data
  }
}

async function call<T>(url: string, body?: unknown): Promise<T> {
  const res = await fetch(
    url,
    body !== undefined
      ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }
      : undefined,
  )
  const json = await res.json().catch(() => ({}))
  if (!res.ok) throw new ApiError(json.error || res.statusText, json)
  return json as T
}

export const apiGet = <T,>(path: string): Promise<T> => call<T>(path)
export const apiPost = <T,>(path: string, body: unknown = {}): Promise<T> => call<T>(path, body)
