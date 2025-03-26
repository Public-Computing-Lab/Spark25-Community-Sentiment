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


load_dotenv()

PORT = os.getenv("EXPERIMENT_5_PORT")
DASH_REQUESTS_PATHNAME = os.getenv("EXPERIMENT_5_DASH_REQUESTS_PATHNAME")

def get_db_engine():
    user = os.getenv("DB_USER")
    password = quote_plus(os.getenv("DB_PASS"))
    host = os.getenv("DB_HOST")
    db = os.getenv("DB_NAME")

    return create_engine(f"mysql+pymysql://{user}:{password}@{host}/{db}")


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
    "B3": "#FFFF00",   
    "B2": "#00FFFF",   
    "C11": "#00FF00"   
}

boston_url = "https://gisportal.boston.gov/ArcGIS/rest/services/PublicSafety/OpenData/MapServer/5/query"

type_to_category = {
    k.strip().title(): v for k, v in raw_type_to_category.items()
}

allowed_types = list(type_to_category.keys())
types_str = "', '".join(allowed_types)

query_311 = "SELECT type, latitude, longitude, DATE(open_dt) AS date, police_district FROM bos311_data"
df_311 = pd.read_sql(query_311, con=engine)
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
    nx_hexagon=45,
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


import plotly.graph_objects as go

daily_merge_sorted = daily_merge.sort_values('day')

smoothed_hom = daily_merge_sorted['homicides'].rolling(window=7).mean()
smoothed_shots = daily_merge_sorted['shots'].rolling(window=7).mean()

fig_crime_timeline = go.Figure()

# homicides 
fig_crime_timeline.add_trace(go.Scatter(
    x=daily_merge_sorted['day'],
    y=daily_merge_sorted['homicides'],
    mode='lines',
    line=dict(color='#FF0000', width=2),
    name='Homicides',
    hovertemplate='Homicides: %{y}<extra></extra>',
    line_shape='spline'
))

#homicides smoothed overlay
fig_crime_timeline.add_trace(go.Scatter(
    x=daily_merge_sorted['day'],
    y=smoothed_hom,
    mode='lines',
    line=dict(color='rgba(255,0,0,0.3)', width=2, dash='dot'),
    name='Homicides (7d Avg)',
    hoverinfo='skip',
    line_shape='spline'
))

#shotsfired
fig_crime_timeline.add_trace(go.Scatter(
    x=daily_merge_sorted['day'],
    y=daily_merge_sorted['shots'],
    mode='lines',
    line=dict(color='#FFD700', width=2),
    name='Shots Fired',
    hovertemplate='Shots Fired: %{y}<extra></extra>',
    line_shape='spline'
))

#shots fired smooth
fig_crime_timeline.add_trace(go.Scatter(
    x=daily_merge_sorted['day'],
    y=smoothed_shots,
    mode='lines',
    line=dict(color='rgba(255,215,0,0.3)', width=2, dash='dot'),
    name='Shots Fired (7d Avg)',
    hoverinfo='skip',
    line_shape='spline'
))


fig_crime_timeline.update_xaxes(range=[pd.to_datetime("2018-01-01"), pd.to_datetime("2024-12-31")])

fig_crime_timeline.update_layout(
    title="Homicides vs. Shots Fired (Daily, with 7-Day Smoothing)",
    title_font=dict(size=18, color='white'),
    height=420,
    paper_bgcolor="black",
    plot_bgcolor="black",
    font_color="white",
    legend_bgcolor="rgba(0,0,0,0)",
    xaxis=dict(title='Date', color='white'),
    yaxis=dict(title='Incidents per Day', color='white')
)


#pie chart
hom_days = set(df_hom['day'])
shot_days = set(df_shots['day'])
matched = sum(1 for d in hom_days if any((d + pd.Timedelta(days=off)) in shot_days for off in [-1, 0, 1]))
no_match = len(hom_days) - matched
pie_data = pd.DataFrame({
    "Category": ["Homicide with Shots±1d", "Homicide without Shots"], 
    "Count": [matched, no_match]
})
fig_pie = px.pie(
    pie_data, names='Category', values='Count',
    color='Category', color_discrete_map={
        "Homicide with Shots±1d": "#FFD700",  
        "Homicide without Shots": "#1f77b4"  
    }
)
fig_pie.update_traces(textfont_color='white')
fig_pie.update_layout(
    title="Homicides With vs. Without Shots Fired (±1 Day)",
    title_font=dict(size=16, color='white'),
    height=300,
    paper_bgcolor="black", font_color="white",
    legend_bgcolor="rgba(0,0,0,0)"
)

#dash initiate
app = Dash(__name__, suppress_callback_exceptions=True,serve_locally=False, requests_pathname_prefix=DASH_REQUESTS_PATHNAME)
app.layout = html.Div(style={'backgroundColor': 'black', 'padding': '10px'}, children=[
    html.H1("City Safety Dashboard", style={
        'textAlign': 'center',
        'color': 'white',
        'marginBottom': '15px'
    }),


    html.Div([

        html.Div([
            dcc.Graph(id='hexbin-map', style={'height': '620px'}),
            html.Div([
                dcc.Graph(id='hover-chart', style={'height': '250px', 'width': '280px'})
            ], id='hover-container', style={'display': 'none'})
        ], style={
            'width': '58%',
            'display': 'inline-block',
            'paddingLeft': '2%',
            'position': 'relative'
        }),


        html.Div([

            html.Div([
                dcc.Graph(
                    id='temporal-chart',
                    figure=fig_timeline,
                    style={'height': '620px', 'width': '100%'}
                )
            ], style={
                'overflow': 'visible', 
                'position': 'relative'
            }),

            html.Div([
                dcc.Slider(
                    id='hexbin-slider',
                    min=0,
                    max=len(month_labels) - 1,
                    step=1,
                    value=0,
                    marks=slider_marks,
                    tooltip={"placement": "top", "always_visible": True},
                    className='rc-slider-311'
                )
            ], style={
                'width': '100%',
                'paddingTop': '12px',
                'paddingBottom': '24px',
                'display': 'flex',
                'justifyContent': 'flex-start'
            })
        ], style={
            'width': '40%',
            'display': 'inline-block',
            'verticalAlign': 'top'
        })
    ], style={'marginBottom': '2rem'}),


    html.Div([
        html.Div([
            dcc.Dropdown(
                id='crime-year-dropdown',
                options=[{'label': str(year), 'value': year} for year in range(2018, 2025)],
                value=2018,
                style={'width': '200px', 'marginBottom': '10px'}
            ),
            dcc.Graph(id='crime-timeline', style={'height': '500px'}),
        ], style={'flex': '2'}),  

        dcc.Graph(id='crime-pie', figure=fig_pie, style={'flex': '1'})
    ], style={'display': 'flex', 'gap': '2rem'}),



    html.Div([
        html.H3("Shots Fired Map (Confirmed vs Unconfirmed)", style={'color': 'white', 'textAlign': 'center'}),
        dcc.Slider(
            id='shots-slider',
            min=0, max=len(month_labels) - 1, step=1, value=0,
            marks=slider_marks,
            tooltip={"placement": "top", "always_visible": True}
        ),
        dcc.Graph(id='shots-fired-map', style={'height': '600px'})
    ], style={'marginTop': '3rem'})

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
    print("\n hover triggered")

    if not hoverData or 'points' not in hoverData:
        print("no data")
        return go.Figure(), {'display': 'none'}

    point = hoverData['points'][0]
    print("hovered point:", point)

    hex_id = point.get('location')
    bbox = point.get('bbox', {})
    print("hex_id:", hex_id)
    print("(bbox):", bbox)

    if not hex_id or 'x0' not in bbox or 'y0' not in bbox:
        print("missing hexid")
        return go.Figure(), {'display': 'none'}

    x_pos = bbox['x0']
    y_pos = bbox['y0']

    geojson = hexmap_fig['data'][0].get('geojson')
    if not geojson:
        print("no geojson found")
        return go.Figure(), {'display': 'none'}

    coords = None
    for feature in geojson['features']:
        if feature.get('id') == hex_id:
            coords = feature['geometry']['coordinates'][0]
            break

    if not coords:
        print("no matching polygon for hexid")
        return go.Figure(), {'display': 'none'}
    
    print("coordinates found")

    polygon = Polygon(coords)
    points_in_hex = df_311[df_311.apply(
        lambda row: polygon.contains(Point(row['longitude'], row['latitude'])), axis=1)]

    print(f"points in hoveredhex: {len(points_in_hex)}")

    if points_in_hex.empty:
        print("no data points")
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
        height=200, width=280,
        margin=dict(t=30, b=10, l=5, r=5),
        paper_bgcolor='white', plot_bgcolor='white',
        font=dict(size=10), showlegend=False
    )
    fig.update_traces(marker_line_color='black', marker_line_width=1)

    style = {
        'position': 'absolute',
        'top': f'{y_pos - 60}px',
        'left': f'{x_pos + 20}px',
        'display': 'block',
        'backgroundColor': 'white',
        'boxShadow': '2px 2px 10px rgba(0,0,0,0.3)',
        'borderRadius': '8px',
        'padding': '5px',
        'zIndex': 1000
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
    Output('shots-fired-map', 'figure'),
    Input('shots-slider', 'value')
)
def update_shots_map(month_index):
    selected_month = month_labels[month_index]
    month_dt = pd.to_datetime(selected_month)

    df_month = df_shots[df_shots["month"] == month_dt]
    if df_month.empty:
        print(f"no data for month: {selected_month}")
        return go.Figure()

    confirmed = df_month[df_month["ballistics_evidence"] == 1]
    unconfirmed = df_month[df_month["ballistics_evidence"] == 0]

    hom_this_month = df_hom_shot_matched[df_hom_shot_matched["month"] == month_dt].copy()
    hom_this_month["latitude"] += 0.0020
    hom_this_month["longitude"] += 0.0020
    print("matched homicides:", len(hom_this_month))
    print(hom_this_month[['latitude', 'longitude', 'date']].head())


    fig = go.Figure()

    #confirmed
    fig.add_trace(go.Scattermapbox(
        lat=confirmed["latitude"],
        lon=confirmed["longitude"],
        mode="markers",
        name="Confirmed (Ballistic)",
        marker=dict(color="red", size=9, opacity=1),
        hoverinfo="text",
        text=confirmed["date"].dt.strftime('%Y-%m-%d %H:%M')
    ))

    #not confirmed
    fig.add_trace(go.Scattermapbox(
        lat=unconfirmed["latitude"],
        lon=unconfirmed["longitude"],
        mode="markers",
        name="Unconfirmed",
        marker=dict(color="#1E90FF", size=7, opacity=1),
        hoverinfo="text",
        text=unconfirmed["date"].dt.strftime('%Y-%m-%d %H:%M')
    ))

    #homcidices
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
        mapbox=dict(
            style="carto-darkmatter",
            center=dict(lat=42.304, lon=-71.07),
            zoom=11.8
        ),
        paper_bgcolor="black",
        plot_bgcolor="black",
        font_color="white",
        title=f"Shots Fired Map with Matched Homicides ({selected_month})",
        margin=dict(l=0, r=0, t=40, b=0),
        legend=dict(
            orientation="v",
            x=1.01, y=1,
            bgcolor="rgba(0,0,0,0)",
            font=dict(size=12)
        )
    )

    add_district_boundaries(fig)
    return fig


@app.callback(
    Output('crime-timeline', 'figure'),
    Input('crime-year-dropdown', 'value')  
)
def update_crime_timeline(selected_year):
    if not selected_year:
        selected_year = 2018
    selected_year = int(selected_year)
    start = pd.to_datetime(f"{selected_year}-01-01")
    end = pd.to_datetime(f"{selected_year}-12-31")

    daily_merge['day'] = pd.to_datetime(daily_merge['day'])
    daily_merge_sorted = daily_merge.sort_values('day')
    filtered_df = daily_merge_sorted[
        (daily_merge_sorted['day'] >= start) & (daily_merge_sorted['day'] <= end)
    ]

    smoothed_hom = filtered_df['homicides'].rolling(window=7, center=True).mean()
    smoothed_shots = filtered_df['shots'].rolling(window=7, center=True).mean()

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=filtered_df['day'],
        y=smoothed_hom,
        customdata=np.stack([filtered_df['homicides']], axis=-1),
        hovertemplate="Homicides: %{customdata[0]}<extra></extra>",
        mode='lines',
        name='Homicides',
        line=dict(color='#FF0000', width=2),
        line_shape='spline'
    ))

    fig.add_trace(go.Scatter(
        x=filtered_df['day'],
        y=smoothed_shots,
        customdata=np.stack([filtered_df['shots']], axis=-1),
        hovertemplate="Shots Fired: %{customdata[0]}<extra></extra>",
        mode='lines',
        name='Shots Fired',
        line=dict(color='#FFD700', width=2),
        line_shape='spline'
    ))

    fig.update_layout(
        height=900,  
        paper_bgcolor="black",
        plot_bgcolor="black",
        font_color="white",
        legend_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(title='Date', color='white', showgrid=False),
        yaxis=dict(title='Incidents per Day', color='white', showgrid=False)
    )

    return fig

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

    df_month['count'] = 1
    grouped = df_month.groupby(['latitude', 'longitude', 'category']).size().reset_index(name='count')
    pivot = grouped.pivot_table(index=['latitude', 'longitude'], columns='category', values='count', fill_value=0).reset_index()
    pivot['total_count'] = pivot.drop(columns=['latitude', 'longitude']).sum(axis=1)
    pivot['text'] = pivot.apply(format_hover, axis=1)

    fig = create_hexbin_mapbox(
        data_frame=pivot,
        lat="latitude",
        lon="longitude",
        nx_hexagon=45,
        agg_func=np.sum,
        color="total_count",  
        opacity=0.7,
        color_continuous_scale=px.colors.sequential.Plasma[::-1],
        mapbox_style="carto-darkmatter",
        center=dict(lat=42.304, lon=-71.07),
        zoom=11.5,
        min_count=1,
        labels={"total_count": "311 Requests"}
    )

    fig.update_coloraxes(colorbar=dict(
        title=dict(text="311 Requests", font=dict(size=12, color="white")),
        orientation="h", x=0.5, y=1.1, xanchor="center", len=0.5,
        thickness=12, tickfont=dict(size=10, color="white"), bgcolor="rgba(0,0,0,0)"
    ))

    for cat, col in category_colors.items():
        fig.add_trace(go.Scattermapbox(
            lat=[None], lon=[None], mode='markers',
            marker=dict(size=10, color=col),
            legendgroup=cat, showlegend=True, name=cat, hoverinfo='skip'
        ))

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
            for poly in poly_list:
                lons = [pt[0] for pt in poly] + [poly[0][0]]
                lats = [pt[1] for pt in poly] + [poly[0][1]]
                fig.add_trace(go.Scattermapbox(
                    lat=lats, lon=lons, mode='lines',
                    line=dict(color=color, width=3),
                    name=f"District {district_code}",
                    legendgroup=f"District {district_code}",
                    showlegend=(poly == poly_list[0]), hoverinfo='skip'
                ))
        except Exception as e:
            print(f"district {district_code} boundary not added", e)

    fig.update_layout(
        title=f"311 Request Hexbin Map ({month_str})",  
        title_font=dict(size=18, color='white'),
        title_x=0.5,
        paper_bgcolor="black",
        plot_bgcolor="black",
        font_color="white",
        legend=dict(
            orientation="v", x=1.02, y=0.95,
            font=dict(color='white'),
            bgcolor="rgba(0,0,0,0)",
            bordercolor="rgba(255,255,255,0.2)", borderwidth=1
        )
    )

    return fig


if __name__ == "__main__":
    app.run_server(debug=True)
