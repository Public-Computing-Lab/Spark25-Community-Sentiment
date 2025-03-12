
from flask import Flask, request, jsonify
import mysql.connector
from datetime import datetime
import os
from dotenv import load_dotenv
from google import genai
from google.genai import types
import uuid
import asyncio
from pathlib import Path
from typing import List, Dict, Union

# Load environment variables
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL")
PORT = os.getenv("API_PORT")
HOST = os.getenv("API_HOST")
DATASTORE_PATH = Path(os.getenv("DATASTORE_PATH"))
PROMPTS_PATH = Path(os.getenv("PROMPTS_PATH"))
ALLOWED_EXTENSIONS = {'csv', 'txt'}  # Add more if needed
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB limit, totally arbitrary

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

#
# Helper functions
#
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
		#config=types.GenerateContentConfig(context_cache[context])
		loop = asyncio.get_event_loop()
		response = await loop.run_in_executor(None, lambda: client.models.generate_content(model=model,contents=prompt,config=types.GenerateContentConfig(cached_content=cache_name)))
		response = client.models.generate_content(model=model,contents=prompt,config=types.GenerateContentConfig(cached_content=cache_name))
		print(f"\n✅ Gemini Response: {response.text}")  # ✅ Log the response!		
		return response.text
	except Exception as e:
		print(f"❌ Error generating response: {e}")  # ✅ Log the error!
		return f"❌ Error generating response: {e}"

# TODO: Unsure if this should be async as well			
def create_gemini_context(context_request, files, preamble):
	cache_exists = False
	for cache in client.caches.list():
		if cache.display_name == context_request + files:
			cache_exists = True
			return cache.name

	try:
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
					
		# Read contents of found files
		content = {"parts": []}
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
		if context_request == 'specific':
			#this may need to be truncated if long filenames
			display_name = context_request+','.join(files)
		display_name = context_request
		
		#create the cache
		cache = client.caches.create(
			model = GEMINI_MODEL,
			config=types.CreateCachedContentConfig(
			  display_name=display_name, 
			  system_instruction=(prompt_content),
			  contents=content["parts"]			  
		  )
		)
		context_meta = {
			'status': 'success',
			'context_request': context_request,
			'files': sorted(files),
			'count': len(files),
			'cache_name': cache.name
		}
		
		return cache.name
			
	except Exception as e:
		print(f"❌ Error generating response: {e}")  # ✅ Log the error!
		return f"❌ Error generating response: {e}"
	
# Log entry - really for testing at the moment
def log_chat(session_id, app_version, data_selected, data_attributes, prompt_preamble, client_query, app_response, client_response_rating):
	try:
		conn = get_db_connection()
		cursor = conn.cursor()
	
		query = """
		INSERT INTO chat_logs (
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
	
		cursor.execute(query, values)
		conn.commit()
		
		log_message_id = cursor.lastrowid
		
		return cursor.lastrowid
	
	except mysql.connector.Error as err:
		print(f"Database error: {str(err)}")
		return False
	
	finally:
		if 'conn' in locals():
			cursor.close()
			conn.close()

def log_chat_response_rating(log_id, client_response_rating):
	try:
		conn = get_db_connection()
		cursor = conn.cursor()
		
		query = f"""
		UPDATE chat_logs
		SET client_response_rating = "{client_response_rating}"
		WHERE id = "{log_id}"		
		"""		
		
		cursor.execute(query)
		conn.commit()
		if cursor.rowcount > 0:
			return log_id
		else:
			return None
	
	except mysql.connector.Error as err:
		print(f"Database error: {str(err)}")
		return False
	
	finally:
		if 'conn' in locals():
			cursor.close()
			conn.close()	
#
#Endpoint Definitions
#
@api.route('/data', methods=['GET', 'POST'])
def route_data():
	if request.method == 'GET':
		try:
			data_request = request.args.get('data_request', '')			
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
		
			return jsonify({
				'status': 'success',
				'request_type': file_type,
				'files': sorted(files),
				'contents': file_contents,
				'count': len(files)
			})
		
		except Exception as e:
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
			return jsonify({
				'error': str(e)
			}), 500

@api.route('/chat', methods=['POST'])
def route_chat():
	context_request = request.args.get('context_request', '')
		
	data = request.get_json()	
	
	# Generate a session ID if not provided
	session_id = data.get('session_id', str(uuid.uuid4()))
	
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
		log_id = log_chat(session_id, 			
			app_version,
			context_request + ' ' + data_selected,
			data_attributes,
			prompt_preamble,
			client_query,			
			app_response,
			None
		)		
		
		response = {
			'session_id': session_id,		
			'response': app_response,
			'log_id': log_id		
		}
		
		return jsonify(response)
	
	except Exception as e:
		print(f"❌ Exception in /chat: {e}")
		return jsonify({"error": f"Internal server error: {e}"}), 500

@api.route('/chat/context', methods=['GET','POST'])
def route_chat_context():
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
		
		return jsonify(response)
		
@api.route('/chat/context/clear', methods=['POST'])
def route_chat_context_clear():
	for cache in client.caches.list():		
		client.caches.delete(name=cache.name)
	
	return jsonify({'Success': 'Context cache cleared.'})
	
# query string log_action [insert, client_response_rating]
@api.route('/log', methods=['POST'])
def route_log():
	log_switch = request.args.get('log_action', '')
	data = request.get_json()
	if log_switch == 'insert':		
		log_id = log_chat(
			session_id=data.get('session_id', ''),			
			app_version=data.get('app_version', ''),
			data_selected=data.get('data_selected', ''),
			data_attributes=data.get('data_attributes', ''),
			prompt_preamble=data.get('prompt_preambe',''),
			client_query=data.get('client_query', ''),
			app_response=data.get('app_response', ''),
			client_response_rating=data.get('client_response_rating', '')
		)
		if id != 0:		
			return jsonify({'message': 'Log entry created successfully', 'log_id': log_id}), 201
		else:
			return jsonify({'error': 'Failed to create log entry'}), 500
		
	if log_switch == 'update_client_response_rating':
		if log_chat_response_rating(
			log_id=data.get('log_id', ''),			
			client_response_rating=data.get('client_response_rating', '')
		):
			return jsonify({'message': 'Log entry created successfully'}), 201
		else:
			return jsonify({'error': 'Failed to create log entry'}), 500	
	
if __name__ == '__main__':	
	api.run(host=HOST, port=PORT, debug=True)
