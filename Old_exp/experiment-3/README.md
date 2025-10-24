# RethinkAI - Experiment 3

## Plotly Dash Data Dashboard & LLM Chatbot using Flask & Gemini API

This project is a **Flask-based chatbot** that interacts with **Google Gemini API** to provide intelligent responses. It processes user questions dynamically using a dataset stored in memory and allows users to provide feedback on responses.

### Features

- **Flask-based API** to interact with Google Gemini LLM.
- **Gemini API Integration** for generating responses.
- **Data Dashboard** from BPD Data Hub datasets
- **LLM Chatbot** to query public safety sentiment using community meeting transcripts as context

### Data

Data for the dashboard are from public [BPD Crime Hub](https://boston-pd-crime-hub-boston.hub.arcgis.com/pages/data) and include:

1. [Arrests](https://boston-pd-crime-hub-boston.hub.arcgis.com/datasets/8cec12c8d60140aca2827eb45484f10b/explore)  
2. [Firearm Recovery](https://data.boston.gov/dataset/boston-police-department-firearm-recovery-counts)  
3. [Homicides](https://boston-pd-crime-hub-boston.hub.arcgis.com/datasets/8ebdeffa072145398be37f21f8bdef77/explore)  
4. [Offenses](https://boston-pd-crime-hub-boston.hub.arcgis.com/datasets/d42bd4040bca419a824ae5062488aced/explore)  
5. [Shootings](https://boston.hub.arcgis.com/datasets/119c38686dac4c24bfcd8a3b099623f5/explore)  
6. [Shots Fired](https://boston.hub.arcgis.com/datasets/dd3a722ccc964876b0c6f426541d704d/explore)  

Transcripts from community meeting discussing public safety and community priorities provides data context for the LLM chat interaction.

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