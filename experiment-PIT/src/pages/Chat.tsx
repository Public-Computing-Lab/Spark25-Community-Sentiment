import React, { useState, useRef, useEffect } from "react"
import { BOTTOM_NAV_HEIGHT } from "../constants/layoutConstants"
import { Box, Typography, TextField, IconButton } from "@mui/material"
import SendIcon from "@mui/icons-material/Send"
import { sendChatMessage } from "../api/api"

type Message = {
  text: string
  sender: "user" | "ml"
}

function Chat() {
  const [messages, setMessages] = useState<Message[]>(() => {
    const storedMessages = localStorage.getItem("chatMessages")
    return storedMessages
      ? JSON.parse(storedMessages)
      : [
          {
          text: "Hi there! Welcome to 26 Blocks.",
          sender: "ml",
          },
          {
            text: "I'm here to help you explore safety insights in your neighborhood.",
            sender: "ml",
          },
          {
            text: "What would you like to find today?",
            sender: "ml",
          },
        ]
  })
  const [input, setInput] = useState("")
  const [isSending, setIsSending] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  // Save messages to localStorage when they change
  useEffect(() => {
    localStorage.setItem("chatMessages", JSON.stringify(messages))
  }, [messages])

  const sendMessage = async () => {
    if (input.trim() === "" || isSending) return

    const userMsg = input.trim()
    setMessages((prev) => [...prev, { text: userMsg, sender: "user" }])
    setInput("")
    setIsSending(true)

    try {
      // Call backend API helper to get AI response
      const data = await sendChatMessage(userMsg)

      // Append backend response to messages
      if (data.response) {
        setMessages((prev) => [...prev, { text: data.response, sender: "ml" }])
      } else {
        setMessages((prev) => [
          ...prev,
          { text: "Sorry, no response from server.", sender: "ml" },
        ])
      }
    } catch (error) {
      setMessages((prev) => [
        ...prev,
        {
          text: "Oops, something went wrong. Please try again.",
          sender: "ml",
        },
      ])
    } finally {
      setIsSending(false)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") sendMessage()
  }

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages])

  return (
    <Box
      sx={{
        display: "flex",
        flexDirection: "column",
        height: `calc(100vh - ${BOTTOM_NAV_HEIGHT}px)`,
        width: "100%",
        bgcolor: "background.paper",
        color: "text.primary",
        overflow: "hidden",
        position: "relative",
        p: 2,
      }}
    >
      <Typography variant="h4" component="h1" mb={2}>
        Chat with Us
      </Typography>

      <Box
        sx={{
          flex: 1,
          overflowY: "auto",
          display: "flex",
          flexDirection: "column",
          gap: 1.25,
          bgcolor: "background.default",
          px: 1,
          pb: 1,
          borderRadius: 1,
          border: "1px solid",
          borderColor: "divider",
        }}
      >
        {messages.map((msg, idx) => (
          <Box
            key={idx}
            sx={{
              alignSelf: msg.sender === "ml" ? "flex-start" : "flex-end",
              bgcolor: "background.paper",
              color: "text.primary",
              border: 2,
              borderColor: "text.primary",
              borderRadius: 2,
              maxWidth: "75%",
              fontSize: "1.2rem",
              p: 1.5,
              wordWrap: "break-word",
              textAlign: msg.sender === "ml" ? "left" : "right",
              whiteSpace: "pre-wrap",
              opacity: isSending && msg.sender === "ml" && idx === messages.length - 1 ? 0.6 : 1,
            }}
          >
            {msg.text}
          </Box>
        ))}
        <div ref={messagesEndRef} />
      </Box>

      <Box
        component="form"
        onSubmit={(e) => {
          e.preventDefault()
          sendMessage()
        }}
        sx={{
          display: "flex",
          alignItems: "center",
          border: 1,
          borderColor: "divider",
          borderRadius: 1,
          mt: 2,
          p: 0.5,
          bgcolor: "background.paper",
        }}
      >
        <TextField
          fullWidth
          variant="standard"
          placeholder="Type your safety concerns..."
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          InputProps={{ disableUnderline: true }}
          sx={{ px: 1 }}
          disabled={isSending}
        />

        <IconButton
          color="primary"
          onClick={sendMessage}
          disabled={input.trim() === "" || isSending}
          aria-label="send message"
          sx={{ ml: 1 }}
        >
          <SendIcon />
        </IconButton>
      </Box>
      <Typography
        variant="caption"
        color="text.secondary"
        sx={{ mt: 0.1, mb: 0, textAlign: "center" }}
      >
        Chat responses may be inaccurate. Check important information.
      </Typography>
    </Box>
  )
}

export default Chat
