import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from dash import Dash, dcc, html
import plotly.graph_objects as go
import plotly.express as px
from sqlalchemy import create_engine
from dash.dependencies import Input, Output, State
from dotenv import load_dotenv
import os
from sqlalchemy import create_engine
from urllib.parse import quote_plus
from dash import html
from dash import ctx, dcc


load_dotenv()

PORT = os.getenv("EXPERIMENT_5_PORT")
DASH_REQUESTS_PATHNAME = os.getenv("EXPERIMENT_5_DASH_REQUESTS_PATHNAME")

def get_db_engine():
    user = os.getenv("DB_USER")
    password = quote_plus(os.getenv("DB_PASSWORD"))
    host = os.getenv("DB_HOST")
    db = os.getenv("DB_NAME")

    return create_engine(f"mysql+pymysql://{user}:{password}@{host}/{db}")

PORT = os.getenv("EXPERIMENT_5_PORT")
DASH_REQUESTS_PATHNAME = os.getenv("EXPERIMENT_5_DASH_REQUESTS_PATHNAME")

engine = get_db_engine()

raw_type_to_category = {
    'Poor Conditions of Property': 'Living Conditions',
    'Needle Pickup': 'Living Conditions',
    'Unsatisfactory Living Conditions': 'Living Conditions',
    'Rodent Activity': 'Living Conditions',
    'Heat - Excessive Insufficient': 'Living Conditions',
    'Unsafe Dangerous Conditions': 'Living Conditions',
    'Pest Infestation - Residential': 'Living Conditions',
    'Missed Trash/Recycling/Yard Waste/Bulk Item': 'Trash, Recycling, And Waste',
    'Schedule a Bulk Item Pickup': 'Trash, Recycling, And Waste',
    'CE Collection': 'Trash, Recycling, And Waste',
    'Schedule a Bulk Item Pickup SS': 'Trash, Recycling, And Waste',
    'Request for Recycling Cart': 'Trash, Recycling, And Waste',
    'Illegal Dumping': 'Trash, Recycling, And Waste',
    'Requests for Street Cleaning': 'Streets, Sidewalks, And Parks',
    'Request for Pothole Repair': 'Streets, Sidewalks, And Parks',
    'Unshoveled Sidewalk': 'Streets, Sidewalks, And Parks',
    'Tree Maintenance Requests': 'Streets, Sidewalks, And Parks',
    'Sidewalk Repair (Make Safe)': 'Streets, Sidewalks, And Parks',
    'Street Light Outages': 'Streets, Sidewalks, And Parks',
    'Sign Repair': 'Streets, Sidewalks, And Parks',
    'Pothole': 'Streets, Sidewalks, And Parks',
    'Parking Enforcement': 'Parking',
    'Space Savers': 'Parking',
    'Parking on Front/Back Yards (Illegal Parking)': 'Parking',
    'Municipal Parking Lot Complaints': 'Parking',
    'Valet Parking Problems': 'Parking',
    'Private Parking Lot Complaints': 'Parking',
}

districts = {
    "B3": "rgba(255, 255, 0, 0.7)",  
    "B2": "rgba(0, 255, 255, 0.7)",   
    "C11": "rgba(0, 255, 0, 0.7)"     
}
boston_url = "https://gisportal.boston.gov/ArcGIS/rest/services/PublicSafety/OpenData/MapServer/5/query"

type_to_category = {
    k.strip().title(): v for k, v in raw_type_to_category.items()
}

allowed_types = list(type_to_category.keys())
types_str = "', '".join(allowed_types)

import requests

api_url = "https://boston.ourcommunity.is/api/data/query?request=311_by_geo&category=all"


resp = requests.get(api_url)
resp.raise_for_status()

# Parse as list of dicts
data = resp.json()

# Now make DataFrame
df_311 = pd.DataFrame(data)

df_311.rename(columns={'open_dt': 'date'}, inplace=True)
df_311['latitude'] = pd.to_numeric(df_311['latitude'], errors='coerce')
df_311['longitude'] = pd.to_numeric(df_311['longitude'], errors='coerce')
df_311['date'] = pd.to_datetime(df_311['date'], errors='coerce')
df_311.dropna(subset=["latitude", "longitude", "date"], inplace=True)

df_311['normalized_type'] = df_311['type'].str.strip().str.title()

df_hom = pd.read_sql("SELECT homicide_date AS date FROM homicide_data", con=engine)

df_shots = pd.read_sql(
    "SELECT incident_date_time AS date, longitude, latitude, ballistics_evidence FROM shots_fired_data",
    con=engine
)

df_shots['ballistics_evidence'] = pd.to_numeric(df_shots['ballistics_evidence'], errors='coerce')
df_shots = df_shots[df_shots['ballistics_evidence'].isin([0, 1])]

engine.dispose()  

df_311['category'] = df_311['normalized_type'].map(type_to_category)
valid_districts = ['B2', 'B3', 'C11']
df_311 = df_311[
    df_311['category'].notna() &
    df_311['police_district'].isin(valid_districts)
]

print("\ncoordinate ranges before filtering:")
print(df_311[['latitude', 'longitude']].describe())

df_311 = df_311[
    (df_311['latitude'] > 40) & (df_311['latitude'] < 43) &  
    (df_311['longitude'] > -72) & (df_311['longitude'] < -70)  
]

print("\ncoordinate ranges after filtering:")
print(df_311[['latitude', 'longitude']].describe())
print("remaining rows:", len(df_311))


df_311['date'] = pd.to_datetime(df_311['date'])
df_hom['date'] = pd.to_datetime(df_hom['date'])
df_shots['date'] = pd.to_datetime(df_shots['date'])
df_shots['date'] = pd.to_datetime(df_shots['date'])
df_shots = df_shots.dropna(subset=['latitude', 'longitude'])


df_shots = df_shots[
    (df_shots['latitude'] > 40) & (df_shots['latitude'] < 43) &
    (df_shots['longitude'] > -72) & (df_shots['longitude'] < -70)
]
df_shots['month'] = df_shots['date'].dt.to_period('M').dt.to_timestamp()
df_shots['month'] = df_shots['date'].dt.to_period('M').dt.to_timestamp()


#preparing coordinates, month, and ballistic evidence
df_shots = df_shots.dropna(subset=["latitude", "longitude", "date"])
df_shots["latitude"] = pd.to_numeric(df_shots["latitude"], errors="coerce")
df_shots["longitude"] = pd.to_numeric(df_shots["longitude"], errors="coerce")
df_shots = df_shots.dropna(subset=["latitude", "longitude"])

df_shots["month"] = df_shots["date"].dt.to_period("M").dt.to_timestamp()

#slider months
available_months = df_shots[
    (df_shots["month"] >= "2018-01-01") & (df_shots["month"] <= "2024-12-31")
]["month"].dropna().sort_values().unique()

month_labels = pd.Series(available_months).dt.strftime('%Y-%m').tolist()
slider_marks = {i: label for i, label in enumerate(month_labels) if i % 3 == 0}


category_colors = {
    'Living Conditions': "#ff7f0e",  
    'Trash, Recycling, And Waste': "#2ca02c",     
   'Streets, Sidewalks, And Parks': "#9467bd",   
   'Parking': "#FFC0CB",
}


#hexbin map
from plotly.figure_factory import create_hexbin_mapbox

df_311 = df_311.dropna(subset=["latitude", "longitude"])

map_center = {
    "lat": df_311["latitude"].mean(),
    "lon": df_311["longitude"].mean()
}


df_311['count'] = 1
grouped = df_311.groupby(['latitude', 'longitude', 'category']).size().reset_index(name='count')
pivot = grouped.pivot_table(index=['latitude', 'longitude'], columns='category', values='count', fill_value=0).reset_index()
pivot['total_count'] = pivot.drop(columns=['latitude', 'longitude']).sum(axis=1)
def format_hover(row):
    parts = [f"{col}: {int(row[col])}" for col in row.index if col not in ['latitude', 'longitude', 'total_count']]
    return f"<b>Total: {int(row['total_count'])}</b><br>" + "<br>".join(parts)

pivot['text'] = pivot.apply(format_hover, axis=1)


fig_map = create_hexbin_mapbox(
    data_frame=pivot,
    lat="latitude",
    lon="longitude",
    nx_hexagon=30,
    agg_func=np.sum,
    color="total_count", 
    opacity=0.7,
    color_continuous_scale="Plasma",
    mapbox_style="carto-darkmatter",
    center=dict(lat=42.304, lon=-71.07),
    zoom=11.5,
    min_count=1,
    labels={"total_count": "311 Requests"}
)
fig_map.update_layout(height=700, width=500)
hexbin_geojson = fig_map.data[0].geojson

fig_map.update_coloraxes(
    colorbar=dict(
        title=dict(
            text="311 Requests",
            font=dict(size=12, color="white")
        ),
        orientation="h",
        x=0.5,
        y=1.1,
        xanchor="center",
        len=0.5,
        thickness=12,
        tickfont=dict(size=10, color="white"),
        bgcolor="rgba(0,0,0,0)"
    )
)

import requests

for district_code, color in districts.items():
    params = {
        "where": f"DISTRICT='{district_code}'",
        "outFields": "DISTRICT",
        "f": "geojson",
        "outSR": "4326"
    }
    try:
        resp = requests.get(boston_url, params=params)
        geojson = resp.json()
        coords = geojson['features'][0]['geometry']['coordinates']
        poly_list = coords if isinstance(coords[0][0][0], float) else [p[0] for p in coords]
        for poly in poly_list:
            lons = [pt[0] for pt in poly]
            lats = [pt[1] for pt in poly]
            lons.append(poly[0][0]); lats.append(poly[0][1])
            fig_map.add_trace(go.Scattermapbox(
                lat=lats, lon=lons, mode='lines',
                line=dict(color=color, width=3),
                name=f"District {district_code}",
                legendgroup=f"District {district_code}",
                showlegend=(poly == poly_list[0]),  
                hoverinfo='skip'
            ))

    except Exception as e:
        print(f"district {district_code} boundary not added", e)



center_lat = map_center["lat"]
center_lon = map_center["lon"]

print(f"map center set to: lat={center_lat}, lon={center_lon}")

fig_map.update_layout(
    mapbox=dict(
        style="carto-darkmatter",
        center=dict(lat=42.29, lon=-71.08),  # adjust center
        zoom=12.2,  # tighter zoom
        bounds=dict(
            west=-71.125,  # left edge
            east=-71.035,  # right edge
            south=42.25,   # bottom edge
            north=42.34    # top edge
        )
    ),
    paper_bgcolor="black",
    plot_bgcolor="black",
    font_color="white",
    legend=dict(
        orientation="v",
        x=1.02,
        y=0.95,
        font=dict(color='white'),
        bgcolor="rgba(0,0,0,0)",
        bordercolor="rgba(255,255,255,0.2)",
        borderwidth=1
    )
)

#legend
for cat, col in category_colors.items():
    fig_map.add_trace(go.Scattermapbox(
        lat=[None], lon=[None], mode='markers',
        marker=dict(size=10, color=col),
        legendgroup=cat, showlegend=True, name=cat, hoverinfo='skip'
    ))

print("cats in filtered df_311:", df_311['category'].unique())


#temporal chart
df_311['month'] = df_311['date'].dt.to_period('M').dt.to_timestamp()  
monthly_counts = df_311.groupby(['month', 'category']).size().reset_index(name='count')
print("type of px:", type(px))  

if monthly_counts.empty:
    print(" no data to plot.")
else:
    fig_timeline = px.area(
        monthly_counts, x='month', y='count', color='category',
        title="311 Requests Over Time by Category",
        color_discrete_map=category_colors,
        labels={"count": "Number of Requests", "month": "Date", "category": "Category"}
    )

print("monthly counts:")
print(monthly_counts.groupby('category')['count'].sum())


fig_timeline.update_layout(
    height=500,
    paper_bgcolor="black", plot_bgcolor="black",
    font_color="white", legend_bgcolor="rgba(0,0,0,0)",
    xaxis=dict(title='Date', color='white', showgrid=False), yaxis=dict(title='311 Requests', color='white', showgrid=False)
)

#trend chart shots fired/ homicides
df_hom['day'] = df_hom['date'].dt.date  
df_shots['day'] = df_shots['date'].dt.date

confirmed_shots = df_shots[df_shots["ballistics_evidence"] == 1].copy()
confirmed_shots["day"] = confirmed_shots["date"].dt.date

hom_days_set = set(df_hom['date'].dt.date)
hom_matched = confirmed_shots[confirmed_shots["day"].apply(lambda d: any((d + pd.Timedelta(days=offset)) in hom_days_set for offset in [-1, 0, 1]))]

df_hom_shot_matched = hom_matched.copy()
df_hom_shot_matched["month"] = df_hom_shot_matched["date"].dt.to_period("M").dt.to_timestamp()


hom_daily = df_hom.groupby('day').size().reset_index(name='homicides')
shots_daily = df_shots.groupby('day').size().reset_index(name='shots')
daily_merge = pd.merge(hom_daily, shots_daily, on='day', how='outer').fillna(0)
daily_merge = daily_merge.sort_values('day')



#dash initiate
app = Dash(__name__, suppress_callback_exceptions=True,serve_locally=False, requests_pathname_prefix=DASH_REQUESTS_PATHNAME)
app.layout = html.Div(style={'backgroundColor': 'black', 'padding': '10px'}, children=[
    html.H1("City Safety Dashboard", style={
        'textAlign': 'center',
        'color': 'white',
        'marginBottom': '15px'
    }),
    dcc.Store(id="chat-history-store", data=[]),
    html.Div([

        html.Div([
            dcc.Graph(id='hexbin-map', style={'height': '800px', 'width': '900px'}),
            html.Div([
                dcc.Graph(id='hover-chart', style={'height': '180px', 'width': '250px'})
            ], id='hover-container', style={
                'display': 'none',
                'backgroundColor': 'rgba(42,42,42,0.95)',
                'borderRadius': '8px',
                'padding': '4px',
                'overflow': 'hidden',
                'position': 'absolute',
                'zIndex': 1000,
                'boxShadow': '2px 2px 12px rgba(0,0,0,0.5)'
            })
        ], style={
            'width': '58%',
            'display': 'inline-block',
            'paddingLeft': '2%',
            'position': 'relative',
            'verticalAlign': 'top'
        }),


        html.Div([
            html.Div("🤖 Assistant", style={
                'color': 'white',
                'fontWeight': 'bold',
                'marginBottom': '8px',
                'fontSize': '16px'
            }),
            html.Div(id='chat-display', style={
                'height': '480px',
                'backgroundColor': '#1a1a1a',
                'color': 'white',
                'border': '1px solid #444',
                'borderRadius': '8px',
                'padding': '10px',
                'overflowY': 'auto',
                'marginBottom': '10px',
                'fontSize': '13px'
            }),
            dcc.Textarea(
                id='chat-input',
                placeholder='Type your question here...',
                style={
                    'width': '100%',
                    'height': '80px',
                    'borderRadius': '8px',
                    'backgroundColor': '#333',
                    'color': 'white',
                    'border': '1px solid #555',
                    'padding': '8px',
                    'resize': 'none',
                    'fontSize': '13px'
                }
            ),
            html.Button("SEND", id='send-button', n_clicks=0, style={
                'marginTop': '8px',
                'width': '100%',
                'backgroundColor': '#ff69b4',
                'color': 'white',
                'border': 'none',
                'borderRadius': '6px',
                'padding': '10px',
                'fontWeight': 'bold',
                'cursor': 'pointer'
            }),


        ], style={
            'width': '38%',
            'display': 'inline-block',
            'paddingLeft': '2%',
            'verticalAlign': 'top'
        })

    ], style={'marginBottom': '2rem'}),

   
    html.Div([
        dcc.Slider(
            id='hexbin-slider',
            min=0,
            max=len(month_labels) - 1,
            step=1,
            value=0,
            marks={i: {'label': label, 'style': {'color': 'white'}} for i, label in slider_marks.items()},
            tooltip={"placement": "bottom", "always_visible": True},
            className='rc-slider-311'
        )
    ], style={
        'width': '100%',
        'margin': '0 auto',
        'paddingTop': '30px',
        'paddingBottom': '0px',
        'backgroundColor': 'black'
    })
])





from dash.dependencies import Input, Output, State
from shapely.geometry import Point, Polygon

@app.callback(
    [Output('hover-chart', 'figure'),
     Output('hover-container', 'style')],
    [Input('hexbin-map', 'hoverData')],
    [State('hexbin-map', 'figure')]
)
def update_hover_chart(hoverData, hexmap_fig):

    if not hoverData or 'points' not in hoverData:
        return go.Figure(), {'display': 'none'}

    point = hoverData['points'][0]

    if 'location' not in point:
        return go.Figure(), {'display': 'none'}

    hex_id = point['location']

    bbox = point.get('bbox', {})

    if not hex_id or 'x0' not in bbox or 'y0' not in bbox:
        return go.Figure(), {'display': 'none'}

    x_pos = bbox['x0']
    y_pos = bbox['y0']

    geojson = hexmap_fig['data'][0].get('geojson')
    if not geojson:

        return go.Figure(), {'display': 'none'}

    coords = None
    for feature in geojson['features']:
        if feature.get('id') == hex_id:
            coords = feature['geometry']['coordinates'][0]
            break

    if not coords:

        return go.Figure(), {'display': 'none'}
    
    

    polygon = Polygon(coords)
    from shapely import vectorized

    lons = df_311['longitude'].values
    lats = df_311['latitude'].values
    mask = vectorized.contains(polygon, lons, lats)
    points_in_hex = df_311[mask]


    print(f"points in hoveredhex: {len(points_in_hex)}")

    if points_in_hex.empty:
        
        return go.Figure(), {'display': 'none'}

    cat_counts = points_in_hex['category'].value_counts().reset_index()
    cat_counts.columns = ['Category', 'Count']
    print("cat counts in hex:\n", cat_counts)

    if cat_counts.empty:
        print("no cat data")
        return go.Figure(), {'display': 'none'}

    fig = px.bar(
        cat_counts, x='Category', y='Count',
        title='311 Requests in Area',
        color='Category',
        color_discrete_map=category_colors
    )
    fig.update_layout(
        height=180, width=250,
        margin=dict(t=30, b=20, l=10, r=10),
        paper_bgcolor='#2a2a2a',  # dark grey
        plot_bgcolor='#2a2a2a',
        font=dict(size=10, color='white'),
        showlegend=False,
        title=dict(font=dict(size=12, color='white'), x=0.5, xanchor='center'),
        xaxis=dict(
            tickangle=-35, 
            tickfont=dict(size=8, color='white'),
            title=None
        ),
        yaxis=dict(
            showgrid=False,
            zeroline=False,
            tickfont=dict(size=8, color='white'),
            title='Count'
        )
    )
   


    style = {
        'position': 'absolute',
        'top': f'{y_pos - 50}px',
        'left': f'{x_pos + 20}px',
        'display': 'block',
        'backgroundColor': '#2a2a2a',  
        'boxShadow': '3px 3px 12px rgba(0,0,0,0.6)',
        'borderRadius': '10px',
        'padding': '6px',
        'zIndex': 1000,
        'border': '1px solid #444'
    }


    print("hover chart is generated")
    return fig, style

def add_district_boundaries(fig):
    for district_code, color in districts.items():
        params = {
            "where": f"DISTRICT='{district_code}'",
            "outFields": "DISTRICT",
            "f": "geojson",
            "outSR": "4326"
        }
        try:
            resp = requests.get(boston_url, params=params)
            geojson = resp.json()
            coords = geojson['features'][0]['geometry']['coordinates']
            poly_list = coords if isinstance(coords[0][0][0], float) else [p[0] for p in coords]
            for poly in poly_list:
                lons = [pt[0] for pt in poly]
                lats = [pt[1] for pt in poly]
                lons.append(poly[0][0]); lats.append(poly[0][1])
                fig.add_trace(go.Scattermapbox(
                    lat=lats, lon=lons, mode='lines',
                    line=dict(color=color, width=3),
                    name=f"District {district_code}",
                    legendgroup=f"District {district_code}",
                    showlegend=(poly == poly_list[0]),  
                    hoverinfo='skip'
                ))

        except Exception as e:
            print(f"district {district_code} boundary not added", e)


@app.callback(
    Output('hexbin-map', 'figure'),
    Input('hexbin-slider', 'value')
)
def update_hexbin_map(month_index):
    selected_month = available_months[month_index]
    month_str = selected_month.strftime('%B %Y')

    df_month = df_311[df_311['date'].dt.to_period('M').dt.to_timestamp() == selected_month]
    if df_month.empty:
        return go.Figure()

    # Prepare hexbin
    df_month['count'] = 1
    grouped = df_month.groupby(['latitude', 'longitude', 'category']).size().reset_index(name='count')
    pivot = grouped.pivot_table(index=['latitude', 'longitude'], columns='category', values='count', fill_value=0).reset_index()
    pivot['total_count'] = pivot.drop(columns=['latitude', 'longitude']).sum(axis=1)
    pivot['text'] = pivot.apply(format_hover, axis=1)

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
        labels={"total_count": "311 Requests"}
    )

    fig.update_coloraxes(colorbar=dict(
        title=dict(text="311 Requests", font=dict(size=12, color="white")),
        orientation="h", x=0.5, y=1.0, xanchor="center", len=0.5,
        thickness=12, tickfont=dict(size=10, color="white"), bgcolor="rgba(0,0,0,0)"
    ))



    # Add district outlines
    for district_code, color in districts.items():
        try:
            params = {
                "where": f"DISTRICT='{district_code}'",
                "outFields": "DISTRICT", "f": "geojson", "outSR": "4326"
            }
            resp = requests.get(boston_url, params=params)
            geojson = resp.json()
            coords = geojson['features'][0]['geometry']['coordinates']
            poly_list = coords if isinstance(coords[0][0][0], float) else [p[0] for p in coords]
            for i, poly in enumerate(poly_list):
                lons = [pt[0] for pt in poly] + [poly[0][0]]
                lats = [pt[1] for pt in poly] + [poly[0][1]]
                fig.add_trace(go.Scattermapbox(
                    lat=lats, lon=lons, mode='lines',
                    line=dict(color=color, width=3),
                    name=f"District {district_code}",
                    legendgroup=f"District {district_code}",
                    showlegend=(i == 0), 
                    hoverinfo='skip'
                ))

        except Exception as e:
            print(f"district {district_code} boundary not added", e)


    dorchester_url = "https://gis.bostonplans.org/hosting/rest/services/Hosted/Boston_Neighborhood_Boundaries/FeatureServer/1/query"
    params = {
        "where": "name='Dorchester'",
        "outFields": "*",
        "f": "geojson",
        "outSR": "4326"
    }

    try:
        
        resp = requests.get(dorchester_url, params=params)


        if resp.status_code != 200:

            raise Exception(f"Request failed with status code {resp.status_code}")

        
        geojson = resp.json()  
        features = geojson.get('features', [])


        if not features:
            print("no features found in geojson")
        else:
            geometry = features[0].get('geometry', {})
            print("geometry type:", geometry.get('type'))

            if geometry['type'] == "Polygon":
                polygons = [geometry['coordinates']]
            elif geometry['type'] == "MultiPolygon":
                polygons = geometry['coordinates']
            else:
                print("unexpected geometry type:", geometry['type'])
                polygons = []

            for i, polygon in enumerate(polygons):
                for j, ring in enumerate(polygon):
                    show = (i == 0 and j == 0)
                    lons = [pt[0] for pt in ring] + [ring[0][0]]
                    lats = [pt[1] for pt in ring] + [ring[0][1]]
                    fig.add_trace(go.Scattermapbox(
                        lat=lats, lon=lons, mode='lines',
                        line=dict(color='white', width=3),
                        name="Neighborhood: Dorchester",
                        legendgroup="Neighborhood: Dorchester",
                        showlegend=show,
                        hoverinfo='skip'
                    ))
            print("dorchester boundary successfully added.")

    except Exception as e:
        print("dorchester boundary not added:", e)


    df_month_shots = df_shots[df_shots["month"] == selected_month]
    confirmed = df_month_shots[df_month_shots["ballistics_evidence"] == 1]
    unconfirmed = df_month_shots[df_month_shots["ballistics_evidence"] == 0]

    hom_this_month = df_hom_shot_matched[df_hom_shot_matched["month"] == selected_month].copy()
    hom_this_month["latitude"] += 0.0020
    hom_this_month["longitude"] += 0.0020


    fig.add_trace(go.Scattermapbox(
        lat=confirmed["latitude"],
        lon=confirmed["longitude"],
        mode="markers",
        name="Confirmed (Ballistic)",
        marker=dict(color="red", size=9, opacity=1),
        hoverinfo="text",
        text=confirmed["date"].dt.strftime('%Y-%m-%d %H:%M')
    ))


    fig.add_trace(go.Scattermapbox(
        lat=unconfirmed["latitude"],
        lon=unconfirmed["longitude"],
        mode="markers",
        name="Unconfirmed",
        marker=dict(color="#1E90FF", size=7, opacity=1),
        hoverinfo="text",
        text=unconfirmed["date"].dt.strftime('%Y-%m-%d %H:%M')
    ))


    fig.add_trace(go.Scattermapbox(
        lat=hom_this_month["latitude"],
        lon=hom_this_month["longitude"],
        mode="markers",
        name="Matched Homicides",
        marker=dict(color="limegreen", size=10, opacity=1),
        hoverinfo="text",
        text=hom_this_month["date"].dt.strftime('%Y-%m-%d %H:%M')
    ))

    fig.update_layout(
        title=f"311 Requests + Shots Fired + Homicides ({month_str})",
        title_font=dict(size=18, color='white'),
        title_x=0.5,
        paper_bgcolor="black",
        plot_bgcolor="black",
        font_color="white",
        legend=dict(
            orientation="h",
            x=0.5,
            y=0.01,
            xanchor="center",
            font=dict(color='white'),
            bgcolor="rgba(0,0,0,0)",
            bordercolor="rgba(255,255,255,0.2)",
            borderwidth=1
        )

    )

    return fig

from dash import ctx
import requests
import json

app.clientside_callback_context = ctx

chat_history = []

def chat_display_div(history):
    return [
        html.Div([
            html.Strong(who + ":", style={"color": "#ff69b4" if who == "You" else "#00ffff"}),
            html.Span(" " + msg, style={"marginLeft": "6px", "fontStyle": "italic"} if msg == "_typing_..." else {"marginLeft": "6px"})
        ], style={"marginBottom": "10px"})
        for who, msg in history
    ]



import dash
from dash import ctx
import time
from dash.exceptions import PreventUpdate
import requests
from dash import callback_context
from dash import callback_context, no_update

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
    from dash.exceptions import PreventUpdate
    import requests

    triggered_id = ctx.triggered_id

    if history is None:
        history = []

    selected_date = available_months[slider_val].strftime('%B %Y')


    if triggered_id == "hexbin-slider":

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
        response = requests.post(
            "https://boston.ourcommunity.is/api/chat?context_request=experiment_5",
            headers={"Content-Type": "application/json"},
            json={"client_query": prompt, "app_version": "5"}
        )
        response.raise_for_status()
        reply = response.json().get("response", "[No reply received]")
    except Exception as e:
        reply = f"[Error: {e}]"

    history.append(("Assistant", reply))
    return history, chat_display_div(history), ""



if __name__ == "__main__":
    app.run_server(debug=True)
