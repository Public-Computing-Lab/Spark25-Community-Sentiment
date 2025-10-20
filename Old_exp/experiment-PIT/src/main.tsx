import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { CssBaseline, ThemeProvider, createTheme, responsiveFontSizes } from '@mui/material'
import App from './App'

let theme = createTheme({
  typography: {
    fontFamily: 'system-ui, Avenir, Helvetica, Arial, sans-serif',
  },
  palette: {
    background: {
      default: '#ffffff',
    },
    text: {
      primary: '#000000',
    },
    primary: {
      main: '#646cff',
    },
    secondary: {
      main: '#535bf2',
    },
  },
})

theme = responsiveFontSizes(theme)

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <BrowserRouter basename="/experimenting/8">
        <App />
      </BrowserRouter>
    </ThemeProvider>
  </StrictMode>,
)
