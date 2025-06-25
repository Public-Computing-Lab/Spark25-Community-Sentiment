import React from "react";
import { useNavigate } from "react-router-dom";
import { Box, Typography, ButtonBase } from "@mui/material";
import MapBase from "./MapBase";
import type {
  Feature,
  Geometry,
  GeoJsonProperties,
  FeatureCollection,
} from "geojson";
import type { Layer } from "mapbox-gl";
import mapboxgl from "mapbox-gl";

interface ChatMapPreviewProps {
  center: [number, number]; // lon, lat
  layers?: Feature<Geometry, GeoJsonProperties>[];
  marker?: [number, number, string]; // [lon, lat, label]
}

const ChatMapPreview: React.FC<ChatMapPreviewProps> = ({
  center,
  layers,
  marker,
}) => {
  const navigate = useNavigate();
  const handleClick = () => {
    const filters = {
      location: [center[1], center[0]],
    };

    navigate("/map", { state: { filters } });
  };

  const safeLayers = Array.isArray(layers) ? layers : [];
  const features = [...safeLayers];

  let markerLabelLayer: Layer | undefined;

  if (Array.isArray(marker) && marker.length === 3) {
    const [lon, lat, label] = marker;

    const markerFeature: Feature<Geometry, GeoJsonProperties> = {
      type: "Feature",
      geometry: {
        type: "Point",
        coordinates: [lon, lat],
      },
      properties: {
        isMarker: true,
        label,
      },
    };

    features.push(markerFeature);

    markerLabelLayer = {
      id: "chat-marker-label",
      type: "symbol",
      source: "chat-preview",
      layout: {
        "text-field": ["get", "label"],
        "text-font": ["Open Sans Semibold", "Arial Unicode MS Bold"],
        "text-offset": [0, 1.5],
        "text-anchor": "top",
      },
      paint: {
        "text-color": "#333",
      },
      filter: ["==", ["get", "isMarker"], true],
    };
  }

  const featureCollection: FeatureCollection<Geometry, GeoJsonProperties> = {
    type: "FeatureCollection",
    features,
  };

  const previewLayer: Layer = {
    id: "chat-preview-layer",
    type: "circle",
    source: "chat-preview",
    paint: {
      "circle-radius": ["case", ["==", ["get", "isMarker"], true], 8, 6],
      "circle-color": [
        "case",
        ["==", ["get", "isMarker"], true],
        "#ff5722",
        "#1976d2",
      ],
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

  if (markerLabelLayer) {
    mapLayers.push({
      id: "chat-marker-label",
      data: featureCollection,
      layer: markerLabelLayer,
    });
  }

  return (
    <ButtonBase
      onClick={handleClick}
      sx={{
        width: "100%",
        height: 300,
        borderRadius: 2,
        overflow: "hidden",
        mt: 1,
        boxShadow: 2,
        border: "1px solid",
        borderColor: "divider",
        display: "block", // so the child (MapBase) fills the button
        textAlign: "left", // prevent text centering
        p: 0, // no extra padding
      }}
    >
      <MapBase center={center} layers={mapLayers} zoom={15.8} />
    </ButtonBase>
  );
};

export default ChatMapPreview;
