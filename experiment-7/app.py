import io
import os
import time
import json
import requests
import pandas as pd
import h3
import dash
from dash import html, dcc, Input, Output, State, callback, ClientsideFunction
import dash_bootstrap_components as dbc
from dash.exceptions import PreventUpdate
from dotenv import load_dotenv
from dash.dependencies import ClientsideFunction

load_dotenv()


class Config:
    APP_VERSION = "0.7.0"
    CACHE_DIR = os.getenv("EXPERIMENT_6_CACHE_DIR", "./cache")
    API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8888")
    MAPBOX_TOKEN = os.getenv("MAPBOX_TOKEN")
    RETHINKAI_API_KEY = os.getenv("RETHINKAI_API_CLIENT_KEY")
    MAP_CENTER = {"lon": -71.07601, "lat": 42.28988}
    MAP_ZOOM = 13
    HEXBIN_WIDTH = 500
    HEXBIN_HEIGHT = 500


# Create cache directory if it doesn't exist
os.makedirs(Config.CACHE_DIR, exist_ok=True)


def cache_stale(path, max_age_minutes=30):
    """Check if cached file is older than specified minutes"""
    return not os.path.exists(path) or (time.time() - os.path.getmtime(path)) > max_age_minutes * 60


def stream_to_dataframe(url: str) -> pd.DataFrame:
    """Stream JSON data from API and convert to DataFrame"""
    headers = {
        "RethinkAI-API-Key": Config.RETHINKAI_API_KEY,
    }
    with requests.get(url, headers=headers, stream=True) as response:
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
                    buffer = buffer[obj_end + 2 :]
                elif "\n]" in buffer:
                    obj_end = buffer.find("\n]")
                    obj_text = buffer[:obj_end]
                    if obj_text.strip():
                        json_data.write(obj_text)
                    json_data.write("]")
                    buffer = buffer[obj_end + 2 :]
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

            raise


def process_dataframe(df, location_columns=True, date_column=True):
    """Common processing for dataframes with location and date data"""
    df = df.copy()
    if location_columns:
        df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
        df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")
        df = df[(df["latitude"] > 40) & (df["latitude"] < 43) & (df["longitude"] > -72) & (df["longitude"] < -70)]

    if date_column:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df["month"] = df["date"].dt.to_period("M").dt.to_timestamp()

    return df


def get_311_data(force_refresh=False):
    """Load 311 data from cache or API"""
    cache_path = os.path.join(Config.CACHE_DIR, "df_311.parquet")
    if not force_refresh and not cache_stale(cache_path):
        print("[CACHE] Using cached 311 data")
        return pd.read_parquet(cache_path)

    print("[LOAD] Fetching 311 data from API...")
    url = f"{Config.API_BASE_URL}/data/query?request=311_by_geo&category=all&stream=True&app_version={Config.APP_VERSION}"
    df = stream_to_dataframe(url)

    df = process_dataframe(df)
    df = df.rename(columns={"normalized_type": "category"})
    df.dropna(subset=["latitude", "longitude", "date", "category"], inplace=True)

    df.to_parquet(cache_path, index=False)
    return df


def get_select_311_data(event_ids="", event_date=""):

    if event_ids:
        url = f"{Config.API_BASE_URL}/data/query?request=311_summary&category=all&stream=True&app_version={Config.APP_VERSION}&event_ids={event_ids}"
    elif event_date:
        url = f"{Config.API_BASE_URL}/data/query?request=311_summary&category=all&stream=True&app_version={Config.APP_VERSION}&date={event_date}"

    response_df = stream_to_dataframe(url)
    reply = response_df.to_csv(index=False)

    return reply


def get_shots_fired_data(force_refresh=False):
    """Load shots fired data and matched homicides from cache or API"""
    cache_path_shots = os.path.join(Config.CACHE_DIR, "df_shots.parquet")
    cache_path_matched = os.path.join(Config.CACHE_DIR, "df_hom_shot_matched.parquet")

    if not force_refresh and not cache_stale(cache_path_shots) and not cache_stale(cache_path_matched):
        print("[CACHE] Using cached shots + matched data")
        df = pd.read_parquet(cache_path_shots)
        df_matched = pd.read_parquet(cache_path_matched)
        return df, df_matched


# def get_311_data(force_refresh=False):
#     """
#     Always load 311 DataFrame from cache.
#     Returns the same pd.DataFrame your old version did.
#     """
#     cache_path = os.path.join(Config.CACHE_DIR, "df_311.parquet")
#     if not os.path.exists(cache_path):
#         raise FileNotFoundError(f"311 cache missing: {cache_path}")
#     df = pd.read_parquet(cache_path)
#     return df


# def get_shots_fired_data(force_refresh=False):
#     """
#     Always load shots-fired and matched-homicides DataFrames from cache.
#     Returns (df_shots, df_hom_shot_matched) just like before.
#     """
#     cache_shots   = os.path.join(Config.CACHE_DIR, "df_shots.parquet")
#     cache_matched = os.path.join(Config.CACHE_DIR, "df_hom_shot_matched.parquet")

#     missing = [p for p in (cache_shots, cache_matched) if not os.path.exists(p)]
#     if missing:
#         raise FileNotFoundError(f"Shots cache missing: {missing}")

#     df_shots           = pd.read_parquet(cache_shots)
#     df_hom_shot_matched = pd.read_parquet(cache_matched)
#     return df_shots, df_hom_shot_matched


# def get_select_311_data(event_ids="", event_date=""):
#     """
#     Load full 311 cache, filter exactly as the summary endpoints did,
#     then return a CSV string.  Matches your old `reply = ...to_csv(...)`.
#     """
#     df = get_311_data()

#     if event_ids:
#         ids = set(str(i) for i in event_ids.split(",") if i)
#         df = df[df["id"].astype(str).isin(ids)]

#     elif event_date:
#         year, month = map(int, event_date.split("-"))
#         ts = pd.Timestamp(year=year, month=month, day=1)
#         df = df[df["date"].dt.to_period("M").dt.to_timestamp() == ts]

#     reply = df.to_csv(index=False)
#     return reply


    # Load shots fired data
    print("[LOAD] Fetching shots fired data from API...")
    url = f"{Config.API_BASE_URL}/data/query?app_version={Config.APP_VERSION}&request=911_shots_fired&stream=True"
    df = stream_to_dataframe(url)

    df = process_dataframe(df)
    df["ballistics_evidence"] = pd.to_numeric(df["ballistics_evidence"], errors="coerce")
    df["day"] = df["date"].dt.date
    df.dropna(subset=["latitude", "longitude", "date"], inplace=True)

    # Load matched homicides data
    print("[LOAD] Fetching matched homicides from API...")
    url_matched = f"{Config.API_BASE_URL}/data/query?app_version={Config.APP_VERSION}&request=911_homicides_and_shots_fired&stream=True"
    df_matched = stream_to_dataframe(url_matched)

    df_matched = process_dataframe(df_matched)
    df_matched.dropna(subset=["latitude", "longitude", "date"], inplace=True)

    df.to_parquet(cache_path_shots, index=False)
    df_matched.to_parquet(cache_path_matched, index=False)
    return df, df_matched


df_shots, df_hom_shot_matched = get_shots_fired_data()
df_311 = get_311_data()

latest = df_311["date"].max()
max_value = (latest.year - 2018) * 12 + (latest.month - 1)

app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.BOOTSTRAP, "https://api.mapbox.com/mapbox-gl-js/v2.15.0/mapbox-gl.css"],
    external_scripts=["https://api.mapbox.com/mapbox-gl-js/v2.15.0/mapbox-gl.js"],
)


app.index_string = f"""
<!DOCTYPE html>
<html>
    <head>
        {{%metas%}}
        <title>Rethink AI - Boston Pilot</title>
        {{%favicon%}}
        {{%css%}}
        <!-- Include Mapbox GL JS and CSS -->
        <script>
            // Make Mapbox token available to client script
            window.MAPBOX_TOKEN = "{Config.MAPBOX_TOKEN}";
        </script>
    </head>
    <body>
        {{%app_entry%}}
        <footer>
            {{%config%}}
            {{%scripts%}}
            {{%renderer%}}
        </footer>
    </body>
</html>
"""


def date_string_to_year_month(date_string):
    from datetime import datetime

    try:
        date_obj = datetime.strptime(date_string, "%B %Y")
        return date_obj.year, date_obj.month
    except Exception as e:
        print(f"Error parsing date string '{date_string}': {e}")
        return 2024, 12


def get_chat_response(prompt):
    """Get chat response from API"""
    try:
        headers = {
            "Content-Type": "application/json",
            "RethinkAI-API-Key": Config.RETHINKAI_API_KEY,
        }
        response = requests.post(f"{Config.API_BASE_URL}/chat?request=experiment_6&app_version={Config.APP_VERSION}", headers=headers, json={"client_query": prompt})
        response.raise_for_status()
        reply = response.json().get("response", "[No reply received]")
    except Exception as e:
        reply = f"[Error: {e}]"

    return reply


# App layout
app.layout = html.Div(
    [
        html.Div(
            [
                html.Div(
                    [
                        html.H2("Your neighbors are worried about safety in the neighborhood, but they are working to improve things for everyone.", className="overlay-heading"),
                        html.Div(
                            [
                                html.Button("Tell me", id="tell-me-btn", className="overlay-btn"),
                                html.Button("Show me", id="show-me-btn", className="overlay-btn"),
                                html.Button("Listen to me", id="listen-to-me-btn", className="overlay-btn", style={"display": "none"}),
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
        html.Div(
            [
                html.Div(id="before-map", className="map"),
            ],
            id="background-container",
        ),
        html.Div([html.H1("Rethink our situation", className="app-header-title")], className="app-header"),
        html.Div(
            [
                html.Div(
                    [
                        html.Div(
                            className="chat-messages-wrapper",
                            children=[
                                dcc.Loading(
                                    id="loading-spinner",
                                    type="circle",
                                    color="#701238",
                                    style={
                                        "position":       "static",   
                                        "background":     "transparent", 
                                        "pointerEvents":  "none"      
                                    },
                                    children=html.Div(id="chat-messages", className="chat-messages"),
                                ),
                                html.Div(id="loading-output", style={"display": "none"}),
                            ],
                        ),
                        html.Div(
                            [
                                dcc.Input(id="chat-input", type="text", placeholder="What are you trying to understand?", className="chat-input"),
                            ],
                            className="chat-input-container",
                        ),
                    ],
                    className="chat-main-container",
                    id="chat-section-left",
                ),
                html.Div(
                    [
                        html.Div(
                            [
                                html.Div(
                                    [
                                        html.Div(id="after-map", className="map"),
                                        dcc.Store(id="hexbin-data-store"),
                                        dcc.Store(id="shots-data-store"),
                                        dcc.Store(id="homicides-data-store"),
                                        dcc.Store(id="selected-hexbins-store", data={"selected_hexbins": [], "selected_ids": []}),
                                        html.Div(
                                            id="date-display",
                                            style={"display": "none"},
                                        ),
                                        html.Div(id="dummy-output", style={"display": "none"}),
                                        html.Button(id="map-move-btn", style={"display": "none"}, **{"data-hexids": "", "data-ids": ""}),
                                    ],
                                    id="magnifier-container",
                                    className="map-container",
                                    style={
                                        # "width": f"{Config.HEXBIN_WIDTH+100}px",
                                        # "height": f"{Config.HEXBIN_HEIGHT+100}px",
                                    },
                                ),
                                html.Div("December 2024", id="date-slider-value", style={"display": "none"}),
                                html.Div([html.Div(id="slider")], className="slider-container"),
                                html.Div([html.Div(id="slider-shadow")], className="slider-container-shadow"),
                            ],
                            className="map-controls",
                        ),
                    ],
                    id="map-section",
                    className="map-section-container",
                ),
                html.Div(
                    [
                        html.Div(
                            className="chat-messages-wrapper",
                            children=[
                                dcc.Loading(
                                    id="loading-spinner-right",
                                    type="circle",
                                    color="#701238",
                                    style={
                                        "position":       "static",   
                                        "background":     "transparent", 
                                        "pointerEvents":  "none"      
                                    },
                                    children=html.Div(id="chat-messages-right", className="chat-messages"),
                                )
                            ],
                        ),
                        html.Div(
                            [
                                dcc.Input(id="chat-input-right", type="text", placeholder="What are you trying to understand?", className="chat-input"),
                                html.Button("Tell me more", id="send-button-right", className="send-btn"),
                            ],
                            className="chat-input-container",
                        ),
                    ],
                    className="chat-main-container",
                    id="chat-section-right",
                ),
            ],
            id="responsive-container",
        ),
        html.Div(id="scroll-trigger", style={"display": "none"}),
        html.Div(id="hide-overlay-value", style={"display": "none"}),
        dcc.Interval(id="hide-overlay-trigger", interval=1300, n_intervals=0, max_intervals=0),
        dcc.Store(id="user-message-store"),
        dcc.Store(id="user-message-store-right"),
        dcc.Store(id="window-dimensions", data=json.dumps({"width": 1200, "height": 800})),
        dcc.Store(id="hexbin-position", data=json.dumps({"top": 115, "right": 35, "width": Config.HEXBIN_WIDTH, "height": Config.HEXBIN_HEIGHT})),
        dcc.Store(id="current-date-store", data="December 2024"),
        html.Div(id="slider-value-display", className="current-date", style={"display": "none"}),
        dcc.Interval(id="initialization-interval", interval=100, max_intervals=1),
        html.Button(id="refresh-chat-btn", style={"display": "none"}),
        html.Button(
            id="update-date-btn", 
            style={"display": "none"}, 
            **{"data-date": "December 2024"},
            n_clicks=0  
        ),
    ],
    className="app-container",
)

# Initialize the slider when the page loads
app.clientside_callback(
    ClientsideFunction(namespace="clientside", function_name="initializeSlider"),
    Output("slider", "children"),
    Input("initialization-interval", "n_intervals"),
)

app.clientside_callback(
    """
    function() {
        const currentDateDisplay = document.querySelector('.current-date');
        if (currentDateDisplay) {
            return currentDateDisplay.textContent;
        }
        return "December 2024"; 
    }
    """,
    Output("current-date-store", "data"),
    Input("update-date-btn", "n_clicks"),
    prevent_initial_call=True
)


app.clientside_callback(
    ClientsideFunction(namespace="clientside", function_name="updateMapData"),
    Output("dummy-output", "children"),
    Input("hexbin-data-store", "data"),
    Input("shots-data-store", "data"),
    Input("homicides-data-store", "data"),
)


app.clientside_callback(
    """
    function(n_clicks) {
      if (!n_clicks) {
        return window.latestSelection || {'selected_hexbins': [], 'selected_ids': []};
      }
      const btn = document.getElementById('map-move-btn');
      if (!btn) { return {'selected_hexbins': [], 'selected_ids': []}; }
      const hexids = btn.getAttribute('data-hexids') || "";
      const ids    = btn.getAttribute('data-ids')    || "";
      const hexList = hexids ? hexids.split(',') : [];
      const idList  = ids    ? ids.split(',')    : [];
      window.latestSelection = {'selected_hexbins': hexList, 'selected_ids': idList};
      return window.latestSelection;
    }
    """,
    Output("selected-hexbins-store", "data"),
    Input("map-move-btn", "n_clicks"),
)


@app.callback(Output("slider-value-display", "children"), Input("date-slider-value", "children"))
def update_slider_display(date_value):
    return date_value


@callback(
    Output("date-display", "children"),
    Input("date-slider-value", "children"),
)
def update_date_display(value):
    year, month = date_string_to_year_month(value)
    return f"{year}-{month:02d}"


@callback(
    [
        Output("hexbin-data-store", "data"),
        Output("shots-data-store", "data"),
        Output("homicides-data-store", "data"),
    ],
    Input("current-date-store", "data"),
)
def update_map_data(date_value):
    year, month = date_string_to_year_month(date_value)
    selected_month = pd.Timestamp(f"{year}-{month:02d}")
    df_month = df_311[df_311["month"] == selected_month]

    shots_month = df_shots[df_shots["date"].dt.to_period("M").dt.to_timestamp() == selected_month]
    homicides_month = df_hom_shot_matched[df_hom_shot_matched["date"].dt.to_period("M").dt.to_timestamp() == selected_month]

    if df_month.empty:
        return {"type": "FeatureCollection", "features": []}, None, None

    resolution = 10
    hex_to_points = {}
    for _, row in df_month.iterrows():
        hex_id = h3.latlng_to_cell(row.latitude, row.longitude, resolution)
        hex_to_points.setdefault(hex_id, []).append(str(row["id"]))

    hex_features = []
    for hex_id, point_ids in hex_to_points.items():
        boundary = h3.cell_to_boundary(hex_id)
        coords = [[lng, lat] for lat, lng in boundary] + [[boundary[0][1], boundary[0][0]]]
        lat_center, lon_center = h3.cell_to_latlng(hex_id)
        hex_features.append({"type": "Feature", "id": hex_id, "properties": {"hex_id": hex_id, "value": len(point_ids), "lat": lat_center, "lon": lon_center, "ids": point_ids}, "geometry": {"type": "Polygon", "coordinates": [coords]}})

    hex_data = {"type": "FeatureCollection", "features": hex_features}

    shots_features = []
    for _, row in shots_month.iterrows():
        shots_features.append({"type": "Feature", "id": str(row["id"]) if "id" in row else None,
                              "properties": {"id": str(row["id"]) if "id" in row else None},
                              "geometry": {"type": "Point", "coordinates": [row["longitude"], row["latitude"]]}})
    hom_features = []
    for _, row in homicides_month.iterrows():
        hom_features.append({"type": "Feature", "id": str(row["id"]) if "id" in row else None,
                             "properties": {"id": str(row["id"]) if "id" in row else None},
                              "geometry": {"type": "Point", "coordinates": [row["longitude"], row["latitude"]]}})
    shots_data = {"type": "FeatureCollection", "features": shots_features}
    homicides_data = {"type": "FeatureCollection", "features": hom_features}

    return hex_data, shots_data, homicides_data


@callback(
    Output("loading-spinner", "style", allow_duplicate=True),
    Input("date-slider-value", "children"),
    prevent_initial_call=True,
)
def show_left_spinner_on_slider_change(slider_value):
    return {"display": "block"}


@callback(
    [
        Output("chat-messages", "children", allow_duplicate=True),
        Output("loading-spinner", "style", allow_duplicate=True),
    ],
    [
        Input("user-message-store", "data"),
        Input("date-slider-value", "children"),
    ],
    [
        State("chat-messages", "children"),
        State("selected-hexbins-store", "data"),
    ],
    prevent_initial_call=True,
)
def handle_chat_response(stored_input, slider_value, current_messages, selected_hexbins_data):

    current_messages = current_messages or []
    year, month = date_string_to_year_month(slider_value)
    selected_date = f"{year}-{month:02d}"
    prompt = f"Your neighbor has selected the date {selected_date} and wants to understand how the situation " f"in your neighborhood of Dorchester on {selected_date} compares to overall trends..."
    if selected_hexbins_data.get("selected_ids"):
        event_ids = ",".join(selected_hexbins_data["selected_ids"])
        event_id_data = get_select_311_data(event_ids=event_ids)
        event_date_data = get_select_311_data(event_date=selected_date)
        prompt += f"\n\nYour neighbor has specifically selected an area within Dorchester to examine. " f"The overall neighborhood 311 data on {selected_date} are: {event_date_data}. " f"The specific area 311 data are: {event_id_data}. Compare the local area data, the neighborhood-wide data, " f"and the overall trends in the original 311 data."
    if stored_input:
        prompt += f"\n\nThe neighbor asks: {stored_input}"
    reply = get_chat_response(prompt)
    bot_response = html.Div([dcc.Markdown(reply, dangerously_allow_html=True)], className="bot-message")
    updated_messages = current_messages + [bot_response]
    return updated_messages, {"display": "none"}


@callback(
    [
        Output("chat-messages-right", "children", allow_duplicate=True),
        Output("chat-input-right", "value"),
        Output("loading-spinner-right", "style", allow_duplicate=True),
        Output("user-message-store-right", "data"),
    ],
    [
        Input("send-button-right", "n_clicks"),
        Input("chat-input-right", "n_submit"),
    ],
    [
        State("chat-input-right", "value"),
        State("chat-messages-right", "children"),
    ],
    prevent_initial_call=True,
)
def handle_chat_input_right(n_clicks, n_submit, input_value, msgs):
    ctx = dash.callback_context
    if not ctx.triggered or not input_value or not input_value.strip():
        raise PreventUpdate
    msgs = msgs or []
    msgs.append(html.Div(input_value, className="user-message"))
    return msgs, "", {"display": "block"}, input_value.strip()


@callback(
    Output("loading-spinner-right", "style", allow_duplicate=True),
    Input("date-slider-value", "children"),
    prevent_initial_call=True,
)
def show_right_spinner_on_slider_change(slider_value):
    return {"display": "block"}


@callback(
    [Output("chat-messages-right", "children", allow_duplicate=True), Output("loading-spinner-right", "style", allow_duplicate=True)],
    [Input("user-message-store-right", "data"), Input("date-slider-value", "children")],
    [State("chat-messages-right", "children"), State("selected-hexbins-store", "data")],
    prevent_initial_call=True,
)
def handle_chat_response_right(stored_input, slider_value, msgs, selected):
    msgs = msgs or []

    year, month = date_string_to_year_month(slider_value)
    selected_date = f"{year}-{month:02d}"
    if stored_input:
        question = stored_input
    else:
        question = f"What were the main concerns in the community around {selected_date}?"

    prompt = f"Your neighbor wants community insights for {selected_date}. Based on meeting transcripts, what were the main concerns?\n\n{question}"

    reply = get_chat_response(prompt)

    msgs.append(html.Div(dcc.Markdown(reply, dangerously_allow_html=True), className="bot-message"))

    return msgs, {"display": "none"}


@callback(
    [
        Output("overlay", "style", allow_duplicate=True),
        Output("map-section", "className"),
        Output("chat-section-left", "className"),
        Output("chat-input", "autoFocus"),
        Output("tell-me-trigger", "children"),
        Output("hide-overlay-trigger", "max_intervals", allow_duplicate=True),
    ],
    [
        Input("show-me-btn", "n_clicks"),
        Input("tell-me-btn", "n_clicks"),
        Input("listen-to-me-btn", "n_clicks"),
    ],
    prevent_initial_call=True,
)
def handle_overlay_buttons(show_clicks, tell_clicks, listen_clicks):
    ctx = dash.callback_context
    if not ctx.triggered:
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update

    button_id = ctx.triggered[0]["prop_id"].split(".")[0]
    overlay_style = {"opacity": "0", "transition": "opacity 1s linear 300ms, opacity 300ms"}
    map_class = "map-main-container"
    chat_class = "chat-main-container"
    auto_focus = False
    tell_me_prompt = None

    if button_id == "show-me-btn":
        map_class = "map-main-container focused"
    elif button_id == "tell-me-btn":
        chat_class = "chat-main-container focused"
        tell_me_prompt = "Give me more details about what issues my neighbors are facing today."
    elif button_id == "listen-to-me-btn":
        chat_class = "chat-main-container focused"
        auto_focus = True

    return overlay_style, map_class, chat_class, auto_focus, tell_me_prompt, 1


@callback(
    [
        Output("overlay", "style", allow_duplicate=True),
        Output("hide-overlay-trigger", "max_intervals", allow_duplicate=True),
    ],
    [
        Input("hide-overlay-trigger", "n_intervals"),
    ],
    prevent_initial_call=True,
)
def complete_overlay_transition(n_intervals):
    if n_intervals > 0:
        return {"display": "none"}, 0
    return dash.no_update, dash.no_update


@callback(
    [
        Output("chat-messages", "children", allow_duplicate=True),
        Output("chat-input", "value", allow_duplicate=True),
        Output("loading-output", "children", allow_duplicate=True),
    ],
    [
        Input("tell-me-trigger", "children"),
    ],
    [
        State("chat-messages", "children"),
    ],
    prevent_initial_call=True,
)
def handle_tell_me_prompt(prompt, current_messages):
    if not prompt:
        raise PreventUpdate

    if not current_messages:
        current_messages = []
    reply = get_chat_response(prompt)
    bot_response = html.Div(
        [
            html.Strong("This is what your neighbors are concerned with:"),
            dcc.Markdown(reply, dangerously_allow_html=True),
        ],
        className="bot-message",
    )
    updated_messages = current_messages + [bot_response]

    return updated_messages, "", dash.no_update


@callback(
    [Output("chat-messages", "children", allow_duplicate=True), Output("chat-messages-right", "children", allow_duplicate=True)],
    [Input("tell-me-btn", "n_clicks"), Input("selected-hexbins-store", "data")],
    [State("date-slider-value", "children")],
    prevent_initial_call=True,
)
def handle_initial_prompts(n_clicks, selected, slider_value):

    if not n_clicks:
        raise PreventUpdate

    year, month = date_string_to_year_month(slider_value)
    selected_date = f"{year}-{month:02d}"

    area_context = ""
    ids = selected.get("selected_ids", [])
    LIMIT = 150

    if ids:
        limited_ids = ids[:LIMIT]
        evt_csv = get_select_311_data(event_ids=",".join(limited_ids))
        date_csv = get_select_311_data(event_date=selected_date)

        area_context = f"\n\nSpecific area 311 data (subset of {LIMIT} records shown):\n{evt_csv}" f"\n\nNeighborhood 311 data for {selected_date}:\n{date_csv}"

        if len(ids) > LIMIT:
            area_context += f"\n\nNote: This area had {len(ids)} events, but only {LIMIT} are analyzed due to system limits."

    stats_prompt = f"Statistical overview for Dorchester on {selected_date}:{area_context} " "Your neighbor has selected this specific area to focus on. You don't have to compare the statistics but just analyze the data and give the statistics along with insights. Focus on counts of 311, shots fired, etc."
    stats_reply = get_chat_response(stats_prompt)
    stats_message = html.Div([html.Strong("Statistical overview for your neighborhood:"), dcc.Markdown(stats_reply, dangerously_allow_html=True)], className="bot-message")

    community_prompt = f"Community meeting summary for {selected_date}:{area_context} " "Your neighbor has selected this specific area to focus on. Share neighbor quotes and concerns."
    community_reply = get_chat_response(community_prompt)
    community_message = html.Div([html.Strong("From recent community meetings:"), dcc.Markdown(community_reply, dangerously_allow_html=True)], className="bot-message")

    return [stats_message], [community_message]

@callback(
    Output("date-slider-value", "children"),
    Input("update-date-btn", "n_clicks"),
    State("update-date-btn", "data-date"),
    prevent_initial_call=True
)
def update_date_from_slider(n_clicks, date_value):
    if not date_value:
        raise PreventUpdate
    return date_value


server = app.server

# Run the app
if __name__ == "__main__":
    app.run(debug=True)
