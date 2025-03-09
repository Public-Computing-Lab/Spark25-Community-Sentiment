# RethinkAI - API

## REST-like API

This project is a **Flask-based REST-like API** supporting the RethinkAI experiments.

###  Endpoints

**/data**

GET: Returns all stored data
POST: Stores new data with a UUID

**/chat**

POST: Accepts query string parameter 'prompt'
prompt=structured for structured data prompt preamble
prompt=unstructured for unstructured data prompt preamble
Returns LLM response


**/chat/context** endpoint:**

POST: Accepts context in request body
Updates the LLM content-cache

**/log**

POST: Accepts query string parameter 'log_action'
log_action=insert creates new log entry
log_action=update_feedback updates the feedback field of existing entry w/ session_id and timestamp

---

## Getting Started

### Clone the Repository

```sh
git clone https://github.com/yourusername/RethinkAI.git
cd RethinkAI/api

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

API_PORT=<port>
```

### Run WSGI Server

- Basic example with gunicorn, you may have/need other options depending on your environment
 
```sh
gunicorn --bind=<hostname>:<port> api:api
```