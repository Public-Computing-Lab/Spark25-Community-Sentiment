import axios from "axios";
import type { Message } from "../constants/chatMessages"

const header = {
    "RethinkAI-API-Key": import.meta.env.VITE_RETHINKAI_API_CLIENT_KEY,
    "Content-Type": "application/json",
  }

export async function sendChatMessage(message: string) {
  const url = `${import.meta.env.VITE_BASE_URL}/chat?request=experiment_pit&app_version=0.7.0&structured_response=False`

  const json = {
    "client_query": message,
  };

  try {
    console.log("➡️ Sending POST to:", url);
    console.log("📦 Payload:", json);
    console.log("header: ", header);
    
    const response = await axios.post(url, json, {
      headers: header
    });
    
    console.log("✅ Response status:", response.status);
    console.log("🧾 Response data:", response.data);

    return response.data;
  } catch (error: any) {
    if (axios.isAxiosError(error)) {
      console.error("❌ Axios error sending chat message:", {
        message: error.message,
        status: error.response?.status,
        data: error.response?.data,
      });
    } else {
      console.error("❌ Unknown error sending chat message:", error);
    }

    throw error;
  }
}

export async function getChatSummary(messages: Message[]) {
  const url = `${import.meta.env.VITE_BASE_URL}/chat/summary?app_version=0.7.0`
  
  try {
    const response = await axios.post(url, {messages}, {headers: header});
    return response.data.summary;
  } catch (error) {
    console.error("Failed to get chat summary:", error);
    return "Summary generation failed.";
  }
}

export async function getShotsData(){//need to integrate date filtering???
  const url = `${import.meta.env.VITE_BASE_URL}/data/query?request=911_shots_fired&app_version=0.7.0&output_type=stream`

  try {
    console.log("➡️ Sending GET request:", url);
    const response = await axios.get(url);

    console.log("✅ Response status:", response.status);
    console.log("🧾 Response data:", response.data);

  }
  finally {
    return;
  }
} 
