"""
analyze.py
----------
Reads every stored reading for a city out of data/aqi.db, and computes:

  - a true daily average AQI, by grouping all of that day's intraday
    samples together (the workflow now fetches every 3 hours, so a
    day is no longer just one snapshot)
  - a 7-day rolling average over those daily averages (smooths out
    day-to-day noise)
  - week-over-week percent change (is this week better or worse than
    last?)
  - a z-score anomaly flag (is *today* unusually far from the recent
    normal?)
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
from zoneinfo import ZoneInfo

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "aqi.db")
SUMMARY_PATH = os.path.join(os.path.dirname(__file__), "data", "summary.json")

# "Today" should mean today in the city being tracked, not in UTC —
# otherwise a sample taken at 11pm IST would get grouped into
# tomorrow's UTC date, which would be a confusing bug to explain.
LOCAL_TZ = ZoneInfo("Asia/Kolkata")

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


def band_for(aqi: float):
    aqi_int = round(aqi)
    for lo, hi, label, color in AQI_BANDS:
        if lo <= aqi_int <= hi:
            return label, color
    return "Unknown", "#888888"


def load_readings(city: str):
    """Every raw intraday sample for this city, oldest first."""
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


def group_into_daily_averages(readings):
    """Collapse raw intraday samples into one average-AQI-per-day series.

    Each reading's UTC timestamp is converted to Asia/Kolkata before
    taking its calendar date, so a run at 11:30pm IST (which is
    18:00 UTC, still "today" in UTC too in this case, but the
    conversion matters generally) always lands on the correct local day.

    Returns two parallel lists, oldest day first:
        dates       -- ISO date strings, e.g. "2026-08-12"
        daily_avg   -- mean AQI of that day's samples, rounded to 1dp
    plus a dict mapping date -> number of samples that day, so the
    dashboard can show "based on N readings" and flag partial days.
    """
    by_date = {}
    for r in readings:
        if r["aqi"] is None:
            continue
        utc_dt = datetime.fromisoformat(r["fetched_at"])
        local_date = utc_dt.astimezone(LOCAL_TZ).date().isoformat()
        by_date.setdefault(local_date, []).append(r["aqi"])

    dates = sorted(by_date.keys())
    daily_avg = [round(sum(by_date[d]) / len(by_date[d]), 1) for d in dates]
    sample_counts = {d: len(by_date[d]) for d in dates}
    return dates, daily_avg, sample_counts


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
    """% change between the average of the last 7 days and the 7 before that."""
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
    """Is today's daily average a statistical outlier vs. recent history?

    We use a z-score: how many standard deviations today's daily
    average sits from the mean of the last 14 days (excluding today
    itself). A |z| > 2 is a common, simple threshold for "worth
    flagging" without being so sensitive it cries wolf on ordinary
    noise.
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

    dates, daily_avg, sample_counts = group_into_daily_averages(readings)
    if not dates:
        return {"city": city, "has_data": False}

    rolling = rolling_average(daily_avg, window=7)
    wow_change = week_over_week(daily_avg)
    z, is_anomaly = anomaly_flag(daily_avg)

    latest_date = dates[-1]
    latest_avg = daily_avg[-1]
    samples_today = sample_counts[latest_date]
    label, color = band_for(latest_avg)

    # Is "today" (in Asia/Kolkata) still in progress, or is this a
    # fully-elapsed day? Lets the dashboard say "so far" honestly
    # instead of implying the average is final while the day is
    # still collecting samples.
    today_local = datetime.now(timezone.utc).astimezone(LOCAL_TZ).date().isoformat()
    is_partial_day = latest_date == today_local

    # Plain-English summary, built from simple rules (no external AI
    # call needed, so this works offline and with zero extra cost —
    # you can always swap this function for an LLM-generated version
    # later as a polish step).
    day_phrase = "so far today" if is_partial_day else f"on {latest_date}"
    lines = [f"Average AQI in {city.title()} {day_phrase} is {latest_avg} "
             f"({label}), based on {samples_today} reading"
             f"{'s' if samples_today != 1 else ''}."]
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
        "daily_avg_aqi": daily_avg,
        "rolling_7d": rolling,
        "latest_date": latest_date,
        "latest_avg_aqi": latest_avg,
        "latest_band": label,
        "latest_color": color,
        "samples_today": samples_today,
        "is_partial_day": is_partial_day,
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
