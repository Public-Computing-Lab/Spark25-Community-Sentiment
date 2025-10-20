/**
 * App.tsx
 *
 * This file contains the main application component which manages routing and layout for the app.
 * The component sets up:
 * - Route handling for different views (e.g., Chat and Map pages).
 * - A global `MapProvider` that may provides context for map usage.
 * - An MUI-based layout structure with a `Navbar` at the bottom and a flexible main content area.
 * - Centralized layout with a bottom sticky navbar.
 * - Dynamic routing for different pages within the app.
 */

import mapboxgl from "mapbox-gl";

// Set up Mapbox access token from environment variables
mapboxgl.accessToken = import.meta.env.VITE_MAPBOX_TOKEN || "";

// Import necessary routing and UI components
import { Routes, Route } from "react-router-dom";
import { CssBaseline, Box } from "@mui/material";

// Import custom components
import Navbar from "./components/Navbar";
import Chat from "./pages/Chat";
import Map from "./pages/Map";
import MapProvider from "./components/MapProvider";

/**
 * App
 *
 * The main entry point of the application. This component sets up routing, layout, and overall structure of the app.
 * It includes the main chat interface, routing to the Map page, and provides consistent layout styling.
 *
 * ### Layout:
 * - A `MapProvider` is used to provide context related to maps throughout the app.
 * - A responsive layout with a sticky `Navbar` at the bottom and flexible content in the main body.
 * - Routing is handled with `react-router-dom`, displaying either the `Chat` or `Map` components based on the current route.
 */
function App() {
  return (
    // Wrap app in MapProvider to manage map context or state globally
    <MapProvider>
      {/* MUI's CssBaseline to normalize styles across browsers */}
      <CssBaseline />

      {/* Main app layout container */}
      <Box
        sx={{
          display: "flex",
          flexDirection: "column",
          minHeight: "100vh",
          bgcolor: "background.default",
          color: "text.primary",
        }}
      >
        {/* Main content container, takes up the available space */}
        <Box component="main" sx={{ flexGrow: 1 }}>
          <Routes>
            <Route path="/" element={<Chat />} />
            <Route path="/map" element={<Map />} />
          </Routes>
        </Box>

        {/* Navbar sticks at bottom */}
        <Navbar />
      </Box>
    </MapProvider>
  );
}

export default App;
