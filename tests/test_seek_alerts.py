from urllib.parse import quote

from bizbot import config, seek_alerts

SALON = "https://www.seekbusiness.com.au/business-listing/mount-pleasant-stunning-hair-salon-for-sale/794248"
CAFE = "https://www.seekbusiness.com.au/business-listing/busy-cafe-in-leederville/700001"
PILATES = "https://www.seekbusiness.com.au/business-listing/boutique-pilates-studio/700002"

# Shaped like a typical alert: one table block per listing, a tracking link with the real address encoded.
EMAIL = f"""
<html><body>
<h1>3 new businesses match your saved search</h1>
<table>
  <tr><td>
    <a href="https://click.example.com/track?u={quote(SALON, safe='')}&amp;id=1">Mount Pleasant Stunning Hair Salon for Sale</a>
    <p>Perth - Greater, Mount Pleasant, WA 6153</p>
    <p>$87,000 + SAV</p>
    <p>Health, Beauty &amp; Fitness &gt; Hair, Beauty &amp; Spa</p>
    <p>Established 23+ years, this salon delivers $13K weekly sales and ~$160K net profit.</p>
    <a href="{SALON}">View business</a>
  </td></tr>
  <tr><td>
    <a href="{CAFE}">Busy Cafe in Leederville</a>
    <p>Perth - Greater, Leederville, WA 6007</p><p>$150,000</p>
    <p>Food &amp; Drink &gt; Coffee, Cafes &amp; Restaurants &gt; Cafe</p>
  </td></tr>
  <tr><td>
    <a href="{PILATES}">Boutique Pilates Studio</a>
    <p>Perth - Greater, Perth, WA 6000</p><p>P.O.A</p>
    <p>Health, Beauty &amp; Fitness &gt; Sport, Fitness &amp; Adventure</p>
  </td></tr>
</table>
<a href="https://www.seekbusiness.com.au/unsubscribe">Unsubscribe</a>
</body></html>
"""


def test_every_listing_is_found_with_its_details():
    listings = {l["id"]: l for l in seek_alerts.parse_alert(EMAIL)}
    assert set(listings) == {"794248", "700001", "700002"}
    salon = listings["794248"]
    assert salon["url"] == SALON
    assert salon["title"] == "Mount Pleasant Stunning Hair Salon for Sale"
    assert salon["price_text"] == "$87,000 + SAV"
    assert salon["location"] == "Perth - Greater, Mount Pleasant, WA 6153"
    assert salon["industry"] == "Health, Beauty & Fitness > Hair, Beauty & Spa"
    assert "net profit" in salon["summary"]
    assert listings["700002"]["price_text"] == "P.O.A"


def test_tracking_links_are_decoded():
    assert seek_alerts.listing_link(f"https://t.example.com/r?url={quote(quote(SALON, safe=''), safe='')}") == (SALON, "794248")
    assert seek_alerts.listing_link("https://www.seekbusiness.com.au/unsubscribe") == ("", "")


def test_alerts_add_new_listings_only_and_skip_food(monkeypatch):
    class Store:
        def __init__(self):
            self.saved = {}

        def load(self, table):
            return {"seek:700002": {"key": "seek:700002", "title": "Boutique Pilates Studio", "price_text": "$300,000"}}

        def save(self, table, rows):
            self.saved = rows

        def log(self, changes, runs):
            self.changes, self.runs = changes, runs

    monkeypatch.setenv("GMAIL_ADDRESS", "alerts@example.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "abcd efgh ijkl mnop")
    monkeypatch.setattr(seek_alerts, "fetch_alerts", lambda address, password: [EMAIL])
    store = Store()
    [stats] = seek_alerts.run(config.load(), store)
    assert set(store.saved) == {"seek:794248", "seek:700002"}  # cafe skipped (food)
    assert store.saved["seek:700002"]["price_text"] == "$300,000"  # existing row left as Check SEEK saw it
    assert (stats["new"], stats["skipped"], stats["fetched"]) == (1, 1, 1)
    assert [c["what"] for c in store.changes] == ["New listing"]


def test_off_without_gmail_settings(monkeypatch):
    monkeypatch.delenv("GMAIL_ADDRESS", raising=False)
    monkeypatch.delenv("GMAIL_APP_PASSWORD", raising=False)
    assert seek_alerts.run(config.load(), store=None) == []
