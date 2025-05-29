import { AppBar, Toolbar, Link as MuiLink } from '@mui/material';
import { Link as RouterLink } from 'react-router-dom';

const navLinks = [
  { label: 'Home', to: '/' },
  { label: 'Map', to: '/map' },
  { label: 'Chat', to: '/chat' },
];

function NavLink({ to, children }: { to: string; children: React.ReactNode }) {
  return (
    <MuiLink
      component={RouterLink}
      to={to}
      underline="hover"
      color="text.primary"
      sx={{ fontWeight: 'bold' }}
    >
      {children}
    </MuiLink>
  );
}

function Navbar() {
  return (
    <AppBar
      position="sticky"
      color="default"
      sx={{ top: 'auto', bottom: 0, bgcolor: 'background.paper'}}
    >
      <Toolbar sx={{ justifyContent: 'center', gap: 3 }}>
        {navLinks.map(({ label, to }) => (
          <NavLink key={to} to={to}>
            {label}
          </NavLink>
        ))}
      </Toolbar>
    </AppBar>
  );
}

export default Navbar;
