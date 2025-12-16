import os
from dotenv import load_dotenv
import pandas as pd
import plotly.express as px
import dash
from dash import dcc, html
from dash.dependencies import Input, Output, State
import dash_bootstrap_components as dbc
import google.generativeai as genai


load_dotenv()  
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')  
PORT = os.getenv("EXPERIMENT_3_PORT")
DASH_REQUESTS_PATHNAME = os.getenv("EXPERIMENT_3_DASH_REQUESTS_PATHNAME")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
else:
    raise Exception("Gemini API key not found. Please set GEMINI_API_KEY in .env file.")



arrests_df = pd.read_csv('data/Arrests_cleaned.csv', usecols=['year', 'neighborhood'])
offenses_df = pd.read_csv('data/Offenses_cleaned.csv', usecols=['year', 'neighborhood', 'crime_category'])
shootings_df = pd.read_csv('data/Shootings_cleaned.csv', usecols=['year', 'neighborhood', 'shooting_type_v2'])
shots_df = pd.read_csv('data/Shots_Fired_cleaned.csv', usecols=['year', 'neighborhood', 'ballistics_evidence'])
homicides_df = pd.read_csv('data/Homicides_cleaned.csv', usecols=['year', 'neighborhood'])
firearm_df = pd.read_csv('data/Firearm_Recovery_cleaned.csv')


transcripts = []
for i in range(1, 9):
    fname = f"data/Transcript {i}.txt"  # Use your local path
    if os.path.exists(fname):
        with open(fname, 'r', encoding='utf-8') as f:
            transcripts.append(f.read())

# Store as a single string to avoid repeated file reads
meeting_context = "\n".join(transcripts)



offenses_df['year'] = pd.to_numeric(offenses_df['year'], errors='coerce')
offenses_df = offenses_df[offenses_df['year'] >= 2015]
homicides_df = homicides_df[homicides_df['year'] >= 2015]

firearm_df['collection_date'] = pd.to_datetime(firearm_df['collection_date'], errors='coerce')
firearm_df = firearm_df.dropna(subset=['collection_date'])

firearm_df['year'] = firearm_df['collection_date'].dt.year.astype(int)

firearm_long = firearm_df.melt(
    id_vars=['year'],
    value_vars=['crime_guns_recovered', 'guns_recovered_safeguard', 'buyback_guns_recovered'],
    var_name='type', value_name='count'
)

# Rename categories
firearm_long['type'] = firearm_long['type'].replace({
    'crime_guns_recovered': 'Crime Guns',
    'guns_recovered_safeguard': 'Safeguard',
    'buyback_guns_recovered': 'Buyback'
})



# Aggregate data by year/neighborhood
arrests_grp = arrests_df.groupby(['year', 'neighborhood']).size().reset_index(name='count')
offenses_grp = offenses_df.groupby(['year', 'neighborhood', 'crime_category']).size().reset_index(name='count')
shootings_grp = shootings_df.groupby(['year', 'neighborhood', 'shooting_type_v2']).size().reset_index(name='count')
shots_grp = shots_df.groupby(['year', 'neighborhood', 'ballistics_evidence']).size().reset_index(name='count')
homicides_grp = homicides_df.groupby(['year', 'neighborhood']).size().reset_index(name='count')
firearm_grp = firearm_df.groupby('year')[['crime_guns_recovered', 'guns_recovered_safeguard', 'buyback_guns_recovered']].sum().reset_index()


offenses_grp['crime_category'] = offenses_grp['crime_category'].replace({'Unknown': 'Other'})
shots_grp['ballistics_evidence'] = shots_grp['ballistics_evidence'].replace({0: 'No Evidence', 1: 'Evidence Found'})


# Convert year to int 
for df in [arrests_grp, offenses_grp, shootings_grp, shots_grp, homicides_grp, firearm_long]:
    df['year'] = df['year'].astype(int)


neighborhoods = sorted(offenses_df['neighborhood'].dropna().unique())
neighborhood_options = [{'label': 'All (Boston)', 'value': 'All'}] + \
                       [{'label': nb, 'value': nb} for nb in neighborhoods if nb != 'Unknown']
default_neighborhood = 'Dorchester'  # default selection for the community focus

# year range 
min_year = max(2015, offenses_grp['year'].min())  
max_year = max(offenses_grp['year'].max(), shootings_grp['year'].max(), shots_grp['year'].max(),
               homicides_grp['year'].max(), arrests_grp['year'].max(), firearm_long['year'].max())
# (The above finds the maximum year across all datasets)

# Dictionary of datasets
datasets = {
    "Arrests": arrests_grp,
    "Offenses": offenses_grp,
    "Shootings": shootings_grp,
    "Shots Fired": shots_grp,
    "Homicides": homicides_grp,
    "Firearm Recovery": firearm_grp
}

# Initialize Google Gemini
chat_model = genai.GenerativeModel("gemini-1.5-pro-latest")
chat_session = chat_model.start_chat()

def ask_chatbot(user_query):
    """
    Sends user query along with meeting transcripts to Gemini API.
    Returns the response from Gemini.
    """
    response = chat_model.generate_content(f"Context: {meeting_context}\nUser Question: {user_query}")
    return response.text  

# Initialize Dash app
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP],serve_locally=False, requests_pathname_prefix=DASH_REQUESTS_PATHNAME)
app.title = "Dorchester Crime Dashboard"

# Layout with filters and graphs
app.layout = html.Div(children=[
    html.H1("Dorchester Crime Dashboard", style={'textAlign': 'center', 'marginBottom': '20px'}),

    # Filters Section
    html.Div([
        html.Label("Neighborhood:", htmlFor='neighborhood-dropdown', style={'marginRight': '10px'}),
        dcc.Dropdown(
            id='neighborhood-dropdown',
            options=[{'label': 'All (Boston)', 'value': 'All'}] + 
                    [{'label': nb, 'value': nb} for nb in offenses_df['neighborhood'].dropna().unique()],
            value='Dorchester',  # Default selection
            clearable=False,
            style={'width': '200px', 'display': 'inline-block'}
        ),

        html.Label("Year Range:", htmlFor='year-range', style={'marginLeft': '40px', 'marginRight': '10px'}),
        dcc.RangeSlider(
            id='year-slider',
            min=2015, 
            max=min(2024, firearm_grp['year'].max()),  # 🔹 Ensures max is not beyond 2024
            value=[2015, min(2024, firearm_grp['year'].max())],  # 🔹 Sets 2024 as the max range
            marks={year: str(year) for year in range(2015, 2025)},  # 🔹 Stops at 2024
            tooltip={"placement": "bottom", "always_visible": False},
            allowCross=False,
            step=1,
            updatemode='mouseup'
        )

    ], style={'padding': '10px 20px'}),

    # Graphs section
    html.Div([
        # Offenses by category
        html.Div([
            html.H4("Offenses by Category Over Time"),
            dcc.Graph(id='offenses-graph', config={'displayModeBar': False})
        ], style={'width': '48%', 'display': 'inline-block', 'verticalAlign': 'top'}),

        # Shootings (fatal vs non-fatal)
        html.Div([
            html.H4("Shooting Incidents (Fatal vs Non-Fatal)"),
            dcc.Graph(id='shootings-graph', config={'displayModeBar': False})
        ], style={'width': '48%', 'display': 'inline-block', 'verticalAlign': 'top', 'marginLeft': '4%'})
    ]),

    html.Div([
        # Shots Fired (with/without evidence)
        html.Div([
            html.H4("Shots Fired Incidents (Confirmed vs Unconfirmed)"),
            dcc.Graph(id='shotsfired-graph', config={'displayModeBar': False})
        ], style={'width': '48%', 'display': 'inline-block', 'verticalAlign': 'top'}),

        # Homicides
        html.Div([
            html.H4("Homicides Over Time"),
            dcc.Graph(id='homicides-graph', config={'displayModeBar': False})
        ], style={'width': '48%', 'display': 'inline-block', 'verticalAlign': 'top', 'marginLeft': '4%'})
    ]),

    html.Div([
        # Firearm Recoveries
        html.Div([
            html.H4("Firearms Recovered (Citywide)"),
            dcc.Graph(id='firearm-graph', config={'displayModeBar': False})
        ], style={'width': '48%', 'display': 'inline-block', 'verticalAlign': 'top'}),

        # Arrests
        html.Div([
            html.H4("Arrests Over Time"),
            dcc.Graph(id='arrests-graph', config={'displayModeBar': False})
        ], style={'width': '48%', 'display': 'inline-block', 'verticalAlign': 'top', 'marginLeft': '4%'})
    ]),

        # Neighborhood Filter for Comparison
    html.Div([
        html.Label("Filter by Neighborhood:", style={'marginRight': '10px'}),
        dcc.Dropdown(
            id='compare-neighborhood-dropdown',
            options=[{'label': 'All (Boston)', 'value': 'All'}] + 
                    [{'label': nb, 'value': nb} for nb in neighborhoods if nb != 'Unknown'],
            value='All',
            clearable=False,
            style={'width': '250px', 'display': 'inline-block'}
        ),
    ], style={'textAlign': 'center', 'marginBottom': '20px'}),


    # Comparison Button
    html.Div([
        html.Button("Compare Datasets", id="open-compare-btn", n_clicks=0, 
                    className="btn btn-secondary", style={'marginBottom': '20px'}),
        dcc.Graph(id='comparison-graph')
    ], style={'textAlign': 'center'}),

    # Dataset Comparison 
    dbc.Modal(
        [
            dbc.ModalHeader("Compare Multiple Datasets"),
            dbc.ModalBody([
                html.P("Select two or more datasets to compare:", style={'marginBottom': '10px'}),
                dcc.Dropdown(
                    id='dataset-select',
                    options=[{'label': name, 'value': name} for name in datasets.keys()],
                    multi=True,
                    placeholder="Select datasets...",
                    style={'marginBottom': '20px'}
                ),
            ]),
            dbc.ModalFooter(dbc.Button("Close", id="close-compare-btn", className="ml-auto"))
        ],
        id="compare-modal",
        is_open=False,
        size="lg"
    ),
    # Chatbot Button & Modal

    html.Div([
        html.Button("Ask the Community AI", id="open-chatbot-btn", n_clicks=0, 
                    className="btn btn-primary", style={'marginBottom': '20px'}),
        
        dbc.Modal([
            dbc.ModalHeader("Community AI Chatbot"),
            dbc.ModalBody([
                # Scrollable Chat History Box
                html.Div(id="chat-history", style={
                    'maxHeight': '300px', 'overflowY': 'auto', 'border': '1px solid #ddd',
                    'padding': '10px', 'marginBottom': '10px'
                }),

                # Chat Input Box
                dcc.Textarea(
                    id='chatbot-input',
                    placeholder="Ask about community concerns, meeting discussions, or trends...",
                    style={'width': '100%', 'height': '80px'}
                ),

                # Loading Spinner & Ask Button
                html.Div([
                    # Ensure spinner properly covers the response section
                    dcc.Loading(
                        id="loading-chat",
                        type="circle",
                        children=[html.Div(id="chatbot-response-container")]
                    ),
                    html.Button("Ask", id="ask-chatbot-btn", n_clicks=0, 
                                className="btn btn-success", style={'marginTop': '10px'}),
                ])
            ]),
            dbc.ModalFooter(dbc.Button("Close", id="close-chatbot-btn", className="ml-auto"))
        ], id="chatbot-modal", is_open=False, size="lg"),

        # Store Chat History
        dcc.Store(id="chat-history-store", data=[])
    ], style={'textAlign': 'center'}),

], style={'fontFamily': 'Arial, sans-serif', 'maxWidth': '1200px', 'margin': '0 auto'})




@app.callback(
    Output("compare-modal", "is_open"),
    [Input("open-compare-btn", "n_clicks"), Input("close-compare-btn", "n_clicks")],
    [State("compare-modal", "is_open")], 
    prevent_initial_call=True
)
def toggle_modal(open_clicks, close_clicks, is_open):
    if dash.callback_context.triggered_id == "open-compare-btn":
        return True
    elif dash.callback_context.triggered_id == "close-compare-btn":
        return False
    return is_open


@app.callback(
    Output("comparison-graph", "figure"),
    Input("dataset-select", "value"),  
    Input("compare-neighborhood-dropdown", "value"),
    prevent_initial_call=True
)
def update_comparison_graph(selected_datasets, selected_neighborhood):
    if not selected_datasets:  
        return px.bar(title="Select at least two datasets to compare")

    merged_df = None

    for dataset in selected_datasets:
        df = datasets[dataset].copy()

        
        if selected_neighborhood != "All" and "neighborhood" in df.columns:
            df = df[df["neighborhood"] == selected_neighborhood]

        
        if dataset == "Firearm Recovery":
            df = firearm_long.groupby("year", as_index=False)["count"].sum()
            df = df.rename(columns={"count": dataset})
        elif "count" in df.columns:
            df = df.groupby("year", as_index=False)["count"].sum().rename(columns={"count": dataset})
        else:
            df = df.melt(id_vars=["year"], var_name="type", value_name=dataset)

        if merged_df is None:
            merged_df = df
        else:
            merged_df = pd.merge(merged_df, df, on="year", how="outer")


    merged_df = merged_df.melt(id_vars=["year"], var_name="Dataset", value_name="count")
    merged_df = merged_df.groupby(["year", "Dataset"], as_index=False)["count"].sum()


    fig = px.bar(merged_df, x="year", y="count", color="Dataset", barmode="group",
                 title=f"Comparison of Selected Datasets Over Time ({selected_neighborhood})")

    return fig  


# Callback to update all graphs when filters change
@app.callback(
    Output('offenses-graph', 'figure'),
    Output('shootings-graph', 'figure'),
    Output('shotsfired-graph', 'figure'),
    Output('homicides-graph', 'figure'),
    Output('firearm-graph', 'figure'),
    Output('arrests-graph', 'figure'),
    Input('neighborhood-dropdown', 'value'),
    Input('year-slider', 'value')
)
def update_graphs(selected_neighborhood, year_range):
    
    start_year, end_year = year_range
    
    if selected_neighborhood and selected_neighborhood != "All":
        
        off_data = offenses_grp[
            (offenses_grp['neighborhood'] == selected_neighborhood) &
            (offenses_grp['year'] >= start_year) & (offenses_grp['year'] <= end_year)
        ]
        shoot_data = shootings_grp[
            (shootings_grp['neighborhood'] == selected_neighborhood) &
            (shootings_grp['year'] >= start_year) & (shootings_grp['year'] <= end_year)
        ]
        shots_data = shots_grp[
            (shots_grp['neighborhood'] == selected_neighborhood) &
            (shots_grp['year'] >= start_year) & (shots_grp['year'] <= end_year)
        ]
        hom_data = homicides_grp[
            (homicides_grp['neighborhood'] == selected_neighborhood) &
            (homicides_grp['year'] >= start_year) & (homicides_grp['year'] <= end_year)
        ]
        arr_data = arrests_grp[
            (arrests_grp['neighborhood'] == selected_neighborhood) &
            (arrests_grp['year'] >= start_year) & (arrests_grp['year'] <= end_year)
        ]
    else:
        # aggregate counts across all neighborhoods for each year
        off_data = offenses_grp[
            (offenses_grp['year'] >= start_year) & (offenses_grp['year'] <= end_year)
        ].groupby(['year', 'crime_category'])['count'].sum().reset_index()
        shoot_data = shootings_grp[
            (shootings_grp['year'] >= start_year) & (shootings_grp['year'] <= end_year)
        ].groupby(['year', 'shooting_type_v2'])['count'].sum().reset_index()
        shots_data = shots_grp[
            (shots_grp['year'] >= start_year) & (shots_grp['year'] <= end_year)
        ].groupby(['year', 'ballistics_evidence'])['count'].sum().reset_index()
        hom_data = homicides_grp[
            (homicides_grp['year'] >= start_year) & (homicides_grp['year'] <= end_year)
        ].groupby('year')['count'].sum().reset_index()
        arr_data = arrests_grp[
            (arrests_grp['year'] >= start_year) & (arrests_grp['year'] <= end_year)
        ].groupby('year')['count'].sum().reset_index()
    # Firearm recovery data is citywide only (no neighborhood column), just filter by year
    fire_data = firearm_long[
        (firearm_long['year'] >= start_year) & (firearm_long['year'] <= end_year)
    ]


    import plotly.express as px

    # 1. Offenses graph: stacked bar by crime category
    if off_data.empty:
        offenses_fig = px.bar(title="No Offense Data")
    else:
        off_data = off_data.sort_values(by='year')  

        offenses_fig = px.bar(off_data, x='year', y='count', color='crime_category',
                            category_orders={'year': list(range(2015, 2025)),  
                                            'crime_category': ['Violent', 'Property', 'Other']},
                            color_discrete_map={'Violent': '#ff7f0e', 'Property': '#1f77b4', 'Other': '#7f7f7f'},
                            labels={'count': 'Number of Offenses', 'year': 'Year', 'crime_category': 'Crime Category'})

        offenses_fig.update_layout(xaxis=dict(type='category'))  

        offenses_fig.update_layout(barmode='stack', xaxis=dict(type='category'))
    offenses_fig.update_layout(template='plotly_white', legend_title_text=None)

    # 2. Shootings graph: stacked bar by shooting outcome (Fatal/Non-Fatal)
    if shoot_data.empty:
        shootings_fig = px.bar(title="No Shooting Data")
    else:
        shootings_fig = px.bar(shoot_data, x='year', y='count', color='shooting_type_v2',
                               category_orders={'shooting_type_v2': ['Non-Fatal', 'Fatal']},
                               color_discrete_map={'Non-Fatal': '#1f77b4', 'Fatal': '#ff7f0e'},
                               labels={'count': 'Number of Shootings', 'year': 'Year', 'shooting_type_v2': 'Type'})
        shootings_fig.update_layout(barmode='stack', xaxis=dict(type='category'))
    shootings_fig.update_layout(template='plotly_white', legend_title_text=None)

    # 3. Shots Fired graph: stacked bar by evidence found vs not
    if shots_data.empty:
        shots_fig = px.bar(title="No Shots Fired Data")
    else:
        shots_fig = px.bar(shots_data, x='year', y='count', color='ballistics_evidence',
                           category_orders={'ballistics_evidence': ['Evidence Found', 'No Evidence']},
                           color_discrete_map={'Evidence Found': '#ff7f0e', 'No Evidence': '#1f77b4'},
                           labels={'count': 'Number of Incidents', 'year': 'Year', 'ballistics_evidence': 'Ballistics'})
        shots_fig.update_layout(barmode='stack', xaxis=dict(type='category'))
    shots_fig.update_layout(template='plotly_white', legend_title_text=None)

    # 4. Homicides graph: simple line over years
    if hom_data.empty:
        homicides_fig = px.line(title="No Homicide Data")
    else:
        homicides_fig = px.line(hom_data, x='year', y='count',
                                labels={'count': 'Number of Homicides', 'year': 'Year'})
    homicides_fig.update_traces(mode='lines+markers', marker=dict(size=6))
    homicides_fig.update_layout(template='plotly_white', yaxis=dict(title='Number of Homicides'))

    # 5. Firearm Recovery graph: stacked bar by type of recovery (citywide data)
    if firearm_long.empty:
        firearm_fig = px.bar(title="No Firearm Data")
    else:
        
        firearm_agg = firearm_long.groupby(['year', 'type'], as_index=False)['count'].sum()

        
        firearm_agg['count'] = firearm_agg['count'].astype(int)

        firearm_fig = px.bar(
            firearm_agg, x='year', y='count', color='type',
            category_orders={'type': ['Crime Guns', 'Safeguard', 'Buyback']},
            color_discrete_map={'Crime Guns': '#ff7f0e', 'Safeguard': '#1f77b4', 'Buyback': '#7f7f7f'},
            labels={'count': 'Number of Firearms', 'year': 'Year', 'type': 'Recovery Type'}
        )

        
        firearm_fig.update_layout(barmode='stack', xaxis=dict(type='category'), bargap=0.05)


    # 6. Arrests graph: line chart of total arrests
    if arr_data.empty:
        arrests_fig = px.line(title="No Arrest Data")
    else:
        arrests_fig = px.line(arr_data, x='year', y='count',
                              labels={'count': 'Number of Arrests', 'year': 'Year'})
    arrests_fig.update_traces(mode='lines+markers', marker=dict(size=6, color='#9467bd'), line=dict(color='#9467bd'))
    arrests_fig.update_layout(template='plotly_white', yaxis=dict(title='Number of Arrests'))

    return offenses_fig, shootings_fig, shots_fig, homicides_fig, firearm_fig, arrests_fig


@app.callback(
    Output("chatbot-modal", "is_open"),
    [Input("open-chatbot-btn", "n_clicks"),
     Input("close-chatbot-btn", "n_clicks")],
    [State("chatbot-modal", "is_open")],
    prevent_initial_call=True
)
def toggle_chatbot(open_clicks, close_clicks, is_open):
    if open_clicks or close_clicks:
        return not is_open
    return is_open


@app.callback(
    Output("chat-history", "children"),
    Output("chat-history-store", "data"),
    Output("chatbot-input", "value"),
    Output("chatbot-response-container", "children"),  
    Input("ask-chatbot-btn", "n_clicks"),  
    Input("chatbot-input", "n_submit"),    
    State("chatbot-input", "value"),
    State("chat-history-store", "data"),
    prevent_initial_call=True
)
def process_chat(n_clicks, n_submit, user_input, chat_history):
    if not user_input:
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update

    
    chat_history.append(html.P(f"**You:** {user_input}", style={'fontWeight': 'bold'}))
    chat_history.append(html.P("**Chatbot is thinking...**", style={'fontStyle': 'italic', 'color': 'gray'}))

    
    loading_spinner = dcc.Loading(type="circle", children=[html.Div()])  

    
    dash.no_update, chat_history, "", loading_spinner

    
    chatbot_response = ask_chatbot(user_input)

    
    chat_history[-1] = html.P(f"**Chatbot:** {chatbot_response}")

    
    return chat_history, chat_history, "", html.Div()  # Empty div removes spinner




server = app.server 

if __name__ == '__main__':
    app.run_server(host='0.0.0.0', port=PORT)



