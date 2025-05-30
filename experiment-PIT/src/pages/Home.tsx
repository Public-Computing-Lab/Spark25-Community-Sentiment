import { Box, Typography } from '@mui/material'

function Home() {
  return (
    <Box
      sx={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
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
        How the Community Feels
      </Typography>
    </Box>
  )
}

export default Home
