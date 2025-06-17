import { Routes, Route, useLocation } from "react-router-dom";
import { CssBaseline, Box } from "@mui/material";
import Navbar from "./components/Navbar";
import Chat from "./pages/Chat";
// import Home from "./pages/Home";
import Map from "./pages/Map";
import { MapProvider } from './components/MapProvider'

function App() {
  const location = useLocation();

  return (
    <MapProvider>
      <CssBaseline />
      <Box
        sx={{
          display: "flex",
          flexDirection: "column",
          minHeight: "100vh",
          bgcolor: "background.default",
          color: "text.primary",
        }}
      >
        {/* Main content grows to fill available space */}
        <Box component="main" sx={{ flexGrow: 1 }}>
          <Routes>
            {/* <Route path="/" element={<Template />} /> */}
            <Route path="/" element={<Chat />} />
            <Route path="/map" element={<div />} />
          </Routes>
        </Box>
        <Box
          sx={{
            display: location.pathname === "/map" ? "block" : "none", // Toggle visibility based on route
            position: "absolute",
            top: 0,
            left: 0,
            width: "100vw",
            height: "100vh",
            zIndex: 0,
          }}
        >
          <Map />
        </Box>

        {/* Navbar sticks at bottom */}
        <Navbar />
      </Box>
    </MapProvider>
  );
}

export default App;
