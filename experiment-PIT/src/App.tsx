import { Routes, Route } from 'react-router-dom'
import { Box, CssBaseline } from '@mui/material'
import Navbar from './components/Navbar'
import Chat from './pages/Chat'
import Template from './pages/Home'
import Map from './pages/Map'

function App() {
  return (
    <>
      <CssBaseline />
      <Box
        sx={{
          display: 'flex',
          flexDirection: 'column',
          minHeight: '100vh', 
          bgcolor: 'background.default',
          color: 'text.primary',
        }}
      >
        {/* Main content grows to fill available space */}
        <Box component="main" sx={{ flexGrow: 1 }}>
          <Routes>
            <Route path="/" element={<Template />} />
            <Route path="/chat" element={<Chat />} />
            <Route path="/map" element={<Map />} />
          </Routes>
        </Box>

        {/* Navbar sticks at bottom */}
        <Navbar />
      </Box>
    </>
  )
}

export default App
