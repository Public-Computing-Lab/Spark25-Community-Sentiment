/**
 * navbar.tsx
 *
 * This file provides a responsive bottom navigation component for navigating between the pages in the app.
 *
 * It uses Material UI components and React Router to manage navigation state and handle route changes.
 * The component highlights the currently active page and provides hover effects for better user interaction.
 */

import * as React from "react";
import { useNavigate, useLocation } from "react-router-dom";
import BottomNavigation from "@mui/material/BottomNavigation";
import BottomNavigationAction from "@mui/material/BottomNavigationAction";
import Paper from "@mui/material/Paper";
import { colorPalette } from "../assets/palette";

import LocationOnIcon from "@mui/icons-material/LocationOn";
import ForumIcon from "@mui/icons-material/Forum";

import { BOTTOM_NAV_HEIGHT } from "../constants/layoutConstants";

// Define the navigation links with corresponding labels, icons, and paths
const navLinks = [
  { label: "Chat", to: "/", icon: <ForumIcon /> },
  { label: "Map", to: "/map", icon: <LocationOnIcon /> },
];

/**
 * Navbar
 *
 * A functional React component that renders a fixed bottom navigation bar
 * allowing users to switch between "Chat" and "Map" views.
 *
 * ### Dependencies:
 * - `useNavigate` and `useLocation` from `react-router-dom` for routing control.
 * - `BottomNavigation`, `BottomNavigationAction`, and `Paper` from Material UI.
 * - `colorPalette` from local theme assets for custom styling.
 * - `BOTTOM_NAV_HEIGHT` for consistent layout height across the app.
 *
 * ### State:
 * - `value` (number): Tracks the currently selected navigation index.
 *
 * ### Returns:
 * - A JSX element that renders the bottom navigation bar with interactive tabs.
 *
 * ### Side Effects:
 * - Navigates to a new route on tab change using `navigate()`.
 *
 * ### Raises:
 * - None explicitly. However, assumes `location.pathname` matches one of the `navLinks` paths.
 */
function Navbar() {
  const navigate = useNavigate(); // Hook to programmatically navigate between routes
  const location = useLocation(); // Hook to access the current route path

  // Determine the index of the current route in the navLinks array
  const currentIndex = navLinks.findIndex(
    (link) => link.to === location.pathname
  );

  // State to keep track of the selected navigation index
  const [value, setValue] = React.useState(
    currentIndex !== -1 ? currentIndex : 0
  );

  // Handle navigation when a user selects a different tab
  const handleChange = (_event: React.SyntheticEvent, newValue: number) => {
    setValue(newValue); // Update local state
    navigate(navLinks[newValue].to); // Navigate to the selected route
  };

  return (
    <Paper
      // Fixed Paper element at the bottom of the screen
      sx={{
        position: "fixed",
        bottom: 0,
        left: 0,
        right: 0,
        height: BOTTOM_NAV_HEIGHT,
      }}
      elevation={3} // Adds a shadow effect for depth
    >
      <BottomNavigation
        showLabels
        value={value}
        onChange={handleChange}
        sx={{
          bgcolor: colorPalette.background, // light blue background
          "& .Mui-selected": {
            color: colorPalette.dark, // navy blue when selected
          },
          "& .MuiBottomNavigationAction-root": {
            color: colorPalette.dark, // default black
            transition: "color 5s ease",
            "&:hover": {
              color: "#026BC4", // bright blue on hover
            },
          },
        }}
      >
        {/* Render each navigation action based on navLinks array */}
        {navLinks.map(({ label, icon }, index) => (
          <BottomNavigationAction key={index} label={label} icon={icon} />
        ))}
      </BottomNavigation>
    </Paper>
  );
}

export default Navbar;
