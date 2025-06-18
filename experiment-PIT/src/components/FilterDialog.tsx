import { Box, Typography, Button, Drawer, Stack, Slider, FormGroup, FormControlLabel, Checkbox } from '@mui/material';
import { useState } from 'react';
import FilterAltOutlinedIcon from '@mui/icons-material/FilterAltOutlined';
import { useMap } from "../components/useMap.tsx";


function FilterDialog({ 
    layers,
    onSelectionChange, //callback function
    onSliderChange
} : {
    layers: string[]
    onSelectionChange : (selectedLayers: string[]) => void
    onSliderChange : (selectedYearsSlider: number[]) => void
}) {
  const [open, setOpen] = useState(false);
  const { selectedData, selectedYears, setSelectedData, setSelectedYears } = useMap(); // Access mapRef and mapContainerRef from context
  

  const toggleFilter = (newOpen: boolean) => () => {
    setOpen(newOpen);
  };

  const handleSelectData = (layerSelected: string) => () => {
    setSelectedData((prevSelectedData) => {
        const filteredData = prevSelectedData.includes(layerSelected) ? prevSelectedData.filter(element => element !== layerSelected) : [...prevSelectedData, layerSelected];
        //if layer is already in prevSelectedData, filter it out, otherwise, add it.
        onSelectionChange(filteredData);
        //pass the new array up to parent through onSelectionChange
        return filteredData;
    });
  };

  const handleSelectYears = (_event: Event, newValues: number[]) => {
    setSelectedYears(() => {
      onSliderChange(newValues);
      console.log(newValues);
      return newValues;
    });
    
  }

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
                value={selectedYears}
                onChange={handleSelectYears}
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
          <FormGroup>
            {layers.map((layer) => (
               <FormControlLabel 
                key={layer} 
                control={
                  <Checkbox 
                    checked={selectedData.includes(layer)} 
                    onChange={handleSelectData(layer)}
                    />
                } 
                label={layer} />
            ))}
          </FormGroup>
        </Box>
        
      </Drawer>

    </div>
    
    
  )

}

export default FilterDialog;