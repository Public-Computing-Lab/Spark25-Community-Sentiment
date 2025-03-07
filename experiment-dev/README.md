# RethinkAI

# 🔥 LLM Chatbot using Flask & Gemini API

This project is a **Flask-based chatbot** that interacts with **Google Gemini API** to provide intelligent responses. It processes user questions dynamically using a dataset stored in memory and allows users to provide feedback on responses.

## 📌 Features

- ✅ **Flask-based API** to interact with Google Gemini LLM.
- ✅ **Gemini API Integration** for generating responses.
- ✅ **Logging System** to track user queries and responses.
- ✅ **Feedback System** (👍 / 👎) to collect user feedback.

---

## 🚀 Getting Started

### **1️⃣ Clone the Repository**

```sh
git clone https://github.com/yourusername/llm-flask-chatbot.git
cd llm-flask-chatbot

```

### **2️⃣ Create & Activate a Virtual Environment**

```sh
python3 -m venv venv
source venv/bin/activate  # On Mac/Linux
venv\Scripts\activate     # On Windows
```

### **3️⃣ Install Dependencies**

pip install -r requirements.txt

### **4️⃣ Setup Environment Variables**

- Create a .env file in the project root

```sh
nano .env
```

- Add the following:

```sh
GEMINI_API_KEY=your_google_gemini_api_key
```
