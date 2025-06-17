import React, { useState, useRef, useEffect } from "react";
import type { Message } from "../constants/chatMessages";
import {
  opening_message,
  suggested_questions,
} from "../constants/chatMessages";
import { BOTTOM_NAV_HEIGHT } from "../constants/layoutConstants";
import { sendChatMessage, getChatSummary } from "../api/api";
import { jsPDF } from "jspdf";
import { colorPalette } from "../assets/palette";

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
  CircularProgress,
} from "@mui/material";

import RoomIcon from "@mui/icons-material/Room";
import SendIcon from "@mui/icons-material/ArrowUpwardRounded";
import RefreshIcon from "@mui/icons-material/Refresh";
import DownloadIcon from "@mui/icons-material/DescriptionOutlined";

// Size of the blue arrow button (helps keep layout math tidy)
const SEND_BTN_SIZE = 44;

function Chat() {
  // ─── Local-storage helpers ─────────────────────────────────────────
  const getInitialMessages = (): Message[] => {
    const stored = localStorage.getItem("chatMessages");
    return stored ? JSON.parse(stored) : opening_message;
  };

  const [messages, setMessages] = useState<Message[]>(getInitialMessages);
  const [input, setInput] = useState("");
  const [isSending, setIsSending] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // confirm dialogs
  const [confirmClearOpen, setConfirmClearOpen] = useState(false);
  const [confirmExportOpen, setConfirmExportOpen] = useState(false);
  const [summaryError, setSummaryError] = useState(false);

  // persist chat
  useEffect(() => {
    localStorage.setItem("chatMessages", JSON.stringify(messages));
  }, [messages]);

  // ─── send handler ─────────────────────────────────────────────────
  const sendMessage = async (customInput?: string) => {
    const userMsg = (customInput ?? input).trim();
    if (!userMsg || isSending) return;

    setMessages((prev) => [...prev, { text: userMsg, sender: "user" }]);
    setInput("");
    setIsSending(true);

    try {
      const data = await sendChatMessage(userMsg, messages, true);
      setMessages((prev) => [
        ...prev,
        {
          text: data.response ?? "Sorry, no response from server.",
          sender: "Gemini",
        },
      ]);
    } catch {
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

  // ─── utils ────────────────────────────────────────────────────────
  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") sendMessage();
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
    doc.text(doc.splitTextToSize(summary, 180), 10, 20);
    doc.save("chat-summary.pdf");
  };

  // scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // ─── render ───────────────────────────────────────────────────────
  return (
    <>
      <Box
        sx={{
          display: "flex",
          flexDirection: "column",
          height: `calc(100vh - ${BOTTOM_NAV_HEIGHT}px)`,
          width: "100%",
          bgcolor: colorPalette.background,
          overflow: "hidden",
        }}
      >
        {/* ─── Header ─────────────────────────────────────────────── */}
        <Box
          sx={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            px: 2,
            height: 75,
            borderBottomLeftRadius: "16px",
            borderBottomRightRadius: "16px",
            bgcolor: colorPalette.dark,
            color: "#fff",
          }}
        >
          <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
            <RoomIcon fontSize="small" />
            <Typography variant="h6" sx={{ fontWeight: 600 }}>
              Chat with Us
            </Typography>
          </Box>
          <Box>
            <IconButton
              onClick={() => setConfirmExportOpen(true)}
              sx={{ color: "#fff" }}
            >
              <DownloadIcon />
            </IconButton>
            <IconButton
              onClick={() => setConfirmClearOpen(true)}
              sx={{ color: "#fff" }}
            >
              <RefreshIcon />
            </IconButton>
          </Box>
        </Box>
{/* ─── Messages ────────────────────────────────────────────── */}
<Box
  sx={{
    flex: 1,
    overflowY: "auto",
    px: 2,
    py: 1.5,
    display: "flex",
    flexDirection: "column",
    gap: 1.5,
  }}
>
  {messages.map((msg, i) => {
    const isBot = msg.sender === "Gemini";
    return (
      <Box
        key={i}
        sx={{
          alignSelf: isBot ? "flex-start" : "flex-end",
          bgcolor: isBot ? colorPalette.botBubble : colorPalette.userBubble,
          color:   isBot ? colorPalette.textOverBotBubble
                         : colorPalette.textOverUserBubble,
          px: 2,
          py: 1.5,
          maxWidth: "80%",
          borderRadius: 4,
          position: "relative",
          whiteSpace: "pre-wrap",
          fontSize: "0.95rem",
          lineHeight: 1.6,
          boxShadow: "0 1px 3px rgba(0,0,0,0.06)",
          border: isBot ? `1px solid ${colorPalette.dark}` : "none",

          /* ===== Tail outline ===== */
          "&::before": {
            content: '""',
            position: "absolute",
            top: 16,                     // exactly the border-radius
            ...(isBot
              ? {
                  left: -12,
                  borderTop:    "12px solid transparent",
                  borderBottom: "12px solid transparent",
                  borderRight:  `12px solid ${colorPalette.dark}`,
                }
              : {
                  right: -12,
                  borderTop:    "12px solid transparent",
                  borderBottom: "12px solid transparent",
                  borderLeft:   `12px solid ${colorPalette.userBubble}`,
                }),
          },

          /* ===== Tail fill ===== */
          "&::after": {
            content: '""',
            position: "absolute",
            top: 17,                     // one px lower to cover outline
            ...(isBot
              ? {
                  left: -11,
                  borderTop:    "11px solid transparent",
                  borderBottom: "11px solid transparent",
                  borderRight:  `11px solid ${colorPalette.botBubble}`,
                }
              : {
                  right: -11,
                  borderTop:    "11px solid transparent",
                  borderBottom: "11px solid transparent",
                  borderLeft:   `11px solid ${colorPalette.userBubble}`,
                }),
          },
        }}
      >
        {msg.text}
      </Box>
    );
  })}

  {isSending && (
    <Box
      sx={{
        alignSelf: "flex-start",
        display: "flex",
        alignItems: "center",
        gap: 1,
        bgcolor: colorPalette.botBubble,
        borderRadius: 16,
        border: `1px solid ${colorPalette.dark}`,
        px: 2,
        py: 1.5,
        color: colorPalette.textOverBotBubble,
      }}
    >
      <CircularProgress size={16} />
      <Typography variant="body2">Bot is thinking…</Typography>
    </Box>
  )}
  <div ref={messagesEndRef} />
</Box>

        {/* ─── Suggested questions (first-time helper) ─────────────── */}
        {messages.length === 1 && (
          <Box sx={{ mt: 0.5 }}>
            <Typography variant="subtitle1" sx={{ mb: 1, px: 2, color: colorPalette.dark, fontWeight: 500,  }}>
              Suggested Questions
            </Typography>
            {suggested_questions.map((q, idx) => (
              <Box
                key={idx}
                sx={{
                  mx: 2,
                  my: 0.5,
                  p: 1.5,
                  borderRadius: 7,
                  bgcolor: colorPalette.botBubble,
                  cursor: "pointer",
                  "&:hover": { backgroundColor: "#d3ecf4" },
                }}
                onClick={() => {
                  setInput(q.question);
                  sendMessage(q.question);
                }}
              >
                <Typography>{q.question}</Typography>
                <Typography variant="caption" color="text.secondary">
                  {q.subLabel}
                </Typography>
              </Box>
            ))}
          </Box>
        )}

        {/* ─── Input bar ──────────────────────────────────────────── */}
        <Box
          sx={{
            position: "relative",
            px: 2,
            pb: 1.25,
            pt: 0.5,
            bgcolor: colorPalette.background,
          }}
        >
          <TextField
            fullWidth
            placeholder="Type your safety concerns…"
            variant="outlined"
            size="small"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={isSending}
            sx={{
              "& .MuiOutlinedInput-root": {
                pr: `${SEND_BTN_SIZE + 15}px`, // space for arrow
                height: "60px",
                borderRadius: "24px",
                backgroundColor: "#f0f8ff",
                "& fieldset": { borderColor: "#b4c5d6" },
                "&:hover fieldset": { borderColor: colorPalette.dark },
                "&.Mui-focused fieldset": {
                  borderColor: colorPalette.dark,
                  boxShadow: "0 0 0 2px rgba(2,68,124,0.18)",
                },
              },
              "& input": { py: 1.5, pl: 2, fontSize: "0.95rem" },
            }}
          />

          {/* blue circular send button */}
          <IconButton
            onClick={() => sendMessage()}
            disabled={!input.trim() || isSending}
            sx={{
              position: "absolute",
              right: 28,
              top: "45%",
              transform: "translateY(-50%)",
              width: SEND_BTN_SIZE,
              height: SEND_BTN_SIZE,
              bgcolor: colorPalette.dark, // #02447C
              borderRadius: "50%",
              boxShadow: "0 2px 6px rgba(0,0,0,.22)",
              "&:hover": { bgcolor: "#003b6d" },
              "&.Mui-disabled": {
                bgcolor: colorPalette.dark,
                opacity: 0.35,
              },
            }}
          >
            <SendIcon sx={{ color: "#fff", fontSize: 22 }} />
          </IconButton>
        </Box>

        <Typography
          variant="caption"
          color="text.secondary"
          sx={{ textAlign: "center", pb: 0.75 }}
        >
          Chat responses may be inaccurate. Check important information.
        </Typography>
      </Box>

      {/* ─── Dialogs ──────────────────────────────────────────────── */}
      <Dialog open={confirmClearOpen} onClose={() => setConfirmClearOpen(false)}>
        <DialogTitle>Clear Chat?</DialogTitle>
        <DialogContent>
          <DialogContentText>
            This will remove all chat messages. Are you sure?
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirmClearOpen(false)}>Cancel</Button>
          <Button
            variant="contained"
            color="error"
            onClick={() => {
              handleClearChat();
              setConfirmClearOpen(false);
            }}
          >
            Clear
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog
        open={confirmExportOpen}
        onClose={() => setConfirmExportOpen(false)}
        PaperProps={{
    sx: {
      bgcolor: colorPalette.background,   
      borderRadius: 3,                   
      px: 3, py: 2,                      
    },
  }}
      >
        <DialogTitle>Export Chat Summary?</DialogTitle>
        <DialogContent>
          <DialogContentText>
            Download a one-page PDF summary of this conversation?
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirmExportOpen(false)}>Cancel</Button>

          <Button
            variant="contained"
            onClick={() => {
              handleExportSummary();
              setConfirmExportOpen(false);
            }}
          >
            Export
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={summaryError} onClose={() => setSummaryError(false)}>
        <DialogTitle>Summary Generation Failed</DialogTitle>
        <DialogContent>
          <DialogContentText>
            The summary couldnʼt be generated. Please try again later.
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setSummaryError(false)}>OK</Button>
        </DialogActions>
      </Dialog>
    </>
  );
}

export default Chat;
