import dash
from dash import dcc, html, Input, Output, State
from dotenv import load_dotenv
import pandas as pd
import geopandas as gpd
import plotly.express as px
import plotly.figure_factory as ff
import plotly.graph_objects as go

load_dotenv()  
PORT = os.getenv("EXPERIMENT_4_PORT")
DASH_REQUESTS_PATHNAME = os.getenv("EXPERIMENT_4_DASH_REQUESTS_PATHNAME")

# Load Arrests Data
arrests_df = pd.read_csv('./data/Arrests_cleaned.csv', low_memory=False)
# Load 311 Data (years 2020–2024)
df_311_list = []
for yr in range(20, 25):
    df = pd.read_csv(f'./data/311_{yr}.csv', low_memory=False)
    df_311_list.append(df)
df_311 = pd.concat(df_311_list, ignore_index=True)

# Standardize column names to lowercase
arrests_df.columns = arrests_df.columns.str.lower()
df_311.columns = df_311.columns.str.lower()

# Convert dates to datetime and create monthyear fields
df_311['open_dt'] = pd.to_datetime(df_311['open_dt'], errors='coerce')
df_311['monthyear'] = df_311['open_dt'].dt.strftime('%Y-%m')
arrests_df['arr_date'] = pd.to_datetime(arrests_df['arr_date'], errors='coerce')
arrests_df['monthyear'] = arrests_df['arr_date'].dt.strftime('%Y-%m')

# Create season column for arrests (1=Winter, 2=Spring, etc., then map to labels)
arrests_df['season'] = arrests_df['arr_date'].dt.month % 12 // 3 + 1
season_map = {1: 'Winter', 2: 'Spring', 3: 'Summer', 4: 'Fall'}
arrests_df['season'] = arrests_df['season'].map(season_map)

# Filter both datasets to only include districts B3 and C11
df_311 = df_311[df_311['police_district'].isin(['B3', 'C11'])]
arrests_df = arrests_df[arrests_df['district'].isin(['B3'])]

# Aggregate monthly arrests (B3 & C11 combined)
monthly_arrests = arrests_df.groupby('monthyear').size().reset_index(name='arrests')

# Aggregate monthly 311 requests for district B3
df_311_B3 = df_311[df_311['police_district'] == 'B3']
monthly_311_B3 = df_311_B3.groupby('monthyear').size().reset_index(name='requests')

# Ensure monthly_311_B3 matches the arrest data timeline exactly
monthly_311_B3 = monthly_arrests[['monthyear']].merge(
    monthly_311_B3, on='monthyear', how='left'
).fillna(0)

monthly_arrests['monthyear_dt'] = pd.to_datetime(monthly_arrests['monthyear'])
monthly_311_B3['monthyear_dt'] = pd.to_datetime(monthly_311_B3['monthyear'])


top_crimes = arrests_df['nibrs_desc'].value_counts().nlargest(5).index
filtered_arrests = arrests_df[arrests_df['nibrs_desc'].isin(top_crimes)]


time_labels = monthly_arrests['monthyear_dt'].dt.strftime('%Y-%m').tolist()

slider_marks = {i: label for i, label in enumerate(time_labels) if i % 3 == 0}


app = dash.Dash(__name__, serve_locally=False, requests_pathname_prefix=DASH_REQUESTS_PATHNAME)
app.layout = html.Div(
    style={'backgroundColor': '#F7F0FA', 'padding': '15px'},
    children=[
        html.H1(
            "Boston Crime & 311 Dashboard", 
            style={'textAlign': 'center', 'color': '#4B3C8E'}
        ),

        html.Div([
            
            html.Div([
                
                dcc.Graph(id='temporal-chart', style={'height': '300px', 'width': '105%'}),

                
                html.Div([
                    dcc.Slider(
                        id='time-slider',
                        min=0, max=len(time_labels) - 1, value=0,
                        marks={i: "" for i in range(len(time_labels))},
                        step=1,
                        included=False,
                        tooltip={"placement": "top", "always_visible": True},
                        updatemode='drag'
                    )

                ], style={
                    'width': '95%',  
                    'margin': 'auto',  
                    'padding': '10px 20px 0px 55px'  
                })
                ,

                
                dcc.Graph(id='temporal-311-chart', style={'height': '300px', 'width': '105%'}),
            ], style={'width': '40%', 'display': 'inline-block', 'verticalAlign':'top'}),

            
            html.Div([
                dcc.Graph(id='hex-map', style={'height': '620px'}),
                dcc.Graph(id='hover-chart', style={'height': '250px', 'marginTop':'-150px'})
            ], style={'width': '58%', 'display': 'inline-block', 'paddingLeft':'2%'}),
        ]),

        
        html.H2(
            "Deeper Analysis of Arrest Data for B3 District",
            style={'textAlign':'center', 'color':'#4B3C8E', 'marginTop':'40px'}
        ),

        html.Div([
            dcc.Graph(id='seasonal-chart', style={'width': '48%', 'display': 'inline-block'}),
            dcc.Graph(id='demographic-chart', style={'width': '48%', 'display': 'inline-block', 'float':'right'})
        ], style={'marginTop':'30px'}),

        html.Div([
            dcc.Graph(id='crime-type-chart', style={'width': '100%', 'marginTop':'30px'})
        ]),
    ]
)

import plotly.figure_factory as ff

@app.callback(
    Output('hex-map', 'figure'),
    Input('time-slider', 'value')
)
def update_hex_map(selected_index):
    selected_month = time_labels[selected_index]

    
    df_month = df_311[(df_311['monthyear'] == selected_month) & (df_311['police_district'] == 'B3')].copy()

    if 'latitude' not in df_month.columns or 'longitude' not in df_month.columns:
        return go.Figure()  

    df_month = df_month.dropna(subset=['latitude', 'longitude'])
    df_month['latitude'] = pd.to_numeric(df_month['latitude'], errors='coerce')
    df_month['longitude'] = pd.to_numeric(df_month['longitude'], errors='coerce')

    
    map_center = {"lat": 42.285, "lon": -71.09}  
    map_zoom = 13.5  # Keep zoom level

    if df_month.empty:
        return px.scatter_mapbox()

    
    hex_fig = ff.create_hexbin_mapbox(
        data_frame=df_month,
        lat="latitude",
        lon="longitude",
        nx_hexagon=30,
        opacity=0.6,
        labels={"color": "311 Requests"},
        agg_func=len,
        color_continuous_scale="Purples",
        mapbox_style="carto-positron",
        center=map_center, 
        zoom=map_zoom,
        min_count=1
    )

    
    hex_fig.update_layout(
        autosize=False,
        height=700,
        margin=dict(t=0, b=0, l=0, r=0),
        paper_bgcolor="#F7F0FA",
        plot_bgcolor="#F7F0FA",
        uirevision="B3-fixed-view"  
    )

    hex_fig.update_coloraxes(colorbar_title="311 Requests", colorscale="Purples")

    return hex_fig




from shapely.geometry import Point, Polygon

@app.callback(
    [Output('hover-chart', 'figure'),
     Output('hover-chart', 'style')],  
    [Input('hex-map', 'hoverData')],
    [State('time-slider', 'value'),
     State('hex-map', 'figure')]
)
def update_hover_chart(hoverData, selected_index, hexmap_fig):
    print("\n DEBUGGING STARTED ")

    if hoverData is None or 'points' not in hoverData:
        print(" hoverData is None")
        return go.Figure(), {'display': 'none'}

    print(f" hoverData received: {hoverData}")

    
    point_data = hoverData['points'][0]
    bbox = point_data.get('bbox', {})

    if 'x0' not in bbox or 'y0' not in bbox:
        print("bbox data is missing, cannot position hover chart")
        return go.Figure(), {'display': 'none'}

    x_pos = bbox['x0']
    y_pos = bbox['y0']

    print(f" Extracted Position - X: {x_pos}, Y: {y_pos}")

    
    hex_id = point_data.get('location')

    
    selected_month = time_labels[selected_index]
    df_month = df_311[df_311['monthyear'] == selected_month].copy()

    if df_month.empty:
        print(" No data for this month")
        return go.Figure(), {'display': 'none'}

    
    df_month['geometry'] = df_month.apply(lambda row: Point(row['longitude'], row['latitude']), axis=1)

    
    hex_polygon = None
    if hexmap_fig and 'data' in hexmap_fig and hexmap_fig['data']:
        geojson = hexmap_fig['data'][0].get('geojson')
        if geojson:
            for feature in geojson['features']:
                if feature.get('id') == hex_id:
                    coords = feature['geometry']['coordinates'][0]
                    hex_polygon = Polygon(coords)
                    break

    if hex_polygon is None:
        print("No matching hexagon found")
        return go.Figure(), {'display': 'none'}

    
    points_in_hex = df_month[df_month['geometry'].apply(lambda p: hex_polygon.contains(p))]

    if points_in_hex.empty:
        print("No 311 request data in hovered hex")
        return go.Figure(), {'display': 'none'}

    
    type_counts = points_in_hex['type'].value_counts().nlargest(5).reset_index()
    type_counts.columns = ['Request Type', 'Count']

    print(f"Data for chart: \n{type_counts}")

    if type_counts.empty:
        print(" No requests found for hovered area")
        return go.Figure(), {'display': 'none'}

    
    bar_width = 0.3 if len(type_counts) > 2 else 0.15  

    
    fig = px.bar(
        type_counts, 
        x='Request Type', 
        y='Count', 
        title='311 Requests in Area', 
        color='Request Type', 
        color_discrete_sequence=px.colors.qualitative.Pastel
    )

    fig.update_traces(marker_line_width=1, marker_line_color="black", width=bar_width)

    fig.update_layout(
        height=180, width=230, showlegend=False, 
        margin=dict(t=30, b=10, l=5, r=5),
        paper_bgcolor="white", plot_bgcolor="white",
        font=dict(size=9), bargap=0.2,
        shapes=[dict(type="rect", xref="paper", yref="paper", x0=0, y0=0, x1=1, y1=1,
                     fillcolor="white", opacity=0.85, layer="below")]
    )

    
    chart_position = {
        'position': 'absolute',
        'top': f'{y_pos - 50}px',  
        'left': f'{x_pos + 20}px',  
        'width': '230px',
        'height': '180px',
        'backgroundColor': 'white',
        'boxShadow': '2px 2px 10px rgba(0,0,0,0.3)',
        'borderRadius': '8px',
        'padding': '5px',
        'display': 'block'
    }

    print("Hover Chart Successfully Generated!")
    return fig, chart_position



@app.callback(
    Output('temporal-chart', 'figure'),
    Input('time-slider', 'value')
)
def update_temporal_chart(selected_index):
    
    aggregated_arrests = filtered_arrests.groupby(['monthyear', 'nibrs_desc']).size().reset_index(name='arrest_count')

    
    crime_colors = {
        "AGGRAVATED ASSAULT": "#1f77b4",
        "ALL OTHER OFFENSES": "#ff7f0e",
        "DRUG/NARCOTIC VIOLATIONS": "#2ca02c",
        "MOTOR VEHICLE VIOLATIONS": "#d62728",
        "OTHER": "#9467bd",
        "OTHER PART II": "#8c564b",
        "WEAPON LAW VIOLATIONS": "#e377c2"
    }

    fig = px.area(
        aggregated_arrests, 
        x='monthyear', 
        y='arrest_count', 
        color='nibrs_desc',
        title='Monthly Arrest Trends (District B3)',
        labels={'monthyear': 'Month', 'arrest_count': 'Number of Arrests', 'nibrs_desc': 'Crime Type'},
        color_discrete_map=crime_colors  
    )

    fig.update_xaxes(
        tickangle=-45,
        dtick='M3',
        tickformat='%m/%Y',
        fixedrange=True,
        ticklabelmode="instant"
    )

    fig.update_layout(
        margin=dict(l=80, r=20, t=50, b=80),
        plot_bgcolor="#F7F0FA",
        paper_bgcolor="#F7F0FA",
        yaxis=dict(fixedrange=True),

        
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=3.0,
            xanchor="center",
            x=0.5,
            font=dict(size=11)
        )
    )

    return fig




@app.callback(
    Output('seasonal-chart', 'figure'),
    Input('time-slider', 'value')
)
def update_seasonal_chart(_):
    season_order = ['Winter', 'Spring', 'Summer', 'Fall']
    fig = px.histogram(
        arrests_df, 
        x='season', 
        category_orders={'season': season_order},
        title='Arrests by Season (B3 District)', 
        labels={'season': 'Season', 'count': 'Arrests'}
    )
    fig.update_traces(marker_color='#BB8FCE')
    fig.update_layout(yaxis_title='Number of Arrests', margin=dict(t=50, b=40, l=40, r=20))
    return fig


@app.callback(
    Output('demographic-chart', 'figure'),
    Input('time-slider', 'value')
)
def update_demographic_chart(_):
    
    filtered_df = arrests_df.dropna(subset=['gender_desc']).copy()

    
    valid_genders = filtered_df['gender_desc'].unique()
    
    
    gender_colors = {
        "MALE": "#8E6BBE",
        "FEMALE": "#C3ACE4"
    }

    
    gender_colors = {k: v for k, v in gender_colors.items() if k in valid_genders}

    
    fig = px.histogram(
        filtered_df, 
        x='age', 
        nbins=20, 
        color='gender_desc',
        title='Age Distribution of Arrestees by Gender',
        labels={'age': 'Age', 'gender_desc': 'Gender'},
        color_discrete_map=gender_colors,  
        template='plotly_white'
    )

    fig.update_layout(
        legend_title_text='Gender',
        legend=dict(x=0.85, y=0.95),
        margin=dict(t=50, b=40, l=40, r=10),
        bargap=0.1,
        plot_bgcolor="#F7F0FA"
    )

    return fig


@app.callback(
    Output('temporal-311-chart', 'figure'),
    Input('time-slider', 'value')
)
def update_temporal_311_chart(selected_index):
    
    top_311_categories = df_311_B3['reason'].value_counts().nlargest(5).index
    filtered_311 = df_311_B3[df_311_B3['reason'].isin(top_311_categories)]

    
    aggregated_311 = (
        filtered_311.groupby(['monthyear', 'reason'])
        .size()
        .reset_index(name='request_count')
    )

    
    request_colors = {
        "Street Light Outage": "#1f77b4",
        "Missed Trash Pickup": "#ff7f0e",
        "Rodent Activity": "#2ca02c",
        "Illegal Parking": "#d62728",
        "Graffiti Removal": "#9467bd"
    }

    fig = px.area(
        aggregated_311,
        x="monthyear",
        y="request_count",
        color="reason",
        title="Monthly 311 Requests (District B3)",
        labels={"monthyear": "Month", "request_count": "Number of Requests", "reason": "Request Type"},
        color_discrete_map=request_colors  
    )

    fig.update_xaxes(
        tickangle=-45,
        dtick="M3",
        tickformat="%m/%Y",
        fixedrange=True,
        ticklabelmode="instant"
    )

    fig.update_layout(
        margin=dict(l=80, r=20, t=50, b=80),
        plot_bgcolor="#F7F0FA",
        paper_bgcolor="#F7F0FA",
        yaxis=dict(fixedrange=True),

        
        legend=dict(
            orientation="h",
            yanchor="top",
            y=-0.8,  
            xanchor="center",
            x=0.5,
            font=dict(size=11)
        )
    )

    return fig



@app.callback(
    Output('crime-type-chart', 'figure'),
    Input('time-slider', 'value')
)
def update_crime_type_chart(selected_index):
    selected_month = time_labels[selected_index]

    arrests_month = arrests_df[arrests_df['monthyear'] == selected_month]

    
    crime_counts = arrests_month['nibrs_desc'].value_counts().nlargest(10).reset_index()
    crime_counts.columns = ['Crime Type', 'Count']

    fig = px.bar(
        crime_counts,
        x='Count',
        y='Crime Type',
        orientation='h',
        title=f'Top 10 Crime Types in {selected_month} (District B3)',
        labels={'Count': 'Number of Arrests', 'Crime Type': 'Crime Type'},
        template='plotly_white'
    )

    fig.update_traces(marker_color='#B284BE')
    fig.update_layout(
        yaxis={'categoryorder':'total ascending'},
        margin=dict(t=50, b=40, l=150, r=20),
        plot_bgcolor="#F7F0FA"
    )

    return fig



px.defaults.template = "plotly_white"
px.defaults.color_continuous_scale = px.colors.sequential.Purples



if __name__ == '__main__':
    app.run_server(host='0.0.0.0', port=PORT, debug=True)