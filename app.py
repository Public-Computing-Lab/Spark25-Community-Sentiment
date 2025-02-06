# raw dataset is being send to the gemini model directly. Long processing time upto 1 minute for
# each question being asked
from flask import Flask, request, jsonify, render_template
import os
import pandas as pd
import google.generativeai as genai
import asyncio
from datetime import datetime
import uuid
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")  
genai.configure(api_key=GEMINI_API_KEY)

app = Flask(__name__, template_folder="templates")

LOG_FILE = "llm_query_log.csv"

def load_csv(file_path, max_rows=1000):
    """Loads a CSV file and limits rows to fit within Gemini's token limit.Initially I processed the whole file
    of 250k rows and processed them parallely which led to quota limit exceeding and rate limit exceeding."""
    try:
        df = pd.read_csv(file_path)
        df = df.head(max_rows)  
        print(f"\n✅ Loaded {len(df)} rows (limited to avoid quota issues).")
        return df
    except Exception as e:
        print(f"❌ Error loading CSV: {e}")
        return None

def generate_initial_prompt(df):
    """Converts the dataset into a format suitable for a one-time Gemini input."""
    dataset_text = df.to_string(index=False)
    
    dataset_prompt = f"""
    You are a data analysis assistant. Below is a dataset containing {df.shape[0]} rows and {df.shape[1]} columns.

    **Dataset Columns:** {', '.join(df.columns)}

    **Dataset Preview:**
    {dataset_text}

    This dataset will be used for answering multiple questions.
    When asked a question related to dataset just explain your findings and don't give the code to be used on the dataset.
      Please store this data in memory and answer all future questions based on it.
    """
    
    return dataset_prompt

async def get_gemini_response(prompt, chat_session):
    """Sends the prompt to Google Gemini and returns the response."""
    try:
        model = genai.GenerativeModel("gemini-1.5-pro")
        response = await asyncio.to_thread(chat_session.send_message, prompt)
        return response.text
    except Exception as e:
        return f"❌ Error generating response: {e}"
    
def log_query(question, answer):
    """Logs the question, answer, timestamp, and assigns a unique query ID for feedback tracking."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    query_id = str(uuid.uuid4())[:8]  # Unique short ID for each question

    log_entry = pd.DataFrame([{
        "Query_ID": query_id,
        "Timestamp": timestamp,
        "Question": question,
        "Answer": answer,
        "Feedback": ""  # Placeholder for feedback
    }])

    if not os.path.exists(LOG_FILE):
        log_entry.to_csv(LOG_FILE, index=False)
    else:
        log_entry.to_csv(LOG_FILE, mode='a', header=False, index=False)

    return query_id 

@app.route("/")
def home():
    """Serves the chatbot frontend."""
    return render_template("index.html")

@app.route("/ask", methods=["POST"])
def ask():
    """Handles user questions and sends them to the LLM."""
    data = request.get_json()
    user_question = data.get("question", "")

    if not user_question:
        return jsonify({"error": "No question provided"}), 400

    prompt = f"Based on the dataset I provided earlier, answer this: {user_question}"
    response = asyncio.run(get_gemini_response(prompt, chat_session))

    # ✅ Generate a `query_id` and log it
    query_id = log_query(user_question, response)

    return jsonify({"answer": response, "query_id": query_id})

@app.route("/crime-stats", methods=["GET"])
def crime_stats():
    """Dynamically calculates key crime insights."""
    most_common_crime = df["Crime"].mode()[0]  # Most frequent crime
    peak_hour = df["Hour"].mode()[0]  # Most frequent crime hour
    most_affected_area = df["Neighborhood"].mode()[0]  # Most crime-heavy neighborhood

    return jsonify({
        "most_common_crime": most_common_crime,
        "peak_hour": f"{peak_hour}:00 - {peak_hour+1}:00",
        "most_affected_area": most_affected_area
    })

@app.route("/feedback", methods=["POST"])
def feedback():
    """Stores user feedback in the log file using Query_ID to prevent overwriting."""
    data = request.get_json()
    query_id = data.get("query_id", "")
    feedback = data.get("feedback", "")

    if not query_id or not feedback:
        return jsonify({"error": "Invalid feedback"}), 400

    # ✅ Check if the log file exists, if not, return an error.
    if not os.path.exists(LOG_FILE):
        return jsonify({"error": "Log file not found"}), 500

    # ✅ Read the CSV safely, handling errors
    try:
        log_df = pd.read_csv(LOG_FILE, dtype=str, encoding="utf-8", on_bad_lines="skip")
    except pd.errors.ParserError:
        return jsonify({"error": "CSV file corrupted, please check formatting"}), 500

    # ✅ Ensure "Query_ID" column exists
    if "Query_ID" not in log_df.columns:
        return jsonify({"error": "Query_ID column missing in CSV"}), 500

    # ✅ Check if Query_ID exists in the log
    if query_id not in log_df["Query_ID"].values:
        return jsonify({"error": "Query ID not found"}), 400

    # ✅ Update feedback for the matching Query_ID
    log_df.loc[log_df["Query_ID"] == query_id, "Feedback"] = feedback

    # ✅ Save updated log file
    log_df.to_csv(LOG_FILE, index=False)

    return jsonify({"success": "Feedback recorded"})




if __name__ == "__main__":
    file_path = 'Boston_Crime_Cleaned_v2.csv'
    df = load_csv(file_path, max_rows=1000)  

    if df is not None:
        print("\n✅ Sending dataset to Gemini... (one-time cost)")
        
        # **Step 1: Load dataset once and store it in Gemini's session**
        dataset_prompt = generate_initial_prompt(df)
        model = genai.GenerativeModel("gemini-1.5-pro")
        chat_session = model.start_chat(history=[])  # Stores the dataset in session memory

        print("\n🔄 Sending dataset to Gemini (One-time process)...")
        asyncio.run(get_gemini_response(dataset_prompt, chat_session))
        
        print("\n✅ Dataset is now loaded. You can ask unlimited questions without reloading the dataset!")

        app.run(debug=True)

        print("\n💬 Ask questions about the dataset. Type 'exit' to quit.")
        while True:
            user_question = input("\n💬 Enter your question: ")
            if user_question.lower() in ['exit', 'quit']:
                print("👋 Exiting... Have a great day!")
                break
            
            # **Step 2: Send only the question, not the dataset**
            prompt = f"Based on the dataset I provided earlier, answer this: {user_question}"
            response = asyncio.run(get_gemini_response(prompt, chat_session))
            log_query(user_question, response)
            print("\n🤖 **AI Response:**\n", response)