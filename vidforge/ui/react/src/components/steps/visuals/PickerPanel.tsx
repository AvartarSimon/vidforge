import { useState } from 'react'
import { Card, CardContent, Tab, Tabs } from '@mui/material'
import type { Segment } from '../../../api/types'
import { AnimTab } from './AnimTab'
import { MeTab } from './MeTab'
import { SearchTab } from './SearchTab'
import { UploadTab } from './UploadTab'

type PickerTab = 'image' | 'video' | 'upload' | 'anim' | 'me'

export function PickerPanel({ seg, segId, onAdded }: { seg: Segment; segId: string; onAdded: () => void }) {
  const [tab, setTab] = useState<PickerTab>('image')

  return (
    <Card variant="outlined">
      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ borderBottom: '1px solid', borderColor: 'divider' }}>
        <Tab value="image" label="搜图片" />
        <Tab value="video" label="搜视频" />
        <Tab value="upload" label="本地文件" />
        <Tab value="anim" label="动画（Remotion）" />
        <Tab value="me" label="🎥 我的镜头" />
      </Tabs>
      <CardContent>
        {tab === 'image' && <SearchTab seg={seg} segId={segId} kind="image" onAdded={onAdded} />}
        {tab === 'video' && <SearchTab seg={seg} segId={segId} kind="video" onAdded={onAdded} />}
        {tab === 'upload' && <UploadTab segId={segId} onAdded={onAdded} />}
        {tab === 'anim' && <AnimTab seg={seg} segId={segId} />}
        {tab === 'me' && <MeTab segId={segId} onAdded={onAdded} />}
      </CardContent>
    </Card>
  )
}
