// src/components/MapBase.tsx
import React, { useEffect, useRef } from "react";
import mapboxgl from "mapbox-gl";
import "mapbox-gl/dist/mapbox-gl.css";

mapboxgl.accessToken = import.meta.env.VITE_MAPBOX_ACCESS_TOKEN;

type MapBaseProps = {
  center: [number, number];
  zoom?: number;
  layers?: Array<{
    id: string;
    data: GeoJSON.FeatureCollection;
    layer: mapboxgl.Layer;
  }>;
  height?: string | number;
  width?: string | number;
};

const MapBase: React.FC<MapBaseProps> = ({
  center,
  zoom = 14,
  layers = [],
  height = 250,
  width = "100%",
}) => {
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<mapboxgl.Map | null>(null);

  useEffect(() => {
    if (!mapContainerRef.current) return;

    mapRef.current = new mapboxgl.Map({
      container: mapContainerRef.current,
      style: "mapbox://styles/mapbox/light-v11",
      center,
      zoom,
      interactive: false, // disables dragging, zooming, etc.
    });

    mapRef.current.on("load", () => {
      layers.forEach(({ id, data, layer }) => {
        if (!mapRef.current!.getSource(id)) {
          mapRef.current!.addSource(id, {
            type: "geojson",
            data,
          });
          mapRef.current!.addLayer(layer);
        }
      });
    });

    return () => {
      mapRef.current?.remove();
    };
  }, [center, zoom, layers]);

  return (
    <div
      ref={mapContainerRef}
      style={{
        width,
        height,
        borderRadius: 8,
        overflow: "hidden",
      }}
    />
  );
};

export default MapBase;
