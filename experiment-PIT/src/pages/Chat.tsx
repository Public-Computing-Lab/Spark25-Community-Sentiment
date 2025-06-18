import React, { useState, useRef, useEffect } from "react";
import type { Message } from "../constants/chatMessages";
import {
  opening_message,
  suggested_questions,
} from "../constants/chatMessages";
import { BOTTOM_NAV_HEIGHT } from "../constants/layoutConstants";
import { sendChatMessage, getChatSummary } from "../api/api";
import { jsPDF } from "jspdf";

import {
  Box,
  Typography,
  TextField,
  IconButton,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogContentText,
  DialogActions,
  Button,
} from "@mui/material";
import SendIcon from "@mui/icons-material/Send";
import RefreshIcon from "@mui/icons-material/Refresh";
import DownloadIcon from "@mui/icons-material/Download";
import CircularProgress from "@mui/material/CircularProgress";

function Chat() {
  const getInitialMessages = (): Message[] => {
    const storedMessages = localStorage.getItem("chatMessages");
    return storedMessages ? JSON.parse(storedMessages) : opening_message;
  };

  const [messages, setMessages] = useState<Message[]>(getInitialMessages);
  const [input, setInput] = useState("");
  const [isSending, setIsSending] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const [confirmClearOpen, setConfirmClearOpen] = useState(false);
  const [confirmExportOpen, setConfirmExportOpen] = useState(false);
  const [summaryError, setSummaryError] = useState(false);

  // Save messages to localStorage when they change
  useEffect(() => {
    localStorage.setItem("chatMessages", JSON.stringify(messages));
  }, [messages]);

  const sendMessage = async (customInput?: string) => {
    const userMsg = (customInput ?? input).trim();
    if (userMsg === "" || isSending) return;

    setMessages((prev) => [...prev, { text: userMsg, sender: "user" }]);
    setInput("");
    setIsSending(true);

    try {
      // Call backend API helper to get AI response
      const data = await sendChatMessage(userMsg, messages, true);

      // Append backend response to messages
      if (data.response) {
        setMessages((prev) => [
          ...prev,
          { text: data.response, sender: "Gemini" },
        ]);
      } else {
        setMessages((prev) => [
          ...prev,
          { text: "Sorry, no response from server.", sender: "Gemini" },
        ]);
      }
    } catch (error) {
      setMessages((prev) => [
        ...prev,
        {
          text: "Oops, something went wrong. Please try again.",
          sender: "Gemini",
        },
      ]);
    } finally {
      setIsSending(false);
    }
  };

  const handleClearChat = () => {
    localStorage.removeItem("chatMessages");
    setMessages(getInitialMessages());
  };

  const handleExportSummary = async () => {
    const summary = await getChatSummary(messages, true);

    if (summary === "Summary generation failed.") {
      setSummaryError(true);
      return;
    }

    const doc = new jsPDF();
    const margin = 10;
    const lineHeight = 10;
    const maxLineWidth = 180; // A4 page width minus margins

    const lines = doc.splitTextToSize(summary, maxLineWidth);
    doc.text(lines, margin, margin + lineHeight);

    doc.save("chat-summary.pdf");
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") sendMessage();
  };

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  return (
    <>
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
        <Box
          sx={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            mb: 2,
          }}
        >
          <Typography variant="h4" component="h1">
            On The Porch!
          </Typography>
          <Box>
            <IconButton
              aria-label="Export Chat Summary"
              onClick={() => setConfirmExportOpen(true)}
            >
              <DownloadIcon />
            </IconButton>
            <IconButton
              aria-label="Clear Chat"
              onClick={() => setConfirmClearOpen(true)}
            >
              <RefreshIcon />
            </IconButton>
          </Box>
        </Box>

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
                alignSelf: msg.sender === "Gemini" ? "flex-start" : "flex-end",
                bgcolor: "background.paper",
                color: "text.primary",
                border: 2,
                borderColor: "text.primary",
                borderRadius: 2,
                maxWidth: "75%",
                fontSize: "1.2rem",
                p: 1.5,
                wordWrap: "break-word",
                textAlign: msg.sender === "Gemini" ? "left" : "right",
                whiteSpace: "pre-wrap",
                opacity:
                  isSending &&
                  msg.sender === "Gemini" &&
                  idx === messages.length - 1
                    ? 0.6
                    : 1,
              }}
            >
              {msg.text}
            </Box>
          ))}
          {isSending && (
            <Box
              sx={{
                alignSelf: "flex-start",
                display: "flex",
                alignItems: "center",
                gap: 1,
                bgcolor: "background.paper",
                border: 2,
                borderColor: "text.secondary",
                borderRadius: 2,
                maxWidth: "75%",
                p: 1.5,
              }}
            >
              <CircularProgress size={16} />
              <Typography variant="body2" color="text.secondary">
                Bot is thinking...
              </Typography>
            </Box>
          )}

          <div ref={messagesEndRef} />
        </Box>

        {messages.length === 1 && (
          <Box sx={{ mt: 2 }}>
            <Typography variant="subtitle1" sx={{ mb: 1 }}>
              Suggested Questions
            </Typography>
            {suggested_questions.map((q, idx) => (
              <Box
                key={idx}
                sx={{
                  px: 2,
                  py: 1,
                  mb: 1,
                  borderRadius: 2,
                  bgcolor: "background.paper",
                  border: "1px solid",
                  borderColor: "divider",
                  cursor: "pointer",
                  "&:hover": {
                    backgroundColor: "action.hover",
                  },
                }}
                onClick={() => {
                  setInput(q.question);
                  sendMessage(q.question);
                }}
              >
                <Typography variant="body1">{q.question}</Typography>
                <Typography variant="caption" color="text.secondary">
                  {q.subLabel}
                </Typography>
              </Box>
            ))}
          </Box>
        )}

        <Box
          component="form"
          onSubmit={(e) => {
            e.preventDefault();
            sendMessage();
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
            placeholder="Type to learn about community safety..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            InputProps={{ disableUnderline: true }}
            sx={{ px: 1 }}
            disabled={isSending}
          />

          <IconButton
            color="primary"
            onClick={() => sendMessage()}
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

      {/* Confirm Clear Dialog */}
      <Dialog
        open={confirmClearOpen}
        onClose={() => setConfirmClearOpen(false)}
      >
        <DialogTitle>Clear Chat?</DialogTitle>
        <DialogContent>
          <DialogContentText>
            This will remove all chat messages. Are you sure you want to
            continue?
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirmClearOpen(false)}>Cancel</Button>
          <Button
            onClick={() => {
              handleClearChat();
              setConfirmClearOpen(false);
            }}
            color="error"
            variant="contained"
          >
            Clear
          </Button>
        </DialogActions>
      </Dialog>

      {/* Confirm Export Dialog */}
      <Dialog
        open={confirmExportOpen}
        onClose={() => setConfirmExportOpen(false)}
      >
        <DialogTitle>Export Chat Summary?</DialogTitle>
        <DialogContent>
          <DialogContentText>
            This will download a summary of the chat as a pdf. Do you want to
            continue?
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirmExportOpen(false)}>Cancel</Button>
          <Button
            onClick={() => {
              handleExportSummary();
              setConfirmExportOpen(false);
            }}
            color="primary"
            variant="contained"
          >
            Export
          </Button>
        </DialogActions>
      </Dialog>

      {/* Summary Failed Dialog */}
      <Dialog open={summaryError} onClose={() => setSummaryError(false)}>
        <DialogTitle>Summary Generation Failed</DialogTitle>
        <DialogContent>
          <DialogContentText>
            The summary could not be generated. Please try again later.
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setSummaryError(false)} autoFocus>
            OK
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}

export default Chat;
