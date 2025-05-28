import React, { useState, useRef, useEffect } from 'react'
import './Chat.css'

function Chat() {
  type Message = {
    text: string
    sender: 'user' | 'ml'
  }
  const [messages, setMessages] = useState<Message[]>([
    { text: 'Hi there! Welcome to 26 Blocks. I\'m here to help you explore safety insights in your neighborhood. What would you like to find today?', sender: 'ml'}
  ])
  const [input, setInput] = useState('')
  const messagesEndRef = useRef<HTMLDivElement>(null)

  const sendMessage = () => {
    if (input.trim() === '') return
    const userMsg = input.trim()

    setMessages(prev => [...prev, {text: userMsg, sender: 'user'}])
    setInput('')
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') sendMessage()
  }

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  return (
    <div className="chat-wrapper">
      <h1>Chat with Us</h1>

      <div className="chat-messages">
        {messages.map((msg, idx) => (
          <div 
            key={idx} 
            className={msg.sender === 'ml' ? 'ml-chat-bubble' : 'user-chat-bubble'}
          >
            {msg.text}
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>

      <div className="chat-input-container">
        <input
          type="text"
          className="chat-input"
          placeholder="Type your safety concerns..."
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
        />
        <button className="chat-send" onClick={sendMessage}>
          ➤
        </button>
      </div>
    </div>
  )
}

export default Chat
