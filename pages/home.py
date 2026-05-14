from dash import html, dcc
import dash_bootstrap_components as dbc
import plotly.graph_objects as go

# --- COMPONENTS ---
def kpi_card(title, id_value, icon="⚡"):
    return dbc.Card([
        dbc.CardBody([
            html.H6(title, className="card-subtitle text-muted"),
            html.H2("Loading...", id=id_value, className="card-title mt-2"),
            html.Small(icon, className="text-muted")
        ])
    ], className="mb-4 shadow-sm")

# --- LAYOUT ---
layout = dbc.Container([
    # 1. Header & Controls
    dbc.Row([
        dbc.Col(html.H2("🏭 EcoFoundry 6.0 Operations"), width=9),
        dbc.Col(html.Div(id="live-clock", className="text-end text-muted mt-2"), width=3)
    ], className="my-4"),

    # 2. KPI Row (Tier 1 & 2)
    dbc.Row([
        dbc.Col(kpi_card("Net Grid Load (kW)", "kpi-grid-load", "🔌"), width=3),
        dbc.Col(kpi_card("Solar Generation (kW)", "kpi-solar-gen", "☀️"), width=3),
        dbc.Col(kpi_card("Today's Bill (₹)", "kpi-bill", "💰"), width=3),
        dbc.Col(kpi_card("Solar Waste (kWh)", "kpi-waste", "📉"), width=3),
    ]),

    # 3. Main Chart Row (70% Profile / 30% Breakdown)
    dbc.Row([
        # Left: Live Power Profile
        dbc.Col([
            dbc.Card([
                dbc.CardHeader("⚡ Live Power Profile (24h Window)"),
                dbc.CardBody(dcc.Graph(id='chart-power-profile', style={'height': '350px'}))
            ], className="shadow-sm")
        ], width=8),

        # Right: Real-time Line Breakdown
        dbc.Col([
            dbc.Card([
                dbc.CardHeader("⚙️ Line Consumption"),
                dbc.CardBody(dcc.Graph(id='chart-line-breakdown', style={'height': '350px'}))
            ], className="shadow-sm")
        ], width=4),
    ], className="mb-4"),

    # 4. Deep Dive Row (Efficiency & Waste)
    dbc.Row([
        # Left: Energy Intensity Trend
        dbc.Col([
            dbc.Card([
                dbc.CardHeader("📉 Energy Intensity (kWh per Part)"),
                dbc.CardBody(dcc.Graph(id='chart-efficiency', style={'height': '300px'}))
            ], className="shadow-sm")
        ], width=6),

        # Right: Solar Waste Analysis
        dbc.Col([
            dbc.Card([
                dbc.CardHeader("🔋 Opportunity Analysis"),
                dbc.CardBody(dcc.Graph(id='chart-waste-opp', style={'height': '300px'}))
            ], className="shadow-sm")
        ], width=6),
    ]),

    # 5. Hidden Interval for Updates (1 second tick)
    dcc.Interval(id='timer-1s', interval=2000, n_intervals=0)

], fluid=True)