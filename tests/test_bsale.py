from bizbot import config
from bizbot.sources import bsale

# A cut-down page with the same structure as a real bsale listing.
PAGE = """
<html><head><meta property="product:price:amount" content="95000"></head><body>
<ul><li><a class="menu-fly" data-pos="#catbah" href="/beauty-and-health">Beauty and Health</a></li></ul>
<div id="catbah"><a href="/hair-salon-for-sale-business">Hair Salon For Sale</a></div>
<h1 class="h2 text-primary mb-4">Established Hair Salon For Sale - Morley</h1>
<div id="listingMain">
  <div class="d-block mb-1"><p>Share</p></div>
  <p class="mt-4 mb-4">Morley, Western Australia 6062</p>
  <h2 class="text-success mt-1">$95,000 + SAV</h2>
  <h3>Key Features</h3>
  <ul class="listReset mb-4"><li>Three hairdressing stations</li></ul>
  <ul class="listReset mt-4"><li>Turnover: $Approximately $281,700 for FY2026</li>
      <li>Established: Operating under current ownership since 2009</li></ul>
  <p><span class="mr-3">Business Category</span> <a href="/hair-salon-for-sale-business"><span>Hair Salon</span></a></p>
  <div class="bsaleDesc">The owner is preparing for retirement.<br>Net profit $60,000 p.a.</div>
  <ul class="my-5 list-inline"><li>Perth Region WA</li><li>Western Australia</li></ul>
  <div class="mt-5"><p>Similar Businesses For Sale</p><ul class="listReset"><li>Other salon</li></ul></div>
</div>
<div id="listingSide"><p class="text-primary bold">Jane Broker</p>
  <a class="btn-phone" data-ph="0400 000 000" href="tel:+61400000000">0400 0....</a></div>
</body></html>
"""


def test_parse_listing_reads_every_field():
    cfg = config.load()
    listing = bsale.parse_listing(PAGE, cfg)
    assert listing["title"] == "Established Hair Salon For Sale - Morley"
    assert (listing["suburb"], listing["postcode"], listing["region"]) == ("Morley", "6062", "Perth Region WA")
    assert listing["perth_metro"] == "Yes"
    assert (listing["price_text"], listing["price_aud"], listing["price_basis"]) == ("$95,000 + SAV", 95_000, "+ stock (SAV)")
    assert (listing["industry"], listing["category"]) == ("Beauty and Health", "Hair Salon")
    assert listing["turnover_aud"] == 281_700
    assert (listing["profit_aud"], listing["profit_type"]) == (60_000, "Net profit")
    assert listing["established"] == "2009"
    assert listing["sale_reason"] == "Retirement"
    assert listing["key_features"].splitlines() == [
        "Three hairdressing stations",
        "Turnover: $Approximately $281,700 for FY2026",
        "Established: Operating under current ownership since 2009",
    ]
    assert (listing["broker"], listing["broker_phone"]) == ("Jane Broker", "0400 000 000")
    assert listing["status"] == "Active"


def test_parse_listing_returns_none_for_a_page_without_a_listing():
    assert bsale.parse_listing("<html><body><h1>Not found</h1></body></html>", config.load()) is None
