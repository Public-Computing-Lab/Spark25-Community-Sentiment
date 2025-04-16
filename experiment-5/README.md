# RethinkAI - Experiment 5

## Plotly Dash Data Dashboard & LLM Chatbot using Flask & Gemini API

This project is a **Flask-based chatbot** that interacts with **Google Gemini API** to provide intelligent responses. It processes user questions dynamically using a dataset stored in memory and allows users to provide feedback on responses.

### Requires

Requires RethinkAI/api.

###  Features

- **Data Dashboard** from BPD Data Hub, and Boston 311 datasets

### Data

Data for the dashboard are from public [BPD Crime Hub](https://boston-pd-crime-hub-boston.hub.arcgis.com/pages/data) and [BOS:311](https://data.boston.gov/dataset/311-service-requests):

1. [Arrests](https://boston-pd-crime-hub-boston.hub.arcgis.com/datasets/8cec12c8d60140aca2827eb45484f10b/explore)
2. [311 Data 2020](https://data.boston.gov/dataset/311-service-requests/resource/6ff6a6fd-3141-4440-a880-6f60a37fe789)
3. [311 Data 2021](https://data.boston.gov/dataset/311-service-requests/resource/f53ebccd-bc61-49f9-83db-625f209c95f5)
4. [311 Data 2022](https://data.boston.gov/dataset/311-service-requests/resource/81a7b022-f8fc-4da5-80e4-b160058ca207)
5. [311 Data 2023](https://data.boston.gov/dataset/311-service-requests/resource/e6013a93-1321-4f2a-bf91-8d8a02f1e62f)
6. [311 Data 2024](https://data.boston.gov/dataset/311-service-requests/resource/dff4d804-5031-443a-8409-8344efd0e5c8)

---

## Getting Started

### Clone the Repository

```sh
git clone https://github.com/yourusername/RethinkAI.git
cd RethinkAI/experiment-5/
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
EXPERIMENT_5_PORT=<port>
EXPERIMENT_5_DASH_REQUESTS_PATHNAME=/
EXPERIMENT_5_VERSION=<0.5.x>
API_BASE_URL=<Rethink API url>
CACHE_DIR=<path to pyarrow cache files>
```

### Run WSGI Server

- Basic example with gunicorn, you may have/need other options depending on your environment
 
```sh
gunicorn --bind=<hostname>:<port> app:server
```
