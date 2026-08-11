# AQI Tracker — Bareilly Air Quality Dashboard

A personal, fully automated air quality tracker. A script pulls the
day's AQI reading, stores it, computes trends, and rebuilds a static
dashboard — every day, on its own, via GitHub Actions.

**Live dashboard:** (add your GitHub Pages URL here once deployed)

## How it works

```
fetch_aqi.py            analyze.py              generate_dashboard.py
   |                        |                          |
   v                        v                          v
WAQI API  --->  data/aqi.db (SQLite)  --->  data/summary.json  --->  docs/index.html
```

1. `fetch_aqi.py` calls the WAQI API for one city and appends a row to `data/aqi.db`.
2. `analyze.py` reads the full history, computes a 7-day rolling average,
   week-over-week % change, and flags anomalies (z-score > 2), writing
   the result to `data/summary.json`.
3. `generate_dashboard.py` turns that JSON into a single static HTML
   file at `docs/index.html`, styled and charted with Chart.js.
4. A GitHub Actions workflow (`.github/workflows/update.yml`) runs all
   three every day at 08:00 IST and commits the results back to the repo.
5. GitHub Pages serves `docs/index.html` as a live website — free, no server.

## Setup from scratch

### 1. Get a free WAQI API token

Go to https://aqicn.org/data-platform/token/, enter your email, and
you'll get a token by email within a few minutes. This is what lets
your script authenticate with the API — think of it like a password
that identifies your script (rather than a browser) to the service.

### 2. Find your city's WAQI slug

Visit https://aqicn.org/city/all/ and find your city, or just try
`https://api.waqi.info/feed/bareilly/?token=YOUR_TOKEN` in a browser —
if it returns `"status":"ok"` with data, the slug works.

### 3. Install Python (if you haven't already)

Check first:
```
python3 --version
```
If that fails, install Python 3.10+ from https://python.org/downloads
(on Windows, tick "Add python.exe to PATH" during install).

### 4. Run it locally once

```bash
cd aqi-tracker
export AQI_TOKEN=your_token_here      # Windows: set AQI_TOKEN=your_token_here
export CITY=bareilly
python3 fetch_aqi.py
python3 analyze.py
python3 generate_dashboard.py
```

Then open `docs/index.html` in your browser directly — no server needed.

You'll only have 1 data point so far, so the chart and rolling average
will look sparse. That's expected; it builds up day by day. Re-run the
three commands daily for a bit locally if you want to see it fill in
before wiring up the automation.

### 5. Push this to GitHub

If you're new to git, here's the full sequence:

```bash
git init
git add .
git commit -m "Initial AQI tracker"
```

Then create an empty repository on github.com (no README, no
.gitignore — you already have files), and:

```bash
git remote add origin https://github.com/YOUR_USERNAME/aqi-tracker.git
git branch -M main
git push -u origin main
```

### 6. Add your token as a GitHub Secret (never commit it directly)

In your repo on GitHub: **Settings → Secrets and variables → Actions →
New repository secret**
- Name: `AQI_TOKEN`
- Value: your WAQI token

Then **Settings → Secrets and variables → Actions → Variables tab →
New repository variable**
- Name: `CITY`
- Value: `bareilly` (or whatever slug you used)

Secrets are for sensitive values (hidden in logs); variables are for
non-sensitive config. Your token is a secret; your city name isn't.

### 7. Turn on GitHub Pages

**Settings → Pages → Build and deployment → Source: "Deploy from a
branch" → Branch: `main`, folder: `/docs`.**

GitHub will give you a URL like
`https://YOUR_USERNAME.github.io/aqi-tracker/` within a minute or two.

### 8. Test the automation manually

**Actions tab → "Update AQI Dashboard" workflow → Run workflow**
(this uses the `workflow_dispatch` trigger, so you don't have to wait
for 8am). Watch it run; if it fails, click into the failed step — the
error message will tell you exactly what's wrong (usually a missing
secret or a typo'd city slug).

After that, it runs daily on its own.

## What to say about this in an interview

- "I built an automated data pipeline that scrapes an API daily via a
  scheduled GitHub Actions job, stores results in SQLite, and
  regenerates a static dashboard — so there's zero server cost and
  zero maintenance once it's running."
- "I implemented anomaly detection with a z-score against a 14-day
  rolling window, not just a raw threshold, so it adapts to what's
  normal for the season instead of hardcoding a number."
- "I made it fully reproducible: a fresh clone with one env var set up
  can regenerate the entire dashboard from scratch."

## Natural next steps (good "v2" talking points)

- Track multiple cities and let the dashboard switch between them.
- Swap the rule-based summary sentence for one written by an LLM
  (e.g. Claude) — feed it the same JSON summary.py already produces.
- Add a "compare to last year" view once you have 12+ months of data.
- Alert yourself (email/Telegram bot) when `is_anomaly` is true.
