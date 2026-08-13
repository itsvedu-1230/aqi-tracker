"""
check_history.py
-----------------
Lists every stored reading for a city side-by-side: when YOU fetched
it (fetched_at) vs. when the station itself says it took that reading
(station_time). If station_time barely moves across many fetches
while fetched_at keeps advancing, that's a strong sign the underlying
sensor is stuck or offline, and WAQI is just re-serving its last
known cached value every time — not that anything in this pipeline
is broken.

Run it from inside the aqi-tracker folder:
    python3 check_history.py
"""

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "aqi.db")


def main():
    if not os.path.exists(DB_PATH):
        print("No database found at data/aqi.db — run fetch_aqi.py first.")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT fetched_at, station_time, aqi
        FROM readings
        ORDER BY fetched_at ASC
        """
    ).fetchall()
    conn.close()

    if not rows:
        print("Database exists but has no readings yet.")
        return

    print(f"{'Fetched at (UTC)':<26} {'Station reports (station_time)':<32} {'AQI'}")
    print("-" * 70)
    for r in rows:
        print(f"{r['fetched_at']:<26} {str(r['station_time']):<32} {r['aqi']}")

    # Flag if station_time hasn't changed across the last several fetches --
    # that's the actual signature of a stalled sensor, not just "AQI
    # happened to repeat."
    recent = rows[-6:] if len(rows) >= 6 else rows
    distinct_station_times = {r["station_time"] for r in recent}
    print()
    if len(distinct_station_times) == 1 and len(recent) > 1:
        print("⚠ station_time has NOT changed across your last "
              f"{len(recent)} fetches. This strongly suggests the "
              "sensor itself is stuck/offline, and WAQI is repeatedly "
              "serving its last cached reading rather than a live one.")
    else:
        print(f"station_time changed {len(distinct_station_times)} times "
              f"across your last {len(recent)} fetches — looks like the "
              "sensor is actively reporting.")


if __name__ == "__main__":
    main()
