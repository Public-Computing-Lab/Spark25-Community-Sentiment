import { Box, Typography, CircularProgress } from "@mui/material";
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
  Size,
  PageOrientation,
  Format,
  DPI,
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

  //loading all data
  useEffect(() => {
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
      //made async in order to be able to load shots data

      //adding rect borders of TNT
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

      // Fetching and adding community assets
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
        const shots_geojson = await processShotsData(); //loading shots data from api and converting to geojson
        const request_geojson = await process311Data(); //loading 311 data from api and converting to geojson

        console.log("geojson format", shots_geojson);

        mapRef.current?.addSource("shots_data", {
          //takes a while to load entire dataset... hopefully will be better when we get it hyperlocal
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

        //adding 311 data
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

        // Retrieve all layers after community-assets is added
        const mapLayers = mapRef.current?.getStyle().layers;
        const layerIds = mapLayers
          ? mapLayers
              .filter((layer) => layer.type === "circle") //getting only the layers i've added
              .map((layer) => layer.id)
          : [];
        setLayers(layerIds);

        setIsLoading(false);
      } catch (error) {
        console.log("Error loading data", error);
      }
    });

    mapRef.current?.on("click", "Community Assets", (e) => {
      //getting popup text
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

    const exportControl = new MapboxExportControl({
      PageSize: Size.A4,
      PageOrientation: PageOrientation.Portrait,
      Format: Format.PNG,
      DPI: DPI[96],
      Crosshair: false,
      PrintableArea: true,
      Local: "en",
      Filename: "TNT-PublicSafety-Data",
      accessToken: mapboxgl.accessToken ?? undefined,
    });

    mapRef.current?.addControl(exportControl, "top-right");

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
      console.log("set new bounds");
    }
  }, [pendingFitBounds, mapRef, setPendingFitBounds]);

  //changing visibility of layers depending on what is checked in filters or not.
  //NEED TO DETERMINE WHY VISIBILITY FOR COMMUNITY ASSETS ISN'T WORKING
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
          //excluding filtering on community assets
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