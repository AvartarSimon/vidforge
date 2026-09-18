import { Accordion, AccordionSummary, Typography } from '@mui/material'
import ExpandMoreIcon from '@mui/icons-material/ExpandMore'

// Stub only — the YouTube competitor-research flow (/api/research/*) is deferred out of phase 1
// (see the plan doc): it's a secondary, opt-in panel even in the old frontend and isn't required
// to prove the core "write → split → edit → save" loop. Kept as a visible placeholder so the
// layout doesn't need rework once it's built for real.
export function ResearchPanel() {
  return (
    <Accordion disabled>
      <AccordionSummary expandIcon={<ExpandMoreIcon />}>
        <Typography variant="body2">🔎 选题助手（即将推出）：看 YouTube 上同类视频的数据，让 AI 判断值不值得做</Typography>
      </AccordionSummary>
    </Accordion>
  )
}
