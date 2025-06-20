import { Box, Typography, Stack } from "@mui/material";

const LegendItem = ({
  color,
  label,
  shape = "circle",
}: {
  color: string;
  label: string;
  shape?: "circle" | "line";
}) => (
  <Box sx={{ display: "flex", alignItems: "center" }}>
    <Box
      sx={{
        width: shape === "line" ? 14 : 10,
        height: shape === "circle" ? 10 : 4,
        backgroundColor: color,
        borderRadius: shape === "circle" ? "50%" : 0,
        mr: 1,
        flexShrink: 0,
      }}
    />
    <Typography sx={{ fontSize: 13 }}>{label}</Typography>
  </Box>
);

export default function Key() {
  return (
    <Box
      sx={{
        maxWidth: 240,          
        bgcolor: "#E9F4FF",    
        boxShadow: "0 4px 12px rgba(0,0,0,0.25)",
        borderRadius: 3,
        p: 1.25,
        overflowY: "auto",
        maxHeight: "26vh",        // never taller than a quarter screen
      }}
    >
      <Typography
        sx={{ fontWeight: 700, mb: 0.75, fontSize: 15 }}
      >
        Legend
      </Typography>

      <Stack spacing={0.75}>
        <LegendItem color="#880808" label="Gun Violence Incidents" />
        <LegendItem color="#228B22" label="Assets" />
        <LegendItem color="#FFC300" label="311 Requests" />
        <LegendItem color="#82aae7" label="TNT Border" shape="line" />
      </Stack>
    </Box>
  );
}
