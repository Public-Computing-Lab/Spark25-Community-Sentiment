/*****************************************************************************************************************
 *  api.ts
 *
 *  This file contains functions to interact with the RethinkAI API.
 *  It includes functions to send chat messages, get chat summaries, and fetch data for 911 shots and 311 requests.
*****************************************************************************************************************/

import axios from "axios";
import type { Message } from "../constants/chatMessages"

// Define the headers for the API requests
// Ensure you have the RethinkAI API key set in your environment variables
const header = {
  "RethinkAI-API-Key": import.meta.env.VITE_RETHINKAI_API_CLIENT_KEY,
  "Content-Type": "application/json",
}


/* 
 * sendPostRequest:
 * Helper function to send the HTTP request and handle errors.
 *
 * Args:
 *   url: The endpoint URL to send the request to.
 *   payload: The data to send in the request body.
 *   headers: The headers to include in the request.
 *   
 * Returns:
 *   A promise that resolves to the response data if the request is successful.
 *   If an error occurs, it logs the error details and re-throws the error for further handling.
 *
 * Raises:
 *   Throws an error if the request fails, which can be caught by the caller.
 */
async function sendPostRequest(url: string, payload: any, headers: any) {

  try {
    // Log the request details for debugging
    console.log("➡️ Sending POST to:", url);
    console.log("📦 Payload:", payload);
    console.log("header: ", headers);

    // Send the POST request using axios
    const response = await axios.post(url, payload, { headers });
    
    // Log the response details for debugging
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

/* 
 * sendChatMessage:
 * Sends a chat message with history to the RethinkAI API and returns the response.
 *
 * Args:
 *   message: The chat message to send.
 *   history: An array of previous messages to include in the context.
 *   is_spatial: A boolean indicating whether to use spatial filtering.
 *
 * Returns:
 *   A promise that resolves to an object containing the response text and optional map data.
 *
 * Raises:
 *   Throws an error if the request fails, which can be caught by the caller.
 */
export async function sendChatMessage(message: string, history: Message[], is_spatial: boolean = false): Promise<{ text: string; mapData?: any }> {
  const urlChat = `${import.meta.env.VITE_BASE_URL}/chat?request=experiment_pit&app_version=0.8.0&structured_response=False&is_spatial=${is_spatial ? 'true' : 'false'}`;
  const formattedHistory = history.map(message => JSON.stringify(message)).join('\n');
  const jsonChat = {
    "client_query": JSON.stringify([...formattedHistory, { text: message, sender: "user" }]),
    "user_message": message
  };

  try {
    const response = await sendPostRequest(urlChat, jsonChat, header);
    console.log("received in sendChatMessage: ", response)
    console.log("END OF SENDCHATMESSAGE");
    return {
      text: response.response ?? "No response.",
      mapData: response.mapData ?? undefined,
    };
  } catch (error) {
    console.error("Error while sending chat message.");
    throw error;
  }
}

/* 
 * getChatSummary:
 * Retrieves a summary of the chat messages from the RethinkAI API.
 *
 * Args:
 *   messages: An array of chat messages to summarize.
 *   is_spatial: A boolean indicating whether to use spatial filtering.
 *
 * Returns:
 *   A promise that resolves to the summary text.
 *
 * Raises:
 *   Throws an error if the request fails, which can be caught by the caller.
 */
export async function getChatSummary(messages: Message[], is_spatial: boolean = false) {
  const url = `${import.meta.env.VITE_BASE_URL}/chat/summary?app_version=0.8.0&is_spatial=${is_spatial ? 'true' : 'false'}`
  
  try {
    // Format the messages for the API request
    const response = await axios.post(url, {messages}, {headers: header});
    console.log(response.data.summary);
    return response.data.summary;
  } catch (error) {
    console.error("Failed to get chat summary:", error);
    return "Summary generation failed.";
  }
}

/*
 * submitSurveyResponse:
 * Submits survey feedback to the RethinkAI API using the /log endpoint.
 *
 * Args:
 *   surveyResponses: An object containing the user's survey responses.
 *   interactionCount: The number of interactions when the survey was triggered.
 *
 * Returns:
 *   A promise that resolves to the response data if successful.
 *
 * Raises:
 *   Throws an error if the request fails, which can be caught by the caller.
 */
export async function submitSurveyResponse(surveyResponses: Record<string, string>, interactionCount: number) {
  const url = `${import.meta.env.VITE_BASE_URL}/log?app_version=0.8.0`;
  
  // Format survey data as requested by Chris - use client_query field
  const surveyData = {
    survey_responses: surveyResponses,
    interaction_count: interactionCount,
    timestamp: new Date().toISOString(),
    survey_type: "feedback_survey"
  };

  const payload = {
    client_query: JSON.stringify(surveyData),
    data_selected: "survey_feedback",
    data_attributes: "user_feedback_collection"
  };

  try {
    const response = await sendPostRequest(url, payload, header);
    console.log("✅ Survey response submitted successfully:", response);
    return response;
  } catch (error) {
    console.error("❌ Error submitting survey response:", error);
    throw error;
  }
}

/*
 * getShotsData:
 * Fetches 911 shots fired data from the RethinkAI API.
 *
 * Args:
 *   filtered_date: An optional date string to filter the data by.
 *   is_spatial: A boolean indicating whether to use spatial filtering.
 *
 * Returns:
 *   A promise that resolves to the response data containing the shots fired information.
 *
 * Raises:
 *   Throws an error if the request fails, which can be caught by the caller.
 */
export async function getShotsData(filtered_date?: string, is_spatial: boolean = false){ //must make sure it is in correct format
  const url = `${import.meta.env.VITE_BASE_URL}/data/query`

  // Set the parameters for the request
  const params = {
    app_version: '0.8.0',
    request: '911_shots_fired',
    output_type:'json',
    date: filtered_date,
    is_spatial: is_spatial ? 'true' : 'false',
  }

  // Set the headers for the request
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
    // Handle errors from the request
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

/*
 * get311Data:
 * Fetches 311 data from the RethinkAI API.
 *
 * Args:
 *   filtered_date: An optional date to filter the data by.
 *   category: An optional category to filter the data by (default is 'all').
 *   is_spatial: A boolean indicating whether to use spatial filtering (default is false).
 *
 * Returns:
 *   A promise that resolves to the response data containing the 311 requests.
 *
 * Raises:
 *   Throws an error if the request fails, which can be caught by the caller.
 */
export async function get311Data(filtered_date?: number, category?: string, is_spatial: boolean = false){
  const url = `${import.meta.env.VITE_BASE_URL}/data/query` //should output type be
  
  // Set the parameters for the request
  const params = {
    request: '311_by_geo',
    category: category || 'all', //default to all if not provided 
    date: filtered_date,
    app_version: '0.8.0',
    output_type: 'stream',
    is_spatial: is_spatial ? 'true' : 'false', // check for spatial filtering
  }

  // Set the headers for the request
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
    // Handle errors from the request
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
