import pandas as pd

from datetime import timedelta
from utils.db_manager import db


def get_dashboard_data(current_sim_time):
    """
    Shared business logic for the live dashboard.

    Returns a dict with:
    - metrics: dict of aggregated KPI values
    - df_prof: DataFrame for the 24h power profile
    - df_lines: DataFrame for line-level consumption
    - df_eff: DataFrame for efficiency trend
    """
    if current_sim_time is None:
        return {
            "metrics": {"g": 0, "s": 0, "w": 0},
            "df_prof": pd.DataFrame(),
            "df_lines": pd.DataFrame(),
            "df_eff": pd.DataFrame(),
        }

    ts_str = current_sim_time.strftime("%Y-%m-%d %H:%M:%S")
    date_str = current_sim_time.strftime("%Y-%m-%d")

    # KPIs & main data (from start of day onwards)
    df_d = db.query(
        f"""
        SELECT 
            SUM("Grid_Draw_KW"*0.25) as g, 
            SUM("Solar_Gen_KW"*0.25) as s, 
            SUM("Solar_Wasted_KW"*0.25) as w 
        FROM "foundry_main_meter" 
        WHERE "Timestamp" >= '{date_str} 00:00:00' 
          AND "Timestamp" <= '{ts_str}'
        """
    )
    if not df_d.empty:
        g = df_d.iloc[0].get("g") or 0
        s = df_d.iloc[0].get("s") or 0
        w = df_d.iloc[0].get("w") or 0
    else:
        g = s = w = 0

    # Power profile
    df_prof = db.get_live_chart_data(current_sim_time)

    # Line breakdown (from start of day onwards)
    df_lines = db.query(
        f"""
        SELECT 'Line 1' as Line, SUM("Total_Line_KW"*0.25) as kWh 
        FROM "line1_consumption2024" 
        WHERE "Timestamp" >= '{date_str} 00:00:00' AND "Timestamp" <= '{ts_str}'
        UNION ALL 
        SELECT 'Line 2', SUM("Total_Line_KW"*0.25) 
        FROM "line2_consumption2024" 
        WHERE "Timestamp" >= '{date_str} 00:00:00' AND "Timestamp" <= '{ts_str}'
        UNION ALL 
        SELECT 'Line 3', SUM("Total_Line_KW"*0.25) 
        FROM "line3_consumption2024" 
        WHERE "Timestamp" >= '{date_str} 00:00:00' AND "Timestamp" <= '{ts_str}'
        """
    )

    # Efficiency trend
    df_eff = db.query(
        f"""
        SELECT "Date", AVG("Energy_Intensity_Per_Unit") as val 
        FROM view_efficiency 
        WHERE "Date" < '{date_str}' 
        GROUP BY "Date" 
        ORDER BY "Date" DESC 
        LIMIT 7
        """
    )

    return {
        "metrics": {"g": g, "s": s, "w": w},
        "df_prof": df_prof,
        "df_lines": df_lines,
        "df_eff": df_eff,
    }

