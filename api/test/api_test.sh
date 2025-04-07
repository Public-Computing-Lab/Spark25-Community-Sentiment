#!/bin/bash

# Configuration
API_URL="http://127.0.0.1:8888"
#API_URL="https://boston.ourcommunity.is/api"
APP_VERSION="test.x"
COOKIE_FILE="cookies.txt"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Global variables
LOG_ID=0
SESSION_ID="\"TEST_SESSION_ID\""

# Helper functions
make_request() {
	local method="$1"
	local endpoint="$2"
	local data="$3"
	local additional_args="${4:-}"

	echo -e "\n${GREEN}Testing ${method} ${endpoint}${NC}"

	local response
	if [ -n "$data" ]; then
		response=$(curl -s -X "$method" \
			-b "$COOKIE_FILE" \
			-c "$COOKIE_FILE" \
			-H "Content-Type: application/json" \
			-d "$data" \
			"${API_URL}${endpoint}" $additional_args)
	else
		response=$(curl -s -X "$method" \
			-b "$COOKIE_FILE" \
			-c "$COOKIE_FILE" \
			-H "Content-Type: application/json" \
			"${API_URL}${endpoint}" $additional_args)
	fi
	
	local status=$?
	
	if [ $status -eq 0 ]; then
		echo -e "\nResponse: $response"
		echo -e "\n${GREEN}Request completed successfully${NC}"
	else
		echo -e "\n${RED}Request failed${NC}"
	fi
	
	# echo "$response"
}

# Context functions
test_context_create() {
	local context_type="${1:-experiment_5}"
	local context_data='{
		"data_selected": "",
		"prompt_preamble":""
	}'

	local endpoint="/chat/context?context_request=${context_type}&app_version=${APP_VERSION}"
	make_request "POST" "$endpoint" "$context_data"
}

test_context_list() {
	local endpoint="/chat/context?app_version=${APP_VERSION}"
	make_request "GET" "$endpoint"
}

test_context_token_count() {
	local context_type="${1:-experiment_5}"
	local endpoint="/chat/context?context_request=${context_type}&app_version=${APP_VERSION}"
	make_request "GET" "$endpoint"
}

test_context_clear() {
	local context_data='{
		"data_selected": "",
		"prompt_preamble":""
	}'

	local endpoint="/chat/context?context_request=all&option=clear&app_version=${APP_VERSION}"
	make_request "POST" "$endpoint" "$context_data"
}

# Chat function
test_chat() {
	local context_type="${1:-experiment_5}"
	local endpoint="/chat?context_request=${context_type}&app_version=${APP_VERSION}"

	local chat_data='{
		"client_query": "The data content describes 311 reports over time to indicate relative health and conditions of the neighborhood, and 911 reports of homicides and shots fired over time indicating incidents of violent crime in the neighborhood. The text content are community meetings and interviews about experiences of safety and voilence in the neighborhood and community meetings discussing community concerns and priorities. Some people think that violence is decreasing, other people still do not feel safe in their neighborhood. Using the data and text content, describe how the two are related and why there is disagreement on the safety of the neighborhood.",        
		"data_selected": "",
		"data_attributes": ""
	}'

	local response=$(make_request "POST" "$endpoint" "$chat_data")		
	echo $response
	LOG_ID=$(echo "$response" | grep -o '"log_id": [0-9]*' | sed 's/"log_id": //')	
	echo "Log ID: $LOG_ID"
}

# Log functions
test_log_insert() {
	local endpoint="/log?app_version=${APP_VERSION}"

	local log_data='{        
		"data_selected": "NONE",
		"data_attributes": "NONE",
		"client_query": "Test log entry: QUERY",
		"app_response": "Test log entry: RESPONSE",
		"client_response_rating": ""
	}'

	local response=$(make_request "POST" "$endpoint" "$log_data")
	echo $response
	LOG_ID=$(echo "$response" | grep -o '"log_id": [0-9]*' | sed 's/"log_id": //')
	echo "Log ID: $LOG_ID"
}

test_log_update() {
	local endpoint="/log?app_version=${APP_VERSION}"

	local log_data='{
		"log_id": '${LOG_ID}',            
		"client_response_rating": "UPDATED"
	}'

	make_request "PUT" "$endpoint" "$log_data"
}

# Data query functions
test_data_query() {
	local ENDPOINTS=(
		"/data/query?request=311_by_geo&app_version=${APP_VERSION}&category=living_conditions&date=2019-02&stream=True"
		"/data/query?request=311_by_geo&app_version=${APP_VERSION}&category=trash&date=2019-02&stream=True"
		"/data/query?request=311_by_geo&app_version=${APP_VERSION}&category=streets&date=2019-02&stream=True"
		"/data/query?request=311_by_geo&app_version=${APP_VERSION}&category=parking&date=2019-02&stream=True"
		"/data/query?request=311_by_geo&app_version=${APP_VERSION}&category=all&date=2019-02&stream=True"
		"/data/query?request=311_by_geo&app_version=${APP_VERSION}&category=living_conditions&stream=True"
		"/data/query?request=311_by_geo&app_version=${APP_VERSION}&category=trash&stream=True"
		"/data/query?request=311_by_geo&app_version=${APP_VERSION}&category=streets&stream=True"
		"/data/query?request=311_by_geo&app_version=${APP_VERSION}&category=parking&stream=True"
		"/data/query?request=311_by_geo&app_version=${APP_VERSION}&category=all&stream=True"
		"/data/query?request=911_shots_fired&app_version=${APP_VERSION}&stream=True"
		"/data/query?request=911_homicides_and_shots_fired&app_version=${APP_VERSION}&stream=True"
		"/data/query?request=zip_geo&app_version=${APP_VERSION}&zipcode=02121,02115&stream=True"
	)

	start_time_big=$(perl -MTime::HiRes=time -e 'printf "%.9f", time')

	for endpoint in "${ENDPOINTS[@]}"; do
		start_time=$(perl -MTime::HiRes=time -e 'printf "%.9f", time')
		make_request "GET" "$endpoint"
		end_time=$(perl -MTime::HiRes=time -e 'printf "%.9f", time')
		elapsed=$(echo "$end_time - $start_time" | bc)
		echo "Request completed in ${elapsed} seconds"
	done

	end_time_big=$(perl -MTime::HiRes=time -e 'printf "%.9f", time')
	elapsed=$(echo "$end_time_big - $start_time_big" | bc)
	echo "All data queries completed in ${elapsed} seconds"
}

test_data_zip() {
	local endpoint="/data/query?request=zip_geo&zipcode=02121,02115&stream=True&app_version=${APP_VERSION}"
	make_request "GET" "$endpoint" "" "| head -n 5"
}

# Run all tests
run_all_tests() {
	echo -e "${GREEN}Starting API tests...${NC}"
	test_context_list
	test_context_token_count
	test_data_query
	test_chat
	sleep 3
	test_log_update
	echo -e "\n${GREEN}All tests completed${NC}"
}

# Main execution
case "$1" in
	"context_create")
		test_context_create "$2"
		;;
	"context_list")
		test_context_list
		;;
	"context_clear")
		test_context_clear
		;;
	"context_token")
		test_context_token_count "$2"
		;;
	"chat")
		test_chat "$2"
		;;
	"log")
		test_log_insert
		test_log_update
		;;
	"zip")
		test_data_zip
		;;
	"data")
		test_data_query
		;;
	"all")
		run_all_tests
		;;
	*)
		echo "Usage: $0 [context_create|context_list|context_clear|context_token|chat|log|zip|data|all] [optional_context_type]"
		exit 1
		;;
esac
