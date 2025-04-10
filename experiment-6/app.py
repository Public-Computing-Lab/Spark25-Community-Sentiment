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
from scipy.spatial import cKDTree
from shapely.geometry import Point, Polygon
from shapely.ops import unary_union
import math

global_start = time.perf_counter()

load_dotenv()
PORT = os.getenv("EXPERIMENT_5_PORT")
DASH_REQUESTS_PATHNAME = os.getenv("EXPERIMENT_5_DASH_REQUESTS_PATHNAME")
API_BASE_URL = os.getenv("API_BASE_URL")
APP_VERSION = os.getenv("APP_VERSION", "5")

districts = {"B3": "rgba(255, 255, 0, 0.7)", "B2": "rgba(0, 255, 255, 0.7)", "C11": "rgba(0, 255, 0, 0.7)"}
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

def chat_display_div(history):
    return [
        html.Div([
            html.Strong(who + ":", style={"color": "#ff69b4" if who == "You" else "#00ffff"}),
            html.Span(" " + msg, style={"marginLeft": "6px", "fontStyle": "italic"} if msg == "_typing_..." else {"marginLeft": "6px"})
        ], style={"marginBottom": "10px"})
        for who, msg in history
    ]

def build_hexagon(lat_center, lon_center, df_pivot=None, nx_hexagon=20):
    R = 6378137.0
    if df_pivot is not None:
        lat_min, lat_max = df_pivot["latitude"].min(), df_pivot["latitude"].max()
        lon_min, lon_max = df_pivot["longitude"].min(), df_pivot["longitude"].max()
        center_lat = (lat_min + lat_max) / 2.0
        lon_span_deg = lon_max - lon_min
        lon_km_per_deg = 111 * math.cos(math.radians(center_lat))
        total_km = lon_span_deg * lon_km_per_deg
        width_per_hex_km = total_km / nx_hexagon if nx_hexagon else 0.0
        size_km = width_per_hex_km / math.sqrt(3) if nx_hexagon else 0.215
    else:
        size_km = 0.215
    x0 = math.radians(lon_center) * R
    y0 = math.log(math.tan(math.pi / 4 + math.radians(lat_center) / 2)) * R
    r = size_km * 1000
    angles = np.linspace(0, 2 * math.pi, 7)[:-1]
    points_xy = [(x0 + r * math.cos(a), y0 + r * math.sin(a)) for a in angles]
    points_latlon = [
        (math.degrees(x / R), math.degrees(2 * math.atan(math.exp(y / R)) - math.pi / 2))
        for x, y in points_xy
    ]
    return Polygon(points_latlon)


chat_history = [
    ("Assistant", 
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

app = Dash(__name__, suppress_callback_exceptions=True, serve_locally=False, requests_pathname_prefix=DASH_REQUESTS_PATHNAME)
app.layout = html.Div(style={"backgroundColor": "black", "padding": "10px"}, children=[
    html.H1("City Safety Dashboard", style={"textAlign": "center", "color": "white", "marginBottom": "15px"}),
    dcc.Store(id="chat-history-store", data=chat_history),
    dcc.Store(id="selected-hexbin", data=None),
    html.Div(id="cookie-status", style={"display": "none"}),
    html.Div(id="debug-output", style={"color": "white", "paddingTop": "10px"}),
    html.Div([html.Div(id="cookie-setter-trigger", style={"display": "none"}), dcc.Store(id="page-load", data="loaded")]),
    html.Div([
        html.Div([dcc.Graph(id="hexbin-map", style={"height": "800px", "width": "900px"})],
                 style={"width": "58%", "display": "inline-block", "paddingLeft": "2%", "position": "relative", "verticalAlign": "top"}),
        html.Div([
            html.Div("🤖 Assistant", style={"color": "white", "fontWeight": "bold", "marginBottom": "8px", "fontSize": "16px"}),
            dcc.Loading(id="chat-loading", type="circle", color="#ff69b4", children=
                html.Div(chat_display_div(chat_history), id="chat-display", style={
                    "height": "480px", "backgroundColor": "#1a1a1a", "color": "white",
                    "border": "1px solid #444", "borderRadius": "8px", "padding": "10px",
                    "overflowY": "auto", "marginBottom": "10px", "fontSize": "13px"
                })
            ),
            html.Button("Analyze Selected Areas", id="analyze-button", n_clicks=0, style={
                "marginBottom": "8px", "width": "100%", "backgroundColor": "#00ffff",
                "color": "black", "border": "none", "borderRadius": "6px", "padding": "10px",
                "fontWeight": "bold", "cursor": "pointer"
            }),
            dcc.Textarea(id="chat-input", placeholder="Type your question here...", style={
                "width": "100%", "height": "80px", "borderRadius": "8px",
                "backgroundColor": "#333", "color": "white", "border": "1px solid #555",
                "padding": "8px", "resize": "none", "fontSize": "13px"
            }),
            html.Button("SEND", id="send-button", n_clicks=0, style={
                "marginTop": "8px", "width": "100%", "backgroundColor": "#ff69b4",
                "color": "white", "border": "none", "borderRadius": "6px", "padding": "10px",
                "fontWeight": "bold", "cursor": "pointer"
            })
        ], style={"width": "38%", "display": "inline-block", "paddingLeft": "2%", "verticalAlign": "top"})
    ], style={"marginBottom": "2rem"}),
    html.Div([
        dcc.Slider(id="hexbin-slider", min=0, max=len(month_labels) - 1, step=1, value=0,
                   marks={i: {"label": label, "style": {"color": "white"}} for i, label in slider_marks.items()},
                   tooltip={"placement": "bottom", "always_visible": True}, className="rc-slider-311")
    ], style={"width": "100%", "margin": "0 auto", "paddingTop": "30px", "paddingBottom": "0px", "backgroundColor": "black"})
])


@app.callback(
    [Output("hexbin-map", "figure"), Output("selected-hexbin", "data")],
    [Input("hexbin-slider", "value"), Input("hexbin-map", "clickData")],
    [State("hexbin-map", "figure"), State("selected-hexbin", "data")]
)
def update_map_and_selection(month_index, clickData, current_fig, selected_list):
    triggered_id = ctx.triggered_id

    if triggered_id == "hexbin-slider":
        start = time.perf_counter()
        selected_month = available_months[month_index]
        month_str = selected_month.strftime("%B %Y")
        df_month = df_311[df_311["date"].dt.to_period("M").dt.to_timestamp() == selected_month]
        if df_month.empty:
            return go.Figure(), []  
        df_month["count"] = 1
        grouped = df_month.groupby(["latitude", "longitude"]).size().reset_index(name="total_count")
        pivot = grouped.copy()
        global df_hexbin_pivot, df_month_tagged
        df_hexbin_pivot = pivot.copy()

        hex_centers = pivot[["latitude", "longitude"]].to_numpy()
        tree = cKDTree(hex_centers)
        coords = df_month[["latitude", "longitude"]].to_numpy()
        distances, indices = tree.query(coords, distance_upper_bound=0.0015)
        valid = distances != np.inf
        df_month.loc[valid, "hexbin_id"] = indices[valid]

        fig = create_hexbin_mapbox(
            data_frame=pivot, lat="latitude", lon="longitude",
            nx_hexagon=20, agg_func=np.sum, color="total_count", opacity=0.7,
            color_continuous_scale=px.colors.sequential.Plasma[::-1],
            mapbox_style="carto-darkmatter", center={"lat": 42.304, "lon": -71.07},
            zoom=11.9, min_count=1, labels={"total_count": "311 Requests"}
        )
        fig.data[0].customdata = list(zip(pivot["latitude"], pivot["longitude"]))
        hexbin_centers = np.array(fig.data[0].customdata)

        tree = cKDTree(hexbin_centers)
        coords = df_month[["latitude", "longitude"]].to_numpy()
        distances, indices = tree.query(coords, distance_upper_bound=0.0015)
        df_month["hex_center_lat"] = np.nan
        df_month["hex_center_lon"] = np.nan
        valid = distances != np.inf
        df_month.loc[valid, "hex_center_lat"] = hexbin_centers[indices[valid], 0]
        df_month.loc[valid, "hex_center_lon"] = hexbin_centers[indices[valid], 1]

        R = 6378137.0
        df_month["x"] = np.radians(df_month["longitude"]) * R
        df_month["y"] = np.log(np.tan(np.pi / 4 + np.radians(df_month["latitude"]) / 2)) * R
        hexbin_centers_xy = np.array([
            (np.radians(lon) * R, np.log(np.tan(np.pi / 4 + np.radians(lat) / 2)) * R)
            for lat, lon in fig.data[0].customdata
        ])
        tree = cKDTree(hexbin_centers_xy)
        coords = df_month[["x", "y"]].to_numpy()
        distances, indices = tree.query(coords, distance_upper_bound=100)
        valid = distances != np.inf
        df_month["bin_x"] = np.nan
        df_month["bin_y"] = np.nan
        df_month.loc[valid, "bin_x"] = hexbin_centers_xy[indices[valid], 0]
        df_month.loc[valid, "bin_y"] = hexbin_centers_xy[indices[valid], 1]
        df_month_tagged = df_month.copy()

        fig.data[0].hovertemplate = "incidents = %{z}<extra></extra><br>Click to select this area"
        fig.update_coloraxes(colorbar=dict(
            title=dict(text="311 Requests", font=dict(size=12, color="white")),
            orientation="h", x=0.5, y=1.0, xanchor="center",
            len=0.5, thickness=12, tickfont=dict(size=10, color="white"),
            bgcolor="rgba(0,0,0,0)"
        ))

        for district_code, color in districts.items():
            try:
                params = {
                    "where": f"DISTRICT='{district_code}'", "outFields": "DISTRICT",
                    "f": "geojson", "outSR": "4326"
                }
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
                        name=f"District {district_code}", legendgroup=f"District {district_code}",
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
                    polygons = []
                    if geometry.get("type") == "Polygon":
                        polygons = [geometry["coordinates"]]
                    elif geometry.get("type") == "MultiPolygon":
                        polygons = geometry["coordinates"]
                    for i, polygon in enumerate(polygons):
                        for j, ring in enumerate(polygon):
                            show = (i == 0 and j == 0)
                            lons = [pt[0] for pt in ring] + [ring[0][0]]
                            lats = [pt[1] for pt in ring] + [ring[0][1]]
                            fig.add_trace(go.Scattermapbox(
                                lat=lats, lon=lons, mode="lines",
                                line=dict(color="white", width=3),
                                name="Neighborhood: Dorchester", legendgroup="Neighborhood: Dorchester",
                                showlegend=show, hoverinfo="skip"
                            ))
        except Exception as e:
            print("dorchester boundary not added:", e)

        df_month_shots = df_shots[df_shots["month"] == selected_month]
        confirmed = df_month_shots[df_month_shots["ballistics_evidence"] == 1]
        unconfirmed = df_month_shots[df_month_shots["ballistics_evidence"] == 0]
        hom_this_month = df_hom_shot_matched[df_hom_shot_matched["month"] == selected_month].copy()

        hom_this_month["latitude"] = hom_this_month["latitude"] + 0.0020
        hom_this_month["longitude"] = hom_this_month["longitude"] + 0.0020
        fig.add_trace(go.Scattermapbox(
            lat=confirmed["latitude"], lon=confirmed["longitude"], mode="markers",
            name="Confirmed (Ballistic)", marker=dict(color="red", size=9, opacity=1),
            hoverinfo="text", text=confirmed["date"].dt.strftime("%Y-%m-%d %H:%M")
        ))
        fig.add_trace(go.Scattermapbox(
            lat=unconfirmed["latitude"], lon=unconfirmed["longitude"], mode="markers",
            name="Unconfirmed", marker=dict(color="#1E90FF", size=7, opacity=1),
            hoverinfo="text", text=unconfirmed["date"].dt.strftime("%Y-%m-%d %H:%M")
        ))
        fig.add_trace(go.Scattermapbox(
            lat=hom_this_month["latitude"], lon=hom_this_month["longitude"], mode="markers",
            name="Matched Homicides", marker=dict(color="limegreen", size=10, opacity=1),
            hoverinfo="text", text=hom_this_month["date"].dt.strftime("%Y-%m-%d %H:%M")
        ))
        fig.update_layout(
            title=f"311 Requests + Shots Fired + Homicides ({month_str})",
            title_font=dict(size=18, color="white"), title_x=0.5,
            paper_bgcolor="black", plot_bgcolor="black", font_color="white",
            legend=dict(
                orientation="h", x=0.5, y=0.01, xanchor="center",
                font=dict(color="white"),
                bgcolor="rgba(0,0,0,0)", bordercolor="rgba(255,255,255,0.2)", borderwidth=1
            )
        )
        print(f"[TIMER] update_hexbin_map ({month_str}) took {time.perf_counter() - start:.2f} seconds")

        return fig, []

    elif triggered_id == "hexbin-map":
        if not clickData or "points" not in clickData or not clickData["points"]:
            raise PreventUpdate
        point = clickData["points"][0]
        if "customdata" not in point or point["customdata"] is None:
            raise PreventUpdate
        lat, lon = point["customdata"]

        if selected_list is None:
            selected_list = []
        current_selection = list(selected_list) if isinstance(selected_list, list) else [selected_list]

        already_selected = False
        for sel in current_selection:
            if abs(sel.get("lat", 0) - lat) < 1e-6 and abs(sel.get("lon", 0) - lon) < 1e-6:
                already_selected = True
                current_selection.remove(sel)
                break
        if not already_selected:
            current_selection.append({"lat": lat, "lon": lon})

        fig = go.Figure(current_fig) if current_fig else go.Figure()

        fig.data = tuple(
            trace for trace in fig.data
            if not (isinstance(trace, go.Scattermapbox) and trace.name == "Selected Area(s) Highlight")
        )

        if current_selection:
            combined_lats, combined_lons = [], []
            for sel in current_selection:
                hex_poly = build_hexagon(sel["lat"], sel["lon"], df_hexbin_pivot, nx_hexagon=20)
                coords = list(hex_poly.exterior.coords)
                lons = [pt[0] for pt in coords]
                lats = [pt[1] for pt in coords]

                if lons[0] != lons[-1] or lats[0] != lats[-1]:
                    lons.append(lons[0]); lats.append(lats[0])
                combined_lats.extend(lats); combined_lons.extend(lons)
 
                combined_lats.append(None); combined_lons.append(None)
            if combined_lats and combined_lats[-1] is None:
                combined_lats.pop(); combined_lons.pop()
            fig.add_trace(go.Scattermapbox(
                lat=combined_lats, lon=combined_lons, mode="lines",
                line=dict(color="#ff69b4", width=4),
                name="Selected Area(s) Highlight", showlegend=False, hoverinfo="skip"
            ))
        return fig, current_selection
    else:
        raise PreventUpdate


@app.callback(Output("debug-output", "children"),
              Input("selected-hexbin", "data"), prevent_initial_call=True)
def show_selected_hexbin(data):
    if not data or (isinstance(data, list) and len(data) == 0):
        return "No hexbin selected."
    if isinstance(data, list):
        centers = "; ".join([f"({d['lat']:.4f}, {d['lon']:.4f})" for d in data])
        return f"Selected hexbins centers: {centers}"
    else:
        return f"Selected hexbin center: lat = {data['lat']}, lon = {data['lon']}"


@app.callback(Output("chat-input", "placeholder"),
              Input("selected-hexbin", "data"), State("hexbin-slider", "value"), prevent_initial_call=True)
def update_chat_placeholder(selection, slider_val):
    if not selection or (isinstance(selection, list) and len(selection) == 0):
        raise PreventUpdate
    selected_month = available_months[slider_val]
    try:
        if isinstance(selection, list):
            if len(selection) == 1:
                summary = get_hexbin_filtered_summary(selection[0], selected_month)
            else:

                return f"{len(selection)} areas selected."
        else:
            summary = get_hexbin_filtered_summary(selection, selected_month)
        return (summary[:300] + "...") if len(summary) > 300 else summary
    except Exception as e:
        return f"Error generating summary: {e}"

def get_hexbin_filtered_summary(hexbin_data, selected_month):
    if not hexbin_data:
        return "[No hexbin selected.]"
    if isinstance(hexbin_data, list):
        if len(hexbin_data) == 0:
            return "[No hexbin selected.]"
        if len(hexbin_data) > 1:
            return f"[Summary not available for {len(hexbin_data)} selected areas]"
        hexbin_data = hexbin_data[0]
    lat_center, lon_center = hexbin_data["lat"], hexbin_data["lon"]
    matched_points = df_hexbin_pivot[
        (np.isclose(df_hexbin_pivot["latitude"], lat_center, atol=1e-6)) &
        (np.isclose(df_hexbin_pivot["longitude"], lon_center, atol=1e-6))
    ]
    if matched_points.empty:
        return f"[No incidents found for this hexbin in {selected_month.strftime('%B %Y')}]"
    tooltip_count = matched_points["total_count"].sum()
    df_hex = df_month_tagged[
        (np.isclose(df_month_tagged["hex_center_lat"], lat_center, atol=1e-6)) &
        (np.isclose(df_month_tagged["hex_center_lon"], lon_center, atol=1e-6))
    ]
    counts = df_hex["category"].value_counts().to_dict()
    categories = {
        "Living Conditions": 0,
        "Trash, Recycling, And Waste": 0,
        "Streets, Sidewalks, And Parks": 0,
        "Parking": 0
    }
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


@app.callback(
    [Output("chat-history-store", "data"), Output("chat-display", "children"), Output("chat-input", "value")],
    [Input("send-button", "n_clicks"), Input("hexbin-slider", "value"),
     Input("selected-hexbin", "data"), Input("analyze-button", "n_clicks")],
    [State("chat-input", "value"), State("chat-history-store", "data")]
)
def handle_chat(n_clicks_send, slider_val, selected_hexbin, n_clicks_analyze, user_input, history):
    if history is None:
        history = []
    triggered_id = ctx.triggered_id
    selected_date = available_months[slider_val].strftime("%B %Y")
    selected_month = available_months[slider_val]

    if triggered_id == "hexbin-slider":
        history = []
        try:
            response = requests.get(f"{API_BASE_URL}/llm_summaries?date={selected_month.strftime('%Y-%m')}&app_version={APP_VERSION}")
            response.raise_for_status()
            reply = response.json().get("summary", "[No summary available]")
        except Exception as e:
            reply = f"[Error fetching summary for {selected_date}: {e}]"
        history.append(("Assistant", reply))
        return history, chat_display_div(history), ""

    elif triggered_id == "selected-hexbin":
        if not selected_hexbin or (isinstance(selected_hexbin, list) and len(selected_hexbin) == 0):
            raise PreventUpdate

        if isinstance(selected_hexbin, list) and len(selected_hexbin) > 1:
            reply = f"[{len(selected_hexbin)} areas selected. Click 'Analyze Selected Areas' to summarize them.]"
            history.append(("Assistant", reply))
            return history, chat_display_div(history), ""

        hex_info = selected_hexbin[0] if isinstance(selected_hexbin, list) else selected_hexbin
        try:
            summary = get_hexbin_filtered_summary(hex_info, selected_month)
            prompt = (
                f"A user has clicked on a specific hexbin to understand that area's conditions more deeply. "
                f"Provide a short analysis based on the data for {selected_date}:\n\n{summary}"
            )
            response = requests.post(
                f"{API_BASE_URL}/chat?request=experiment_5&app_version={APP_VERSION}",
                headers={"Content-Type": "application/json"},
                json={"client_query": prompt}
            )
            response.raise_for_status()
            reply = response.json().get("response", "[No reply received]")
        except Exception as e:
            reply = f"[Error summarizing hexbin data: {e}]"
        history.append(("Assistant", reply))
        return history, chat_display_div(history), ""

    elif triggered_id == "analyze-button":
        if not selected_hexbin or (isinstance(selected_hexbin, list) and len(selected_hexbin) == 0):
            reply = "[No areas selected. Please select one or more hexagons first.]"
            history.append(("Assistant", reply))
            return history, chat_display_div(history), ""
        areas = selected_hexbin if isinstance(selected_hexbin, list) else [selected_hexbin]

        global df_month_tagged
        if 'df_month_tagged' not in globals():
            df_month_tagged = df_311[df_311["date"].dt.to_period("M").dt.to_timestamp() == selected_month].copy()
            pivot_tmp = df_month_tagged.groupby(["latitude", "longitude"]).size().reset_index(name="total_count")
            centers_tmp = pivot_tmp[["latitude", "longitude"]].to_numpy()
            tree_tmp = cKDTree(centers_tmp)
            coords_tmp = df_month_tagged[["latitude", "longitude"]].to_numpy()
            dist_tmp, idx_tmp = tree_tmp.query(coords_tmp, distance_upper_bound=0.0015)
            valid_tmp = dist_tmp != np.inf
            df_month_tagged["hex_center_lat"] = np.nan
            df_month_tagged["hex_center_lon"] = np.nan
            df_month_tagged.loc[valid_tmp, "hex_center_lat"] = centers_tmp[idx_tmp[valid_tmp], 0]
            df_month_tagged.loc[valid_tmp, "hex_center_lon"] = centers_tmp[idx_tmp[valid_tmp], 1]

        mask = np.zeros(len(df_month_tagged), dtype=bool)
        for area in areas:
            mask |= ((np.isclose(df_month_tagged["hex_center_lat"], area["lat"], atol=1e-6)) &
                     (np.isclose(df_month_tagged["hex_center_lon"], area["lon"], atol=1e-6)))
        df_311_selected = df_month_tagged[mask]
        if df_311_selected.empty:
            list_311 = "[No 311 requests in selected areas]"
        else:
            list_311_lines = [f"- {cat}" for cat in df_311_selected["category"]]
            list_311 = "\n".join(list_311_lines)

        df_month_shots = df_shots[df_shots["month"] == selected_month]
        df_month_hom = df_hom_shot_matched[df_hom_shot_matched["month"] == selected_month]
        if not areas:
            list_911 = "[No 911 incidents in selected areas]"
        else:
            hex_polygons = [build_hexagon(area["lat"], area["lon"], df_hexbin_pivot, nx_hexagon=20) for area in areas]
            combined_region = unary_union(hex_polygons) if len(hex_polygons) > 1 else hex_polygons[0]
            incidents = []

            for _, row in df_month_shots.iterrows():
                point = Point(row["longitude"], row["latitude"])
                if combined_region.contains(point):
                    time_str = row["date"].strftime("%Y-%m-%d %H:%M")
                    if pd.notna(row.get("ballistics_evidence")) and int(row["ballistics_evidence"]) == 1:
                        incidents.append((row["date"], f"{time_str} – Confirmed Shots Fired"))
                    else:
                        incidents.append((row["date"], f"{time_str} – Unconfirmed Shots Fired"))

            for _, row in df_month_hom.iterrows():
                point = Point(row["longitude"], row["latitude"])
                if combined_region.contains(point):
                    time_str = row["date"].strftime("%Y-%m-%d %H:%M")
                    incidents.append((row["date"], f"{time_str} – Homicide"))
            if not incidents:
                list_911 = "[No 911 incidents in selected areas]"
            else:
                incidents.sort(key=lambda x: x[0])  
                list_911_lines = [f"- {desc}" for _, desc in incidents]
                list_911 = "\n".join(list_911_lines)

        prompt = (
            f"The user has selected {len(areas)} areas on the map for {selected_date}. "
            f"They have requested an analysis of trends and patterns in these specific areas. "
            f"Below is the raw data for the 311 service requests and 911 incidents in the selected areas during {selected_date}.\n\n"
            f"311 Service Requests in selected areas:\n{list_311}\n\n"
            f"911 Incidents in selected areas:\n{list_911}\n\n"
            f"Provide a concise summary of any notable trends, patterns, or anomalies observed in these selected areas for {selected_date}."
        )
        try:
            response = requests.post(
                f"{API_BASE_URL}/chat?request=experiment_5&app_version={APP_VERSION}",
                headers={"Content-Type": "application/json"},
                json={"client_query": prompt}
            )
            response.raise_for_status()
            reply = response.json().get("response", "[No reply received]")
        except Exception as e:
            reply = f"[Error analyzing selected areas: {e}]"
        history.append(("Assistant", reply))
        return history, chat_display_div(history), ""

    elif triggered_id == "send-button":
        if not user_input or not user_input.strip():
            raise PreventUpdate
        history.append(("You", user_input.strip()))
        prompt = (
            f"The user has selected a subset of the available 311 and 911 data. They are only looking at the data for {selected_date} in the Dorchester neighborhood.\n\n"
            f"Describe the conditions captured in the meeting transcripts and interviews and how those related to the trends seein the 911 and 311 CSV data for the date {selected_date}.\n\n"
            f"Point out notable spikes, drops, or emerging patterns in the data for {selected_date}, and connect them to lived experiences and perceptions.\n\n"
            f"Use the grouped 311 categories and the 911 incident data together to provide a holistic, narrative-driven analysis."
        )

        if selected_hexbin:
            try:
                if isinstance(selected_hexbin, list) and len(selected_hexbin) == 1:
                    hex_summary = get_hexbin_filtered_summary(selected_hexbin[0], selected_month)
                elif isinstance(selected_hexbin, dict):
                    hex_summary = get_hexbin_filtered_summary(selected_hexbin, selected_month)
                else:
                    hex_summary = None
                if hex_summary:
                    prompt += (
                        f"\n\nThe user is especially interested in one specific hexbin and wants a more localized interpretation. "
                        f"Here is the data from that area:\n\n{hex_summary}"
                    )
            except Exception as e:
                prompt += f"\n\n[Could not include hexbin summary: {e}]"
        prompt += f"\n\nUser's question: {user_input.strip()}"
        try:
            response = requests.post(
                f"{API_BASE_URL}/chat?request=experiment_5&app_version={APP_VERSION}",
                headers={"Content-Type": "application/json"},
                json={"client_query": prompt}
            )
            response.raise_for_status()
            reply = response.json().get("response", "[No reply received]")
        except Exception as e:
            reply = f"[Error: {e}]"
        history.append(("Assistant", reply))
        return history, chat_display_div(history), ""
    else:
        raise PreventUpdate

server = app.server
print(f"[TIMER] Total Dash app setup time: {time.perf_counter() - global_start:.2f} seconds")

if __name__ == "__main__":
    app.run(debug=True)