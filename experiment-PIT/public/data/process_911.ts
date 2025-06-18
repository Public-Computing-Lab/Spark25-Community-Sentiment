import { getShotsData } from '../../src/api/api.ts';

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
   
    try {
         //loading 
        const shots_data = await getShotsData(undefined, true);

        const shots_geojson: GeoJSON = { type: "FeatureCollection", features: [] as GeoJSONFeature[] }; //defining type of array


        //converting to GeoJSON
        for (const instance of shots_data){ //using for of instead of for in
            const shot_id = instance.id;
            const shot_latitude = instance.latitude;
            const shot_longitude = instance.longitude;
            const shot_date = new Date(instance.date);
            const shot_year = shot_date.getFullYear();
            //const shot_ballistics = instance.ballistics_evidence
            //include ballistics evidence?

            shots_geojson.features.push({
                "type": "Feature",
                "properties": {
                    id: shot_id,
                    date: shot_date.toLocaleString("en"),
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