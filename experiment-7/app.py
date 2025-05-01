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
from datetime import datetime
import plotly.graph_objs as go

load_dotenv()


class Config:
    APP_VERSION = "0.7.0"
    CACHE_DIR = os.getenv("EXPERIMENT_7_CACHE_DIR", "./cache")
    DASH_REQUESTS_PATHNAME = os.getenv("EXPERIMENT_7_DASH_REQUESTS_PATHNAME", "/")
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
    if location_columns:
        # Convert in-place
        df.loc[:, "latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
        df.loc[:, "longitude"] = pd.to_numeric(df["longitude"], errors="coerce")

        # Only after all conversions, filter once
        mask = (df["latitude"] > 40) & (df["latitude"] < 43) & (df["longitude"] > -72) & (df["longitude"] < -70)
        df = df.loc[mask].copy()

    if date_column:
        # Use .loc to avoid the warning while modifying
        df.loc[:, "date"] = pd.to_datetime(df["date"], errors="coerce")
        df.loc[:, "month"] = df["date"].dt.to_period("M").dt.to_timestamp()

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

    headers = {
        "Content-Type": "application/json",
        "RethinkAI-API-Key": Config.RETHINKAI_API_KEY,
    }
    if event_ids:
        response = requests.post(
            f"{Config.API_BASE_URL}/data/query?request=311_summary&category=all&stream=False&app_version={Config.APP_VERSION}&output_type=csv",
            headers=headers,
            json={"event_ids": event_ids},
        )

    elif event_date:
        response = requests.get(
            f"{Config.API_BASE_URL}/data/query?request=311_summary&category=all&stream=False&app_version={Config.APP_VERSION}&date={event_date}&output_type=csv",
            headers=headers,
        )

    response.raise_for_status()
    return response.text


def get_shots_fired_data(force_refresh=False):
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

    df = process_dataframe(df)
    df["ballistics_evidence"] = pd.to_numeric(df["ballistics_evidence"], errors="coerce")
    df["day"] = df["date"].dt.date
    df.dropna(subset=["latitude", "longitude", "date"], inplace=True)

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


def compute_area_category_counts(event_ids: list[str], date_str: str) -> dict[str, int]:
    if not event_ids:
        return {}
    csv_str = get_select_311_data(event_ids=",".join(event_ids), event_date="")
    df_area = pd.read_csv(io.StringIO(csv_str))
    cols = df_area.columns.tolist()
    if "reported_issue" in df_area.columns and "total" in df_area.columns:
        label_col = "reported_issue"
        value_col = "total"
    else:
        label_col, value_col = cols[:2]
    counts = dict(zip(df_area[label_col], df_area[value_col]))
    return counts


def compute_area_shot_count(hex_ids: list[str], shots_geojson: dict) -> int:
    if not hex_ids or not shots_geojson or "features" not in shots_geojson:
        return 0
    count = 0
    for feat in shots_geojson["features"]:
        lon, lat = feat["geometry"]["coordinates"]
        cell = h3.latlng_to_cell(lat, lon, 10)
        if cell in hex_ids:
            count += 1
    return count


app = dash.Dash(
    __name__,
    suppress_callback_exceptions=True,
    serve_locally=False,
    requests_pathname_prefix=Config.DASH_REQUESTS_PATHNAME,
    external_stylesheets=[dbc.themes.BOOTSTRAP, "https://api.mapbox.com/mapbox-gl-js/v2.15.0/mapbox-gl.css"],
    external_scripts=["https://api.mapbox.com/mapbox-gl-js/v2.15.0/mapbox-gl.js"],
    meta_tags=[{"name": "viewport", "content": "width=device-width, initial-scale=1"}],
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


def date_string_to_year_month(date_string: str):
    try:
        date_obj = datetime.strptime(date_string, "%B %Y")
        return date_obj.year, date_obj.month
    except Exception as e:
        print(f"Error parsing date string '{date_string}': {e}")
        return 2024, 12


def get_chat_response(prompt: str, structured_response: bool = False):
    try:
        headers = {
            "Content-Type": "application/json",
            "RethinkAI-API-Key": Config.RETHINKAI_API_KEY,
        }
        response = requests.post(f"{Config.API_BASE_URL}/chat?request=experiment_7&app_version={Config.APP_VERSION}&structured_response={structured_response}", headers=headers, json={"client_query": prompt})
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
                            [
                                html.Div("By The Numbers", id="stats-tab", className="chat-tab active"),
                                html.Div("In Our Words", id="community-tab", className="chat-tab"),
                            ],
                            className="chat-tabs-container",
                        ),
                        html.Div(
                            [
                                html.Div(
                                    className="chat-messages-wrapper",
                                    id="stats-chat-container",
                                    children=[
                                        html.Div(
                                            [
                                                dcc.Graph(
                                                    id="category-pie-chart",
                                                    config={"displayModeBar": False},
                                                ),
                                                html.Div(
                                                    id="shots-count-display",
                                                ),
                                            ],
                                            className="stats-visualization-container",
                                        ),
                                        dcc.Loading(
                                            id="loading-spinner",
                                            type="circle",
                                            color="#701238",
                                            children=html.Div(id="chat-messages", className="chat-messages"),
                                        ),
                                        html.Div(id="loading-output", style={"display": "none"}),
                                    ],
                                ),
                                html.Div(
                                    className="chat-messages-wrapper",
                                    id="community-chat-container",
                                    style={"display": "none"},
                                    children=[
                                        dcc.Loading(
                                            id="loading-spinner-right",
                                            type="circle",
                                            color="#701238",
                                            children=html.Div(id="chat-messages-right", className="chat-messages"),
                                        ),
                                    ],
                                ),
                            ],
                            className="chat-content-container",
                        ),
                        html.Div(
                            [
                                dcc.Input(id="chat-input-combined", type="text", placeholder="What are you trying to understand?", className="chat-input"),
                                html.Button("Tell me more", id="send-button-combined", className="send-btn"),
                            ],
                            className="chat-input-container",
                        ),
                        html.Div(
                            [
                                dcc.Input(id="chat-input", type="text", style={"display": "none"}),
                            ],
                            style={"display": "none"},
                        ),
                        html.Div(
                            [
                                dcc.Input(id="chat-input-right", type="text", style={"display": "none"}),
                                html.Button("", id="send-button-right", style={"display": "none"}),
                            ],
                            style={"display": "none"},
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
        dcc.Store(id="active-tab-store", data="stats"),
        dcc.Store(id="user-message-store"),
        dcc.Store(id="user-message-store-right"),
        dcc.Store(id="window-dimensions", data=json.dumps({"width": 1200, "height": 800})),
        dcc.Store(id="hexbin-position", data=json.dumps({"top": 115, "right": 35, "width": Config.HEXBIN_WIDTH, "height": Config.HEXBIN_HEIGHT})),
        dcc.Store(id="current-date-store", data="December 2024"),
        dcc.Store(id="hexbin-data-store-background"),
        dcc.Store(id="area-category-counts-store"),
        dcc.Store(id="area-shot-count-store"),
        dcc.Store(id="area-homicide-count-store"),
        html.Div(id="background-data-applied", style={"display": "none"}),
        html.Div(id="slider-value-display", className="current-date", style={"display": "none"}),
        dcc.Interval(id="initialization-interval", interval=100, max_intervals=1),
        html.Button(id="refresh-chat-btn", style={"display": "none"}, n_clicks=0),
        html.Button(id="update-date-btn", style={"display": "none"}, **{"data-date": "December 2024"}, n_clicks=0),
    ],
    className="app-container",
)


# Add the middleware to standardize headers
# @app.server.after_request
# def standardize_headers(response):
#     # Remove any existing Connection header
#     if "Connection" in response.headers:
#         del response.headers["Connection"]
#
#     # Set single consistent header
#     response.headers["Connection"] = "keep-alive"
#     return response


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
    prevent_initial_call=True,
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
    function(backgroundData) {
        if (!backgroundData) return '';

        function applyBackgroundData(attempts = 0) {
            if (attempts >= 10) return;

            const beforeMap = window.beforeMap;
            if (!beforeMap || !beforeMap.isStyleLoaded()) {
                setTimeout(() => applyBackgroundData(attempts + 1), 500);
                return;
            }

            const bgSource = beforeMap.getSource('hexDataBackground');
            if (bgSource) {
                bgSource.setData(backgroundData);
                console.log('Background map data applied with',
                    backgroundData.features ? backgroundData.features.length : 0, 'features');
            } else {
                setTimeout(() => applyBackgroundData(attempts + 1), 500);
            }
        }

        applyBackgroundData();
        return '';
    }
    """,
    Output("background-data-applied", "children"),
    Input("hexbin-data-store-background", "data"),
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

app.clientside_callback(
    """
    function(messages) {
        return window.clientside.scrollChat(messages, 'chat-messages');
    }
    """,
    Output("chat-messages", "style", allow_duplicate=True),
    Input("chat-messages", "children"),
    prevent_initial_call=True,
)

app.clientside_callback(
    """
    function(messages) {
        return window.clientside.scrollChat(messages, 'chat-messages-right');
    }
    """,
    Output("chat-messages-right", "style", allow_duplicate=True),
    Input("chat-messages-right", "children"),
    prevent_initial_call=True,
)

app.clientside_callback(
    """
    function(n_refresh, n_date, current_date) {
    if (!n_refresh && !n_date) return '';

    window.iwCounter = window.iwCounter || 0;
    
    const msgs = document.querySelectorAll('.bot-message:not([data-processed="true"])');

    msgs.forEach(msg => {
        // wait for either <p> or our custom headers
        if (!msg.querySelector('p') && !msg.querySelector('.llm-response-header')) return;
        msg.setAttribute('data-processed', 'true');

        // build the collapsible wrapper
        const originalHTML = msg.innerHTML;
        const wrapper = document.createElement('div');
        wrapper.className = 'collapsible-response';

        // Determine if this is in the community tab
        const isCom = !!msg.closest('#community-chat-container');
        
        // Get appropriate label based on tab
        let label;
        if (isCom) {
        // Check if this is a response to a user question or auto-generated
        const responseType = msg.getAttribute('data-response-type');
        
        if (responseType === 'user-question') {
            // This is a response to a user question - use the question as header
            const userQuestion = msg.getAttribute('data-user-question');
            if (userQuestion) {
            // Truncate if too long
            if (userQuestion.length > 60) {
                label = userQuestion.substring(0, 57) + '...';
            } else {
                label = userQuestion;
            }
            } else {
            // Fallback
            label = "What Neighbors Are Saying";
            }
        } else {
            // This is an auto-generated response (from time slider or initial load)
            label = "What Neighbors Are Saying";
        }
        } else {
        // For stats tab, use date
        label = current_date;
        }

        const header = document.createElement('div');
        header.className = 'collapsible-header expanded';
        header.innerHTML =
        '<span class="date-label" style="font-size: 16px; font-weight: bold;">' + label + '</span>' +
        '<span class="toggle-icon">▼</span>';
        header.addEventListener('click', function() {
        this.classList.toggle('expanded');
        const c = this.nextElementSibling;
        c.style.display = c.style.display==='none' ? '' : 'none';
        this.querySelector('.toggle-icon').textContent =
            c.style.display==='none' ? '▶' : '▼';
        });

        // content container
        const content = document.createElement('div');
        content.className = 'collapsible-content';
        content.innerHTML = originalHTML;
        
        // Make sure content is fully visible
        content.style.display = 'block';
        content.style.overflow = 'visible';
        content.style.height = 'auto';

        // ── CATEGORY REMOVAL FOR COMMUNITY TAB ─────────────────────────
        if (isCom) {
        try {
            // Simple approach to remove category headers
            const categoryPatterns = [
            /Living Conditions:[\s\S]*?((?=Trash:|Streets:|Parking:|$))/g,
            /Trash:[\s\S]*?((?=Living Conditions:|Streets:|Parking:|$))/g,
            /Streets:[\s\S]*?((?=Living Conditions:|Trash:|Parking:|$))/g,
            /Parking:[\s\S]*?((?=Living Conditions:|Trash:|Streets:|$))/g
            ];
            
            let contentHTML = content.innerHTML;
            // Apply each pattern
            categoryPatterns.forEach(pattern => {
            contentHTML = contentHTML.replace(pattern, '');
            });
            
            content.innerHTML = contentHTML;
        } catch (e) {
            console.error("Error cleaning categories:", e);
        }
        }
        // ─────────────────────────────────────────────────────────────

        // ── CATEGORY COLORS FOR STATS TAB ─────────────────────────────
        if (!isCom) {
        // your four custom plus re-used burgundy for the fifth
        const sliceColors = [
            '#FFA95A',  // Living Conditions
            '#6987C4',  // Trash
            '#A9A9A9',  // Streets
            '#701238',  // Parking
            '#701238'   // Violent Crime
        ];
        const keys = [
            'living-conditions',
            'trash',
            'streets',
            'parking',
            'violent-crime'
        ];

        keys.forEach((key, idx) => {
            const container = content.querySelector('.llm-response-' + key);
            if (!container) return;

            // gather all nodes until next header
            let node = container.nextSibling;
            const toMove = [];
            while (node && !(node.nodeType===1 && node.classList.contains('llm-response-header'))) {
            toMove.push(node);
            node = node.nextSibling;
            }
            toMove.forEach(n => container.appendChild(n));

            // apply your custom slice color at 10% opacity
            const [r,g,b] = sliceColors[idx].match(/\w\w/g).map(h => parseInt(h,16));
            container.style.backgroundColor = `rgba(${r},${g},${b},0.1)`;
            container.style.padding = '0.5em';
            container.style.borderRadius = '4px';
            container.style.marginBottom = '1em';
          });
        }
        // ─────────────────────────────────────────────────────────────

        wrapper.appendChild(header);
        wrapper.appendChild(content);
        msg.innerHTML = '';
        msg.appendChild(wrapper);
    });

    return '';
    }
    """,
    Output("loading-output", "children"),
    [Input("refresh-chat-btn", "n_clicks"), Input("update-date-btn", "n_clicks")],
    [State("current-date-store", "data")],
)

# — at the very bottom of your app.py, after your other callbacks —

app.clientside_callback(
    """
    function(clickData) {
      // 1) clear any old highlights
      document.querySelectorAll('.llm-response-header').forEach(function(hdr) {
        var box = hdr.nextElementSibling;
        if (box) box.style.boxShadow = '';
      });

      // 2) if nothing clicked, bail
      if (!clickData || !clickData.points || !clickData.points.length) {
        return '';
      }

      // 3) see which slice label was clicked
      var category = clickData.points[0].label;

      // 4) map the exact pie labels → your paragraph keys
      var labelToKey = {
        'Living Conditions':             'living-conditions',
        'Trash, Recycling, And Waste':   'trash',
        'Streets, Sidewalks, And Parks': 'streets',
        'Parking':                        'parking',
        'Violent Crime':                 'violent-crime'
      };
      var key = labelToKey[category];
      if (!key) return '';

      // 5) neon highlight colors per category
      var highlightColors = {
        'living-conditions': 'rgba(255,169,90,0.8)',
        'trash':             'rgba(105,135,196,0.8)',
        'streets':           'rgba(169,169,169,0.8)',
        'parking':           'rgba(112,18,56,0.8)',
        'violent-crime':     'rgba(112,18,56,0.8)'
      };
      var neon = highlightColors[key] || 'rgba(0,200,255,0.8)';

      // 6) find the latest stats message
      var msgs    = document.querySelectorAll('#stats-chat-container .bot-message');
      if (!msgs.length) return '';
      var lastMsg = msgs[msgs.length - 1];

      // 7) if it’s collapsed (header lacks 'expanded'), simulate a click to expand
      var header  = lastMsg.querySelector('.collapsible-header');
      if (header && !header.classList.contains('expanded')) {
        header.click();
      }

      // 8) highlight & scroll the matching paragraph
      var container = lastMsg.querySelector('.llm-response-' + key);
      if (container) {
        container.style.boxShadow = '0 0 15px 5px ' + neon;
        container.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }

      return '';
    }
    """,
    Output("loading-output", "children", allow_duplicate=True),
    Input("category-pie-chart", "clickData"),
    prevent_initial_call=True,
)

app.clientside_callback(
    """
    function(activeTab) {
      const inp = document.querySelector('.chat-input-container');
      if (!inp) return '';
      inp.style.display = activeTab === 'stats' ? 'none' : '';
      return '';
    }
    """,
    Output("dummy-output", "children", allow_duplicate=True),
    Input("active-tab-store", "data"),
    prevent_initial_call="initial_duplicate",
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
        shots_features.append({"type": "Feature", "id": str(row["id"]) if "id" in row else None, "properties": {"id": str(row["id"]) if "id" in row else None}, "geometry": {"type": "Point", "coordinates": [row["longitude"], row["latitude"]]}})
    hom_features = []
    for _, row in homicides_month.iterrows():
        hom_features.append({"type": "Feature", "id": str(row["id"]) if "id" in row else None, "properties": {"id": str(row["id"]) if "id" in row else None}, "geometry": {"type": "Point", "coordinates": [row["longitude"], row["latitude"]]}})
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
        Output("refresh-chat-btn", "n_clicks", allow_duplicate=True),  # Add this output
    ],
    [
        Input("user-message-store", "data"),
        Input("current-date-store", "data"),
    ],
    [
        State("chat-messages", "children"),
        State("selected-hexbins-store", "data"),
        State("refresh-chat-btn", "n_clicks"),
    ],
    prevent_initial_call=True,
)
def handle_chat_response(stored_input, slider_value, current_messages, selected_hexbins_data, refresh_clicks):

    current_messages = current_messages or []
    year, month = date_string_to_year_month(slider_value)
    selected_date = f"{year}-{month:02d}"
    prompt = f"response-type = analytic. Your neighbor has selected the date {selected_date} and wants to understand how the situation " f"in your neighborhood of Dorchester on {selected_date} compares to overall trends..."
    if selected_hexbins_data.get("selected_ids"):
        event_ids = ",".join(selected_hexbins_data["selected_ids"])
        event_id_data = get_select_311_data(event_ids=event_ids)
        event_date_data = get_select_311_data(event_date=selected_date)
        prompt += (
            f"\n\nYour neighbor has specifically selected an area within Dorchester to examine. "
            f"The overall neighborhood 311 data on {selected_date} are: {event_date_data}. "
            f"The specific area 311 data are: {event_id_data}. Compare the local area data, the neighborhood-wide data, "
            f"and the overall trends in the original 311 data."
        )
    # Requesting response for 311 By the Numbers
    reply = get_chat_response(prompt=prompt, structured_response=True)
    bot_response = html.Div([dcc.Markdown(reply, dangerously_allow_html=True)], className="bot-message")
    updated_messages = current_messages + [bot_response]
    refresh_clicks = 0 if refresh_clicks is None else refresh_clicks + 1

    return updated_messages, {"display": "none"}, refresh_clicks


@callback(
    [
        Output("chat-messages-right", "children", allow_duplicate=True),
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
    
    return msgs, {"display": "block"}, input_value.strip()


@callback(
    Output("loading-spinner-right", "style", allow_duplicate=True),
    Input("date-slider-value", "children"),
    prevent_initial_call=True,
)
def show_right_spinner_on_slider_change(slider_value):
    return {"display": "block"}

@callback(
    [
        Output("chat-messages-right", "children", allow_duplicate=True),
        Output("loading-spinner-right", "style", allow_duplicate=True),
        Output("refresh-chat-btn", "n_clicks", allow_duplicate=True),
    ],
    [
        Input("user-message-store-right", "data"),
        Input("current-date-store", "data"),
    ],
    [
        State("chat-messages-right", "children"),
        State("selected-hexbins-store", "data"),
        State("refresh-chat-btn", "n_clicks"),
    ],
    prevent_initial_call=True,
)
def handle_chat_response_right(stored_input, slider_value, msgs, selected, refresh_clicks):
    msgs = msgs or []
    ctx = dash.callback_context
    trigger_id = ctx.triggered[0]['prop_id'] if ctx.triggered else None
    
    year, month = date_string_to_year_month(slider_value)
    selected_date = f"{year}-{month:02d}"
    
    # Determine if this was triggered by a user question or slider change
    is_user_question = stored_input and trigger_id == 'user-message-store-right.data'
    
    # Build prompt based on trigger source
    if is_user_question:
        prompt = f"response-type = community. Your neighbor wants to hear community voices for {selected_date}. Based on the available data, provide insight in a direct and to-the-point manner to your neighbor's question: {stored_input}"
    else:
        prompt = f"response-type = community. Share community voices and concerns from {selected_date}. Write from neighbors' perspectives using first-person quotes. Avoid using category headers like 'Living Conditions:', 'Trash:', etc. Focus on personal testimonials and community sentiment. Provide detailed multi-paragraph responses with several specific examples from community members."

    # Get area context if available  
    area_context = ""
    ids = selected.get("selected_ids", [])
    LIMIT = 150

    if ids:
        limited_ids = ids[:LIMIT]
        evt_csv = get_select_311_data(event_ids=",".join(limited_ids))
        date_csv = get_select_311_data(event_date=selected_date)

        area_context = (
            f"\n\nNeighbors in a specific area reported these issues: {evt_csv}\n\n"
            f"Across the neighborhood on {selected_date}, reports show: {date_csv}"
        )
        
        if len(ids) > LIMIT:
            area_context += f"\n\nNote: This area had {len(ids)} reported concerns, but only {LIMIT} are being considered due to system limits."

        # Add area context to the prompt
        prompt += area_context

    reply = get_chat_response(prompt=prompt, structured_response=False)

    # Add data attributes to the bot message
    bot_msg_attrs = {
        "data-response-type": "user-question" if is_user_question else "auto-generated",
        "data-date": selected_date
    }
    
    # Only add the user question attribute if this is a response to a user question
    if is_user_question:
        bot_msg_attrs["data-user-question"] = stored_input
    
    msgs.append(html.Div(
        dcc.Markdown(reply, dangerously_allow_html=True), 
        className="bot-message",
        **bot_msg_attrs
    ))

    refresh_clicks = 0 if refresh_clicks is None else refresh_clicks + 1

    return msgs, {"display": "none"}, refresh_clicks



@callback(
    [
        Output("overlay", "style", allow_duplicate=True),
        Output("map-section", "className"),
        Output("chat-section-right", "className"),
        Output("chat-input-combined", "autoFocus"),
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
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update

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
        Output("refresh-chat-btn", "n_clicks", allow_duplicate=True),  # Add this output
    ],
    [
        Input("tell-me-trigger", "children"),
    ],
    [
        State("chat-messages", "children"),
        State("refresh-chat-btn", "n_clicks"),
    ],
    prevent_initial_call=True,
)
def handle_tell_me_prompt(prompt, current_messages, refresh_clicks):
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

    refresh_clicks = 0 if refresh_clicks is None else refresh_clicks + 1

    return updated_messages, "", dash.no_update, refresh_clicks


@callback(
    [
        Output("chat-messages", "children", allow_duplicate=True),
        Output("chat-messages-right", "children", allow_duplicate=True),
        Output("refresh-chat-btn", "n_clicks", allow_duplicate=True),
    ],
    [
        Input("tell-me-btn", "n_clicks"),
        Input("selected-hexbins-store", "data"),
    ],
    [
        State("current-date-store", "data"),
        State("refresh-chat-btn", "n_clicks"),
    ],
    prevent_initial_call=True,
)
def handle_initial_prompts(n_clicks, selected, slider_value, refresh_clicks):
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

    stats_prompt = (
        f"response-type = analytic. A by-the-numbers overview for Dorchester on {selected_date}:{area_context} "
        "Your neighbor has selected this specific area to focus on. You don't have to compare the statistics but just analyze the data and give the statistics along with insights. Focus on counts of 311, shots fired, etc."
    )
    stats_reply = get_chat_response(prompt=stats_prompt, structured_response=True)
    stats_message = html.Div(
        [html.Strong("A by-the-numbers overview of your neighborhood:"), dcc.Markdown(stats_reply, dangerously_allow_html=True)], 
        className="bot-message",
        **{
            "data-response-type": "auto-generated",
            "data-date": selected_date
        }
    )

    community_prompt = (
        f"response-type = community. Share voices from {selected_date} community meetings:{area_context} "
        "Write from the perspective of residents using first-person quotes. Avoid using category "
        "headers like 'Living Conditions:', 'Trash:', etc. Focus on personal testimonials and community sentiment. "
        "Provide detailed multi-paragraph responses with several specific examples from community members."
    )
    community_reply = get_chat_response(prompt=community_prompt, structured_response=False)
    community_message = html.Div(
        [html.Strong("From recent community meetings:"), dcc.Markdown(community_reply, dangerously_allow_html=True)], 
        className="bot-message",
        **{
            "data-response-type": "auto-generated",
            "data-date": selected_date
        }
    )
    refresh_clicks = 0 if refresh_clicks is None else refresh_clicks + 1

    return [stats_message], [community_message], refresh_clicks


@callback(
    Output("date-slider-value", "children"),
    Input("update-date-btn", "n_clicks"),
    State("update-date-btn", "data-date"),
    prevent_initial_call=True,
)
def update_date_from_slider(n_clicks, date_value):
    if not date_value:
        raise PreventUpdate
    return date_value


@callback(
    Output("hexbin-data-store-background", "data"),
    Input("initialization-interval", "n_intervals"),
)
def get_all_hexbin_data(_):
    df_all = df_311.copy()

    if df_all.empty:
        return {"type": "FeatureCollection", "features": []}

    resolution = 10
    hex_to_points = {}
    for _, row in df_all.iterrows():
        hex_id = h3.latlng_to_cell(row.latitude, row.longitude, resolution)
        hex_to_points.setdefault(hex_id, []).append(str(row["id"]))

    max_value = max([len(points) for points in hex_to_points.values()]) if hex_to_points else 1
    hex_features = []
    for hex_id, point_ids in hex_to_points.items():
        boundary = h3.cell_to_boundary(hex_id)
        coords = [[lng, lat] for lat, lng in boundary] + [[boundary[0][1], boundary[0][0]]]
        lat_center, lon_center = h3.cell_to_latlng(hex_id)

        count = len(point_ids)
        normalized_value = 1 + (count / max_value) * 9

        hex_features.append({"type": "Feature", "id": hex_id, "properties": {"hex_id": hex_id, "value": normalized_value, "count": count, "lat": lat_center, "lon": lon_center}, "geometry": {"type": "Polygon", "coordinates": [coords]}})

    return {"type": "FeatureCollection", "features": hex_features}


@callback(
    [
        Output("stats-chat-container", "style"),
        Output("community-chat-container", "style"),
        Output("stats-tab", "className"),
        Output("community-tab", "className"),
        Output("active-tab-store", "data"),
    ],
    [
        Input("stats-tab", "n_clicks"),
        Input("community-tab", "n_clicks"),
    ],
    [
        State("active-tab-store", "data"),
    ],
    prevent_initial_call=True,
)
def switch_tabs(stats_clicks, community_clicks, active_tab):
    ctx = dash.callback_context
    if not ctx.triggered:
        return {"display": "block"}, {"display": "none"}, "chat-tab active", "chat-tab", "stats"

    button_id = ctx.triggered[0]["prop_id"].split(".")[0]

    if button_id == "stats-tab":
        return {"display": "block"}, {"display": "none"}, "chat-tab active", "chat-tab", "stats"
    else:
        return {"display": "none"}, {"display": "block"}, "chat-tab", "chat-tab active", "community"


@callback(
    [
        # Add allow_duplicate=True to the first output
        Output("chat-input-combined", "value", allow_duplicate=True),
        Output("chat-input-right", "value", allow_duplicate=True),
        Output("chat-input-right", "n_submit", allow_duplicate=True),
        Output("send-button-right", "n_clicks", allow_duplicate=True),
        Output("loading-spinner", "style", allow_duplicate=True),
        Output("loading-spinner-right", "style", allow_duplicate=True),
    ],
    [
        Input("send-button-combined", "n_clicks"),
        Input("chat-input-combined", "n_submit"),
    ],
    [
        State("chat-input-combined", "value"),
        State("active-tab-store", "data"),
    ],
    prevent_initial_call=True,
)
def handle_combined_chat_input(n_clicks, n_submit, input_value, active_tab):
    ctx = dash.callback_context
    if not ctx.triggered or not input_value or not input_value.strip():
        raise PreventUpdate

    # Always clear the combined input
    left_input = dash.no_update
    right_input = dash.no_update
    right_submit = dash.no_update
    right_clicks = dash.no_update
    left_loading = {"display": "none"}
    right_loading = {"display": "none"}

    if active_tab == "stats":
        left_input = input_value
        left_loading = {"display": "block"}
    else:
        right_input = input_value
        right_submit = 1
        right_clicks = 1
        right_loading = {"display": "block"}

    return "", right_input, right_submit, right_clicks, left_loading, right_loading

@callback(
    [
        Output("chat-input-combined", "value", allow_duplicate=True),
        Output("chat-input-combined", "placeholder"),
    ],
    Input("tell-me-trigger", "children"),
    prevent_initial_call=True,
)
def update_chat_input_from_trigger(trigger_value):
    if trigger_value:
        return "", trigger_value

    return dash.no_update, dash.no_update

@callback(
    Output("area-category-counts-store", "data"),
    [
        Input("selected-hexbins-store", "data"),
        Input("current-date-store", "data"),
    ],
)
def update_category_counts(selected, date_str):
    year, month = date_string_to_year_month(date_str)
    ts = pd.Timestamp(f"{year}-{month:02d}")
    df_month = df_311[df_311["month"] == ts]
    ids = selected.get("selected_ids", [])
    if ids:
        df_month = df_month[df_month["id"].astype(str).isin(ids)]

    counts = df_month["category"].value_counts().to_dict()

    return counts


@callback(
    Output("area-shot-count-store", "data"),
    [
        Input("selected-hexbins-store", "data"),
        Input("current-date-store", "data"),
    ],
)
def update_shot_count(selected, date_str):
    year, month = date_string_to_year_month(date_str)
    ts = pd.Timestamp(f"{year}-{month:02d}")
    df_month = df_shots[df_shots["date"].dt.to_period("M").dt.to_timestamp() == ts]
    hex_ids = selected.get("selected_hexbins", [])
    if not hex_ids:
        total = len(df_month)
        return total

    df_month = df_month.copy()
    df_month["cell"] = df_month.apply(lambda r: h3.latlng_to_cell(r.latitude, r.longitude, 10), axis=1)
    count = df_month[df_month["cell"].isin(hex_ids)].shape[0]
    return count


@callback(
    Output("area-homicide-count-store", "data"),
    [
        Input("selected-hexbins-store", "data"),
        Input("current-date-store", "data"),
    ],
)
def update_homicide_count(selected, date_str):
    year, month = date_string_to_year_month(date_str)
    ts = pd.Timestamp(f"{year}-{month:02d}")
    df_month = df_hom_shot_matched[df_hom_shot_matched["date"].dt.to_period("M").dt.to_timestamp() == ts].copy()

    # build the H3 cells column via list comprehension
    df_month["cell"] = [h3.latlng_to_cell(lat, lon, 10) for lat, lon in zip(df_month["latitude"], df_month["longitude"])]

    hex_ids = selected.get("selected_hexbins", [])
    if hex_ids:
        count = df_month["cell"].isin(hex_ids).sum()
    else:
        count = len(df_month)

    return count


@app.callback(
    Output("category-pie-chart", "figure"),
    Input("area-category-counts-store", "data"),
)
def render_category_pie(counts):
    if not counts:
        return go.Figure(layout={"annotations": [{"text": "No data", "x": 0.5, "y": 0.5, "showarrow": False}]})
    labels = list(counts.keys())
    values = list(counts.values())

    # map each exact string to its color
    color_map = {
        "Streets, Sidewalks, And Parks": "#A9A9A9",
        "Parking": "#701238",
        "Living Conditions": "#FFA95A",
        "Trash, Recycling, And Waste": "#6987C4",
    }
    # build the color list in the same order as labels
    colors = [color_map.get(lbl, "#CCCCCC") for lbl in labels]

    fig = go.Figure(data=[go.Pie(labels=labels, values=values, hole=0.2, sort=False, marker=dict(colors=colors), showlegend=False)])  # preserve order
    fig.update_layout(margin={"l": 0, "r": 0, "t": 0, "b": 0})
    return fig


@callback(
    Output("shots-count-display", "children"),
    [
        Input("area-shot-count-store", "data"),
        Input("area-homicide-count-store", "data"),
    ],
)
def render_counts(shots_count, homicides_count):
    # Create a consistent style for both icons
    bullet_style = {
        "fontSize": "34px",      
        "marginRight": "4px",
        "display": "inline-block",
        "verticalAlign": "middle",
        "lineHeight": "1",
    }
    
    # Create consistent text style
    text_style = {
        "display": "inline-block", 
        "verticalAlign": "middle",
    }
    
    # Create consistent item container style
    item_style = {
        "display": "flex",
        "alignItems": "center", 
        "justifyContent": "center",
        "margin": "0 1rem",
    }

    # Use proper singular/plural forms for shots fired
    shots_text = "Shot Fired" if shots_count == 1 else "Shots Fired"
    
    # Shots fired with consistent styling
    shots_span = html.Div([
        html.Span("• ", style={**bullet_style, "color": "#701238"}),
        html.Span(f"{shots_count} {shots_text}", style=text_style),
    ], style=item_style)
    
    # Initialize items list with shots span
    items = [shots_span]
    
    # Only add homicide count if it's greater than 0
    if homicides_count and homicides_count > 0:
        # Use proper singular/plural forms for homicides
        homicide_text = "Homicide" if homicides_count == 1 else "Homicides"
        
        hom_span = html.Div([
            html.Span("• ", style={**bullet_style, "color": "#000000"}),
            html.Span(f"{homicides_count} {homicide_text}", style=text_style),
        ], style=item_style)
        items.append(hom_span)

    return html.Div(
        html.Div(
            items,
            style={
                "backgroundColor": "white",
                "padding": "8px 15px",
                "borderRadius": "20px",
                "display": "flex",
                "alignItems": "center",
                "justifyContent": "center",
                "boxShadow": "0 1px 3px rgba(0,0,0,0.1)",
            }
        ),
        style={
            "display": "flex",
            "justifyContent": "center",
            "alignItems": "center",
            "marginTop": "0.5rem",
            "fontSize": "16px",
        }
    )

server = app.server

# Run the app
if __name__ == "__main__":
    app.run(debug=True)
