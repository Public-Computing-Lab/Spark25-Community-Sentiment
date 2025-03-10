
from flask import Flask, request, jsonify
import mysql.connector
from datetime import datetime
import os
from dotenv import load_dotenv
import google.generativeai as genai
import uuid
import asyncio

# Load environment variables
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
PORT = os.getenv("API_PORT")
HOST = os.getenv("API_HOST")

api = Flask(__name__)

# Database configuration
db_config = {
	'host': os.getenv('DB_HOST', 'localhost'),
	'user': os.getenv('DB_USER'),
	'password': os.getenv('DB_PASSWORD'),
	'database': os.getenv('DB_NAME')
}

# GenAI configuration
genai.configure(api_key=GEMINI_API_KEY)

# Data storage placeholder
data_store = []

# DB Connection
def get_db_connection():
	return mysql.connector.connect(**db_config)
	
# Send prompt to Gemini
async def get_gemini_response(prompt):
	"""Sends the prompt to Google Gemini and returns the response."""
	try:
		model = genai.GenerativeModel("gemini-1.5-pro")
		loop = asyncio.get_event_loop()
		response = await loop.run_in_executor(None, lambda: model.generate_content(prompt))
		
		print(f"\n✅ Gemini Response: {response.text}")  # ✅ Log the response!
		
		return response.text
	except Exception as e:
		print(f"❌ Error generating response: {e}")  # ✅ Log the error!
		return f"❌ Error generating response: {e}"

# Log entry
def log_chat(session_id, timestamp, experiment_version, data_active, data_attributes, user_query, llm_response, user_rating):
	# session_id: browser session
	# experiment_version: RethinkAI experiment being logged
	# data_used: list of data sources (not actual data)
	# data_attributes: list of active data attributes (if data is filtered)
	# user_query: user chat query 
	# llm_prompt: pre-engineer prompt used
	# llm_response: full response text from LLM
	# user_rating: 1 = question answered; 0 = question not answered
	# timestamp 
	try:
		conn = get_db_connection()
		cursor = conn.cursor()
	
		query = """
		INSERT INTO chat_logs (
			session_id,
			timestamp,
			experiment_version,
			data_active,
			data_attributes,
			user_query,
			llm_response,
			user_rating
		) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
		"""
	
		values = (
			session_id,
			timestamp,
			experiment_version,
			data_active,
			data_attributes,
			user_query,
			llm_response,
			user_rating
		)
	
		cursor.execute(query, values)
		conn.commit()
		return True
	
	except mysql.connector.Error as err:
		print(f"Database error: {str(err)}")
		return False
	
	finally:
		if 'conn' in locals():
			cursor.close()
			conn.close()

def log_chat_feedback(session_id, timestamp, user_rating):
	try:
		conn = get_db_connection()
		cursor = conn.cursor()
		
		query = f"""
		UPDATE chat_logs
		SET user_rating = {user_rating}
		WHERE session_id = {session_id}
		AND timestamp = {timestamp}
		"""
		
		curson.execute(query)
		return True
	
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
def handle_data():
	if request.method == 'GET':
		return jsonify(data_store)

	elif request.method == 'POST':
		data = request.get_json()
		if not data:
			return jsonify({'error': 'No data provided'}), 400

		data_id = str(uuid.uuid4())
		# placeholder
		data_store[data_id] = data
		return jsonify({'id': data_id, 'data': data}), 201

@api.route('/chat', methods=['POST'])
def chat():
	prompt_switch = request.args.get('prompt', '')
	data = request.get_json()
	
	# Generate a session ID if not provided
	session_id = data.get('session_id', str(uuid.uuid4()))
	
	# Extract chat parameters
	experiment_version = data.get('experiment_version', '')
	data_active = data.get('data_active', '')
	data_attributes = data.get('data_attributes', '')
	user_query = data.get('user_query', '')
	
	prompt_preamble = '';
	if prompt_switch == 'structured':
		prompt_preamble = 'PLACEHODER TEXT FOR STRUCTURED DATA PROMPT'
	elif prompt_switch == 'unsctructured':
		prompt_preamble = 'PLACEHODLDER TEXT FOR UNSTRUCTURED DATA PROMPT'
		
	full_prompt = f"{prompt_preamble}\n\nUser question: {user_query}"
	
	# Process chat 
	llm_response = get_gemini_response(prompt)
	response_timestamp = datetime.now().isoformat()
	
	# Log the interaction
	log_status = log_chat(session_id, 
		response_timestamp,		
		experiment_version,
		data_active,
		data_attributes,
		user_query,
		llm_response,
		None
	)		
	
	response = {
		'session_id': session_id,		
		'response': llm_response,
		'timestamp': response_timestamp,
		'log_status': 'success' if log_status else 'failed'
	}
	
	return jsonify(response)

@api.route('/chat/context', methods=['POST'])
def chat_context():
	data = request.get_json()
	if not data or 'context' not in data:
		return jsonify({'error': 'No context provided'}), 400

	# set and update context cache
	# TODO: see https://ai.google.dev/gemini-api/docs/caching?lang=python
	
	return jsonify(response)

# query string log_action [insert, update_feedback]
@api.route('/log', methods=['POST'])
def log():
	log_switch = request.args.get('log_action', '')
	data = request.get_json()
	
	if log_switch == 'insert':		
		if log_chat(
			session_id=data.get('session_id', ''),
			timestamp=data.get('timestamp', ''),
			experiment_version=data.get('experiment_version', ''),
			data_active=data.get('data_active', ''),
			data_attributes=data.get('data_attributes', ''),
			user_query=data.get('user_query', ''),
			llm_response=data.get('llm_response', ''),
			user_rating=data.get('user_rating', '')
		):		
			return jsonify({'message': 'Log entry created successfully'}), 201
		else:
			return jsonify({'error': 'Failed to create log entry'}), 500
		
	if log_switch == 'update_feedback':
		if log_chat_feedback(
			session_id=data.get('session_id', ''),
			timestamp=data.get('timestamp', ''),
			user_rating=data.get('user_rating', '')
		):
			return jsonify({'message': 'Log entry created successfully'}), 201
		else:
			return jsonify({'error': 'Failed to create log entry'}), 500	
	
if __name__ == '__main__':	
	api.run(host=HOST, port=PORT, debug=True)
