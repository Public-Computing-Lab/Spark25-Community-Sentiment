import {
  Box,
  Typography,
  Drawer,
  Stack,
  Slider,
  FormGroup,
  FormControlLabel,
  Checkbox,
  Fab,
} from "@mui/material";
import { useState } from "react";
import FilterAltOutlinedIcon from "@mui/icons-material/FilterAltOutlined";
import { BOTTOM_NAV_HEIGHT } from "../constants/layoutConstants";

interface FilterDialogProps {
  layers: string[];
  onSelectionChange: (layers: string[]) => void;
  onSliderChange: (years: number[]) => void;
}

export default function FilterDialog({
  layers,
  onSelectionChange,
  onSliderChange,
}: FilterDialogProps) {
  const [open, setOpen] = useState(false);
  const [selectedData, setSelectedData] = useState<string[]>(["Community Assets"]);
  const [selectedYears, setSelectedYears] = useState<number[]>([2018, 2024]);

  /* ——— handlers ——— */
  const toggleFilter = (newOpen: boolean) => () => setOpen(newOpen);

  const handleSelectData = (layer: string) => () => {
    setSelectedData((prev) => {
      const next = prev.includes(layer) ? prev.filter((l) => l !== layer) : [...prev, layer];
      onSelectionChange(next);
      return next;
    });
  };

  const handleSelectYears = (_: Event, newVals: number[]) => {
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
