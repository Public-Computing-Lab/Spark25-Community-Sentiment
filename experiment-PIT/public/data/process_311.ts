import { getShotsData } from '../../src/api/api.ts';
import { check } from "@placemarkio/check-geojson";

//TO USE:
//run this file on map load and download geojson file to give to mapbox to create vector tileset.

interface GeoJSONFeature {
    type: string,
    properties: {
        id: number;
        date: string;
    };
    geometry: {
        type: string;
        coordinates: number[];
    }
}

//process shots data from api and turning into geojson
export const processShotsData = async () => {
    //loading 
    const shots_data = await getShotsData();
    const shots_geojson = { type: "FeatureCollection", features: [] as GeoJSONFeature[] }; //defining type of array

    //converting to GeoJSON
    for (const instance of shots_data){ //using for of instead of for in
        const shot_id = instance.id;
        const shot_latitude = instance.latitude;
        const shot_longitude = instance.longitude;
        const shot_date = instance.date;
        //const shot_ballistics = instance.ballistics_evidence
        //include ballistics evidence?

        shots_geojson.features.push({
            "type": "Feature",
            "properties": {
                id: shot_id,
                date: shot_date,
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
    
    //
    
    // Create a downloadable file to export to give to mapbox
    try {
        const checkingObj = check(JSON.stringify(shots_geojson, null, 2));
        console.log("validating geojson..");
        console.log(checkingObj);

        const blob = new Blob([JSON.stringify(shots_geojson, null, 2)], { type: 'application/json' });
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

// or could turn into csv file to give to mapboxs