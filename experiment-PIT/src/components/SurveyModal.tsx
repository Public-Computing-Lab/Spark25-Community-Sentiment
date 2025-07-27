/**
 * SurveyModal.tsx
 *
 * Modal component for collecting user feedback about the chatbot experience.
 * Shows after every 10 interactions as configured by your seniors.
 */

import React, { useState } from "react";
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  FormControl,
  FormLabel,
  RadioGroup,
  FormControlLabel,
  Radio,
  Typography,
  Box,
  IconButton,
  Alert,
} from "@mui/material";
import CloseIcon from "@mui/icons-material/Close";
import { SURVEY_QUESTIONS } from "../constants/chatMessages";

interface SurveyResponse {
  [key: string]: string;
}

interface SurveyModalProps {
  open: boolean;
  onClose: () => void;
  onSubmit: (responses: SurveyResponse) => void;
}

const SurveyModal: React.FC<SurveyModalProps> = ({
  open,
  onClose,
  onSubmit,
}) => {
  const [responses, setResponses] = useState<SurveyResponse>({});
  const [showThankYou, setShowThankYou] = useState(false);

  const handleResponseChange = (questionId: string, value: string) => {
    setResponses((prev) => ({
      ...prev,
      [questionId]: value,
    }));
  };

  const handleSubmit = () => {
    // Check if all questions are answered
    const allAnswered = SURVEY_QUESTIONS.every((q) => responses[q.id]);

    if (allAnswered) {
      onSubmit(responses);
      setShowThankYou(true);

      // Close modal after showing thank you message
      setTimeout(() => {
        setShowThankYou(false);
        setResponses({});
        onClose();
      }, 2000);
    }
  };

  const handleClose = () => {
    setResponses({});
    setShowThankYou(false);
    onClose();
  };

  const isComplete = SURVEY_QUESTIONS.every((q) => responses[q.id]);

  if (showThankYou) {
    return (
      <Dialog
        open={open}
        maxWidth="sm"
        fullWidth
        PaperProps={{
          sx: {
            borderRadius: 3,
            p: 2,
          },
        }}
      >
        <DialogContent>
          <Box sx={{ textAlign: "center", py: 4 }}>
            <Alert severity="success" sx={{ mb: 2 }}>
              <Typography variant="h6" sx={{ fontWeight: 600 }}>
                Thank you for your feedback!
              </Typography>
              <Typography variant="body2" sx={{ mt: 1 }}>
                Your input helps us improve On The Porch for the community.
              </Typography>
            </Alert>
          </Box>
        </DialogContent>
      </Dialog>
    );
  }

  return (
    <Dialog
      open={open}
      onClose={handleClose}
      maxWidth="sm"
      fullWidth
      PaperProps={{
        sx: {
          borderRadius: 3,
          p: 1,
        },
      }}
    >
      <DialogTitle sx={{ pb: 1 }}>
        <Box
          sx={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "flex-start",
          }}
        >
          <Box>
            <Typography
              variant="h6"
              component="div"
              sx={{ fontWeight: 600, color: "#02447C" }}
            >
              Help us improve On The Porch
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
              Your feedback helps us make the chatbot more helpful for the
              community.
            </Typography>
          </Box>
          <IconButton onClick={handleClose} size="small">
            <CloseIcon />
          </IconButton>
        </Box>
      </DialogTitle>

      <DialogContent sx={{ pt: 2 }}>
        {SURVEY_QUESTIONS.map((question, index) => (
          <Box key={question.id} sx={{ mb: 3 }}>
            <FormControl component="fieldset" fullWidth>
              <FormLabel
                component="legend"
                sx={{
                  fontWeight: 500,
                  color: "#02447C",
                  mb: 2,
                  fontSize: "0.95rem",
                }}
              >
                {question.question}
              </FormLabel>
              <RadioGroup
                value={responses[question.id] || ""}
                onChange={(e) =>
                  handleResponseChange(question.id, e.target.value)
                }
                sx={{
                  display: "grid",
                  gridTemplateColumns: "1fr 1fr", // Two columns
                  gap: 1,
                  "& .MuiFormControlLabel-root": {
                    margin: 0,
                  },
                }}
              >
                {question.options.map((option) => (
                  <FormControlLabel
                    key={option}
                    value={option}
                    control={
                      <Radio
                        sx={{
                          color: "#02447C",
                          "&.Mui-checked": {
                            color: "#02447C",
                          },
                          "& .MuiSvgIcon-root": {
                            fontSize: "1.2rem",
                          },
                        }}
                      />
                    }
                    label={
                      <Typography
                        variant="body2"
                        sx={{ fontSize: "0.85rem", lineHeight: 1.3 }}
                      >
                        {option}
                      </Typography>
                    }
                    sx={{
                      alignItems: "flex-start",
                      "& .MuiRadio-root": {
                        padding: "4px 8px 4px 4px",
                      },
                    }}
                  />
                ))}
              </RadioGroup>
            </FormControl>
          </Box>
        ))}
      </DialogContent>

      <DialogActions sx={{ px: 3, pb: 3 }}>
        <Button
          onClick={handleClose}
          sx={{
            color: "#666",
            textTransform: "none",
          }}
        >
          Skip
        </Button>
        <Button
          onClick={handleSubmit}
          disabled={!isComplete}
          variant="contained"
          sx={{
            backgroundColor: "#02447C",
            "&:hover": {
              backgroundColor: "#01335d",
            },
            textTransform: "none",
            px: 3,
          }}
        >
          Submit Feedback
        </Button>
      </DialogActions>
    </Dialog>
  );
};

export default SurveyModal;
