// Thin fetch wrapper: GET when no body, POST + JSON when a body is given; server errors come back
// as {error: string, ...extra}.

export class ApiError extends Error {
  data: Record<string, unknown>
  constructor(message: string, data: Record<string, unknown>) {
    super(message)
    this.data = data
  }
}

// The language variant being edited (project.json `variants`): every /api call carries it, so
// the voice, the build and the outputs all follow the language switcher without each caller
// remembering to pass it. A call that names its own `lang=` keeps it.
let currentLang: string | null = null
export function setApiLang(lang: string | null) {
  currentLang = lang
}

function withLang(url: string): string {
  if (!currentLang || !url.startsWith('/api/') || /[?&]lang=/.test(url)) return url
  return url + (url.includes('?') ? '&' : '?') + 'lang=' + encodeURIComponent(currentLang)
}

async function call<T>(path: string, body?: unknown): Promise<T> {
  const url = withLang(path)
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
