from types import SimpleNamespace

import pytest

from bizbot import abn, config


class FakeLookup:
    """Stands in for ABN Lookup: names() by query, details() by ABN."""

    def __init__(self, names, details):
        self._names, self._details = names, details
        self.requests = 0

    def names(self, query):
        self.requests += 1
        return self._names.get(query, [])

    def details(self, number):
        self.requests += 1
        return self._details[number]


def name(number, text, postcode, state="WA", current=True):
    return {"abn": number, "name": text, "postcode": postcode, "state": state, "iscurrent": current, "score": 100}


def details(number, entity, kind, code, postcode, since="2005-01-01", status="Active", business_names=()):
    return {"Abn": number, "AbnStatus": status, "AbnStatusEffectiveFrom": since, "EntityName": entity, "EntityTypeName": kind,
            "EntityTypeCode": code, "AddressPostcode": postcode, "AddressState": "WA", "BusinessName": list(business_names)}


ROW = {"name": "Subiaco Dental Practice", "suburb": "Subiaco", "postcode": "6008"}


def test_same_name_in_the_same_postcode_is_a_high_match_with_the_sole_trader_as_owner():
    lookup = FakeLookup(
        {"Subiaco Dental Practice": [name("36737256533", "SUBIACO DENTAL PRACTICE", "6008")]},
        {"36737256533": details("36737256533", "YOONG, ALEX CHUNG-EN", "Individual/Sole Trader", "IND", "6008", business_names=["Subiaco Dental Practice"])},
    )
    found = abn.match(lookup, ROW, "WA")
    assert (found["abn"], found["abn_match"], found["owner"]) == ("36 737 256 533", "High", "Alex Chung-En Yoong")
    assert found["abn_business_names"] == "Subiaco Dental Practice"


def test_other_postcode_is_medium_and_noted():
    lookup = FakeLookup(
        {"Subiaco Dental Practice": [name("83125642430", "Subiaco Dental Practice Pty Ltd", "6009")]},
        {"83125642430": details("83125642430", "MH DENTAL SERVICES PTY LIMITED", "Australian Private Company", "PRV", "6009")},
    )
    found = abn.match(lookup, ROW, "WA")
    assert found["abn_match"] == "Medium"
    assert found["owner"] == "Not on ABN (company: directors need an ASIC company extract)"
    assert "ABN location is 6009." in found["abn_notes"]


def test_prefers_the_abn_in_the_practice_postcode_and_mentions_the_other():
    lookup = FakeLookup(
        {"Subiaco Dental Practice": [name("85316868135", "SUBIACO DENTAL PRACTICE", "6010"), name("79228998908", "SUBIACO DENTAL PRACTICE", "6008")]},
        {
            "85316868135": details("85316868135", "PASTORINO, SUSANNA", "Individual/Sole Trader", "IND", "6010", since="2000-01-01"),
            "79228998908": details("79228998908", "The Trustee for Alagati Family Trust", "Discretionary Trading Trust", "DTT", "6008", since="2025-06-01"),
        },
    )
    found = abn.match(lookup, ROW, "WA")
    assert found["abn"] == "79 228 998 908"
    assert found["owner"] == "Not on ABN (trust: the trustee needs an ASIC search)"
    assert "possibly a recent change of owner" in found["abn_notes"]
    assert "Also on ABN 85 316 868 135: PASTORINO, SUSANNA" in found["abn_notes"]


def test_no_close_name_leaves_the_abn_empty_and_names_the_closest():
    lookup = FakeLookup({"Subiaco Dental Practice": [name("11111111111", "PERTH SMILE CENTRE", "6000")]}, {})
    found = abn.match(lookup, ROW, "WA")
    assert (found["abn"], found["abn_match"]) == ("", "Low")
    assert "PERTH SMILE CENTRE" in found["abn_notes"]


def test_other_states_and_cancelled_abns_are_ignored():
    lookup = FakeLookup({"Subiaco Dental Practice": [name("1", "SUBIACO DENTAL PRACTICE", "2000", state="NSW"), name("2", "SUBIACO DENTAL PRACTICE", "6008", current=False)]}, {})
    assert abn.match(lookup, ROW, "WA")["abn_notes"] == "No similar name on ABN Lookup"


def test_name_without_suburb_is_tried_too():
    assert abn._queries("Jupiter Health Subiaco", "Subiaco") == ["Jupiter Health Subiaco", "Jupiter Health"]
    assert abn._queries("Jupiter Health - Subiaco", "Subiaco") == ["Jupiter Health - Subiaco", "Jupiter Health"]
    assert abn._queries("Rokeby GP", "Subiaco") == ["Rokeby GP"]


def test_similarity_and_owner_wording():
    assert abn.similarity("Dental 359", "DENTAL 359 PTY LTD") == 1.0
    assert abn.similarity("Dental 359", "Dental 359 Subiaco") >= 0.9
    assert abn.similarity("Alford And Collins", "COLLINS & ALFORD") >= 0.9  # same partners, other order
    assert abn.similarity("Subiaco Dental", "Subiaco Medical") < 0.9
    assert abn.owner({"EntityName": "COLLINS & ALFORD", "EntityTypeName": "Family Partnership"}) == "COLLINS & ALFORD (partners' names aren't shown on ABN Lookup)"


def test_lookup_reads_jsonp_and_raises_abr_messages():
    class Client:
        def __init__(self, text):
            self.text = text

        def get(self, url, **_):
            assert "guid=key" in url
            return SimpleNamespace(text=self.text, raise_for_status=lambda: None)

    ok = abn.AbnLookup(Client('c({"Message":"","Names":[{"Abn":"1","Name":"X","IsCurrent":true}]})'), "key")
    assert ok.names("x") == [{"abn": "1", "name": "X", "iscurrent": True}]
    bad = abn.AbnLookup(Client('c({"Message":"The GUID entered is not recognised as a Registered Party","Names":[]})'), "key")
    with pytest.raises(abn.AbnError, match="GUID"):
        bad.names("x")


def test_sync_stops_when_the_key_is_refused(monkeypatch):
    def refuse(lookup, row, state):
        raise abn.AbnError("The GUID entered is not recognised as a Registered Party")

    monkeypatch.setattr(abn, "match", refuse)
    businesses = {k: {"key": k, "name": k, "status": "Listed"} for k in ("a", "b")}
    stats = abn.sync(config.load(), businesses, [], "bad-key")
    assert stats["result"].startswith("ABN Lookup didn't accept the key")
    assert stats["backlog"] == 2
