/**
 * Map.tsx
 * This file hosts the map interface and is where the assets, 311, 911 data is displayed along with their tooltips. 
 * Also creates loading screen while larger data sets loads
 * it also includes the filter functionality and map-chat-link functionality.
 */

import { Box, CircularProgress } from "@mui/material";
import ReactDOM from "react-dom/client"; // For React 18+

import Key from "../components/Key";
import Tooltip from "../components/Tooltip"; // Adjust path as needed
import FilterDialog from "../components/FilterDialog";

import { useMap } from "../components/useMap.tsx";
import { useEffect, useState } from "react";
import { BOTTOM_NAV_HEIGHT } from "../constants/layoutConstants";
import mapboxgl from "mapbox-gl";
import "mapbox-gl/dist/mapbox-gl.css";
import {
  MapboxExportControl,
} from "@watergis/mapbox-gl-export";
import "@watergis/mapbox-gl-export/dist/mapbox-gl-export.css";
import { processShotsData } from "../api/process_911.ts";
import { process311Data } from "../api/process_311.ts";
import { colorPalette } from "../assets/palette";
import MapOutlinedIcon from "@mui/icons-material/MapOutlined";
//besure to install mapbox-gl 

function Map() {
  const {
    mapRef,
    mapContainerRef,
    pendingFitBounds,
    setPendingFitBounds,
    selectedLayers,
    selectedYearsSlider,
    setSelectedLayer,
    setSelectedYearsSlider,
  } = useMap(); // Access mapRef and mapContainerRef from context
  const [layers, setLayers] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  mapboxgl.accessToken = import.meta.env.VITE_MAPBOX_TOKEN;

  useEffect(() => {
    /** 
     * Loads mapbox map and loads all data onto map
     * Args/Dependencies: mapRef, mapContainerRef
     * Returns: N/A
    */
    if (mapContainerRef.current) {
      mapRef.current = new mapboxgl.Map({
        //creating map
        container: mapContainerRef.current,
        center: [-71.076543, 42.288386], //centered based on 4 rectangle coordinates of TNT
        zoom: 14.5,
        minZoom: 12,
        style: "mapbox://styles/mapbox/light-v11", //should decide on style
      });
    }

    //adding initial map annotations
    mapRef.current?.on("load", async () => {

      //storing data of rect borders of TNT
      mapRef.current?.addSource("TNT", {
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
          properties: {},
        },
      });
      //loading 
      mapRef.current?.addLayer({
        id: "tnt-outline",
        type: "line",
        source: "TNT",
        layout: {},
        paint: {
          "line-color": "#82aae7",
          "line-width": 3,
        },
      });

      // Fetching and adding community assets from map_2.geojson
      fetch(`${import.meta.env.BASE_URL}/data/map_2.geojson`)
        .then((response) => response.json())
        .then((geojsonData) => {
          mapRef.current?.addSource("assets", {
            type: "geojson",
            data: geojsonData,
          });
          
          mapRef.current?.addLayer({
            id: "Community Assets",
            type: "circle",
            source: "assets",
            paint: {
              "circle-radius": 5,
              "circle-color": "#228B22",
            },
          });
        })
        .catch((error) => {
          console.error("Error fetching community assets:", error);
        });

      setIsLoading(true); //using loading screen while data loads

      try { //adding 311 and shots data 
        const shots_geojson = await processShotsData(); //loading from api and converting to geojson
        const request_geojson = await process311Data(); //loading from api and converting to geojson

        //shots data
        mapRef.current?.addSource("shots_data", {
          type: "geojson",
          data: shots_geojson,
        });

        mapRef.current?.addLayer({
          id: "Gun Violence Incidents",
          type: "circle",
          source: "shots_data",
          paint: {
            'circle-radius': 4,
            'circle-color': "#5d17d5" ,
          }
        })

        //311 data
        mapRef.current?.addSource("311_data", {
          //takes even longer than 911 data...
          type: "geojson",
          data: request_geojson, //change to non-personal account
        });

        mapRef.current?.addLayer({
          id: "311 Requests",
          type: "circle",
          source: "311_data",
          paint: {
            "circle-radius": 4,
            "circle-color": "#FFC300",
            "circle-opacity": 0.3,
          },
        });

        // Retrieve all layers after community-assets is added for filter dialog text
        const mapLayers = mapRef.current?.getStyle().layers;
        const layerIds = mapLayers
          ? mapLayers
              .filter((layer) => layer.type === "circle") //getting only the layers i've added
              .map((layer) => layer.id)
          : [];
        setLayers(layerIds);

        setIsLoading(false); //turning loading screen off
      } catch (error) {
        console.log("Error loading data", error);
      }
    });

    //Tooltips
    mapRef.current?.on("click", "Community Assets", (e) => {
      const type = "Community Assets";
      if (e.features && e.features[0]) {
        const name =
          e.features[0].properties && e.features[0].properties["Name"];
        const alternates =
          e.features[0].properties &&
          e.features[0].properties["Alternate Names"];
        const geometry = e.features[0].geometry as {
          type: "Point";
          coordinates: number[];
        }; //type assertion to prevent typescript error
        const coordinates = geometry.coordinates.slice();

        while (Math.abs(e.lngLat.lng - coordinates[0]) > 180) {
          coordinates[0] += e.lngLat.lng > coordinates[0] ? 360 : -360; //adjusting X coordinate of popup
        } //may need to give more wiggle room for mobile

        // Create a container div for the React component
        const container = document.createElement("div");

        // Render Tooltip into the container
        ReactDOM.createRoot(container).render(
          <Tooltip type={type} name={name} alternates={alternates} />
        );

        new mapboxgl.Popup()
          .setLngLat([coordinates[0], coordinates[1]])
          .setDOMContent(container)
          .addTo(mapRef.current!);
      }
    });

    mapRef.current?.on("click", "Gun Violence Incidents", (e) => {
      //getting popup text
      const type = "Gun Violence Incidents";
      if (e.features && e.features[0]) {
        const date =
          e.features[0].properties && e.features[0].properties["date"];
        const geometry = e.features[0].geometry as {
          type: "Point";
          coordinates: number[];
        }; //type assertion to prevent typescript error
        const coordinates = geometry.coordinates.slice();

        while (Math.abs(e.lngLat.lng - coordinates[0]) > 180) {
          coordinates[0] += e.lngLat.lng > coordinates[0] ? 360 : -360; //adjusting X coordinate of popup
        } //may need to give more wiggle room for mobile

        // Create a container div for the React component
        const container = document.createElement("div");

        // Render Tooltip into the container
        ReactDOM.createRoot(container).render(
          <Tooltip type={type} date={date} />
        );

        new mapboxgl.Popup()
          .setLngLat([coordinates[0], coordinates[1]])
          .setDOMContent(container)
          .addTo(mapRef.current!);
      }
    });

    mapRef.current?.on("click", "311 Requests", (e) => {
      //getting popup text
      const type = "311 Requests";
      if (e.features && e.features[0]) {
        const date =
          e.features[0].properties && e.features[0].properties["date"];
        const request_type =
          e.features[0].properties && e.features[0].properties["request_type"];
        const geometry = e.features[0].geometry as {
          type: "Point";
          coordinates: number[];
        }; //type assertion to prevent typescript error
        const coordinates = geometry.coordinates.slice();

        while (Math.abs(e.lngLat.lng - coordinates[0]) > 180) {
          coordinates[0] += e.lngLat.lng > coordinates[0] ? 360 : -360; //adjusting X coordinate of popup
        } //may need to give more wiggle room for mobile

        // Create a container div for the React component
        const container = document.createElement("div");

        // Render Tooltip into the container
        ReactDOM.createRoot(container).render(
          <Tooltip type={type} name={request_type} date={date} />
        );

        new mapboxgl.Popup()
          .setLngLat([coordinates[0], coordinates[1]])
          .setDOMContent(container)
          .addTo(mapRef.current!);
      }
    });

    //Export Map PDF functionality
    const exportControl = new MapboxExportControl({
      accessToken: mapboxgl.accessToken ?? undefined,
    });
    mapRef.current?.addControl(exportControl as unknown as mapboxgl.IControl, "top-right");

    return () => {};
  }, [mapRef, mapContainerRef]);


  //map-chat link (zoom functionality)
  useEffect(() => {
    if (mapRef.current && pendingFitBounds) {
      mapRef.current.fitBounds(new mapboxgl.LngLatBounds(pendingFitBounds), {
        padding: 40,
        duration: 1000,
      });
      setPendingFitBounds(null); // Reset so it can be triggered again
    }
  }, [pendingFitBounds, mapRef, setPendingFitBounds]);

  //changing visibility of layers depending on what is checked in filters or not.
  useEffect(() => {
    if (mapRef.current) {
      layers.forEach((layerId) => {
        const visibility = selectedLayers.includes(layerId)
          ? "visible"
          : "none";
        mapRef.current?.setLayoutProperty(layerId, "visibility", visibility);
      });
    }
  }, [mapRef, selectedLayers, layers]);

  //filtering by years
  useEffect(() => {
    if (mapRef.current) {
      layers.forEach((layerId) => {
        if (layerId !== "Community Assets") {
          //excluding filtering on community assets as it has no year property
          mapRef.current?.setFilter(layerId, [
            "all", //(AND)
            [">=", "year", selectedYearsSlider[0]],
            ["<=", "year", selectedYearsSlider[selectedYearsSlider.length - 1]],
          ]);
        }
      });
    }
  }, [mapRef, selectedYearsSlider, layers]);


   /* ─── Render ───────────────────────────────────────────── */
  return (
    <Box
      sx={{
        display: "flex",
        flexDirection: "column",
        height: `calc(100vh - ${BOTTOM_NAV_HEIGHT}px)`,
        width: "100%",
        bgcolor: "#E7F4FF",
        overflow: "hidden",
      }}
    >
      {/* ─── Header ─────────────────────────────────────── */}
      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          px: 2,
          height: 75,
          borderBottomLeftRadius: 16,
          borderBottomRightRadius: 16,
          bgcolor: colorPalette.dark,
          color: "#fff",
        }}
      >
        <MapOutlinedIcon
   fontSize="large"       
   sx={{ mr: 0.5 }}        
 />
        
      </Box>
      {isLoading && (
        <Box
          sx={{
            position: "absolute",
            top: "50%",
            left: "50%",
            transform: "translate(-50%, -50%)",
            zIndex: 1000,
          }}
        >
          <CircularProgress />
        </Box>
      )}
      {isLoading && (
        <Box
          sx={{
            //element rendering the map
            position: "absolute",
            top: 0,
            left: 0,
            width: "100%",
            height: "100%",
            backgroundColor: "rgba(10, 10, 10, 0.32)",
            zIndex: 3,
          }}
        />
      )}

      {/* ─── Flexible content area (fills the rest) ─────── */}
      <Box sx={{ flex: 1, p: 2, position: "relative" }}>
        {/* Mapbox container fills its parent */}
        <Box ref={mapContainerRef} sx={{ position: "absolute", inset: 0 }} />

        {/* Legend overlay */}
        <Box sx={{ position: "absolute", top: "4em", left: 5 }}>
          <Key />
        </Box>
      </Box>
      <FilterDialog
        layers={layers}
        onSelectionChange={setSelectedLayer}
        onSliderChange={setSelectedYearsSlider}
      />
    </Box>
  );
}

export default Map;