/**
 * MapBase.tsx
 *
 * This component renders a Map using Mapbox GL and allows adding layers of GeoJSON data.
 * The map is rendered inside a container and can display layers based on the passed props.
 * The map has the following features:
 * - It centers on the specified coordinates (`center` prop).
 * - It has a default zoom level, which can be customized via the `zoom` prop.
 * - It accepts additional map layers (`layers` prop) in GeoJSON format.
 * - The map's height and width are customizable via the `height` and `width` props.
 *
 * It uses Mapbox GL for rendering the map and handling the layers, and React hooks (`useEffect` and `useRef`) for managing side effects and references.
 *
 * ### Props:
 * - `center`: The center coordinates of the map [longitude, latitude].
 * - `zoom`: The initial zoom level (default is 14).
 * - `layers`: An array of layer objects, each containing an id, data (GeoJSON), and layer configuration.
 * - `height`: The height of the map container (default is 250).
 * - `width`: The width of the map container (default is "100%").
 *
 * ### Returns:
 * - A `<div>` element containing the Mapbox GL map, with the specified layers and settings applied.
 *
 * ### Side Effects:
 * - Initializes the Mapbox map on mount.
 * - Adds layers to the map dynamically based on the `layers` prop.
 * - Removes the map on unmount to clean up resources.
 */

import React, { useEffect, useRef } from "react";
import mapboxgl from "mapbox-gl";
import "mapbox-gl/dist/mapbox-gl.css";

/**
 * MapBaseProps
 *
 * Type definition for the component props.
 * - `center`: Coordinates for the map center ([longitude, latitude]).
 * - `zoom`: Zoom level for the map (optional, defaults to 14).
 * - `layers`: Array of layers to add to the map, each containing an `id`, `data`, and `layer`.
 * - `height`: Height of the map container (optional, defaults to 250).
 * - `width`: Width of the map container (optional, defaults to "100%").
 */
type MapBaseProps = {
  center: [number, number]; // Center of the map in [longitude, latitude]
  zoom?: number; // Zoom level for the map (default: 14)
  layers?: Array<{
    id: string; // Unique identifier for the layer
    data: GeoJSON.FeatureCollection; // GeoJSON data for the layer
    layer: mapboxgl.Layer; // Mapbox GL layer configuration
  }>;
  height?: string | number; // Height of the map container (default: 250px)
  width?: string | number; // Width of the map container (default: "100%")
};

/**
 * MapBase
 *
 * A functional React component that renders a Mapbox map with specified layers.
 * The component accepts props to customize the map's center, zoom level, layers, height, and width.
 * It initializes the map and adds the specified layers once the map is loaded.
 *
 * ### Dependencies:
 * - `mapbox-gl`: Used for rendering the map and handling map layers.
 * - `useRef`: Used to reference the DOM element for the map container.
 * - `useEffect`: Used for side effects like initializing the map and adding/removing layers.
 *
 * ### Returns:
 * - A map container `<div>` that holds the rendered Mapbox map.
 */
const MapBase: React.FC<MapBaseProps> = ({
  center,
  zoom = 14,
  layers = [],
  height = 250,
  width = "100%",
}) => {
  // Reference for the map container DOM element.
  const mapContainerRef = useRef<HTMLDivElement>(null);

  // Reference for the Mapbox GL map instance.
  const mapRef = useRef<mapboxgl.Map | null>(null);

  useEffect(() => {
    // Ensure that the map container is available before initializing the map.
    if (!mapContainerRef.current) return;

    // Initialize the Mapbox GL map.
    mapRef.current = new mapboxgl.Map({
      container: mapContainerRef.current, // The container DOM element
      style: "mapbox://styles/mapbox/light-v11", // Map style (light theme)
      center, // Map center coordinates
      zoom, // Map zoom level
      interactive: false, // Disable map interaction (dragging, zooming, etc.)
    });

    // Once the map is loaded, add the provided layers to the map.
    mapRef.current.on("load", () => {
      layers.forEach(({ id, data, layer }) => {
        // Check if the source with the given id exists.
        if (!mapRef.current!.getSource(id)) {
          // If the source doesn't exist, add a new source with the GeoJSON data.
          mapRef.current!.addSource(id, {
            type: "geojson",
            data,
          });
        } else {
          // If the source exists, update the data of the source.
          const source = mapRef.current!.getSource(
            id
          ) as mapboxgl.GeoJSONSource;
          source.setData(data);
        }

        // Check if the layer with the given id exists.
        if (!mapRef.current!.getLayer(layer.id)) {
          // If the layer doesn't exist, add the new layer to the map.
          mapRef.current!.addLayer(layer);
        }
      });
    });

    // Cleanup function to remove the map when the component unmounts.
    return () => {
      mapRef.current?.remove(); // Clean up the map to prevent memory leaks.
    };
  }, [center, zoom, layers]); // Re-run effect when any of these props change.

  return (
    // The container for the map, styled with width, height, and border-radius.
    <div
      ref={mapContainerRef} // Attach the reference to the map container
      style={{
        width: "100%", // Full width
        height: height, // Set the height from props
        borderRadius: 8, // Rounded corners
        overflow: "hidden", // Prevent overflow of map content
        position: "relative", // Position relative to allow for proper layout
      }}
    />
  );
};

export default MapBase;
