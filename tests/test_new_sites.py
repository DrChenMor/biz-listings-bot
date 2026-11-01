from types import SimpleNamespace

import pytest

from bizbot import config
from bizbot.http import Unavailable
from bizbot.run import _newest_first
from bizbot.sources import anybusiness, business2sell, businessforsale, noagentbusiness


class FakeClient:
    def __init__(self, pages):
        self.pages = pages

    def get(self, url, **_):
        return SimpleNamespace(status_code=200, text=self.pages[url])


def b2s_card(listing_id, title, category="Cleaning"):
    return f"""<div class="b2s_listing"><h2 class="b2s_listing_heading"><a href="/businesses-details/{title.lower().replace(' ', '-')}-{listing_id}.php">{title}</a></h2>
    <div class="b2s_listing_price">$100,000</div><p class="b2s_listing_subheading">Short.</p><ul class="b2s_listing_cat"><li>{category}</li></ul></div>"""


def b2s_page(cards, total, next_page=None):
    more = f'<a href="https://www.business2sell.com.au/businesses/wa?page={next_page}">Next</a>' if next_page else ""
    return f"<html><head><title>{total} Business for sale in Western Australia | Business2sell.com.au</title></head><body>{cards}{more}</body></html>"


B2S = "https://www.business2sell.com.au/businesses/wa"


def test_business2sell_reads_every_page_and_leaves_food_out():
    client = FakeClient({
        B2S: b2s_page(b2s_card(1, "Carpet Cleaning") + b2s_card(2, "Busy Cafe", "Cafe"), 3, next_page=2),
        f"{B2S}?page=2": b2s_page(b2s_card(3, "Hair Salon", "Beauty"), 3),
    })
    entries = business2sell.list_entries(client, config.load())
    assert [e.listing_id for e in entries] == ["1", "3"]
    assert entries[0].url == "https://www.business2sell.com.au/businesses-details/carpet-cleaning-1.php"


def test_business2sell_links_without_a_number_use_their_words_as_the_id():
    html = '<div class="b2s_listing"><h2 class="b2s_listing_heading"><a href="/businesses-details/hire-business-in-perth.php">Hire</a></h2></div>'
    entries = business2sell.list_entries(FakeClient({B2S: b2s_page(html, 1)}), config.load())
    assert [e.listing_id for e in entries] == ["hire-business-in-perth"]


def test_business2sell_short_read_does_not_look_like_removed_listings():
    client = FakeClient({B2S: b2s_page(b2s_card(1, "Carpet Cleaning"), 50)})
    with pytest.raises(Unavailable, match="read only 1 of 50"):
        business2sell.list_entries(client, config.load())


def test_business2sell_listing_page():
    html = """<h2 class="b2s_standard_heading">Established VR Business – Perth</h2><ul class="b2s_listing_top_list">
    <li> <span>Location:</span> Osborne Park, Perth, Western Australia </li><li><span>Category:</span> Entertainment, Amusements</li>
    <li><span>Asking Price:</span>$240,000</li><li><span>Sales revenue :</span>$283,000</li><li><span>Net profit :</span>$87,000</li></ul>
    <div class="business_description_wrapper"><h3>Business description</h3><p>Established since 2019. Owner is retiring. Call 0422 930 549.</p>
    <p>Seller Name : Jason Wilkinson</p><p>Phone:</p></div>"""
    row = business2sell.parse_listing(html, config.load())
    assert (row["title"], row["suburb"], row["region"]) == ("Established VR Business – Perth", "Osborne Park", "Perth")
    assert (row["industry"], row["category"]) == ("Entertainment", "Entertainment, Amusements")
    assert (row["price_aud"], row["turnover_aud"], row["profit_aud"]) == (240_000, 283_000, 87_000)
    assert (row["broker"], row["broker_phone"], row["established"]) == ("Jason Wilkinson", "0422 930 549", "2019")
    assert "Seller Name" not in row["description"] and not row["description"].startswith("Business description")


def test_business2sell_undisclosed_figures_stay_empty():
    html = """<h2 class="b2s_standard_heading">Quiet Shop</h2><ul><li><span>Asking Price:</span>$50,000</li><li><span>Sales revenue :</span>Undisclosed</li>
    <li><span>Net profit :</span>Undisclosed</li></ul><div class="business_description_wrapper">A quiet shop.</div>"""
    row = business2sell.parse_listing(html, config.load())
    assert (row["turnover_aud"], row["profit_aud"]) == (None, None)


AB = "https://www.anybusiness.com.au/business-for-sale/wa"


def ab_card(slug):
    return f'<div class="uk-grid"><a href="/listings/{slug}"><img alt="x"></a><a href="/listings/{slug}">View more</a><p>$110,000</p></div>'


def test_anybusiness_reads_every_page_and_leaves_food_out_from_the_link():
    client = FakeClient({
        AB: f'<p>3 results</p>{ab_card("bunbury-wa-6230-home-garden-services-3472796")}{ab_card("kardinya-wa-6163-franchise-food-hospitality-cafe-3472413")}<a href="/business-for-sale/wa?page=2">2</a>',
        f"{AB}?page=2": f'{ab_card("augusta-wa-6290-other-3462928")}',
    })
    entries = anybusiness.list_entries(client, config.load())
    assert [e.listing_id for e in entries] == ["3472796", "3462928"]


def test_anybusiness_listing_page():
    html = """<link rel="canonical" href="https://www.anybusiness.com.au/listings/osborne-park-wa-6017-amusements-3474051">
    <div>Status:</div><div>Under Offer</div><div itemprop="name"><h1>Turnkey VR Business</h1>
    <div style="font-style: italic">Amusements | Business for Sale | 120 Hector St W, Osborne Park, WA, 6017</div></div>
    <span itemprop="price">$240,000</span><div itemprop="seller"><p>Advance Business Brokers (AU)</p><p>9B Pecten Close, Heathridge, WA 6027</p><p>Rachel Dowdy</p></div><div itemprop="description">Revenue of $283,000 last year.</div>
    <div class="view-agent-mobile-btn" data-react-props='{"defaultContactNO":"0490 357 312"}'></div>"""
    row = anybusiness.parse_listing(html, config.load())
    assert (row["title"], row["status"]) == ("Turnkey VR Business", "Under offer")
    assert (row["category"], row["suburb"], row["postcode"], row["perth_metro"]) == ("Amusements", "Osborne Park", "6017", "Yes")
    assert (row["price_aud"], row["turnover_aud"]) == (240_000, 283_000)
    assert (row["broker"], row["broker_phone"]) == ("Rachel Dowdy / Advance Business Brokers (AU)", "0490 357 312")
    assert "120 Hector St W" in row["key_features"]


def test_anybusiness_owner_ad_is_a_private_seller():
    html = '<div><h1>Shop</h1></div><div itemprop="seller"><p>Vendor details</p><p>Name:</p><p>Sam</p></div>'
    assert anybusiness.parse_listing(html, config.load())["broker"] == "Private Seller: Sam"


BFS = "https://www.businessforsale.com.au/for-sale/wa/"


def bfs_card(listing_id):
    return f'<div class="result listing"><a href="/australia/{listing_id}/some-business">A business</a></div>'


def test_businessforsale_reads_every_page_with_ids_that_are_not_numbers():
    client = FakeClient({
        BFS: f'<p>2 businesses listed for sale in WA</p>{bfs_card("38jemW10109")}<a href="{BFS}?page=2">2</a>',
        f"{BFS}?page=2": bfs_card("844b0a42db"),
    })
    entries = businessforsale.list_entries(client, config.load())
    assert [e.listing_id for e in entries] == ["38jemW10109", "844b0a42db"]
    assert entries[0].url == "https://www.businessforsale.com.au/australia/38jemW10109/some-business"
    assert sorted(entries + [SimpleNamespace(listing_id="42")], key=_newest_first)[-1].listing_id == "42"


def test_businessforsale_listing_page_marks_owner_direct_as_a_private_seller():
    html = """<script type="application/ld+json">{"@graph":[{"@type":"Product","name":"Mobile Hostel","category":"Personal Services > Travel Agency","description":"Short."}]}</script>
    <p>OWNER DIRECT</p><p>Asking price</p><p>$240,000</p><p>+GST, Negotiable</p><p>Revenue</p><p>$250k - 500k</p><p>Profit</p><p>$100k - $200k</p>
    <p>Full description, as written by the seller</p><p>An established tour business.</p><p>02 · THE NUMBERS</p><p>Location</p><p>Perth Region, WA</p>"""
    row = businessforsale.parse_listing(html, config.load())
    assert (row["title"], row["industry"], row["category"]) == ("Mobile Hostel", "Personal Services", "Travel Agency")
    assert (row["region"], row["suburb"], row["broker"]) == ("Perth Region", "", "Private Seller")
    assert (row["price_text"], row["price_aud"]) == ("$240,000 +GST, Negotiable", 240_000)
    assert (row["turnover_aud"], row["profit_aud"]) == (250_000, 100_000)
    assert row["description"] == "An established tour business."


def test_businessforsale_broker_ad_and_a_suburb_written_without_a_comma():
    html = """<script type="application/ld+json">{"@graph":[{"@type":"Product","name":"Dog Wash","category":"Franchise > Franchise Resale"}]}</script>
    <p>Asking price</p><p>$30,000</p><p>Full description, as written by the broker</p><p>Love dogs?</p><p>03 · LOCATION</p><p>Location</p><p>Nedlands WA</p>"""
    row = businessforsale.parse_listing(html, config.load())
    assert (row["suburb"], row["region"], row["broker"], row["description"]) == ("Nedlands", "Nedlands", "", "Love dogs?")


NAB = "https://www.noagentbusiness.com.au"


def nab_page(heading, lines, name="Pilates Studio", description="Phone enquiries - please quote property ID 41433. Call 1300 594 794. Est. 2015."):
    body = "".join(f"<p>{line}</p>" for line in lines)
    record = '{"@type":"RealEstateListing","name":"%s","description":"%s"}' % (name, description)
    return f'<script type="application/ld+json">{record}</script><h1>{heading}</h1>{body}'


def test_no_agent_business_reads_the_sitemap_and_leaves_food_out_from_the_link():
    sitemap = f"""<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
    <url><loc>{NAB}/business-retail-wa-denmark-9638/</loc><lastmod>2019-06-07T02:29:34+00:00</lastmod></url>
    <url><loc>{NAB}/business-food-_-hospitality-wa-perth-10000/</loc><lastmod>2026-02-14T20:08:16+00:00</lastmod></url>
    <url><loc>{NAB}/business-accommodation-_-tourism-wa-dunsborough-10209/</loc><lastmod>2020-10-29T03:22:31+00:00</lastmod></url>
    <url><loc>{NAB}/about-us/</loc></url></urlset>"""
    client = SimpleNamespace(get=lambda url, **_: SimpleNamespace(status_code=200, content=sitemap.encode(), text=sitemap))
    entries = noagentbusiness.list_entries(client, config.load())
    assert [(e.listing_id, e.lastmod[:4]) for e in entries] == [("9638", "2019"), ("10209", "2020")]


def test_no_agent_business_ad_is_a_private_seller():
    html = nab_page("Pilates Business For Sale By Owner Applecross, Western Australia (ID 41433)", ["Gallery", "$179,000", "Leisure / Entertainment For Sale:", "Applecross 6153 WA", "Stunning studio"])
    row = noagentbusiness.parse_listing(html, config.load())
    assert (row["title"], row["status"], row["broker"]) == ("Pilates Studio", "Active", "Private Seller")
    assert (row["category"], row["suburb"], row["postcode"], row["perth_metro"]) == ("Leisure / Entertainment", "Applecross", "6153", "Yes")
    assert (row["price_aud"], row["broker_phone"], row["established"]) == (179_000, "1300 594 794", "2015")


def test_no_agent_business_old_sold_ads_count_as_sold():
    html = nab_page("Retail Business Sold By Owner Denmark, Western Australia (ID 9638)", ["$250,000", "Retail Sold:", "Denmark 6333 WA"])
    row = noagentbusiness.parse_listing(html, config.load())
    assert (row["status"], row["category"]) == ("Sold", "Retail")


def test_no_agent_business_takes_the_place_from_the_link_when_the_page_hides_it():
    page = nab_page("Kayak Business For Sale By Owner (ID 30341)", ["Gallery"], name="Kayak Retailer")
    client = SimpleNamespace(get=lambda url, **_: SimpleNamespace(status_code=200, text=page, raise_for_status=lambda: None))
    entry = noagentbusiness.Entry("30341", f"{NAB}/business-retail-wa-perth-30341/", "2026-10-28")
    row = noagentbusiness.fetch_listing(client, entry, config.load())
    assert (row["suburb"], row["region"]) == ("Perth", "Perth")
