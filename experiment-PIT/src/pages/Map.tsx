import { Box, Typography } from '@mui/material'
import {useRef, useEffect} from 'react';
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

    //adding rect borders of TNT
    mapRef.current.on('load', () => {
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
        id: 'outline',
        type: 'line',
        source: 'TNT',
        layout: {},
        paint: {
          'line-color': '#0d54c2',
          'line-width': 3
        }
      });

    });
    return () => {
      mapRef.current.remove() //removes map after unmounting
    }
  }, [])


  return (
    <Box
      sx={{
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      <Box sx={{ //element rendering the map
        left: '0', 
        top: '0', 
        position: 'absolute', 
        width: '100vw !important',
        height: '100%',
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
