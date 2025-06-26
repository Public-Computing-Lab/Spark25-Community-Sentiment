/**
 * chatMessages.ts
 *
 * This file defines the data structures for chat messages used in the app.
 *
 * ### Exports:
 * - **Message Type**: A type definition for the structure of a chat message.
 * - **opening_message**: The initial message presented by the AI when a user starts a conversation.
 * - **suggested_questions**: A list of pre-defined questions that help guide the user in their first interaction with the assistant.
 */

// The structure of a message in the chat, including the message text and the sender.
export type Message = {
  text: string;
  sender: "user" | "Gemini";
};

// Initial message sent by Gemini when the user starts a conversation.
export const opening_message: Message[] = [
    {
      text:
        "Hi there! Welcome to On The Porch. " +
        "I'm here to help you explore safety insights in the Talbot-Norfolk Triangle. " +
        "You can ask me about community concerns, city initiatives, and other neighborhood developments. " +
        "What would you like to explore?",
      sender: "Gemini", // Send by bot in chat
    },
];

// Suggested questions to help the user start the conversation.
export const suggested_questions = [
  {
    question: "What challenges are my neighbors discussing?",
    subLabel: "Search community meeting transcripts",
  },
  {
    question: "What is being done about speeding and traffic?",
    subLabel: "Explore city initiatives",
  },
  {
    question: "Tell me about youth spaces in the neighborhood",
    subLabel: "Learn about community organizations",
  },
];
