"""
generate_dashboard.py
----------------------
Reads data/summary.json (produced by analyze.py) and writes a single,
self-contained static HTML file to docs/index.html -- one full section
per monitoring station in the city, stacked on the same page, since
Bareilly's two CPCB stations (Rajendra Nagar, Civil Lines) can and do
show meaningfully different numbers, and picking just one would hide
that real variation.

Static and self-contained on purpose: no backend server, so it's free
to host on GitHub Pages and there's nothing that can go down except
GitHub itself.
"""

import os
import json
import re

SUMMARY_PATH = os.path.join(os.path.dirname(__file__), "data", "summary.json")
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "docs", "index.html")


def render_no_data_page(city: str) -> str:
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{city} Air Quality</title></head>
<body style="font-family: sans-serif; background:#1B2226; color:#EDE6D8; padding:4rem; text-align:center;">
<h1>No data yet</h1>
<p>Run fetch_aqi.py at least once, then analyze.py, then this script again.</p>
</body></html>"""


def slugify(text: str) -> str:
    """Turn a station name into something safe to use as an HTML id /
    Chart.js canvas id, e.g. 'Civil Lines, Bareilly - UPPCB' -> 'civil-lines-bareilly-uppcb'."""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def render_station_section(station_name: str, s: dict) -> str:
    slug = slugify(station_name)
    dates_json = json.dumps(s["dates"])
    aqi_json = json.dumps(s["daily_avg_aqi"])
    rolling_json = json.dumps(s["rolling_7d"])

    latest_avg = s["latest_avg_aqi"]
    band = s["latest_band"]
    color = s["latest_color"]
    wow = s["week_over_week_pct"]
    summary_text = s["summary_text"]
    is_anomaly = s["is_anomaly"]
    samples_today = s["samples_today"]
    is_partial_day = s["is_partial_day"]
    instant_aqi = s["latest_instant_aqi"]
    instant_band = s["latest_instant_band"]
    instant_color = s["latest_instant_color"]
    instant_time = s["latest_instant_time"]
    dominant = s["latest_dominant_pollutant"]

    marker_pct = max(0, min(100, (latest_avg / 400) * 100))
    hero_label = "Today's average (so far)" if is_partial_day else "Latest daily average"

    wow_html = ""
    if wow is not None:
        direction_word = "worse" if wow > 0 else "better"
        arrow = "&#8593;" if wow > 0 else "&#8595;"
        wow_html = f"""
        <div class="stat-card">
          <div class="stat-label">Week over week</div>
          <div class="stat-value">{arrow} {abs(wow)}%</div>
          <div class="stat-sub">{direction_word} than last week</div>
        </div>"""

    anomaly_html = ""
    if is_anomaly:
        anomaly_html = """
        <div class="anomaly-badge">Unusual reading today — outside the recent normal range</div>"""

    return f"""
  <section class="station-section">
    <h2 class="station-name">{station_name}</h2>

    <div class="hero">
      <div class="hero-label">{hero_label}</div>
      <div class="hero-top">
        <div class="aqi-number">{latest_avg}</div>
        <div class="aqi-band">{band}</div>
        <div class="current-reading">
          <div class="current-reading-number" style="color:{instant_color}">{instant_aqi}</div>
          <div class="current-reading-meta">
            <div class="current-reading-label">Current &middot; {instant_band}</div>
            <div class="current-reading-time">as of {instant_time} IST &middot; {dominant} dominant</div>
          </div>
        </div>
      </div>
      <div class="samples-note">Based on {samples_today} reading{'s' if samples_today != 1 else ''} {'so far today' if is_partial_day else 'that day'}</div>
      <div class="summary-text">{summary_text}</div>
      <div class="visibility-bar"><div class="visibility-marker" style="left:{marker_pct}%"></div></div>
      <div class="visibility-labels"><span>Good</span><span>Moderate</span><span>Poor</span><span>Severe</span></div>
      {anomaly_html}
    </div>

    <div class="stats-row">
      <div class="stat-card">
        <div class="stat-label">Current AQI band</div>
        <div class="stat-value" style="color:{color}">{band}</div>
      </div>
      {wow_html}
      <div class="stat-card">
        <div class="stat-label">Days tracked</div>
        <div class="stat-value">{len(s["daily_avg_aqi"])}</div>
        <div class="stat-sub">days of history</div>
      </div>
    </div>

    <div class="chart-card">
      <div class="chart-title">Daily average AQI over time (with 7-day rolling average)</div>
      <canvas id="chart-{slug}" height="110"></canvas>
    </div>
  </section>

  <script>
    (function() {{
      const ctx = document.getElementById('chart-{slug}').getContext('2d');
      new Chart(ctx, {{
        type: 'line',
        data: {{
          labels: {dates_json}.map(d => d.slice(5, 10)),
          datasets: [
            {{
              label: 'Daily average AQI',
              data: {aqi_json},
              borderColor: '#8B9498',
              backgroundColor: 'transparent',
              pointRadius: 0,
              borderWidth: 1,
              tension: 0.2,
            }},
            {{
              label: '7-day average',
              data: {rolling_json},
              borderColor: '{color}',
              backgroundColor: 'transparent',
              pointRadius: 0,
              borderWidth: 2.5,
              tension: 0.3,
            }},
          ]
        }},
        options: {{
          responsive: true,
          plugins: {{
            legend: {{ labels: {{ color: '#8B9498', font: {{ family: 'IBM Plex Mono' }} }} }}
          }},
          scales: {{
            x: {{ ticks: {{ color: '#8B9498' }}, grid: {{ color: 'rgba(255,255,255,0.04)' }} }},
            y: {{ ticks: {{ color: '#8B9498' }}, grid: {{ color: 'rgba(255,255,255,0.06)' }} }}
          }}
        }}
      }});
    }})();
  </script>
"""


def render_dashboard(summary: dict) -> str:
    city = summary["city"].title()
    generated_at = summary["generated_at"]
    stations = summary["stations"]

    station_sections = "\n".join(
        render_station_section(name, s) for name, s in stations.items()
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{city} Air Quality Tracker</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
  :root {{
    --bg: #1B2226;
    --surface: #232D33;
    --surface-2: #2B363D;
    --text: #EDE6D8;
    --text-muted: #8B9498;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    background: linear-gradient(180deg, #1B2226 0%, #20292E 100%);
    color: var(--text);
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    padding: 2.5rem 1.25rem 4rem;
  }}
  .wrap {{ max-width: 880px; margin: 0 auto; }}
  .eyebrow {{
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.8rem;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--text-muted);
    margin-bottom: 0.5rem;
  }}
  h1 {{
    font-size: clamp(1.8rem, 4vw, 2.6rem);
    font-weight: 800;
    margin: 0 0 1rem;
    letter-spacing: -0.02em;
  }}
  .station-count-note {{
    color: var(--text-muted);
    font-size: 0.9rem;
    margin-bottom: 2rem;
  }}
  .station-section {{ margin-bottom: 3rem; }}
  .station-name {{
    font-size: 1.1rem;
    font-weight: 700;
    color: var(--text);
    margin: 0 0 1rem;
    padding-bottom: 0.5rem;
    border-bottom: 1px solid rgba(255,255,255,0.08);
  }}
  .hero {{
    background: var(--surface);
    border-radius: 18px;
    padding: 2.25rem;
    margin-bottom: 1.5rem;
    border: 1px solid rgba(255,255,255,0.06);
  }}
  .hero-label {{
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.75rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--text-muted);
    margin-bottom: 0.6rem;
  }}
  .hero-top {{ display: flex; align-items: baseline; gap: 1rem; flex-wrap: wrap; }}
  .aqi-number {{
    font-family: 'IBM Plex Mono', monospace;
    font-size: 4.5rem;
    font-weight: 700;
    color: inherit;
    line-height: 1;
  }}
  .aqi-band {{
    font-size: 1.2rem;
    font-weight: 600;
  }}
  .current-reading {{
    display: flex;
    align-items: baseline;
    gap: 0.6rem;
    padding: 0.9rem 1.1rem;
    background: var(--surface-2);
    border-radius: 12px;
    margin-left: auto;
  }}
  .current-reading-number {{
    font-family: 'IBM Plex Mono', monospace;
    font-size: 1.8rem;
    font-weight: 700;
  }}
  .current-reading-meta {{ display: flex; flex-direction: column; gap: 0.1rem; }}
  .current-reading-label {{
    font-size: 0.7rem; letter-spacing: 0.06em; text-transform: uppercase;
    color: var(--text-muted);
  }}
  .current-reading-time {{
    font-size: 0.75rem; color: var(--text-muted);
    font-family: 'IBM Plex Mono', monospace;
  }}
  .samples-note {{ font-size: 0.8rem; color: var(--text-muted); margin-top: 0.75rem; }}
  .summary-text {{ color: var(--text-muted); margin-top: 0.4rem; font-size: 1rem; line-height: 1.5; }}
  .visibility-bar {{
    position: relative;
    margin-top: 1.75rem;
    height: 14px;
    border-radius: 999px;
    background: linear-gradient(90deg,
      #3E7C6F 0%, #8FA85E 16%, #D9A441 33%, #D9722C 50%, #C0432E 75%, #7A2E3A 100%);
  }}
  .visibility-marker {{
    position: absolute;
    top: -7px;
    width: 3px;
    height: 28px;
    background: var(--text);
    transform: translateX(-50%);
    box-shadow: 0 0 8px rgba(237,230,216,0.6);
  }}
  .visibility-labels {{
    display: flex; justify-content: space-between;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.7rem; color: var(--text-muted);
    margin-top: 0.5rem;
  }}
  .anomaly-badge {{
    margin-top: 1.25rem;
    display: inline-block;
    background: rgba(192,67,46,0.15);
    color: #E08A78;
    border: 1px solid rgba(192,67,46,0.4);
    padding: 0.4rem 0.8rem;
    border-radius: 8px;
    font-size: 0.85rem;
  }}
  .stats-row {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 1rem; margin-bottom: 1.5rem; }}
  .stat-card {{
    background: var(--surface);
    border-radius: 14px;
    padding: 1.25rem;
    border: 1px solid rgba(255,255,255,0.06);
  }}
  .stat-label {{ font-size: 0.8rem; color: var(--text-muted); margin-bottom: 0.4rem; }}
  .stat-value {{ font-family: 'IBM Plex Mono', monospace; font-size: 1.6rem; font-weight: 700; }}
  .stat-sub {{ font-size: 0.8rem; color: var(--text-muted); margin-top: 0.2rem; }}
  .chart-card {{
    background: var(--surface);
    border-radius: 18px;
    padding: 1.75rem;
    border: 1px solid rgba(255,255,255,0.06);
  }}
  .chart-title {{ font-size: 0.9rem; color: var(--text-muted); margin-bottom: 1rem; }}
  footer {{
    margin-top: 1rem;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.75rem;
    color: var(--text-muted);
    text-align: center;
  }}
</style>
</head>
<body>
<div class="wrap">
  <div class="eyebrow">Personal air quality tracker</div>
  <h1>{city} Air Quality</h1>
  <div class="station-count-note">Tracking {len(stations)} monitoring stations independently &mdash; each has its own sensor and can read differently.</div>

  {station_sections}

  <footer>
    Source: CPCB (Central Pollution Control Board), via data.gov.in &middot; Last updated {generated_at} UTC
  </footer>
</div>
</body>
</html>"""


def main():
    if not os.path.exists(SUMMARY_PATH):
        print("No summary.json found — run analyze.py first.")
        return

    with open(SUMMARY_PATH) as f:
        summary = json.load(f)

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)

    if not summary.get("has_data"):
        html = render_no_data_page(summary["city"])
    else:
        html = render_dashboard(summary)

    with open(OUTPUT_PATH, "w") as f:
        f.write(html)

    print(f"Dashboard written to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
