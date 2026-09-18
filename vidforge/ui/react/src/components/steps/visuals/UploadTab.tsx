import { useRef, useState } from 'react'
import { Box, Typography } from '@mui/material'
import { apiPost } from '../../../api/client'
import { useProject } from '../../../state/ProjectContext'

function readAsBase64(f: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const rd = new FileReader()
    rd.onload = () => resolve((rd.result as string).split(',')[1])
    rd.onerror = reject
    rd.readAsDataURL(f)
  })
}

export function UploadTab({ segId, onAdded }: { segId: string; onAdded: () => void }) {
  const { patch, saveNow } = useProject()
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)
  const [status, setStatus] = useState<string | null>(null)

  const uploadFiles = async (files: FileList | File[]) => {
    for (const f of Array.from(files)) {
      setStatus(`上传 ${f.name}…`)
      try {
        const b64 = await readAsBase64(f)
        const j = await apiPost<{ path: string; kind: string }>('/api/assets/upload', { name: f.name, data_b64: b64 })
        patch((raw) => {
          const s = raw.segments.find((x) => x.id === segId)
          if (!s) return
          s.clips.push(j.kind === 'video' ? { video: j.path } : { image: j.path, motion: 'zoom_in' })
        })
      } catch (e) {
        setStatus(e instanceof Error ? e.message : String(e))
        return
      }
    }
    setStatus(null)
    if (await saveNow()) onAdded()
  }

  return (
    <Box>
      <Box
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault()
          setDragging(false)
          uploadFiles(e.dataTransfer.files)
        }}
        sx={{
          border: '2px dashed',
          borderColor: dragging ? 'primary.main' : 'divider',
          borderRadius: 2,
          p: 4,
          textAlign: 'center',
          cursor: 'pointer',
        }}
      >
        <Typography color="text.secondary">点击选择或拖入图片 / 视频文件（会复制到 assets/local/）</Typography>
        <input
          ref={inputRef}
          type="file"
          hidden
          multiple
          accept="image/*,video/*"
          onChange={(e) => e.target.files && uploadFiles(e.target.files)}
        />
      </Box>
      {status && (
        <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
          {status}
        </Typography>
      )}
    </Box>
  )
}
