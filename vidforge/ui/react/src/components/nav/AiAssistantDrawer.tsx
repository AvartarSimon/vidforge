import { useEffect, useState } from 'react'
import {
  Box,
  Button,
  Drawer,
  IconButton,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from '@mui/material'
import CloseIcon from '@mui/icons-material/Close'
import { apiGet, apiPost } from '../../api/client'
import type { ChatLoginStatus, ChatSite } from '../../api/types'
import { useProject } from '../../state/ProjectContext'

async function pollLoginStatus(setStatus: (s: string) => void) {
  for (let i = 0; i < 150; i++) {
    await new Promise((r) => setTimeout(r, 2000))
    let j: ChatLoginStatus
    try {
      j = await apiGet<ChatLoginStatus>('/api/chat/login/status')
    } catch {
      continue
    }
    if (!j.running) {
      const entries = Object.entries(j.status || {})
      setStatus(entries.length ? '窗口已关闭：' + entries.map(([k, ok]) => `${ok ? '✓' : '✗'} ${k}`).join(' ') : '窗口已关闭。')
      return
    }
  }
  setStatus('登录窗口还开着（5 分钟已到，继续登录不影响，关闭窗口后刷新页面看结果）。')
}

export function AiAssistantDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { raw } = useProject()
  const [sites, setSites] = useState<ChatSite[]>([])
  const [hasLocalLlm, setHasLocalLlm] = useState(false)
  const [site, setSite] = useState(() => localStorage.getItem('vf.ai_site') || '__local')
  const [loginHint, setLoginHint] = useState('')
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState('')
  const [status, setStatus] = useState('')
  const [busy, setBusy] = useState(false)
  const [loginWall, setLoginWall] = useState(false)

  useEffect(() => {
    if (!open) return
    Promise.all([
      apiGet<{ sites: ChatSite[] }>('/api/chat/sites').catch(() => ({ sites: [] })),
      apiGet<{ available: boolean }>('/api/llm/status').catch(() => ({ available: false })),
    ]).then(([s, llm]) => {
      setSites(s.sites)
      setHasLocalLlm(llm.available)
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  useEffect(() => {
    if (!open) return
    if (site === '__local') {
      setLoginHint('')
      return
    }
    apiGet<ChatLoginStatus>('/api/chat/login/status')
      .then((j) => {
        if (site in (j.status || {})) setLoginHint(j.status[site] ? '✓ 已登录' : '✗ 还没登录成功，点「登录这个网站」')
        else setLoginHint('还不确定登录状态——第一次用请点「登录这个网站」。')
      })
      .catch(() => setLoginHint(''))
  }, [open, site])

  const login = async () => {
    setLoginHint('已打开浏览器窗口，登录这个网站后关闭窗口…')
    try {
      await apiPost('/api/chat', { login: true, sites: [site] })
    } catch (e) {
      setLoginHint(e instanceof Error ? e.message : String(e))
      return
    }
    await pollLoginStatus(setLoginHint)
  }

  const ask = async (retry = false) => {
    const q = question.trim()
    if (!q) return
    localStorage.setItem('vf.ai_site', site)
    setBusy(true)
    setLoginWall(false)
    setStatus(site === '__local' ? '本地模型思考中…' : retry ? '登录后重新提问，等待回答…' : '在浏览器里提问，等待回答…')
    try {
      const j = site === '__local' ? await apiPost<{ text: string }>('/api/llm', { prompt: q }) : await apiPost<{ text: string }>('/api/chat', { site, prompt: q })
      setAnswer(j.text)
      setStatus('')
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e)
      setAnswer(message)
      setStatus('')
      setLoginWall(!retry && site !== '__local' && /登录|验证|verify|log ?in/i.test(message))
    }
    setBusy(false)
  }

  const addContext = () => {
    const s = raw?.segments[0]
    if (s) setQuestion((q) => `${q}\n\n当前段旁白：${s.text}`)
  }

  return (
    <Drawer anchor="right" open={open} onClose={onClose}>
      <Box sx={{ width: 420, p: 2, display: 'flex', flexDirection: 'column', height: '100%' }}>
        <Stack direction="row" justifyContent="space-between" alignItems="center">
          <Typography variant="h6">✦ AI 助手</Typography>
          <IconButton size="small" onClick={onClose}>
            <CloseIcon fontSize="small" />
          </IconButton>
        </Stack>
        <Stack direction="row" spacing={1} sx={{ mt: 1 }}>
          <TextField select size="small" label="用哪个" value={site} onChange={(e) => setSite(e.target.value)} sx={{ minWidth: 220 }}>
            {hasLocalLlm && <MenuItem value="__local">本地模型（离线，快，推荐）</MenuItem>}
            {sites.map((s) => (
              <MenuItem key={s.id} value={s.id}>
                {s.label}（我的浏览器）
              </MenuItem>
            ))}
          </TextField>
          {site !== '__local' && (
            <Button size="small" onClick={login}>
              登录这个网站
            </Button>
          )}
        </Stack>
        {loginHint && (
          <Typography variant="caption" color={loginHint.startsWith('✓') ? 'success.main' : 'text.secondary'}>
            {loginHint}
          </Typography>
        )}
        <TextField
          multiline
          minRows={4}
          placeholder="随便问点什么……"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          sx={{ mt: 1.5 }}
        />
        <Stack direction="row" spacing={1} sx={{ mt: 1 }}>
          <Button size="small" onClick={addContext} disabled={!raw?.segments.length}>
            带上当前段旁白
          </Button>
          <Button variant="contained" size="small" onClick={() => ask(false)} disabled={busy}>
            发送
          </Button>
        </Stack>
        {status && (
          <Typography variant="caption" color="text.secondary" sx={{ mt: 1 }}>
            {status}
          </Typography>
        )}
        {loginWall && (
          <Button
            size="small"
            color="warning"
            onClick={async () => {
              await login()
              ask(true)
            }}
            sx={{ alignSelf: 'flex-start', mt: 0.5 }}
          >
            先登录再重试
          </Button>
        )}
        {answer && (
          <Box sx={{ mt: 1.5, flexGrow: 1, overflow: 'auto' }}>
            <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap' }}>
              {answer}
            </Typography>
            <Stack direction="row" spacing={1} sx={{ mt: 1 }}>
              <Button size="small" onClick={() => navigator.clipboard.writeText(answer)}>
                复制
              </Button>
              <Button
                size="small"
                onClick={() => {
                  setAnswer('')
                  setQuestion('')
                }}
              >
                清空
              </Button>
            </Stack>
          </Box>
        )}
      </Box>
    </Drawer>
  )
}
