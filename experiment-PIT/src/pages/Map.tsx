import { Box, Typography } from '@mui/material'
import {useRef, useEffect} from 'react';
import { BOTTOM_NAV_HEIGHT } from "../constants/layoutConstants"
import mapboxgl from 'mapbox-gl';
import 'mapbox-gl/dist/mapbox-gl.css';

//besure to install mapbox-gl 

function Map() {
  const mapRef = useRef();
  const mapContainerRef = useRef(); //.current assigns it a value

  useEffect(() => {
    mapboxgl.accessToken = "pk.eyJ1IjoiYWthbXJhMTE4IiwiYSI6ImNtYjluNW03MTBpd3cyanBycnU4ZjQ3YjcifQ.LSPKVriOtvKxyZasMcxqxw"; //using personal access token for now
    
    mapRef.current = new mapboxgl.Map({ //creating map
      container: mapContainerRef.current,
      center: [-71.076543, 42.288386], //centered based on 4 rectangle coordinates of TNT
      zoom: 14.5,
      minZoom: 12,
      style: "mapbox://styles/mapbox/light-v11", //should decide on style
    });

    //adding initial map annotations
    mapRef.current.on('load', () => {
      //adding rect borders of TNT
      mapRef.current.addSource('TNT', {
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
          }
        }
      });

      mapRef.current.addLayer({
        id: 'tnt-outline',
        type: 'line',
        source: 'TNT',
        layout: {},
        paint: {
          'line-color': '#0d54c2',
          'line-width': 3,
          'line-opacity': 0.6,
        }
      });

      // Fetching and adding community assets
      fetch('/data/map_2.geojson')
        .then((response) => response.json())
        .then((geojsonData) => {
          mapRef.current.addSource('assets', {
            type: 'geojson',
            data: geojsonData,
          });

          mapRef.current.addLayer({
            id: 'community-assets',
            type: 'circle',
            source: 'assets',
            paint: {
              'circle-radius': 5,
              'circle-color': '#228B22',
            },
          });
        })
        
      //adding initial community assets from map annotations

    });

    //use mapbox.Popup() for tooltips [ON CLICK]
    const popup = new mapboxgl.Popup({
      closeOnClick: true
    })

    mapRef.current.on('click', 'community-assets', (e) => { //getting popup text
        const name = e.features[0].properties['Name'];
        const alternates = e.features[0].properties['Alternate Names'];
        const coordinates = e.features[0].geometry['coordinates'].slice();

        while (Math.abs(e.lngLat.lng - coordinates[0]) > 180) {
          coordinates[0] += e.lngLat.lng > coordinates[0] ? 360 : -360; //adjusting X coordinate of popup
        } //may need to give more wiggle room for mobile 

        const description = name.concat(alternates) //need to figure out better styling for popup

        new mapboxgl.Popup()
          .setLngLat(coordinates)
          .setText(description)
          .addTo(mapRef.current);

    })
    

    return () => {
      mapRef.current.remove() //removes map after unmounting
    }
  }, [])


  return (
    <Box
      sx={{
        display: 'flex',
        flexDirection: 'column',
        height: `calc(100vh - ${BOTTOM_NAV_HEIGHT}px)`,
      }}
    >
      <Box sx={{ //element rendering the map
        left: '0', 
        top: '0', 
        flex: 1, 
        width: '100%',
      }}
        ref={mapContainerRef}
      />
      <Typography 
        variant="h3"
        sx={{
          position: 'absolute',
          zIndex: '10',
          padding: '0.5em',
        }}
      > Map View
      </Typography>
    </Box>
    
  )
}

export default Map
