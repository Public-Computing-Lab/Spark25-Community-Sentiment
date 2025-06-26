/**
 * Chat.tsx
 *
 * This file provides a chat interface component that allows users to send and receive messages from an AI assistant.
 * The component supports:
 * - Sending and receiving text messages with the AI (Gemini).
 * - Displaying chat history, with messages coming from either the user or the AI.
 * - Exporting the chat history to a PDF summary.
 * - Clearing the chat history stored in local storage.
 *
 * It uses Material UI for layout and UI elements, and integrates with an API to send messages and fetch summaries.
 */

import React, { useState, useRef, useEffect } from "react";
import type { Message } from "../constants/chatMessages";

// Import constants and API helpers
import {
  opening_message,
  suggested_questions,
} from "../constants/chatMessages";
import { BOTTOM_NAV_HEIGHT, SEND_BTN_SIZE } from "../constants/layoutConstants";
import { sendChatMessage, getChatSummary } from "../api/api";
import { jsPDF } from "jspdf";
import { MdTextRender } from "jspdf-md-renderer";
import { colorPalette } from "../assets/palette";
import FileDownloadOutlinedIcon from "@mui/icons-material/FileDownloadOutlined";

// MUI components
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
import SendIcon from "@mui/icons-material/ArrowUpwardRounded";
import RefreshIcon from "@mui/icons-material/Refresh";
import onLogo from "/public/on_the_porch_logo.png";

/**
 * Chat
 *
 * A functional React component that renders a full chat interface where users can interact with an AI assistant.
 * This component handles the sending and receiving of messages, displays the conversation history,
 * and provides options to export the chat summary or clear the chat.
 *
 * ### Dependencies:
 * - `useState`, `useRef`, `useEffect` from React for managing state and effects.
 * - `sendChatMessage` and `getChatSummary` from the `api/api` module to interact with the backend.
 * - `jsPDF` and `MdTextRender` for generating a PDF summary of the chat.
 * - `Box`, `Typography`, `TextField`, `IconButton`, and other MUI components for the UI.
 * - `colorPalette` from local theme assets for custom styling.
 * - `BOTTOM_NAV_HEIGHT` for consistent layout height across the app.
 *
 * ### State:
 * - `messages` (array): The list of messages in the chat history.
 * - `input` (string): The current text input from the user.
 * - `isSending` (boolean): A flag to track if a message is currently being sent.
 * - `confirmClearOpen` (boolean): Whether the clear chat confirmation dialog is open.
 * - `confirmExportOpen` (boolean): Whether the export chat summary confirmation dialog is open.
 * - `summaryError` (boolean): Whether there was an error generating the chat summary.
 *
 * ### Returns:
 * - A JSX element representing the full chat interface with:
 *   - Chat history.
 *   - User input field.
 *   - Send button.
 *   - Option to clear the chat or export the summary.
 *   - Dialogs for clearing chat or exporting the summary.
 *
 * ### Side Effects:
 * - Calls the backend API to get the AI's response when a message is sent.
 * - Automatically scrolls to the bottom of the chat history when a new message is added.
 * - Displays loading indicators while waiting for the AI's response.
 * - Opens confirmation dialogs for clearing the chat or exporting the summary.
 *
 * ### Raises:
 * - If there is an error in generating the summary, displays a summary error dialog.
 */
function Chat() {
  // ─── Local-storage helpers ─────────────────────────────────────────
  /**
   * Retrieves initial messages from local storage or sets the opening message if none is found.
   *
   * @returns {Message[]} Initial set of messages.
   */
  const getInitialMessages = (): Message[] => {
    const stored = localStorage.getItem("chatMessages");
    return stored ? JSON.parse(stored) : opening_message;
  };

  // States for chat, input, sending status, etc.
  const [messages, setMessages] = useState<Message[]>(getInitialMessages);
  const [input, setInput] = useState("");
  const [isSending, setIsSending] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // States for confirmation dialogs
  const [confirmClearOpen, setConfirmClearOpen] = useState(false);
  const [confirmExportOpen, setConfirmExportOpen] = useState(false);
  const [summaryError, setSummaryError] = useState(false);

  // ─── send handler ─────────────────────────────────────────────────
  /**
   * Sends a chat message to the server and appends the response to the chat.
   *
   * @param {string} [customInput] Optional custom input for the message.
   */
  const sendMessage = async (customInput?: string) => {
    const userMsg = (customInput ?? input).trim();
    if (!userMsg || isSending) return;

    // Update the message list with the user's message
    setMessages((prev) => [...prev, { text: userMsg, sender: "user" }]);
    setInput(""); // Reset input field
    setIsSending(true); // Indicate that a message is being sent

    try {
      // Send the message to the server and get a response
      const data = await sendChatMessage(userMsg, messages, true);

      // Append the server's response to the chat
      if (data.text) {
        setMessages((prev) => [...prev, { text: data.text, sender: "Gemini" }]);
      } else {
        setMessages((prev) => [
          ...prev,
          { text: "Sorry, no response from server.", sender: "Gemini" },
        ]);
      }
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          text: "Oops, something went wrong. Please try again.",
          sender: "Gemini",
        },
      ]);
    } finally {
      setIsSending(false); // Reset sending status
    }
  };

  // ─── utils ────────────────────────────────────────────────────────
  /**
   * Handles the "Enter" key press to send a message.
   *
   * @param {React.KeyboardEvent<HTMLInputElement>} e The keyboard event.
   */
  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") sendMessage();
  };

  /**
   * Clears the chat history from local storage and resets the message list.
   */
  const handleClearChat = () => {
    localStorage.removeItem("chatMessages");
    setMessages(getInitialMessages());
  };

  /**
   * Exports the chat summary as a PDF.
   */
  const handleExportSummary = async () => {
    const summary = await getChatSummary(messages, true);

    if (summary === "Summary generation failed.") {
      setSummaryError(true);
      return;
    }

    const doc = new jsPDF({ format: "a4", orientation: "portrait" });

    // Add app name to document
    doc.setFont("helvetica", "normal");
    doc.setFontSize(16);
    const pageHeight = doc.internal.pageSize.getHeight();
    doc.text(
      "On The Porch",
      doc.internal.pageSize.getWidth() / 2,
      pageHeight - 10,
      { align: "center" }
    );

    // Set formatting options for summary
    const options = {
      cursor: { x: 10, y: 10 },
      page: {
        cursor: { x: 10, y: 10 },
        format: "a4",
        maxContentWidth: 190,
        maxContentHeight: 277,
        lineSpace: 1.5,
        defaultLineHeightFactor: 1.2,
        defaultFontSize: 12,
        defaultTitleFontSize: 18,
        topmargin: 10,
        xpading: 10,
        xmargin: 10,
        indent: 10,
      },
      font: {
        bold: { name: "helvetica", style: "bold" },
        regular: { name: "helvetica", style: "normal" },
        light: { name: "helvetica", style: "light" },
      },
      color: "#000000",
      endCursorYHandler: (y: number) => {
        console.log("End cursor Y position:", y);
      },
    };

    // Use MdTextRender function and Gemini's MD response to render summary
    await MdTextRender(doc, summary, options);

    // Save the PDF as 'chat-summary.pdf'
    doc.save("chat-summary.pdf");
  };

  // Scroll to bottom on new messages
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
            <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
              <img
                src={onLogo}
                alt="On The Porch Logo"
                style={{
                  height: 70,
                  width: "auto",
                  display: "block",
                  marginTop: 6,
                }}
              />
            </Box>
          </Box>
          <Box>
            {/* Export and Clear chat buttons */}
            <IconButton
              onClick={() => setConfirmExportOpen(true)}
              sx={{ color: "#fff" }}
            >
              <FileDownloadOutlinedIcon />
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
                  bgcolor: isBot
                    ? colorPalette.botBubble
                    : colorPalette.userBubble,
                  color: isBot
                    ? colorPalette.textOverBotBubble
                    : colorPalette.textOverUserBubble,
                  px: 2,
                  py: 1.5,
                  maxWidth: "80%",
                  borderBottomLeftRadius: "15px",
                  borderBottomRightRadius: "15px",
                  borderTopRightRadius: "15px",
                  borderTopLeftRadius: "15px",
                  position: "relative",
                  whiteSpace: "pre-wrap",
                  fontSize: "1.25rem",
                  fontWeight: 440,
                  lineHeight: 1.6,
                  boxShadow: "0 1px 3px rgba(0,0,0,0.06)",
                  border: isBot ? `1px solid ${colorPalette.dark}` : "none",

                  "&::before, &::after": {
                    content: '""',
                    position: "absolute",

                    top: "calc(50% - 12px)", // 12 px is half the arrow height
                  },

                  "&::before": isBot
                    ? {
                        left: -12,
                        borderTop: "12px solid transparent",
                        borderBottom: "12px solid transparent",
                        borderRight: `12px solid ${colorPalette.dark}`, // outline color
                      }
                    : {
                        right: -12,
                        borderTop: "12px solid transparent",
                        borderBottom: "12px solid transparent",
                        borderLeft: `12px solid ${colorPalette.userBubble}`,
                      },

                  "&::after": isBot
                    ? {
                        left: -11,
                        borderTop: "11px solid transparent",
                        borderBottom: "11px solid transparent",
                        borderRight: `11px solid ${colorPalette.botBubble}`, // fill color
                      }
                    : {
                        right: -11,
                        borderTop: "11px solid transparent",
                        borderBottom: "11px solid transparent",
                        borderLeft: `11px solid ${colorPalette.userBubble}`,
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
              <Typography variant="body2">Thinking…</Typography>
            </Box>
          )}
          <div ref={messagesEndRef} />
        </Box>

        {/* ─── Suggested questions (first-time helper) ─────────────── */}
        {messages.length === 1 && (
          <Box sx={{ mt: 0.5 }}>
            <Typography
              variant="subtitle1"
              sx={{ mb: 1, px: 2, color: colorPalette.dark, fontWeight: 500 }}
            >
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
      <Dialog
        open={confirmClearOpen}
        onClose={() => setConfirmClearOpen(false)}
        PaperProps={{
          sx: {
            bgcolor: colorPalette.background, // same light-blue card
            borderRadius: 3,
            px: 3,
            py: 2,
          },
        }}
      >
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
            px: 3,
            py: 2,
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
