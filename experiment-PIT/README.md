# Experiment-PIT

This project is a collaboration between Rethink AI and the **Community Sentiment and Public Safety** initiative within the PIT-NE Impact Fellowship 2025. It includes a modern web app for exploring public safety data and interacting with a large language model (LLM) via chat.

## Overview

- **Frontend**: Vite + React + TypeScript (in `experiment-PIT/`)
- **Backend**: Flask API (in `api/`)
- **LLM**: Google Gemini (via `google-genai`)
- **Data Sources**: MySQL (911 and 311 data), GeoJSON (community assets), Mapbox vector tiles

The app now consists of two main pages:
- **Chat page** (default on load): Sends user prompts to the Gemini API and displays results.
- **Map page**: Displays public safety and community data via interactive mapping.

---

## Key Changes from Previous Version

- Removed "Tell me" / "Show me" entry split — now opens directly to the **chat interface**
- New frontend: built with **Vite + React + TypeScript**, housed in `experiment-PIT/`
- Updated Gemini model: `models/gemini-2.5-flash-preview-05-20`
- `.env` file now includes **VITE-prefixed variables** for frontend use
- Mobile-first web app development
- Retained Map and Chat functionalities with updated UI and in separate tabs
- **Backend changes:**
  - Custom MySQL queries added for access to data only in the Talbot-Norfolk Triangle
  - New API endpoint added for chat summarization using Gemini

---

## Data Sources

The project uses a mix of structured and geospatial public data:

### Community Assets
- Geocoded in a Jupyter notebook pipeline
- Converted into GeoJSON using [geojson.io](https://geojson.io/)
- Final output file: `map_2.geojson`

### 911 Call Data
- Loaded from a **MySQL database**
- Exported to a local GeoJSON format for use in the app
- Converted into a **Mapbox vector tileset**
- Tileset is used as a Mapbox URL to power one of the map layers

### Additional Public Datasets

Data for the dashboard are from public [BPD Crime Hub](https://boston-pd-crime-hub-boston.hub.arcgis.com/pages/data) and [BOS:311](https://data.boston.gov/dataset/311-service-requests):

1. [Arrests](https://boston-pd-crime-hub-boston.hub.arcgis.com/datasets/8cec12c8d60140aca2827eb45484f10b/explore)
2. [311 Data 2020](https://data.boston.gov/dataset/311-service-requests/resource/6ff6a6fd-3141-4440-a880-6f60a37fe789)
3. [311 Data 2021](https://data.boston.gov/dataset/311-service-requests/resource/f53ebccd-bc61-49f9-83db-625f209c95f5)
4. [311 Data 2022](https://data.boston.gov/dataset/311-service-requests/resource/81a7b022-f8fc-4da5-80e4-b160058ca207)
5. [311 Data 2023](https://data.boston.gov/dataset/311-service-requests/resource/e6013a93-1321-4f2a-bf91-8d8a02f1e62f)
6. [311 Data 2024](https://data.boston.gov/dataset/311-service-requests/resource/dff4d804-5031-443a-8409-8344efd0e5c8)

---

## Getting Started

### 1. Clone the Repository

```sh
git clone https://github.com/yourusername/experiment-pit.git
cd experiment-pit
```

### 2. Set Up the Backend (Flask API)

#### Create and Activate a Virtual Environment

```sh
python3 -m venv venv
source venv/bin/activate  # Mac/Linux
venv\Scripts\activate     # Windows
```

#### Install Python Dependencies

```sh
pip install -r requirements.txt
```

#### Create a `.env` File

```sh
nano .env
```

Add the following:

```ini
######################################
# API Keys
######################################
GEMINI_API_KEY=<your_gemini_key>
MAPBOX_TOKEN=<your_mapbox_token>
RETHINKAI_API_CLIENT_KEY=<your_rethinkai_key>

######################################
# Gemini Options
######################################
GEMINI_MODEL=models/gemini-2.5-flash-preview-05-20
GEMINI_CACHE_TTL=0.125

######################################
# Host
######################################
API_HOST=127.0.0.1
API_PORT=8888
API_BASE_URL=http://127.0.0.1:8888
DATASTORE_HOST=127.0.0.1

EXPERIMENT_7_DASH_REQUESTS_PATHNAME=/
EXPERIMENT_7_CACHE_DIR=./cache

######################################
# Vite Frontend Keys
######################################
VITE_GEMINI_API_KEY=<your_gemini_key>
VITE_MAPBOX_TOKEN=<your_mapbox_token>
VITE_RETHINKAI_API_KEYS=<your_rethinkai_keys>
VITE_RETHINKAI_API_CLIENT_KEY=<your_rethinkai_client_key>
VITE_BASE_URL=http://127.0.0.1:8888

############################
# Database Config
############################
DB_USER=<your username>
DB_PASSWORD=<your password>
DB_HOST=127.0.0.1
DB_NAME=rethink_ai_boston

```

#### Run the Backend Server

```sh
gunicorn --bind=127.0.0.1:8888 app:server
```

---

### 3. Set Up the Frontend (Vite)

```sh
cd experiment-PIT
npm install
npm run dev
```

This will start the Vite dev server at [http://localhost:5173](http://localhost:5173).

---

## Development Notes

* The frontend communicates with the backend via full URLs using `VITE_BASE_URL`, so no Vite proxy is needed.
* CORS is already enabled on the Flask backend.
* If deploying, update `.env` variables as needed and set appropriate static hosting and API routing.

---
