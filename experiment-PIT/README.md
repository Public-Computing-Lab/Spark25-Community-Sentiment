# Experiment-PIT

[This project](https://boston.ourcommunity.is/experimenting/8/) is a collaboration between Rethink AI and the **Community Sentiment and Public Safety** initiative within the PIT-NE Impact Fellowship 2025. It includes a modern mobile-first web app for exploring public safety data. This is accomplished through chat interaction with a large language model (LLM) and a dynamic neighborhood map that displays relevant data. 

The aim is to help the Talbot-Norfolk Triangle (TNT) community within Dorchester better understand and share their experiences with public safety by combining real community voices with official city data. By putting these sources of information in conversation, we hope to create a centralized hub of community and official knowledge that allows community members and local organizations to understand their neighborhood's challenges and strengths, ultimately using this information as a jumping-off point for action and advocacy.

For the SE/UX portion of this project, We have packaged data into an accessible and intuitive interface that will be used by community groups to represent their needs to the City of Boston. This interface builds on the existing `experiment-7` prototype that: 
- maps out crime and disorder patterns in the neighborhood based on 5 years of 311 data and police crime data 
- leverages an LLM to provide sentiment context to this structured data by using 3 years of community meeting transcripts

This version, `experiment-PIT`, builds on this prototype with new data sources, an accessible and appealing interface, and features that empower community members to go deeper into the available data.

Work on this project has been guided by [Talbot Norfolk Triangle Neighbors United](https://www.tbpm.org/community/tnt-neighbors-united/), a civic association of residents, local businesses, churches, schools, and non-profit partners working together to create a thriving community that is more eco-friendly, healthier, safer, connected, and economically-empowered. This org represents 26 blocks in Dorchester and hosts community meetings, which has been an integral part of this project’s data collection and dialogue with community stakeholders.


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
- Cleaned up in Google Sheets
- Geocoded in a Jupyter notebook pipeline
- Converted into GeoJSON using [geojson.io](https://geojson.io/)
- Final output file: `map_2.geojson` in `public/data/`

### 911 Call and 311 Request Data
- Loaded from a **MySQL database**
- Exported to a local GeoJSON format for use in the app
- Final output files: `process_911.tsx` and `process_311.tsx` in `public/data/`

### Budget Data
- Downloaded from the [City of Boston Capital Plan (FY26–30)](https://data.boston.gov/organization/office-of-budget-management)
- Filtered to include Dorchester, Citywide, and Multi-Neighborhood projects only
- Converted from `.csv` to `.txt` for prompt compatibility
- Includes:
  - `budget_filtered.txt`: Cleaned capital projects data
  - `budget_data_dictionary_v1.txt`: Definitions for project fields (Department, Scope, Budget, etc.)
- Used by the chat box to answer questions about city investments.

### Policy Data
- Sourced from public city policy documents
  - [Anti-Displacement Action Plan](https://www.boston.gov/departments/planning-advisory-council/anti-displacement-action-plan) 
  - [Imagine Boston 2030 City Master Plan](https://www.boston.gov/civic-engagement/imagine-boston-2030)
  - [Neighborhood Slow Streets Program](https://www.boston.gov/departments/transportation/neighborhood-slow-streets)
- The content of these plans has been distilled into 3 policy summaries using Gemini's deep research tool
  - `Boston Anti-Displacement Plan Analysis.txt`
  - `Imagine Boston 2030 Analysis.txt`
  - `Boston Slow Streets Plan Analysis.txt`
- Gemini primarily sourced data for these summaries from the city policy documents and some supplemental info from other online sources, all of which are cited in the summaries.
- Each summary includes a particular focus on the connection of each policy to both Dorchester and the TNT neighborhood.
- Used by the model to answer questions about city plans, specific initiatives, and various processes affecting the TNT neighborhood.

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
