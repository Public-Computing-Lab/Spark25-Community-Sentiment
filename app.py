# raw dataset is being sent to the Gemini model directly.
from flask import Flask, request, jsonify, render_template
import os
import pandas as pd
import google.generativeai as genai
import asyncio
from datetime import datetime
import uuid
from dotenv import load_dotenv

APP_VERSION = "0.01"

# ✅ Load environment variables
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=GEMINI_API_KEY)

app = Flask(__name__, template_folder="templates")

LOG_FILE = "llm_query_log.csv"

# ✅ Load CSV function
def load_csv(file_path, max_rows=1000):
    """Loads a CSV file and limits rows to fit within Gemini's token limit."""
    try:
        df = pd.read_csv(file_path)
        df = df.head(max_rows)
        print(f"\n✅ Loaded {len(df)} rows (limited to avoid quota issues).")
        return df
    except Exception as e:
        print(f"❌ Error loading CSV: {e}")
        return None

# ✅ Determine dataset path (works for local & server)
if os.path.exists("/app/ReThink_AI_Chatbot/db/Boston_Crime_Cleaned_v2.csv"):  # ✅ Adjust for Fly.io
    file_path = "/app/ReThink_AI_Chatbot/db/Boston_Crime_Cleaned_v2.csv"
else:
    file_path = os.path.join(os.getcwd(), "db", "Boston_Crime_Cleaned_v2.csv")  # ✅ Local fallback



df = load_csv(file_path, max_rows=1000)  # ✅ Load dataset globally

# ✅ Generate dataset prompt function
def generate_initial_prompt(df):
    """Converts the dataset into a format suitable for Gemini input."""
    dataset_text = df.to_string(index=False)

    dataset_prompt = f"""
    You are a data analysis assistant. Below is a dataset containing {df.shape[0]} rows and {df.shape[1]} columns.

    **Dataset Columns:** {', '.join(df.columns)}

    **Dataset Preview:**
    {dataset_text}

    This dataset will be used for answering multiple questions.
    When asked a question related to the dataset, just explain your findings and don't give the code to be used on the dataset.
    Please answer based on this dataset.
    """

    return dataset_prompt

# ✅ Send prompt to Gemini
async def get_gemini_response(prompt):
    """Sends the prompt to Google Gemini and returns the response."""
    try:
        model = genai.GenerativeModel("gemini-1.5-pro")
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, lambda: model.generate_content(prompt))
        
        print(f"\n✅ Gemini Response: {response.text}")  # ✅ Log the response!
        
        return response.text
    except Exception as e:
        print(f"❌ Error generating response: {e}")  # ✅ Log the error!
        return f"❌ Error generating response: {e}"


# ✅ Log query function
def log_query(question, answer):
    """Logs the question, answer, timestamp, and assigns a unique query ID."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    query_id = str(uuid.uuid4())[:8]  # Unique short ID for each question

    log_entry = pd.DataFrame([{
        "Query_ID": query_id,
        "Timestamp": timestamp,
        "Question": question,
        "Answer": answer,
        "Feedback": ""
    }])

    if not os.path.exists(LOG_FILE):
        log_entry.to_csv(LOG_FILE, index=False)
    else:
        log_entry.to_csv(LOG_FILE, mode='a', header=False, index=False)

    return query_id 

# ✅ Flask Routes
@app.route("/")
def home():
    """Serves the chatbot frontend with version info."""
    return render_template("index.html", version=APP_VERSION)

@app.route("/ask", methods=["POST"])
def ask():
    """Handles user questions and sends them to the LLM."""
    try:
        data = request.get_json()
        user_question = data.get("question", "")

        if not user_question:
            return jsonify({"error": "No question provided"}), 400

        print(f"🔄 Processing user question: {user_question}")

        # ✅ Use dataset in the prompt
        dataset_prompt = generate_initial_prompt(df)
        full_prompt = f"{dataset_prompt}\n\nUser question: {user_question}"

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        response = loop.run_until_complete(get_gemini_response(full_prompt))

        if "❌ Error" in response:
            print(f"❌ ERROR from Gemini API: {response}")
            return jsonify({"error": response}), 500

        query_id = log_query(user_question, response)
        return jsonify({"answer": response, "query_id": query_id})

    except Exception as e:
        print(f"❌ Exception in /ask: {e}")
        return jsonify({"error": f"Internal server error: {e}"}), 500

@app.route("/crime-stats", methods=["GET"])
def crime_stats():
    """Dynamically calculates key crime insights."""
    if df is None:
        return jsonify({"error": "Dataset not loaded"}), 500

    most_common_crime = df["Crime"].mode()[0] if "Crime" in df.columns else "N/A"
    peak_hour = df["Hour"].mode()[0] if "Hour" in df.columns else "N/A"
    most_affected_area = df["Neighborhood"].mode()[0] if "Neighborhood" in df.columns else "N/A"

    return jsonify({
        "most_common_crime": most_common_crime,
        "peak_hour": f"{peak_hour}:00 - {peak_hour+1}:00" if isinstance(peak_hour, int) else "N/A",
        "most_affected_area": most_affected_area
    })

@app.route("/feedback", methods=["POST"])
def feedback():
    """Stores user feedback in the log file using Query_ID."""
    data = request.get_json()
    query_id = data.get("query_id", "")
    feedback = data.get("feedback", "")

    if not query_id or not feedback:
        return jsonify({"error": "Invalid feedback"}), 400

    if not os.path.exists(LOG_FILE):
        return jsonify({"error": "Log file not found"}), 500

    try:
        log_df = pd.read_csv(LOG_FILE, dtype=str, encoding="utf-8", on_bad_lines="skip")
    except pd.errors.ParserError:
        return jsonify({"error": "CSV file corrupted, please check formatting"}), 500

    if "Query_ID" not in log_df.columns or query_id not in log_df["Query_ID"].values:
        return jsonify({"error": "Query ID not found"}), 400

    log_df.loc[log_df["Query_ID"] == query_id, "Feedback"] = feedback
    log_df.to_csv(LOG_FILE, index=False)
    return jsonify({"success": "Feedback recorded"})

# ✅ Run Flask App (Supports Local & Server Deployment)
def start_app():
    """Starts the Flask application (for local & server)."""
    print("\n🚀 Server is running on 0.0.0.0:8080")  # ✅ Fixed!
    app.run(host="0.0.0.0", port=8080)

if __name__ == "__main__":
    start_app()
