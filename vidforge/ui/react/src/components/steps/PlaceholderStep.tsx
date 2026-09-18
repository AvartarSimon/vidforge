import { Box, Typography } from '@mui/material'

export function PlaceholderStep({ n, label }: { n: number; label: string }) {
  return (
    <Box sx={{ p: 6, textAlign: 'center' }}>
      <Typography variant="h6" color="text.secondary">
        第 {n} 步 · {label}
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
        即将推出。
      </Typography>
    </Box>
  )
}
