export type Message = {
  text: string;
  sender: "user" | "ml";
};

export const opening_message: Message[] = [
    {
      text:
        "Hi there! Welcome to 26 Blocks. " +
        "I'm here to help you explore safety insights in your neighborhood. " +
        "What would you like to find today?",
      sender: "ml",
    },
  ];
