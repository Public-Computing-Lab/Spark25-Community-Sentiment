
from flask import Flask, request, jsonify, make_response, render_template_string, session, g
import mysql.connector
import datetime
import os
from dotenv import load_dotenv
from google import genai
from google.genai import types
import uuid
import asyncio
from pathlib import Path
from typing import List, Dict, Union
import re
import csv
import io

# Load environment variables
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL")
GEMINI_CACHE_TTL = os.getenv("GEMINI_CACHE_TTL")
PORT = os.getenv("API_PORT")
HOST = os.getenv("API_HOST")
DATASTORE_PATH = Path(os.getenv("DATASTORE_PATH"))
PROMPTS_PATH = Path(os.getenv("PROMPTS_PATH"))
ALLOWED_EXTENSIONS = {'csv', 'txt'}  # Add more if needed
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB limit, totally arbitrary
FLASK_SECRET_KEY=os.getenv("FLASK_SECRET_KEY","rethinkAI2025!")
FLASK_SESSION_COOKIE_SECURE=os.getenv("FLASK_SESSION_COOKIE_SECURE",False)

# Database configuration
db_config = {
	'host': os.getenv('DB_HOST', 'localhost'),
	'user': os.getenv('DB_USER'),
	'password': os.getenv('DB_PASSWORD'),
	'database': os.getenv('DB_NAME')
}

# GenAI configuration
client = genai.Client(api_key=GEMINI_API_KEY)

api = Flask(__name__)
# Set up configuration
api.config.update(
	SECRET_KEY=FLASK_SECRET_KEY,
	PERMANENT_SESSION_LIFETIME = datetime.timedelta(days=7),
	SESSION_COOKIE_HTTPONLY=True,
	SESSION_COOKIE_SECURE=FLASK_SESSION_COOKIE_SECURE  # Set to True in production with HTTPS
)

#
# Helper functions
#

# Checks if a string is in 'YYYY-MM' format.
def is_ym_format(date_string):
	pattern = r"^\d{4}-\d{2}$"
	match = re.match(pattern, date_string)
	if match:
		year, month = map(int, date_string.split('-'))
		if 1 <= month <= 12:
			return True
	return False

def allowed_file(filename: str) -> bool:
	return '.' in filename and \
		filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS
	   
def get_files(file_type: str = None, specific_files: List[str] = None) -> List[str]:
	try:
		if not DATASTORE_PATH.exists():
			return []

		if specific_files:
			return [
				str(f.name) for f in DATASTORE_PATH.iterdir()
				if f.is_file() and f.name in specific_files and not f.name.startswith('.')
			]

		if file_type:
			return [
				str(f.name) for f in DATASTORE_PATH.iterdir()
				if f.is_file() and f.suffix.lower() == f'.{file_type}' and not f.name.startswith('.')
			]

		return [
			str(f.name) for f in DATASTORE_PATH.iterdir()
			if f.is_file() and not f.name.startswith('.')
		]

	except Exception as e:
		print(f"Error getting files: {e}")
		return []

def read_file_content(filename: str) -> Union[str, Dict, None]:
	try:
		file_path = DATASTORE_PATH / filename
		if not file_path.exists():
			return None

		if file_path.suffix.lower() == '.csv':
			# For CSV files, you might want to use pandas or csv module
			with open(file_path, 'r') as f:
				return f.read()

		elif file_path.suffix.lower() == '.txt':
			with open(file_path, 'r') as f:
				return f.read()

		return None

	except Exception as e:
		print(f"Error reading file {filename}: {e}")
		return None

# DB Connection
def get_db_connection():
	return mysql.connector.connect(**db_config)
	
# Send prompt to Gemini
async def get_gemini_response(prompt, cache_name):
	"""Sends the prompt to Google Gemini and returns the response."""	
	try:	
		model = GEMINI_MODEL		
		loop = asyncio.get_event_loop()
		response = await loop.run_in_executor(None, lambda: client.models.generate_content(model=model,contents=prompt,config=types.GenerateContentConfig(cached_content=cache_name)))
		print(f"\n✅ Gemini Response: {response.text}")  # ✅ Log the response!		
		return response.text
	except Exception as e:
		print(f"❌ Error generating response: {e}")  # ✅ Log the error!
		return f"❌ Error generating response: {e}"

# TODO: Unsure if this should be async as well			
def create_gemini_context(context_request, files="", preamble="", generate_cache=True):
	# test if cache exists	
	for cache in client.caches.list():
		if cache.display_name == context_request + files:		
			return cache.name

	try:
		# dict for gemini context
		content = {"parts": []}
		
		if context_request == 'structured':
			files = get_files('csv')
			preamble = 'structured_data_prompt.txt'
		elif context_request == 'unstructured':
			files = get_files('txt')
			preamble = 'unstructured_data_prompt.txt'			
		elif context_request == 'all':
			files = get_files()
			preamble = 'all_data_prompt.txt'
		elif context_request == 'specific':
			if files != '':
				specific_files = [f.strip() for f in files.split(',')]
				files = get_files(specific_files=specific_files)
			else:
				return False
		elif context_request == 'experiment_5':			
			files = get_files('txt')
			query = f"""
			WITH incident_data AS (
				SELECT
					year,
					'911 Shot Fired Confirmed' AS incident_type,
					quarter,
					month
				FROM shots_fired_data
				WHERE 
					district IN ('B2', 'B3', 'C11') 
					AND ballistics_evidence = 1 
					AND neighborhood = 'Dorchester' 
					AND year >= 2018 
					AND year < 2025
				UNION ALL
				SELECT
					year,
					'911 Shot Fired Unconfirmed' AS incident_type,
					quarter,
					month
				FROM shots_fired_data
				WHERE 
					district IN ('B2', 'B3', 'C11') 
					AND ballistics_evidence = 0 
					AND neighborhood = 'Dorchester' 
					AND year >= 2018 
					AND year < 2025
				UNION ALL
				SELECT
					year,
					'911 Homicides' AS incident_type,
					quarter,
					month
				FROM homicide_data
				WHERE 
					district IN ('B2', 'B3', 'C11')
					AND neighborhood = 'Dorchester'
					AND year >= 2018
					AND year < 2025
				UNION ALL
				SELECT
					YEAR(open_dt) AS year,
					'311 Trash/Dumping Issues' AS incident_type,
					QUARTER(open_dt) AS quarter,
					MONTH(open_dt) AS month
				FROM bos311_data
				WHERE 
					type IN ('Missed Trash/Recycling/Yard Waste/Bulk Item', 'Illegal Dumping') 
					AND police_district IN ('B2', 'B3', 'C11') 
					AND neighborhood = 'Dorchester'
				UNION ALL
				SELECT
					YEAR(open_dt) AS year,
					'311 Living Condition Issues' AS incident_type,
					QUARTER(open_dt) AS quarter,
					MONTH(open_dt) AS month
				FROM bos311_data
				WHERE 
					type IN ('Poor Conditions of Property', 'Needle Pickup', 'Unsatisfactory Living Conditions', 
							'Rodent Activity', 'Heat - Excessive Insufficient', 'Unsafe Dangerous Conditions', 
							'Pest Infestation - Residential') 
					AND police_district IN ('B2', 'B3', 'C11') 
					AND neighborhood = 'Dorchester'
				UNION ALL
				SELECT
					YEAR(open_dt) AS year,
					'311 Streets Issues' AS incident_type,
					QUARTER(open_dt) AS quarter,
					MONTH(open_dt) AS month
				FROM bos311_data
				WHERE 
					type IN ('Requests for Street Cleaning', 'Request for Pothole Repair', 'Unshoveled Sidewalk', 
							'Tree Maintenance Requests', 'Sidewalk Repair (Make Safe)', 'Street Light Outages', 'Sign Repair') 
					AND police_district IN ('B2', 'B3', 'C11') 
					AND neighborhood = 'Dorchester'
				UNION ALL
				SELECT
					YEAR(open_dt) AS year,
					'311 Parking Issues' AS incident_type,
					QUARTER(open_dt) AS quarter,
					MONTH(open_dt) AS month
				FROM bos311_data
				WHERE 
					type IN ('Parking Enforcement', 'Space Savers', 'Parking on Front/Back Yards (Illegal Parking)', 
							'Municipal Parking Lot Complaints', 'Private Parking Lot Complaints') 
					AND police_district IN ('B2', 'B3', 'C11') 
					AND neighborhood = 'Dorchester'
			)
			SELECT
				year,
				incident_type,
				COUNT(*) AS total_by_year,
				SUM(CASE WHEN quarter = 1 THEN 1 ELSE 0 END) AS q1_total,
				SUM(CASE WHEN quarter = 2 THEN 1 ELSE 0 END) AS q2_total,
				SUM(CASE WHEN quarter = 3 THEN 1 ELSE 0 END) AS q3_total,
				SUM(CASE WHEN quarter = 4 THEN 1 ELSE 0 END) AS q4_total,
				SUM(CASE WHEN month = 1 THEN 1 ELSE 0 END) AS jan_total,
				SUM(CASE WHEN month = 2 THEN 1 ELSE 0 END) AS feb_total,
				SUM(CASE WHEN month = 3 THEN 1 ELSE 0 END) AS mar_total,
				SUM(CASE WHEN month = 4 THEN 1 ELSE 0 END) AS apr_total,
				SUM(CASE WHEN month = 5 THEN 1 ELSE 0 END) AS may_total,
				SUM(CASE WHEN month = 6 THEN 1 ELSE 0 END) AS jun_total,
				SUM(CASE WHEN month = 7 THEN 1 ELSE 0 END) AS jul_total,
				SUM(CASE WHEN month = 8 THEN 1 ELSE 0 END) AS aug_total,
				SUM(CASE WHEN month = 9 THEN 1 ELSE 0 END) AS sep_total,
				SUM(CASE WHEN month = 10 THEN 1 ELSE 0 END) AS oct_total,
				SUM(CASE WHEN month = 11 THEN 1 ELSE 0 END) AS nov_total,
				SUM(CASE WHEN month = 12 THEN 1 ELSE 0 END) AS dec_total
			FROM incident_data
			GROUP BY year, incident_type
			ORDER BY year, incident_type		
			"""
			
			results = db_query(query=query)
			result_string = ""
			
			output = io.StringIO()  
			writer = csv.DictWriter(output, fieldnames=results[0].keys()) 
			writer.writeheader()
			writer.writerows(results)
			result_string = output.getvalue()				
			
			content["parts"].append({"text":result_string})
			
			preamble = 'experiment_5.txt'			
			
		# Read contents of found files
		
		for file in files:
			file_content = read_file_content(file)
			if file_content is not None:				
				content["parts"].append({"text":file_content})
						
		# Read prompt preamble		
		if context_request != 'specific':
			path = PROMPTS_PATH / preamble		
			if not path.is_file():
				raise FileNotFoundError(f"File not found: {PROMPTS_PATH}")
			try:
				prompt_content = path.read_text(encoding='utf-8')
			except Exception as e:
				raise Exception(f"Error reading file HERE: {str(e)}")
		else:
			prompt_content = preamble
				
		#set the display name
		if generate_cache:
			if context_request == 'specific':
				#this may need to be truncated if long filenames
				display_name = context_request+','.join(files)
			else:
				display_name = context_request
			
			#set cache expire time
			expire_time = (
				(
					datetime.datetime.now(datetime.timezone.utc)
					+ datetime.timedelta(days=int(GEMINI_CACHE_TTL))
				)
				.isoformat()
				.replace("+00:00", "Z")
			)
			#create the cache
			cache = client.caches.create(
				model = GEMINI_MODEL,
				config=types.CreateCachedContentConfig(
				display_name=display_name, 
				system_instruction=(prompt_content),
				expire_time=expire_time,
				contents=content["parts"]			  
			)
			)
			
			return cache.name
		#just return token count for the cache as test
		else:
			content["parts"].append({"text":prompt_content})			
			total_tokens = client.models.count_tokens(
				model=GEMINI_MODEL, 
				contents=content["parts"]
			)			
			return total_tokens
			
	except Exception as e:
		print(f"❌ Error generating response: {e}") 
		return f"❌ Error generating response: {e}"

# Log events
def log_event(session_id, app_version, data_selected='', data_attributes='', prompt_preamble='', client_query='', app_response='', client_response_rating='', log_id=''):
	if not session_id or not app_version:
		print(f"Missing session_id or app_version: {str(err)}")
		return False 
	try:
		conn = get_db_connection()
		cursor = conn.cursor()
		#empty log_id, insert new entry	
		if not log_id:
			query = """
			INSERT INTO interaction_log (
				session_id,			
				app_version,
				data_selected,
				data_attributes,
				prompt_preamble,
				client_query,
				app_response,
				client_response_rating
			) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
			"""
			
			values = (
				session_id,			
				app_version,
				data_selected,
				data_attributes,
				prompt_preamble,
				client_query,
				app_response,
				client_response_rating
			)
		#log_id exists, update entry, only w/ non-null fields	
		else:			
			query = f"""
			UPDATE interaction_log
			"""
			if data_selected:
				query += f"""
				SET data_selected = "{data_selected}"
				"""
			if data_attributes:
				query += f"""
				SET data_attributes = "{data_attributes}"
				"""
			if prompt_preamble:
				query += f"""
				SET prompt_preamble = "{prompt_preamble}"
				"""
			if client_query:
				query += f"""
				SET client_query = "{client_query}"
				"""
			if app_response:
				query += f"""
				SET app_response = "{app_response}"
				"""
			if client_response_rating:
				query += f"""
				SET client_response_rating = "{client_response_rating}"
				"""
			query += f"""
			WHERE id = "{log_id}"		
			"""					
			values = ''
	
		cursor.execute(query, values)
		conn.commit()
		
		if not log_id:
			app_response_id = cursor.lastrowid
		else:
			app_response_id = log_id		
		
		return app_response_id
	
	except mysql.connector.Error as err:
		print(f"Database error: {str(err)}")
		return False
	
	finally:
		if 'conn' in locals():
			cursor.close()
			conn.close()

# DB Query
def db_query(query):
	try:
		conn = get_db_connection()
		cursor = conn.cursor(dictionary=True)
	
		cursor.execute(query)
		result = cursor.fetchall()
		#print(result)
		if result:			
			return result
		else:
			return None  						
	
	except mysql.connector.Error as err:
		print(f"Database error: {str(err)}")
		return False
	
	finally:
		if 'conn' in locals():
			cursor.close()
			conn.close()

# Middleware to check session and create if needed
@api.before_request
def check_session():
	if 'session_id' not in session:
		session.permanent = True  # Make the session persistent
		session['session_id'] = str(uuid.uuid4())
		log_event(session_id=session['session_id'], app_version='0', app_response="New session created")

	# Log the request
	g.log_entry = log_event(session_id=session['session_id'], app_version='0', client_query=f"Request: {request.url}")

#
#Endpoint Definitions
#

@api.route('/data/query', methods=['GET'])
def route_data_query():
	session_id = session.get('session_id')
	app_version = request.cookies.get('app_version','0')
	
	try:
		data_request = request.args.get('request', '')			
		if not data_request:
			return jsonify({
				'error': 'Missing data_request parameter'
			}), 400
		
		request_options = request.args.get('category','')
		if data_request.startswith('311_by') and not request_options:
			return jsonify({
				'error': 'Missing required options parameter for 311 request'
			}), 400
			
		request_date = request.args.get('date','')
		if data_request.startswith('311_on_date') and not request_date:
			return jsonify({
				'error': 'Missing required options parameter for 311 request'
			}), 400
		request_zipcode = request.args.get('zipcode','')
		
		# Switch for 311_by queries using the 311 types listed below	
		if data_request.startswith('311_by'):
			if request_options == 'living_conditions':
				category_types = "'Poor Conditions of Property', 'Needle Pickup', 'Unsatisfactory Living Conditions', 'Rodent Activity', 'Unsafe Dangerous Conditions', 'Pest Infestation - Residential'"
			elif request_options == 'trash':
				category_types = "'Missed Trash/Recycling/Yard Waste/Bulk Item', 'Illegal Dumping'"
			elif request_options == 'streets':
				category_types = "'Requests for Street Cleaning', 'Request for Pothole Repair', 'Unshoveled Sidewalk', 'Tree Maintenance Requests', 'Sidewalk Repair (Make Safe)', 'Street Light Outages', 'Sign Repair'"
			elif request_options == 'parking':	
				category_types = "'Parking Enforcement', 'Space Savers', 'Parking on Front/Back Yards (Illegal Parking)', 'Municipal Parking Lot Complaints', 'Private Parking Lot Complaints'"
			elif request_options == 'all':
				category_types = "'Poor Conditions of Property', 'Needle Pickup', 'Unsatisfactory Living Conditions', 'Rodent Activity', 'Unsafe Dangerous Conditions', 'Pest Infestation - Residential', 'Missed Trash/Recycling/Yard Waste/Bulk Item', 'Illegal Dumping','Requests for Street Cleaning', 'Request for Pothole Repair', 'Unshoveled Sidewalk', 'Tree Maintenance Requests', 'Sidewalk Repair (Make Safe)', 'Street Light Outages', 'Sign Repair','Parking Enforcement', 'Space Savers', 'Parking on Front/Back Yards (Illegal Parking)', 'Municipal Parking Lot Complaints', 'Private Parking Lot Complaints'"

		if data_request == '311_on_date_geo':
			if not is_ym_format(request_date):
				return jsonify({
					'error': 'Incorrect date format. Expects "YYYY-MM"'
				}), 400
			query = f"""
			SELECT latitude, longitude
			FROM bos311_data
			WHERE DATE_FORMAT(open_dt, '%Y-%m') = '{request_date}'
				AND type IN ('Poor Conditions of Property', 'Needle Pickup', 'Unsatisfactory Living Conditions', 'Rodent Activity', 'Unsafe Dangerous Conditions', 'Pest Infestation - Residential', 'Missed Trash/Recycling/Yard Waste/Bulk Item', 'Illegal Dumping','Requests for Street Cleaning', 'Request for Pothole Repair', 'Unshoveled Sidewalk', 'Tree Maintenance Requests', 'Sidewalk Repair (Make Safe)', 'Street Light Outages', 'Sign Repair','Parking Enforcement', 'Space Savers', 'Parking on Front/Back Yards (Illegal Parking)', 'Municipal Parking Lot Complaints', 'Private Parking Lot Complaints')				
				AND police_district IN ('B3', 'B2', 'C11')
				AND neighborhood = 'Dorchester';
			"""
		elif data_request == '311_on_date_count':
			if not is_ym_format(request_date):
				return jsonify({
					'error': 'Incorrect date format. Expects "YYYY-MM"'
				}), 400
			query = f"""
			SELECT
				CASE
					WHEN type IN ('Poor Conditions of Property', 'Needle Pickup', 'Unsatisfactory Living Conditions', 'Rodent Activity', 'Unsafe Dangerous Conditions', 'Pest Infestation - Residential') THEN 'Living Conditions'
					WHEN type IN ('Missed Trash/Recycling/Yard Waste/Bulk Item', 'Illegal Dumping') THEN 'Trash, Recycling, And Waste'
					WHEN type IN ('Requests for Street Cleaning', 'Request for Pothole Repair', 'Unshoveled Sidewalk', 'Tree Maintenance Requests', 'Sidewalk Repair (Make Safe)', 'Street Light Outages', 'Sign Repair') THEN 'Streets, Sidewalks, And Parks'
					WHEN type IN ('Parking Enforcement', 'Space Savers', 'Parking on Front/Back Yards (Illegal Parking)', 'Municipal Parking Lot Complaints', 'Private Parking Lot Complaints')
					THEN 'Parking'
				END AS request_category,
				COUNT(*) AS request_count,
				DATE_FORMAT(open_dt, '%Y-%m') AS monthyear
			FROM bos311_data
			WHERE DATE_FORMAT(open_dt, '%Y-%m') = '{request_date}'
			  AND police_district IN ('B3', 'B2', 'C11')
			"""			
			if request_zipcode:				
				query += f"""
				AND location_zipcode = {request_zipcode}
				"""
			query +=  """
			AND neighborhood = 'Dorchester'
			GROUP BY request_category, monthyear
			HAVING request_category IS NOT NULL;
			"""
		elif data_request == '311_year_month':
			query= f"""
			SELECT DISTINCT DATE_FORMAT(open_dt, '%Y-%m') AS monthyear
			FROM bos311_data
			WHERE police_district IN ('B3', 'B2', 'C11')
			AND neighborhood = 'Dorchester';
			ORDER BY monthyear;
			"""
		elif data_request == '311_by_type':		
			query = f"""
			SELECT
				police_district,
				type,
				YEAR(open_dt) AS year,
				COUNT(*) AS total_by_year,
				SUM(CASE WHEN QUARTER(open_dt) = 1 THEN 1 ELSE 0 END) AS q1_total,
				SUM(CASE WHEN QUARTER(open_dt) = 2 THEN 1 ELSE 0 END) AS q2_total,
				SUM(CASE WHEN QUARTER(open_dt) = 3 THEN 1 ELSE 0 END) AS q3_total,
				SUM(CASE WHEN QUARTER(open_dt) = 4 THEN 1 ELSE 0 END) AS q4_total,
				SUM(CASE WHEN MONTH(open_dt) = 1 THEN 1 ELSE 0 END) AS jan_total,
				SUM(CASE WHEN MONTH(open_dt) = 2 THEN 1 ELSE 0 END) AS feb_total,
				SUM(CASE WHEN MONTH(open_dt) = 3 THEN 1 ELSE 0 END) AS mar_total,
				SUM(CASE WHEN MONTH(open_dt) = 4 THEN 1 ELSE 0 END) AS apr_total,
				SUM(CASE WHEN MONTH(open_dt) = 5 THEN 1 ELSE 0 END) AS may_total,
				SUM(CASE WHEN MONTH(open_dt) = 6 THEN 1 ELSE 0 END) AS jun_total,
				SUM(CASE WHEN MONTH(open_dt) = 7 THEN 1 ELSE 0 END) AS jul_total,
				SUM(CASE WHEN MONTH(open_dt) = 8 THEN 1 ELSE 0 END) AS aug_total,
				SUM(CASE WHEN MONTH(open_dt) = 9 THEN 1 ELSE 0 END) AS sep_total,
				SUM(CASE WHEN MONTH(open_dt) = 10 THEN 1 ELSE 0 END) AS oct_total,
				SUM(CASE WHEN MONTH(open_dt) = 11 THEN 1 ELSE 0 END) AS nov_total,
				SUM(CASE WHEN MONTH(open_dt) = 12 THEN 1 ELSE 0 END) AS dec_total
			FROM
				bos311_data
			WHERE
				type IN ({category_types})
				AND police_district IN ('B2','B3','C11') 
				AND neighborhood = 'Dorchester'				
			GROUP BY
				police_district, type, year 
			ORDER BY
				police_district, type, year;
			"""				
		elif data_request == '311_by_total':
			query = f"""
			SELECT
				YEAR(open_dt) AS year,
				'parking' AS incident_type,  -- Fixed category name
				COUNT(*) AS total_year,
				SUM(CASE WHEN QUARTER(open_dt) = 1 THEN 1 ELSE 0 END) AS q1_total,
				SUM(CASE WHEN QUARTER(open_dt) = 2 THEN 1 ELSE 0 END) AS q2_total,
				SUM(CASE WHEN QUARTER(open_dt) = 3 THEN 1 ELSE 0 END) AS q3_total,
				SUM(CASE WHEN QUARTER(open_dt) = 4 THEN 1 ELSE 0 END) AS q4_total,
				SUM(CASE WHEN MONTH(open_dt) = 1 THEN 1 ELSE 0 END) AS jan_total,
				SUM(CASE WHEN MONTH(open_dt) = 2 THEN 1 ELSE 0 END) AS feb_total,
				SUM(CASE WHEN MONTH(open_dt) = 3 THEN 1 ELSE 0 END) AS mar_total,
				SUM(CASE WHEN MONTH(open_dt) = 4 THEN 1 ELSE 0 END) AS apr_total,
				SUM(CASE WHEN MONTH(open_dt) = 5 THEN 1 ELSE 0 END) AS may_total,
				SUM(CASE WHEN MONTH(open_dt) = 6 THEN 1 ELSE 0 END) AS jun_total,
				SUM(CASE WHEN MONTH(open_dt) = 7 THEN 1 ELSE 0 END) AS jul_total,
				SUM(CASE WHEN MONTH(open_dt) = 8 THEN 1 ELSE 0 END) AS aug_total,
				SUM(CASE WHEN MONTH(open_dt) = 9 THEN 1 ELSE 0 END) AS sep_total,
				SUM(CASE WHEN MONTH(open_dt) = 10 THEN 1 ELSE 0 END) AS oct_total,
				SUM(CASE WHEN MONTH(open_dt) = 11 THEN 1 ELSE 0 END) AS nov_total,
				SUM(CASE WHEN MONTH(open_dt) = 12 THEN 1 ELSE 0 END) AS dec_total
			FROM
				bos311_data
			WHERE
				type IN ({category_types})
				AND police_district IN ('B2', 'B3', 'C11') 
				AND neighborhood = 'Dorchester' 
			GROUP BY
				year
			ORDER BY
				year
			"""				
		elif data_request == '311_by_geo':	
			query = f"""
			SELECT
				type,
				open_dt,
				police_district,
				location,
				latitude,
				longitude
			FROM 
				bos311_data
			WHERE 
				type IN ({category_types})
				AND police_district IN ('B2', 'B3', 'C11')
				AND neighborhood = 'Dorchester'
			"""									
		elif data_request == '911_homicides':	
			query = f"""
			SELECT
				year,
				COUNT(*) AS total_by_year,
				SUM(CASE WHEN quarter = 1 THEN 1 ELSE 0 END) AS q1_total,
				SUM(CASE WHEN quarter = 2 THEN 1 ELSE 0 END) AS q2_total,
				SUM(CASE WHEN quarter = 3 THEN 1 ELSE 0 END) AS q3_total,
				SUM(CASE WHEN quarter = 4 THEN 1 ELSE 0 END) AS q4_total,
				SUM(CASE WHEN month = 1 THEN 1 ELSE 0 END) AS jan_total,
				SUM(CASE WHEN month = 2 THEN 1 ELSE 0 END) AS feb_total,
				SUM(CASE WHEN month = 3 THEN 1 ELSE 0 END) AS mar_total,
				SUM(CASE WHEN month = 4 THEN 1 ELSE 0 END) AS apr_total,
				SUM(CASE WHEN month = 5 THEN 1 ELSE 0 END) AS may_total,
				SUM(CASE WHEN month = 6 THEN 1 ELSE 0 END) AS jun_total,
				SUM(CASE WHEN month = 7 THEN 1 ELSE 0 END) AS jul_total,
				SUM(CASE WHEN month = 8 THEN 1 ELSE 0 END) AS aug_total,
				SUM(CASE WHEN month = 9 THEN 1 ELSE 0 END) AS sep_total,
				SUM(CASE WHEN month = 10 THEN 1 ELSE 0 END) AS oct_total,
				SUM(CASE WHEN month = 11 THEN 1 ELSE 0 END) AS nov_total,
				SUM(CASE WHEN month = 12 THEN 1 ELSE 0 END) AS dec_total				
			FROM homicide_data
			WHERE district IN ('B2', 'B3', 'C11')
			AND year >= 2018
			AND year < 2025
			AND neighborhood = 'Dorchester'
			GROUP BY year;			
			"""				
		elif data_request == '911_shots_fired':	
			query = f"""
			SELECT
				year,
				district,
				ballistics_evidence,
				neighborhood,
				hour_of_day,
				day_of_week,
				latitude,
				longitude
			FROM shots_fired_data
			WHERE district IN ('B2', 'B3', 'C11')
			AND neighborhood = 'Dorchester'
			AND year >= 2018
			AND year < 2025			
			GROUP BY year, district, neighborhood, ballistics_evidence, hour_of_day, day_of_week, latitude, longitude;
			"""			
		elif data_request == '911_shots_fired_count_confirmed':	
			query = f"""
			SELECT
				year,
				COUNT(*) AS total_by_year,
				SUM(CASE WHEN quarter = 1 THEN 1 ELSE 0 END) AS q1_total,
				SUM(CASE WHEN quarter = 2 THEN 1 ELSE 0 END) AS q2_total,
				SUM(CASE WHEN quarter = 3 THEN 1 ELSE 0 END) AS q3_total,
				SUM(CASE WHEN quarter = 4 THEN 1 ELSE 0 END) AS q4_total,
				SUM(CASE WHEN month = 1 THEN 1 ELSE 0 END) AS jan_total,
				SUM(CASE WHEN month = 2 THEN 1 ELSE 0 END) AS feb_total,
				SUM(CASE WHEN month = 3 THEN 1 ELSE 0 END) AS mar_total,
				SUM(CASE WHEN month = 4 THEN 1 ELSE 0 END) AS apr_total,
				SUM(CASE WHEN month = 5 THEN 1 ELSE 0 END) AS may_total,
				SUM(CASE WHEN month = 6 THEN 1 ELSE 0 END) AS jun_total,
				SUM(CASE WHEN month = 7 THEN 1 ELSE 0 END) AS jul_total,
				SUM(CASE WHEN month = 8 THEN 1 ELSE 0 END) AS aug_total,
				SUM(CASE WHEN month = 9 THEN 1 ELSE 0 END) AS sep_total,
				SUM(CASE WHEN month = 10 THEN 1 ELSE 0 END) AS oct_total,
				SUM(CASE WHEN month = 11 THEN 1 ELSE 0 END) AS nov_total,
				SUM(CASE WHEN month = 12 THEN 1 ELSE 0 END) AS dec_total
			FROM shots_fired_data
			WHERE district IN ('B2', 'B3', 'C11')
			AND ballistics_evidence = 1
			AND neighborhood = 'Dorchester'
			AND year >= 2018
			AND year < 2025			
			GROUP BY year
			"""
		elif data_request == '911_shots_fired_count_unconfirmed':	
			query = f"""
			SELECT
				year,
				COUNT(*) AS total_by_year,
				SUM(CASE WHEN quarter = 1 THEN 1 ELSE 0 END) AS q1_total,
				SUM(CASE WHEN quarter = 2 THEN 1 ELSE 0 END) AS q2_total,
				SUM(CASE WHEN quarter = 3 THEN 1 ELSE 0 END) AS q3_total,
				SUM(CASE WHEN quarter = 4 THEN 1 ELSE 0 END) AS q4_total,
				SUM(CASE WHEN month = 1 THEN 1 ELSE 0 END) AS jan_total,
				SUM(CASE WHEN month = 2 THEN 1 ELSE 0 END) AS feb_total,
				SUM(CASE WHEN month = 3 THEN 1 ELSE 0 END) AS mar_total,
				SUM(CASE WHEN month = 4 THEN 1 ELSE 0 END) AS apr_total,
				SUM(CASE WHEN month = 5 THEN 1 ELSE 0 END) AS may_total,
				SUM(CASE WHEN month = 6 THEN 1 ELSE 0 END) AS jun_total,
				SUM(CASE WHEN month = 7 THEN 1 ELSE 0 END) AS jul_total,
				SUM(CASE WHEN month = 8 THEN 1 ELSE 0 END) AS aug_total,
				SUM(CASE WHEN month = 9 THEN 1 ELSE 0 END) AS sep_total,
				SUM(CASE WHEN month = 10 THEN 1 ELSE 0 END) AS oct_total,
				SUM(CASE WHEN month = 11 THEN 1 ELSE 0 END) AS nov_total,
				SUM(CASE WHEN month = 12 THEN 1 ELSE 0 END) AS dec_total
			FROM shots_fired_data
			WHERE district IN ('B2', 'B3', 'C11')
			AND ballistics_evidence = 0
			AND neighborhood = 'Dorchester'
			AND year >= 2018
			AND year < 2025			
			GROUP BY year
			"""
		elif data_request == '911_homicides_and_shots_fired':				
			query = f"""
			SELECT 			 
				h.year as year,
				h.quarter as quarter,
				h.month as month,
				h.day_of_week as day,
				h.hour_of_day as hour,
				h.district as police_district,
				s.address as shot_address,
				s.latitude as latitude,
				s.longitude as longitude				
			FROM 
				shots_fired_data s
			INNER JOIN 
				homicide_data h
			ON 
				DATE(s.incident_date_time) = DATE(h.homicide_date)			
				AND s.district = h.district
			WHERE 
				s.ballistics_evidence = 1
				AND h.district IN ('B3', 'C11', 'B2')
				AND h.neighborhood = 'Dorchester'
				AND s.year >= 2018
				AND s.year < 2025
			"""						
		
		result = db_query(query=query)			
		
		log_event(session_id=session_id, app_version=app_version, log_id=g.log_entry, app_response=f"Request: SUCCESS")	
		return jsonify(result)
		
	
	except Exception as e:
		log_event(session_id=session_id, app_version=app_version, log_id=g.log_entry, app_response=f"Request: ERROR: {str(e)}")
		return jsonify({
			'error': str(e)
		}), 500

@api.route('/data/zipcode', methods=['GET'])
def route_data_zipcode():
	session_id = session.get('session_id')
	app_version = request.cookies.get('app_version','0')
	
	try:
		data_request = request.args.get('request', '')			
		if not data_request:
			return jsonify({
				'error': 'Missing data_request parameter'
			}), 400
	
		query = f"""
		SELECT JSON_OBJECT(
			'type', 'FeatureCollection',
			'features', JSON_ARRAYAGG(
				JSON_OBJECT(
					'type', 'Feature',
					'geometry', ST_AsGeoJSON(boundary),
					'properties', JSON_OBJECT('zipcode', zipcode)
				)
			)
		)
		FROM zipcode_geo
		WHERE zipcode IN ({data_request})
		"""				
		
		result = db_query(query=query)
		
		log_event(session_id=session_id, app_version=app_version, log_id=g.log_entry, app_response=f"Request: SUCCESS")
		return jsonify(result)
	
	except Exception as e:
		log_event(session_id=session_id, app_version=app_version, log_id=g.log_entry, app_response=f"Request: ERROR: {str(e)}")
		return jsonify({
			'error': str(e)
		}), 500

@api.route('/data/file', methods=['GET', 'POST'])
def route_data_file():
	session_id = session.get('session_id')
	app_version = request.cookies.get('app_version','0')
	
	if request.method == 'GET':
		try:
			data_request = request.args.get('request', '')			
			if not data_request:
				return jsonify({
					'error': 'Missing data_request parameter'
				}), 400
		
			# Just list filenames
			if data_request == 'list':
				files = get_files()
				return jsonify({
					'status': 'success',
					'request_type': 'LIST',
					'files': sorted(files),
					'count': len(files)
				})
		
			# Get file contents based on request type
			if data_request == 'structured':
				files = get_files('csv')
				file_type = 'CSV'
			elif data_request == 'unstructured':
				files = get_files('txt')
				file_type = 'TEXT'
			elif data_request == 'all':
				files = get_files()
				file_type = 'ALL'
			else:
				specific_files = [f.strip() for f in data_request.split(',')]
				files = get_files(specific_files=specific_files)
				file_type = 'SPECIFIC'
		
			# Read contents of found files
			file_contents = {}
			for file in files:
				content = read_file_content(file)
				if content is not None:
					file_contents[file] = content
			
			log_event(session_id=session_id, app_version=app_version, log_id=g.log_entry, app_response=f"Request: SUCCESS")	
			return jsonify({
				'status': 'success',
				'request_type': file_type,
				'files': sorted(files),
				'contents': file_contents,
				'count': len(files)
			})
		
		except Exception as e:
			log_event(session_id=session_id, app_version=app_version, log_id=g.log_entry, app_response=f"Request: ERROR: {str(e)}")
			return jsonify({
				'error': str(e)
			}), 500
	#POST is totally untested
	elif request.method == 'POST':
		try:
			# Check if files were uploaded
			if 'files' not in request.files:
				return jsonify({
					'error': 'No files provided'
				}), 400
		
			files = request.files.getlist('files')
		
			if not files or files[0].filename == '':
				return jsonify({
					'error': 'No files selected'
				}), 400
		
			saved_files = []
			errors = []
		
			for file in files:
				if file and allowed_file(file.filename):
					filename = secure_filename(file.filename)
					file_path = DATASTORE_PATH / filename
		
					# Check file size
					file.seek(0, os.SEEK_END)
					size = file.tell()
					file.seek(0)
		
					if size > MAX_FILE_SIZE:
						errors.append(f"{filename}: File too large")
						continue
		
					try:
						file.save(file_path)
						saved_files.append(filename)
					except Exception as e:
						errors.append(f"{filename}: {str(e)}")
				else:
					errors.append(f"{file.filename}: Invalid file type")
		
			response = {
				'status': 'success' if saved_files else 'error',
				'saved_files': saved_files,
				'count': len(saved_files)
			}
		
			if errors:
				response['errors'] = errors
		
			return jsonify(response), 200 if saved_files else 400
		
		except Exception as e:
			log_event(session_id=session_id, app_version=app_version, log_id=g.log_entry, app_response=f"Request: ERROR: {str(e)}")
			return jsonify({
				'error': str(e)
			}), 500

@api.route('/chat/token_count', methods=['POST'])
def route_token_count():
	session_id = session.get('session_id')
	app_version = request.cookies.get('app_version','0')
	
	context_request = request.args.get('context_request', '')
	
	data = request.get_json()	
	# Extract chat data parameters
	app_version = data.get('app_version', '')
	data_selected = data.get('data_selected', '')
	data_attributes = data.get('data_attributes', '')
	client_query = data.get('client_query', '')
	prompt_preamble = data.get('prompt_preamble','')
	
	token_count=create_gemini_context(context_request=context_request, files=data_selected, preamble=prompt_preamble, generate_cache=False)
	
	# Return as JSON response
	# return jsonify({"total_tokens": "token_count.total_tokens"})
	
	if isinstance(token_count, str): 
		return jsonify({"cache_name": token_count})
	elif isinstance(token_count, int):
		return jsonify({"token_count": token_count})
	elif isinstance(token_count.total_tokens, int):
		return jsonify({"token_count": token_count.total_tokens})
	else:
		# Handle the error appropriately, e.g., log the error and return an error response
		print(f"Error getting token count: {token_count}")  # Log the error
		return jsonify({"error": "Failed to get token count"}), 500 # Return an error response

@api.route('/chat', methods=['POST'])
def route_chat():
	session_id = session.get('session_id')
	app_version = request.cookies.get('app_version','0')
	
	context_request = request.args.get('context_request', '')
		
	data = request.get_json()	
	
	# Extract chat data parameters
	app_version = data.get('app_version', '')
	data_selected = data.get('data_selected', '')
	data_attributes = data.get('data_attributes', '')
	client_query = data.get('client_query', '')
	prompt_preamble = data.get('prompt_preamble','')
	
	# data_selected, optional, list of files used when context_request==s
	cache_name=create_gemini_context(context_request, data_selected, prompt_preamble)	
	
	full_prompt = f"User question: {client_query}"

	# Process chat 
	try:
		loop = asyncio.new_event_loop()
		asyncio.set_event_loop(loop)
		app_response = loop.run_until_complete(get_gemini_response(full_prompt, cache_name))				
		if "❌ Error" in app_response:
			print(f"❌ ERROR from Gemini API: {app_response}")
			return jsonify({"error": app_response}), 500	
	
		log_status=False
		# Log the interaction
		log_id = log_event(session_id=session_id, app_version=app_version, data_selected=context_request + ' ' + data_selected,data_attributes=data_attributes,prompt_preamble=prompt_preamble,client_query=full_prompt,app_response=app_response)				
		response = {
			'session_id': session_id,		
			'response': app_response,
			'log_id': log_id		
		}
		
		log_event(session_id=session_id, app_version=app_version, log_id=g.log_entry, app_response=f"Request: SUCCESS")	
		return jsonify(response)
	
	except Exception as e:
		log_event(session_id=session_id, app_version=app_version, log_id=g.log_entry, app_response=f"Request: ERROR: {str(e)}")
		print(f"❌ Exception in /chat: {e}")
		return jsonify({"error": f"Internal server error: {e}"}), 500

@api.route('/chat/context', methods=['GET','POST'])
def route_chat_context():
	session_id = session.get('session_id')
	app_version = request.cookies.get('app_version','0')
	
	if request.method == 'GET':
		response = {}
		for cache in client.caches.list():
			response[cache.name]=str(cache)			
				
		return jsonify(response)
		
	if request.method == 'POST':
		#TODO: implement 'specific' context_request with list of files from datastore
		#FOR NOW: assumes 'structured', 'unstructured', and 'all' for context_request
		context_request = request.args.get('context_request', '')
		if not context_request:
			return jsonify({
				'error': 'Missing context_request parameter'
			}), 400
		
		data = request.get_json()
		# Extract chat data parameters
		data_selected = data.get('data_selected', '')		
		prompt_preamble = data.get('prompt_preamble','')
		
		response = cache_name=create_gemini_context(context_request, data_selected, prompt_preamble)
		
		log_event(session_id=session_id, app_version=app_version, log_id=g.log_entry, app_response=f"Request: SUCCESS")	
		return jsonify(response)
		
@api.route('/chat/context/clear', methods=['POST'])
def route_chat_context_clear():
	session_id = session.get('session_id')
	app_version = request.cookies.get('app_version','0')
	
	for cache in client.caches.list():		
		client.caches.delete(name=cache.name)
	
	log_event(session_id=session_id, app_version=app_version, log_id=g.log_entry, app_response=f"Request: SUCCESS")	
	return jsonify({'Success': 'Context cache cleared.'})
	
# query string log_action [insert, client_response_rating]
@api.route('/log', methods=['POST'])
def route_log():
	session_id = session.get('session_id')
	app_version = request.cookies.get('app_version','0')
	
	log_switch = request.args.get('log_action', '')
	data = request.get_json()

	log_id = log_event(
		session_id=session_id,			
		app_version=app_version,
		data_selected=data.get('data_selected', ''),
		data_attributes=data.get('data_attributes', ''),
		prompt_preamble=data.get('prompt_preambe',''),
		client_query=data.get('client_query', ''),
		app_response=data.get('app_response', ''),
		client_response_rating=data.get('client_response_rating', ''),
		log_id=data.get('log_id', '')
	)
	if log_id != 0:
		log_event(session_id=session_id, app_version=app_version, log_id=g.log_entry, app_response=f"Request: SUCCESS")		
		return jsonify({'message': 'Log entry created successfully', 'log_id': log_id}), 201
	else:
		log_event(session_id=session_id, app_version=app_version, log_id=g.log_entry, app_response=f"Request: ERROR: Log entry not created")
		return jsonify({'error': 'Failed to create log entry'}), 500
			
	
if __name__ == '__main__':	
	api.run(host=HOST, port=PORT, debug=True)
