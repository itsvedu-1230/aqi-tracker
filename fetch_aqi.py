"""
fetch_aqi.py
------------
Pulls real-time air quality data for a city from India's CPCB
(Central Pollution Control Board) open data API, via data.gov.in.

This replaces an earlier version built on WAQI. The switch happened
because WAQI's single station for Bareilly (Rajendra Nagar) had gone
stale -- its last actual sensor reading was ~2 months old, but WAQI
kept serving that same cached value on every fetch without any error.
Going straight to CPCB, the actual government source WAQI itself
aggregates from, avoids that caching layer entirely.

Two things are structurally different from the WAQI version:

1. This queries by CITY NAME (e.g. "Bareilly"), not a single station
   slug. CPCB typically runs multiple monitoring stations per city, so
   this fetches ALL of them and stores one row per station per run,
   rather than picking just one.

2. Each pollutant CPCB returns (PM2.5, PM10, NO2, SO2, CO, OZONE, NH3)
   is already reported as a 0-500 AQI SUB-INDEX, not a raw
   concentration in ug/m3 -- so no breakpoint formula needs to be
   implemented here. Per CPCB's own official methodology, a station's
   overall AQI is simply the maximum sub-index across its reported
   pollutants (whichever pollutant is worst determines the number),
   which is what get computed below.

Run it like:
    CPCB_API_KEY=your_key_here CITY=Bareilly python fetch_aqi.py

Environment variables:
    CPCB_API_KEY - free key from https://data.gov.in (My Account -> API Keys)
    CITY         - city name exactly as CPCB lists it, e.g. "Bareilly"
"""

import os
import sys
import sqlite3
import json
import time
from datetime import datetime, timezone
from collections import defaultdict
import urllib.request
import urllib.parse
import urllib.error

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "aqi.db")

# This is CPCB's "Real time Air Quality Index from various locations"
# dataset on data.gov.in -- every resource on that platform has a
# fixed ID like this, separate from your personal API key.
RESOURCE_ID = "3b01bcb8-0b14-4abf-b6f2-c1bfd384ba69"


def get_env_or_die(name: str) -> str:
    """Read a required environment variable, or exit with a clear error."""
    value = os.environ.get(name)
    if not value:
        print(f"ERROR: environment variable {name} is not set.", file=sys.stderr)
        print("See the top of fetch_aqi.py for what's expected.", file=sys.stderr)
        sys.exit(1)
    return value


def fetch_city_records(city: str, api_key: str) -> list:
    """Call the CPCB API and return the raw list of pollutant records for this city.

    The API returns one row PER POLLUTANT PER STATION -- e.g. a city
    with 2 stations each reporting 5 pollutants comes back as 10 flat
    records, not nested by station. group_by_station() below is what
    turns that into something usable.

    data.gov.in's API is a government service and noticeably slower /
    flakier than something like WAQI -- it's common for a request to
    simply time out under load rather than return an error response.
    A single timeout used to crash the whole run (caught only
    urllib.error.URLError, which doesn't cover every timeout path --
    a bare TimeoutError can surface directly from the underlying
    socket read instead of being wrapped). This now retries a few
    times with a short backoff before giving up, since a slow response
    one cycle doesn't mean the API is actually down.

    A request built with just urlopen(url) sends Python's bare default
    User-Agent header (e.g. "Python-urllib/3.12"). Some government
    APIs quietly stall (rather than reject) requests that don't look
    like they're coming from a real browser, as basic anti-bot
    protection -- which looks EXACTLY like a network timeout from the
    caller's side, making it easy to misdiagnose as "the server is
    just slow." Setting a normal browser-like User-Agent below is a
    common, low-risk workaround for that -- this is still the same
    legitimate request with a valid API key, just with a header most
    real HTTP clients already send by default.
    """
    params = urllib.parse.urlencode({
        "api-key": api_key,
        "format": "json",
        "filters[city]": city,
        "limit": 100,
    })
    url = f"https://api.data.gov.in/resource/{RESOURCE_ID}?{params}"
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/124.0.0.0 Safari/537.36"),
            "Accept": "application/json",
        },
    )

    max_attempts = 3
    last_error = None

    for attempt in range(1, max_attempts + 1):
        try:
            with urllib.request.urlopen(request, timeout=25) as response:
                payload = json.loads(response.read().decode("utf-8"))
            break
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last_error = e
            if attempt < max_attempts:
                wait_seconds = 5 * attempt  # 5s, then 10s
                print(f"WARNING: attempt {attempt}/{max_attempts} failed "
                      f"({e}). Retrying in {wait_seconds}s...", file=sys.stderr)
                time.sleep(wait_seconds)
            else:
                print(f"ERROR: could not reach CPCB API after "
                      f"{max_attempts} attempts: {e}", file=sys.stderr)
                sys.exit(1)
    else:
        # Shouldn't be reachable (the loop above always either breaks
        # or exits), but guards against silently falling through with
        # no payload if that ever changes.
        print(f"ERROR: could not reach CPCB API: {last_error}", file=sys.stderr)
        sys.exit(1)

    if payload.get("status") != "ok":
        print(f"ERROR: CPCB API returned status={payload.get('status')!r}", file=sys.stderr)
        sys.exit(1)

    return payload.get("records", [])


def group_by_station(records: list) -> dict:
    """Turn CPCB's flat pollutant-per-row list into one entry per station.

    Each station ends up with every pollutant's sub-index, plus the
    station's overall AQI (the max sub-index across pollutants, per
    CPCB's official rule) and which pollutant is driving that number
    -- the "dominant pollutant".

    Rows with avg_value of "NA" (a pollutant the station doesn't
    monitor, or a momentary gap) are skipped rather than treated as 0
    -- a missing reading isn't the same as a good one.
    """
    stations = defaultdict(lambda: {"pollutants": {}, "last_update": None,
                                     "latitude": None, "longitude": None})

    for r in records:
        station_name = r.get("station")
        avg_raw = r.get("avg_value")
        if station_name is None or avg_raw in (None, "NA", ""):
            continue
        try:
            avg_value = float(avg_raw)
        except ValueError:
            continue

        entry = stations[station_name]
        entry["pollutants"][r.get("pollutant_id")] = avg_value
        entry["last_update"] = r.get("last_update")
        entry["latitude"] = r.get("latitude")
        entry["longitude"] = r.get("longitude")

    results = {}
    for station_name, entry in stations.items():
        if not entry["pollutants"]:
            continue
        dominant_pollutant = max(entry["pollutants"], key=entry["pollutants"].get)
        aqi = entry["pollutants"][dominant_pollutant]
        results[station_name] = {
            "aqi": aqi,
            "dominant_pollutant": dominant_pollutant,
            "pollutants": entry["pollutants"],
            "last_update": entry["last_update"],
            "latitude": entry["latitude"],
            "longitude": entry["longitude"],
        }
    return results


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Create the readings table if this is the first run.

    This schema is NOT compatible with the earlier WAQI-based version
    (that one had no `station` column, since it only ever tracked one
    station). If you're upgrading from that version, start with a
    fresh data/aqi.db rather than trying to migrate -- the old data
    was from a stalled sensor anyway, so there's nothing worth
    carrying forward.
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS readings (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            city                TEXT NOT NULL,
            station             TEXT NOT NULL,
            fetched_at          TEXT NOT NULL,   -- ISO 8601 UTC timestamp
            station_time        TEXT,            -- CPCB's own "last_update" for this station
            aqi                 REAL,
            dominant_pollutant  TEXT,
            pollutants_json     TEXT,            -- every pollutant's sub-index, for later digging
            latitude            TEXT,
            longitude           TEXT
        )
        """
    )
    conn.commit()


def main():
    city = get_env_or_die("CITY")
    api_key = get_env_or_die("CPCB_API_KEY")

    records = fetch_city_records(city, api_key)
    stations = group_by_station(records)

    if not stations:
        print(f"WARNING: no usable station data returned for city={city!r}. "
              "This can happen if every pollutant came back as 'NA' this "
              "cycle -- not necessarily an error, but worth checking if it "
              "repeats.")
        return

    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    ensure_schema(conn)

    fetched_at = datetime.now(timezone.utc).isoformat()

    for station_name, data in stations.items():
        conn.execute(
            """
            INSERT INTO readings
                (city, station, fetched_at, station_time, aqi,
                 dominant_pollutant, pollutants_json, latitude, longitude)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                city, station_name, fetched_at, data["last_update"],
                data["aqi"], data["dominant_pollutant"],
                json.dumps(data["pollutants"]), data["latitude"], data["longitude"],
            ),
        )
        print(f"Saved reading for {station_name}: AQI={data['aqi']} "
              f"(dominant: {data['dominant_pollutant']})")

    conn.commit()
    conn.close()


if __name__ == "__main__":
    main()
