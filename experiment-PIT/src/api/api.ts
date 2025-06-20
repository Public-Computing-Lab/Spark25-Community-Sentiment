import axios from "axios";
import type { Message } from "../constants/chatMessages"

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

export async function sendChatMessage(message: string, history: Message[], is_spatial: boolean = false) {
  // Send chat message with history
  const urlChat = `${import.meta.env.VITE_BASE_URL}/chat?request=experiment_pit&app_version=0.7.0&structured_response=False&is_spatial=${is_spatial ? 'true' : 'false'}`;
  const formattedHistory = history.map(message => JSON.stringify(message)).join('\n');
  const jsonChat = {
    "client_query": JSON.stringify([...formattedHistory, { text: message, sender: "user" }]),
    "user_message": message
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
