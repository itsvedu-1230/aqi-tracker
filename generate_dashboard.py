"""
generate_dashboard.py
----------------------
Reads data/summary.json (produced by analyze.py) and writes a single,
self-contained static HTML file to docs/index.html.

Layout, top to bottom:
  1. Header + a "live" indicator badge
  2. Station Comparison section -- an overlaid chart of both stations'
     daily averages on the same axes, plus a correlation coefficient
     and current gap between them. This only renders when there's
     more than one station AND enough overlapping days to compute a
     correlation; with just one station or too little shared history,
     it's skipped entirely rather than shown empty.
  3. A side-by-side grid of per-station panels (current reading,
     daily average, stats, individual chart) -- collapses to a single
     column automatically on narrow/mobile screens via CSS grid,
     nothing JS-driven.

Static and self-contained on purpose: no backend server, so it's free
to host on GitHub Pages and there's nothing that can go down except
GitHub itself.
"""

import os
import json
import re

SUMMARY_PATH = os.path.join(os.path.dirname(__file__), "data", "summary.json")
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "docs", "index.html")

# Stable per-station identity colors, used specifically in the
# comparison chart where two lines need to stay visually distinct
# regardless of what AQI band either station is currently in (each
# station's own panel instead uses ITS OWN current-band color as the
# accent, which is intentionally a different color system).
STATION_IDENTITY_COLORS = ["#4E9A85", "#D9A441", "#6C8EBF", "#C0432E", "#8FA85E"]


def render_no_data_page(city: str) -> str:
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{city} Air Quality</title></head>
<body style="font-family: sans-serif; background:#1B2226; color:#EDE6D8; padding:4rem; text-align:center;">
<h1>No data yet</h1>
<p>Run fetch_aqi.py at least once, then analyze.py, then this script again.</p>
</body></html>"""


def slugify(text: str) -> str:
    """Turn a station name into something safe for an HTML id / Chart.js
    canvas id, e.g. 'Civil Lines, Bareilly - UPPCB' -> 'civil-lines-bareilly-uppcb'."""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def short_name(station_name: str) -> str:
    """'Rajendra Nagar, Bareilly - UPPCB' -> 'Rajendra Nagar' -- the
    city/agency suffix is redundant once it's already the page title,
    and repeating it in every card label just adds noise."""
    return station_name.split(",")[0].strip()


def render_station_panel(station_name: str, s: dict, identity_color: str) -> tuple:
    """Returns (html, chart_js) for one station's panel in the grid."""
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
        <div class="anomaly-badge">Unusual reading today</div>"""

    html = f"""
    <div class="station-panel">
      <div class="station-panel-header">
        <span class="station-dot" style="background:{identity_color}"></span>
        <h2 class="station-name">{short_name(station_name)}</h2>
      </div>

      <div class="hero">
        <div class="hero-label">{hero_label}</div>
        <div class="hero-top">
          <div class="aqi-number" style="color:{color}">{latest_avg}</div>
          <div class="aqi-band" style="color:{color}">{band}</div>
        </div>
        <div class="current-reading">
          <div class="current-reading-number" style="color:{instant_color}">{instant_aqi}</div>
          <div class="current-reading-meta">
            <div class="current-reading-label">Current &middot; {instant_band}</div>
            <div class="current-reading-time">{instant_time} IST &middot; {dominant}</div>
          </div>
        </div>
        <div class="samples-note">Based on {samples_today} reading{'s' if samples_today != 1 else ''} {'so far today' if is_partial_day else 'that day'}</div>
        <div class="visibility-bar"><div class="visibility-marker" style="left:{marker_pct}%"></div></div>
        {anomaly_html}
      </div>

      <div class="stats-row">
        {wow_html}
        <div class="stat-card">
          <div class="stat-label">Days tracked</div>
          <div class="stat-value">{len(s["daily_avg_aqi"])}</div>
        </div>
      </div>

      <div class="chart-card">
        <div class="chart-title">Daily average (7-day rolling average overlaid)</div>
        <canvas id="chart-{slug}" height="100"></canvas>
      </div>

      <div class="summary-text-block">{summary_text}</div>
    </div>
"""

    chart_js = f"""
      new Chart(document.getElementById('chart-{slug}').getContext('2d'), {{
        type: 'line',
        data: {{
          labels: {dates_json}.map(d => d.slice(5, 10)),
          datasets: [
            {{ label: 'Daily average', data: {aqi_json}, borderColor: '#8B9498',
               backgroundColor: 'transparent', pointRadius: 0, borderWidth: 1, tension: 0.2 }},
            {{ label: '7-day average', data: {rolling_json}, borderColor: '{identity_color}',
               backgroundColor: 'transparent', pointRadius: 0, borderWidth: 2.5, tension: 0.3 }},
          ]
        }},
        options: {{
          responsive: true,
          plugins: {{ legend: {{ labels: {{ color: '#8B9498', font: {{ family: 'IBM Plex Mono', size: 10 }} }} }} }},
          scales: {{
            x: {{ ticks: {{ color: '#8B9498', font: {{ size: 10 }} }}, grid: {{ color: 'rgba(255,255,255,0.04)' }} }},
            y: {{ ticks: {{ color: '#8B9498', font: {{ size: 10 }} }}, grid: {{ color: 'rgba(255,255,255,0.06)' }} }}
          }}
        }}
      }});
"""
    return html, chart_js


def render_comparison_section(comparisons: list, colors_by_station: dict) -> tuple:
    """Returns (html, chart_js) for the cross-station comparison card(s).
    Empty strings if there's nothing worth showing (e.g. correlation
    couldn't be computed due to too little shared history)."""
    if not comparisons:
        return "", ""

    cards_html = []
    all_chart_js = []

    for idx, c in enumerate(comparisons):
        a_short, b_short = short_name(c["station_a"]), short_name(c["station_b"])
        color_a = colors_by_station[c["station_a"]]
        color_b = colors_by_station[c["station_b"]]
        chart_id = f"comparison-chart-{idx}"

        if c["correlation"] is None:
            correlation_html = (f'<div class="stat-sub">Not enough overlapping days yet '
                                 f'({len(c["shared_dates"])} so far, need 3+) to compute a '
                                 f'correlation.</div>')
        else:
            correlation_html = (f'<div class="stat-value">{c["correlation"]}</div>'
                                 f'<div class="stat-sub">{c["correlation_label"]} '
                                 f'&middot; {len(c["shared_dates"])} shared days</div>')

        worse_html = ""
        if c["currently_worse"]:
            worse_html = f"""
            <div class="stat-card">
              <div class="stat-label">Currently worse</div>
              <div class="stat-value" style="font-size:1.1rem;">{short_name(c["currently_worse"])}</div>
              <div class="stat-sub">by {c["current_diff"]} AQI points right now</div>
            </div>"""

        cleaner_html = ""
        if c["generally_cleaner"] and c["avg_gap_history"] is not None:
            cleaner_html = f"""
            <div class="stat-card">
              <div class="stat-label">Generally cleaner</div>
              <div class="stat-value" style="font-size:1.1rem;">{short_name(c["generally_cleaner"])}</div>
              <div class="stat-sub">by {c["avg_gap_history"]} AQI avg, over {len(c["shared_dates"])} shared days</div>
            </div>"""

        station_avg_html = ""
        if c["station_a_mean"] is not None and c["station_b_mean"] is not None:
            station_avg_html = f"""
            <div class="stat-card">
              <div class="stat-label">{short_name(c["station_a"])} avg</div>
              <div class="stat-value">{c["station_a_mean"]}</div>
              <div class="stat-sub">over shared history</div>
            </div>
            <div class="stat-card">
              <div class="stat-label">{short_name(c["station_b"])} avg</div>
              <div class="stat-value">{c["station_b_mean"]}</div>
              <div class="stat-sub">over shared history</div>
            </div>"""

        chart_html = ""
        if c["shared_dates"]:
            chart_html = f"""
            <div class="chart-card">
              <div class="chart-title">Daily average AQI, both stations overlaid</div>
              <canvas id="{chart_id}" height="100"></canvas>
            </div>"""

            dates_json = json.dumps(c["shared_dates"])
            a_json = json.dumps(c["station_a_daily"])
            b_json = json.dumps(c["station_b_daily"])
            all_chart_js.append(f"""
      new Chart(document.getElementById('{chart_id}').getContext('2d'), {{
        type: 'line',
        data: {{
          labels: {dates_json}.map(d => d.slice(5, 10)),
          datasets: [
            {{ label: '{a_short}', data: {a_json}, borderColor: '{color_a}',
               backgroundColor: 'transparent', pointRadius: 2, borderWidth: 2, tension: 0.25 }},
            {{ label: '{b_short}', data: {b_json}, borderColor: '{color_b}',
               backgroundColor: 'transparent', pointRadius: 2, borderWidth: 2, tension: 0.25 }},
          ]
        }},
        options: {{
          responsive: true,
          plugins: {{ legend: {{ labels: {{ color: '#8B9498', font: {{ family: 'IBM Plex Mono', size: 11 }} }} }} }},
          scales: {{
            x: {{ ticks: {{ color: '#8B9498' }}, grid: {{ color: 'rgba(255,255,255,0.04)' }} }},
            y: {{ ticks: {{ color: '#8B9498' }}, grid: {{ color: 'rgba(255,255,255,0.06)' }} }}
          }}
        }}
      }});
""")

        cards_html.append(f"""
    <div class="comparison-card">
      <div class="comparison-pair-label">{a_short} &nbsp;vs&nbsp; {b_short}</div>
      <div class="stats-row">
        <div class="stat-card">
          <div class="stat-label">Correlation</div>
          {correlation_html}
        </div>
        {station_avg_html}
        {worse_html}
        {cleaner_html}
      </div>
      {chart_html}
    </div>""")

    section_html = f"""
  <section class="comparison-section">
    <h2 class="section-heading">Station Comparison</h2>
    <p class="section-subtext">How closely the two stations track each other, and where they currently disagree.</p>
    {"".join(cards_html)}
  </section>
"""
    return section_html, "".join(all_chart_js)


def render_dashboard(summary: dict) -> str:
    city = summary["city"].title()
    generated_at = summary["generated_at"]
    stations = summary["stations"]
    comparisons = summary.get("comparisons", [])

    colors_by_station = {
        name: STATION_IDENTITY_COLORS[i % len(STATION_IDENTITY_COLORS)]
        for i, name in enumerate(stations.keys())
    }

    panel_html_parts = []
    all_chart_js = []

    for name, s in stations.items():
        html, js = render_station_panel(name, s, colors_by_station[name])
        panel_html_parts.append(html)
        all_chart_js.append(js)

    comparison_html, comparison_js = render_comparison_section(comparisons, colors_by_station)
    all_chart_js.append(comparison_js)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{city} Air Quality Tracker</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=IBM+Plex+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
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
    padding: 0 1.25rem 4rem;
  }}
  .top-accent {{
    height: 4px;
    background: linear-gradient(90deg, #3E7C6F 0%, #8FA85E 20%, #D9A441 45%, #D9722C 65%, #C0432E 85%, #7A2E3A 100%);
  }}
  .wrap {{ max-width: 1080px; margin: 0 auto; padding-top: 2.25rem; }}
  .header-row {{ display: flex; align-items: flex-start; justify-content: space-between; flex-wrap: wrap; gap: 1rem; margin-bottom: 0.5rem; }}
  .eyebrow-row {{ display: flex; align-items: center; gap: 0.5rem; }}
  .eyebrow {{
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.8rem;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--text-muted);
  }}
  .live-badge {{
    display: inline-flex; align-items: center; gap: 0.4rem;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.7rem;
    color: #8FA85E;
    background: rgba(143,168,94,0.12);
    border: 1px solid rgba(143,168,94,0.3);
    padding: 0.25rem 0.6rem;
    border-radius: 999px;
  }}
  .live-dot {{
    width: 6px; height: 6px; border-radius: 50%;
    background: #8FA85E;
    animation: pulse 2s infinite;
  }}
  @keyframes pulse {{
    0%, 100% {{ opacity: 1; }}
    50% {{ opacity: 0.35; }}
  }}
  h1 {{
    font-size: clamp(1.8rem, 4vw, 2.6rem);
    font-weight: 800;
    margin: 0.3rem 0 0.4rem;
    letter-spacing: -0.02em;
  }}
  .station-count-note {{
    color: var(--text-muted);
    font-size: 0.9rem;
    margin-bottom: 2.25rem;
  }}
  .section-heading {{
    font-size: 1.15rem;
    font-weight: 700;
    margin: 0 0 0.3rem;
  }}
  .section-subtext {{
    color: var(--text-muted);
    font-size: 0.88rem;
    margin: 0 0 1.25rem;
  }}
  .comparison-section {{ margin-top: 2.75rem; margin-bottom: 2.75rem; }}
  .comparison-card {{
    background: var(--surface);
    border-radius: 18px;
    padding: 1.75rem;
    border: 1px solid rgba(255,255,255,0.06);
    margin-bottom: 1rem;
  }}
  .comparison-pair-label {{
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.85rem;
    color: var(--text-muted);
    margin-bottom: 1rem;
  }}
  .stations-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(380px, 1fr));
    gap: 1.5rem;
  }}
  .station-panel {{
    background: var(--surface);
    border-radius: 18px;
    padding: 1.5rem;
    border: 1px solid rgba(255,255,255,0.06);
    transition: box-shadow 0.2s ease, border-color 0.2s ease;
  }}
  .station-panel:hover {{
    box-shadow: 0 8px 28px rgba(0,0,0,0.28);
    border-color: rgba(255,255,255,0.12);
  }}
  .station-panel-header {{ display: flex; align-items: center; gap: 0.55rem; margin-bottom: 1rem; }}
  .station-dot {{ width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }}
  .station-name {{ font-size: 1.05rem; font-weight: 700; margin: 0; }}
  .hero {{
    background: var(--surface-2);
    border-radius: 14px;
    padding: 1.5rem;
    margin-bottom: 1.1rem;
  }}
  .hero-label {{
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.7rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--text-muted);
    margin-bottom: 0.5rem;
  }}
  .hero-top {{ display: flex; align-items: baseline; gap: 0.85rem; flex-wrap: wrap; margin-bottom: 0.9rem; }}
  .aqi-number {{
    font-family: 'IBM Plex Mono', monospace;
    font-size: 3.4rem;
    font-weight: 700;
    line-height: 1;
  }}
  .aqi-band {{ font-size: 1.05rem; font-weight: 600; }}
  .current-reading {{
    display: flex;
    align-items: baseline;
    gap: 0.55rem;
    padding: 0.7rem 0.9rem;
    background: rgba(0,0,0,0.18);
    border-radius: 10px;
  }}
  .current-reading-number {{
    font-family: 'IBM Plex Mono', monospace;
    font-size: 1.4rem;
    font-weight: 700;
  }}
  .current-reading-meta {{ display: flex; flex-direction: column; gap: 0.05rem; }}
  .current-reading-label {{
    font-size: 0.68rem; letter-spacing: 0.05em; text-transform: uppercase;
    color: var(--text-muted);
  }}
  .current-reading-time {{
    font-size: 0.72rem; color: var(--text-muted);
    font-family: 'IBM Plex Mono', monospace;
  }}
  .samples-note {{ font-size: 0.76rem; color: var(--text-muted); margin-top: 0.7rem; }}
  .visibility-bar {{
    position: relative;
    margin-top: 1rem;
    height: 10px;
    border-radius: 999px;
    background: linear-gradient(90deg,
      #3E7C6F 0%, #8FA85E 16%, #D9A441 33%, #D9722C 50%, #C0432E 75%, #7A2E3A 100%);
  }}
  .visibility-marker {{
    position: absolute;
    top: -5px;
    width: 3px;
    height: 20px;
    background: var(--text);
    transform: translateX(-50%);
    box-shadow: 0 0 6px rgba(237,230,216,0.6);
  }}
  .anomaly-badge {{
    margin-top: 1rem;
    display: inline-block;
    background: rgba(192,67,46,0.15);
    color: #E08A78;
    border: 1px solid rgba(192,67,46,0.4);
    padding: 0.3rem 0.65rem;
    border-radius: 8px;
    font-size: 0.76rem;
  }}
  .stats-row {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 0.75rem; margin-bottom: 1.1rem; }}
  .stat-card {{
    background: var(--surface-2);
    border-radius: 12px;
    padding: 0.9rem 1rem;
  }}
  .stat-label {{ font-size: 0.72rem; color: var(--text-muted); margin-bottom: 0.3rem; }}
  .stat-value {{ font-family: 'IBM Plex Mono', monospace; font-size: 1.3rem; font-weight: 700; }}
  .stat-sub {{ font-size: 0.72rem; color: var(--text-muted); margin-top: 0.15rem; }}
  .chart-card {{
    background: var(--surface-2);
    border-radius: 14px;
    padding: 1.1rem;
    margin-bottom: 0.9rem;
  }}
  .chart-title {{ font-size: 0.78rem; color: var(--text-muted); margin-bottom: 0.75rem; }}
  .summary-text-block {{ color: var(--text-muted); font-size: 0.85rem; line-height: 1.5; }}
  footer {{
    margin-top: 1.5rem;
    padding-top: 1.5rem;
    border-top: 1px solid rgba(255,255,255,0.06);
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.75rem;
    color: var(--text-muted);
    text-align: center;
  }}
  footer .made-with {{ margin-top: 0.4rem; opacity: 0.7; }}
</style>
</head>
<body>
<div class="top-accent"></div>
<div class="wrap">
  <div class="header-row">
    <div>
      <div class="eyebrow-row">
        <span class="eyebrow">Personal air quality tracker</span>
      </div>
      <h1>{city} Air Quality</h1>
    </div>
    <div class="live-badge"><span class="live-dot"></span>Auto-updates every 3 hours</div>
  </div>
  <div class="station-count-note">Tracking {len(stations)} CPCB monitoring station{'s' if len(stations) != 1 else ''} independently{' — each has its own sensor and can read differently.' if len(stations) > 1 else '.'}</div>

  <section>
    <h2 class="section-heading">By Station</h2>
    <p class="section-subtext">Each station's own current reading, daily average, and trend.</p>
    <div class="stations-grid">
      {"".join(panel_html_parts)}
    </div>
  </section>

  {comparison_html}

  <footer>
    Source: CPCB (Central Pollution Control Board), via data.gov.in &middot; Last updated {generated_at} UTC
    <div class="made-with">Built with Python, GitHub Actions &amp; Chart.js</div>
  </footer>
</div>

<script>
{"".join(all_chart_js)}
</script>
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
