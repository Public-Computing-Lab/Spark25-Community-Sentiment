import React, { useState, useRef, useEffect } from 'react'
import { Box, Typography, TextField, IconButton } from '@mui/material'
import SendIcon from '@mui/icons-material/Send'

function Chat() {
  type Message = {
    text: string
    sender: 'user' | 'ml'
  }
  const [messages, setMessages] = useState<Message[]>([
    {
      text:
        "Hi there! Welcome to 26 Blocks. I'm here to help you explore safety insights in your neighborhood. What would you like to find today?",
      sender: 'ml',
    },
  ])
  const [input, setInput] = useState('')
  const messagesEndRef = useRef<HTMLDivElement>(null)

  const sendMessage = () => {
    if (input.trim() === '') return
    const userMsg = input.trim()
    setMessages((prev) => [...prev, { text: userMsg, sender: 'user' }])
    setInput('')
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') sendMessage()
  }

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  return (
    <Box
      sx={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        width: '100%',
        bgcolor: 'background.paper',
        color: 'text.primary',
        overflow: 'hidden',
        position: 'relative',
        p: 2,
      }}
    >
      <Typography variant="h4" component="h1" mb={2}>
        Chat with Us
      </Typography>

      <Box
        sx={{
          flex: 1,
          overflowY: 'auto',
          display: 'flex',
          flexDirection: 'column',
          gap: 1.25,
          bgcolor: 'background.default',
          px: 1,
          pb: 1,
          borderRadius: 1,
          border: '1px solid',
          borderColor: 'divider',
        }}
      >
        {messages.map((msg, idx) => (
          <Box
            key={idx}
            sx={{
              alignSelf: msg.sender === 'ml' ? 'flex-start' : 'flex-end',
              bgcolor: 'background.paper',
              color: 'text.primary',
              border: 2,
              borderColor: 'text.primary',
              borderRadius: 2,
              maxWidth: '75%',
              fontSize: '1.2rem',
              p: 1.5,
              wordWrap: 'break-word',
              textAlign: msg.sender === 'ml' ? 'left' : 'right',
              whiteSpace: 'pre-wrap',
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
          display: 'flex',
          alignItems: 'center',
          border: 1,
          borderColor: 'divider',
          borderRadius: 1,
          mt: 2,
          p: 0.5,
          bgcolor: 'background.paper',
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
        />

        <IconButton
          color="primary"
          onClick={sendMessage}
          disabled={input.trim() === ''}
          aria-label="send message"
          sx={{ ml: 1 }}
        >
          <SendIcon />
        </IconButton>
      </Box>
    </Box>
  )
}

export default Chat
