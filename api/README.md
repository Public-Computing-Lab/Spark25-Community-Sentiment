# RethinkAI - API

This project is a **Flask-based REST-ish API** supporting the RethinkAI experiments.

##  Endpoints

### /chat/data/query \[ GET \] 
---
#### **GET crime and 311 data as geoJson objects***
```
GET /data/query?request=<request_type>&category=<311_category>&date=%Y-%m&zipcode=<zipcode>&app_version=<0.0>&output_type=<type>
```
##### Query arguments:
```app_version=<n.n>```    
```category={living_conditions | trash | streets | parking | all}```  
```date=%Y-%m``` is date in format 2020-04  
```output_type=<csv | json | stream}``` sets how data is returned, defaults to json  
```request=<311_by_geo | 311_summary | 311_summary | 911_shots_fired | 911_homicides_and_shots_fired>``` set data to get   

**DEPRECATED**
```stream={True | False}``` toggles streamed data on query. Use output_type.

**Required**:
Set 'category=\<category_name\>' 

**Requested**:
Set 'app_version' for logging purposes
Set 'output_type' to return data streams for large queries, default is 'False'

**Optional**:
When 'date' is set, response is only for that date (YYYY-MM)
When 'zipcode' is set, response is limited to that (or those) zipcodes

##### Examples:

```GET /data/query?request=311_by_geo&app_version=0.7.0&category=all&date=2019-02&output_type=stream```   

*Response*: 
```
[{"type": "Street Light Outages", "date": "2019-02-01T01:01:00", "latitude": 42.28815955047899, "longitude": -71.07624064392203, "normalized_type": "Streets, Sidewalks, And Parks"},
{"type": "Request for Pothole Repair", "date": "2019-02-01T02:36:00", "latitude": 42.28799780855182, "longitude": -71.07788181270013, "normalized_type": "Streets, Sidewalks, And Parks"},
{"type": "Illegal Dumping", "date": "2019-02-01T03:34:00", "latitude": 42.3136695303992, "longitude": -71.06354055837639, "normalized_type": "Trash, Recycling, And Waste"},
{"type": "Parking Enforcement", "date": "2019-02-01T03:42:00", "latitude": 42.30033128015117, "longitude": -71.05554981087488, "normalized_type": "Parking"},
...]
```  
---
```GET /data/query?request=311_by_geo&app_version=0.7.0&category=all&output_type=stream```
  
*Response*: 
```
[{"type": "Unshoveled Sidewalk", "date": "2018-01-01T01:13:49", "latitude": 42.29328953098479, "longitude": -71.06248060117767, "normalized_type": "Streets, Sidewalks, And Parks"},
{"type": "Requests for Street Cleaning", "date": "2018-01-01T01:17:25", "latitude": 42.29318951933669, "longitude": -71.05414058306353, "normalized_type": "Streets, Sidewalks, And Parks"},
{"type": "Pest Infestation - Residential", "date": "2018-01-01T04:42:00", "latitude": 42.29162964489721, "longitude": -71.07515104543928, "normalized_type": "Living Conditions"},
{"type": "Poor Conditions of Property", "date": "2018-01-01T07:14:03", "latitude": 42.31125956241783, "longitude": -71.08671061589506, "normalized_type": "Living Conditions"},
...]
```  
---
```GET /data/query?request=911_shots_fired&app_version=0.7.0&output_type=stream```

*Response*: 
```
[{"date": "2018-11-27T18:28:00", "ballistics_evidence": 0, "latitude": 42.31106389, "longitude": -71.07089457},
{"date": "2018-11-30T05:24:00", "ballistics_evidence": 0, "latitude": 42.29899805, "longitude": -71.06538128},
{"date": "2018-12-02T02:45:00", "ballistics_evidence": 1, "latitude": 42.30201489, "longitude": -71.0777625},
{"date": "2018-11-30T23:44:00", "ballistics_evidence": 1, "latitude": 42.30312067, "longitude": -71.06066511},
...]
```  
---
```GET /data/query?request=911_homicides_and_shots_fired&app_version=0.7.0&output_type=stream```

*Response*: 
```
[{"date": "2019-08-06T05:29:20", "latitude": 42.27119574, "longitude": -71.09732141},
{"date": "2019-08-06T05:29:20", "latitude": 42.30473204, "longitude": -71.08111101},
{"date": "2020-01-23T00:15:39", "latitude": 42.31419046, "longitude": -71.06550668},
{"date": "2020-02-05T23:28:42", "latitude": 42.31372767, "longitude": -71.07216273},
...]
```
---
```GET /data/query?request=311_summary&app_version=0.7.0&category=all&output_type=stream```  
311 summary for all data in base filter  
*Response*:
```
{"reported_issue": "Trash, Recycling, And Waste", "total": 20395},
{"reported_issue": "Parking", "total": 43266},
{"reported_issue": "Living Conditions", "total": 22542},
{"reported_issue": "Streets, Sidewalks, And Parks", "total": 50003}
```
---
```GET /data/query?request=311_summary&app_version=0.7.0&category=all&devent_ids=<list of 311 ids>&output_type=stream```  
311 summary from listed ids  
*Response*:
```
{"reported_issue": "Streets, Sidewalks, And Parks", "total": 1},
{"reported_issue": "Trash, Recycling, And Waste", "total": 1},
{"reported_issue": "Living Conditions", "total": 1}
```
---
```GET /data/query?request=311_summary&app_version=0.7.0&category=all&date=<YYYY-MM>&output_type=stream```  
311 summary for stated date  
NOTE: if event_ids and data are both given, will only return summary by id  
*Response*:
```
{"reported_issue": "Trash, Recycling, And Waste", "total": 117},
{"reported_issue": "Parking", "total": 380},
{"reported_issue": "Living Conditions", "total": 139},
{"reported_issue": "Streets, Sidewalks, And Parks", "total": 667}
```

### /chat/data/query \[ POST \] 
---
#### **POST data query request, used when requesting many 311 records**
```
POST /data/query?request=311_summary&app_version=0.7.0&output_type=json"  
``` 
*Json Data object*  
```
{  
    event_ids: "1718415,1716303,1707849,1714058,1714546,..."  
}  
```
*Response*  
```  
[ 
  { 
    "category": "Living Conditions", 
    "subcategory": "TOTAL", 
    "total": 1 
  }, 
  { 
    "category": "Parking", 
    "subcategory": "Parking Enforcement", 
    "total": 3 
  }, 
  { 
    "category": "Parking", 
    "subcategory": "TOTAL", 
    "total": 3 
  }, 
  { 
    "category": "Streets, Sidewalks, And Parks", 
    "subcategory": "Request for Pothole Repair", 
    "total": 9 
  }, 
  { 
    "category": "Streets, Sidewalks, And Parks", 
    "subcategory": "TOTAL", 
    "total": 9 
  } 
]
```  

### /chat \[ POST \]
---
#### **POST user question with prompt preamble for data context**
```
POST /chat?request={structured | unstructured | all | specific}
```
*Json Data object*
```
{
    app_version: "{app_version}"
    data_selected: ["{file1.csv}", "{file2.txt}"] #required for context_request=specific
    data_attributes: ["{attrib1}", "{attrib2}", "{attrib3}"] #optional
    client_query: "{User chat query}",
    prompt_preamble: "{Prompt preable} #required for context_request=specific"
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
    app_version: "{app_version}"
    data_selected: "'{file1.csv}', '{file2.txt}'", # optional
    data_attributes: ["{attrib1}", "{attrib2}", "{attrib3}"], # optional
    prompt_preamble: "{Prompt preable} # optional
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
    app_version: "{app_version}"
    data_selected: "'{file1.csv}', '{file2.txt}'", # optional
    data_attributes: ["{attrib1}", "{attrib2}", "{attrib3}"], # optional
    prompt_preamble: "{Prompt preable} # optional
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

### /llm_summaries \[ GET \] 

#### **GET LLM Summaries by date***
```
GET /llm_summaries?month=%Y-%m&app_version=<0.0>
```
Returns a pre-fetched LLM summary for given month in YYYY-MM format

*Response*
```
{
  "month": "2022-08",
  "summary": "## August 2022: City Safety and Service Summary\n\nThis report summarizes..."
}  
```

### /llm_summaries/all \[ GET \] 

#### **GET all LLM Summaries***
```
GET /llm_summaries/all?app_version=<0.0>
```
*Response*
```
[
  {
    "month_label": "2018-01",
    "summary": "## City Safety & Service Snapshot: January 2018\n\nThis summary highlights..."
  },
  {
    "month_label": "2018-02",
    "summary": "While the provided data spans 2018 through 2024, you're requesting a summary ..."
  },
  {
    "month_label": "2018-03",
    "summary": "## Boston Safety & Service Trends: 2018-2023 (Year-to-Date)\n\nThis summary ..."
  }.
  ...
]
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
#client apps will need to have a matching api key  
#supports a list of keys  
RETHINKAI_API_KEYS=<key,key,key>  

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