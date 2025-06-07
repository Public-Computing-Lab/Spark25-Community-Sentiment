export type Message = {
  text: string;
  sender: "user" | "Gemini";
};

export const opening_message: Message[] = [
    {
      text:
        "Hi there! Welcome to 26 Blocks. " +
        "I'm here to help you explore safety insights in your neighborhood. " +
        "What would you like to find today?",
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
