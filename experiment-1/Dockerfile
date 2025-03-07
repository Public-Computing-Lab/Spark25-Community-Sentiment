# ✅ Use the official Python slim image
FROM python:3.11-slim

# ✅ Set working directory inside the container
WORKDIR /app/ReThink_AI_Chatbot

# ✅ Copy everything from the current directory to the container
COPY . .

# ✅ Ensure the database folder exists
RUN mkdir -p /app/ReThink_AI_Chatbot/db

# ✅ Explicitly copy the CSV file
COPY db/Boston_Crime_Cleaned_v2.csv /app/ReThink_AI_Chatbot/db/Boston_Crime_Cleaned_v2.csv

# ✅ Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# ✅ Expose the correct port (Fly.io expects 8080)
EXPOSE 8080

# ✅ Start the Flask app
CMD ["gunicorn", "-b", "0.0.0.0:8080", "app:app"]
