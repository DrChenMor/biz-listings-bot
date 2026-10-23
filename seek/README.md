# SEEK Business listings

SEEK turns away windowless (headless) bots, the kind that run on servers like GitHub's, so SEEK can't be
collected there. There are two ways to get its listings into the **SEEK listings** tab, and both use the same
page-reading code and the same rules.

## Check SEEK (on your Mac)

Double-click **Check SEEK.command** in the project folder. A Chromium window opens and, at a person's pace
(a few minutes):

- reads the newest pages of each search in `config.toml` `[seek]` (3 pages ≈ 60 listings);
- opens up to 10 listings that don't have their full description yet, for the description and the broker's
  phone numbers;
- saves everything to the **SEEK listings** tab, with the same no-duplicates, change-tracking and no-food rules.

You can watch it, or click into the window and take over at any time. It runs only when you start it. If SEEK
ever shows a security check, it stops and says so; it never tries to get past one.

First time on a new Mac: `.venv/bin/pip install -r requirements-mac.txt && .venv/bin/playwright install chromium`,
then copy `.env.example` to `.env` and fill in your sheet ID and key file path.

## Save to sheet bookmark (as you browse)

You browse SEEK as normal and click a **Save to sheet** bookmark. It reads the listings on the page you're
looking at and adds them to the **SEEK listings** tab:

- **On a results page**, it saves all 20 listings: title, price, type, location, industry, advertiser and summary.
- **On a single listing**, it also saves the full description, including the broker's name and phone number
  when the listing gives them.
- **Each listing is added once.** When you see it again, the row is updated, and price drops, title changes
  and "under offer" are written to the Changes tab.
- **Food businesses are skipped** (cafés, restaurants, takeaways, bakeries, liquor stores and so on).

## Setup (about 5 minutes, once)

1. Open your Google Sheet. Go to **Extensions → Apps Script**.
2. Delete the code in the editor. Paste in the whole of [`SaveToSheet.gs`](SaveToSheet.gs), then click **Save**
   (the disk icon).
3. Click **Deploy → New deployment**. Click the gear next to "Select type" and choose **Web app**. Set:
   - **Execute as:** Me
   - **Who has access:** Anyone

   Click **Deploy**.
4. Google asks you to authorise the script. Choose your account. If it says "Google hasn't verified this app",
   click **Advanced → Go to (project name) (unsafe)**. That warning appears for every personal script; it's your own
   code, running in your own account. Click **Allow**.
5. Copy the **Web app URL** and open it in Chrome. It shows a **Save to sheet** button: drag it onto your
   bookmarks bar (press Cmd+Shift+B if the bar is hidden).

Keep the web app URL to yourself: anyone who has it can add rows to your sheet.

## Daily use

Open this search: health and personal services, within 50 km of Perth, newest first:

<https://www.seekbusiness.com.au/businesses-for-sale/within-health-beauty-fitness-or-personal-services/in-perth-wa?rad=50&sort=1>

Click **Save to sheet** on each results page. A new tab confirms what was saved, e.g. "Saved 20 listings:
3 new, 1 changed, 16 already up to date". Newest listings come first, so checking pages 1–2 every day or
two catches everything new. For listings that interest you, open them and click **Save to sheet** again to add the
full description and contact details.

## If you change the script later

After pasting a new version, use **Deploy → Manage deployments → Edit (pencil) → Version: New version → Deploy**.
The web app URL and your bookmark stay the same.

## Tests

`node --test seek/` checks the parts that decide what gets written (needs Node.js).
