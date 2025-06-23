export type Message = {
  text: string;
  sender: "user" | "Gemini";
};

export const opening_message: Message[] = [
    {
      text:
        "Hi there! Welcome to On The Porch. " +
        "I'm here to help you explore safety insights in the Talbot-Norfolk Triangle. " +
        "You can ask me about community concerns, city initiatives, and other neighborhood developments. " +
        "What would you like to explore?",
      sender: "Gemini",
    },
];

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
