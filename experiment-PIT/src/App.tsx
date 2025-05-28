import { Routes, Route } from 'react-router-dom'
import Navbar from './components/Navbar'
import Chat from './pages/Chat'
import Template from './pages/Template'

function App() {
  return (
    <>
      <Routes>
        <Route path="/" element={<Template />} />
        <Route path="/chat" element={<Chat />} />
      </Routes>
      <Navbar />
    </>
  )
}

export default App
