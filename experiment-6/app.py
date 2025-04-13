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
import plotly.graph_objects as go
import plotly.express as px
import h3
import json

# Load environment variables
load_dotenv()


class Config:
    HOST = os.getenv("EXPERIMENT_6_HOST", "127.0.0.1")
    PORT = os.getenv("EXPERIMENT_6_PORT", "8060")
    DASH_REQUESTS_PATHNAME = os.getenv("EXPERIMENT_6_DASH_REQUESTS_PATHNAME")
    APP_VERSION = os.getenv("EXPERIMENT_6_VERSION", "0.6")  # Fixed typo
    CACHE_DIR = os.getenv("EXPERIMENT_6_CACHE_DIR", "./cache")
    API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8888")
    MAPBOX_TOKEN = os.getenv("MAPBOX_TOKEN")
    # MAP_CENTER = dict(lon=-71.07, lat=42.297)
    MAP_CENTER = dict(lon=-71.07601, lat=42.28988)
    MAP_ZOOM = 14  # 12.3
    HEXBIN_WIDTH = 500
    HEXBIN_HEIGHT = 500


# Create cache directory if it doesn't exist
os.makedirs(Config.CACHE_DIR, exist_ok=True)


def cache_stale(path, max_age_minutes=30):
    """Check if cached file is older than specified minutes"""
    return not os.path.exists(path) or (time.time() - os.path.getmtime(path)) > max_age_minutes * 60


def stream_to_dataframe(url: str) -> pd.DataFrame:
    """Stream JSON data from API and convert to DataFrame"""
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
            # If all recovery attempts fail, raise the original error
            raise


def process_dataframe(df, location_columns=True, date_column=True):
    """Common processing for dataframes with location and date data"""
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
        url = f"{Config.API_BASE_URL}/data/query?request=311_summary_by_id&category=all&stream=True&app_version={Config.APP_VERSION}&event_ids={event_ids}"
    elif event_date:
        url = f"{Config.API_BASE_URL}/data/query?request=311_summary_by_date&category=all&stream=True&app_version={Config.APP_VERSION}&date={event_date}"

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


# Load data
df_shots, df_hom_shot_matched = get_shots_fired_data()
df_311 = get_311_data()

# Initialize the Dash app
app = dash.Dash(__name__, suppress_callback_exceptions=True, external_stylesheets=[dbc.themes.BOOTSTRAP, "/assets/style.css"], meta_tags=[{"name": "viewport", "content": "width=device-width, initial-scale=1"}])

# Define hexbin position
hexbin_position = {"top": 115, "right": 35, "width": Config.HEXBIN_WIDTH, "height": Config.HEXBIN_HEIGHT}


# Helper functions for date slider
def generate_marks():
    """Generate marks for the year-month slider"""
    marks = {}
    for year in range(2018, 2025):
        for month in range(1, 13):
            # Mark value is year * 12 + (month - 1)
            value = (year - 2018) * 12 + month - 1

            if month == 1:
                marks[value] = {"label": f"{year}", "style": {"font-weight": "bold"}}
            else:
                # Minor tick marks for other months (no labels)
                marks[value] = {"label": ""}

    return marks


def slider_value_to_date(value):
    """Convert slider value to year and month"""
    year = 2018 + (value // 12)
    month = (value % 12) + 1  # 1-based month
    return year, month


# Calculate min and max values for slider
min_value = 0  # Jan 2018
max_value = (2024 - 2018) * 12 + 11  # Dec 2024


def get_chat_response(prompt):
    """Get chat response from API"""
    try:
        response = requests.post(f"{Config.API_BASE_URL}/chat?request=experiment_6&app_version={Config.APP_VERSION}", headers={"Content-Type": "application/json"}, json={"client_query": prompt})
        response.raise_for_status()
        reply = response.json().get("response", "[No reply received]")
    except Exception as e:
        reply = f"[Error: {e}]"

    return reply


def calculate_offset(zoom_level, window_width=1200, window_height=800, panel_width=300, panel_height=300, panel_position=None):
    """Calculate longitude/latitude offset based on zoom level and window dimensions"""
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
        pixel_offset_x = panel_center_x - window_center_x - 170

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
initial_window_width = 1200
initial_window_height = 800
initial_offset_data = calculate_offset(Config.MAP_ZOOM, initial_window_width, initial_window_height, Config.HEXBIN_WIDTH, Config.HEXBIN_HEIGHT, hexbin_position)

# Apply the offset to the initial background map center
initial_bg_center = {"lat": Config.MAP_CENTER["lat"] - initial_offset_data["lat"], "lon": Config.MAP_CENTER["lon"] - initial_offset_data["lon"]}


# Layout
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
                        html.H2("Your neighbors are worried about safety in the neighborhood, but they are working to improve things to make it safer for everyone.", className="overlay-heading"),
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
        # Map underlay, tracks zoom/drag of hexbin map
        html.Div(
            [
                dcc.Graph(
                    id="background-map",
                    figure={
                        "data": [
                            # Empty scattermapbox trace to ensure the map renders
                            go.Scattermapbox(lat=[], lon=[], mode="markers", marker={"size": 1}, showlegend=False)
                        ],
                        "layout": {
                            "mapbox": {
                                "accesstoken": Config.MAPBOX_TOKEN,
                                "style": "mapbox://styles/mapbox/light-v11",
                                "center": initial_bg_center,
                                "zoom": Config.MAP_ZOOM,
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
                ),
                html.Div(id="background-filter", style={"position": "absolute", "top": 0, "left": 0, "width": "100%", "height": "100%", "background-color": "rgba(255, 255, 255, 0.6)", "pointer-events": "none"}),
            ],
            id="background-container",
            style={"position": "absolute", "width": "100%", "height": "100vh", "zIndex": -1, "pointerEvents": "none"},
        ),
        # Header
        html.Div([html.H1("Rethink our situation", className="app-header-title")], className="app-header"),
        # Main container for responsive layout
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
                                # Spinner
                                html.Div(dcc.Loading(id="loading-spinner", type="circle", overlay_style={"visibility": "visible", "filter": "blur(2px)"}, color="#701238", children=html.Div(id="loading-output", style={"display": "none"})), className="spinner-container"),
                            ],
                        ),
                        # Chat input and send button
                        html.Div([dcc.Input(id="chat-input", type="text", placeholder="What are you trying to understand?", className="chat-input"), html.Button("Tell me more", id="send-button", className="send-btn")], className="chat-input-container"),
                    ],
                    className="chat-main-container",
                    id="chat-section",
                ),
                # Right side - Map container
                html.Div(
                    [
                        # Map container
                        html.Div(
                            [
                                dcc.Graph(id="hexbin-map", figure={}, style={"height": "100%", "width": "100%"}),
                                dcc.Store(id="hex-to-ids-store", data={}),
                                # Test element - can be removed in production
                                html.Div(id="click-info", style={"position": "absolute", "top": "10px", "right": "10px", "backgroundColor": "white", "padding": "10px", "borderRadius": "5px", "boxShadow": "0 0 10px rgba(0,0,0,0.1)", "zIndex": 1000, "maxHeight": "300px", "overflowY": "auto", "display": "none"}),
                            ],
                            id="map-container",
                            className="map-div",
                        ),
                        # Date slider
                        html.Div(
                            [html.Div(className="selector-label"), dcc.Slider(id="date-slider", min=min_value, max=max_value, step=1, marks=generate_marks(), value=max_value, included=False), html.Div(id="date-display", className="date-text")],
                            className="slider-container",
                        ),
                    ],
                    className="map-main-container",
                    id="map-section",
                ),
            ],
            className="responsive-container",
        ),
        # Helper components
        html.Div(id="scroll-trigger", style={"display": "none"}),
        html.Div(id="hide-overlay-value", style={"display": "none"}),
        dcc.Interval(
            id="hide-overlay-trigger",
            interval=1300,  # milliseconds (1s + 300ms from your transition)
            n_intervals=0,
            max_intervals=0,  # Initially disabled
        ),
        dcc.Store(id="user-message-store"),
        dcc.Store(id="map-state", data=json.dumps({"center": Config.MAP_CENTER, "zoom": Config.MAP_ZOOM})),
        dcc.Store(id="window-dimensions", data=json.dumps({"width": 1200, "height": 800})),
        dcc.Store(id="hexbin-position", data=json.dumps(hexbin_position)),
        dcc.Store(id="selected-hexbins-store", data={"selected_hexbins": [], "selected_ids": []}),
        html.Div(id="window-resize-trigger", style={"display": "none"}),
    ],
    className="app-container",
)


# Clientside callback to track window dimensions
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
        Output("hexbin-map", "figure", allow_duplicate=True),
        Output("hex-to-ids-store", "data"),
        Output("loading-spinner", "style", allow_duplicate=True),
    ],
    [
        Input("date-slider", "value"),
    ],
    [
        State("selected-hexbins-store", "data"),
    ],
    prevent_initial_call="initial_duplicate",
)
def update_map(slider_value, selected_hexbins_data=None):
    # Convert slider value to year and month
    year, month = slider_value_to_date(slider_value)

    # Format as YYYY-MM
    month_str = f"{year}-{month:02d}"
    selected_month = pd.Timestamp(month_str)

    # Filter data for selected month
    df_month = df_311[df_311["date"].dt.to_period("M").dt.to_timestamp() == selected_month]

    # Filter shots and homicides data for the selected month
    shots_month = df_shots[df_shots["date"].dt.to_period("M").dt.to_timestamp() == selected_month]
    homicides_month = df_hom_shot_matched[df_hom_shot_matched["date"].dt.to_period("M").dt.to_timestamp() == selected_month]

    # Create figure
    fig = go.Figure()

    # If no data for the selected month
    if df_month.empty:
        fig.add_annotation(text=f"No data available for {month_str}", showarrow=False, font=dict(size=16))
        return fig, {}, {"display": "none"}

    # Prepare data for hexbin visualization
    id_field = "id"

    # Generate hexagons and aggregate data
    resolution = 10
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
    # Get current selection state
    current_selected = []
    if selected_hexbins_data:
        current_selected = selected_hexbins_data.get("selected_hexbins", [])

    for i, h in enumerate(hex_ids):
        # Get boundary coordinates
        boundary = h3.cell_to_boundary(h)
        # Convert to [lon, lat] format for GeoJSON
        boundary_geojson = [[lng, lat] for lat, lng in boundary]
        # Add first point at the end to close the polygon
        boundary_geojson = [boundary_geojson + [boundary_geojson[0]]]

        # Create feature with ID that matches the index
        hex_polygons.append({"type": "Feature", "id": i, "properties": {"value": hex_values[h], "hex_id": h}, "geometry": {"type": "Polygon", "coordinates": boundary_geojson}})

    # Create properly formatted GeoJSON collection
    geojson = {"type": "FeatureCollection", "features": hex_polygons}

    # Get z values and locations in matching order
    z_values = [hex_values[hex_ids[i]] for i in range(len(hex_ids))]
    locations = list(range(len(hex_ids)))

    # Store hexagon IDs in the same order for customdata
    customdata = hex_ids

    # Create line colors and widths based on selection state
    line_colors = []
    line_widths = []

    for h in hex_ids:
        if h in current_selected:
            line_colors.append("rgba(252, 148, 30, 1)")
            line_widths.append(5)
        else:
            line_colors.append("rgba(255, 255, 255, 0.5)")
            line_widths.append(1)

    # Add choropleth layer
    fig.add_trace(
        go.Choroplethmapbox(
            geojson=geojson,
            locations=locations,
            z=z_values,
            customdata=customdata,
            colorscale=px.colors.sequential.Sunsetdark,
            marker_opacity=0.7,
            marker_line_width=line_widths,
            marker_line_color=line_colors,
            below="",  # Places hexbins BELOW street labels
            showscale=True,
            colorbar=dict(
                title=dict(text="311 Requests", font=dict(size=12, color="grey")),
                orientation="v",
                x=0.005,
                y=0.75,
                xanchor="left",
                yanchor="middle",
                len=0.5,
                thickness=15,
                tickfont=dict(size=10, color="grey"),
                bgcolor="rgba(0,0,0,0)",
            ),
            hoverinfo="none",  # Disable hover
        )
    )

    # Add shots fired scatter plot
    if not shots_month.empty:
        fig.add_trace(
            go.Scattermapbox(
                lat=shots_month["latitude"],
                lon=shots_month["longitude"],
                mode="markers",
                marker=dict(size=15, color="#A43800", opacity=0.9, symbol="circle"),
                name="Shots Fired",
                hoverinfo="none",
                showlegend=True,
                customdata=shots_month["id"] if "id" in shots_month.columns else None,
            )
        )

    # Add homicides scatter plot
    if not homicides_month.empty:
        fig.add_trace(
            go.Scattermapbox(
                lat=homicides_month["latitude"],
                lon=homicides_month["longitude"],
                mode="markers",
                marker=dict(size=15, color="#232E33", opacity=0.9, symbol="circle"),
                name="Homicides",
                hoverinfo="none",
                showlegend=True,
                customdata=homicides_month["id"] if "id" in homicides_month.columns else None,
            )
        )

    # Set up the mapbox layout
    fig.update_layout(
        mapbox=dict(
            style="mapbox://styles/mapbox/light-v11",
            center=Config.MAP_CENTER,
            zoom=Config.MAP_ZOOM,
            accesstoken=Config.MAPBOX_TOKEN,
        ),
        margin={"r": 0, "t": 0, "l": 0, "b": 0},
        autosize=True,
        legend=dict(yanchor="bottom", y=0.07, xanchor="left", x=0, bgcolor="rgba(0,0,0,0)", font=dict(size=12, color="grey")),  # Position at the bottom  # Position at the left
    )

    return fig, hex_to_ids, {"display": "block"}


@app.callback(Output("background-map", "figure"), [Input("hexbin-map", "relayoutData"), Input("hexbin-position", "data"), Input("window-dimensions", "data")], State("background-map", "figure"))
def update_background_map(relayoutData, hexbin_position_json, window_dimensions_json, current_figure):
    # Parse window dimensions and hexbin glass position
    try:
        window_dimensions = json.loads(window_dimensions_json) if window_dimensions_json else {"width": 1200, "height": 800}
        hexbin_position = json.loads(hexbin_position_json) if hexbin_position_json else {"top": 100, "left": 100}

        window_width = window_dimensions.get("width", 1200)
        window_height = window_dimensions.get("height", 800)

        panel_width = hexbin_position.get("width", Config.HEXBIN_WIDTH)
        panel_height = hexbin_position.get("height", Config.HEXBIN_HEIGHT)
    except Exception as e:
        print(f"Error parsing dimensions: {e}")
        window_width = initial_window_width
        window_height = 800
        panel_width = Config.HEXBIN_WIDTH
        panel_height = Config.HEXBIN_HEIGHT

    # Create a copy of the current figure to modify
    new_figure = dict(current_figure)

    # Handle center updates if relayoutData is available
    if relayoutData and "mapbox.center" in relayoutData:
        try:
            # The format can vary, so handle different cases
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

                # Calculate offset
                offset_data = calculate_offset(current_zoom, window_width, window_height, panel_width, panel_height, hexbin_position)

                # Apply the offset to center the background map appropriately
                bg_center = {"lat": hexbin_center["lat"] - offset_data["lat"], "lon": hexbin_center["lon"] - offset_data["lon"]}

                new_figure["layout"]["mapbox"]["center"] = bg_center
        except Exception as e:
            print(f"Error processing center: {e}")

    # Handle zoom updates
    if relayoutData and "mapbox.zoom" in relayoutData:
        new_zoom = max(relayoutData["mapbox.zoom"], 0)
        new_figure["layout"]["mapbox"]["zoom"] = new_zoom

    return new_figure


@callback(
    [
        Output("selected-hexbins-store", "data"),
        Output("hexbin-map", "figure", allow_duplicate=True),
    ],
    [
        Input("hexbin-map", "clickData"),
    ],
    [
        State("hex-to-ids-store", "data"),
        State("click-info", "style"),
        State("selected-hexbins-store", "data"),
        State("hexbin-map", "figure"),
    ],
    prevent_initial_call=True,
)
def handle_hexbin_click(click_data, hex_to_ids, current_style, selected_hexbins_data, current_figure):
    if not click_data:
        return "Click on a hexagon to see data points", current_style, selected_hexbins_data, current_figure

    try:
        # Extract the hexagon ID from the click data
        point_data = click_data["points"][0]
        hex_id = point_data["customdata"]

        # Get current selection state
        current_selected = selected_hexbins_data.get("selected_hexbins", [])
        current_selected_ids = selected_hexbins_data.get("selected_ids", [])

        # Toggle selection state for the clicked hexbin
        if hex_id in current_selected:
            # Remove from selection
            current_selected.remove(hex_id)
            # Remove associated IDs from the global list
            point_ids = hex_to_ids.get(hex_id, [])
            current_selected_ids = [id_val for id_val in current_selected_ids if id_val not in point_ids]
        else:
            # Add to selection
            current_selected.append(hex_id)
            # Add associated IDs to the global list
            point_ids = hex_to_ids.get(hex_id, [])
            current_selected_ids.extend(point_ids)

        # Update selected hexbins data
        updated_hexbins_data = {"selected_hexbins": current_selected, "selected_ids": current_selected_ids}

        # Update figure to show selected hexbins with red outlines
        new_figure = dict(current_figure)

        # Find the choroplethmapbox trace and update marker line colors
        for trace_idx, trace in enumerate(new_figure["data"]):
            if trace.get("type") == "choroplethmapbox":
                # Create a list of line colors based on selection state
                line_colors = []
                line_widths = []

                # Get geojson features and match with hexbin IDs
                features = trace.get("geojson", {}).get("features", [])

                for feature in features:
                    hex_feature_id = feature.get("properties", {}).get("hex_id")
                    if hex_feature_id in current_selected:
                        # Selected hexbins get red outlines and thicker lines
                        line_colors.append("rgba(252, 148, 30, 1)")
                        line_widths.append(5)
                    else:
                        # Unselected hexbins keep original styling
                        line_colors.append("rgba(255, 255, 255, 0.5)")
                        line_widths.append(1)

                # Update the marker line properties in the trace
                new_figure["data"][trace_idx]["marker"]["line"]["color"] = line_colors
                new_figure["data"][trace_idx]["marker"]["line"]["width"] = line_widths

        return updated_hexbins_data, new_figure

    except Exception as e:
        return f"Error processing click data: {str(e)}", current_style, selected_hexbins_data, current_figure


# Callback chain for chat functionality - Part 1: Handle user input and show loading
@callback(
    [
        Output("chat-messages", "children", allow_duplicate=True),
        Output("chat-input", "value"),
        Output("scroll-trigger", "children"),
        Output("loading-spinner", "style"),
        Output("user-message-store", "data"),
    ],
    [
        Input("send-button", "n_clicks"),
        Input("chat-input", "n_submit"),
    ],
    [
        State("chat-input", "value"),
        State("chat-messages", "children"),
    ],
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
    [
        Output("chat-messages", "children", allow_duplicate=True),
        Output("loading-spinner", "style", allow_duplicate=True),
    ],
    [
        Input("user-message-store", "data"),
        Input("date-slider", "value"),
    ],
    [
        State("chat-messages", "children"),
        State("selected-hexbins-store", "data"),
    ],
    prevent_initial_call=True,
)
def handle_chat_response(stored_input, slider_value, current_messages, selected_hexbins_data):
    ctx = dash.callback_context
    triggered_id = ctx.triggered_id

    if not current_messages:
        current_messages = []

    year, month = slider_value_to_date(slider_value)
    selected_date = f"{year}-{month:02d}"

    prompt = f"Your neighbor has selected the date {selected_date} and wants to understand how the situtation in your neighborhood of Dorchester on {selected_date} compares to the overall trends for safety and neighborhood conditionsin in the CSV data and meeting trasncripts. \n\nGive a very brief update – between 5 and 10 sentences - that describes the concerns and conditions in your neighborhood of Dorchester on {selected_date}. Use quotes from the meeting transcripts to illustrate how neighbors are thinking."

    if selected_hexbins_data.get("selected_ids"):
        event_ids = ",".join(str(id) for id in selected_hexbins_data.get("selected_ids"))
        event_id_data = get_select_311_data(event_ids=event_ids)
        event_date_data = get_select_311_data(event_date=selected_date)

        prompt += f"\n\nYour neighbor has specifically selected the following 311 data to examine. There are two additional data sets to consider in your response. \n\nThe first is data describing 311 reports across the neighborhood of Dorchester on the {selected_date}. The summary data by date are:{event_date_data}. \n\nThe other data set is for the 311 reports in specific areas within the Dorchester neighborhood your neighbor has chosen to examine. The specific area data are: {event_id_data}. \n\nCompare the data across these scales: the very local data your neighbor selected, the neighborhood-wide data on the {selected_date}, and the overall trends in the 311 data originally provided."

    if triggered_id == "user-message-store":
        if not stored_input:
            raise PreventUpdate

        # Add user question to prompt
        prompt += f"\n\nWhen constructing your response, be sure to prioritize an answer to the following question your neighbor asked: {stored_input}."

    # Get response from API
    # reply = prompt
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
    [
        Output("overlay", "style", allow_duplicate=True),
        Output("map-section", "className"),
        Output("chat-section", "className"),
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

    # Hide the overlay
    # overlay_style = {"display": "none"}
    overlay_style = {"opacity": "0", "transition": "opacity 1s linear 300ms, opacity 300ms"}
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

    # Get response from API
    reply = get_chat_response(prompt)

    # Process the predefined message
    bot_response = html.Div(
        [
            html.Strong("This is what your neighbors are concerned with:"),
            dcc.Markdown(reply, dangerously_allow_html=True),
        ],
        className="bot-message",
    )

    # Update chat with bot response only (no user message since system initiated)
    updated_messages = current_messages + [bot_response]

    return updated_messages, "", dash.no_update


# Run the app
if __name__ == "__main__":
    app.run(host=Config.HOST, port=Config.PORT, debug=True)
