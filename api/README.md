# RethinkAI - API

This project is a **Flask-based REST-ish API** supporting the RethinkAI experiments.

##  Endpoints

#### **GET crime and 311 data as geoJson objects***
```
GET /data/query?app_version=<0.0>&request=<request_type>&date=%Y-%m&zipcode=<zipcode>
```
```<request_type>``` is one of: 
##### Crime Data
- **911_shots_fired** - return shots fired w/ location
- **911_shots_fired_count_confirmed** - return count of confirmed shots fired by year with totals by quarter, and month
- **911_shots_fired_count_unconfirmed** - return count of unconfirmed shots fired by year with totals by quarter, and month
- **911_homicides** - return counts for homicides by year with totals by quarter, and month
- **911_homicides_and_shots_fired** - return matches where a homicide and shot_fired occurred same date, same police district

##### 311 Data
> 311_by\* requires ?category={living_conditions | trash | streets | parking}  
> 311_on\* requires ?date=%Y-%m  
> 311_on_date_count optionally takes &zipcode=\<zipcode\> to filter by zip (for hover chart)  
- **311_by_geo** - return locations of 311 data, by type option below
- **311_by_total** - return total counts by year with quarter and month, by type option below
- **311_by_type** - return counts for each type in type option below
- **311_year_month** - return all 311 dates in %Y-%m format
- **311_on_date_count** - return category counts by date, 
- **311_on_date_geo** - returns all lat/longs for 311 categories by date, requires '&date=%Y-%m'

##### Other
- **zip_geo** - returns geojson object for requested zipcodes, requires &zipcode=\<zipcode,zipcode,...\>

*Response*

{json object}


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
---
#### **POST create new context cache**
```
POST /chat/context?request=<context_request>
```
*Json Data object*
```
{
    app_version = "{app_version}"
    data_selected = "'{file1.csv}', '{file2.txt}'", # optional
    data_attributes = ["{attrib1}", "{attrib2}", "{attrib3}"], # optional
    prompt_preamble = "{Prompt preable} # optional
}
```
*Response*
```
{
    "{cache_name}"
}
```
#### **POST clear context cache**
```
POST /chat/context?request=<context_request>&option=clear
```
Clears the requested context cache. When context_request == all, will clear all context caches
*Json Data object*
```
{
    app_version = "{app_version}"
    data_selected = "'{file1.csv}', '{file2.txt}'", # optional
    data_attributes = ["{attrib1}", "{attrib2}", "{attrib3}"], # optional
    prompt_preamble = "{Prompt preable} # optional
}
```
*Response*
```
{
"Success":"Context cache cleared."
}
```
### /chat/context \[ GET \] 

#### **GET current context cache**
```
GET /chat/context
```
Returns object with a list of context caches  
*Response*
```
{
    "{context_cache}"
}
```
#### **GET token count without creating the cache**
```
GET /chat/context?request=<context_request>
```
Returns token count for requested context – does not create the context
*Response*
```
{
"token_count":<total_tokens>
}
```


### /log \[ POST \]
---
#### **POST user action logging**
```
POST /log
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
    "app_response": "{LLM response}",
    "log_id": "{log_id}" // optional, necessary for updating log entries 	
}
```
*Response*
```
{
    "log_id":"log_id"
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