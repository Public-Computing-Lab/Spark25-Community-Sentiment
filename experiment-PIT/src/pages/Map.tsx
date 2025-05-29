import { Box, Typography } from '@mui/material'

function Map() {
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
        map map
      </Typography>
    </Box>
  )
}

export default Map
