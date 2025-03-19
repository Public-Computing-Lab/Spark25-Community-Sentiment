#!/bin/bash

# API base URL
API_URL="http://127.0.0.1:8888/"

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

LOG_ID=0
SESSION_ID="\"TEST_SESSION_ID\""

# Function to test /data/context endpoint
test_context_create(){
	context_data='{
		"data_selected": "",
		"prompt_preamble":""
	}'
	
	echo -e "\n${GREEN}Testing POST /chat/context?context_request=structured${NC}"
	response=$(curl -s -X POST \
		-H "Content-Type: application/json" \
		-d "$context_data" \
		"${API_URL}/chat/context?context_request=structured")
	
	if [ $? -eq 0 ]; then
		echo "Response: $response"
		echo -e "${GREEN}Chat endpoint test completed${NC}"
	else
		echo -e "${RED}Chat endpoint test failed${NC}"
	fi
	
	echo -e "\n${GREEN}Testing POST /chat/context?context_request=unstructured${NC}"
	response=$(curl -s -X POST \
		-H "Content-Type: application/json" \
		-d "$context_data" \
		"${API_URL}/chat/context?context_request=unstructured")
	
	if [ $? -eq 0 ]; then
		echo "Response: $response"
		echo -e "${GREEN}Chat endpoint test completed${NC}"
	else
		echo -e "${RED}Chat endpoint test failed${NC}"
	fi
	
	echo -e "\n${GREEN}Testing POST /chat/context?context_request=all${NC}"
	response=$(curl -s -X POST \
		-H "Content-Type: application/json" \
		-d "$context_data" \
		"${API_URL}/chat/context?context_request=all")
	
	if [ $? -eq 0 ]; then
		echo "Response: $response"
		echo -e "${GREEN}Chat endpoint test completed${NC}"
	else
		echo -e "${RED}Chat endpoint test failed${NC}"
	fi
	
}

test_context_list(){
	echo -e "\n${GREEN}Testing GET /chat/context${NC}"
	response=$(curl -X GET \
		-H "Content-Type: application/json" \
		"${API_URL}/chat/context")
	
	if [ $? -eq 0 ]; then
		echo "Response: $response"
		echo -e "${GREEN}Chat endpoint test completed${NC}"
	else
		echo -e "${RED}Chat endpoint test failed${NC}"
	fi
}

test_context_clear(){
	echo -e "\n${GREEN}Testing POST /chat/context/clear${NC}"
	response=$(curl -s -X POST \
		-H "Content-Type: application/json" \
		"${API_URL}/chat/context/clear")
	
	if [ $? -eq 0 ]; then
		echo "Response: $response"
		echo -e "${GREEN}Chat endpoint test completed${NC}"
	else
		echo -e "${RED}Chat endpoint test failed${NC}"
	fi
	
}
# Function to test /data endpoint
test_data(){
	echo -e "\n${GREEN}Testing GET /data?request=list${NC}"
	response=$(curl -X GET \
		-H "Content-Type: application/json" \
		"${API_URL}/data?data_request=list")
	
	if [ $? -eq 0 ]; then
		echo "Response: $response"
		echo -e "${GREEN}Chat endpoint test completed${NC}"
	else
		echo -e "${RED}Chat endpoint test failed${NC}"
	fi
	
	echo -e "\n${GREEN}Testing GET /data?request=structured${NC}"
	response=$(curl -X GET \
		-H "Content-Type: application/json" \
		"${API_URL}/data?data_request=structured")
	
	if [ $? -eq 0 ]; then
		echo "Response: $response"
		echo -e "${GREEN}Chat endpoint test completed${NC}"
	else
		echo -e "${RED}Chat endpoint test failed${NC}"
	fi
	
	echo -e "\n${GREEN}Testing GET /data?request=unstructured${NC}"
	response=$(curl -X GET \
		-H "Content-Type: application/json" \
		"${API_URL}/data?data_request=unstructured")
	
	if [ $? -eq 0 ]; then
		echo "Response: $response"
		echo -e "${GREEN}Chat endpoint test completed${NC}"
	else
		echo -e "${RED}Chat endpoint test failed${NC}"
	fi
	
	echo -e "\n${GREEN}Testing GET /data?request=all${NC}"
	response=$(curl -X GET \
		-H "Content-Type: application/json" \
		"${API_URL}/data?data_request=all")
	
	if [ $? -eq 0 ]; then
		echo "Response: $response"
		echo -e "${GREEN}Chat endpoint test completed${NC}"
	else
		echo -e "${RED}Chat endpoint test failed${NC}"
	fi
	
	echo -e "\n${GREEN}Testing GET /data?request=file1.csv,file2.txt${NC}"
	response=$(curl -X GET \
		-H "Content-Type: application/json" \
		"${API_URL}/data?data_request=Arrests_cleaned.csv,Transcript_4.txt")
	
	if [ $? -eq 0 ]; then
		echo "Response: $response"
		echo -e "${GREEN}Chat endpoint test completed${NC}"
	else
		echo -e "${RED}Chat endpoint test failed${NC}"
	fi
}
# Function to test /chat endpoint
#"session_id": '${SESSION_ID}',
test_chat() {
	echo -e "\n${GREEN}Testing POST /chat${NC}"
	
	chat_data='{
		"client_query": "What are the key take aways from the data?",		
		"app_version": "0",
		"data_selected": "",
		"data_attributes": ""
	}'
	
	echo -e "\n${GREEN}Testing POST /chat?context_request=structured${NC}"
	response=$(curl -s -X POST \
		-H "Content-Type: application/json" \
		-d "$chat_data" \
		"${API_URL}/chat?context_request=structured")
	echo "Response: $response"
		
	echo -e "\n${GREEN}Testing POST /chat?context_request=unstructured${NC}"
	response=$(curl -s -X POST \
		-H "Content-Type: application/json" \
		-d "$chat_data" \
		"${API_URL}/chat?context_request=unstructured")
	echo "Response: $response"

	echo -e "\n${GREEN}Testing POST /chat?context_request=all${NC}"
	response=$(curl -s -X POST \
		-H "Content-Type: application/json" \
		-d "$chat_data" \
		"${API_URL}/chat?context_request=all")
	echo "Response: $response"
	
	LOG_ID=$(echo "$response" | jq ".log_id")
	# Check if curl command was successful
	if [ $? -eq 0 ]; then
		echo -e "${GREEN}Chat endpoint test completed${NC}"
	else
		echo -e "${RED}Chat endpoint test failed${NC}"
	fi
}

test_chat_single() {
	echo -e "\n${GREEN}Testing POST /chat${NC}"
	
	chat_data='{
		"client_query": "What are the key take aways from the data?",		
		"app_version": "0",
		"data_selected": "",
		"data_attributes": ""
	}'
		
	echo -e "\n${GREEN}Testing POST /chat?context_request=unstructured${NC}"
	response=$(curl -s -X POST \
		-H "Content-Type: application/json" \
		-d "$chat_data" \
		"${API_URL}/chat?context_request=unstructured")
	echo "Response: $response"
	
	LOG_ID=$(echo "$response" | jq ".log_id")
	# Check if curl command was successful
	if [ $? -eq 0 ]; then
		echo -e "${GREEN}Chat endpoint test completed${NC}"
	else
		echo -e "${RED}Chat endpoint test failed${NC}"
	fi
}

# Function to test /log endpoint
test_log_insert() {
	echo -e "\n${GREEN}Testing POST /log?log_action=insert${NC}"

	# Current timestamp in ISO format
	#timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
	log_data='{
		"session_id": '${SESSION_ID}',		
		"app_version": "0",
		"data_selected": "NONE",
		"data_attributes": "NONE",
		"client_query": "Test log entry: QUERY",
		"app_response": "Test log entry: RESPONSE",
		"client_response_rating": ""
	}'
	
	response=$(curl -s -X POST \
		-H "Content-Type: application/json" \
		-d "$log_data" \
		"${API_URL}/log?log_action=insert")
	
	LOG_ID=$(echo "$response" | jq ".log_id")
	# Check if curl command was successful
	if [ $? -eq 0 ]; then
		echo "Response: $response"
		echo -e "${GREEN}Log endpoint test completed${NC}"
	else
		echo -e "${RED}Log endpoint test failed${NC}"
	fi
}

# Function to test /log?log_action=update_client_response_rating endpoint
test_log_update() {
	echo -e "\n${GREEN}Testing POST /log?log_action=update_client_response_rating${NC}"
	
	# Current timestamp in ISO format
	#timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
	log_data='{
		"log_id": '${LOG_ID}',			
		"client_response_rating": "UPDATED"
	}'
	
	response=$(curl -s -X POST \
		-H "Content-Type: application/json" \
		-d "$log_data" \
		"${API_URL}/log?log_action=update_client_response_rating")

	# Check if curl command was successful
	if [ $? -eq 0 ]; then
		echo "Response: $response"
		echo -e "${GREEN}Log endpoint test completed${NC}"
	else
		echo -e "${RED}Log endpoint test failed${NC}"
	fi
}

# Function to run all tests
run_all_tests() {
	echo -e "${GREEN}Starting API tests...${NC}"
	test_context_create
	test_context_list
	test_data
	test_chat
	sleep 3
	test_log_update
	test_context_clear
	echo -e "\n${GREEN}All tests completed${NC}"
}

# Main execution
case "$1" in
	"cache_create")
		test_context_create
		;;
	"cache_list")
		test_context_list
		;;
	"cache_clear")
		test_context_clear
		;;
	"data")
		test_data
		;;
	"chat")
		test_chat
		;;
	"chat_single")
		test_chat_single
		;;
	"log")
		test_log_insert
		test_log_update
		;;
	"all")
		run_all_tests
		;;
	*)
		echo "Usage: $0 [cache_create | cache_list | cache_clear | data | chat | chat_single | log | all]"
		exit 1
		;;
esac
