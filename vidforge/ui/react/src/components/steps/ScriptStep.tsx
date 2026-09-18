import { useEffect, useState } from 'react'
import { Card, CardContent, Chip, Stack, TextField, Typography } from '@mui/material'
import { apiGet } from '../../api/client'
import type { Category } from '../../api/types'
import { useProject } from '../../state/ProjectContext'
import { AiGeneratePanel } from './script/AiGeneratePanel'
import { ResearchPanel } from './script/ResearchPanel'
import { ScriptEditorPanel } from './script/ScriptEditorPanel'

export function ScriptStep() {
  const { raw, patch } = useProject()
  const [categories, setCategories] = useState<Category[]>([])

  useEffect(() => {
    apiGet<{ categories: Category[] }>('/api/categories')
      .then((j) => setCategories(j.categories))
      .catch(() => setCategories([]))
  }, [])

  if (!raw) return null
  const category = categories.find((c) => c.id === raw.category)

  return (
    <Stack spacing={2}>
      <Card variant="outlined">
        <CardContent>
          <Stack direction="row" spacing={2} flexWrap="wrap" useFlexGap>
            <TextField
              label={
                <span>
                  视频标题{category && <Chip label={category.name} size="small" sx={{ ml: 1 }} />}
                </span>
              }
              value={raw.title || ''}
              onChange={(e) =>
                patch((r) => {
                  r.title = e.target.value
                })
              }
              sx={{ minWidth: 280, flexGrow: 1 }}
            />
            <TextField
              label="封面文字（\n 换行）"
              value={(raw.thumbnail_text || '').replace(/\n/g, '\\n')}
              onChange={(e) =>
                patch((r) => {
                  r.thumbnail_text = e.target.value.replace(/\\n/g, '\n')
                })
              }
              sx={{ minWidth: 280, flexGrow: 1 }}
            />
          </Stack>
          {category && (category.topic_notes || category.insights) && (
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
              {[category.topic_notes && `要讲什么：${category.topic_notes}`, category.insights && `心得：${category.insights}`]
                .filter(Boolean)
                .join(' · ')}
            </Typography>
          )}
        </CardContent>
      </Card>
      <ResearchPanel />
      <AiGeneratePanel categories={categories} />
      <ScriptEditorPanel />
    </Stack>
  )
}
