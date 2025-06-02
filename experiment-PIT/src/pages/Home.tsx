import { Box, Typography } from '@mui/material'
import { BOTTOM_NAV_HEIGHT } from "../constants/layoutConstants"

function Home() {
  return (
    <Box
      sx={{
        display: 'flex',
        flexDirection: 'column',
        height: `calc(100vh - ${BOTTOM_NAV_HEIGHT}px)`,
        width: '100%',
        bgcolor: 'background.paper',
        color: 'text.primary',
        overflow: 'hidden',
        position: 'relative',
        p: 2,
      }}
    >
      <Typography variant="h4" component="h1" mb={2}>
        Home
      </Typography>
      <Typography variant="h1" component="h1" mb={2}>
        What is Dorchester Like?
      </Typography>
    </Box>
  )
}

export default Home
