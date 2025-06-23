import React from "react";
import Box from "@mui/material/Box";
import MapBase from "./MapBase";
import type {
  Feature,
  Geometry,
  GeoJsonProperties,
  FeatureCollection,
} from "geojson";
import type { Layer } from "mapbox-gl";

interface ChatMapPreviewProps {
  center: [number, number];
  layers: Feature<Geometry, GeoJsonProperties>[]; // raw features passed from chat response
}

const ChatMapPreview: React.FC<ChatMapPreviewProps> = ({ center, layers }) => {
  const featureCollection: FeatureCollection<Geometry, GeoJsonProperties> = {
    type: "FeatureCollection",
    features: layers,
  };

  const previewLayer: Layer = {
    id: "chat-preview-layer",
    type: "circle",
    source: "chat-preview",
    paint: {
      "circle-radius": 6,
      "circle-color": "#1976d2",
      "circle-stroke-color": "#fff",
      "circle-stroke-width": 2,
    },
  };

  const mapLayers = [
    {
      id: "chat-preview",
      data: featureCollection,
      layer: previewLayer,
    },
  ];

  return (
    <Box
      sx={{
        width: "100%",
        height: 300,
        borderRadius: 2,
        overflow: "hidden",
        mt: 1,
        boxShadow: 2,
        border: "1px solid",
        borderColor: "divider",
      }}
    >
      <MapBase center={center} layers={mapLayers} />
    </Box>
  );
};

export default ChatMapPreview;
