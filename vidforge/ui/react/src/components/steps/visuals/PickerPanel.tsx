import { useState } from 'react'
import { Card, CardContent, Tab, Tabs } from '@mui/material'
import type { Segment } from '../../../api/types'
import { SearchTab } from './SearchTab'
import { UploadTab } from './UploadTab'

// "动画（Remotion）" and "🎥 我的镜头" tabs are deferred out of this pass — they need their own
// substantial UI (Remotion props editor, footage-library browser) and aren't required to prove
// the core loop (search/upload a clip → it shows up on the segment). See the commit message.
export function PickerPanel({ seg, segId, onAdded }: { seg: Segment; segId: string; onAdded: () => void }) {
  const [tab, setTab] = useState<'search' | 'upload'>('search')

  return (
    <Card variant="outlined">
      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ borderBottom: '1px solid', borderColor: 'divider' }}>
        <Tab value="search" label="搜索素材" />
        <Tab value="upload" label="本地文件" />
        <Tab value="anim" label="动画（即将推出）" disabled />
        <Tab value="me" label="🎥 我的镜头（即将推出）" disabled />
      </Tabs>
      <CardContent>
        {tab === 'search' ? <SearchTab seg={seg} segId={segId} onAdded={onAdded} /> : <UploadTab segId={segId} onAdded={onAdded} />}
      </CardContent>
    </Card>
  )
}
