# Import necessary modules
from flask import Flask, request, jsonify, render_template
import os
import pandas as pd
import google.generativeai as genai
import asyncio
import matplotlib.pyplot as plt
import seaborn as sns
import io
import base64
import json
from datetime import datetime
import uuid
from dotenv import load_dotenv
import re 
import matplotlib
matplotlib.use('Agg')  # Use a non-interactive backend to avoid GUI errors


APP_VERSION = "0.02"

# ✅ Load environment variables
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
PORT = os.getenv("EXPERIMENT_2_PORT")

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

# ✅ Determine dataset path
file_path = os.path.join(os.getcwd(), "db", "Boston_Crime_Cleaned_v2.csv")  
df = load_csv(file_path, max_rows=1000)

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
def get_gemini_response(prompt):
    """Sends the prompt to Google Gemini and returns the response."""
    try:
        model = genai.GenerativeModel("gemini-1.5-pro")
        response = model.generate_content(prompt)  # ✅ No `await`
        
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

def get_gemini_visualization_prompt(query, df):
    """Asks Gemini how to visualize the given query using only valid dataset columns and chart types."""

    # ✅ Get available column names dynamically
    available_columns = df.columns.str.strip().tolist()  # Strip spaces to avoid mismatches
    column_info = ", ".join(available_columns)

    # ✅ Define valid chart types (must match what is implemented in /visualize)
    valid_chart_types = [
        "bar", "line", "histogram", "scatter", "heatmap"
    ]
    chart_types_str = ", ".join(valid_chart_types)

    dataset_summary = f"""
    The dataset has {df.shape[0]} rows and {df.shape[1]} columns.
    **Available Columns:** {column_info}
    **Data Types:** {df.dtypes.to_dict()}

    **Important:**
    - **Only use column names from the provided list. Do not make up column names.**
    - **Choose only from these valid chart types:** {chart_types_str}
    - **If aggregation is required, apply `.value_counts()` or `.count()` to categorical variables.**
    - **Ensure JSON output follows the format below.**
    """

    prompt = f"""
    You are a data visualization assistant. A user has asked to visualize data with the following request:
    "{query}"

    Based on the dataset provided below, suggest the most appropriate visualization.

    Your response **must** be in the following JSON format:
    ```json
    {{
        "plot_type": "bar",
        "x": "ValidColumnName",
        "y": "ValidColumnName",
        "aggregation": "count",
        "reasoning": "A bar chart is best for comparing categorical data such as different crime types."
    }}
    ```

    - **Only use column names from this list:** {available_columns}
    - **Only suggest these visualization types:** {valid_chart_types}
    - **If counting occurrences of a category, use `.value_counts()` on `Incident_ID` or categorical columns.**
    
    {dataset_summary}
    """

    try:
        model = genai.GenerativeModel("gemini-1.5-pro")
        response = model.generate_content(prompt)

        # ✅ Log response for debugging
        print(f"✅ Gemini Visualization Response:\n{response.text}")

        return response.text
    except Exception as e:
        print(f"❌ Error generating visualization suggestion: {e}")
        return None




# ✅ Chatbot Endpoint
@app.route("/ask", methods=["POST"])
def ask():
    """Handles user questions and sends them to the LLM."""
    try:
        data = request.get_json()
        user_question = data.get("question", "").strip()

        if not user_question:
            return jsonify({"error": "No question provided"}), 400

        dataset_prompt = generate_initial_prompt(df)
        full_prompt = f"{dataset_prompt}\n\nUser question: {user_question}"

        response = get_gemini_response(full_prompt)

        if "429" in response or "quota" in response.lower():
            print("❌ Gemini API Quota Exceeded")
            return jsonify({"error": "Our AI quota has been exceeded. Please try again later."}), 503

        print(f"✅ Gemini Response: {response}")

        query_id = log_query(user_question, response)

        return jsonify({"answer": response, "query_id": query_id})

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"❌ Internal Server Error: {str(e)}")
        return jsonify({"error": f"Internal server error: {str(e)}"}), 500


# ✅ Crime Statistics Calculation
@app.route("/crime-stats", methods=["GET"])
def crime_stats():
    """Dynamically calculates key crime insights."""
    try:
        if df is None:
            return jsonify({"error": "Dataset not loaded"}), 500

        # ✅ Verify correct column names
        crime_col = "OFFENSE_CODE_GROUP" if "OFFENSE_CODE_GROUP" in df.columns else "Crime"
        hour_col = "HOUR" if "HOUR" in df.columns else "Hour"
        neighborhood_col = "DISTRICT" if "DISTRICT" in df.columns else "Neighborhood"

        if crime_col not in df.columns or hour_col not in df.columns or neighborhood_col not in df.columns:
            print(f"❌ Column mismatch! Available columns: {df.columns.tolist()}")
            return jsonify({"error": "Dataset format is incorrect. Columns missing."}), 500

        # ✅ Compute insights
        most_common_crime = df[crime_col].mode()[0] if crime_col in df.columns else "Unknown"
        peak_hour = df[hour_col].mode()[0] if hour_col in df.columns else "Unknown"
        most_affected_area = df[neighborhood_col].mode()[0] if neighborhood_col in df.columns else "Unknown"

        print(f"✅ Crime Stats: {most_common_crime}, {peak_hour}, {most_affected_area}")

        return jsonify({
            "most_common_crime": most_common_crime,
            "peak_hour": f"{peak_hour}:00 - {peak_hour+1}:00" if isinstance(peak_hour, int) else peak_hour,
            "most_affected_area": most_affected_area
        })

    except Exception as e:
        print(f"❌ Error in /crime-stats: {e}")
        return jsonify({"error": f"Failed to retrieve crime stats: {e}"}), 500


# ✅ Feedback Collection
@app.route("/feedback", methods=["POST"])
def feedback():
    return jsonify({"message": "Feedback endpoint working"})

@app.route("/", methods=["GET"])
def home():
    return render_template("index.html")

@app.route("/visualize", methods=["POST"])
def visualize():
    """Generates a visualization dynamically based on user query using Gemini's suggestions."""
    try:
        data = request.get_json()
        query = data.get("query", "").strip()

        if not query:
            return jsonify({"error": "No query provided"}), 400

        print(f"🔍 Generating visualization for query: {query}")

        # ✅ Ensure column names are clean
        df.columns = df.columns.str.strip()

        # ✅ Print column names for debugging
        print(f"🔍 Available Columns in Dataset: {df.columns.tolist()}")

        gemini_response = get_gemini_visualization_prompt(query, df)

        if not gemini_response:
            return jsonify({"error": "Failed to interpret visualization request"}), 500

        try:
            cleaned_response = re.sub(r"```(?:json)?\n?|```", "", gemini_response).strip()
            viz_instructions = json.loads(cleaned_response)
        except json.JSONDecodeError:
            print("❌ Failed to parse AI response:", cleaned_response)
            return jsonify({"error": "Failed to parse AI response"}), 500

        # Normalize AI's column selection to match actual dataset columns safely
        plot_type = viz_instructions.get("plot_type", "").lower().replace(" chart", "")
        x_col = viz_instructions.get("x") or ""
        y_col = viz_instructions.get("y") or ""
        aggregation = viz_instructions.get("aggregation", "").lower()
        reasoning = viz_instructions.get("reasoning", "")

        print(f"📊 AI Suggested Plot: {plot_type}, X: {x_col}, Y: {y_col}, Aggregation: {aggregation}")
        print(f"💡 Reasoning: {reasoning}")

        # Handle NoneType safely by providing a default empty string before applying .lower()
        x_col = next((col for col in df.columns if col.lower() == x_col.lower()), x_col) if x_col else ""
        y_col = next((col for col in df.columns if col.lower() == y_col.lower()), y_col) if y_col else ""

        print(f"✅ Mapped Columns: X → {x_col}, Y → {y_col}")

        # Check if x_col is still empty or invalid
        if not x_col or x_col not in df.columns:
            return jsonify({"error": f"Invalid or missing column for X-axis: '{x_col}'"}), 400
        if y_col and y_col not in df.columns:
            return jsonify({"error": f"Invalid or missing column for Y-axis: '{y_col}'"}), 400


        plt.figure(figsize=(8, 5))

        # ✅ Handle Aggregation Properly
        if aggregation == "count":
            print(f"🔄 Applying Count Aggregation for: {x_col}")
            data = df[x_col].value_counts().reset_index()
            data.columns = [x_col, "Count"]  # ✅ Use actual column name instead of "Category"
            x_col, y_col = x_col, "Count"

            # ✅ Convert to datetime if applicable
            if "date" in x_col.lower():
                data[x_col] = pd.to_datetime(data[x_col], errors='coerce')

            print(f"✅ Processed Data for Plotting:\n{data.head()}")

        if plot_type == "bar":
            sns.barplot(data=data, x=x_col, y=y_col, palette="coolwarm")
            plt.xticks(rotation=45, ha='right')
            plt.tight_layout()
            plt.title(f"Bar Chart: {x_col} vs {y_col}")

        elif plot_type == "line" and y_col:
            sns.lineplot(data=data, x=x_col, y=y_col)
            plt.title(f"Line Chart: {x_col} vs {y_col}")

        elif plot_type == "histogram":
            sns.histplot(df[x_col], bins=20, kde=True, color="blue")
            plt.xticks(rotation=45, ha='right')
            plt.tight_layout()
            plt.title(f"Histogram: {x_col}")

        elif plot_type == "scatter" and y_col:
            sns.scatterplot(data=df, x=x_col, y=y_col, alpha=0.7)
            plt.title(f"Scatter Plot: {x_col} vs {y_col}")

        elif plot_type == "heatmap":
            plt.figure(figsize=(10, 6))
            sns.heatmap(df.corr(), annot=True, cmap="coolwarm", fmt=".2f")
            plt.title("Heatmap of Correlations")

        else:
            return jsonify({"error": f"Plot type '{plot_type}' is not supported yet"}), 400

        img_io = io.BytesIO()
        plt.savefig(img_io, format="png")
        plt.close()
        img_io.seek(0)
        img_base64 = base64.b64encode(img_io.getvalue()).decode()

        return jsonify({
            "image": img_base64,
            "reasoning": reasoning
        })

    except Exception as e:
        print(f"❌ Error generating visualization: {e}")
        return jsonify({"error": f"Failed to generate visualization: {e}"}), 500





from app import app  # Make sure 'app' is correctly referenced for Vercel



