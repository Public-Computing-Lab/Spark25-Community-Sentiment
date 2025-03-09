# RethinkAI - API

## REST-like API

This project is a **Flask-based REST-like API** supporting the RethinkAI experiments.

###  Endpoints

**/data**

GET: Returns all stored data
POST: Stores new data with a UUID

**/chat**

POST: Accepts query string parameter 'prompt'
Returns LLM response
'Prompt' specifies pre-generated prompts to aid context

**/chat/context** endpoint:**

POST: Accepts context in request body
Updates the LLM content-cache, does not return a response

**/log**

POST: Stores interaction logs in SQL database
Validates fields
Includes timestamp automatically

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

API_PORT=<port>
```

### Run WSGI Server

- Basic example with gunicorn, you may have/need other options depending on your environment
 
```sh
gunicorn --bind=<hostname>:<port> api:api
```