import os
from pathlib import Path

import duckdb
import pandas as pd


def _get_duckdb_path() -> Path:
    """
    Resolve the DuckDB database path using DUCKDB_PATH or a sensible default.
    """
    raw_path = os.getenv("DUCKDB_PATH", "data/energy.duckdb")
    path = Path(raw_path)
    if not path.is_absolute():
        base_dir = Path(__file__).resolve().parents[1]
        path = base_dir / path
    return path


class DBManager:
    """
    DuckDB-backed data access layer exposing:
    - db.query(sql: str) -> pandas.DataFrame
    - db.get_live_chart_data(current_sim_time) -> pandas.DataFrame
    """

    def __init__(self):
        try:
            db_path = _get_duckdb_path()
            db_path.parent.mkdir(parents=True, exist_ok=True)
            self.con = duckdb.connect(str(db_path), read_only=False)
            print(f"Connected to DuckDB at {db_path}")
        except Exception as e:
            print(f"DuckDB Connection Failed: {e}")
            self.con = None

    def get_live_chart_data(self, current_sim_time):
        """Fetches current day's window for the Power Flow chart"""
        if self.con is None or current_sim_time is None:
            return pd.DataFrame()

        ts_str = current_sim_time.strftime("%Y-%m-%d %H:%M:%S")
        date_str = current_sim_time.strftime("%Y-%m-%d")

        query = f"""
            SELECT *
            FROM view_power_profile
            WHERE "Timestamp" >= '{date_str} 00:00:00'
              AND "Timestamp" <= CAST('{ts_str}' AS TIMESTAMP)
            ORDER BY "Timestamp" ASC
        """

        try:
            return self.con.execute(query).fetchdf()
        except Exception as e:
            print(f"❌ Chart Query Error (DuckDB): {e}")
            return pd.DataFrame()

    def query(self, sql_query):
        """General Query Executor using DuckDB"""
        if self.con is None or not sql_query:
            return pd.DataFrame()

        try:
            return self.con.execute(sql_query).fetchdf()
        except Exception as e:
            print(f"❌ Query Failed (DuckDB): {e}")
            return pd.DataFrame()


# Initialize
db = DBManager()