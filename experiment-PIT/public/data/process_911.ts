import { get311Data } from '../../src/api/api.ts';
import { check } from "@placemarkio/check-geojson";

interface GeoJSONFeature {
    type: string,
    properties: {
        id: number;
        request_type: string,
        date: string;
    };
    geometry: {
        type: string;
        coordinates: number[];
    }
}

export const process311Data = async () => {
    //loading 
    const request_data = await get311Data();
    const request_geojson = { type: "FeatureCollection", features: [] as GeoJSONFeature[] }; //defining type of array

    //converting to geojson
    for (const instance of request_data){
        const request_id = instance.id;
        const request_type = instance.type;
        const request_latitude = instance.latitude;
        const request_longitude = instance.longitude;
        const request_date = instance.date;

        request_geojson.features.push({
            "type": "Feature",
            "properties": {
                id: request_id,
                request_type: request_type,
                date: request_date,
            },
            "geometry": {
                "type": "Point",
                "coordinates": [
                    parseFloat(request_latitude),
                    parseFloat(request_longitude)
                ]
            } 
        })

    }

     // Create a downloadable file to export to give to mapbox
    try {
        const checkingObj = check(JSON.stringify(request_geojson, null, 2));
        console.log("validating geojson..");
        console.log(checkingObj);

        const blob = new Blob([JSON.stringify(request_geojson, null, 2)], { type: 'application/json' });
        console.log("✅ blob created!")
        const url = URL.createObjectURL(blob);
    
        const a = document.createElement('a');
        a.href = url;
        a.download = 'shots_data.geojson';
        a.click();
    
        console.log('✅ GeoJSON file download triggered!');
    } catch (error) {
        console.log('❌ Error validating, creating, or downloading the GeoJSON file:', error);
    }
       
}