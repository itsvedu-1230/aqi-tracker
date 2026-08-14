"""
analyze.py
----------
Reads every stored reading out of data/aqi.db and computes, SEPARATELY
FOR EACH STATION in the city (Bareilly currently has two: Rajendra
Nagar and Civil Lines):

  - a true daily average AQI, by grouping that station's intraday
    samples together (converted to Asia/Kolkata local time first, so
    "today" means today in India, not in UTC)
  - a 7-day rolling average over those daily averages
  - week-over-week percent change
  - a z-score anomaly flag (is *today* unusually far from that
    station's own recent normal?)
  - a plain-English one-line summary

Writes the result to data/summary.json as one entry per station, which
generate_dashboard.py then reads to render a separate section for
each. Keeping "compute the numbers" (this file) separate from "draw
the page" (generate_dashboard.py) means the look can change later
without touching this logic at all.
"""

import os
import json
import sqlite3
import statistics
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "aqi.db")
SUMMARY_PATH = os.path.join(os.path.dirname(__file__), "data", "summary.json")

# "Today" should mean today in the city being tracked, not in UTC --
# otherwise a sample taken late at night IST could get grouped into
# the wrong calendar day.
LOCAL_TZ = ZoneInfo("Asia/Kolkata")

# CPCB's own AQI categories -- same bands India's National AQI uses,
# which is also what the dominant-pollutant sub-index values from
# fetch_aqi.py are already expressed on.
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


def list_stations(city: str):
    """Every distinct station name stored for this city, in a stable order."""
    if not os.path.exists(DB_PATH):
        return []
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT DISTINCT station FROM readings WHERE city = ? ORDER BY station",
        (city,),
    ).fetchall()
    conn.close()
    return [r[0] for r in rows]


def load_readings(city: str, station: str):
    """Every raw intraday sample for this specific station, oldest first."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT fetched_at, aqi, dominant_pollutant
        FROM readings
        WHERE city = ? AND station = ?
        ORDER BY fetched_at ASC
        """,
        (city, station),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def group_into_daily_averages(readings):
    """Collapse raw intraday samples into one average-AQI-per-day series.

    Returns two parallel lists, oldest day first (dates, daily
    averages), plus a dict mapping date -> sample count, so the
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
    """Trailing rolling average; averages over whatever's available for
    the first `window - 1` points rather than leaving gaps."""
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
    """Is today's daily average a statistical outlier vs. this station's
    own recent history? z-score against the last 14 daily averages."""
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


def build_station_summary(city: str, station: str):
    readings = load_readings(city, station)
    if not readings:
        return None

    dates, daily_avg, sample_counts = group_into_daily_averages(readings)
    if not dates:
        return None

    rolling = rolling_average(daily_avg, window=7)
    wow_change = week_over_week(daily_avg)
    z, is_anomaly = anomaly_flag(daily_avg)

    latest_date = dates[-1]
    latest_avg = daily_avg[-1]
    samples_today = sample_counts[latest_date]
    label, color = band_for(latest_avg)

    latest_reading = readings[-1]
    latest_instant_aqi = latest_reading["aqi"]
    latest_dominant = latest_reading["dominant_pollutant"]
    instant_label, instant_color = band_for(latest_instant_aqi)
    instant_local_dt = datetime.fromisoformat(latest_reading["fetched_at"]).astimezone(LOCAL_TZ)
    # Built manually rather than with "%-I" -- that strips the leading
    # zero on Linux/Mac but isn't supported by Windows' strftime, and
    # this needs to run on both.
    hour_12 = instant_local_dt.hour % 12 or 12
    am_pm = "AM" if instant_local_dt.hour < 12 else "PM"
    latest_instant_time = f"{hour_12}:{instant_local_dt.minute:02d} {am_pm}"

    today_local = datetime.now(timezone.utc).astimezone(LOCAL_TZ).date().isoformat()
    is_partial_day = latest_date == today_local

    day_phrase = "so far today" if is_partial_day else f"on {latest_date}"
    lines = [f"Average AQI at {station} {day_phrase} is {latest_avg} "
             f"({label}), based on {samples_today} reading"
             f"{'s' if samples_today != 1 else ''}. "
             f"The most recent reading, at {latest_instant_time}, was "
             f"{latest_instant_aqi} ({instant_label}), driven mainly by "
             f"{latest_dominant}."]
    if wow_change is not None:
        direction = "worse" if wow_change > 0 else "better"
        lines.append(f"That's {abs(wow_change)}% {direction} than last week.")
    if is_anomaly:
        direction = "higher" if z > 0 else "lower"
        lines.append(f"This is unusually {direction} than the recent norm "
                      f"(z={z}) — worth a closer look.")

    return {
        "station": station,
        "latest_instant_aqi": latest_instant_aqi,
        "latest_instant_band": instant_label,
        "latest_instant_color": instant_color,
        "latest_instant_time": latest_instant_time,
        "latest_dominant_pollutant": latest_dominant,
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


def label_correlation(r: float) -> str:
    """Turn a Pearson correlation coefficient into a plain-English phrase.

    Thresholds (0.7 / 0.4 / 0.2) are the commonly used rough bands for
    "strong / moderate / weak" correlation strength -- not a precise
    statistical standard, just a reasonable convention for a summary
    sentence.
    """
    abs_r = abs(r)
    if abs_r < 0.2:
        return "not meaningfully correlated"
    strength = "strongly" if abs_r >= 0.7 else "moderately" if abs_r >= 0.4 else "weakly"
    direction = "correlated" if r >= 0 else "inversely correlated"
    return f"{strength} {direction}"


def compare_stations(station_summaries: dict) -> list:
    """For every pair of stations, compute how closely their daily
    averages track each other, and how far apart their most recent
    readings currently are.

    Correlation is computed only over dates BOTH stations actually
    have data for (their intersection) -- comparing on days where one
    station is missing would silently misalign the two series.
    Needs at least 3 overlapping days; below that a correlation
    coefficient is too noisy to mean anything, so it's left as None
    rather than reported with false confidence.
    """
    names = list(station_summaries.keys())
    comparisons = []

    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            name_a, name_b = names[i], names[j]
            a, b = station_summaries[name_a], station_summaries[name_b]

            a_by_date = dict(zip(a["dates"], a["daily_avg_aqi"]))
            b_by_date = dict(zip(b["dates"], b["daily_avg_aqi"]))
            shared_dates = sorted(set(a_by_date) & set(b_by_date))

            correlation = None
            correlation_label = None
            a_series = [a_by_date[d] for d in shared_dates]
            b_series = [b_by_date[d] for d in shared_dates]

            if len(shared_dates) >= 3:
                try:
                    correlation = round(statistics.correlation(a_series, b_series), 2)
                    correlation_label = label_correlation(correlation)
                except statistics.StatisticsError:
                    # Happens if one series has zero variance (every
                    # value identical) -- correlation is undefined,
                    # not zero, so leave it as None rather than guess.
                    pass

            current_diff = round(abs(a["latest_instant_aqi"] - b["latest_instant_aqi"]), 1)
            if a["latest_instant_aqi"] > b["latest_instant_aqi"]:
                currently_worse = name_a
            elif b["latest_instant_aqi"] > a["latest_instant_aqi"]:
                currently_worse = name_b
            else:
                currently_worse = None

            # Beyond the single current-moment snapshot above, look at
            # the whole shared history: each station's own average
            # over those days, and which one tends to run cleaner
            # overall rather than just right now.
            station_a_mean = round(statistics.mean(a_series), 1) if a_series else None
            station_b_mean = round(statistics.mean(b_series), 1) if b_series else None
            avg_gap_history = None
            generally_cleaner = None
            if station_a_mean is not None and station_b_mean is not None:
                avg_gap_history = round(abs(station_a_mean - station_b_mean), 1)
                if station_a_mean < station_b_mean:
                    generally_cleaner = name_a
                elif station_b_mean < station_a_mean:
                    generally_cleaner = name_b

            comparisons.append({
                "station_a": name_a,
                "station_b": name_b,
                "shared_dates": shared_dates,
                "station_a_daily": a_series,
                "station_b_daily": b_series,
                "station_a_mean": station_a_mean,
                "station_b_mean": station_b_mean,
                "avg_gap_history": avg_gap_history,
                "generally_cleaner": generally_cleaner,
                "correlation": correlation,
                "correlation_label": correlation_label,
                "current_diff": current_diff,
                "currently_worse": currently_worse,
            })

    return comparisons


def build_summary(city: str):
    stations = list_stations(city)
    if not stations:
        return {"city": city, "has_data": False}

    station_summaries = {}
    for station in stations:
        summary = build_station_summary(city, station)
        if summary is not None:
            station_summaries[station] = summary

    if not station_summaries:
        return {"city": city, "has_data": False}

    comparisons = compare_stations(station_summaries) if len(station_summaries) >= 2 else []

    return {
        "city": city,
        "has_data": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "stations": station_summaries,
        "comparisons": comparisons,
    }


def main():
    city = os.environ.get("CITY", "Bareilly")
    summary = build_summary(city)
    os.makedirs(os.path.dirname(SUMMARY_PATH), exist_ok=True)
    with open(SUMMARY_PATH, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"Wrote summary to {SUMMARY_PATH}")
    if summary.get("has_data"):
        for station, s in summary["stations"].items():
            print(f"\n{station}:")
            print(f"  {s['summary_text']}")


if __name__ == "__main__":
    main()
