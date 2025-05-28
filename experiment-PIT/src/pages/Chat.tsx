import React, { useState, useRef, useEffect } from 'react'
import './Chat.css'

function Chat() {
  const [messages, setMessages] = useState<string[]>([])
  const [input, setInput] = useState('')
  const messagesEndRef = useRef<HTMLDivElement>(null)

  const sendMessage = () => {
    if (input.trim() === '') return
    setMessages(prev => [...prev, input.trim()])
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
          <div key={idx} className="chat-bubble">{msg}</div>
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
