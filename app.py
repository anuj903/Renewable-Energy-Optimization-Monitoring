import json
import os
from dash import Dash, html, dcc, Input, Output, State, dash_table, no_update
import dash_bootstrap_components as dbc
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from datetime import timedelta
from utils.db_manager import db
from utils.forecaster import generate_forecast
from utils.ai_scheduler import get_optimized_schedule
from utils.dashboard_service import get_dashboard_data
from utils.planner_service import get_forecast_and_schedule

# Note: We are NOT using dbc.themes because we have custom assets/styles.css
app = Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP]) 
server = app.server

# --- CONFIG ---
SIM_START_TIME = pd.to_datetime("2024-12-16 09:00:00")
FORECAST_DATE = "2024-12-17"

# --- LOAD JSON JOB SPECS ---
JSON_FILE = "job_specs.json"
if os.path.exists(JSON_FILE):
    with open(JSON_FILE, "r") as f:
        job_specs_raw = json.load(f)
else:
    job_specs_raw = [{"Job_Type": "Generic Job", "Unit_Power_KW": 50, "Unit_Duration_Mins": 60, "Constraint": "Any"}]

job_options_list = [{'label': j['Job_Type'], 'value': j['Job_Type']} for j in job_specs_raw]
job_specs_lookup = {j['Job_Type']: j for j in job_specs_raw}

# --- INITIAL BACKLOG ---
first_job_name = list(job_specs_lookup.keys())[0]
initial_backlog = [{
    "Job": first_job_name, 
    "Qty": 1, 
    "Duration_Mins": job_specs_lookup[first_job_name]['Unit_Duration_Mins'], 
    "Power_KW": job_specs_lookup[first_job_name]['Unit_Power_KW'], 
    "Priority": "High"
}]

# ==========================================
#  LAYOUT (Updated to include Bottom Row)
# ==========================================
app.layout = html.Div(className="container", children=[
    
    # --- HEADER ---
    html.Div(className="header", children=[
        html.Div(className="logo-section", children=[
            html.Div("🏭", className="logo"),
            html.H1("EcoFoundry 6.0", className="title")
        ]),
        html.Div(className="status-indicator", children=[
            html.Div(className="status-dot"),
            html.Span("Live Operations (Dec 16)")
        ])
    ]),

    # --- KPI GRID ---
    html.Div(className="metrics-grid", children=[
        html.Div(className="metric-card grid-import", children=[
            html.Div("Grid Import", className="metric-label"),
            html.Div([html.Span(id="kpi-grid"), html.Span("kWh", className="metric-unit")], className="metric-value"),
            html.Div("↓ 12% vs yesterday", className="metric-subtext")
        ]),
        html.Div(className="metric-card solar-gen", children=[
            html.Div("Solar Generation", className="metric-label"),
            html.Div([html.Span(id="kpi-solar"), html.Span("kWh", className="metric-unit")], className="metric-value"),
            html.Div("↑ 8% vs yesterday", className="metric-subtext")
        ]),
        html.Div(className="metric-card bill", children=[
            html.Div("Estimated Bill", className="metric-label"),
            html.Div([html.Span(id="kpi-bill")], className="metric-value"),
            html.Div("↓ ₹32k saved this month", className="metric-subtext")
        ]),
        html.Div(className="metric-card waste", children=[
            html.Div("Solar Waste", className="metric-label"),
            html.Div([html.Span(id="kpi-waste"), html.Span("kWh", className="metric-unit")], className="metric-value"),
            html.Div("⚠️ High waste detected", className="metric-subtext")
        ]),
    ]),

    # --- ROW 1: POWER FLOW & BREAKDOWN ---
    html.Div(className="main-content", children=[
        # Power Flow Chart
        html.Div(className="chart-card", children=[
            html.Div(className="chart-header", children=[
                html.Div("Power Flow - 24 Hour Trend", className="chart-title"),
            ]),
            dcc.Graph(id='chart-power-profile', style={'height': '320px'}, config={'displayModeBar': False})
        ]),
        
        # Energy Breakdown (HTML Bars)
        html.Div(className="chart-card", children=[
            html.Div("Energy Breakdown", className="chart-title", style={'marginBottom': '20px'}),
            html.Div(id='breakdown-container', className="breakdown-bars")
        ]),
    ]),

    # --- ROW 2: CONSUMPTION & DISTRIBUTION (THE MISSING PART) ---
    html.Div(className="bottom-section", style={'display': 'grid', 'gridTemplateColumns': '1fr 1fr', 'gap': '25px', 'marginBottom': '40px'}, children=[
        
        # 1. Daily Consumption (Bar Chart)
        html.Div(className="chart-card", children=[
            html.Div(className="chart-header", children=[
                html.Div("Daily Energy Consumption (kWh/Part)", className="chart-title"),
            ]),
            dcc.Graph(id='chart-daily-consumption', style={'height': '280px'}, config={'displayModeBar': False})
        ]),

        # 2. Distribution (Donut Chart) - UPDATED TITLE
        html.Div(className="chart-card", children=[
            html.Div(className="chart-header", children=[
                html.Div("Power Source Distribution", className="chart-title"),
            ]),
            dcc.Graph(id='chart-distribution', style={'height': '280px'}, config={'displayModeBar': False})
        ]),
    ]),

    # --- PLANNER SECTION ---
    html.H2(f"🔮 AI Planner ({FORECAST_DATE})", className="section-heading"),

    # Planner KPIs
    html.Div(className="kpi-row", children=[
        html.Div(className="metric-card solar-gen", children=[
            html.Div("Predicted Solar", className="metric-label"),
            html.Div(id="plan-solar", className="metric-value")
        ]),
        html.Div(className="metric-card bill", children=[
            html.Div("Expected Load", className="metric-label"),
            html.Div(id="plan-load", className="metric-value")
        ]),
        html.Div(className="metric-card grid-import", children=[
            html.Div("Free Energy Available", className="metric-label"),
            html.Div(id="plan-free", className="metric-value")
        ]),
    ]),

    # Planner Tools
    html.Div(className="main-content", children=[
        # LEFT: Controls
        html.Div(className="chart-card", children=[
            html.Div("1. Job Backlog Manager", className="chart-title", style={'marginBottom': '15px'}),
            html.Label("Select Job Type:", className="fw-bold small"),
            dcc.Dropdown(id='dropdown-job-type', options=job_options_list, value=job_options_list[0]['value'], clearable=False, className="mb-2"),
            html.Div(id='div-job-info', className="mb-3"),
            dbc.Button("⬇️ Add to Backlog", id='btn-add-row', color="primary", className="mb-3 w-100"),
            dash_table.DataTable(
                id='table-backlog',
                columns=[{'name': 'Job', 'id': 'Job'}, {'name': 'Qty', 'id': 'Qty', 'type': 'numeric', 'editable': True}, {'name': 'Prio', 'id': 'Priority', 'editable': True}],
                data=initial_backlog,
                row_deletable=True,
                style_as_list_view=True,
                style_cell={'textAlign': 'left', 'fontSize': '13px', 'padding': '8px'},
                style_header={'backgroundColor': 'white', 'fontWeight': 'bold', 'borderBottom': '2px solid #eee'},
            ),
            html.Br(),
            dbc.Button("✨ Run AI Scheduler", id='btn-run-scheduler', color="success", className="w-100")
        ]),
        # RIGHT: Gantt
        html.Div(className="chart-card", children=[
            html.Div("2. Optimization Result", className="chart-title"),
            dcc.Graph(id='chart-forecast', style={'height': '200px'}, config={'displayModeBar': False}),
            html.Hr(),
            dcc.Loading(dcc.Graph(id='chart-gantt', style={'height': '250px'}, config={'displayModeBar': False})),
            html.Div(id='ai-insights', className="mt-3 small text-muted")
        ])
    ]),

    dcc.Interval(id='timer-1s', interval=15000, n_intervals=0)
])


# ==========================================
#  CALLBACKS
# ==========================================

@app.callback(
    [Output('kpi-grid', 'children'), Output('kpi-solar', 'children'), Output('kpi-bill', 'children'), Output('kpi-waste', 'children'),
     Output('chart-power-profile', 'figure'), Output('breakdown-container', 'children'),
     Output('chart-daily-consumption', 'figure'), Output('chart-distribution', 'figure')],
    [Input('timer-1s', 'n_intervals')]
)
def update_live(n):
    curr_time = SIM_START_TIME + timedelta(minutes=n * 15)

    # Centralized business logic for KPIs and raw data
    data = get_dashboard_data(curr_time)
    g = data["metrics"]["g"]
    s = data["metrics"]["s"]
    w = data["metrics"]["w"]

    # 2. Power Profile
    df_prof = data["df_prof"]
    fig_prof = go.Figure()
    if not df_prof.empty:
        df_prof.columns = [c.lower() for c in df_prof.columns]
        x_col = 'timestamp' if 'timestamp' in df_prof.columns else 'Timestamp'
        fig_prof.add_trace(go.Scatter(x=df_prof[x_col], y=df_prof.get('solar',[]), fill='tozeroy', line_color='#f39c12', name='Solar', fillcolor='rgba(243, 156, 18, 0.2)'))
        fig_prof.add_trace(go.Scatter(x=df_prof[x_col], y=df_prof.get('load',[]), line_color='#2ecc71', name='Load', line_width=2))
    
    common_layout = dict(margin=dict(t=10,b=10,l=30,r=10), plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', xaxis=dict(showgrid=True, gridcolor='rgba(0,0,0,0.05)'), yaxis=dict(showgrid=True, gridcolor='rgba(0,0,0,0.05)'))
    fig_prof.update_layout(legend=dict(orientation="h", y=1.1), **common_layout)

    # 3. Line Data (For HTML Bars Only)
    df_lines = data["df_lines"]
    
    # A. HTML Bars
    breakdown_html = []
    if not df_lines.empty:
        df_lines.columns = ['Line', 'kWh']
        df_lines = df_lines.sort_values(by='kWh', ascending=False)
        max_val = df_lines['kWh'].max() or 1
        part_map = {'Line 1': 'Engine Block', 'Line 2': 'Transmission', 'Line 3': 'Brake Calipers'}
        colors = ['bar-gradient-1', 'bar-gradient-2', 'bar-gradient-3']

        for i, row in df_lines.reset_index().iterrows():
            pct = (row['kWh'] / max_val) * 100
            bar_item = html.Div(className="breakdown-item", children=[
                html.Div(row['Line'], className="breakdown-label"),
                html.Div(className="breakdown-bar-container", children=[
                    html.Div(className=f"breakdown-bar {colors[i % 3]}", style={'width': f"{pct}%"}, children=f"{int(row['kWh']):,} kWh ({part_map.get(row['Line'])})")
                ])
            ])
            breakdown_html.append(bar_item)

    # 4. Daily Consumption Bar Chart
    df_eff = data["df_eff"]
    fig_bar = go.Figure()
    if not df_eff.empty:
        df_eff.columns = ['date', 'val']
        df_eff = df_eff.sort_values(by='date')
        fig_bar = px.bar(df_eff, x='date', y='val', color='val', color_continuous_scale='Teal')
        fig_bar.update_layout(coloraxis_showscale=False, **common_layout)

    # 5. RESTORED: Power Source Donut (Grid vs Solar vs Waste)
    # Logic: 'Solar Used' = Total Solar - Wasted
    solar_used = s - w
    if solar_used < 0: solar_used = 0 # Safety clip

    fig_donut = px.pie(
        values=[g, solar_used, w], 
        names=['Grid Import', 'Solar Used', 'Solar Waste'], 
        hole=0.6, 
        color_discrete_sequence=['#bdc3c7', '#27ae60', '#e74c3c'] # Grey, Green, Red
    )
    
    fig_donut.update_layout(
        margin=dict(t=0,b=0,l=0,r=0), 
        showlegend=True, 
        legend=dict(orientation="h", y=-0.1), 
        plot_bgcolor='rgba(0,0,0,0)', 
        paper_bgcolor='rgba(0,0,0,0)'
    )

    return f"{int(g):,}", f"{int(s):,}", f"₹ {int(g*8.19):,}", f"{int(w):,}", fig_prof, breakdown_html, fig_bar, fig_donut


# 2. SHOW JOB INFO
@app.callback(Output('div-job-info', 'children'), Input('dropdown-job-type', 'value'))
def show_job_info(selected_job):
    if not selected_job: return html.Div()
    specs = job_specs_lookup.get(selected_job, {})
    return dbc.Alert([
        html.Span("⚡ Power: ", className="fw-bold"), f"{specs.get('Unit_Power_KW')} kW | ",
        html.Span("⏱ Duration: ", className="fw-bold"), f"{specs.get('Unit_Duration_Mins')} min"
    ], color="light", className="py-2 mb-0 small")

# 3. ADD TO BACKLOG
@app.callback(Output('table-backlog', 'data'), Input('btn-add-row', 'n_clicks'), State('dropdown-job-type', 'value'), State('table-backlog', 'data'), prevent_initial_call=True)
def add_to_backlog(n, job, current_data):
    if not job: return no_update
    if current_data is None: current_data = []
    specs = job_specs_lookup.get(job, {})
    current_data.append({"Job": job, "Qty": 1, "Duration_Mins": specs.get('Unit_Duration_Mins'), "Power_KW": specs.get('Unit_Power_KW'), "Priority": "Med"})
    return current_data

# 4. RUN SCHEDULER
@app.callback(
    [Output('chart-forecast', 'figure'), Output('chart-gantt', 'figure'), Output('ai-insights', 'children'),
     Output('plan-solar', 'children'), Output('plan-load', 'children'), Output('plan-free', 'children')],
    Input('btn-run-scheduler', 'n_clicks'),
    State('table-backlog', 'data')
)
def run_scheduler(n_clicks, backlog):
    result = get_forecast_and_schedule(FORECAST_DATE, backlog)
    df_fc = result["forecast"]
    empty_fig = go.Figure().update_layout(title="No Forecast", plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
    
    if df_fc.empty:
        return empty_fig, empty_fig, "Forecast Error", "0 kWh", "0 kWh", "0 kWh"

    # KPIs
    totals = result["totals"]
    total_solar = totals["solar"]
    total_load = totals["load"]
    total_free = totals["free"]

    # Forecast Chart
    fig_fc = go.Figure()
    fig_fc.add_trace(go.Scatter(x=df_fc['date'], y=df_fc['Pred_Solar'], line=dict(dash='dot', color='#f39c12'), name='Solar'))
    fig_fc.add_trace(go.Scatter(x=df_fc['date'], y=df_fc['Likely_Load'], line_color='#2ecc71', name='Load'))
    fig_fc.add_trace(go.Scatter(x=df_fc['date'], y=df_fc['Available_Waste'], fill='tozeroy', line_color='rgba(52, 152, 219, 0.5)', name='Free'))
    fig_fc.update_layout(margin=dict(t=0,b=0,l=0,r=0), legend=dict(orientation="h", y=1.1), plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')

    # Gantt Chart Init
    fig_gantt = go.Figure().update_layout(title="Ready to Schedule", plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
    insights = dcc.Markdown("Click **'Run AI Scheduler'** to optimize.")

    if n_clicks and backlog:
        try:
            ai_res = result.get("ai_result") or {}

            if not ai_res:
                insights = "⚠️ No excess solar energy available for scheduling or AI unavailable."
            elif ai_res.get('Schedule'):
                df_sch = pd.DataFrame(ai_res['Schedule'])
                df_sch['Start'] = pd.to_datetime(df_sch['Start'])
                df_sch['End'] = pd.to_datetime(df_sch['End'])

                fig_gantt = px.timeline(
                    df_sch, 
                    x_start="Start", 
                    x_end="End", 
                    y="Task",
                    color="Task",
                    hover_data=["ID", "Status"],
                )
                
                shift_start_ts = pd.to_datetime(f"{FORECAST_DATE} 09:00:00").timestamp() * 1000
                fig_gantt.add_vline(x=shift_start_ts, line_width=1, line_dash="dash", line_color="gray", annotation_text="Shift Start")
                
                fig_gantt.update_yaxes(autorange="reversed", title="")
                fig_gantt.update_layout(
                    margin=dict(t=30,b=0,l=0,r=0), 
                    height=250, 
                    plot_bgcolor='rgba(0,0,0,0)', 
                    paper_bgcolor='rgba(0,0,0,0)',
                    showlegend=False,
                )
                
                # Display Insights as Bullet Points
                insights = dcc.Markdown(ai_res.get('Insights', 'Schedule Optimized.'))
            else:
                insights = "AI returned no schedule."
        except Exception as e:
            insights = f"Scheduler Error: {str(e)}"

    return fig_fc, fig_gantt, insights, f"{total_solar:,} kWh", f"{total_load:,} kWh", f"{total_free:,} kWh"

if __name__ == '__main__':
    # Use PORT from environment (Railway) and bind to 0.0.0.0 for container networking
    port = int(os.environ.get("PORT", 8050))
    app.run(host="0.0.0.0", port=port, debug=False)