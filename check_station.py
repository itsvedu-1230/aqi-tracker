"""
check_station.py
-----------------
Prints out exactly which physical monitoring station WAQI's API is
reading from for your most recent reading, using the raw_json column
that fetch_aqi.py already saves with every row (it saves the full API
response precisely so this kind of digging is possible later without
needing to re-fetch anything).

Run it from inside the aqi-tracker folder:
    python3 check_station.py
"""

import sqlite3
import json
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "aqi.db")


def main():
    if not os.path.exists(DB_PATH):
        print("No database found at data/aqi.db — run fetch_aqi.py first.")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT fetched_at, aqi, raw_json FROM readings ORDER BY fetched_at DESC LIMIT 1"
    ).fetchone()
    conn.close()

    if row is None:
        print("Database exists but has no readings yet.")
        return

    data = json.loads(row["raw_json"])

    print(f"Reading fetched at (UTC): {row['fetched_at']}")
    print(f"AQI reported: {row['aqi']}")
    print()

    city_info = data.get("city", {})
    print("--- Station details ---")
    print(f"Station name: {city_info.get('name', 'not provided')}")
    print(f"Coordinates:  {city_info.get('geo', 'not provided')}")
    print(f"Station URL:  {city_info.get('url', 'not provided')}")

    attributions = data.get("attributions", [])
    if attributions:
        print()
        print("--- Data attribution (where WAQI sourced this from) ---")
        for a in attributions:
            print(f"- {a.get('name', 'unknown')}: {a.get('url', '')}")

    dominant = data.get("dominentpol")
    if dominant:
        print()
        print(f"Dominant pollutant driving this AQI figure: {dominant}")


if __name__ == "__main__":
    main()
