# Use official Python image
FROM python:3.11-slim

# Set working directory inside the container
WORKDIR /app/ReThink_AI_Chatbot  

# Copy everything from your local project to the container
COPY . .  

# Ensure the database folder exists
RUN mkdir -p /app/ReThink_AI_Chatbot/db

# Copy the dataset into the correct location
COPY db/Boston_Crime_Cleaned_v2.csv /app/ReThink_AI_Chatbot/db/Boston_Crime_Cleaned_v2.csv

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Run the application
CMD ["gunicorn", "-b", "0.0.0.0:8002", "app:app"]

