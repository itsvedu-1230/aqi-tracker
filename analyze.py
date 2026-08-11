"""
analyze.py
----------
Reads every stored reading for a city out of data/aqi.db, and computes:

  - a 7-day rolling average (smooths out day-to-day noise)
  - week-over-week percent change (is this week better or worse than last?)
  - a z-score anomaly flag (is *today* unusually far from the recent normal?)
  - a plain-English one-line summary of the above

Writes the result to data/summary.json, which generate_dashboard.py
then reads. Splitting "compute the numbers" (this file) from "draw the
page" (generate_dashboard.py) is deliberate: it means you can swap the
dashboard's look later without touching the analysis logic at all.
"""

import os
import json
import sqlite3
import statistics
from datetime import datetime, timezone

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "aqi.db")
SUMMARY_PATH = os.path.join(os.path.dirname(__file__), "data", "summary.json")

# WAQI's standard AQI breakpoints, used to label a number as more than
# just a number.
AQI_BANDS = [
    (0, 50, "Good", "#3E7C6F"),
    (51, 100, "Satisfactory", "#8FA85E"),
    (101, 200, "Moderate", "#D9A441"),
    (201, 300, "Poor", "#D9722C"),
    (301, 400, "Very Poor", "#C0432E"),
    (401, 1000, "Severe", "#7A2E3A"),
]


def band_for(aqi: int):
    for lo, hi, label, color in AQI_BANDS:
        if lo <= aqi <= hi:
            return label, color
    return "Unknown", "#888888"


def load_readings(city: str):
    if not os.path.exists(DB_PATH):
        print("No database found yet — run fetch_aqi.py at least once first.")
        return []

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT fetched_at, aqi, pm25, pm10
        FROM readings
        WHERE city = ?
        ORDER BY fetched_at ASC
        """,
        (city,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def rolling_average(values, window):
    """Simple trailing rolling average, one output per input point.

    For the first `window - 1` points there isn't enough history yet,
    so we average over whatever's available rather than returning None —
    a chart with gaps at the start looks broken; this doesn't.
    """
    out = []
    for i in range(len(values)):
        start = max(0, i - window + 1)
        chunk = values[start : i + 1]
        out.append(round(sum(chunk) / len(chunk), 1))
    return out


def week_over_week(values):
    """% change between the average of the last 7 readings and the 7 before that."""
    if len(values) < 14:
        return None
    last_week = values[-7:]
    prior_week = values[-14:-7]
    prior_avg = sum(prior_week) / len(prior_week)
    last_avg = sum(last_week) / len(last_week)
    if prior_avg == 0:
        return None
    return round(((last_avg - prior_avg) / prior_avg) * 100, 1)


def anomaly_flag(values):
    """Is today's reading a statistical outlier vs. the recent history?

    We use a z-score: how many standard deviations today's value sits
    from the mean of the last 14 days (excluding today itself). A
    |z| > 2 is a common, simple threshold for "worth flagging" without
    being so sensitive it cries wolf on ordinary noise.
    """
    if len(values) < 8:
        return None, None

    history = values[-15:-1] if len(values) >= 15 else values[:-1]
    if len(history) < 5:
        return None, None

    mean = statistics.mean(history)
    stdev = statistics.pstdev(history)
    today = values[-1]

    if stdev == 0:
        return 0.0, False

    z = round((today - mean) / stdev, 2)
    return z, abs(z) > 2


def build_summary(city: str):
    readings = load_readings(city)
    if not readings:
        return {"city": city, "has_data": False}

    aqi_values = [r["aqi"] for r in readings if r["aqi"] is not None]
    dates = [r["fetched_at"] for r in readings if r["aqi"] is not None]

    rolling = rolling_average(aqi_values, window=7)
    wow_change = week_over_week(aqi_values)
    z, is_anomaly = anomaly_flag(aqi_values)

    latest_aqi = aqi_values[-1]
    label, color = band_for(latest_aqi)

    # Plain-English summary, built from simple rules (no external AI
    # call needed, so this works offline and with zero extra cost —
    # you can always swap this function for an LLM-generated version
    # later as a polish step).
    lines = [f"Today's AQI in {city.title()} is {latest_aqi} ({label})."]
    if wow_change is not None:
        direction = "worse" if wow_change > 0 else "better"
        lines.append(f"That's {abs(wow_change)}% {direction} than last week.")
    if is_anomaly:
        direction = "higher" if z > 0 else "lower"
        lines.append(f"This is unusually {direction} than the recent norm "
                      f"(z={z}) — worth a closer look.")

    return {
        "city": city,
        "has_data": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dates": dates,
        "aqi_values": aqi_values,
        "rolling_7d": rolling,
        "latest_aqi": latest_aqi,
        "latest_band": label,
        "latest_color": color,
        "week_over_week_pct": wow_change,
        "anomaly_zscore": z,
        "is_anomaly": is_anomaly,
        "summary_text": " ".join(lines),
    }


def main():
    city = os.environ.get("CITY", "bareilly")
    summary = build_summary(city)
    os.makedirs(os.path.dirname(SUMMARY_PATH), exist_ok=True)
    with open(SUMMARY_PATH, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"Wrote summary to {SUMMARY_PATH}")
    if summary.get("has_data"):
        print(summary["summary_text"])


if __name__ == "__main__":
    main()
