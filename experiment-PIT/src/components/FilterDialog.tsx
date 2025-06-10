import { Box, Typography, Button, Drawer, Stack, Slider } from '@mui/material';
import { useState } from 'react';
import FilterAltOutlinedIcon from '@mui/icons-material/FilterAltOutlined';


function FilterDialog({ 
    layers,
} : {
    layers: string[]
}) {
  const [open, setOpen] = useState(false);

  const toggleFilter = (newOpen: boolean) => () => {
    setOpen(newOpen);
  };

  return (
    <div>
      <Button 
      onClick={toggleFilter(true)}
      variant="contained" 
      sx={{
        position: 'absolute', 
        right: '1em', 
        bottom: '4em', 
        borderRadius: '75%', 
        width: '50px', // Explicitly set the width
        height: '50px', // Explicitly set the height
        minWidth: '50px', // Prevent stretching
        }}>
        <FilterAltOutlinedIcon />
      </Button>
      <Drawer anchor="bottom" open={open} onClose={toggleFilter(false)}>
        <Box sx={{margin: '1em'}}>
          <Typography>
            Time Range
          </Typography>
          <Stack sx={{ display: 'flex', flexDirection: 'row', alignItems: 'center', margin: 1 }}>
              2018
              <Slider
                step={1}
                marks
                min={2018}
                valueLabelDisplay="auto"
                max={2024}
                sx={{
                  marginLeft: '1em',
                  marginRight: '1em'
                }}
              />
              2024
          </Stack>
          <Typography>
            Data Type
          </Typography>
          

        </Box>
        
      </Drawer>

    </div>
    
    
  )

}

export default FilterDialog;