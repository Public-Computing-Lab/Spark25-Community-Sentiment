import { Routes, Route } from 'react-router-dom'
import Navbar from './components/Navbar'
import Chat from './pages/Chat'
import Template from './pages/Template'
import Map from './pages/Map'

function App() {
  return (
    <>
      <Routes>
        <Route path="/" element={<Template />} />
        <Route path="/chat" element={<Chat />} />
        <Route path="/map" element={<Map />} />
      </Routes>
      <Navbar />
    </>
  )
}

export default App
