import joblib
import pandas as pd
import numpy as np
from utils.db_manager import db

try:
    rf_model = joblib.load("solar_model.pkl")
    print("✅ Solar Model Loaded")
except:
    rf_model = None

def generate_forecast(target_date_str):
    if rf_model is None: return pd.DataFrame()

    # 1. FETCH WEATHER (all rows for this date)
    df_db = db.query(f"""
        SELECT "Solar_Irradiance_W_m2", "Direct_Normal_Irradiance_W_m2", "Cloud_Cover_Pct", "Temperature_C"
        FROM "foundry_weather_solar2024"
        WHERE "date" >= '{target_date_str} 00:00:00'
          AND "date" <  '{target_date_str} 23:59:59'
        ORDER BY "date" ASC
    """)
    
    if df_db.empty: 
        print("❌ No weather data found.")
        return pd.DataFrame()

    df_db.columns = [c.lower() for c in df_db.columns]

    # --- 🛑 FORCE PERFECT 24H INDEX (00:00 to 23:00) ---
    # This guarantees we have 24 hourly rows, no matter what the DB gives us
    perfect_24h_index = pd.date_range(start=f"{target_date_str} 00:00:00", periods=24, freq='h')
    
    # Pad or Truncate to exactly 24 rows
    if len(df_db) < 24:
        df_db = df_db.reindex(range(24), method='ffill') # Fill missing hours
    elif len(df_db) > 24:
        df_db = df_db.iloc[:24] # Cut extra hours
        
    # Apply the clean timestamps
    df_db['date'] = perfect_24h_index

    # 2. ML PREDICTION
    df_db['hour'] = df_db['date'].dt.hour
    df_db['month'] = df_db['date'].dt.month
    
    model_input = pd.DataFrame()
    model_input['Hour'] = df_db['hour']
    model_input['Month'] = df_db['month']
    model_input['Solar_Irradiance_W_m2'] = df_db.get('solar_irradiance_w_m2')
    model_input['Direct_Normal_Irradiance_W_m2'] = df_db.get('direct_normal_irradiance_w_m2')
    model_input['Cloud_Cover_Pct'] = df_db.get('cloud_cover_pct')
    model_input['Temperature_C'] = df_db.get('temperature_c')
    
    try:
        df_db['Pred_Solar'] = rf_model.predict(model_input)
    except:
        return pd.DataFrame()

    # 3. INTERPOLATION
    df_fc = df_db[['date', 'Pred_Solar']].set_index('date')
    
    # Resample to 15min. With exactly 24 hourly rows, this will produce exactly 96 rows + 1 (last edge)
    # We use limit_direction='both' to handle edges cleanly
    df_fc = df_fc.resample('15min').interpolate(method='time')
    
    # Enforce exact start/end to avoid "97th" row or "93rd" row issues
    start_ts = pd.to_datetime(f"{target_date_str} 00:00:00")
    end_ts = pd.to_datetime(f"{target_date_str} 23:45:00")
    df_fc = df_fc[(df_fc.index >= start_ts) & (df_fc.index <= end_ts)]
    
    df_fc = df_fc.reset_index()
    df_fc['Pred_Solar'] = df_fc['Pred_Solar'].clip(lower=0)

    # =========================================================
    # 4. LOAD PROFILE DRIVEN BY PRODUCTION PLAN (The Fix)
    # =========================================================
    
    # A. Fetch the Plan for Target Date
    df_plan = db.query(f"""
        SELECT "Status" 
        FROM "foundry_daily_production_plan_verified" 
        WHERE "Date" = '{target_date_str}'
    """)
    
    # B. Count Active Lines
    active_lines = 0
    if not df_plan.empty:
        # Check for 'Production', 'Active', 'On' (Case insensitive)
        active_lines = df_plan[df_plan['Status'].str.lower().isin(['production', 'active', 'on'])].shape[0]
        print(f"✅ Found Plan for {target_date_str}: {active_lines} Lines Active")
    else:
        print(f"⚠️ No Plan found for {target_date_str}. Assuming Default (2 Lines).")
        active_lines = 2 # Default fallback

    # C. Fetch Base Profile (Weekdays Only)
    # We use Average Weekday Load as the 'Base Shape'
    df_hist = db.query("""
        SELECT 
            EXTRACT(HOUR FROM "Timestamp") as h, 
            EXTRACT(MINUTE FROM "Timestamp") as m, 
            AVG("Total_Foundry_Load_KW") as avg_load
        FROM "foundry_main_meter"
        WHERE EXTRACT(ISODOW FROM "Timestamp") < 6
        GROUP BY 1, 2
    """)
    
    if df_hist.empty: return pd.DataFrame()
    df_hist.columns = [c.lower() for c in df_hist.columns]
    
    # Merge
    df_fc['h'] = df_fc['date'].dt.hour.astype(int)
    df_fc['m'] = df_fc['date'].dt.minute.astype(int)
    df_hist['h'] = df_hist['h'].astype(int)
    df_hist['m'] = df_hist['m'].astype(int)
    
    df_final = pd.merge(df_fc, df_hist, on=['h', 'm'], how='left')

    # D. APPLY SCALING LOGIC
    # Formula: 0.4 (Baseload) + 0.2 per active line.
    # If 3 lines are active, Scale = 1.0.
    # But note: The DB 'avg_load' is an AVERAGE (mix of 1, 2, and 3 line days).
    # It is roughly ~85k kWh.
    # To hit ~123k (Peak Capacity) when Scale = 1.0, we need to boost the average 
    # by a 'Peak Factor' (approx 1.45x).
    
    user_scale = 0.3 + (0.2 * active_lines)
    peak_calibration_factor = 1.15
    
    # 5. FINAL CALCS
    df_final['Likely_Load'] = df_final['avg_load'].fillna(0) * user_scale * peak_calibration_factor    
    # FILL ANY REMAINING GAPS (The Chart Fix)
    df_final['Pred_Solar'] = df_final['Pred_Solar'].fillna(0)
    
    df_final['Available_Waste'] = (df_final['Pred_Solar'] - df_final['Likely_Load']).clip(lower=0)    
    # Check row count
    print(f"✅ Generated Forecast: {len(df_final)} rows")
    
    return df_final