from bizbot.names import abns_in, names_from_file, valid_abn


def test_names_tom_wrote_into_file_names():
    assert names_from_file("Balance Sheet 2026 - N24 Impex Pty Ltd.pdf") == ["N24 Impex Pty Ltd"]
    assert names_from_file("Business Profile - Studio Pilates Applecross.pdf") == ["Studio Pilates Applecross"]
    assert names_from_file("Information Memorandum - Pilates Fit Perth Cockburn.pdf") == ["Pilates Fit Perth Cockburn"]
    assert names_from_file("V3 Core Focus Pilates Business Profile.pdf") == ["Core Focus Pilates"]


def test_unclear_file_names_suggest_nothing():
    for name in ["N24 Asset list.xlsx", "V4 IML Group IM FMA.pdf", "Communication", "scan_0012.pdf"]:
        assert names_from_file(name) == [], name


def test_brokers_and_addresses_are_not_the_business():
    assert names_from_file("IM - Gold Coast Business Brokers Pty Ltd.pdf") == []
    assert names_from_file("Lease - Shop 3, 30 Hammond Rd.pdf") == []


def test_abn_checksum():
    assert valid_abn("51824753556")
    assert not valid_abn("51824753557")
    assert not valid_abn("12345678901")


def test_abns_in_a_document_labelled_ones_first_each_once():
    text = "Call 0893811111. Ref 53 004 085 616.\nPilates Fit Pty Ltd ABN: 51 824 753 556\nABN 51824753556"
    assert abns_in(text) == ["51824753556", "53004085616"]
    assert abns_in("Invoice 12 345 678 901") == []


def test_capital_names_from_abn_lookup_read_normally():
    from bizbot.names import readable
    assert readable("VASSE VALLEY HEMP FARM PTY LTD") == "Vasse Valley Hemp Farm Pty Ltd"
    assert readable("N24 IMPEX PTY LTD") == "N24 Impex Pty Ltd"
    assert readable("Pilates Fit Perth") == "Pilates Fit Perth"
