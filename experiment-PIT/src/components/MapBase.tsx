import { useRef, useEffect } from "react";
import mapboxgl from "mapbox-gl";
import "mapbox-gl/dist/mapbox-gl.css";
import { Box } from "@mui/material";
import { processShotsData } from "../../public/data/process_911";
import { process311Data } from "../../public/data/process_311";

type MapBaseProps = {
  center: [number, number];
  zoom?: number;
  showLayers: {
    shots?: boolean;
    data311?: boolean;
    assets?: boolean;
  };
  height?: string;
  width?: string;
};

function MapBase({
  center,
  zoom = 14.5,
  showLayers,
  height = "300px",
  width = "100%",
}: MapBaseProps) {
  const mapRef = useRef<mapboxgl.Map | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    mapboxgl.accessToken =
      "pk.eyJ1IjoiYWthbXJhMTE4IiwiYSI6ImNtYjluNW03MTBpd3cyanBycnU4ZjQ3YjcifQ.LSPKVriOtvKxyZasMcxqxw";

    mapRef.current = new mapboxgl.Map({
      container: containerRef.current!,
      center,
      zoom,
      style: "mapbox://styles/mapbox/light-v11",
      interactive: false,
    });

    mapRef.current.on("load", async () => {
      mapRef.current!.addSource("TNT", {
        type: "geojson",
        data: {
          type: "Feature",
          geometry: {
            type: "Polygon",
            coordinates: [
              [
                [-71.081913, 42.294138],
                [-71.071855, 42.293938],
                [-71.071315, 42.2845],
                [-71.08144, 42.284301],
                [-71.081913, 42.294138],
              ],
            ],
          },
        },
      });

      mapRef.current!.addLayer({
        id: "tnt-outline",
        type: "line",
        source: "TNT",
        paint: {
          "line-color": "#82aae7",
          "line-width": 3,
        },
      });

      if (showLayers.shots) {
        const shots_geojson = await processShotsData();
        mapRef.current!.addSource("shots_data", {
          type: "geojson",
          data: shots_geojson,
        });
        mapRef.current!.addLayer({
          id: "shots_vector",
          type: "circle",
          source: "shots_data",
          paint: {
            "circle-radius": 3,
            "circle-color": "#880808",
          },
        });
      }

      if (showLayers.data311) {
        const request_geojson = await process311Data();
        mapRef.current!.addSource("311_data", {
          type: "geojson",
          data: request_geojson,
        });
        mapRef.current!.addLayer({
          id: "311_vector",
          type: "circle",
          source: "311_data",
          paint: {
            "circle-radius": 3,
            "circle-color": "#FBEC5D",
          },
        });
      }

      if (showLayers.assets) {
        const assetResponse = await fetch("/data/map_2.geojson");
        const assetData = await assetResponse.json();
        mapRef.current!.addSource("assets", {
          type: "geojson",
          data: assetData,
        });
        mapRef.current!.addLayer({
          id: "community-assets",
          type: "circle",
          source: "assets",
          paint: {
            "circle-radius": 5,
            "circle-color": "#228B22",
          },
        });
      }
    });

    return () => {
      mapRef.current?.remove();
    };
  }, [center, zoom, showLayers]);

  return (
    <Box
      ref={containerRef}
      sx={{
        height,
        width,
        borderRadius: 2,
        overflow: "hidden",
        boxShadow: 3,
      }}
    />
  );
}

export default MapBase;
