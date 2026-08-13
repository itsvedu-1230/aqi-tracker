# AQI Tracker

I got tired of not knowing whether it's actually a good idea to be outside on a given day, so I built this to check for me. It pulls air quality data for Bareilly automatically, keeps a running history, and flags when a day is unusually bad — all without me touching it.

**Live:** https://itsvedu-1230.github.io/aqi-tracker/

## What it does

Every 3 hours, a GitHub Actions job wakes up, hits CPCB's (India's Central Pollution Control Board) real-time API, and saves whatever it gets back — one row per monitoring station in the city. Bareilly currently has two, Rajendra Nagar and Civil Lines, and they genuinely don't always agree, so the dashboard tracks and charts each one separately rather than blending them into a single number.

Once a day's worth of samples are in for a station, `analyze.py` averages them into a daily figure instead of trusting one snapshot — a single reading swings around a lot depending on the time of day. From there it computes a 7-day rolling average, compares this week to last week, and flags anything statistically off compared to that station's own last two weeks. Then it rebuilds a static dashboard and pushes it back to the repo.

```
CPCB API -> fetch_aqi.py -> aqi.db (SQLite) -> analyze.py -> summary.json -> generate_dashboard.py -> docs/index.html
```

## Why CPCB instead of WAQI

This project originally pulled from WAQI (World Air Quality Index), a third-party aggregator, not CPCB directly. It worked fine at first, but I eventually noticed the AQI number had been stuck at exactly 63 for three straight days — which isn't physically plausible. Digging into the raw API response, the station's own `station_time` field hadn't moved in almost two months. The sensor was dead, and WAQI was just re-serving its last cached reading every time I asked, without ever returning an error.

Switching to CPCB's own API goes straight to the actual government source WAQI itself pulls from, cutting out that caching layer. It also turned out CPCB has two stations for Bareilly, not one, so rather than arbitrarily picking a single one I decided to track both.

## Why I built it this way

**SQLite, not a CSV.** I only need one thing writing to it and wanted to actually query the data instead of parsing a flat file by hand.

**Static HTML, no backend.** The dashboard only needs to update every few hours, so a real server felt like overkill. A plain HTML file hosted on GitHub Pages costs nothing and there's nothing to keep alive.

**Two stations shown independently, not averaged together.** Averaging Rajendra Nagar and Civil Lines into one number would hide real, meaningful variation — I've seen them differ by over 200 AQI points on the same day, once driven by an ozone spike at only one of the two. Showing both keeps the dashboard honest about what it actually knows.

**No breakpoint formula needed.** I initially assumed I'd have to implement CPCB's AQI calculation from raw pollutant concentrations myself. Turns out the API already returns each pollutant as a 0–500 AQI sub-index, not a raw concentration — so a station's overall AQI is just the max sub-index across its pollutants, which is CPCB's own official rule anyway.

**z-score over a fixed AQI threshold.** A fixed "flag anything over 300" rule isn't fair across seasons. Comparing today to a station's own recent 14-day average adapts itself instead.

## Setup

If you want to run your own copy:

1. Register at https://data.gov.in and get a free API key from your account page
2. Confirm your city has live data: `https://api.data.gov.in/resource/3b01bcb8-0b14-4abf-b6f2-c1bfd384ba69?api-key=YOUR_KEY&format=json&filters[city]=YourCity&limit=50`
3. Locally: `CPCB_API_KEY=your_key CITY=YourCity python3 fetch_aqi.py`, then `analyze.py`, then `generate_dashboard.py`
4. Push to GitHub, add `CPCB_API_KEY` as a repo secret and `CITY` as a repo variable, turn on Pages (source: `/docs` folder)

The workflow in `.github/workflows/update.yml` handles the rest — runs every 3 hours and commits the updated data and dashboard back automatically.

## Known limitations

- If a fetch fails, that cycle's sample is just missing — no retry yet.
- Government sensor feeds like CPCB's are known to have gaps or lag occasionally; there's no automatic staleness detection yet (the WAQI incident was caught manually, by noticing a suspiciously flat number).
- No alerting anywhere — you have to open the dashboard to see if something's flagged.
- The 7-day / 14-day windows for the rolling average and anomaly detection are reasonable defaults, not rigorously tuned against real seasonal data.

## Stack

Python (standard library only — sqlite3, urllib, json, statistics), SQLite, GitHub Actions for scheduling, GitHub Pages for hosting, Chart.js for the charts, CPCB's real-time API (via data.gov.in) for data.
