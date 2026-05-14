"""
Developer-only utility for scanning CSV datasets with DuckDB
and generating a JSON schema file for the LLM.

This script is **not** used by the deployed web app and assumes
`duckdb` is installed from `requirements-dev.txt`.
"""

import duckdb
import json
import os
import pandas as pd

DATA_FOLDER = "../data"
OUTPUT_FILE = "../config/schemas.json"

def get_duckdb_type(dtype):
    """Map Pandas/Numpy types to SQL types for the LLM"""
    if 'int' in str(dtype): return 'INTEGER'
    if 'float' in str(dtype): return 'DECIMAL'
    if 'datetime' in str(dtype): return 'TIMESTAMP'
    return 'VARCHAR'

def scan_datasets():
    schemas = {}
    
    # Initialize DuckDB connection
    con = duckdb.connect(database=':memory:')
    
    files = [f for f in os.listdir(DATA_FOLDER) if f.endswith('.csv')]
    
    print(f"🔍 Scanning {len(files)} files...")
    
    for file in files:
        file_path = os.path.join(DATA_FOLDER, file)
        table_name = file.replace(".csv", "").replace(" ", "_").lower()
        
        # Load CSV into DuckDB virtually to sniff types
        con.execute(f"CREATE OR REPLACE VIEW {table_name} AS SELECT * FROM read_csv_auto('{file_path}')")
        
        # Get Column Info
        df_summ = con.execute(f"DESCRIBE {table_name}").df()
        
        columns_info = []
        for _, row in df_summ.iterrows():
            col_name = row['column_name']
            col_type = row['column_type']
            
            # Metadata: Get min/max for numbers, unique values for text (if few)
            metadata = ""
            try:
                if 'DOUBLE' in col_type or 'BIGINT' in col_type:
                    stats = con.execute(f"SELECT MIN({col_name}), MAX({col_name}), AVG({col_name}) FROM {table_name}").fetchone()
                    metadata = f"Range: {int(stats[0] or 0)} to {int(stats[1] or 0)}"
                elif 'VARCHAR' in col_type:
                    # Check cardinality
                    count = con.execute(f"SELECT COUNT(DISTINCT {col_name}) FROM {table_name}").fetchone()[0]
                    if count < 10:
                        vals = con.execute(f"SELECT DISTINCT {col_name} FROM {table_name}").df()[col_name].tolist()
                        metadata = f"Categories: {vals}"
            except:
                pass

            columns_info.append({
                "name": col_name,
                "type": col_type,
                "context": metadata
            })
            
        schemas[table_name] = {
            "description": f"Data loaded from {file}",
            "columns": columns_info
        }
        print(f"✅ Processed {table_name}")

    # Save to JSON
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(schemas, f, indent=4)
    
    print(f"\n🎉 Schema saved to {OUTPUT_FILE}")

if __name__ == "__main__":
    scan_datasets()