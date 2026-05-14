from dash import html, dcc, callback, Input, Output, State, dash_table, no_update
import dash_bootstrap_components as dbc
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import json
from utils.db_manager import db
from utils.planner_service import get_forecast_and_schedule  # Shared business logic

# --- CONFIG ---
# Reverted to Dec 16 based on our previous success
TOMORROW_DATE = "2024-12-16" 

# Initial Backlog Data
initial_backlog = [
    {"Job": "Furnace Pre-Heat", "Qty": 1, "Duration_Mins": 60, "Power_KW": 120, "Priority": "High"},
    {"Job": "EV Forklift Charge", "Qty": 4, "Duration_Mins": 45, "Power_KW": 30, "Priority": "Med"},
    {"Job": "Slag Processing", "Qty": 2, "Duration_Mins": 90, "Power_KW": 45, "Priority": "Low"},
]

layout = dbc.Container([
    # Header
    dbc.Row([
        dbc.Col(html.H2(f"🔮 Production Planner: {TOMORROW_DATE}"), width=8),
        dbc.Col([
            dbc.Button("✨ Run AI Scheduler", id="btn-run-schedule", color="success", className="mt-2 w-100"),
            dcc.Store(id='store-forecast-data'), # Hidden store for forecast
            dcc.Store(id='store-schedule-result') # Hidden store for AI result
        ], width=4)
    ], className="my-4"),

    # Main Content
    dbc.Row([
        # LEFT COLUMN (Charts)
        dbc.Col([
            # 1. Forecast Chart
            dbc.Card([
                dbc.CardHeader("Expected Power Balance (ML Forecast)"),
                dbc.CardBody(dcc.Loading(dcc.Graph(id="chart-forecast", style={"height": "350px"})))
            ], className="shadow-sm mb-4"),
            
            # 2. AI Gantt Chart (The new addition)
            dbc.Card([
                dbc.CardHeader("🗓️ AI Optimized Schedule"),
                dbc.CardBody([
                    dcc.Loading(dcc.Graph(id="chart-gantt", style={"height": "300px"})),
                    html.Div(id="ai-insights", className="alert alert-info mt-2", style={"display": "none"})
                ])
            ], className="shadow-sm")
        ], width=8),

        # RIGHT COLUMN (Backlog Editor)
        dbc.Col([
            dbc.Card([
                dbc.CardHeader("📋 Job Backlog (Editable)"),
                dbc.CardBody([
                    dash_table.DataTable(
                        id='table-backlog',
                        columns=[
                            {'name': 'Job', 'id': 'Job'},
                            {'name': 'Qty', 'id': 'Qty', 'type': 'numeric'},
                            {'name': 'Mins', 'id': 'Duration_Mins', 'type': 'numeric'},
                            {'name': 'kW', 'id': 'Power_KW', 'type': 'numeric'},
                            {'name': 'Priority', 'id': 'Priority', 'presentation': 'dropdown'}
                        ],
                        data=initial_backlog,
                        editable=True,
                        row_deletable=True,
                        dropdown={
                            'Priority': {'options': [{'label': i, 'value': i} for i in ['High', 'Med', 'Low']]}
                        },
                        style_cell={'textAlign': 'left', 'fontSize': '12px'},
                        style_header={'backgroundColor': '#f8f9fa', 'fontWeight': 'bold'}
                    ),
                    dbc.Button("Add Job", id='btn-add-row', n_clicks=0, size="sm", color="secondary", className="mt-2 w-100")
                ])
            ], className="shadow-sm", style={"height": "100%"})
        ], width=4)
    ])
], fluid=True)


# --- CALLBACKS ---

# 1. Handle Backlog Updates (Add Rows)
@callback(
    Output('table-backlog', 'data'),
    Input('btn-add-row', 'n_clicks'),
    State('table-backlog', 'data'),
    prevent_initial_call=True
)
def add_row(n_clicks, rows):
    rows.append({"Job": "New Task", "Qty": 1, "Duration_Mins": 30, "Power_KW": 10, "Priority": "Low"})
    return rows

# 2. Run Forecast & AI Schedule
@callback(
    [Output('chart-forecast', 'figure'),
     Output('chart-gantt', 'figure'),
     Output('ai-insights', 'children'),
     Output('ai-insights', 'style')],
    [Input('btn-run-schedule', 'n_clicks')],
    [State('table-backlog', 'data')]
)
def update_planner(n_clicks, backlog_data):
    # Default return if no click
    if not n_clicks:
        return no_update, no_update, no_update, {"display": "none"}

    result = get_forecast_and_schedule(TOMORROW_DATE, backlog_data)
    df_fc = result["forecast"]

    if df_fc.empty:
        return go.Figure().update_layout(title="Forecast Error"), go.Figure(), "", {"display": "none"}

    # Build Forecast Chart
    fig_fc = go.Figure()
    fig_fc.add_trace(go.Scatter(x=df_fc['date'], y=df_fc['Pred_Solar'], name='Predicted Solar', line=dict(color='#FFC107', dash='dot')))
    fig_fc.add_trace(go.Scatter(x=df_fc['date'], y=df_fc['Likely_Load'], name='Likely Load', line=dict(color='#1B5E20')))
    fig_fc.add_trace(go.Scatter(x=df_fc['date'], y=df_fc['Available_Waste'], name='Free Energy', fill='tozeroy', line=dict(color='#66BB6A', width=0)))
    fig_fc.update_layout(margin=dict(l=0, r=0, t=30, b=0), legend=dict(orientation="h", y=1.1))

    ai_result = result.get("ai_result") or {}

    # Build Gantt Chart
    if 'Schedule' in ai_result and len(ai_result['Schedule']) > 0:
        sch_df = pd.DataFrame(ai_result['Schedule'])
        
        # Convert dates
        sch_df['Start'] = pd.to_datetime(sch_df['Start'])
        sch_df['End'] = pd.to_datetime(sch_df['End'])
        
        fig_gantt = px.timeline(
            sch_df, x_start="Start", x_end="End", y="Task", color="Status",
            color_discrete_map={"Scheduled": "#4CAF50", "Skipped": "#FF5252"},
            text="Task"
        )
        fig_gantt.update_traces(textposition='inside', opacity=0.9)
        fig_gantt.update_yaxes(autorange="reversed")
        fig_gantt.update_layout(
            margin=dict(l=10, r=10, t=10, b=10),
            height=300,
            xaxis=dict(title="", tickformat="%H:%M"),
            yaxis=dict(title="")
        )
        
        insights_text = f"💡 **AI Insights:** {ai_result.get('Insights', 'No insights.')}"
        insights_style = {"display": "block"}
        
    else:
        fig_gantt = go.Figure().update_layout(
            title="Could not generate schedule.", 
            xaxis=dict(showgrid=False, showticklabels=False),
            yaxis=dict(showgrid=False, showticklabels=False)
        )
        insights_text = "AI Error"
        insights_style = {"display": "none"}

    return fig_fc, fig_gantt, insights_text, insights_style