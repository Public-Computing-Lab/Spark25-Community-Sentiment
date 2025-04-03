import os
import time
import requests
import numpy as np
import pandas as pd
from urllib.parse import quote_plus
from dotenv import load_dotenv
from sqlalchemy import create_engine
from dash import Dash, dcc, html, ctx
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate
import plotly.express as px
import plotly.graph_objects as go
from plotly.figure_factory import create_hexbin_mapbox


global_start = time.perf_counter()

load_dotenv()

PORT = os.getenv("EXPERIMENT_5_PORT")
DASH_REQUESTS_PATHNAME = os.getenv("EXPERIMENT_5_DASH_REQUESTS_PATHNAME")

raw_type_to_category = {
    "Poor Conditions of Property": "Living Conditions",
    "Needle Pickup": "Living Conditions",
    "Unsatisfactory Living Conditions": "Living Conditions",
    "Rodent Activity": "Living Conditions",
    "Heat - Excessive Insufficient": "Living Conditions",
    "Unsafe Dangerous Conditions": "Living Conditions",
    "Pest Infestation - Residential": "Living Conditions",
    "Missed Trash/Recycling/Yard Waste/Bulk Item": "Trash, Recycling, And Waste",
    "Schedule a Bulk Item Pickup": "Trash, Recycling, And Waste",
    "CE Collection": "Trash, Recycling, And Waste",
    "Schedule a Bulk Item Pickup SS": "Trash, Recycling, And Waste",
    "Request for Recycling Cart": "Trash, Recycling, And Waste",
    "Illegal Dumping": "Trash, Recycling, And Waste",
    "Requests for Street Cleaning": "Streets, Sidewalks, And Parks",
    "Request for Pothole Repair": "Streets, Sidewalks, And Parks",
    "Unshoveled Sidewalk": "Streets, Sidewalks, And Parks",
    "Tree Maintenance Requests": "Streets, Sidewalks, And Parks",
    "Sidewalk Repair (Make Safe)": "Streets, Sidewalks, And Parks",
    "Street Light Outages": "Streets, Sidewalks, And Parks",
    "Sign Repair": "Streets, Sidewalks, And Parks",
    "Pothole": "Streets, Sidewalks, And Parks",
    "Parking Enforcement": "Parking",
    "Space Savers": "Parking",
    "Parking on Front/Back Yards (Illegal Parking)": "Parking",
    "Municipal Parking Lot Complaints": "Parking",
    "Valet Parking Problems": "Parking",
    "Private Parking Lot Complaints": "Parking",
}

districts = {"B3": "rgba(255, 255, 0, 0.7)", "B2": "rgba(0, 255, 255, 0.7)", "C11": "rgba(0, 255, 0, 0.7)"}
boston_url = "https://gisportal.boston.gov/ArcGIS/rest/services/PublicSafety/OpenData/MapServer/5/query"

type_to_category = {k.strip().title(): v for k, v in raw_type_to_category.items()}


def get_db_engine():
    user = os.getenv("DB_USER")
    password = quote_plus(os.getenv("DB_PASSWORD"))
    host = os.getenv("DB_HOST")
    db = os.getenv("DB_NAME")

    return create_engine(f"mysql+pymysql://{user}:{password}@{host}/{db}")


CACHE_DIR = "./cache"
os.makedirs(CACHE_DIR, exist_ok=True)


def cache_stale(path, max_age_minutes=30):
    return not os.path.exists(path) or (time.time() - os.path.getmtime(path)) > max_age_minutes * 60


def load_311_data(force_refresh=False):
    cache_path = os.path.join(CACHE_DIR, "df_311.parquet")
    if not force_refresh and not cache_stale(cache_path):
        print("[CACHE] Using cached 311 data")
        return pd.read_parquet(cache_path)

    print("[LOAD] Fetching 311 data from API...")
    url = "https://boston.ourcommunity.is/api/data/query?request=311_by_geo&category=all&app_version=0.5.1"
    df = pd.DataFrame(requests.get(url).json())

    df.rename(columns={"open_dt": "date"}, inplace=True)
    df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
    df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df.dropna(subset=["latitude", "longitude", "date"], inplace=True)
    df["normalized_type"] = df["type"].str.strip().str.title()

    # valid_districts = ["B2", "B3", "C11"]
    # df = df[df["police_district"].isin(valid_districts)]

    df = df[(df["latitude"] > 40) & (df["latitude"] < 43) & (df["longitude"] > -72) & (df["longitude"] < -70)]

    df.to_parquet(cache_path, index=False)
    return df


def load_homicide_data(engine, force_refresh=False):
    cache_path = os.path.join(CACHE_DIR, "df_homicide.parquet")
    if not force_refresh and not cache_stale(cache_path):
        print("[CACHE] Using cached homicide data")
        df = pd.read_parquet(cache_path)
    else:
        print("[LOAD] Fetching homicide data from DB...")
        df = pd.read_sql("SELECT homicide_date AS date FROM homicide_data", con=engine)
        df["date"] = pd.to_datetime(df["date"])
        df.to_parquet(cache_path, index=False)

    df["day"] = df["date"].dt.date
    return df


def load_shots_fired_data(engine, df_hom, force_refresh=False):
    cache_path_shots = os.path.join(CACHE_DIR, "df_shots.parquet")
    cache_path_matched = os.path.join(CACHE_DIR, "df_hom_shot_matched.parquet")

    if not force_refresh and not cache_stale(cache_path_shots) and not cache_stale(cache_path_matched):
        df = pd.read_parquet(cache_path_shots)
        df_matched = pd.read_parquet(cache_path_matched)
        return df, df_matched

    print("[LOAD] Fetching shots fired data from API...")
    url = "http://boston.ourcommunity.is/api/data/query?app_version=0.5.1&request=911_shots_fired"
    resp = requests.get(url)
    resp.raise_for_status()
    df = pd.DataFrame(resp.json())

    df.rename(columns={"incident_date_time": "date"}, inplace=True)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["ballistics_evidence"] = pd.to_numeric(df["ballistics_evidence"], errors="coerce")
    df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
    df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")

    df.dropna(subset=["latitude", "longitude", "date"], inplace=True)
    df = df[df["ballistics_evidence"].isin([0, 1])]
    df["month"] = df["date"].dt.to_period("M").dt.to_timestamp()
    df["day"] = df["date"].dt.date

    confirmed = df[df["ballistics_evidence"] == 1].copy()
    hom_days_set = set(df_hom["day"])
    matched = confirmed[confirmed["day"].apply(lambda d: any((d + pd.Timedelta(days=offset)) in hom_days_set for offset in [-1, 0, 1]))]
    matched["month"] = matched["date"].dt.to_period("M").dt.to_timestamp()

    df.to_parquet(cache_path_shots, index=False)
    matched.to_parquet(cache_path_matched, index=False)

    return df, matched


engine = get_db_engine()
df_hom = load_homicide_data(engine)
df_shots, df_hom_shot_matched = load_shots_fired_data(engine, df_hom)
df_311 = load_311_data()
engine.dispose()

df_311["category"] = df_311["normalized_type"].map(type_to_category)


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
    """
    function(data) {
        const d = new Date();
        d.setTime(d.getTime() + (30*24*60*60*1000));
        const expires = "expires=" + d.toUTCString();
        document.cookie = "app_version=5;" + expires + ";path=/";

        return "Cookie 'app_version=5' has been set successfully!";
    }
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


@app.callback([Output("chat-history-store", "data"), Output("chat-display", "children"), Output("chat-input", "value")], [Input("send-button", "n_clicks"), Input("hexbin-slider", "value")], [State("chat-input", "value"), State("chat-history-store", "data")])
def handle_chat_simple(n_clicks, slider_val, user_input, history):
    start = time.perf_counter()
    triggered_id = ctx.triggered_id

    if history is None:
        history = []

    selected_date = available_months[slider_val].strftime("%B %Y")

    if triggered_id == "hexbin-slider":
        history = []
        prompt = (
            f"Provide a professional summary of key trends in the city's safety and service data for {selected_date}. "
            f"Use both 311 service request data (grouped into four categories: Living Conditions, Trash/Recycling/Waste, "
            f"Streets/Sidewalks/Parks, and Parking) and 911 incident data (homicides and shots fired). "
            f"Highlight any significant changes, spikes, or drops in activity across these categories. "
            f"Where applicable, connect these trends to potential implications for neighborhood safety or quality of life. "
            f"This summary should help stakeholders understand the most relevant patterns in the data for this time period."
        )
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

    else:

        raise PreventUpdate

    try:
        response = requests.post("https://boston.ourcommunity.is/api/chat?context_request=experiment_5", headers={"Content-Type": "application/json"}, json={"client_query": prompt, "app_version": "5"})
        response.raise_for_status()
        reply = response.json().get("response", "[No reply received]")
    except Exception as e:
        reply = f"[Error: {e}]"

    history.append(("Assistant", reply))
    print(f"[TIMER] handle_chat_simple triggered by {triggered_id} took {time.perf_counter() - start:.2f} seconds")
    return history, chat_display_div(history), ""


server = app.server
print(f"[TIMER] Total Dash app setup time: {time.perf_counter() - global_start:.2f} seconds")

if __name__ == "__main__":
    app.run(debug=True)
