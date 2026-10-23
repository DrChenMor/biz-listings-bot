# Business listings bot

Collects WA businesses for sale into a Google Sheet, three times a day, and keeps track of what changes:
new listings, price changes, "under offer", and listings that disappear (sold or withdrawn).

No AI and no paid services. It runs free on GitHub Actions, and Google Sheets is free.

## What it reads

| Site | Status | How |
|---|---|---|
| [bsale.com.au](https://bsale.com.au) | ✅ Working | Public sitemap + listing pages. About 1,900 WA listings. |
| SEEK Business | ⛔ Not included | Cloudflare stops automated browsers on the first page. |
| BusinessesForSale.com | ⛔ Not included | Cloudflare blocks automated requests outright. |

The bot never tries to get past a site's bot protection. If a site starts refusing it (HTTP 403 or 429),
it stops that site for the run and writes "blocked" in the Runs tab.

## How it stays efficient and quiet

- **Only opens what changed.** bsale's sitemap gives each listing's last-updated time, so after the first
  fill the bot opens only new or updated listings.
- **Slow and random.** It waits 3–8 seconds (random) between pages, shuffles the order, runs at odd times,
  and scheduled runs start after a random 0–10 minute wait.
- **Respects robots.txt** on every site it reads.
- **Never adds a listing twice.** Each listing is keyed by site + listing ID.
- **Caps each run** at 400 pages. The first fill of ~1,900 listings takes about 5 runs (under 2 days);
  newest listings are collected first.

## The Google Sheet

**Listings** tab, one row per listing:
Status · Title · Notes · Industry · Category · Suburb · Postcode · Region · Perth metro · Asking price ·
Price (AUD) · Price basis · Turnover · Profit · Profit type · Established · Reason for sale ·
Broker / seller · Broker phone · URL · … · Key features · Description

- **Notes** is a one-line summary built by simple rules, e.g.
  *"Hair Salon in Morley, Perth Region WA. Asking $95,000. Turnover ~$281,700/yr. Est. 2009. Selling because: Retirement."*
  When a listing states profit, the note also gives the price-to-profit multiple.
- Turnover and profit are read from the listing text by patterns. They are right most of the time, but
  check the Description before relying on a number.
- **Status**: Active, Under offer, Sold, or Removed (gone from the site).
- New listings are added at the top.
- **Add your own columns to the right of the "Key" column** (for example "Contacted?" or "My notes").
  The bot keeps them lined up with their listing. Don't edit the bot's columns; it overwrites them.

**Changes** tab: one row per new listing, price change, status change, title or category change, or
description edit, with the old and new values.

**Runs** tab: one row per run, so you can see the bot is alive and what it did.

## Setup

### 1. Google service account (lets the bot write to your sheet)

1. Go to <https://console.cloud.google.com/>, create a project (any name).
2. **APIs & Services → Library** → enable **Google Sheets API**.
3. **IAM & Admin → Service accounts → Create service account** (any name, no roles needed).
4. Open the new account → **Keys → Add key → Create new key → JSON**. A `.json` file downloads.
   Keep it private; never commit it.
5. Create a new Google Sheet. Click **Share** and add the service account's email
   (ends in `iam.gserviceaccount.com`) as **Editor**.
6. Copy the sheet ID from its URL: `https://docs.google.com/spreadsheets/d/<SHEET_ID>/edit`.

### 2. GitHub

1. Push this folder to a GitHub repository.
2. **Settings → Secrets and variables → Actions → New repository secret**, add:
   - `SHEET_ID`: the sheet ID, or the sheet's whole link
   - `GOOGLE_SERVICE_ACCOUNT_JSON`: paste the whole contents of the `.json` key file
3. **Actions → Business listings bot → Run workflow** to start the first fill now.

GitHub Actions minutes: unlimited on public repos. A private repo gets 2,000 free minutes a month; this bot
uses roughly 600–1,000 after the first fill. Scheduled workflows pause after 60 days without commits.
GitHub emails you, and one click re-enables them.

## Run it on your Mac

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m bizbot run --store local --limit 20     # writes to data/ (CSV + JSON)
```

With the Google Sheet:

```bash
export SHEET_ID=...
export GOOGLE_SERVICE_ACCOUNT_FILE=~/keys/listings-bot.json
.venv/bin/python -m bizbot run --store sheet
```

Tests: `.venv/bin/pip install pytest && .venv/bin/python -m pytest`

## Settings

`config.toml`: pages per run, delay range, start jitter, state (`wa`), and which postcodes count as
Perth metro.

## Adding another site

Write `bizbot/sources/<site>.py` with `NAME`, `list_entries()` (every listing's ID, URL and last-updated
time) and `fetch_listing()` (the fields for one listing), then register it in
`bizbot/sources/__init__.py` and enable it in `config.toml`. WA broker websites are good candidates.
