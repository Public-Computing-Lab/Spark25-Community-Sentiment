# Experiment-PIT

this document describes the flow of data and components that the Community Sentiment and Public Safety group of the PIT-NE Impact Fellowship completed

## Map
1. Data about Community Assets
- geocoding completed in geopipeline jupyter notebook
- resulted in a spreadsheet, given to geojson.io to be converted to a geojson
- final product is map_2.geojson

2. 911 data
- loaded from MySQL database
- processed and converted to geojson file to be downloaded 
- downloaded file given to mapbox to be converted to vector tileset
- vector tileset used as url for map layer




