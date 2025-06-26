/**
 * ChatMapPreview.tsx
 *
 * This file provides a map preview component that displays a map with a specific center, optional layers, and a marker.
 * The component supports:
 * - Rendering a map with a given center and optional layers (GeoJSON format).
 * - Displaying a marker at a specific location with an optional label.
 * - Redirecting the user to a full map view when the preview map is clicked.
 *
 * It uses Mapbox for rendering the map and Material UI for layout and UI elements.
 */

import React from "react";
import { useNavigate } from "react-router-dom"; // For navigation to a different route
import { ButtonBase } from "@mui/material"; // For clickable map preview
import MapBase from "./MapBase"; // Custom component for rendering the map
import type {
  Feature,
  Geometry,
  GeoJsonProperties,
  FeatureCollection,
} from "geojson"; // Types for GeoJSON data
import type { Layer } from "mapbox-gl"; // Mapbox layer types

/**
 * ChatMapPreviewProps
 *
 * Type definition for the properties accepted by the ChatMapPreview component.
 *
 * - `center`: The [longitude, latitude] coordinates for the center of the map.
 * - `layers`: Optional array of GeoJSON features to be rendered as layers on the map.
 * - `marker`: Optional marker to be placed on the map, specified by [longitude, latitude, label].
 */
interface ChatMapPreviewProps {
  center: [number, number]; // lon, lat
  layers?: Feature<Geometry, GeoJsonProperties>[]; // Optional GeoJSON layers
  marker?: [number, number, string]; // Optional marker with [lon, lat, label]
}

/**
 * ChatMapPreview
 *
 * A functional React component that renders a map preview with optional layers and a marker.
 * It displays a clickable map that redirects to a detailed map view when clicked.
 *
 * ### Dependencies:
 * - `useNavigate` from `react-router-dom` for navigation.
 * - `ButtonBase` from MUI to make the map preview clickable.
 * - `MapBase` for rendering the actual map.
 * - GeoJSON and Mapbox types for layer and feature handling.
 *
 * ### Props:
 * - `center`: Coordinates for the map's center.
 * - `layers`: Optional GeoJSON layers to render on the map.
 * - `marker`: Optional marker with a label to be placed on the map.
 *
 * ### Returns:
 * - A JSX element representing a clickable map preview that redirects to the full map page when clicked.
 */
const ChatMapPreview: React.FC<ChatMapPreviewProps> = ({
  center,
  layers,
  marker,
}) => {
  const navigate = useNavigate(); // Navigate to the full map view when clicked

  // Handle click event to navitage to the full map with filters
  const handleClick = () => {
    const filters = {
      location: [center[1], center[0]],
    };

    // Navigate to the "/map" route with filters as state
    navigate("/map", { state: { filters } });
  };

  // Ensure layers are safely defined, fallback to an empty array
  const safeLayers = Array.isArray(layers) ? layers : [];
  const features = [...safeLayers]; // Combine layers with any additional features

  let markerLabelLayer: Layer | undefined; // Optional layer for marker layers

  // If a marker is provided, create a feature and label layer
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

    features.push(markerFeature); // Add marker feature to the list

    markerLabelLayer = {
      id: "chat-marker-label", // ID for marker label layer
      type: "symbol", // Layer type is symbol (text)
      source: "chat-preview",
      layout: {
        "text-field": ["get", "label"], // Use the label property for the text
        "text-font": ["Open Sans Semibold", "Arial Unicode MS Bold"],
        "text-offset": [0, 1.5], // Offset label position
        "text-anchor": "top", // Place label above the marker
      },
      paint: {
        "text-color": "#333", // Label color
      },
      filter: ["==", ["get", "isMarker"], true], // Apply filter to only show the marker label
    };
  }

  // Create a GeoJSON FeatureCollection to hold the map features
  const featureCollection: FeatureCollection<Geometry, GeoJsonProperties> = {
    type: "FeatureCollection",
    features,
  };

  // Define the preview layer for the map (circle layer)
  const previewLayer: Layer = {
    id: "chat-preview-layer", // Layer ID
    type: "circle", // Use circle for markers
    source: "chat-preview", // Source of the layer data
    paint: {
      "circle-radius": ["case", ["==", ["get", "isMarker"], true], 8, 6], // Circle size based on marker presence
      "circle-color": [
        "case", // Conditional color based on marker presence
        ["==", ["get", "isMarker"], true],
        "#ff5722", // Marker color
        "#1976d2", // Default color
      ],
      "circle-stroke-color": "#fff", // Stroke color for the circle
      "circle-stroke-width": 2, // Stroke width for the circle
    },
  };

  // Define the map layers
  const mapLayers = [
    {
      id: "chat-preview",
      data: featureCollection,
      layer: previewLayer,
    },
  ];

  // Add the marker label layer if it exists
  if (markerLabelLayer) {
    mapLayers.push({
      id: "chat-marker-label",
      data: featureCollection,
      layer: markerLabelLayer,
    });
  }

  // Render the map preview inside a clickable button container
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
