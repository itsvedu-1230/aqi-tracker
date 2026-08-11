"""
fetch_aqi.py
------------
Pulls today's air quality reading for one city from the WAQI
(World Air Quality Index) public API, and appends it to a local
SQLite database (data/aqi.db).

WAQI is used because it's free, covers Indian cities well (it
aggregates India's CPCB station data), and needs only a free
token — no credit card, no approval wait.

Run it like:
    AQI_TOKEN=your_token_here CITY=bareilly python fetch_aqi.py

Environment variables:
    AQI_TOKEN  - your free token from https://aqicn.org/data-platform/token/
    CITY       - the city slug WAQI expects, e.g. "bareilly", "delhi", "mumbai"
"""

import os
import sys
import sqlite3
import json
from datetime import datetime, timezone
import urllib.request
import urllib.error

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "aqi.db")


def get_env_or_die(name: str) -> str:
    """Read a required environment variable, or exit with a clear error.

    Failing loudly here (instead of silently using a placeholder) matters:
    a script that fetches nothing but doesn't complain is far worse than
    one that stops and tells you exactly what's missing.
    """
    value = os.environ.get(name)
    if not value:
        print(f"ERROR: environment variable {name} is not set.", file=sys.stderr)
        print("See the top of fetch_aqi.py for what's expected.", file=sys.stderr)
        sys.exit(1)
    return value


def fetch_reading(city: str, token: str) -> dict:
    """Call the WAQI API and return the parsed JSON response."""
    url = f"https://api.waqi.info/feed/{city}/?token={token}"
    try:
        with urllib.request.urlopen(url, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as e:
        print(f"ERROR: could not reach WAQI API: {e}", file=sys.stderr)
        sys.exit(1)

    if payload.get("status") != "ok":
        # WAQI returns status="error" with a message when the city slug
        # is wrong or the token is invalid/rate-limited.
        print(f"ERROR: WAQI API returned status={payload.get('status')!r}: "
              f"{payload.get('data')}", file=sys.stderr)
        sys.exit(1)

    return payload["data"]


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Create the readings table if this is the first run.

    One row per (city, fetched_at). We store the individual pollutant
    sub-indices (pm25, pm10, etc.) as separate columns because WAQI's
    headline "aqi" number is just the worst of these, and later on
    you may want to know *which* pollutant is driving a bad day.
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS readings (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            city          TEXT NOT NULL,
            fetched_at    TEXT NOT NULL,   -- ISO 8601 UTC timestamp
            station_time  TEXT,            -- timestamp the station itself reports
            aqi           INTEGER,         -- WAQI's overall AQI (max of sub-indices)
            pm25          REAL,
            pm10          REAL,
            o3            REAL,
            no2           REAL,
            so2           REAL,
            co            REAL,
            raw_json      TEXT             -- full API response, kept for safety
        )
        """
    )
    conn.commit()


def extract_fields(data: dict) -> dict:
    """Pull out the sub-indices we care about, tolerating missing ones.

    Not every station reports every pollutant, so each lookup defaults
    to None rather than raising a KeyError.
    """
    iaqi = data.get("iaqi", {})

    def sub(key: str):
        entry = iaqi.get(key)
        return entry.get("v") if entry else None

    return {
        "aqi": data.get("aqi"),
        "station_time": data.get("time", {}).get("s"),
        "pm25": sub("pm25"),
        "pm10": sub("pm10"),
        "o3": sub("o3"),
        "no2": sub("no2"),
        "so2": sub("so2"),
        "co": sub("co"),
    }


def main():
    city = get_env_or_die("CITY")
    token = get_env_or_die("AQI_TOKEN")

    data = fetch_reading(city, token)
    fields = extract_fields(data)

    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    ensure_schema(conn)

    conn.execute(
        """
        INSERT INTO readings
            (city, fetched_at, station_time, aqi, pm25, pm10, o3, no2, so2, co, raw_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            city,
            datetime.now(timezone.utc).isoformat(),
            fields["station_time"],
            fields["aqi"],
            fields["pm25"],
            fields["pm10"],
            fields["o3"],
            fields["no2"],
            fields["so2"],
            fields["co"],
            json.dumps(data),
        ),
    )
    conn.commit()
    conn.close()

    print(f"Saved reading for {city}: AQI={fields['aqi']} "
          f"(pm2.5={fields['pm25']}, pm10={fields['pm10']})")


if __name__ == "__main__":
    main()
