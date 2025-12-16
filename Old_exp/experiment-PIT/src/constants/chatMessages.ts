/**
 * chatMessages.ts
 *
 * This file defines the data structures for chat messages used in the app.
 *
 * ### Exports:
 * - **Message Type**: A type definition for the structure of a chat message.
 * - **opening_message**: The initial message presented by the AI when a user starts a conversation.
 * - **suggested_questions**: A list of pre-defined questions that help guide the user in their first interaction with the assistant.
 * - **SURVEY_QUESTIONS**: Survey questions for user feedback
 * - **SURVEY_CONFIG**: Configuration for when to show survey
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

// Survey questions based on your seniors' requirements
export const SURVEY_QUESTIONS = [
  {
    id: "helpfulness",
    question: "How helpful are the answers from the chat bot?",
    options: ["Very helpful", "Somewhat helpful", "Not very helpful", "Not helpful at all"]
  },
  {
    id: "understanding",
    question: "Do you feel the chatbot understands your questions or concerns?",
    options: ["Yes, completely", "Yes, somewhat", "No, not really", "No, not at all"]
  },
  {
    id: "satisfaction",
    question: "How satisfied are you with your experience?",
    options: ["Very satisfied", "Satisfied", "Dissatisfied", "Very dissatisfied"]
  }
];

// Survey configuration - Chris's suggestion: first at 5, then every 10
export const SURVEY_CONFIG = {
  FIRST_TRIGGER: 5,     // Show after 5 interactions
  RECURRING_TRIGGER: 10 // Then every 10 interactions after that
};