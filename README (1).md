# AQI Tracker

I got tired of not knowing whether it's actually a good idea to be outside on a given day, so I built this to check for me. It pulls air quality data for Bareilly automatically, keeps a running history, and flags when a day is unusually bad — all without me touching it.

**Live:** https://itsvedu-1230.github.io/aqi-tracker/

## What it does

Every 3 hours, a GitHub Actions job wakes up, hits the WAQI (World Air Quality Index) API, and saves the reading. Once a day's worth of samples are in, `analyze.py` averages them into a single daily number instead of trusting one snapshot — I noticed early on that a single 8am reading swings around a lot depending on morning traffic, so averaging across the day gives a much more honest picture.

From there it computes a 7-day rolling average, compares this week to last week, and flags anything that looks statistically off compared to the last two weeks (z-score, not just some day I picked). Then it rebuilds a static dashboard and pushes it back to the repo.

```
WAQI API -> fetch_aqi.py -> aqi.db (SQLite) -> analyze.py -> summary.json -> generate_dashboard.py -> docs/index.html
```

## Why I built it this way

**SQLite, not a CSV.** I only need one thing writing to it and I wanted to actually query the data (filter by date, etc.) instead of parsing a flat file by hand every time.

**Static HTML, no backend.** The dashboard only needs to update every few hours, so running an actual server felt like overkill. A plain HTML file hosted on GitHub Pages costs nothing and there's nothing to keep alive.

**z-score over a fixed AQI threshold.** My first instinct was "flag anything over 300," but that's not fair across seasons — Bareilly in November is just going to be worse than June regardless of anything unusual happening. Comparing today to the city's own recent 14-day average instead of a fixed number felt like the more honest approach.

**Averaging samples instead of trusting one reading.** This was the most recent change. Originally it just grabbed one reading a day at 8am and called that "today's AQI," but that's really just one moment, not the day. Now it fetches every 3 hours and averages what it's collected — a lot more representative, and one weird spike doesn't wreck the whole day's number anymore.

## Setup

If you want to run your own copy:

1. Get a free token from https://aqicn.org/data-platform/token/
2. Find your city's slug at https://aqicn.org/city/all/
3. Locally: `AQI_TOKEN=your_token CITY=yourcity python3 fetch_aqi.py`, then `analyze.py`, then `generate_dashboard.py`
4. Push to GitHub, add `AQI_TOKEN` as a repo secret and `CITY` as a repo variable, turn on Pages (source: `/docs` folder)

The workflow in `.github/workflows/update.yml` handles the rest — it runs every 3 hours and commits the updated data and dashboard back automatically.

## Known limitations

- If the API call fails on a given cycle, that sample is just missing — no retry yet. On my list, just haven't gotten to it.
- Only tracks one city right now, though the database schema already has a `city` column so adding more shouldn't take much.
- No alerting anywhere — you have to actually open the dashboard to see if something's flagged as unusual. An email or Telegram ping when a day looks bad would be the obvious next step.
- The 7-day / 14-day windows for the rolling average and anomaly detection are reasonable starting points, not something I've rigorously tuned against real seasonal data yet.

## Stack

Python (standard library only — sqlite3, urllib, json, statistics), SQLite, GitHub Actions for scheduling, GitHub Pages for hosting, Chart.js for the chart.
