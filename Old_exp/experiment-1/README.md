# RethinkAI - Experiment 1

## LLM Chatbot using Flask & Gemini API

This project is a **Flask-based chatbot** that interacts with **Google Gemini API** to provide intelligent responses. It processes user questions dynamically using a dataset stored in memory and allows users to provide feedback on responses.

###  Features

- **Flask-based API** to interact with Google Gemini LLM.
- **Gemini API Integration** for generating responses.
- **Logging System** to track user queries and responses.
- **Feedback System** (👍 / 👎) to collect user feedback.

### Data

Data for the dashboard are from public [BPD Crime Hub](https://boston-pd-crime-hub-boston.hub.arcgis.com/pages/data):  

1. [Offenses](https://boston-pd-crime-hub-boston.hub.arcgis.com/datasets/d42bd4040bca419a824ae5062488aced/explore)  

---

## Getting Started

### Clone the Repository

```sh
git clone https://github.com/yourusername/RethinkAI.git
cd RethinkAI/experiment-1/

```

### Create & Activate a Virtual Environment

```sh
python3 -m venv venv
source venv/bin/activate  # On Mac/Linux
venv\Scripts\activate     # On Windows
```

### Install Dependencies

```sh
pip3 install -r requirements.txt
```

### Setup Environment Variables

- Create a .env file in the project root

```sh
nano .env
```

- Add the following:

```sh
GEMINI_API_KEY=<google_gemini_api_key>

EXPERIMENT_1_PORT=<port>
```

### Run WSGI Server

- Basic example with gunicorn, you may have/need other options depending on your environment
 
```sh
gunicorn --bind=<hostname>:<port> app:app
```