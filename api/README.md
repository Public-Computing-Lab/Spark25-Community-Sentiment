# RethinkAI - API

This project is a **Flask-based REST-ish API** supporting the RethinkAI experiments.

##  Endpoints

### /data/zipzode \[ GET \]
---
#### **GET zipcode geoJson objects***
```
GET /data/zipcode?request=<zipcode>,<zipcode>,<zipcode>...
```
*Response*

geoJson object with zipcode boundaries

### /data/query \[ GET \]

---
#### **GET zipcode geoJson objects***
```
GET /data/query?request=<request_type>&options=<request_options>
```
request expects one of: 
- 911_shots_fired - return shots fired w/ location
- 911_shots_fired_confirmed - return count of confirmed shots fired by year with totals by quarter, and month
- 911_shots_fired_unconfirmed - return count of unconfirmed shots fired by year with totals by quarter, and month
- 911_homicides - return counts for homicides by year with totals by quarter, and month
- 911_homicides_and_shots_fired - return matches where a homicide and shot_fired occurred same date, same police district
- 311_geo - return locations of 311 data, by type option below
- 311_total - return total counts by year with quarter and month, by type option below
- 311_by_type - return counts for each type in type option below

All of the 311* requests require one option:

- living_conditions
- trash
- streets
- parking

*Response*

json object 

### /data/file \[ GET | POST \]
---
#### **GET a LIST of available files**
```
GET /data/file?request=list
```
*Response*
```
{
    "status": "success",
    "request_type": "LIST",
    "files": ["{data1.csv}", "{note1.txt}", "{data2.csv}"],
    "count": "{file_count}"
}
```

#### **GET CSV files**
```
GET /data/file?request=structured
```
*Response*
```
{
    "status": "success",
    "request_type": "CSV",
    "files": ["{data1.csv}", "{data2.csv}"],
    "contents": {
        "data1.csv": "content of data1...",
        "data2.csv": "content of data2..."
    },
    "count": "{file_count}"
}
```

#### **GET TXT files**
```
GET /data/file?request=unstructured
```
*Response*
```
{
    "status": "success",
    "request_type": "TXT",
    "files": ["{file1.txt}", "{file2.txt}"],
    "contents": {
        "file1.txt": "content of file1...",
        "file2.txt": "content of file2..."
    },
    "count": "{file_count}"
}
```
#### **GET all (CSV & TXT) files**
```
GET /data/file?request=all
```
*Response*
```
{
    "status": "success",
    "request_type": "ALL",
    "files": ["{file1.txt}", "{file2.csv}"],
    "contents": {
        "file1.txt": "content of file1...",
        "file2.csv": "content of file2..."
    },
    "count": "{file_count}"
}
```

#### **GET specific files**
Untested – works in theory.
```
GET /data/file?request=file1.csv,file2.txt
```
*Response*
```
{
    "status": "success",
    "request_type": "SPECIFIC",
    "files": ["{file1.csv}", "{file2.txt}"],
    "contents": {
        "file1.csv": "content of file1...",
        "file2.txt": "content of file2..."
    },
    "count": "{file_count}"
}
```

#### **POST files to datastore**
Incomplete
```
POST /data/file
```
*Json Data object*
```
{
 TBD
}
```

*Response*
```
{
    "status": "success",
    "saved_files": ["{file1.csv}", "{file2.txt}"],
    "count": "{file_count}"
}
```

### /chat \[ POST \]
---
#### **POST user question with prompt preamble for data context**
```
POST /chat?context_request={structured | unstructured | all | specific}
```
*Json Data object*
```
{
    app_version = "{app_version}"
    data_selected = ["{file1.csv}", "{file2.txt}"] #required for context_request=specific
    data_attributes = ["{attrib1}", "{attrib2}", "{attrib3}"] #optional
    client_query = "{User chat query}",
    prompt_preamble = "{Prompt preable} #required for context_request=specific"
}
```
*Response*
```
{
    "session_id": "{session_id}",		
    "response": "{llm_response}",
    "log_id": "{log_id}"
}
```


### /chat/context \[ POST \] 

#### **POST new context cache to LLM with files in datastore**
```
POST /chat/context?context_request={structured | unstructured | all | specific}
```
*Json Data object*
```
{
    app_version = "{app_version}"
    data_selected = "'{file1.csv}', '{file2.txt}'", # required for context_request=specific
    data_attributes = ["{attrib1}", "{attrib2}", "{attrib3}"], # optional
    prompt_preamble = "{Prompt preable} # required for context_request=specific"
}
```
*Response*
```
{
    "{cache_name}"
}
```

### /chat/context \[ GET \] 

#### **GET current context cache***
*Response*
```
{
    "{context_cache}"
}
```

### /chat/context \[ POST \] 

#### **POST clear all context cache***
*Response*
```
{
    "{'Success': 'Context cache cleared.'}"
}
```

### /log \[ POST \]
---
#### **POST chat log to logging database**
```
POST /log?log_action=insert
```
*Json Data object*
```
{
    "session_id": "{session_id}",		
    "app_version": "{experiment_versio}n",
    "data_selected": "'{file1.csv}', '{file2.txt}'",
    "data_attributes": ["{attrib1}", "{attrib2}", "{attrib3}"],
    "prompt_preamble": "{Prompt preamble}"
    "client_query": "{User chat query}",
    "client_response_rating": "{answered | unanswered}",
    "app_response": "{LLM response}"	
}
```
*Response*
```
{
    "log_id":"log_id"
}
```

#### **POST user_rating feedback update**
Update log entry based on user feedback.
```
POST /log?log_action=update_client_response_rating
```
*Json Data object*
```
{
    "log_id": "{log_id}",			
    "client_response_rating": "{answered | unanswered}"
}
```
*Response*
```
{
    "log_id":"{log_id}"
}
```


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
GEMINI_MODEL=<models/gemini-1.5-pro-{revision}>
API_PORT=<port>

# Database config
DB_HOST=<hostname>
DB_USER=<user_name>
DB_PASSWORD=<password>
DB_NAME=<db_name>

# Datastore
DATASTORE_PATH=<relative_path> #./datastore
PROMPTS_PATH=<relative_path> #./prompts
```

### Run WSGI Server

- Basic example with gunicorn, you may have/need other options depending on your environment
 
```sh
gunicorn --bind=<hostname>:<port> api:api
```