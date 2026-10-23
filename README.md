# Business listings bot

Two bots that fill one Google Sheet and keep track of what changes:

- **Listings bot** (`python -m bizbot run`): WA businesses for sale, three times a day. New listings,
  price changes, "under offer", and listings that disappear (sold or withdrawn).
- **Health bot** (`python -m bizbot health`): health practices suburb by suburb from healthdirect, once a
  day, with contacts, location and, once your ABN Lookup key is set, the ABN and owner.

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

## Health businesses

The health bot reads [healthdirect](https://www.healthdirect.gov.au/australian-health-services)'s public
search pages ("Dentists in Subiaco", "Physiotherapy in Subiaco", ...) for the suburbs in `config.toml`, and
keeps **one row per practice per address** with every service it offers.

**Health businesses** tab: Status · Business name · Sector · Type (practice, individual practitioner,
hospital) · Main service · All services · Address · Suburb · Postcode · Phone · Email · Website · ABN
columns · Practitioners · Billing · Latitude/Longitude · Map link · healthdirect link · dates.

- **Choosing suburbs**: `[health] suburbs` in `config.toml`, written like healthdirect writes them
  (`subiaco-6008-wa`), or `postcode_ranges = [[6000, 6199]]` for all of Perth metro. Each suburb has about
  110 service-type pages; a run reads up to 300 pages, so a suburb takes about one run.
- **Keeping up to date**: each search page is read again every 30 days. New practices appear as "New
  business" in the Changes tab; one that no page has shown for 60 days becomes "Not seen recently".
- **Health pages** tab: the bot's progress through healthdirect's pages. Leave it alone.

**ABN matching** switches on by itself once the `ABN_GUID` secret holds your free
[ABN Lookup key](https://abr.business.gov.au/Tools/WebServices). For each practice it searches ABN Lookup by
name and fills ABN, registered entity, entity type, owner, ABN active-from date and business names.
The **ABN match** column says how far to trust it:

| ABN match | Meaning |
|---|---|
| High | Same name, and the ABN is registered in the practice's postcode |
| Medium | Same name in another postcode (often the owner's home or head office), or a very close name in the same postcode |
| Low | Nothing close enough. ABN columns stay empty; ABN notes names the closest candidate to check by hand |

ABN Lookup shows an owner's name only for sole traders. For companies and trusts the Owner column says an
ASIC search is needed; for partnerships it shows the partnership's name. ABN records are checked again every
90 days, and a new ABN or entity for a practice is logged in Changes: often a sign of a new owner.

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
   - `ABN_GUID` (when it arrives): your ABN Lookup key, for the health bot's owner matching
3. **Actions → Business listings bot → Run workflow** to start the first fill now. The same goes for
   **Health businesses bot**.

GitHub Actions minutes: unlimited on public repos. A private repo gets 2,000 free minutes a month; this bot
uses roughly 600–1,000 after the first fill. Scheduled workflows pause after 60 days without commits.
GitHub emails you, and one click re-enables them.

## Run it on your Mac

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m bizbot run --store local --limit 20      # listings -> data/ (CSV + JSON)
.venv/bin/python -m bizbot health --store local --limit 20   # health practices -> data/
```

Add `ABN_GUID=...` in front of the health command to try ABN matching locally.

With the Google Sheet:

```bash
export SHEET_ID=...
export GOOGLE_SERVICE_ACCOUNT_FILE=~/keys/listings-bot.json
.venv/bin/python -m bizbot run --store sheet
```

Tests: `.venv/bin/pip install pytest && .venv/bin/python -m pytest`

## Settings

`config.toml`: pages per run, delay range, start jitter, state (`wa`), which postcodes count as
Perth metro, the health bot's suburbs and service types, and how often health pages and ABN records are
checked again.

## Adding another site

Write `bizbot/sources/<site>.py` with `NAME`, `list_entries()` (every listing's ID, URL and last-updated
time) and `fetch_listing()` (the fields for one listing), then register it in
`bizbot/sources/__init__.py` and enable it in `config.toml`. WA broker websites are good candidates.
