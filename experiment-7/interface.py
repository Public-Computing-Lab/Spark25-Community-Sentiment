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
import plotly.graph_objects as go

# from plotly.figure_factory import create_hexbin_mapbox
import plotly.express as px

# import numpy as np
import h3
import json

# Configuration constants
load_dotenv()


class Config:
    HOST = os.getenv("EXPERIMENT_6_HOST", "127.0.0.1")
    PORT = os.getenv("EXPERIMENT_6_PORT", "8060")
    DASH_REQUESTS_PATHNAME = os.getenv("EXPERIMENT_6_DASH_REQUESTS_PATHNAME")
    APP_VERSION = os.getenv("EXPERIMETN_6_VERSION", "0.6.x")
    CACHE_DIR = os.getenv("EXPERIMETN_6_CACHE_DIR", "./cache")
    API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8888")
    MAPBOX_TOKEN = os.getenv("MAPBOX_TOKEN")


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
app = dash.Dash(__name__, suppress_callback_exceptions=True, external_stylesheets=[dbc.themes.BOOTSTRAP, "/assets/style.css"], meta_tags=[{"name": "viewport", "content": "width=device-width, initial-scale=1"}])

########################################


# Helper functions
#
# Generate marks for the slider (years with months as minor ticks)
def generate_marks():
    marks = {}
    for year in range(2018, 2025):
        for month in range(1, 13):
            # Mark value is year * 12 + (month - 1)
            # This ensures values are consecutive integers
            value = (year - 2018) * 12 + month - 1

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


# Get chat response from API
def get_chat_response(prompt):
    try:
        response = requests.post(f"{Config.API_BASE_URL}/chat?request=experiment_5&app_version={Config.APP_VERSION}", headers={"Content-Type": "application/json"}, json={"client_query": prompt})
        response.raise_for_status()
        reply = response.json().get("response", "[No reply received]")
    except Exception as e:
        reply = f"[Error: {e}]"

    return reply


# Define map center and zoom level
initial_center = dict(lon=-71.07, lat=42.297)
initial_zoom = 12

hexbin_width = 500
hexbin_height = 500
hexbin_position = {"top": 115, "right": 35, "width": hexbin_width, "height": hexbin_height}


# Function to calculate longitude offset based on zoom level and window width
def calculate_offset(zoom_level, window_width=1200, window_height=800, panel_width=300, panel_height=300, panel_position=None):

    degrees_per_pixel_lon = 360 / (256 * (2**zoom_level))

    degrees_per_pixel_lat = 170 / (256 * (2**zoom_level))

    if panel_position:
        # Calculate horizontal offset
        if "right" in panel_position and "left" not in panel_position:
            left = window_width - panel_position.get("right", 0) - panel_width
        else:
            left = panel_position.get("left", window_width - panel_width - 100)

        # Calculate horizontal offset
        window_center_x = window_width / 2
        panel_center_x = left + (panel_width / 2)
        pixel_offset_x = panel_center_x - window_center_x - 190

        # Calculate vertical offset
        if "bottom" in panel_position and "top" not in panel_position:
            top = window_height - panel_position.get("bottom", 0) - panel_height
        else:
            top = panel_position.get("top", 100)

        # Calculate vertical offset
        window_center_y = window_height / 2
        panel_center_y = top + (panel_height / 2)
        pixel_offset_y = panel_center_y - window_center_y

        # Convert pixel offsets to degrees
        lon_offset = degrees_per_pixel_lon * pixel_offset_x
        lat_offset = degrees_per_pixel_lat * pixel_offset_y

        # Latitude increases northward, but y-coordinates increase downward
        lat_offset = -lat_offset
    else:
        # Default offset calculation when panel position is not available
        pixel_offset_x = (window_width / 2) + 10
        pixel_offset_y = 0

        lon_offset = degrees_per_pixel_lon * pixel_offset_x
        lat_offset = degrees_per_pixel_lat * pixel_offset_y

    return {"lon": lon_offset, "lat": lat_offset, "pixel_x": pixel_offset_x, "pixel_y": pixel_offset_y}


# Use a reasonable default window width for initial load
# Calculate initial offset with reasonable default values for window width
initial_window_width = 1200
initial_window_height = 800
initial_offset_data = calculate_offset(initial_zoom, initial_window_width, initial_window_height, hexbin_width, hexbin_height, hexbin_position)


# Apply the offset to the initial background map center
initial_bg_center = {"lat": initial_center["lat"] - initial_offset_data["lat"], "lon": initial_center["lon"] - initial_offset_data["lon"]}


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
                        html.H2("Your neighbors are worried about safety in the neighborhood, but they are working to improve things and make it safer for everyone.", className="overlay-heading"),
                        html.Div(
                            [
                                html.Button("Tell me", id="tell-me-btn", className="overlay-btn"),
                                html.Button("Show me", id="show-me-btn", className="overlay-btn"),
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
        # Map underlay
        html.Div(
            [
                dcc.Graph(
                    id="background-map",
                    figure={
                        "data": [
                            # Adding an empty scattermapbox trace to ensure the map renders
                            go.Scattermapbox(lat=[], lon=[], mode="markers", marker={"size": 1}, showlegend=False)
                        ],
                        "layout": {
                            "mapbox": {
                                "accesstoken": Config.MAPBOX_TOKEN,
                                "style": "mapbox://styles/mapbox/light-v11",
                                "center": initial_bg_center,  # Use the offset center
                                "zoom": initial_zoom,
                            },
                            "margin": {"l": 0, "r": 0, "t": 0, "b": 0},
                            "uirevision": "no_ui",
                            "dragmode": False,
                            "showlegend": False,
                            "hoverdistance": -1,  # Disable hover
                            "clickmode": "",  # Disable clicking
                        },
                    },
                    config={
                        "displayModeBar": False,
                        "scrollZoom": False,
                        "doubleClick": False,
                        "showTips": False,
                        "responsive": True,
                        "staticPlot": True,  # Makes the plot non-interactive
                    },
                    style={"width": "100%", "height": "100vh"},
                )
            ],
            style={"position": "absolute", "width": "100%", "height": "100vh", "zIndex": -1, "pointerEvents": "none"},
        ),
        # Header
        html.Div([html.H1("This is where we are...", className="app-header-title")], className="app-header"),
        # Main container that will handle responsive layout
        html.Div(
            [
                # Left side - Chat container
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
                # Right side - Map container
                html.Div(
                    [
                        # Map container - placeholder for your map implementation
                        html.Div(
                            [
                                dcc.Graph(id="hexbin-map", figure={}, style={"height": "100%", "width": "100%"}),
                                dcc.Store(id="hex-to-ids-store", data={}),
                                # just for testing, remove later
                                html.Div(id="click-info", style={"position": "absolute", "top": "10px", "right": "10px", "backgroundColor": "white", "padding": "10px", "borderRadius": "5px", "boxShadow": "0 0 10px rgba(0,0,0,0.1)", "zIndex": 1000, "maxHeight": "300px", "overflowY": "auto", "display": "none"}),
                            ],
                            id="map-container",
                            className="map-div",
                        ),
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
        dcc.Store(id="map-state", data=json.dumps({"center": dict(lon=-71.07, lat=42.297), "zoom": 12.3})),
        # Store component to track window dimensions
        dcc.Store(id="window-dimensions", data=json.dumps({"width": 1200, "height": 800})),
        dcc.Store(id="hexbin-position", data=json.dumps(hexbin_position)),
        # Hidden div to track window resize events
        html.Div(id="window-resize-trigger", style={"display": "none"}),
        html.Script(src="https://api.mapbox.com/mapbox-gl-js/v2.14.1/mapbox-gl.js"),
    ],
    className="app-container",
)

app.clientside_callback(
    """
    function(trigger) {
        // Get window dimensions
        const windowWidth = window.innerWidth;
        const windowHeight = window.innerHeight;
        
        // Get hexbin glass element and its dimensions
        const hexbin_map = document.getElementById('hexbin-map');
        if (!hexbin_map) {
            return [
                JSON.stringify({width: windowWidth, height: windowHeight}),
                JSON.stringify({top: 100, right: 100})
            ];
        }
        
        // Calculate position based on its fixed position
        const rect = hexbin_map.getBoundingClientRect();
        const position = {
            top: rect.top,
            left: rect.left,
            right: windowWidth - rect.right,
            bottom: windowHeight - rect.bottom,
            width: rect.width,
            height: rect.height
        };
        
        return [
            JSON.stringify({width: windowWidth, height: windowHeight}),
            JSON.stringify(position)
        ];
    }
    """,
    [Output("window-dimensions", "data"), Output("hexbin-position", "data")],
    Input("window-resize-trigger", "n_clicks"),
)


# Callback to update the map based on selected date
@callback(
    [
        Output("hexbin-map", "figure"),
        Output("hex-to-ids-store", "data"),
        Output("loading-spinner", "style", allow_duplicate=True),
    ],
    [Input("date-slider", "value")],
    prevent_initial_call="initial_duplicate",
)
def update_map(slider_value):
    # Convert slider value to year and month
    year, month = slider_value_to_date(slider_value)

    # Format as YYYY-MM
    month_str = f"{year}-{month:02d}"
    selected_month = pd.Timestamp(month_str)

    df_month = df_311[df_311["date"].dt.to_period("M").dt.to_timestamp() == selected_month]
    hex_to_ids_store = dcc.Store(id="hex-to-ids-store", data={})

    # Create a div to display clicked hexagon data
    click_info_div = html.Div(id="click-info", style={"position": "absolute", "top": "10px", "right": "10px", "backgroundColor": "white", "padding": "10px", "borderRadius": "5px", "boxShadow": "0 0 10px rgba(0,0,0,0.1)", "zIndex": 1000, "maxHeight": "300px", "overflowY": "auto", "display": "none"})  # Hidden initially
    fig = go.Figure()
    if df_month.empty:
        fig.add_annotation(text=f"No data available for {month_str}", showarrow=False, font=dict(size=16))
        map_graph = dcc.Graph(id="hexbin-map", figure=fig, style={"height": "100%", "width": "100%"}, config={"responsive": True, "displayModeBar": False})
        spinner_style = {"display": "none"}
        return html.Div([map_graph, hex_to_ids_store, click_info_div]), spinner_style
    else:
        # Prepare hexbin
        id_field = "id"
        df_month["count"] = 1
        grouped = df_month.groupby(["latitude", "longitude", "category"]).size().reset_index(name="count")
        pivot = grouped.pivot_table(index=["latitude", "longitude"], columns="category", values="count", fill_value=0).reset_index()
        pivot["total_count"] = pivot.drop(columns=["latitude", "longitude"]).sum(axis=1)

        # Generate hexagons and aggregate data
        resolution = 10  # Adjust based on your needs
        hexagons = {}  # For counts
        hex_to_ids = {}  # Map hex_ids to original data point IDs

        for idx, row in df_month.iterrows():
            hex_id = h3.latlng_to_cell(row.latitude, row.longitude, resolution)

            # Store count for choropleth coloring
            if hex_id in hexagons:
                hexagons[hex_id].append(1)  # Count of 1 for each point
                hex_to_ids[hex_id].append(str(row[id_field]))  # Store ID of data point
            else:
                hexagons[hex_id] = [1]
                hex_to_ids[hex_id] = [str(row[id_field])]

        # Calculate sum for each hexagon
        hex_values = {h: sum(vals) for h, vals in hexagons.items()}
        hex_ids = list(hex_values.keys())

        # Create GeoJSON features with proper IDs for choropleth
        hex_polygons = []
        hex_id_to_index = {}  # Map h3 hex_id to feature index

        for i, h in enumerate(hex_ids):
            # Store mapping from h3 hex_id to feature index (for click data lookup)
            hex_id_to_index[h] = i

            # Get boundary coordinates
            boundary = h3.cell_to_boundary(h)
            # Convert to [lon, lat] format for GeoJSON
            boundary_geojson = [[lng, lat] for lat, lng in boundary]
            # Add first point at the end to close the polygon
            boundary_geojson = [boundary_geojson + [boundary_geojson[0]]]

            # Create feature with ID that matches the index
            hex_polygons.append({"type": "Feature", "id": i, "properties": {"value": hex_values[h], "hex_id": h}, "geometry": {"type": "Polygon", "coordinates": boundary_geojson}})  # Store the h3 hex_id for lookup later

        # Create properly formatted GeoJSON collection
        geojson = {"type": "FeatureCollection", "features": hex_polygons}

        # Get z values and locations in matching order
        z_values = [hex_values[hex_ids[i]] for i in range(len(hex_ids))]
        locations = list(range(len(hex_ids)))

        # Store hexagon IDs in the same order for customdata
        customdata = hex_ids

        # Add choropleth layer with hover disabled
        fig.add_trace(
            go.Choroplethmapbox(
                geojson=geojson,
                locations=locations,
                z=z_values,
                customdata=customdata,  # Store hex_ids for click callback
                colorscale=px.colors.sequential.RdPu[::-1],
                marker_opacity=0.7,
                marker_line_width=1,
                marker_line_color="rgba(255, 255, 255, 0.5)",
                below="",  # This places hexbins BELOW all other layers including street labels
                showscale=True,
                colorbar=dict(
                    title="Count",
                    thickness=15,
                    len=0.75,
                    x=0.95,
                ),
                hoverinfo="none",  # Disable hover information
            )
        )

        # Set up the mapbox layout with a style that includes street labels
        fig.update_layout(
            mapbox=dict(
                style="mapbox://styles/mapbox/light-v11",  # Style with street labels on top
                center=dict(lon=-71.07, lat=42.297),  # Center on Boston
                zoom=12.3,
                accesstoken=Config.MAPBOX_TOKEN,
            ),
            margin={"r": 0, "t": 0, "l": 0, "b": 0},
        )

        fig.update_coloraxes(
            colorbar=dict(
                title=dict(text="311 Requests", font=dict(size=12, color="grey")),
                orientation="v",
                x=0,
                y=0.75,
                xanchor="left",
                yanchor="middle",
                len=0.5,
                thickness=12,
                tickfont=dict(size=10, color="grey"),
                bgcolor="rgba(0,0,0,0)",
            ),
        )

    # Make it responsive to container size
    fig.update_layout(autosize=True, height=None, width=None)
    map_graph = dcc.Graph(id="hexbin-map", figure=fig, style={"height": "100%", "width": "100%"}, config={"responsive": True, "displayModeBar": True})  # Let it take the height of the

    spinner_style = {"display": "block"}
    hex_to_ids_store = dcc.Store(id="hex-to-ids-store", data=hex_to_ids)

    return fig, hex_to_ids, spinner_style


@app.callback(Output("background-map", "figure"), [Input("hexbin-map", "relayoutData"), Input("hexbin-position", "data"), Input("window-dimensions", "data")], State("background-map", "figure"))
def update_background_map(relayoutData, hexbin_position_json, window_dimensions_json, current_figure):
    # Parse window dimensions and hexbin glass position
    try:
        window_dimensions = json.loads(window_dimensions_json) if window_dimensions_json else {"width": 1200, "height": 800}
        hexbin_position = json.loads(hexbin_position_json) if hexbin_position_json else {"top": 100, "left": 100}

        window_width = window_dimensions.get("width", 1200)
        window_height = window_dimensions.get("height", 800)

        # If position has right but not left, calculate left
        # if "right" in hexbin_position and "left" not in hexbin_position:
        #     hexbin_position["left"] = window_width - hexbin_position.get("right", 0) - hexbin_position.get("width", 300)

        panel_width = hexbin_position.get("width", hexbin_width)
        panel_height = hexbin_position.get("height", hexbin_height)
    except Exception as e:
        print(f"Error parsing dimensions: {e}")
        window_width = initial_window_width
        window_height = 800
        hexbin_position = hexbin_position
        panel_width = hexbin_width
        panel_height = hexbin_height

    # Create a copy of the current figure to modify
    new_figure = dict(current_figure)

    # Handle center updates if relayoutData is available
    if relayoutData and "mapbox.center" in relayoutData:
        try:
            # The format can vary, so we need to handle different cases
            center_data = relayoutData["mapbox.center"]

            # Check if it's a list/tuple with at least 2 elements
            if isinstance(center_data, (list, tuple)) and len(center_data) >= 2:
                hexbin_center = {"lat": center_data[0], "lon": center_data[1]}
            # If it's already a dict with lat/lon
            elif isinstance(center_data, dict) and "lat" in center_data and "lon" in center_data:
                hexbin_center = center_data
            else:
                # Skip if format is unexpected
                hexbin_center = None

            if hexbin_center:
                # Get current zoom level
                current_zoom = new_figure["layout"]["mapbox"]["zoom"]

                # Use the calculation function with window dimensions and magnifying glass position
                offset_data = calculate_offset(current_zoom, window_width, window_height, panel_width, panel_height, hexbin_position)

                # Apply the offset to center the background map appropriately
                bg_center = {"lat": hexbin_center["lat"] - offset_data["lat"], "lon": hexbin_center["lon"] - offset_data["lon"]}

                new_figure["layout"]["mapbox"]["center"] = bg_center
                print(f"Window: {window_width}x{window_height}, Pixel Offset: ({offset_data['pixel_x']}, {offset_data['pixel_y']})")
                print(f"Degree Offset: (lon: {offset_data['lon']}, lat: {offset_data['lat']})")
                print(f"Magnifying center: {hexbin_center}, Background center: {bg_center}")
        except Exception as e:
            print(f"Error processing center: {e}")

    # Handle zoom updates
    if relayoutData and "mapbox.zoom" in relayoutData:
        new_zoom = max(relayoutData["mapbox.zoom"], 0)
        new_figure["layout"]["mapbox"]["zoom"] = new_zoom

    return new_figure


# Add a callback to handle clicks on hexagons
@callback(
    [Output("click-info", "children"), Output("click-info", "style")],
    [Input("hexbin-map", "clickData")],
    [
        State("hex-to-ids-store", "data"),
        State("click-info", "style"),
    ],
)
def display_click_data(click_data, hex_to_ids, current_style):
    if not click_data:
        return "Click on a hexagon to see data points", current_style

    try:
        # Extract the hexagon ID from the click data
        hex_id = click_data["points"][0]["customdata"]
        count = click_data["points"][0]["z"]

        # Get the data point IDs for this hexagon
        point_ids = hex_to_ids.get(hex_id, [])

        # Create the content to display
        content = [html.H4(f"Hexagon Info", style={"margin-top": "0"}), html.P(f"Total Points: {count}"), html.P("Data Point IDs:"), html.Div([html.Ul([html.Li(id_val) for id_val in point_ids], style={"margin": "0", "padding-left": "20px"})], style={"maxHeight": "200px", "overflowY": "auto"})]

        # Show the info div
        new_style = dict(current_style)
        new_style["display"] = "block"

        return content, new_style

    except Exception as e:
        return f"Error processing click data: {str(e)}", current_style


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
    [Input("user-message-store", "data"), Input("date-slider", "value")],
    [State("chat-messages", "children")],
    prevent_initial_call=True,
)
def handle_chat_response(stored_input, slider_value, current_messages):
    ctx = dash.callback_context
    triggered_id = ctx.triggered_id

    if not current_messages:
        current_messages = []

    year, month = slider_value_to_date(slider_value)
    selected_date = f"{year}-{month:02d}"

    prompt = f"Your neighbor has selected the date {selected_date} and wants to understand how the situtation in your neighborhood of Dorchester on {selected_date} compares to the overall trends for safety and neighborhood conditionsin in the CSV data and meeting trasncripts.\n\n Give a very brief update – between 5 and 10 sentences - that describes the concerns and conditions in your neighborhood of Dorchester on {selected_date}. Use quotes from the meeting transcripts to illustrate how neighbors are thinking."

    if triggered_id == "user-message-store":
        if not stored_input:
            raise PreventUpdate

        # Get the date from the slider
        prompt += f"When constructing your response, be sure to prioritize an answer to the following question your neighbor asked: {stored_input}."

    reply = get_chat_response(prompt)

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

    reply = get_chat_response(prompt)

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
