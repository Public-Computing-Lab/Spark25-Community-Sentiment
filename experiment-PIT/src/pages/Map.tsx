import { Box, Typography, IconButton } from '@mui/material'
import Key from '../components/Key';
import { useMap } from "../components/MapProvider";
import { useEffect, useState} from 'react';
import { BOTTOM_NAV_HEIGHT } from "../constants/layoutConstants"
import mapboxgl from 'mapbox-gl';
import 'mapbox-gl/dist/mapbox-gl.css';
import { processShotsData } from '../../public/data/process_911';
import { process311Data } from '../../public/data/process_311';
import FilterDialog from '../components/FilterDialog';
import LayersClearIcon from '@mui/icons-material/LayersClear';
//besure to install mapbox-gl 

function Map() {
  const { mapRef, mapContainerRef } = useMap(); // Access mapRef and mapContainerRef from context

  const [layers, setLayers] = useState<string[]>([]);
  const [selectedLayers, setSelectedLayer] = useState<string[]>(["Community Assets"]);
  const [selectedYears, setSelectedYears] = useState<number[]>([2018, 2024]);

  const handleMapClear = () => {
    //need to implement, what do we want to see?
    
  }

  //loading all data
  useEffect(() => {

    mapboxgl.accessToken = "pk.eyJ1IjoiYWthbXJhMTE4IiwiYSI6ImNtYjluNW03MTBpd3cyanBycnU4ZjQ3YjcifQ.LSPKVriOtvKxyZasMcxqxw"; 
    
    if (mapContainerRef.current){
        mapRef.current = new mapboxgl.Map({ //creating map
        container: mapContainerRef.current,
        center: [-71.076543, 42.288386], //centered based on 4 rectangle coordinates of TNT
        zoom: 14.5,
        minZoom: 12,
        style: "mapbox://styles/mapbox/light-v11", //should decide on style
      });
    }

    //adding initial map annotations
    mapRef.current?.on('load', async () => { //made async in order to be able to load shots data
      //adding rect borders of TNT
      mapRef.current?.addSource('TNT', {
        type: 'geojson',
        data: {
          type: 'Feature',
          geometry: {
            type: 'Polygon',
            coordinates: [
              [
                [-71.081913, 42.294138],
                [-71.071855, 42.293938],
                [-71.071315, 42.284500],
                [-71.081440,42.284301],
                [-71.081913, 42.294138],
              ]
            ],
          },
          properties: {}
        }
      });

      mapRef.current?.addLayer({
        id: 'tnt-outline',
        type: 'line',
        source: 'TNT',
        layout: {},
        paint: {
          'line-color': '#82aae7',
          'line-width': 3,
        }
      });

        // Fetching and adding community assets
      fetch(`${import.meta.env.BASE_URL}data/map_2.geojson`)
        .then((response) => response.json())
        .then((geojsonData) => {
          mapRef.current?.addSource('assets', {
            type: 'geojson',
            data: geojsonData,
          });

          mapRef.current?.addLayer({
            id: 'Community Assets',
            type: 'circle',
            source: 'assets',
            paint: {
              'circle-radius': 5,
              'circle-color': '#228B22',
            },
          });
          
        })
        .catch((error) => {
          console.error('Error fetching community assets:', error);
        });
    
      const shots_geojson = await processShotsData(); //loading shots data from api and converting to geojson
      const request_geojson = await process311Data(); //loading 311 data from api and converting to geojson

      mapRef.current?.addSource('shots_data', { //takes a while to load entire dataset... hopefully will be better when we get it hyperlocal
        type: 'geojson',
        data: shots_geojson
      });

      mapRef.current?.addLayer({
        id: 'Gun Violence Incidents',
        type: 'circle',
        source: 'shots_data',
        paint: {
          'circle-radius': 3,
          'circle-color': '#880808',
        }
      })

      //adding 311 data
      mapRef.current?.addSource('311_data', { //takes even longer than 911 data...
        type: 'geojson',
        data: request_geojson //change to non-personal account
      });

      mapRef.current?.addLayer({
        id: '311 Requests',
        type: 'circle',
        source: '311_data',
        paint: {
          'circle-radius': 3,
          'circle-color': '#FFC300',
          'circle-opacity': 0.3,
        }
      });
      

      // Retrieve all layers after community-assets is added
      const mapLayers = mapRef.current?.getStyle().layers;
      const layerIds = mapLayers
        ? mapLayers
            .filter(layer => layer.type === 'circle') //getting only the layers i've added
            .map(layer => layer.id)
        : [];
      setLayers(layerIds);
    });

    mapRef.current?.on('click', 'Community Assets', (e) => { //getting popup text
      if (e.features && e.features[0]) {
        const name = e.features[0].properties && e.features[0].properties['Name'];
        const alternates = e.features[0].properties && e.features[0].properties['Alternate Names'];
        const geometry = e.features[0].geometry as { type: 'Point'; coordinates: number[] }; //type assertion to prevent typescript error
        const coordinates = geometry.coordinates.slice();

        while (Math.abs(e.lngLat.lng - coordinates[0]) > 180) {
          coordinates[0] += e.lngLat.lng > coordinates[0] ? 360 : -360; //adjusting X coordinate of popup
        } //may need to give more wiggle room for mobile 

        const description = `<strong>${name}</strong><br>${alternates}` //need to figure out better styling for popup

        new mapboxgl.Popup()
          .setLngLat([coordinates[0], coordinates[1]])
          .setHTML(description)
          .addTo(mapRef.current!);
      }
    })

    mapRef.current?.on('click', 'Gun Violence Incidents', (e) => { //getting popup text
      if (e.features && e.features[0]) {
        const name = e.features[0].properties && e.features[0].properties['year'];
        const geometry = e.features[0].geometry as { type: 'Point'; coordinates: number[] }; //type assertion to prevent typescript error
        const coordinates = geometry.coordinates.slice();

        while (Math.abs(e.lngLat.lng - coordinates[0]) > 180) {
          coordinates[0] += e.lngLat.lng > coordinates[0] ? 360 : -360; //adjusting X coordinate of popup
        } //may need to give more wiggle room for mobile 

        const description = `<strong>${name}</strong>` //need to figure out better styling for popup

        new mapboxgl.Popup()
          .setLngLat([coordinates[0], coordinates[1]])          
          .setHTML(description)
          .addTo(mapRef.current!);
      }
    })

    mapRef.current?.on('click', '311 Requests', (e) => { //getting popup text
      if (e.features && e.features[0]) {
        const year = e.features[0].properties && e.features[0].properties['year'];
        const type = e.features[0].properties && e.features[0].properties['request_type'];
        const geometry = e.features[0].geometry as { type: 'Point'; coordinates: number[] }; //type assertion to prevent typescript error
        const coordinates = geometry.coordinates.slice();

        while (Math.abs(e.lngLat.lng - coordinates[0]) > 180) {
          coordinates[0] += e.lngLat.lng > coordinates[0] ? 360 : -360; //adjusting X coordinate of popup
        } //may need to give more wiggle room for mobile 

        const description = `<strong>${year}</strong><br>${type}` //need to figure out better styling for popup

        new mapboxgl.Popup()
          .setLngLat([coordinates[0], coordinates[1]])
          .setHTML(description)
          .addTo(mapRef.current!);
      }
    })
    
    return () => {

    }
  }, []);

  //changing visibility of layers depending on what is checked in filters or not.
  useEffect(() => {
    if (mapRef.current) {
      layers.forEach((layerId) => {
        const visibility = selectedLayers.includes(layerId) ? 'visible' : 'none';
        mapRef.current?.setLayoutProperty(layerId, 'visibility', visibility);
      });
    }
  }, [selectedLayers, layers]);


  //filtering by years
  useEffect(() => {
    if (mapRef.current) {
      layers.forEach((layerId) => {
        if (layerId !== "Community Assets"){ //excluding filtering on community assets
          mapRef.current?.setFilter(layerId, [
            "all",
            [">=", "year", selectedYears[0]],
            ["<=", "year", selectedYears[selectedYears.length - 1]],
          ]);
        }
      })
    }
  }, [selectedYears, layers])


  return (
    <Box
      sx={{
        display: 'flex',
        flexDirection: 'column',
        height: `calc(100vh - ${BOTTOM_NAV_HEIGHT}px)`,
        width: '100%',
        bgcolor: 'background.paper',
        color: 'text.primary',
        overflow: 'hidden',
        position: 'relative',
        p: 2,
      }}
    >
      <Box
          sx={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            mb: 2,
          }}
        >
          <Typography variant="h4" component="h1">
            Map
          </Typography>
          <IconButton
            aria-label="Clear Map"
            onClick={handleMapClear}
          >
            <LayersClearIcon/>
          </IconButton>
      </Box>
      
      <Box sx={{ //element rendering the map
        left: '0', 
        top: '0', 
        flex: 1, 
        width: '100%',
        height: `calc(100vh - ${BOTTOM_NAV_HEIGHT}px)`,
        position: 'relative',
      }}
        ref={mapContainerRef}
      />
      <Box sx={{mb: 3, position: 'absolute', left: '5', top: '4em'}}>
          <Key />
      </Box>
      <FilterDialog layers={layers} onSelectionChange={setSelectedLayer} onSliderChange={setSelectedYears}/>
      
    </Box>
    
  )
}

export default Map;
