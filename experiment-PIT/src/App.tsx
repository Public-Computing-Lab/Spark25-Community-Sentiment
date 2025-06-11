import { Routes, Route } from "react-router-dom";
import { CssBaseline, Box, ThemeProvider } from "@mui/material";
import { customTheme } from "./assets/theme";
import Navbar from "./components/Navbar";
import Chat from "./pages/Chat";
// import Home from "./pages/Home";
import Map from "./pages/Map";

function App() {
  return (
    
      <ThemeProvider theme={customTheme}>
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
            <Route path="/map" element={<Map />} />
          </Routes>
        </Box>

        {/* Navbar sticks at bottom */}
        <Navbar />
      </Box>
      </ThemeProvider>
   
  );
}

export default App;
