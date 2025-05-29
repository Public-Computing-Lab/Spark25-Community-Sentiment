import { useState } from 'react'
import { Box, Button, Typography, Link } from '@mui/material'
import reactLogo from '../assets/react.svg'
import viteLogo from '/vite.svg'

function Template() {
  const [count, setCount] = useState(0)

  return (
    <Box
      sx={{
        maxWidth: '1280px',
        margin: '0 auto',
        p: 4,
        textAlign: 'center',
        height: '100vh',
      }}
    >
      <Box>
        <Link href="https://vite.dev" target="_blank">
          <Box
            component="img"
            src={viteLogo}
            alt="Vite logo"
            sx={{
              height: '6em',
              p: '1.5em',
              transition: 'filter 300ms',
              '&:hover': {
                filter: 'drop-shadow(0 0 2em #646cffaa)',
              },
            }}
          />
        </Link>
        <Link href="https://react.dev" target="_blank">
          <Box
            component="img"
            src={reactLogo}
            alt="React logo"
            sx={{
              height: '6em',
              p: '1.5em',
              transition: 'filter 300ms',
              animation: 'logo-spin 20s linear infinite',
              '&:hover': {
                filter: 'drop-shadow(0 0 2em #61dafbaa)',
              },
              '@media (prefers-reduced-motion: reduce)': {
                animation: 'none',
              },
            }}
          />
        </Link>
      </Box>

      <Typography variant="h3" gutterBottom>
        Vite + React
      </Typography>

      <Box sx={{ p: 4 }}>
        <Button variant="contained" onClick={() => setCount((c) => c + 1)}>
          count is {count}
        </Button>
        <Typography sx={{ mt: 2 }}>
          Edit <code>src/App.tsx</code> and save to test HMR
        </Typography>
      </Box>

      <Typography sx={{ color: '#888' }}>
        Click on the Vite and React logos to learn more
      </Typography>

      {/* Keyframes for logo spin */}
      <style>
        {`
          @keyframes logo-spin {
            from { transform: rotate(0deg); }
            to { transform: rotate(360deg); }
          }
        `}
      </style>
    </Box>
  )
}

export default Template
