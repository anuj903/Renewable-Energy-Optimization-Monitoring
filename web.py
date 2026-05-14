import os
from datetime import datetime
from pathlib import Path
import csv

from flask import Flask, jsonify, render_template, request

from utils.dashboard_service import get_dashboard_data
from utils.planner_service import get_forecast_and_schedule


BASE_DIR = Path(__file__).resolve().parent
JOB_SPECS_PATH = BASE_DIR / "data" / "Intermittent_Job_Specs.csv"
JOB_SPECS = []
if JOB_SPECS_PATH.exists():
    with JOB_SPECS_PATH.open(newline="") as f:
        reader = csv.DictReader(f)
        JOB_SPECS = list(reader)


def create_app() -> Flask:
    """
    Create a Flask application that exposes:
    - HTML pages (Jinja templates) that mirror the current Dash dashboards.
    - JSON APIs that reuse the same business-logic services as Dash callbacks.
    """
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )

    # -----------------------
    #  HTML ROUTES
    # -----------------------
    @app.route("/")
    def dashboard_page():
        """
        Main operations dashboard.

        The page loads a static HTML skeleton; charts and KPIs are hydrated
        via `/api/dashboard` calls from JavaScript.
        """
        forecast_date = os.getenv("PLANNER_DATE", "2024-12-17")
        return render_template("dashboard.html", forecast_date=forecast_date, job_specs=JOB_SPECS)

    # -----------------------
    #  JSON API ENDPOINTS
    # -----------------------
    @app.get("/api/dashboard")
    def api_dashboard():
        """
        Returns dashboard KPIs and series data used by the HTML frontend.

        Query params (all optional):
        - ts: ISO timestamp for the simulated "now".

        If not provided, we fall back to a simulated historical date that
        matches the DuckDB dataset (2024 data), so the dashboard always
        shows non-empty charts instead of querying the current real date.
        """
        ts_param = request.args.get("ts")
        if ts_param:
            # Accept full ISO strings from JS (e.g. ...Z) by normalizing before parsing
            ts_clean = ts_param.strip()
            if ts_clean.endswith("Z"):
                ts_clean = ts_clean[:-1]
            try:
                current_time = datetime.fromisoformat(ts_clean)
            except ValueError:
                # Fallback to simulated dataset date if parsing fails
                sim_date = os.getenv("DASHBOARD_DATE", "2024-12-17")
                try:
                    current_time = datetime.fromisoformat(f"{sim_date} 17:00:00")
                except ValueError:
                    current_time = datetime.utcnow()
        else:
            # Use a simulated date aligned with the dataset instead of "now"
            sim_date = os.getenv("DASHBOARD_DATE", "2024-12-17")
            try:
                current_time = datetime.fromisoformat(f"{sim_date} 17:00:00")
            except ValueError:
                current_time = datetime.utcnow()

        data = get_dashboard_data(current_time)

        metrics = data["metrics"]
        df_prof = data["df_prof"]
        df_lines = data["df_lines"]
        df_eff = data["df_eff"]

        def _frame_to_dict(df):
            if df is None or df.empty:
                return []
            # Convert any datetime/Timestamp columns to ISO strings so
            # jsonify serialises them as "2024-12-16T09:00:00" rather than
            # the RFC-1123 HTTP date format that Plotly cannot parse.
            df = df.copy()
            for col in df.columns:
                if hasattr(df[col], 'dt'):
                    df[col] = df[col].dt.strftime('%Y-%m-%dT%H:%M:%S')
            return df.to_dict(orient="records")

        payload = {
            "metrics": metrics,
            "profile": _frame_to_dict(df_prof),
            "lines": _frame_to_dict(df_lines),
            "efficiency": _frame_to_dict(df_eff),
        }
        return jsonify(payload)

    @app.post("/api/planner")
    def api_planner():
        """
        Runs forecast + optional AI scheduling.

        Expects JSON body:
        {
          "date": "YYYY-MM-DD",
          "backlog": [ { ... job spec ... }, ... ],
          "run_ai": true | false   # optional, defaults to true
        }
        """
        body = request.get_json(silent=True) or {}
        date_str = body.get("date") or os.getenv("PLANNER_DATE", "2024-12-17")
        backlog = body.get("backlog") or []
        run_ai = body.get("run_ai", True)

        result = get_forecast_and_schedule(date_str, backlog, run_ai=bool(run_ai))

        df_fc = result["forecast"]
        totals = result["totals"]
        ai_result = result.get("ai_result") or {}

        if not df_fc.empty:
            df_fc = df_fc.copy()
            for col in df_fc.columns:
                if hasattr(df_fc[col], 'dt'):
                    df_fc[col] = df_fc[col].dt.strftime('%Y-%m-%dT%H:%M:%S')
            forecast_records = df_fc.to_dict(orient="records")
        else:
            forecast_records = []

        response = {
            "date": date_str,
            "forecast": forecast_records,
            "totals": totals,
            "ai_result": ai_result,
        }
        return jsonify(response)

    return app


# WSGI entrypoint for Gunicorn and local dev
app = create_app()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8050))
    app.run(host="0.0.0.0", port=port, debug=False)
