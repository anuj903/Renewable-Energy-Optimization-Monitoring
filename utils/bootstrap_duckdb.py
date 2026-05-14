import os
from pathlib import Path

import duckdb


"""
Utility to (re)build the DuckDB database file used by the app.

It expects CSV files in a source data directory and creates the
`Energy` schema and core tables/views so that existing queries in:
- utils/dashboard_service.py
- utils/forecaster.py
continue to work unchanged.

Usage (local dev):
    DUCKDB_PATH=data/energy.duckdb DUCKDB_SOURCE_DIR=data python -m utils.bootstrap_duckdb
"""


EXPECTED_TABLES = {
    # Main meter time-series: used for KPIs, profiles, and efficiency
    "foundry_main_meter": "Foundry_Main_Meter_15min2024.csv",
    # Weather + solar inputs for the forecaster
    "foundry_weather_solar2024": "Foundry_Weather_Solar2024.csv",
    # Line-level consumption for breakdown chart
    "line1_consumption2024": "Line1_Consumption2024.csv",
    "line2_consumption2024": "Line2_Consumption2024.csv",
    "line3_consumption2024": "Line3_Consumption2024.csv",
    # Production plan table used by the forecaster
    "foundry_daily_production_plan_verified": "Foundry_Daily_Production_Plan_Verified.csv",
    # Optional pre-computed efficiency view data (not present by default)
    # If this CSV is missing, a derived view will be created from foundry_main_meter.
    "view_efficiency": "view_efficiency.csv",
}


def _get_paths():
    db_raw = os.getenv("DUCKDB_PATH", "data/energy.duckdb")
    src_raw = os.getenv("DUCKDB_SOURCE_DIR", "data")

    base_dir = Path(__file__).resolve().parents[1]

    db_path = Path(db_raw)
    if not db_path.is_absolute():
        db_path = base_dir / db_path

    src_dir = Path(src_raw)
    if not src_dir.is_absolute():
        src_dir = base_dir / src_dir

    return db_path, src_dir


def bootstrap():
    db_path, src_dir = _get_paths()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Bootstrapping DuckDB at: {db_path}")
    print(f"Reading CSVs from: {src_dir}")

    con = duckdb.connect(str(db_path), read_only=False)

    # Load each expected table from its CSV if present (into the default schema)
    for table_name, csv_name in EXPECTED_TABLES.items():
        csv_path = src_dir / csv_name
        if not csv_path.exists():
            print(f"Missing CSV for {table_name}: {csv_path}")
            continue

        sql = f"""
            CREATE OR REPLACE TABLE \"{table_name}\" AS
            SELECT * FROM read_csv_auto('{csv_path.as_posix()}');
        """
        print(f"Loading {csv_path.name} into {table_name}")
        con.execute(sql)

    # Create view_power_profile if not provided as a standalone view/CSV
    try:
        print("Ensuring view_power_profile exists...")
        con.execute(
            """
            CREATE OR REPLACE VIEW view_power_profile AS
            SELECT
                "Timestamp",
                "Solar_Gen_KW"  AS "Solar",
                "Total_Foundry_Load_KW" AS "Load"
            FROM "foundry_main_meter";
            """
        )
        print("Created view_power_profile")
    except Exception as e:
        print(f"Could not create view_power_profile: {e}")

    # If we did NOT load a dedicated view_efficiency table, attempt a simple view
    try:
        info = con.execute(
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'view_efficiency';"
        ).fetchone()
        has_eff_table = bool(info and info[0] > 0)
    except Exception:
        has_eff_table = False

    if not has_eff_table:
        try:
            print("Creating derived view_efficiency from foundry_main_meter...")
            con.execute(
                """
                CREATE OR REPLACE VIEW view_efficiency AS
                SELECT
                    CAST("Timestamp" AS DATE) AS "Date",
                    AVG("Solar_Fraction") AS "Energy_Intensity_Per_Unit"
                FROM "foundry_main_meter"
                GROUP BY CAST("Timestamp" AS DATE);
                """
            )
            print("Created view_efficiency")
        except Exception as e:
            print(f"Could not create view_efficiency: {e}")

    con.close()
    print("DuckDB bootstrap complete.")


if __name__ == "__main__":
    bootstrap()

