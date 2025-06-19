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
    question: "What are my neighbors worried about?",
    subLabel: "Searching community meeting transcripts",
  },
  {
    question: "How are the road conditions on Talbot Ave?",
    subLabel: "Exploring geographic data",
  },
  {
    question: "Where do residents avoid walking at night?",
    subLabel: "Learn about hot spots",
  },
];
