/**
 * process_311.ts
 * This file takes the 311 data from the api endpoint and converts it to a geojson to be able to load into the map
 * Also holds the typescript interfaces dictating what properties the geojson feature would have.
 */

import { get311Data } from './api.ts';

interface GeoJSON {
    type: "FeatureCollection",
    features: GeoJSONFeature[]
}

interface GeoJSONFeature {
    type: "Feature",
    properties: {
        id: number;
        request_type: string,
        date: string;
        year: number;
    };
    geometry: {
        type: "Point";
        coordinates: number[];
    }
}

export const process311Data = async () => {
    /** 
     * take 311 data from api and converts to geojson format 
     * Args/Dependencies: N/A
     * Returns: request_geojson: GeoJSON 
    */
    try {
         //loading 
        const request_data = await get311Data(undefined, undefined, true);

        const request_geojson: GeoJSON = { type: "FeatureCollection", features: [] as GeoJSONFeature[] }; //defining type of array


        //converting to geojson
        for (const instance of request_data){
            const request_id = instance.id;
            const request_type = instance.type;
            const request_latitude = instance.latitude;
            const request_longitude = instance.longitude;
            const request_date = new Date(instance.date);
            const request_year = request_date.getFullYear(); //date object property

            request_geojson.features.push({
                "type": "Feature",
                "properties": {
                    id: request_id,
                    request_type: request_type,
                    date: request_date.toLocaleString("en"),//formatting of dates
                    year: request_year,
                },
                "geometry": {
                    "type": "Point",
                    "coordinates": [
                        parseFloat(request_longitude),
                        parseFloat(request_latitude)
                    ]
                } 
            })

        }

        return request_geojson;

    } catch (error) {
        console.log("❌ Error loading 311 data from database or converting to geojson..", error);
    }
       
}