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

# slider months
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
    return [html.Div([html.Strong(who + ":", style={"color": "#ff69b4" if who == "You" else "#00ffff"}), html.Span(" " + msg, style={"marginLeft": "6px", "fontStyle": "italic"} if msg == "_typing_..." else {"marginLeft": "6px"})], style={"marginBottom": "10px"}) for who, msg in history]


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
* The surge in gun violence reflected in the 911 data demands immediate attention. Investigating underlying causes, implementing effective prevention strategies, and strengthening community partnerships are crucial to addressing this alarming trend and ensuring neighborhood safety.""",
    )
]


# dash initiate
app = Dash(__name__, suppress_callback_exceptions=True, serve_locally=False, requests_pathname_prefix=DASH_REQUESTS_PATHNAME)
app.layout = html.Div(
    style={"backgroundColor": "black", "padding": "10px"},
    children=[
        html.H1("City Safety Dashboard", style={"textAlign": "center", "color": "white", "marginBottom": "15px"}),
        dcc.Store(id="chat-history-store", data=chat_history),
        html.Div([html.Div(id="cookie-setter-trigger", style={"display": "none"}), dcc.Store(id="page-load", data="loaded")]),
        html.Div(
            [
                html.Div(
                    [
                        dcc.Graph(id="hexbin-map", style={"height": "800px", "width": "900px"}),
                    ],
                    style={"width": "58%", "display": "inline-block", "paddingLeft": "2%", "position": "relative", "verticalAlign": "top"},
                ),
                html.Div(
                    [
                        html.Div("🤖 Assistant", style={"color": "white", "fontWeight": "bold", "marginBottom": "8px", "fontSize": "16px"}),
                        dcc.Loading(
                            id="chat-loading",
                            type="circle",
                            color="#ff69b4",
                            children=html.Div(chat_display_div(chat_history), id="chat-display", style={"height": "480px", "backgroundColor": "#1a1a1a", "color": "white", "border": "1px solid #444", "borderRadius": "8px", "padding": "10px", "overflowY": "auto", "marginBottom": "10px", "fontSize": "13px"}),
                        ),
                        dcc.Textarea(id="chat-input", placeholder="Type your question here...", style={"width": "100%", "height": "80px", "borderRadius": "8px", "backgroundColor": "#333", "color": "white", "border": "1px solid #555", "padding": "8px", "resize": "none", "fontSize": "13px"}),
                        html.Button("SEND", id="send-button", n_clicks=0, style={"marginTop": "8px", "width": "100%", "backgroundColor": "#ff69b4", "color": "white", "border": "none", "borderRadius": "6px", "padding": "10px", "fontWeight": "bold", "cursor": "pointer"}),
                    ],
                    style={"width": "38%", "display": "inline-block", "paddingLeft": "2%", "verticalAlign": "top"},
                ),
            ],
            style={"marginBottom": "2rem"},
        ),
        html.Div(
            [dcc.Slider(id="hexbin-slider", min=0, max=len(month_labels) - 1, step=1, value=0, marks={i: {"label": label, "style": {"color": "white"}} for i, label in slider_marks.items()}, tooltip={"placement": "bottom", "always_visible": True}, className="rc-slider-311")],
            style={"width": "100%", "margin": "0 auto", "paddingTop": "30px", "paddingBottom": "0px", "backgroundColor": "black"},
        ),
    ],
)


# Clientside callback to set cookie on page load
app.clientside_callback(
    f"""
    function(data) {{
        const d = new Date();
        d.setTime(d.getTime() + (30*24*60*60*1000));
        const expires = "expires=" + d.toUTCString();
        document.cookie = "app_version={APP_VERSION};" + expires + ";path=/";

        return "Cookie 'app_version=5' has been set successfully!";
    }}
    """,
    Output("cookie-status", "children"),
    Input("page-load", "data"),
)


@app.callback(Output("hexbin-map", "figure"), Input("hexbin-slider", "value"))
def update_hexbin_map(month_index):
    start = time.perf_counter()
    selected_month = available_months[month_index]
    month_str = selected_month.strftime("%B %Y")

    df_month = df_311[df_311["date"].dt.to_period("M").dt.to_timestamp() == selected_month]
    if df_month.empty:
        return go.Figure()

    # Prepare hexbin
    df_month["count"] = 1
    grouped = df_month.groupby(["latitude", "longitude", "category"]).size().reset_index(name="count")
    pivot = grouped.pivot_table(index=["latitude", "longitude"], columns="category", values="count", fill_value=0).reset_index()
    pivot["total_count"] = pivot.drop(columns=["latitude", "longitude"]).sum(axis=1)

    fig = create_hexbin_mapbox(data_frame=pivot, lat="latitude", lon="longitude", nx_hexagon=20, agg_func=np.sum, color="total_count", opacity=0.7, color_continuous_scale=px.colors.sequential.Plasma[::-1], mapbox_style="carto-darkmatter", center=dict(lat=42.304, lon=-71.07), zoom=11.9, min_count=1, labels={"total_count": "311 Requests"})
    fig.data[0].hovertemplate = "incidents = %{z}<extra></extra>"

    fig.update_coloraxes(colorbar=dict(title=dict(text="311 Requests", font=dict(size=12, color="white")), orientation="h", x=0.5, y=1.0, xanchor="center", len=0.5, thickness=12, tickfont=dict(size=10, color="white"), bgcolor="rgba(0,0,0,0)"))

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
                fig.add_trace(go.Scattermapbox(lat=lats, lon=lons, mode="lines", line=dict(color=color, width=3), name=f"District {district_code}", legendgroup=f"District {district_code}", showlegend=(i == 0), hoverinfo="skip"))

        except Exception as e:
            print(f"district {district_code} boundary not added", e)

    dorchester_url = "https://gis.bostonplans.org/hosting/rest/services/Hosted/Boston_Neighborhood_Boundaries/FeatureServer/1/query"
    params = {"where": "name='Dorchester'", "outFields": "*", "f": "geojson", "outSR": "4326"}

    try:

        resp = requests.get(dorchester_url, params=params)

        if resp.status_code != 200:

            raise Exception(f"Request failed with status code {resp.status_code}")

        geojson = resp.json()
        features = geojson.get("features", [])

        if not features:
            print("no features found in geojson")
        else:
            geometry = features[0].get("geometry", {})
            print("geometry type:", geometry.get("type"))

            if geometry["type"] == "Polygon":
                polygons = [geometry["coordinates"]]
            elif geometry["type"] == "MultiPolygon":
                polygons = geometry["coordinates"]
            else:
                print("unexpected geometry type:", geometry["type"])
                polygons = []

            for i, polygon in enumerate(polygons):
                for j, ring in enumerate(polygon):
                    show = i == 0 and j == 0
                    lons = [pt[0] for pt in ring] + [ring[0][0]]
                    lats = [pt[1] for pt in ring] + [ring[0][1]]
                    fig.add_trace(go.Scattermapbox(lat=lats, lon=lons, mode="lines", line=dict(color="white", width=3), name="Neighborhood: Dorchester", legendgroup="Neighborhood: Dorchester", showlegend=show, hoverinfo="skip"))
            print("dorchester boundary successfully added.")

    except Exception as e:
        print("dorchester boundary not added:", e)

    df_month_shots = df_shots[df_shots["month"] == selected_month]
    confirmed = df_month_shots[df_month_shots["ballistics_evidence"] == 1]
    unconfirmed = df_month_shots[df_month_shots["ballistics_evidence"] == 0]

    hom_this_month = df_hom_shot_matched[df_hom_shot_matched["month"] == selected_month].copy()
    hom_this_month["latitude"] += 0.0020
    hom_this_month["longitude"] += 0.0020

    fig.add_trace(go.Scattermapbox(lat=confirmed["latitude"], lon=confirmed["longitude"], mode="markers", name="Confirmed (Ballistic)", marker=dict(color="red", size=9, opacity=1), hoverinfo="text", text=confirmed["date"].dt.strftime("%Y-%m-%d %H:%M")))

    fig.add_trace(go.Scattermapbox(lat=unconfirmed["latitude"], lon=unconfirmed["longitude"], mode="markers", name="Unconfirmed", marker=dict(color="#1E90FF", size=7, opacity=1), hoverinfo="text", text=unconfirmed["date"].dt.strftime("%Y-%m-%d %H:%M")))

    fig.add_trace(go.Scattermapbox(lat=hom_this_month["latitude"], lon=hom_this_month["longitude"], mode="markers", name="Matched Homicides", marker=dict(color="limegreen", size=10, opacity=1), hoverinfo="text", text=hom_this_month["date"].dt.strftime("%Y-%m-%d %H:%M")))

    fig.update_layout(
        title=f"311 Requests + Shots Fired + Homicides ({month_str})",
        title_font=dict(size=18, color="white"),
        title_x=0.5,
        paper_bgcolor="black",
        plot_bgcolor="black",
        font_color="white",
        legend=dict(orientation="h", x=0.5, y=0.01, xanchor="center", font=dict(color="white"), bgcolor="rgba(0,0,0,0)", bordercolor="rgba(255,255,255,0.2)", borderwidth=1),
    )
    print(f"[TIMER] update_hexbin_map ({month_str}) took {time.perf_counter() - start:.2f} seconds")
    return fig


@app.callback(
    [Output("chat-history-store", "data"),
     Output("chat-display", "children"),
     Output("chat-input", "value")],
    [Input("send-button", "n_clicks"),
     Input("hexbin-slider", "value")],
    [State("chat-input", "value"),
     State("chat-history-store", "data")]
)
def handle_chat_simple(n_clicks, slider_val, user_input, history):
    start = time.perf_counter()
    triggered_id = ctx.triggered_id

    if history is None:
        history = []

    selected_date = available_months[slider_val].strftime("%B %Y")
    selected_month_str = available_months[slider_val].strftime("%Y-%m")

    if triggered_id == "hexbin-slider":
        history = []
        try:
            response = requests.get(f"{API_BASE_URL}/llm_summaries?month={selected_month_str}")
            response.raise_for_status()
            reply = response.json().get("summary", "[No summary available]")
        except Exception as e:
            reply = f"[Error fetching summary for {selected_month_str}: {e}]"

    elif triggered_id == "send-button":
        if not user_input or not user_input.strip():
            raise PreventUpdate
        history.append(("You", user_input.strip()))
        prompt = (
            f"The data shows 311 service requests and 911 incidents for {selected_date} in Boston neighborhoods.\n\n"
            f"311 data reflects concerns about neighborhood conditions and quality of life. The request types are grouped into four major categories:\n"
            "- **Living Conditions**: 'Poor Conditions of Property', 'Needle Pickup', 'Unsatisfactory Living Conditions', "
            "'Rodent Activity', 'Heat - Excessive Insufficient', 'Unsafe Dangerous Conditions', 'Pest Infestation - Residential'\n"
            "- **Trash, Recycling, And Waste**: 'Missed Trash/Recycling/Yard Waste/Bulk Item', 'Schedule a Bulk Item Pickup', 'CE Collection', "
            "'Schedule a Bulk Item Pickup SS', 'Request for Recycling Cart', 'Illegal Dumping'\n"
            "- **Streets, Sidewalks, And Parks**: 'Requests for Street Cleaning', 'Request for Pothole Repair', 'Unshoveled Sidewalk', "
            "'Tree Maintenance Requests', 'Sidewalk Repair (Make Safe)', 'Street Light Outages', 'Sign Repair', 'Pothole'\n"
            "- **Parking**: 'Parking Enforcement', 'Space Savers', 'Parking on Front/Back Yards (Illegal Parking)', 'Municipal Parking Lot Complaints', "
            "'Valet Parking Problems', 'Private Parking Lot Complaints'\n\n"
            f"911 data includes reported homicides and shots fired, indicating incidents of violent crime.\n\n"
            f"Text content includes quotes from community meetings and interviews. Some residents believe violence is decreasing, while others still feel unsafe. "
            f"Concerns range from housing quality and trash overflow to gang activity and street-level violence.\n\n"
            f"Using both data and text content, explain how these two types of information reflect community safety. "
            f"Describe why there might be disagreement between what the data shows and how people feel. "
            f"Point out notable spikes, drops, or emerging patterns in the data for {selected_date}, and connect them to lived experiences and perceptions. "
            f"Use the grouped 311 categories and the 911 incident data together to provide a holistic, narrative-driven analysis.\n\n"
            f"User's question: {user_input.strip()}"
        )

        try:
            response = requests.post(
                f"{API_BASE_URL}/chat?context_request=experiment_5",
                headers={"Content-Type": "application/json"},
                json={"client_query": prompt, "app_version": f"{APP_VERSION}"}
            )
            response.raise_for_status()
            reply = response.json().get("response", "[No reply received]")
        except Exception as e:
            reply = f"[Error: {e}]"

    else:
        raise PreventUpdate

    history.append(("Assistant", reply))
    print(f"[TIMER] handle_chat_simple triggered by {triggered_id} took {time.perf_counter() - start:.2f} seconds")
    return history, chat_display_div(history), ""




server = app.server
print(f"[TIMER] Total Dash app setup time: {time.perf_counter() - global_start:.2f} seconds")

if __name__ == "__main__":
    app.run(debug=True)
