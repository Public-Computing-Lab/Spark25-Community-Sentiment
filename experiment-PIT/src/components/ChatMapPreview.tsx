import { Box, Typography } from "@mui/material";
import MapBase from "./MapBase";
import { Link } from "react-router-dom";

type ChatMapPreviewProps = {
  streetName: string;
  lat: number;
  lon: number;
  showLayers: {
    shots?: boolean;
    data311?: boolean;
    assets?: boolean;
  };
};

function ChatMapPreview({
  streetName,
  lat,
  lon,
  showLayers,
}: ChatMapPreviewProps) {
  return (
    <Link
      to={`/map?lat=${lat}&lon=${lon}&layers=${Object.keys(showLayers).join(
        ","
      )}`}
      style={{ textDecoration: "none" }}
    >
      <Box
        sx={{
          display: "flex",
          flexDirection: "column",
          p: 1,
          bgcolor: "background.paper",
          borderRadius: 2,
          boxShadow: 1,
          maxWidth: "300px",
          cursor: "pointer",
          "&:hover": {
            boxShadow: 4,
          },
        }}
      >
        <Typography variant="caption" sx={{ mb: 0.5 }}>
          Map preview: {streetName}
        </Typography>
        <MapBase
          center={[lon, lat]}
          zoom={15}
          showLayers={showLayers}
          height="200px"
        />
      </Box>
    </Link>
  );
}

export default ChatMapPreview;
