import * as React from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import BottomNavigation from '@mui/material/BottomNavigation';
import BottomNavigationAction from '@mui/material/BottomNavigationAction';
import Paper from '@mui/material/Paper';

import HomeIcon from '@mui/icons-material/Home';
import LocationOnIcon from '@mui/icons-material/LocationOn';
import ForumIcon from '@mui/icons-material/Forum';

import { BOTTOM_NAV_HEIGHT } from '../constants/layoutConstants';

const navLinks = [
  { label: 'Home', to: '/', icon: <HomeIcon /> },
  { label: 'Map', to: '/map', icon: <LocationOnIcon /> },
  { label: 'Chat', to: '/chat', icon: <ForumIcon /> },
];

function Navbar() {
  const navigate = useNavigate();
  const location = useLocation();

  const currentIndex = navLinks.findIndex(link => link.to === location.pathname);
  const [value, setValue] = React.useState(currentIndex !== -1 ? currentIndex : 0);

  const handleChange = (_event: React.SyntheticEvent, newValue: number) => {
    setValue(newValue);
    navigate(navLinks[newValue].to);
  };

  return (
    <Paper sx={{ position: 'fixed', bottom: 0, left: 0, right: 0, height: BOTTOM_NAV_HEIGHT }} elevation={3}>
      <BottomNavigation showLabels value={value} onChange={handleChange}>
        {navLinks.map(({ label, icon }, index) => (
          <BottomNavigationAction key={index} label={label} icon={icon} />
        ))}
      </BottomNavigation>
    </Paper>
  );
}

export default Navbar;
