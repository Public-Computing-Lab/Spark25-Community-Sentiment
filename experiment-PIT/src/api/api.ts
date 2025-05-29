// src/api/api.ts
import axios from "axios";

const BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8888"; // fallback if env missing

const headers = {
  "RethinkAI-API-Key": import.meta.env.VITE_RETHINKAI_API_KEY || "",
};

/**
 * Sends a user message to the backend /chat endpoint and returns the response.
 * @param message The user's chat message
 * @returns The API response data
 */
export async function sendChatMessage(message: string) {
  try {
    const url = `${BASE_URL}/chat`;
    const payload = {
      client_query: message,
      prompt_preamble: "",
    };
    const response = await axios.post(url, payload, { headers });
    return response.data;
  } catch (error) {
    console.error("Error sending chat message:", error);
    throw error;
  }
}
