import json
from types import SimpleNamespace

from bizbot import config, health


def record(service_id, name="Subiaco Dental", org="org-1", loc="loc-1", suburb="SUBIACO", postcode="6008", service="Dentists", contacts=None, practitioners=None):
    return {
        "id": service_id,
        "organisation": {"name": name, "id": org},
        "location": {"id": loc, "physicalLocation": {"addressLine1": "1 Rokeby Road", "postcode": postcode, "suburb": {"label": suburb}, "geocode": {"latitude": -31.9, "longitude": 115.8}}},
        "serviceType": [{"label": service}],
        "billingOptions": [{"valueType": {"label": "Fees apply for this service"}, "value": "yes"}],
        "contacts": contacts if contacts is not None else [
            {"valueType": {"label": "Phone"}, "value": "08 9000 0000", "priority": 4},
            {"valueType": {"label": "Email"}, "value": "Hello@SubiDental.com.au", "priority": 2},
            {"valueType": {"label": "Website"}, "value": "https://www.subidental.com.au/", "priority": 1},
        ],
        "practitioners": practitioners or [],
    }


def pin(service_id, name, suburb="SUBIACO", postcode="6008", lat=-31.9, lng=115.8):
    return {"id": service_id, "organisationName": name, "suburbLabel": suburb, "postcode": postcode, "stateLabel": "WA", "location": {"latitude": lat, "longitude": lng}}


def page_html(services, pins, label="Dentists"):
    data = {"props": {"pageProps": {"healthcareServices": {"count": len(pins), "services": services}, "mapPins": pins, "serviceType": {"valueType": {"label": label}}}}}
    return f'<html><script id="__NEXT_DATA__" type="application/json">{json.dumps(data)}</script></html>'


class FakeClient:
    def __init__(self, pages):
        self.pages = pages
        self.opened = []

    def get(self, url, **_):
        self.opened.append(url)
        return SimpleNamespace(text=self.pages.get(url, "<html></html>"))


def stats():
    return dict(new=0, updated=0, removed=0, fetched=0, backlog=0, errors=0)


def test_business_fields_reads_contacts_address_and_billing():
    fields = health.business_fields(record("s1"))
    assert fields["key"] == "hd:org-1:loc-1"
    assert (fields["address"], fields["suburb"], fields["postcode"]) == ("1 Rokeby Road", "Subiaco", "6008")
    assert (fields["phones"], fields["emails"], fields["websites"]) == (["08 9000 0000"], ["hello@subidental.com.au"], ["subidental.com.au"])
    assert fields["billing"] == "Fees apply"
    assert fields["map"] == "https://www.google.com/maps/search/?api=1&query=-31.9,115.8"


def test_one_row_per_practice_and_address_with_all_its_services():
    businesses, changes, counts = {}, [], stats()
    health.merge(businesses, health.business_fields(record("s1", service="Psychology")), "2026-10-23 10:00", changes, counts)
    health.merge(businesses, health.business_fields(record("s2", service="GP (General practice)", contacts=[])), "2026-10-23 10:00", changes, counts)
    row = businesses["hd:org-1:loc-1"]
    assert row["services"] == "GP (General practice); Psychology"
    assert (row["main_service"], row["sector"], row["kind"]) == ("GP (General practice)", "GP / medical centre", "Practice / clinic")
    assert row["email"] == "hello@subidental.com.au"  # kept even though the second service listed none
    assert row["service_ids"] == "s1 s2"
    assert counts["new"] == 1 and [c["what"] for c in changes] == ["New business"]


def test_a_new_phone_number_is_logged_as_a_change():
    businesses, changes, counts = {}, [], stats()
    health.merge(businesses, health.business_fields(record("s1")), "2026-10-23 10:00", changes, counts)
    changes.clear()
    new_phone = [{"valueType": {"label": "Phone"}, "value": "08 9111 1111", "priority": 4}]
    health.merge(businesses, health.business_fields(record("s1", contacts=new_phone)), "2026-10-24 10:00", changes, counts)
    assert [(c["what"], c["old"], c["new"]) for c in changes] == [("Phone", "08 9000 0000", "08 9000 0000; 08 9111 1111")]
    # The same number written differently isn't new.
    changes.clear()
    same_number = [{"valueType": {"label": "Phone"}, "value": "08 90000000", "priority": 4}]
    health.merge(businesses, health.business_fields(record("s1", contacts=same_number)), "2026-10-25 10:00", changes, counts)
    assert changes == []


def test_individual_practitioners_and_sectors():
    assert health.main_service({"Cardiology"}) == ("Cardiology", "Medical specialist")
    assert health.main_service({"Optometry", "Audiology"}) == ("Audiology", "Optical & hearing")
    assert health.main_service({"Psychology"}, "St John Of God Hospital - Subiaco")[1] == "Hospital / day surgery"
    assert health.main_service({"Cancer support group"})[1] == "Community / support"
    assert health.main_service({"Parenting and family support", "Psychology"}) == ("Psychology", "Mental health")
    assert health.main_service({"Dietetics"})[1] == "Allied health"
    assert health.main_service({"Anaesthetics"})[1] == "Medical specialist"
    businesses, changes, counts = {}, [], stats()
    health.merge(businesses, health.business_fields(record("s1", name="Dr Jane Smith", service="Cardiology")), "now", changes, counts)
    assert businesses["hd:org-1:loc-1"]["kind"] == "Individual practitioner"


def test_search_page_opens_only_the_practice_pages_it_needs():
    cfg = config.load()
    search_url = "https://www.healthdirect.gov.au/australian-health-services/search/subiaco-6008-wa/dentists/310144008"
    known_url = "https://www.healthdirect.gov.au/australian-health-services/healthcare-service/subiaco-6008-wa/kings-dental/dentists/s3"
    unknown_url = "https://www.healthdirect.gov.au/australian-health-services/healthcare-service/subiaco-6008-wa/rokeby-dental/dentists/s4"
    full = [record("s1"), record("s2", name="Leederville Dental", org="org-2", loc="loc-2", suburb="LEEDERVILLE", postcode="6007")]
    pins = [pin("s1", "Subiaco Dental"), pin("s3", "Kings Dental", lat=-31.95), pin("s4", "Rokeby Dental", lat=-31.96), pin("s5", "Far Dental", suburb="NEDLANDS", postcode="6009")]
    detail = json.dumps({"props": {"pageProps": {"healthcareService": record("s4", name="Rokeby Dental", org="org-4", loc="loc-4")}}})
    client = FakeClient({search_url: page_html(full, pins), unknown_url: f'<script id="__NEXT_DATA__">{detail}</script>'})
    businesses = {"hd:org-3:loc-3": {"key": "hd:org-3:loc-3", "name": "Kings Dental", "service_ids": "s3", "services": "Dentists", "details_checked": health.now()}}
    page = {"key": search_url, "service": "dentists"}

    used, complete = health._read_search_page(cfg, client, page, businesses, [], stats(), "2026-10-23 10:00", budget=10)

    assert client.opened == [search_url, unknown_url]  # Kings is known and fresh; Leederville and Nedlands aren't target suburbs
    assert known_url not in client.opened
    assert (used, complete) == (2, True)
    assert set(businesses) == {"hd:org-1:loc-1", "hd:org-3:loc-3", "hd:org-4:loc-4"}
    assert page["results"] == 4 and page["last_checked"] == "2026-10-23 10:00"


def test_page_left_unfinished_when_the_budget_runs_out():
    cfg = config.load()
    search_url = "https://www.healthdirect.gov.au/x/search/subiaco-6008-wa/dentists/1"
    client = FakeClient({search_url: page_html([], [pin("s4", "Rokeby Dental")])})
    page = {"key": search_url, "service": "dentists"}
    used, complete = health._read_search_page(cfg, client, page, {}, [], stats(), "now", budget=1)
    assert (used, complete) == (1, False)
    assert "last_checked" not in page


def test_target_suburbs_and_postcode_ranges():
    cfg = config.load()
    assert health._is_target(cfg, "subiaco-6008-wa", "6008")
    assert health._is_target(cfg, "subiaco", "6008")
    assert not health._is_target(cfg, "nedlands", "6009")
    cfg.health.postcode_ranges = [(6000, 6010)]
    assert health._is_target(cfg, "nedlands", "6009")
