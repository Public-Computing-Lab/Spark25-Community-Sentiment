import os
import time
import requests
import numpy as np
import pandas as pd
from dotenv import load_dotenv
from dash import Dash, dcc, html, ctx
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate
import plotly.express as px
import plotly.graph_objects as go
from plotly.figure_factory import create_hexbin_mapbox
import io
from shapely.geometry import Point, Polygon
from shapely.ops import unary_union
import math

global_start = time.perf_counter()

load_dotenv()

PORT = os.getenv("EXPERIMENT_5_PORT")
DASH_REQUESTS_PATHNAME = os.getenv("EXPERIMENT_5_DASH_REQUESTS_PATHNAME")
API_BASE_URL = os.getenv("API_BASE_URL")
APP_VERSION = os.getenv("APP_VERSION", "5")

districts = {
    "B3": "rgba(255, 255, 0, 0.7)",
    "B2": "rgba(0, 255, 255, 0.7)",
    "C11": "rgba(0, 255, 0, 0.7)"
}
boston_url = "https://gisportal.boston.gov/ArcGIS/rest/services/PublicSafety/OpenData/MapServer/5/query"

CACHE_DIR = "./cache"
os.makedirs(CACHE_DIR, exist_ok=True)

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
            if not in_array and "[\n" in buffer:
                in_array = True
                json_data.write("[")
                buffer = buffer.replace("[\n", "")
            while in_array:
                if ",\n" in buffer:
                    obj_end = buffer.find(",\n")
                    obj_text = buffer[:obj_end]
                    json_data.write(obj_text + ",")
                    buffer = buffer[obj_end + 2:]
                elif "\n]" in buffer:
                    obj_end = buffer.find("\n]")
                    obj_text = buffer[:obj_end]
                    if obj_text.strip():
                        json_data.write(obj_text)
                    json_data.write("]")
                    buffer = buffer[obj_end + 2:]
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

def load_311_data(force_refresh=False):
    cache_path = os.path.join(CACHE_DIR, "df_311.parquet")
    if not force_refresh and not cache_stale(cache_path):
        print("[CACHE] Using cached 311 data")
        return pd.read_parquet(cache_path)
    print("[LOAD] Fetching 311 data from API...")
    url = f"{API_BASE_URL}/data/query?request=311_by_geo&category=all&stream=True&app_version={APP_VERSION}"
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
    cache_path_shots = os.path.join(CACHE_DIR, "df_shots.parquet")
    cache_path_matched = os.path.join(CACHE_DIR, "df_hom_shot_matched.parquet")
    if not force_refresh and not cache_stale(cache_path_shots) and not cache_stale(cache_path_matched):
        print("[CACHE] Using cached shots + matched data")
        df = pd.read_parquet(cache_path_shots)
        df_matched = pd.read_parquet(cache_path_matched)
        return df, df_matched
    print("[LOAD] Fetching shots fired data from API...")
    url = f"{API_BASE_URL}/data/query?app_version={APP_VERSION}&request=911_shots_fired&stream=True"
    df = stream_to_dataframe(url)
    df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
    df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df.dropna(subset=["latitude", "longitude", "date"], inplace=True)
    df["ballistics_evidence"] = pd.to_numeric(df["ballistics_evidence"], errors="coerce")
    df["month"] = df["date"].dt.to_period("M").dt.to_timestamp()
    df["day"] = df["date"].dt.date
    print("[LOAD] Fetching matched homicides from API...")
    url_matched = f"{API_BASE_URL}/data/query?app_version={APP_VERSION}&request=911_homicides_and_shots_fired&stream=True"
    df_matched = stream_to_dataframe(url_matched)
    df_matched["date"] = pd.to_datetime(df_matched["date"], errors="coerce")
    df_matched.dropna(subset=["latitude", "longitude", "date"], inplace=True)
    df_matched["month"] = df_matched["date"].dt.to_period("M").dt.to_timestamp()
    df.to_parquet(cache_path_shots, index=False)
    df_matched.to_parquet(cache_path_matched, index=False)
    return df, df_matched


df_shots, df_hom_shot_matched = load_shots_fired_data()
df_311 = load_311_data()


available_months = df_shots[(df_shots["month"] >= "2018-01-01") & (df_shots["month"] <= "2024-12-31")]["month"].dropna().sort_values().unique()
month_labels = pd.Series(available_months).dt.strftime("%Y-%m").tolist()
slider_marks = {i: label for i, label in enumerate(month_labels) if i % 3 == 0}
category_colors = {
    "Living Conditions": "#ff7f0e",
    "Trash, Recycling, And Waste": "#2ca02c",
    "Streets, Sidewalks, And Parks": "#9467bd",
    "Parking": "#FFC0CB",
}

initial_index = 0
for i, m in enumerate(available_months):
    if not df_311[df_311["date"].dt.to_period("M").dt.to_timestamp() == m].empty:
        initial_index = i
        break


chat_history = [
    (
        "Assistant",
        """**City Safety and Service Trends: January 2018**

**Overview:** January 2018 saw a typical seasonal uptick in 311 service requests related to winter weather and its impact on living conditions, trash collection, and street maintenance. However, concerning spikes in 911 incidents involving gun violence cast a shadow over otherwise expected trends.

**311 Service Requests:**
* **Living Conditions:** Requests for this category were elevated, likely due to heating issues and building maintenance challenges exacerbated by cold weather. This trend directly impacts resident quality of life, potentially increasing risks for vulnerable populations.
* **Trash/Recycling/Waste:** Requests saw a minor increase, possibly attributable to holiday waste accumulation and weather-related collection delays. This impacts neighborhood cleanliness and can contribute to resident dissatisfaction.
* **Streets/Sidewalks/Parks:** Requests significantly spiked, driven by snow removal needs, icy conditions, and pothole formation. This directly impacts pedestrian and vehicle safety, highlighting the need for timely and efficient winter street maintenance.
* **Parking:** Requests were high, likely due to snow-related parking restrictions and limited space availability. This adds stress for residents already navigating challenging winter conditions.

**911 Incident Data:**
* **Homicides:** While the overall number remains relatively low, two homicides occurring in January represent a concerning start to the year and warrant further investigation into potential causes and contributing factors.
* **Shots Fired:** Both confirmed and unconfirmed reports of shots fired were notably high in January, indicating a significant spike in gun violence. This trend raises serious concerns for neighborhood safety and necessitates a proactive response from law enforcement and community organizations.

**Key Implications:**
* While January typically sees increased 311 requests due to winter weather, the city must ensure efficient service delivery to maintain quality of life and address potential safety risks, particularly for vulnerable residents.
* The surge in gun violence reflected in the 911 data demands immediate attention. Investigating underlying causes, implementing effective prevention strategies, and strengthening community partnerships are crucial to addressing this alarming trend and ensuring neighborhood safety."""
    )
]

from dash import html, dcc

def chat_display_div(history):
    return [
        html.Div([
            html.Strong(who + ":", style={"color": "#ff69b4" if who == "You" else "#00ffff"}),
            dcc.Markdown(msg, dangerously_allow_html=True, style={"marginLeft": "6px"})
            if who == "Assistant" else html.Span(" " + msg, style={"marginLeft": "6px"})
        ], style={"marginBottom": "10px"})
        for who, msg in history
    ]


app = Dash(__name__, suppress_callback_exceptions=True, serve_locally=False, requests_pathname_prefix=DASH_REQUESTS_PATHNAME)
app.layout = html.Div(
    style={"backgroundColor": "black", "padding": "10px"},
    children=[
        html.H1("City Safety Dashboard", style={"textAlign": "center", "color": "white", "marginBottom": "15px"}),
        dcc.Store(id="chat-history-store", data=chat_history),
        dcc.Store(id="selected-hexbin", data=[]),
        html.Div(id="enter-key-listener-output", style={"display": "none"}),
        html.Div(id="enter-key-listener-output", style={"display": "none"}),
        html.Div(id="cookie-status", style={"display": "none"}),
        html.Div(id="cookie-setter-trigger", style={"display": "none"}),
        dcc.Store(id="page-load", data="loaded"),
        html.Div(
            [
                html.Div(
                    [dcc.Graph(id="hexbin-map", style={"height": "800px", "width": "900px"})],
                    style={"width": "58%", "display": "inline-block", "paddingLeft": "2%", "position": "relative", "verticalAlign": "top"},
                ),
                html.Div(
                    [
                        html.Div("🤖 Assistant", style={"color": "white", "fontWeight": "bold", "marginBottom": "8px", "fontSize": "16px"}),
                        dcc.Loading(
                            id="chat-loading",
                            type="circle",
                            color="#ff69b4",
                            children=html.Div(chat_display_div(chat_history), id="chat-display", style={
                                "height": "480px", "backgroundColor": "#1a1a1a", "color": "white",
                                "border": "1px solid #444", "borderRadius": "8px", "padding": "10px",
                                "overflowY": "auto", "marginBottom": "10px", "fontSize": "13px"
                            })
                        ),
                        html.Div("No areas selected. Click on the map to select an area.", id="selection-status", style={"color": "white", "fontStyle": "italic", "marginBottom": "8px"}),
                        html.Button("Analyze Selected Areas", id="analyze-button", n_clicks=0, style={
                            "marginTop": "8px", "width": "100%", "backgroundColor": "#ff69b4", "color": "white",
                            "border": "none", "borderRadius": "6px", "padding": "10px", "fontWeight": "bold", "cursor": "pointer"
                        }),
                        dcc.Textarea(id="chat-input", placeholder="Type your question here...", style={
                            "width": "100%", "height": "80px", "borderRadius": "8px", "backgroundColor": "#333",
                            "color": "white", "border": "1px solid #555", "padding": "8px",
                            "resize": "none", "fontSize": "13px"
                        }),
                        html.Button("SEND", id="send-button", n_clicks=0, style={
                            "marginTop": "8px", "width": "100%", "backgroundColor": "#ff69b4", "color": "white",
                            "border": "none", "borderRadius": "6px", "padding": "10px", "fontWeight": "bold", "cursor": "pointer"
                        }),
                    ],
                    style={"width": "38%", "display": "inline-block", "paddingLeft": "2%", "verticalAlign": "top"},
                ),
            ],
            style={"marginBottom": "2rem"},
        ),
        html.Div(
            [dcc.Slider(
                id="hexbin-slider",
                min=0,
                max=len(month_labels) - 1,
                step=1,
                value=initial_index,
                marks={i: {"label": label, "style": {"color": "white"}} for i, label in slider_marks.items()},
                tooltip={"placement": "bottom", "always_visible": True},
                className="rc-slider-311"
            )],
            style={"width": "100%", "margin": "0 auto", "paddingTop": "30px", "paddingBottom": "0px", "backgroundColor": "black"},
        ),
    ],
)

# Clientside callback to handle pressing Enter in the chat textarea
app.clientside_callback(
    """
    function(data) {
        setTimeout(() => {
            const textarea = document.getElementById('chat-input');
            if (textarea && !textarea._hasEnterListener) {
                textarea.addEventListener('keydown', function(e) {
                    if (e.key === 'Enter' && !textarea.value.trim() == '' && !e.shiftKey) {
                        e.preventDefault();
                        document.getElementById('send-button').click();
                    }
                });
                textarea._hasEnterListener = true;
            }
        }, 500);
        return '';
    }
    """,
    Output("enter-key-listener-output", "children"),
    Input("page-load", "data"),
)


hexbin_polygon_map = {}

@app.callback(
    Output("hexbin-map", "figure"),
    [Input("hexbin-slider", "value"), Input("selected-hexbin", "data")],
)
def update_hexbin_map(month_index, selected_data):
    start = time.perf_counter()
    selected_month = available_months[month_index]
    month_str = selected_month.strftime("%B %Y")
    df_month = df_311[df_311["date"].dt.to_period("M").dt.to_timestamp() == selected_month]
    global df_month_tagged, hexbin_polygon_map
    if df_month.empty:
        
        fig = go.Figure()
        hexbin_polygon_map = {}
    else:
        df_month["count"] = 1
        grouped = df_month.groupby(["latitude", "longitude"]).size().reset_index(name="total_count")
        pivot = grouped.copy()
        
        fig = create_hexbin_mapbox(
            data_frame=pivot,
            lat="latitude",
            lon="longitude",
            nx_hexagon=20,
            agg_func=np.sum,
            color="total_count",
            opacity=0.7,
            color_continuous_scale=px.colors.sequential.Plasma[::-1],
            mapbox_style="carto-darkmatter",
            center=dict(lat=42.304, lon=-71.07),
            zoom=11.9,
            min_count=1,
            labels={"total_count": "311 Requests"},
        )
        
        features = fig.data[0].geojson["features"]
        centers = []
        polygon_map = {}
        for feature in features:
            fid = feature["id"]
            x_str, y_str = fid.split(",")
            x = float(x_str); y = float(y_str)
            lon_center = x * 180 / math.pi
            lat_center = (2 * math.atan(math.exp(y)) - math.pi/2) * 180 / math.pi
            centers.append((lat_center, lon_center))
            coords = feature["geometry"]["coordinates"][0]
            polygon_map[(lat_center, lon_center)] = coords

        fig.data[0].customdata = centers
        df_month_tagged = df_month.copy()
        hexbin_polygon_map = polygon_map
        fig.data[0].hovertemplate = "Click to select this area<extra></extra>"
        fig.update_coloraxes(colorbar=dict(
            title=dict(text="311 Requests", font=dict(size=12, color="white")),
            orientation="h", x=0.5, y=1.0, xanchor="center", len=0.5, thickness=12,
            tickfont=dict(size=10, color="white"), bgcolor="rgba(0,0,0,0)"
        ))
        for district_code, color in districts.items():
            try:
                params = {"where": f"DISTRICT='{district_code}'", "outFields": "DISTRICT", "f": "geojson", "outSR": "4326"}
                resp = requests.get(boston_url, params=params)
                geojson = resp.json()
                coords = geojson["features"][0]["geometry"]["coordinates"]
                poly_list = coords if isinstance(coords[0][0][0], float) else [p[0] for p in coords]
                for i, poly in enumerate(poly_list):
                    lons = [pt[0] for pt in poly] + [poly[0][0]]
                    lats = [pt[1] for pt in poly] + [poly[0][1]]
                    fig.add_trace(go.Scattermapbox(
                        lat=lats, lon=lons, mode="lines",
                        line=dict(color=color, width=3),
                        name=f"District {district_code}",
                        legendgroup=f"District {district_code}",
                        showlegend=(i == 0), hoverinfo="skip"
                    ))
            except Exception as e:
                print(f"district {district_code} boundary not added", e)

        dorchester_url = "https://gis.bostonplans.org/hosting/rest/services/Hosted/Boston_Neighborhood_Boundaries/FeatureServer/1/query"
        params = {"where": "name='Dorchester'", "outFields": "*", "f": "geojson", "outSR": "4326"}
        try:
            resp = requests.get(dorchester_url, params=params)
            if resp.status_code == 200:
                geojson = resp.json()
                features = geojson.get("features", [])
                if features:
                    geometry = features[0].get("geometry", {})
                    if geometry["type"] == "Polygon":
                        polygons = [geometry["coordinates"]]
                    elif geometry["type"] == "MultiPolygon":
                        polygons = geometry["coordinates"]
                    else:
                        polygons = []
                    for i, polygon in enumerate(polygons):
                        for j, ring in enumerate(polygon):
                            show = i == 0 and j == 0
                            lons = [pt[0] for pt in ring] + [ring[0][0]]
                            lats = [pt[1] for pt in ring] + [ring[0][1]]
                            fig.add_trace(go.Scattermapbox(
                                lat=lats, lon=lons, mode="lines",
                                line=dict(color="white", width=3),
                                name="Neighborhood: Dorchester",
                                legendgroup="Neighborhood: Dorchester",
                                showlegend=show, hoverinfo="skip"
                            ))
        except Exception as e:
            print("dorchester boundary not added:", e)

        df_month_shots = df_shots[df_shots["month"] == selected_month]
        confirmed = df_month_shots[df_month_shots["ballistics_evidence"] == 1]
        unconfirmed = df_month_shots[df_month_shots["ballistics_evidence"] == 0]
        hom_this_month = df_hom_shot_matched[df_hom_shot_matched["month"] == selected_month].copy()
        hom_this_month["latitude"] += 0.0020
        hom_this_month["longitude"] += 0.0020
        fig.add_trace(go.Scattermapbox(
            lat=confirmed["latitude"], lon=confirmed["longitude"],
            mode="markers", name="Confirmed (Ballistic)",
            marker=dict(color="red", size=9, opacity=1),
            hoverinfo="text", text=confirmed["date"].dt.strftime("%Y-%m-%d %H:%M")
        ))
        fig.add_trace(go.Scattermapbox(
            lat=unconfirmed["latitude"], lon=unconfirmed["longitude"],
            mode="markers", name="Unconfirmed",
            marker=dict(color="#1E90FF", size=7, opacity=1),
            hoverinfo="text", text=unconfirmed["date"].dt.strftime("%Y-%m-%d %H:%M")
        ))
        fig.add_trace(go.Scattermapbox(
            lat=hom_this_month["latitude"], lon=hom_this_month["longitude"],
            mode="markers", name="Matched Homicides",
            marker=dict(color="limegreen", size=10, opacity=1),
            hoverinfo="text", text=hom_this_month["date"].dt.strftime("%Y-%m-%d %H:%M")
        ))
        fig.update_layout(
            title=f"311 Requests + Shots Fired + Homicides ({month_str})",
            title_font=dict(size=18, color="white"),
            title_x=0.5,
            paper_bgcolor="black",
            plot_bgcolor="black",
            font_color="white",
            legend=dict(
                orientation="h", x=0.5, y=0.01, xanchor="center",
                font=dict(color="white"),
                bgcolor="rgba(0,0,0,0)", bordercolor="rgba(255,255,255,0.2)", borderwidth=1
            ),

            clickmode='event+select'
        )
        if len(fig.data) > 0:
            traces = list(fig.data)
            hex_trace = traces.pop(0)
            traces.append(hex_trace)
            fig.data = tuple(traces)

    if selected_data:
        for sel in selected_data:
            coords = hexbin_polygon_map.get((sel["lat"], sel["lon"]))
            if coords:

                lons = [pt[0] for pt in coords]
                lats = [pt[1] for pt in coords]
                if (lons[0], lats[0]) != (lons[-1], lats[-1]):
                    lons.append(lons[0])
                    lats.append(lats[0])
                fig.add_trace(go.Scattermapbox(
                    lat=lats, lon=lons, mode="lines",
                    line=dict(color="fuchsia", width=4),
                    name="Selected Area", showlegend=False, hoverinfo="skip"
                ))
    print(f"[TIMER] update_hexbin_map ({month_str}) took {time.perf_counter() - start:.2f} seconds")
    return fig

@app.callback(
    Output("selected-hexbin", "data"),
    Output("selection-status", "children"),
    Output("analyze-button", "disabled"),
    Input("hexbin-map", "clickData"),
    Input("hexbin-slider", "value"),
    State("selected-hexbin", "data")
)
def update_selection(clickData, month_index, current_selected):
    triggered_id = ctx.triggered_id

    if triggered_id == "hexbin-slider":
        return [], "No areas selected. Click on the map to select an area.", True

    if not clickData or "points" not in clickData:
        raise PreventUpdate
    point = clickData["points"][0]
    if "customdata" not in point or point["customdata"] is None:

        raise PreventUpdate
    lat, lon = point["customdata"]
    if current_selected is None:
        current_selected = []

    exists = any(abs(sel["lat"] - lat) < 1e-6 and abs(sel["lon"] - lon) < 1e-6 for sel in current_selected)
    if exists:
        current_selected = [sel for sel in current_selected if not (abs(sel["lat"] - lat) < 1e-6 and abs(sel["lon"] - lon) < 1e-6)]
    else:
        current_selected = current_selected + [{"lat": lat, "lon": lon}]
    n = len(current_selected)
    status_text = (
        f"{n} area{'s' if n != 1 else ''} selected. Click the 'Analyze Selected Areas' button to summarize them."
        if n > 0 else "No areas selected. Click on the map to select an area."
    )
    return current_selected, status_text, (False if n > 0 else True)


@app.callback(
    Output("chat-history-store", "data"),
    Output("chat-display", "children"),
    Output("chat-input", "value"),
    Input("send-button", "n_clicks"),
    Input("hexbin-slider", "value"),
    Input("analyze-button", "n_clicks"),
    State("chat-input", "value"),
    State("chat-history-store", "data"),
    State("selected-hexbin", "data")
)
def update_chat(n_send, slider_val, n_analyze, user_input, chat_history_state, selected_hexbin):
    triggered_id = ctx.triggered_id
    selected_date = available_months[slider_val].strftime("%B %Y")
    history = list(chat_history_state) if chat_history_state is not None else []

    if triggered_id == "hexbin-slider":
        try:
            api_month = available_months[slider_val].strftime("%Y-%m")
            response = requests.get(f"{API_BASE_URL}/llm_summaries?month={api_month}&app_version={APP_VERSION}")

            response.raise_for_status()
            reply = response.json().get("summary", "[No summary available]")
        except Exception as e:
            reply = f"[Error fetching summary for {selected_date}: {e}]"
        history = [("Assistant", reply)]
        return history, chat_display_div(history), ""

    elif triggered_id == "analyze-button":
        if not selected_hexbin or len(selected_hexbin) == 0:
            raise PreventUpdate
        try:
            print("[DEBUG] Selected hexbins:", selected_hexbin)
            print("[DEBUG] Selected month:", available_months[slider_val])
            print("[DEBUG] 311 records tagged in df_month_tagged:", df_month_tagged.shape)
            records_text = get_selected_area_records(selected_hexbin, available_months[slider_val])
            print("[DEBUG] Records text:\n", records_text)

            prompt = (
                f"The user has selected {len(selected_hexbin)} area{'s' if len(selected_hexbin) != 1 else ''} in the Dorchester neighborhood for {selected_date}. "
                f"The following are the 311 and 911 records for these selected area{'s' if len(selected_hexbin) != 1 else ''}:\n\n{records_text}\n\n"
                "Summarize any notable patterns, trends, or anomalies from this data, providing clear numeric details and insights."
            )
            response = requests.post(
                f"{API_BASE_URL}/chat?request=experiment_5&app_version={APP_VERSION}",
                headers={"Content-Type": "application/json"},
                json={"client_query": prompt},
                timeout=30
            )
            response.raise_for_status()
            json_data = response.json()
            print("[DEBUG] LLM raw response JSON:", json_data)
            reply = json_data.get("response", "[No reply received]")
        except Exception as e:
            reply = f"[Error summarizing selected areas: {e}]"
        history.append(("Assistant", reply))
        return history, chat_display_div(history), ""

    elif triggered_id == "send-button":
        if not user_input or not user_input.strip():
            raise PreventUpdate
        history.append(("You", user_input.strip()))
        prompt = (
            f"The user has selected a subset of the available 311 and 911 data. They are only looking at the data for {selected_date} in the Dorchester neighborhood.\n\n"
            f"Describe the conditions captured in the meeting transcripts and how those related to the trends seen in the 911 and 311 CSV data for the date {selected_date}.\n\n"
            f"Point out notable spikes, drops, or emerging patterns in the data for {selected_date}, and connect them to lived experiences and perceptions.\n\n"
            f"Use the grouped 311 categories and the 911 incident data together to provide a holistic, narrative-driven analysis."
        )
        if selected_hexbin and len(selected_hexbin) > 0:
            try:
                records_text = get_selected_area_records(selected_hexbin, available_months[slider_val])
                prompt += (
                    f"\n\nThe user is especially interested in the selected area{'s' if len(selected_hexbin) != 1 else ''} and wants a more localized interpretation. "
                    f"Here are the data from that area:\n\n{records_text}"
                )
            except Exception as e:
                prompt += f"\n\n[Could not include selected area data: {e}]"
        prompt += f"\n\nUser's question: {user_input.strip()}"
        try:
            response = requests.post(
                f"{API_BASE_URL}/chat?request=experiment_5&app_version={APP_VERSION}",
                headers={"Content-Type": "application/json"},
                json={"client_query": prompt},
                timeout=10
            )
            response.raise_for_status()
            reply = response.json().get("response", "[No reply received]")
        except Exception as e:
            reply = f"[Error: {e}]"
        history.append(("Assistant", reply))
        return history, chat_display_div(history), ""

    raise PreventUpdate

def get_hexbin_filtered_summary(hexbin_data, selected_month):
    if not hexbin_data:
        return "[No hexbin selected.]"
    lat_center, lon_center = hexbin_data["lat"], hexbin_data["lon"]
    global df_month_tagged, hexbin_polygon_map
    coords = hexbin_polygon_map.get((lat_center, lon_center))
    if not coords:
        return f"[No incidents found for this hexbin in {selected_month.strftime('%B %Y')}]"
    poly = Polygon(coords)
    inside_points = df_month_tagged[df_month_tagged.apply(lambda row: poly.contains(Point(row["longitude"], row["latitude"])), axis=1)]
    if inside_points.empty:
        return f"[No incidents found for this hexbin in {selected_month.strftime('%B %Y')}]"
    tooltip_count = len(inside_points)
    counts = inside_points["category"].value_counts().to_dict()

    categories = {"Living Conditions": 0, "Trash, Recycling, And Waste": 0, "Streets, Sidewalks, And Parks": 0, "Parking": 0}
    for cat, cnt in counts.items():
        for group in categories:
            if group.lower() in cat.lower() or cat.lower() in group.lower():
                categories[group] += cnt
    summary = f"""**Exact Hexbin Summary for {selected_month.strftime('%B %Y')}**  
-  Center: ({lat_center:.4f}, {lon_center:.4f})  
- 311 Requests: {int(tooltip_count)} total (matches tooltip)  
"""
    for k, v in categories.items():
        summary += f"  • {k}: {v}\n"
    return summary


def get_selected_area_records(selected_list, selected_month):
    global df_month_tagged, df_shots, df_hom_shot_matched, hexbin_polygon_map
    if not selected_list or len(selected_list) == 0:
        return ""

    polygons = []
    for item in selected_list:
        coords = hexbin_polygon_map.get((item["lat"], item["lon"]))
        if coords:
            polygons.append(Polygon(coords))
    region = unary_union(polygons) if polygons else Polygon()
    df311 = df_month_tagged.copy()
    df_shots_month = df_shots[df_shots["month"] == selected_month]
    df_hom_month = df_hom_shot_matched[df_hom_shot_matched["month"] == selected_month]
    df311_in = df311[df311.apply(lambda r: region.contains(Point(r["longitude"], r["latitude"])), axis=1)]
    df_shots_in = df_shots_month[df_shots_month.apply(lambda r: region.contains(Point(r["longitude"], r["latitude"])), axis=1)]
    df_hom_in = df_hom_month[df_hom_month.apply(lambda r: region.contains(Point(r["longitude"], r["latitude"])), axis=1)]
    lines = []
    if df311_in.empty:
        lines.append("311 Records: None")
    else:
        lines.append("311 Records:")
        for _, row in df311_in.iterrows():
            date_str = row["date"].strftime("%Y-%m-%d") if pd.notna(row["date"]) else ""
            lines.append(f"- {row['category']} ({date_str})")
    lines.append("")
    if df_shots_in.empty and df_hom_in.empty:
        lines.append("911 Records: None")
    else:
        lines.append("911 Records:")
        for _, row in df_shots_in.iterrows():
            date_str = row["date"].strftime("%Y-%m-%d %H:%M") if pd.notna(row["date"]) else ""
            incident_type = "Shots Fired (Confirmed)" if row.get("ballistics_evidence", 0) == 1 else "Shots Fired (Unconfirmed)"
            lines.append(f"- {incident_type} ({date_str})")
        for _, row in df_hom_in.iterrows():
            date_str = row["date"].strftime("%Y-%m-%d %H:%M") if pd.notna(row["date"]) else ""
            lines.append(f"- Homicide ({date_str})")
    return "\n".join(lines)


server = app.server
print(f"[TIMER] Total Dash app setup time: {time.perf_counter() - global_start:.2f} seconds")

if __name__ == "__main__":
    app.run(debug=True)
