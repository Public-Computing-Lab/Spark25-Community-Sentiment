import axios from "axios";
import type { Message } from "../constants/chatMessages"

const MAPBOX_ACCESS_TOKEN = "pk.eyJ1IjoiYWthbXJhMTE4IiwiYSI6ImNtYjluNW03MTBpd3cyanBycnU4ZjQ3YjcifQ.LSPKVriOtvKxyZasMcxqxw"; 
const tnt_bbox = "-71.081784,42.284182,-71.071601,42.293255";

interface Location {
  name: string;
  type: 'specific' | 'vague';
  reference?: string;
}

interface GeocodedLocation {
  name: string;
  coordinates: [number, number]; // [longitude, latitude]
}

const header = {
    "RethinkAI-API-Key": import.meta.env.VITE_RETHINKAI_API_CLIENT_KEY,
    "Content-Type": "application/json",
  }

// Helper function to send the HTTP request and handle errors
async function sendPostRequest(url: string, payload: any, headers: any) {
  try {
    console.log("➡️ Sending POST to:", url);
    console.log("📦 Payload:", payload);
    console.log("header: ", headers);

    const response = await axios.post(url, payload, { headers });
    
    console.log("✅ Response status:", response.status);
    console.log("🧾 Response data:", response.data);

    return response.data;

  } catch (error: any) {
    if (axios.isAxiosError(error)) {
      console.error("❌ Axios error sending request:", {
        message: error.message,
        status: error.response?.status,
        data: error.response?.data,
      });
    } else {
      console.error("❌ Unknown error sending request:", error);
    }

    throw error; // Re-throw the error to be handled by the caller
  }
}


async function geocodeSpecific(locationName: string): Promise<[number, number] | null> {
  const url = `https://api.mapbox.com/geocoding/v5/mapbox.places/${encodeURIComponent(locationName)}.json`;
  const params = {
    bbox: tnt_bbox,
    access_token: MAPBOX_ACCESS_TOKEN,
    limit: 1
  };

  try {
    const response = await axios.get(url, { params });
    const data = response.data;

    if (data.features && data.features.length > 0) {
      return data.features[0].geometry.coordinates as [number, number];
    }
    return null;
  } catch (error) {
    console.error('Error geocoding specific location:', error);
    return null;
  }
}

async function geocodeVague(locationName: string, referenceLocation: string): Promise<[number, number] | null> {
  // First, geocode the reference location
  const referenceCoords = await geocodeSpecific(referenceLocation);
  if (!referenceCoords) {
    return null;
  }

  // Now, search for the vague location near the reference location
  const url = `https://api.mapbox.com/geocoding/v5/mapbox.places/${encodeURIComponent(locationName)}.json`;
  const params = {
    access_token: MAPBOX_ACCESS_TOKEN,
    bbox: tnt_bbox,
    proximity: `${referenceCoords[0]},${referenceCoords[1]}`,
    limit: 1
  };

  try {
    const response = await axios.get(url, { params });
    const data = response.data;

    if (data.features && data.features.length > 0) {
      return data.features[0].geometry.coordinates as [number, number];
    }
    return null;
  } catch (error) {
    console.error('Error geocoding vague location:', error);
    return null;
  }
}

async function geocodeLocations(locations: Location[]): Promise<GeocodedLocation[]> {
  // console.log("received locations in geocodeLocations: ", locations, locations.length);
  // console.log("isArray:", Array.isArray(locations));
  // console.log("keys:", Object.keys(locations));

  const geocodedLocations: GeocodedLocation[] = [];

  for (const location of locations) {
    try {
      // console.log("individual location: ", location);
      let coordinates: [number, number] | null = null;

      if (location.type === 'specific') {
        // console.log("location type exists");
        coordinates = await geocodeSpecific(location.name);
      } else if (location.type === 'vague' && location.reference) {
        coordinates = await geocodeVague(location.name, location.reference);
      }

      if (coordinates) {
        geocodedLocations.push({
          name: location.name,
          coordinates
        });
      }
    } catch (err) {
      console.error("❌ Error during geocoding loop:", err, "location:", location);
      throw err; // rethrow to trigger the outer error handler
    }
  }

  return geocodedLocations;
}

function injectCoordinatesIntoMessage(userMessage: string, geocodedLocations: GeocodedLocation[]): string {
  let updatedMessage = userMessage;

  geocodedLocations.forEach(location => {
    const coordStr = ` (coordinates: ${location.coordinates[0]}, ${location.coordinates[1]})`;
    updatedMessage = updatedMessage.replace(location.name, location.name + coordStr);
  });

  return updatedMessage;
}

export async function sendChatMessage(message: string, history: Message[], is_spatial: boolean = false) {

  // Get all locations
  const urlLocations = `${import.meta.env.VITE_BASE_URL}/chat/identify_places?request=identify_places&app_version=0.7.0&structured_response=False&is_spatial=${is_spatial ? 'true' : 'false'}`;
  const payloadLocations = { "message": message };
  
  let locations: Location[];
  let locationEmbeddedMessage = message;

  embedLocation: try {
    const rawResponse = await sendPostRequest(urlLocations, payloadLocations, header); // Gives a string

    if (rawResponse === "No locations found.") break embedLocation; // If no locations, break

    const jsonResponse = typeof rawResponse === 'string' ? JSON.parse(rawResponse) : rawResponse;
    locations = jsonResponse.locations;
    locations = Object.values(locations);
    // console.log("received locations: ", locations, typeof locations);

    const geocodedLocations = await geocodeLocations(locations);
    // console.log("geocoded: ", geocodedLocations);
    locationEmbeddedMessage = injectCoordinatesIntoMessage(message, geocodedLocations);
    console.log("location embedded message: ", locationEmbeddedMessage);

  } catch (error) {
    // Error is already logged in sendPostRequest, so no need to handle here again
    console.error("Error while fetching locations.");
    throw error;
  }

  // Send chat message with history
  const urlChat = `${import.meta.env.VITE_BASE_URL}/chat?request=experiment_pit&app_version=0.7.0&structured_response=False&is_spatial=${is_spatial ? 'true' : 'false'}`;
  const formattedHistory = history.map(locationEmbeddedMessage => JSON.stringify(locationEmbeddedMessage)).join('\n');
  const jsonChat = {
    "client_query": JSON.stringify([...formattedHistory, { text: locationEmbeddedMessage, sender: "user" }]),
  };

  try {
    const response = await sendPostRequest(urlChat, jsonChat, header);
    console.log("END OF SENDCHATMESSAGE");
    return response;
  } catch (error) {
    console.error("Error while sending chat message.");
    throw error;
  }
}


export async function getChatSummary(messages: Message[], is_spatial: boolean = false) {
  const url = `${import.meta.env.VITE_BASE_URL}/chat/summary?app_version=0.7.0&is_spatial=${is_spatial ? 'true' : 'false'}`
  
  try {
    const response = await axios.post(url, {messages}, {headers: header});
    console.log(response.data.summary);
    return response.data.summary;
  } catch (error) {
    console.error("Failed to get chat summary:", error);
    return "Summary generation failed.";
  }
}

export async function getShotsData(filtered_date?: string, is_spatial: boolean = false){//must make sure it is in correct format
  const url = `${import.meta.env.VITE_BASE_URL}/data/query`

  const params = {
    app_version: '0.7.0',
    request: '911_shots_fired',
    output_type:'json',
    date: filtered_date,
    is_spatial: is_spatial ? 'true' : 'false',
  }

  const headers = {
    "RethinkAI-API-Key": import.meta.env.VITE_RETHINKAI_API_CLIENT_KEY,
  };

  try {
    // const response = await axios.get(url, { headers});
    // console.log("➡️ Sending GET request:", url);
    const response = await axios.get(url, { params, headers});
    console.log("➡️ Sending GET request:", url, params);
    console.log("✅ Response status:", response.status);
    console.log("🧾 Response data:", response.data);

    return response.data
  } catch (error: any) {
    if (axios.isAxiosError(error)) {
      console.error("❌ Axios error getting shots data:", {
        message: error.message,
        status: error.response?.status,
        data: error.response?.data,
      });
    } else {
      console.error("❌ Unknown error getting shots data:", error.toJSON());
    }

    throw error;
  }
} 

export async function get311Data(filtered_date?: number, category?: string, is_spatial: boolean = false){
  const url = `${import.meta.env.VITE_BASE_URL}/data/query` //should output type be
  const params = {
    request: '311_by_geo',
    category: category || 'all', //default to all if not provided 
    date: filtered_date,
    app_version: '0.7.0',
    output_type: 'stream',
    is_spatial: is_spatial ? 'true' : 'false', // check for spatial filtering
  }

  const headers = {
    "RethinkAI-API-Key": import.meta.env.VITE_RETHINKAI_API_CLIENT_KEY,
  };

  try {
    const response = await axios.get(url, { params, headers});
    console.log("➡️ Sending GET request:", url, params);

    console.log("✅ Response status:", response.status);
    console.log("🧾 Response data:", response.data);

    return response.data
  } catch (error: any) {
    if (axios.isAxiosError(error)) {
      console.error("❌ Axios error getting 311 data:", {
        message: error.message,
        status: error.response?.status,
        data: error.response?.data,
      });
    } else {
      console.error("❌ Unknown error getting 311 data:", error.toJSON());
    }

    throw error;
  }
}
