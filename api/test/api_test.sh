#!/bin/bash

# API base URL
API_URL="http://127.0.0.1:8888/"
#API_URL="https://boston.ourcommunity.is/api"
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
	
	# echo -e "\n${GREEN}Testing POST /chat/context?context_request=structured${NC}"
	# response=$(curl -s -X POST \
	# 	-b cookies.txt \
	# 	-c cookies.txt \
	# 	--cookie "app_version=0" \
	# 	-H "Content-Type: application/json" \
	# 	-d "$context_data" \
	# 	"${API_URL}/chat/context?context_request=structured")
	# 
	# if [ $? -eq 0 ]; then
	# 	echo "Response: $response"
	# 	echo -e "${GREEN}Chat endpoint test completed${NC}"
	# else
	# 	echo -e "${RED}Chat endpoint test failed${NC}"
	# fi
	# 
	# echo -e "\n${GREEN}Testing POST /chat/context?context_request=unstructured${NC}"
	# response=$(curl -s -X POST \
	# 	-b cookies.txt \
	# 	-c cookies.txt \
	# 	--cookie "app_version=0" \
	# 	-H "Content-Type: application/json" \
	# 	-d "$context_data" \
	# 	"${API_URL}/chat/context?context_request=unstructured")
	# 
	# if [ $? -eq 0 ]; then
	# 	echo "Response: $response"
	# 	echo -e "${GREEN}Chat endpoint test completed${NC}"
	# else
	# 	echo -e "${RED}Chat endpoint test failed${NC}"
	# fi
	# 
	# echo -e "\n${GREEN}Testing POST /chat/context?context_request=all${NC}"
	# response=$(curl -s -X POST \
	# 	-b cookies.txt \
	# 	-c cookies.txt \
	# 	--cookie "app_version=0" \
	# 	-H "Content-Type: application/json" \
	# 	-d "$context_data" \
	# 	"${API_URL}/chat/context?context_request=all")
	# 
	# if [ $? -eq 0 ]; then
	# 	echo "Response: $response"
	# 	echo -e "${GREEN}Chat endpoint test completed${NC}"
	# else
	# 	echo -e "${RED}Chat endpoint test failed${NC}"
	# fi
	
	echo -e "\n${GREEN}Testing POST /chat/context?context_request=experiment_5${NC}"
	response=$(curl -s -X POST \
		-b cookies.txt \
		-c cookies.txt \
		--cookie "app_version=0" \
		-H "Content-Type: application/json" \
		-d "$context_data" \
		"${API_URL}/chat/context?context_request=experiment_5")
	
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
		-b cookies.txt \
		-c cookies.txt \
		--cookie "app_version=0" \
		-H "Content-Type: application/json" \
		"${API_URL}/chat/context")
	
	if [ $? -eq 0 ]; then
		echo "Response: $response"
		echo -e "${GREEN}Chat endpoint test completed${NC}"
	else
		echo -e "${RED}Chat endpoint test failed${NC}"
	fi
}

# Function to test /data/context/token_count
test_context_token_count(){	
	echo -e "\n${GREEN}Testing GET /chat/context?context_request=experiment_5${NC}"
	response=$(curl -X GET \
		-b cookies.txt \
		-c cookies.txt \
		--cookie "app_version=0" \
		-H "Content-Type: application/json" \
		"${API_URL}/chat/context?context_request=experiment_5")
	
	if [ $? -eq 0 ]; then
		echo "Response: $response"
		echo -e "${GREEN}Chat endpoint test completed${NC}"
	else
		echo -e "${RED}Chat endpoint test failed${NC}"
	fi
	
}

test_context_clear(){
	echo -e "\n${GREEN}Testing POST /chat/context?context_request=experiment_5&option=clear${NC}"
	context_data='{
		"data_selected": "",
		"prompt_preamble":""
	}'
	
	response=$(curl -s -X POST \
	-b cookies.txt \
	-c cookies.txt \
	--cookie "app_version=0" \
	-H "Content-Type: application/json" \
	-d "$context_data" \
	"${API_URL}/chat/context?context_request=all&option=clear")
	
	if [ $? -eq 0 ]; then
		echo "Response: $response"
		echo -e "${GREEN}Chat endpoint test completed${NC}"
	else
		echo -e "${RED}Chat endpoint test failed${NC}"
	fi
	
}


test_chat() {
	echo -e "\n${GREEN}Testing POST /chat${NC}"
	
	chat_data='{
		"client_query": "The data content describes 311 reports over time to indicate relative health and conditions of the neighborhood, and 911 reports of homicides and shots fired over time indicating incidents of violent crime in the neighborhood. The text content are community meetings and interviews about experiences of safety and voilence in the neighborhood and community meetings discussing community concerns and priorities. Some people think that violence is decreasing, other people still do not feel safe in their neighborhood. Using the data and text content, describe how the two are related and why there is disagreement on the safety of the neighborhood.",		
		"app_version": "0",
		"data_selected": "",
		"data_attributes": ""
	}'
		
	echo -e "\n${GREEN}Testing POST /chat?context_request=experiment_5${NC}"
	response=$(curl -s -X POST \
		-b cookies.txt \
		-c cookies.txt \
		--cookie "app_version=0" \
		-H "Content-Type: application/json" \
		-d "$chat_data" \
		"${API_URL}/chat?context_request=experiment_5")
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
	echo -e "\n${GREEN}Testing POST /log${NC}"

	# Current timestamp in ISO format
	#timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
	log_data='{		
		"data_selected": "NONE",
		"data_attributes": "NONE",
		"client_query": "Test log entry: QUERY",
		"app_response": "Test log entry: RESPONSE",
		"client_response_rating": ""
	}'
	
	response=$(curl -s -X POST \
		-b cookies.txt \
		-c cookies.txt \
		--cookie "app_version=0" \
		-H "Content-Type: application/json" \
		-d "$log_data" \
		"${API_URL}/log")
	
	LOG_ID=$(echo "$response" | jq ".log_id")
	echo $LOG_ID
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
	echo -e "\n${GREEN}Testing POST /log${NC}"
	
	# Current timestamp in ISO format
	#timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
	echo $LOG_ID
	log_data='{
		"log_id": '${LOG_ID}',			
		"client_response_rating": "UPDATED"
	}'
	
	response=$(curl -s -X PUT \
		-b cookies.txt \
		-c cookies.txt \
		--cookie "app_version=0" \
		-H "Content-Type: application/json" \
		-d "$log_data" \
		"${API_URL}/log")

	# Check if curl command was successful
	if [ $? -eq 0 ]; then
		echo "Response: $response"
		echo -e "${GREEN}Log endpoint test completed${NC}"
	else
		echo -e "${RED}Log endpoint test failed${NC}"
	fi
}

# Function to test /data/query?request=
test_data_query() {
	
	ENDPOINTS_OPTIONS=(
		"311_on_date_geo&app_version=5.5&date=2019-02"
		"311_on_date_count&app_version=5.5&date=2020-04"
		"311_on_date_count&app_version=5.5&date=2021-06&zipcode=02121"
		"311_year_month&app_version=5.5"
		"311_by_type&app_version=5.5&category=living_conditions"
		"311_by_type&app_version=5.5&category=trash"
		"311_by_type&app_version=5.5&category=streets"
		"311_by_type&app_version=5.5&category=parking"
		"311_by_type&app_version=5.5&category=all"
		"311_by_total&app_version=5.5&category=living_conditions"
		"311_by_total&app_version=5.5&category=trash"
		"311_by_total&app_version=5.5&category=streets"
		"311_by_total&app_version=5.5&category=parking"
		"311_by_total&app_version=5.5&category=all"
		"311_by_geo&app_version=5.5&category=living_conditions"
		"311_by_geo&app_version=5.5&category=trash"
		"311_by_geo&app_version=5.5&category=streets"
		"311_by_geo&app_version=5.5&category=parking"
		"311_by_geo&app_version=5.5&category=all"
		"911_homicides&app_version=5.5"
		"911_shots_fired&app_version=5.5"
		"911_shots_fired_count_confirmed&app_version=5.5"
		"911_shots_fired_count_unconfirmed&app_version=5.5"
		"911_homicides_and_shots_fired&app_version=5.5"
		"zip_geo&app_version=5.5&zipcode=02121,02115"
	)
	start_time_big=$(perl -MTime::HiRes=time -e 'printf "%.9f", time')
	for endpoint in "${ENDPOINTS_OPTIONS[@]}"; do
		
		echo -e "\n${GREEN}Testing GET /data/query?request=${endpoint}${NC}"
		# Current timestamp in ISO format
		#timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
		# log_data='{
		# 	"log_id": '${LOG_ID}',			
		# 	"client_response_rating": "UPDATED"
		# }'
		#read -p "Press Enter to execute this query (or type 'skip' to skip, 'quit' to exit): " user_input
		start_time=$(perl -MTime::HiRes=time -e 'printf "%.9f", time')		
		
		echo "Timing GET request to: $URL"
		response=$(curl -X GET \
			-b cookies.txt \
			-c cookies.txt \
			--cookie "app_version=0" \
			-H "Content-Type: application/json" \
			-d "$log_data" \
			"${API_URL}/data/query?request=${endpoint}")
		#End timing
		end_time=$(perl -MTime::HiRes=time -e 'printf "%.9f", time')
		
		# Calculate elapsed time
		elapsed=$(echo "$end_time - $start_time" | bc)
		
		# Check if curl command was successful
		if [ $? -eq 0 ]; then
			#echo "Response Length: ${#response}"
			echo "Request completed in ${elapsed} seconds"
			echo -e "${GREEN}Log endpoint test completed${NC}"
		else
			echo -e "${RED}Log endpoint test failed${NC}"
		fi
	done
	end_time_big=$(perl -MTime::HiRes=time -e 'printf "%.9f", time')
	elapsed=$(echo "$end_time_big - $start_time_big" | bc)
	echo "Request completed in ${elapsed} seconds"
}

# Function to test /data/zipcode?request=
test_data_zip() {
	echo -e "\n${GREEN}Testing GET /data/query?request=zip_geo&zipcode=02115${NC}"
	
	# Current timestamp in ISO format
	#timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
	# log_data='{
	# 	"log_id": '${LOG_ID}',			
	# 	"client_response_rating": "UPDATED"
	# }'
	
	response=$(curl -X GET \
		-b cookies.txt \
		-c cookies.txt \
		--cookie "app_version=0" \
		-H "Content-Type: application/json" \
		-d "$log_data" \
		"${API_URL}/data/query?request=zip_geo&zipcode=02121,02115")

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
		test_context_create
		;;
	"context_list")
		test_context_list
		;;
	"context_clear")
		test_context_clear
		;;
	"context_token")
		test_context_token_count
		;;
	"chat")
		test_chat
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
		echo "Usage: $0 [cache_create | cache_list | cache_clear | data | chat | chat_single | log | all]"
		exit 1
		;;
esac
