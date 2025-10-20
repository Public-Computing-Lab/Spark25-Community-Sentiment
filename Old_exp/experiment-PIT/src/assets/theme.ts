import { createTheme } from "@mui/material/styles";

export const customTheme = createTheme({
  typography: {
    fontFamily: "'Inter', 'Helvetica Neue', Arial, sans-serif",
    fontSize: 14,
    body1: {
      fontWeight: 400,
      lineHeight: 1.6,
    },
    body2: {
      fontSize: "0.9rem",
    },
    h6: {
      fontWeight: 600,
      fontSize: "1.05rem",
    },
    caption: {
      fontSize: "0.75rem",
      fontWeight: 300,
    },
  },
});
