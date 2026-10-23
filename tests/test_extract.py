from bizbot import extract


def test_money_reads_common_price_formats():
    assert extract.money("$95,000") == 95_000
    assert extract.money("$1,000,000 + SAV") == 1_000_000
    assert extract.money("$1.2m WIWO") == 1_200_000
    assert extract.money("$450k") == 450_000
    assert extract.money("$350,000 - $450,000") == 350_000
    assert extract.money("P.O.A") is None
    # A year typed straight after a dollar sign is not an amount.
    assert extract.money("$2026FY revenue approximately $550,000") == 550_000
    assert extract.price("625,000") == 625_000
    assert extract.price("$200K") == 200_000


def test_turnover_skips_words_and_annualises_weekly_takings():
    assert extract.turnover("Turnover: $Approximately $281,700 for FY2026") == 281_700
    assert extract.turnover("FY2026 sales of approximately $281,700") == 281_700
    assert extract.turnover("Averaging $51,415 a week, open 6 days") == 51_415 * 52
    assert extract.turnover("Monthly revenue $20,000 per month") == 240_000
    assert extract.turnover("Turnover: $2026FY revenue approximately $550,000 PA ex GST") == 550_000
    assert extract.turnover("Revenue approx. $400,000 last year") == 400_000
    assert extract.turnover("Turnover: $2026 – $329,300; 2025 – $317,900") == 329_300
    # An asking price after "sales" is not turnover.
    assert extract.turnover("Business sales: asking $300,000 + SAV") is None
    # An amount in a later clause belongs to something else.
    assert extract.turnover("All sales are cash, so there are no debtors, and $250,000 in orders") is None


def test_amount_written_before_its_keyword():
    text = "Established 23+ years, this salon delivers $13K weekly sales and ~$160K net profit, with 11 stations."
    assert extract.turnover(text) == 13_000 * 52
    assert extract.profit(text) == (160_000, "Net profit")
    assert extract.turnover("$1.2m annual turnover") == 1_200_000


def test_phone_numbers_found_once_each():
    text = "Call John on 0422 930 549 or 1300 366 521. Mobile: 0422930549. Office +61 8 9381 1111"
    assert extract.phones(text) == ["0422 930 549", "1300 366 521", "+61 8 9381 1111"]


def test_profit_and_type():
    assert extract.profit("EBITDA of $210,000 last year") == (210_000, "EBITDA")
    assert extract.profit("Adjusted net profit $95k") == (95_000, "Adjusted net profit")
    assert extract.profit("Net profit: $150,000 p.a.") == (150_000, "Net profit")
    assert extract.profit("A profitable cafe asking $120,000") == (None, "")
    assert extract.profit("Net Profit: $2026FY PEBITDA approximately $225,000 PA") == (225_000, "PEBITDA")


def test_established_price_basis_reasons_and_status():
    assert extract.established("Operating under current ownership since 2009") == "2009"
    assert extract.established("With 7 years of trading history") == "7+ years"
    assert extract.price_basis("$1,000,000 + SAV") == "+ stock (SAV)"
    assert extract.price_basis("$100,000 WIWO") == "Walk in walk out"
    assert extract.price_basis("P.O.A") == "Price on application"
    assert extract.sale_reasons("Owner is retiring after 20 years. Motivated seller.") == "Retirement, Motivated seller"
    assert extract.status("-- UNDER OFFER -- Cannington restaurant", "$50,000") == "Under offer"
    assert extract.status("Busy cafe", "$80,000") == "Active"


def test_perth_metro_and_notes():
    assert extract.perth_metro("6062", [(6000, 6199)]) == "Yes"
    assert extract.perth_metro("6230", [(6000, 6199)]) == "No"
    assert extract.perth_metro("", [(6000, 6199)]) == ""
    notes = extract.build_notes(
        dict(status="Active", category="Hair Salon", suburb="Morley", region="Perth Region WA", price_text="$95,000",
             price_aud=95_000, turnover_aud=281_700, profit_aud=50_000, profit_type="Net profit", established="2009",
             sale_reason="Retirement")
    )
    assert notes == (
        "Hair Salon in Morley, Perth Region WA. Asking $95,000. Turnover ~$281,700/yr. "
        "Net profit ~$50,000/yr. Price is 1.9x profit. Est. 2009. Selling because: Retirement."
    )
