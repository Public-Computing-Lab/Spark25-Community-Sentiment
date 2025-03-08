# RethinkAI - Experiment 3

## Plotly Dash & LLM Chat interface

This experiment uses the Plotly Dash framework to present a public safety dashboard using data from the BPD Data Hub [https://boston-pd-crime-hub-boston.hub.arcgis.com/pages/data].

The interface includes an LLM chat window for interacting with transcripts from community meeting in the Dorchester Neighborhood where residents discussed public safety.

# RethinkAI - Experiment 3

## Plotly Dash Data Dashboard & LLM Chatbot using Flask & Gemini API

This project is a **Flask-based chatbot** that interacts with **Google Gemini API** to provide intelligent responses. It processes user questions dynamically using a dataset stored in memory and allows users to provide feedback on responses.

###  Features

- **Flask-based API** to interact with Google Gemini LLM.
- **Gemini API Integration** for generating responses.
- **Data Dashboard** from BPD Data Hub datasets
- **LLM Chatbot** to query public safety sentiment using community meeting transcripts as context

---

## Getting Started

### Clone the Repository

```sh
git clone https://github.com/yourusername/RethinkAI.git
cd RethinkAI/experiment-3/

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

EXPERIMENT_3_PORT=<port>
EXPERIMENT_3_DASH_REQUESTS_PATHNAME=/ #URL path for 
```

### Run WSGI Server

- Basic example with gunicorn, you may have/need other options depending on your environment
 
```sh
gunicorn --bind=<hostname>:<port> app3:server
```