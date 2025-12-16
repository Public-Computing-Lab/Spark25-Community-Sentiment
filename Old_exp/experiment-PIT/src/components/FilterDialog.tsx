/**
 * FilterDialog.tsx
 * This file host the UI of the filter in the map interface. 
 * Sends data up to the Map.tsx component about which data layers and years are being filtered.
 */

import { Box, Typography, Drawer, Stack, Slider, FormGroup, FormControlLabel, Checkbox, Fab } from '@mui/material';
import { useState } from 'react';
import FilterAltOutlinedIcon from '@mui/icons-material/FilterAltOutlined';
import { useMap } from "../components/useMap.tsx";
import { BOTTOM_NAV_HEIGHT } from "../constants/layoutConstants";


function FilterDialog({ 
    layers,
    onSelectionChange, //callback function
    onSliderChange
} : {
    layers: string[]
    onSelectionChange : (selectedLayers: string[]) => void
    onSliderChange : (selectedYears: number[]) => void
}) {
  const [open, setOpen] = useState(false);
  const { selectedData, selectedYears, setSelectedData, setSelectedYears } = useMap(); // Access these variables

  const toggleFilter = (newOpen: boolean) => () => {
     /** 
     * Functionality to open and close filter, triggered by onClose()
     * Args/Dependencies: newOpen (boolean)
     * Returns: N/A
    */
    setOpen(newOpen);
  };

  const handleSelectData = (layer: string) => () => {
    /** 
     * Functionality to updated which data layers are being filtered
     * Updates the checked boxes accordingly
     * Args/Dependencies: layer: string
     * Returns: next: string[] (the updated set of layers being filtered)
    */
    setSelectedData((prev) => {
      const next = prev.includes(layer) ? prev.filter((l) => l !== layer) : [...prev, layer];
      onSelectionChange(next);
      return next;
    });
  };

  const handleSelectYears = (_: Event, newVals: number[]) => {
    /** 
     * Functionality to updated which years are being filtered
     * Updates the slider accordingly
     * Args/Dependencies: newVals: number[]
     * Returns: N/A
    */
    setSelectedYears(newVals);
    onSliderChange(newVals);
  };

  /* ——— render ——— */
  return (
    <>
      {/* Floating circular filter button */}
      <Fab
        onClick={toggleFilter(true)}
        sx={{
          position: "absolute",
          right: 16,
          bottom: `calc(${BOTTOM_NAV_HEIGHT}px + 24px)`,
          bgcolor: "#02447C",
          color: "#fff",
          "&:hover": { bgcolor: "#01335d" },
        }}
      >
        <FilterAltOutlinedIcon />
      </Fab>

      {/* Bottom-sheet drawer */}
      <Drawer
      
        anchor="bottom"
        open={open}
        onClose={toggleFilter(false)}
        PaperProps={{
          sx: {
            bgcolor: "#D6ECFF",                        // bright blue body
            borderTopLeftRadius: 20,
            borderTopRightRadius: 20,
            pb: 4,
          },
        }}
        
      >
        <Box sx={{ px: 3, pt: 3 }}>
          {/* Year slider */}
          <Typography sx={{ fontWeight: 600, mb: 1 }}>Time Range</Typography>
          <Stack direction="row" alignItems="center" sx={{ mb: 3 }}>
            2018
            <Slider
              step={1}
              marks
              min={2018}
              max={2024}
              value={selectedYears}
              onChange={handleSelectYears}
              valueLabelDisplay="auto"
              sx={{
                mx: 2,
                color: "#02447C",
                "& .MuiSlider-thumb": { boxShadow: "0 0 0 3px rgba(2,68,124,0.25)" },
              }}
            />
            2024
          </Stack>

          {/* Layer check-boxes */}
          <Typography sx={{ fontWeight: 600, mb: 1 }}>Data Type</Typography>
          <FormGroup>
            {layers.map((layer) => (
              <FormControlLabel
                key={layer}
                control={
                  <Checkbox
                    checked={selectedData.includes(layer)}
                    onChange={handleSelectData(layer)}
                    sx={{
                      color: "#02447C",
                      "&.Mui-checked": { color: "#02447C" },
                    }}
                  />
                }
                label={layer}
              />
            ))}
          </FormGroup>
        </Box>
      </Drawer>
    </>
  );
}

export default FilterDialog;