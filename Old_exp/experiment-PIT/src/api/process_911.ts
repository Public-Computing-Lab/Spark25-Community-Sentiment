/**
 * process_911.ts
 * This file takes the 911 data from the api endpoint and converts it to a geojson to be able to load into the map
 * Also holds the typescript interfaces dictating what properties the geojson feature would have.
 */

import { getShotsData } from './api.ts';

interface GeoJSON {
    type: "FeatureCollection",
    features: GeoJSONFeature[]
}

interface GeoJSONFeature {
    type: "Feature",
    properties: {
        id: number;
        date: string;
        year: number;
    };
    geometry: {
        type: "Point";
        coordinates: number[];
    }
}

//process shots data from api and turning into geojson
export const processShotsData = async () => {
   /** 
     * take 911 data from api and converts to geojson format 
     * Args/Dependencies: N/A
     * Returns: shots_geojson: GeoJSON 
    */
    try {
         //loading 
        const shots_data = await getShotsData(undefined, true);

        const shots_geojson: GeoJSON = { type: "FeatureCollection", features: [] as GeoJSONFeature[] }; //defining type of array


        //converting to GeoJSON
        for (const instance of shots_data){ 
            const shot_id = instance.id;
            const shot_latitude = instance.latitude;
            const shot_longitude = instance.longitude;
            const shot_date = new Date(instance.date);
            const shot_year = shot_date.getFullYear(); //date object property
            //const shot_ballistics = instance.ballistics_evidence
            //include ballistics evidence?

            shots_geojson.features.push({
                "type": "Feature",
                "properties": {
                    id: shot_id,
                    date: shot_date.toLocaleString("en"),//formatting of dates
                    year: shot_year,
                    //ballistics: shot_ballistics,
                },
                "geometry": {
                    "type": "Point",
                    "coordinates": [
                        parseFloat(shot_longitude),
                        parseFloat(shot_latitude)
                    ]
                } 
            })
        }
        return shots_geojson;
        
    } catch (error) {
        console.log('❌ Error loading 911 data from database or converting to GeoJSON file:', error);
    }
   
}

// or could turn into csv file to give to mapboxs