#!/bin/bash

# Configuration
#API_URL="http://127.0.0.1:8888"
API_URL="https://boston.ourcommunity.is/api"
APP_VERSION="test.x"
COOKIE_FILE="cookies.txt"
RETHINKAI_API_KEY=<rethink api key>

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
	echo $data
	local response
	if [ -n "$data" ]; then
		response=$(curl -s -X "$method" \
			-b "$COOKIE_FILE" \
			-c "$COOKIE_FILE" \
			-H "Content-Type: application/json" \
			-H "RethinkAI-API-Key: $RETHINKAI_API_KEY" \
			-d "$data" \
			"${API_URL}${endpoint}" $additional_args)
	else
		response=$(curl -s -X "$method" \
			-b "$COOKIE_FILE" \
			-c "$COOKIE_FILE" \
			-H "Content-Type: application/json" \
			-H "RethinkAI-API-Key: $RETHINKAI_API_KEY" \
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
	local context_type="${1:-experiment_7}"
	local context_data='{
		"data_selected": "",
		"prompt_preamble":""
	}'

	local endpoint="/chat/context?context_request=${context_type}&app_version=${APP_VERSION}&output_type=csv"
	make_request "POST" "$endpoint" "$context_data"
}

test_context_list() {
	local endpoint="/chat/context?app_version=${APP_VERSION}"
	make_request "GET" "$endpoint"
}

test_context_token_count() {
	local context_type="${1:-experiment_7}"
	local endpoint="/chat/context?context_request=${context_type}&app_version=${APP_VERSION}&output_type=csv"
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
	local context_type="${1:-experiment_7}"
	local endpoint="/chat?context_request=${context_type}&app_version=${APP_VERSION}&structured_response=True"

	local chat_data='{
		"client_query": "Your neighbor has selected the date June 2021 and wants to understand how the situation in your neighborhood of Dorchester on June 2021 compares to overall trends...",        
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
		
		"/data/query?request=311_summary&app_version=${APP_VERSION}&category=all&event_ids=883034,890272,1008333&stream=True"
		"/data/query?request=311_summary&app_version=${APP_VERSION}&category=all&date=2019-02&stream=False&output_type=csv"
		"/data/query?request=311_summary&app_version=${APP_VERSION}&category=all&date=2019-02&stream=False&output_type=json"
		"/data/query?request=311_summary&app_version=${APP_VERSION}&category=all&stream=True"
				
		"/data/query?request=911_shots_fired&app_version=${APP_VERSION}&stream=True"
		"/data/query?request=911_homicides_and_shots_fired&app_version=${APP_VERSION}&stream=True"
		"/data/query?request=zip_geo&app_version=${APP_VERSION}&zipcode=02121,02115&stream=True"
		
		"/data/query?request=311_summary&category=all&stream=True&app_version=${APP_VERSION}&date=2020-07&output_type=csv"
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

test_data_query_post() {
	
	local endpoint="/data/query?request=311_summary&app_version=${APP_VERSION}&category=all&event_ids=883034,890272,1008333&stream=False&output_type=json"
	
	local data='{
		"event_ids": "1718415,1716303,1707849,1714058,1714546,1714569,1715451,1715530,1721332,1711058,1711056,1712003,1711651,1706282,1712179,1724319,1719586,1708770,1716699,1722741,1721009,1704376,1708386,1719113,1721415,1703298,1703304,1707087,1707259,1708466,1710107,1710356,1711067,1711278,1712834,1712836,1712846,1713876,1714826,1714887,1716167,1716334,1716377,1718783,1718939,1719083,1719921,1720707,1720833,1720850,1720855,1723003,1725640,1713606,1702094,1702104,1702195,1702308,1702309,1702315,1702560,1702588,1702630,1702634,1702858,1703543,1703659,1703701,1703717,1703795,1703972,1704241,1704372,1704399,1704619,1704635,1704685,1704706,1704710,1704757,1704939,1704946,1705262,1705283,1705494,1705495,1705540,1705660,1705774,1706179,1706220,1706422,1706483,1706962,1707042,1707076,1707095,1707157,1707160,1707166,1707233,1707442,1707461,1707507,1707508,1707539,1707593,1707758,1708217,1708264,1708398,1708473,1708510,1709065,1709096,1709292,1709876,1709963,1709966,1710264,1710405,1710857,1710906,1711011,1711028,1711044,1711098,1711173,1711174,1711205,1711314,1711883,1711902,1712751,1712773,1712835,1712887,1713029,1713041,1713062,1713139,1713464,1713963,1713968,1714077,1714448,1714526,1714688,1715450,1715476,1715531,1715635,1715732,1715746,1715807,1715896,1715929,1716024,1716028,1716094,1716143,1716157,1716251,1716309,1716380,1716444,1716583,1716613,1716668,1716709,1717109,1717904,1717965,1717996,1718022,1718025,1718206,1718277,1718286,1718302,1718306,1718943,1718959,1718990,1719087,1719102,1719150,1719238,1719260,1719301,1719484,1720010,1720031,1720080,1720120,1720125,1720311,1720944,1721252,1721481,1721750,1721812,1721886,1721905,1721935,1722084,1722107,1722157,1723659,1723668,1723699,1723723,1723773,1723785,1724081,1724142,1724299,1724336,1725565,1725779,1725782,1725857,1725858,1725887,1725932,1711324,1712045,1712817,1721386,1721443,1722135,1724092,1714405,1702944,1703023,1703312,1703623,1703639,1704623,1704631,1705082,1706855,1707344,1708221,1708263,1708517,1709164,1709182,1709184,1709329,1709336,1709456,1710083,1710085,1710382,1710397,1711164,1711202,1711758,1712747,1712855,1713839,1714810,1715860,1716105,1716373,1716620,1717611,1719002,1719056"
		
	}'
	
	start_time_big=$(perl -MTime::HiRes=time -e 'printf "%.9f", time')
	echo $endpoint
	
	local response=$(make_request "POST" "$endpoint" "$data")
	echo $response
	end_time=$(perl -MTime::HiRes=time -e 'printf "%.9f", time')
	elapsed=$(echo "$end_time - $start_time" | bc)
	echo "Request completed in ${elapsed} seconds"
	

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
	"data_post")
		test_data_query_post
		;;
	"all")
		run_all_tests
		;;
	*)
		echo "Usage: $0 [context_create|context_list|context_clear|context_token|chat|log|zip|data|data_post|all] [optional_context_type]"
		exit 1
		;;
esac
