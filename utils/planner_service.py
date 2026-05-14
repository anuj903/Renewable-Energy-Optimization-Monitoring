import pandas as pd

from utils.forecaster import generate_forecast
from utils.ai_scheduler import get_optimized_schedule


def get_forecast_and_schedule(forecast_date: str, backlog, run_ai: bool = True):
    """
    Shared business logic for planner views.

    Returns a dict with:
    - forecast: DataFrame with forecast data
    - totals: dict with solar/load/free kWh aggregates
    - ai_result: dict returned by the AI scheduler (may be empty)
    """
    df_fc = generate_forecast(forecast_date)
    if df_fc.empty:
        return {
            "forecast": pd.DataFrame(),
            "totals": {"solar": 0, "load": 0, "free": 0},
            "ai_result": {},
        }

    total_solar = int(df_fc["Pred_Solar"].sum() * 0.25)
    total_load = int(df_fc["Likely_Load"].sum() * 0.25)
    total_free = int(df_fc["Available_Waste"].sum() * 0.25)

    ai_result = {}
    if run_ai and backlog:
        try:
            slots = df_fc[df_fc["Available_Waste"] > 20]
            if not slots.empty:
                slots_json = (
                    slots[["date", "Available_Waste"]]
                    .resample("1h", on="date")
                    .mean()
                    .to_json(date_format="iso")
                )
                ai_result = get_optimized_schedule(slots_json, backlog, forecast_date)
        except Exception:
            ai_result = {}

    return {
        "forecast": df_fc,
        "totals": {"solar": total_solar, "load": total_load, "free": total_free},
        "ai_result": ai_result,
    }

