import { get311Data } from '../../src/api/api.ts';

interface GeoJSONFeature {
    type: string,
    properties: {
        id: number;
        request_type: string,
        date: string;
        year: number;
    };
    geometry: {
        type: string;
        coordinates: number[];
    }
}

export const process311Data = async () => {
    try {
         //loading 
        const request_data = await get311Data();
        const request_geojson = { type: "FeatureCollection", features: [] as GeoJSONFeature[] }; //defining type of array

        //converting to geojson
        for (const instance of request_data){
            const request_id = instance.id;
            const request_type = instance.type;
            const request_latitude = instance.latitude;
            const request_longitude = instance.longitude;
            const request_date = new Date(instance.date);
            const request_year = request_date.getFullYear();

            request_geojson.features.push({
                "type": "Feature",
                "properties": {
                    id: request_id,
                    request_type: request_type,
                    date: request_date.toLocaleString("en"),
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