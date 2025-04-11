import io
import os
import time
import requests
from dotenv import load_dotenv
import pandas as pd
import dash
from dash import html, dcc, Input, Output, State, callback
import dash_bootstrap_components as dbc
from dash.exceptions import PreventUpdate

# from datetime import datetime
# import json

# Configuration constants
load_dotenv()


class Config:
    HOST = os.getenv("EXPERIMENT_6_HOST", "127.0.0.1")
    PORT = os.getenv("EXPERIMENT_6_PORT", "8060")
    DASH_REQUESTS_PATHNAME = os.getenv("EXPERIMENT_6_DASH_REQUESTS_PATHNAME")
    APP_VERSION = os.getenv("EXPERIMETN_6_VERSION", "0.6.x")
    CACHE_DIR = os.getenv("EXPERIMETN_6_CACHE_DIR", "./cache")
    API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8888")


os.makedirs(Config.CACHE_DIR, exist_ok=True)


def cache_stale(path, max_age_minutes=30):
    return not os.path.exists(path) or (time.time() - os.path.getmtime(path)) > max_age_minutes * 60


def stream_to_dataframe(url: str) -> pd.DataFrame:

    with requests.get(url, stream=True) as response:
        if response.status_code != 200:
            raise Exception(f"Error: {response.status_code} - {response.text}")

        json_data = io.StringIO()

        buffer = ""
        in_array = False

        for chunk in response.iter_content(chunk_size=1024, decode_unicode=True):
            if not chunk:
                continue

            buffer += chunk

            # Handle the opening of the JSON array
            if not in_array and "[\n" in buffer:
                in_array = True
                json_data.write("[")
                buffer = buffer.replace("[\n", "")

            # Process complete JSON objects
            while in_array:
                if ",\n" in buffer:
                    obj_end = buffer.find(",\n")
                    obj_text = buffer[:obj_end]

                    json_data.write(obj_text + ",")

                    buffer = buffer[obj_end + 2 :]  # +2 for ",\n"

                elif "\n]" in buffer:
                    obj_end = buffer.find("\n]")
                    obj_text = buffer[:obj_end]

                    if obj_text.strip():
                        json_data.write(obj_text)
                    json_data.write("]")

                    buffer = buffer[obj_end + 2 :]  # +2 for "\n]"
                    in_array = False
                    break

                else:
                    break

        json_data.seek(0)

        try:
            return pd.read_json(json_data, orient="records")
        except Exception as e:
            if "Unexpected end of file" in str(e) or "Empty data passed" in str(e):
                return pd.DataFrame()
            json_str = json_data.getvalue()
            if json_str.strip() and json_str.strip() != "[" and json_str.strip() != "[]":
                try:
                    if not json_str.rstrip().endswith("]"):
                        if json_str.rstrip().endswith(","):
                            json_str = json_str.rstrip()[:-1] + "]"
                        else:
                            json_str += "]"
                    return pd.read_json(io.StringIO(json_str), orient="records")
                except Exception:
                    pass
            # If all recovery attempts fail, raise the original error
            raise


def load_311_data(force_refresh=False):
    cache_path = os.path.join(Config.CACHE_DIR, "df_311.parquet")
    if not force_refresh and not cache_stale(cache_path):
        print("[CACHE] Using cached 311 data")
        return pd.read_parquet(cache_path)

    print("[LOAD] Fetching 311 data from API...")
    url = f"{Config.API_BASE_URL}/data/query?request=311_by_geo&category=all&stream=True&app_version={Config.APP_VERSION}"
    df = stream_to_dataframe(url)

    df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
    df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df.dropna(subset=["latitude", "longitude", "date"], inplace=True)
    df = df[(df["latitude"] > 40) & (df["latitude"] < 43) & (df["longitude"] > -72) & (df["longitude"] < -70)]
    df = df.rename(columns={"normalized_type": "category"})
    df.dropna(subset=["category"], inplace=True)
    df.to_parquet(cache_path, index=False)
    return df


def load_shots_fired_data(force_refresh=False):
    cache_path_shots = os.path.join(Config.CACHE_DIR, "df_shots.parquet")
    cache_path_matched = os.path.join(Config.CACHE_DIR, "df_hom_shot_matched.parquet")

    if not force_refresh and not cache_stale(cache_path_shots) and not cache_stale(cache_path_matched):
        print("[CACHE] Using cached shots + matched data")
        df = pd.read_parquet(cache_path_shots)
        df_matched = pd.read_parquet(cache_path_matched)
        return df, df_matched

    print("[LOAD] Fetching shots fired data from API...")
    url = f"{Config.API_BASE_URL}/data/query?app_version={Config.APP_VERSION}&request=911_shots_fired&stream=True"
    df = stream_to_dataframe(url)

    df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
    df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df.dropna(subset=["latitude", "longitude", "date"], inplace=True)
    df["ballistics_evidence"] = pd.to_numeric(df["ballistics_evidence"], errors="coerce")
    df["month"] = df["date"].dt.to_period("M").dt.to_timestamp()
    df["day"] = df["date"].dt.date

    print("[LOAD] Fetching matched homicides from API...")
    url_matched = f"{Config.API_BASE_URL}/data/query?app_version={Config.APP_VERSION}&request=911_homicides_and_shots_fired&stream=True"
    df_matched = stream_to_dataframe(url_matched)

    df_matched["date"] = pd.to_datetime(df_matched["date"], errors="coerce")
    df_matched.dropna(subset=["latitude", "longitude", "date"], inplace=True)
    df_matched["month"] = df_matched["date"].dt.to_period("M").dt.to_timestamp()

    df.to_parquet(cache_path_shots, index=False)
    df_matched.to_parquet(cache_path_matched, index=False)
    return df, df_matched


df_shots, df_hom_shot_matched = load_shots_fired_data()
df_311 = load_311_data()

########################################

# Initialize the Dash app
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP, "/assets/style.css"], meta_tags=[{"name": "viewport", "content": "width=device-width, initial-scale=1"}])

########################################


# Generate marks for the slider (years with months as minor ticks)
def generate_marks():
    marks = {}
    for year in range(2018, 2025):
        for month in range(1, 13):
            # Mark value is year * 12 + (month - 1)
            # This ensures values are consecutive integers
            value = (year - 2018) * 12 + month - 1

            # Only add labels for January of each year
            if month == 1:
                marks[value] = {"label": f"{year}", "style": {"font-weight": "bold"}}
            else:
                # Minor tick marks for other months (no labels)
                marks[value] = {"label": ""}

    return marks


# Calculate min and max values
min_value = 0  # Jan 2018
max_value = (2024 - 2018) * 12 + 11  # Dec 2024


# Function to convert slider value to year and month
def slider_value_to_date(value):
    # Calculate year and month from slider value
    year = 2018 + (value // 12)
    month = (value % 12) + 1  # 1-based month
    return year, month


# Layout
# CSS for auto-scrolling (limited solution)
app.index_string = """
<!DOCTYPE html>
<html>
    <head>
        {%metas%}
        <title>Rethink AI - Boston Pilot</title>
        {%favicon%}
        {%css%}		
    </head>
    <body>
        {%app_entry%}
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>
    </body>
</html>
"""
app.layout = html.Div(
    [
        # Full-screen overlay
        html.Div(
            [
                html.Div(
                    [
                        html.H2("Your neighbors are worried about rising violence in the neighborhood, but they are working together to improve things and make it safer for everyone.", className="overlay-heading"),
                        html.Div(
                            [
                                html.Button("Show me", id="show-me-btn", className="overlay-btn"),
                                html.Button("Tell me", id="tell-me-btn", className="overlay-btn"),
                                html.Button("Listen to me", id="listen-to-me-btn", className="overlay-btn"),
                            ],
                            className="overlay-buttons",
                        ),
                    ],
                    className="overlay-content",
                ),
                html.Div(id="tell-me-trigger", style={"display": "none"}),
            ],
            id="overlay",
            className="overlay",
        ),
        # Header
        html.Div([html.H1("This is where we are...", className="app-header-title")], className="app-header"),
        # Main container that will handle responsive layout
        html.Div(
            [
                # Left side - Map container
                html.Div(
                    [
                        html.Div(
                            className="chat-messages-wrapper",
                            children=[
                                # Message container
                                html.Div(id="chat-messages", className="chat-messages"),
                                # Spinner positioned inside the messages area
                                html.Div(dcc.Loading(id="loading-spinner", type="circle", children=html.Div(id="loading-output", style={"display": "none"})), className="spinner-container"),
                            ],
                        ),
                        # Chat input and send button
                        html.Div([dcc.Input(id="chat-input", type="text", placeholder="Type your message...", className="chat-input"), html.Button("Send", id="send-button", className="send-btn")], className="chat-input-container"),
                    ],
                    className="chat-main-container",
                    id="chat-section",
                ),
                # Right side - Chat container
                html.Div(
                    [
                        # Map container - placeholder for your map implementation
                        html.Div(id="map-container", className="map-div"),
                        # Date slider (single selector for year-month)
                        html.Div(
                            [html.Div(className="selector-label"), dcc.Slider(id="date-slider", min=min_value, max=max_value, step=1, marks=generate_marks(), value=max_value, included=False), html.Div(id="date-display", className="date-text")],  # Default to last date (Jan 2018)  # No range, just a single point
                            className="slider-container",
                        ),
                    ],
                    className="map-main-container",
                    id="map-section",
                ),
            ],
            className="responsive-container",
        ),
        # Simple div to trigger scrolling
        html.Div(id="scroll-trigger", style={"display": "none"}),
        dcc.Store(id="user-message-store"),
    ],
    className="app-container",
)


# Callback to update the map based on selected date
@callback(Output("map-container", "children"), [Input("date-slider", "value")])
def update_map(slider_value):
    # Convert slider value to year and month
    year, month = slider_value_to_date(slider_value)

    # Format as YYYY-MM
    date_formatted = f"{year}-{month:02d}"

    # Here you would update the map based on the selected date
    # For placeholder purposes:
    return f"Map showing data for: {date_formatted}"


# Callback chain for chat functionality - Part 1: Handle user input and show loading
@callback(
    [Output("chat-messages", "children", allow_duplicate=True), Output("chat-input", "value"), Output("scroll-trigger", "children"), Output("loading-spinner", "style"), Output("user-message-store", "data")],
    [Input("send-button", "n_clicks"), Input("chat-input", "n_submit")],
    [State("chat-input", "value"), State("chat-messages", "children")],
    prevent_initial_call=True,
)
def handle_chat_input(n_clicks, n_submit, input_value, current_messages):
    # Check if callback was triggered
    ctx = dash.callback_context
    if not ctx.triggered:
        raise PreventUpdate

    # Don't do anything if the input is empty
    if not input_value or input_value.strip() == "":
        raise PreventUpdate

    if not current_messages:
        current_messages = []

    # Add user message
    user_message = html.Div(f"{input_value}", className="user-message")
    updated_messages = current_messages + [user_message]

    # Show loading spinner
    spinner_style = {"display": "block"}

    # Trigger scrolling by returning a timestamp
    timestamp = int(time.time())

    # Store user input for part 2
    stored_input = input_value.strip()

    # Clear input, update messages, show spinner
    return updated_messages, "", timestamp, spinner_style, stored_input


# Callback chain for chat functionality - Part 2: Process the request and display bot response
@callback(
    [Output("chat-messages", "children", allow_duplicate=True), Output("loading-spinner", "style", allow_duplicate=True)],
    [Input("user-message-store", "data")],
    [State("chat-messages", "children"), State("date-slider", "value")],
    prevent_initial_call=True,
)
def handle_chat_response(stored_input, current_messages, slider_value):
    if not stored_input:
        raise PreventUpdate

    # Get the date from the slider
    year, month = slider_value_to_date(slider_value)
    selected_date = f"{year}-{month:02d}"

    # Construct the prompt
    prompt = (
        f"The user has selected a subset of the available 311 and 911 data. They are only looking at the data for {selected_date} in the Dorchester neighborhood.\n\n"
        f"Describe the conditions captured in the meeting transcripts and interviews and how those related to the trends seein the 911 and 311 CSV data for "
        f"the date {selected_date}.\n\n"
        f"Point out notable spikes, drops, or emerging patterns in the data for {selected_date}, and connect them to lived experiences and perceptions.\n\n"
        f"Use the grouped 311 categories and the 911 incident data together to provide a holistic, narrative-driven analysis."
        f"Your neighbor's question: {stored_input}"
    )

    try:
        response = requests.post(f"{Config.API_BASE_URL}/chat?request=experiment_5&app_version={Config.APP_VERSION}", headers={"Content-Type": "application/json"}, json={"client_query": prompt})
        response.raise_for_status()
        reply = response.json().get("response", "[No reply received]")
    except Exception as e:
        reply = f"[Error: {e}]"

    # Create bot response
    bot_response = html.Div(
        [
            dcc.Markdown(reply, dangerously_allow_html=True),
        ],
        className="bot-message",
    )

    # Update messages with bot response
    updated_messages = current_messages + [bot_response]

    # Hide spinner
    spinner_style = {"display": "none"}

    return updated_messages, spinner_style


# Callback to hide overlay and focus on appropriate section
@callback(
    [Output("overlay", "style"), Output("map-section", "className"), Output("chat-section", "className"), Output("chat-input", "autoFocus"), Output("tell-me-trigger", "children")],
    [Input("show-me-btn", "n_clicks"), Input("tell-me-btn", "n_clicks"), Input("listen-to-me-btn", "n_clicks")],
    prevent_initial_call=True,
)
def handle_overlay_buttons(show_clicks, tell_clicks, listen_clicks):
    ctx = dash.callback_context
    if not ctx.triggered:
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update

    button_id = ctx.triggered[0]["prop_id"].split(".")[0]

    # Hide the overlay
    overlay_style = {"display": "none"}

    # Default classes
    map_class = "map-main-container"
    chat_class = "chat-main-container"
    auto_focus = False
    tell_me_prompt = None

    # Set focus based on which button was clicked
    if button_id == "show-me-btn":
        map_class = "map-main-container focused"
    elif button_id == "tell-me-btn":
        chat_class = "chat-main-container focused"
        tell_me_prompt = "Give me more details about what issues my neighbors are facing today."
    elif button_id == "listen-to-me-btn":
        chat_class = "chat-main-container focused"
        auto_focus = True

    return overlay_style, map_class, chat_class, auto_focus, tell_me_prompt


@callback([Output("chat-messages", "children", allow_duplicate=True), Output("chat-input", "value", allow_duplicate=True), Output("loading-output", "children", allow_duplicate=True)], [Input("tell-me-trigger", "children")], [State("chat-messages", "children")], prevent_initial_call=True)
def handle_tell_me_prompt(prompt, current_messages):
    if not prompt:
        raise PreventUpdate

    if not current_messages:
        current_messages = []

    try:
        response = requests.post(f"{Config.API_BASE_URL}/chat?request=experiment_5&app_version={Config.APP_VERSION}", headers={"Content-Type": "application/json"}, json={"client_query": prompt})
        response.raise_for_status()
        reply = response.json().get("response", "[No reply received]")
    except Exception as e:
        reply = f"[Error: {e}]"

    # Process the predefined message
    bot_response = html.Div(
        [
            html.Strong("And this is what's going on..."),
            dcc.Markdown(reply, dangerously_allow_html=True),
        ],
        className="bot-message",
    )

    # Update chat with bot response only (no user message since system initiated)
    updated_messages = current_messages + [bot_response]
    # timestamp = int(time.time())
    # Return updated chat
    return updated_messages, "", dash.no_update


########################################
# Run the app
if __name__ == "__main__":
    app.run(host=Config.HOST, port=Config.PORT, debug=True)
