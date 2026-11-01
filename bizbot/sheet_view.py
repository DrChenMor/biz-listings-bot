"""Makes the Google Sheet easy to use: tidy data tabs, and two search tabs with dropdowns.

Run with `python -m bizbot tidy-sheet`. It's safe to run again: it replaces its own formatting, and keeps
whatever is picked in the dropdowns. It only changes how tabs look, never the bots' data.

The search tabs ("Find a business", "Find a health practice") only read the data tabs, through formulas.
Those formulas use ranges that start at row 1 (A1:A), because the bots insert new rows at row 2 and a range
starting at row 2 would slide down and miss them.
"""
from gspread.utils import rowcol_to_a1

from .health import HEALTH, HEALTH_PAGES
from .seek import SEEK
from .sources.commercialrealestate import TABLE as CRE
from .store import CHANGE_COLUMNS, LISTINGS, RUN_COLUMNS, SKIPPED, Table

FIND_BUSINESS = "Find a business"
FIND_HEALTH = "Find a health practice"
FIND_DATA = "Find data"  # hidden: the three listing tabs joined into one list
LISTS = "Lists"  # hidden: what the dropdowns offer

HEADER_BLUE = "1F4E79"
PICK_YELLOW = "FFF2CC"
BAND_BLUE = "EAF1F8"
AMBER = "FCE4C4"
GREY = "E3E3E3"
GREEN = "D5EFD8"
TAB_FIND = "2E9E5B"
TAB_DATA = "1F4E79"
TAB_LOG = "A0A0A0"

# Dropdown choices. Each type of business is a pattern matched against a listing's industry and category.
# Sites file many businesses under broad headings ("Beauty and Health" holds hair salons and gyms), so those
# headings are removed first, and the patterns match the specific words that are left.
TYPE_NOISE = r"beauty and health|beauty, health & fitness|health, beauty & fitness >|personal services >|professional services|mobile services"
BUSINESS_TYPES = [
    ("All types", "."),
    ("Health and medical", r"medical|dental|dentist|doctor|physio|chiro|pharmac|psycholog|podiatr|optom|aged care|disability|health ?care|health services|\bnursing|allied|natural therap"),
    ("Beauty and hair", r"beauty|hair|barber|salon|nail|\bspa\b|massage|cosmetic|tann"),
    ("Fitness and sport", r"fitness|\bgym|pilates|yoga|\bsport|recreation"),
    ("Childcare and education", r"child|education|training|tutor|school|coaching"),
    ("Cleaning and home services", r"clean|lawn|garden|pest|\bpool|handym|mowing|nursery"),
    ("Trades and construction", r"building|construct|plumb|\btrade|roof|paint|concrete|civil|electrician"),
    ("Automotive and transport", r"\bauto|\bcars?\b|mechanic|truck|transport|courier|tyre|motor|detailing|marine|freight|petrol|smash|wrecker|bike"),
    ("Retail and shops", r"retail|\bshop|clothing|homeware|florist|gift|newsagen|furniture|hardware|post office"),
    ("Professional and finance", r"professional|account|bookkeep|finance|mortgage|insurance|legal|real estate|marketing|advertising|computer"),
    ("Manufacturing and wholesale", r"manufacturer|wholesale|import|distribut|industrial|machinery"),
    ("Pets and animals", r"\bpets?\b|animal|\bdog"),
    ("Accommodation and tourism", r"accommodation|tourism|motel|caravan|hotel|travel|guest house|bed and breakfast|hostel"),
    ("Online and work from home", r"online|website|work from home|working from home"),
    ("Farming and rural", r"agricultur|farm|rural|livestock|aquaculture"),
    ("Other services", r"printing|entertainment|\bhire\b|wedding"),
    ("Franchises", r"franchise"),
]
MAX_PRICES = [
    ("Any price", 0), ("Up to $100,000", 100_000), ("Up to $200,000", 200_000), ("Up to $300,000", 300_000),
    ("Up to $500,000", 500_000), ("Up to $750,000", 750_000), ("Up to $1,000,000", 1_000_000), ("Up to $2,000,000", 2_000_000),
]
AREAS = ["Perth only", "All of WA"]
SORTS = ["Newest first", "Cheapest first", "Highest profit"]
SECTORS = [
    "All types", "GP / medical centre", "Dental", "Pharmacy", "Allied health", "Mental health", "Medical specialist",
    "Optical & hearing", "Pathology & imaging", "Hospital / day surgery", "Complementary", "Community / support", "Other",
]
CONTACTS = ["Everyone", "Has an email", "Has a website"]

BOT_COLUMNS_NOTE = "The bots fill these columns. Add your own columns to the right instead."
SEARCH_TAB_NOTE = "This list fills itself. Change only the yellow boxes."

# How each tab looks. Columns not listed in `widths` are 120 wide.
_LISTING_LOOK = dict(
    hide=["Source", "Listing ID", "Last seen", "Site updated", "Fingerprint", "Key"],
    widths={"Status": 90, "Title": 340, "Notes": 420, "Category": 170, "Suburb": 130, "Postcode": 75, "Region": 170, "Perth metro": 70,
            "Asking price": 150, "Price (AUD)": 100, "Broker / seller": 190, "Broker phone": 130, "URL": 200, "Key features": 300, "Description": 400},
    money=["Price (AUD)", "Turnover (AUD/yr)", "Profit (AUD/yr)"],
    new_since="First seen",
)
DATA_TABS = [
    dict(table=LISTINGS, **_LISTING_LOOK),
    dict(table=CRE, **_LISTING_LOOK),
    dict(table=SEEK, hide=["Listing ID", "SEEK updated", "Last seen", "Key"],
         widths={"Status": 90, "Title": 340, "Asking price": 150, "Price (AUD)": 100, "Industry": 240, "Location": 220, "Advertiser": 200,
                 "Phones in listing": 150, "Summary": 420, "Description": 400, "URL": 200},
         money=["Price (AUD)", "Turnover (AUD/yr)", "Profit (AUD/yr)"], new_since="First seen"),
    dict(table=HEALTH,
         hide=["Latitude", "Longitude", "Last seen", "Details checked", "ABN checked", "healthdirect service IDs", "Organisation ID", "Location ID", "Key"],
         widths={"Status": 80, "Business name": 280, "Sector": 150, "Type": 130, "Main service": 180, "All services listed": 240, "Address": 240,
                 "Suburb": 120, "Postcode": 75, "Phone": 130, "Email": 220, "Website": 190, "Registered entity (ABN)": 200, "Owner name on ABN": 200,
                 "Practitioners": 200, "Map": 120, "healthdirect link": 150},
         money=[]),
]
LOG_TABS = [
    dict(table=Table("Changes", CHANGE_COLUMNS), widths={"When": 130, "Listing ID": 110, "Title": 320, "What changed": 130, "Old": 200, "New": 200, "URL": 200}),
    dict(table=Table("Runs", RUN_COLUMNS), widths={"Started": 130, "Result": 420}),
    dict(table=SKIPPED, widths={"Title": 320, "Reason": 320, "URL": 200, "Key": 150}),
]
HIDDEN_TABS = [HEALTH_PAGES.tab, "Busy", FIND_DATA, LISTS]
TAB_ORDER = [FIND_BUSINESS, FIND_HEALTH, LISTINGS.tab, CRE.tab, SEEK.tab, HEALTH.tab, "Changes", "Runs", SKIPPED.tab]


def tidy(book) -> None:
    """Build the search tabs and restyle every tab. `book` is a gspread Spreadsheet."""
    lists = _ensure_tab(book, LISTS, 1000, 12)
    find_data = _ensure_tab(book, FIND_DATA, 5000, 16)
    business = _ensure_tab(book, FIND_BUSINESS, 5000, 14)
    health = _ensure_tab(book, FIND_HEALTH, 10000, 13)
    _write_lists(lists)
    find_data.update(values=[[_find_data_formula(), *[""] * 14, _search_text_formula()]], range_name="A1", value_input_option="USER_ENTERED")
    _write_find_business(business)
    _write_find_health(health)

    sheets = book.fetch_sheet_metadata({
        "includeGridData": "false",
        "fields": "sheets(properties(title,sheetId,gridProperties),bandedRanges(bandedRangeId),conditionalFormats,protectedRanges(protectedRangeId,description),merges)",
    })["sheets"]
    by_title = {s["properties"]["title"]: s for s in sheets}
    requests = []
    for sheet in sheets:
        requests += _clear_styling(sheet)
    for spec in DATA_TABS:
        requests += _table_style(by_title[spec["table"].tab], spec, data_tab=True)
    for spec in LOG_TABS:
        requests += _table_style(by_title[spec["table"].tab], spec, data_tab=False)
    requests += _find_business_style(by_title[FIND_BUSINESS]) + _find_health_style(by_title[FIND_HEALTH])
    requests += _tab_arrangement(by_title)
    book.batch_update({"requests": requests})


def _ensure_tab(book, title: str, rows: int, cols: int):
    existing = {ws.title: ws for ws in book.worksheets()}
    return existing.get(title) or book.add_worksheet(title, rows=rows, cols=cols)


def _col(table: Table, header: str) -> str:
    """A whole column of a tab, from row 1 so that new rows at row 2 are never missed."""
    letter = rowcol_to_a1(1, table.headers.index(header) + 1)[:-1]
    return f"'{table.tab}'!{letter}1:{letter}"


# --- The hidden tabs ------------------------------------------------------------------------------------------------

def _write_lists(ws) -> None:
    columns = {
        "A": ["Type of business"] + [name for name, _ in BUSINESS_TYPES],
        "B": ["Pattern"] + [pattern for _, pattern in BUSINESS_TYPES],
        "D": ["Max price"] + [label for label, _ in MAX_PRICES],
        "E": ["Value"] + [value for _, value in MAX_PRICES],
        "G": ["Sort"] + SORTS,
        "H": ["Area"] + AREAS,
        "I": ["Sector"] + SECTORS,
        "J": ["Contact"] + CONTACTS,
    }
    for column, values in columns.items():
        ws.update(values=[[v] for v in values], range_name=f"{column}1", value_input_option="RAW")
    suburb = _col(HEALTH, "Suburb")
    suburbs = f'={{"Suburb";"All suburbs";SORT(UNIQUE(FILTER({suburb},{suburb}<>"",{suburb}<>"Suburb")))}}'
    ws.update(values=[[suburbs]], range_name="L1", value_input_option="USER_ENTERED")


def _listing_rows(table: Table, site: str, where: str, perth: str, kind: str, summary: str, broker: str, phone: str) -> str:
    """One tab's listings as the columns of Find data, leaving out empty rows and the header row."""
    title, asking, price = _col(table, "Title"), _col(table, "Asking price"), _col(table, "Price (AUD)")
    turnover, profit = _col(table, "Turnover (AUD/yr)"), _col(table, "Profit (AUD/yr)")
    columns = [
        # bsale's price box says SOLD on many listings whose own title says Under Offer.
        _col(table, "Status"), title, f'IF(UPPER({asking})="SOLD","Not shown",{asking})',
        # SEEK uses a price of $1 for "price on application".
        f'IF(ISNUMBER({price})*({price}>1),{price},"")', turnover,
        # A profit as high as the turnover can't be right: the reader took a sales figure for it.
        f'IF(ISNUMBER({turnover})*ISNUMBER({profit})*({profit}>={turnover}),"",{profit})',
        where, perth, f'REGEXREPLACE(LOWER({kind}),"{TYPE_NOISE}","")',
        _col(table, summary), _col(table, broker), _col(table, phone), _col(table, "URL"),
        f'IFERROR(DATEVALUE(LEFT({_col(table, "First seen")},10)))', f'IF({title}<>"","{site}","")',
    ]
    return "FILTER({" + ",".join(columns) + f'}},{title}<>"",{title}<>"Title")'


def _broker_site_rows(table: Table, site: str) -> str:
    suburb, region, metro = _col(table, "Suburb"), _col(table, "Region"), _col(table, "Perth metro")
    return _listing_rows(
        table, site,
        where=f'IF({suburb}<>"",{suburb},{region})',
        # Perth if flagged so, or if the flag is empty and the listing's region says Perth.
        perth=f'REGEXMATCH(LOWER({metro}&"|"&{region}),"^yes|^\\|.*perth")',
        kind=f'{_col(table, "Industry")}&" "&{_col(table, "Category")}',
        summary="Notes", broker="Broker / seller", phone="Broker phone",
    )


def _find_data_formula() -> str:
    """Columns: A status, B title, C asking price, D price, E turnover, F profit, G where, H Perth?, I type,
    J summary, K broker, L phone, M link, N date added, O site."""
    seek = _listing_rows(
        SEEK, "SEEK",
        where=_col(SEEK, "Location"),
        perth=f'{_col(SEEK, "Title")}<>""',  # the SEEK search only covers 50 km around Perth
        kind=f'{_col(SEEK, "Industry")}&" "&{_col(SEEK, "Type")}',
        summary="Summary", broker="Advertiser", phone="Phones in listing",
    )
    return f'=ARRAYFORMULA({{{_broker_site_rows(LISTINGS, "bsale")};{_broker_site_rows(CRE, "commercialrealestate")};{seek}}})'


def _search_text_formula() -> str:
    return '=ARRAYFORMULA(IF(B1:B="","",B1:B&" "&G1:G&" "&I1:I&" "&J1:J&" "&K1:K))'


# --- The search tabs ------------------------------------------------------------------------------------------------

def _keep_or(existing: list, index: int, default: str) -> str:
    return existing[index] if index < len(existing) and existing[index] else default


def _business_results() -> str:
    d = f"'{FIND_DATA}'!"
    # Result columns: 1 status, 2 title, 3 asking price, 4 turnover, 5 profit, 6 where, 7 summary, 8 broker, 9 phone,
    # 10 date added, 11 site, 12 sort order (hidden), 13 link (hidden). The sort order is always a number, smallest
    # first: an empty price or profit in Find data is text, which a plain sort would put on top.
    sort_order = (
        f'IF($D$5="Cheapest first",IF(ISNUMBER({d}D1:D),{d}D1:D,1E+12),'
        f'IF($D$5="Highest profit",IF(ISNUMBER({d}F1:F),-{d}F1:F,1),IFERROR(-{d}N1:N,0)))'
    )
    show = ",".join([*(f"{d}{c}1:{c}" for c in "ABCEFGJKLNO"), sort_order, f"{d}M1:M"])
    keep = ",".join([
        f'{d}B1:B<>""',
        f'{d}A1:A<>"Removed"',
        f'IF($A$5="Perth only",{d}H1:H,{d}B1:B<>"")',
        f"REGEXMATCH({d}I1:I,VLOOKUP($B$5,{LISTS}!$A:$B,2,FALSE))",
        f'IF($L$5=0,{d}B1:B<>"",({d}D1:D>0)*({d}D1:D<=$L$5))',
        f"ISNUMBER(SEARCH($F$5,{d}P1:P))",
    ])
    return f'=ARRAYFORMULA(IFERROR(SORT(FILTER({{{show}}},{keep}),12,TRUE),"No businesses match. Try fewer filters."))'


def _write_find_business(ws) -> None:
    picked = (ws.get_values("A5:F5") or [[]])[0]
    ws.update(
        values=[
            ["Find a business for sale"],
            ["Pick from the yellow boxes and the list updates by itself. Green date = added this week. Orange = under offer. "
             "With a price limit, listings that show no price are left out."],
            [""],
            ["Where", "Type of business", "Most you'd pay", "Sort by", "", "Search any word (suburb, broker, \"dental\"...)", "", "Businesses found"],
            [_keep_or(picked, 0, "Perth only"), _keep_or(picked, 1, "All types"), _keep_or(picked, 2, "Any price"), _keep_or(picked, 3, "Newest first"), "",
             _keep_or(picked, 5, ""), "", "=COUNTA(B8:B)"],
            [""],
            ["Status", "Business", "Asking price", "Turnover /yr", "Profit /yr", "Where", "What the listing says", "Broker", "Phone", "Added", "Found on", "", "", "Listing"],
            [_business_results()],
        ],
        range_name="A1",
        value_input_option="USER_ENTERED",
    )
    ws.update(values=[[f"=VLOOKUP($C$5,{LISTS}!$D:$E,2,FALSE)"]], range_name="L5", value_input_option="USER_ENTERED")
    ws.update(values=[['=ARRAYFORMULA(IF(LEN(M8:M),HYPERLINK(M8:M,"Open"),""))']], range_name="N8", value_input_option="USER_ENTERED")


def _health_results() -> str:
    def h(header: str) -> str:
        return _col(HEALTH, header)

    # Result columns 10 and 11 are the links, shown as short "Map" and "Open" links beside the list.
    show = ",".join(h(header) for header in [
        "Business name", "Sector", "Main service", "Suburb", "Phone", "Email", "Website", "Address", "Owner name on ABN", "Map", "healthdirect link",
    ])
    name, status = h("Business name"), h("Status")
    words = '&" "&'.join(h(header) for header in ["Business name", "All services listed", "Address", "Suburb", "Postcode", "Practitioners"])
    keep = ",".join([
        f'{name}<>""',
        f'{name}<>"Business name"',
        f'{status}<>"Not seen recently"',
        f'(($A$5="All types")+({h("Sector")}=$A$5))>0',
        f'(($B$5="All suburbs")+({h("Suburb")}=$B$5))>0',
        f'IF($D$5="Has an email",{h("Email")}<>"",IF($D$5="Has a website",{h("Website")}<>"",{name}<>""))',
        f"ISNUMBER(SEARCH($F$5,{words}))",
    ])
    return f'=IFERROR(SORT(FILTER({{{show}}},{keep}),4,TRUE,1,TRUE),"No practices match. Try fewer filters.")'


def _write_find_health(ws) -> None:
    picked = (ws.get_values("A5:F5") or [[]])[0]
    ws.update(
        values=[
            ["Find a health practice"],
            ["Pick from the yellow boxes and the list updates by itself. Sorted by suburb. Phone, email and website show when the practice lists them."],
            [""],
            ["Type of practice", "Suburb", "", "Show", "", "Search any word (name, street, \"podiatry\"...)", "", "Practices found"],
            [_keep_or(picked, 0, "Pharmacy"), _keep_or(picked, 1, "All suburbs"), "", _keep_or(picked, 3, "Everyone"), "", _keep_or(picked, 5, ""), "", "=COUNTA(B8:B)"],
            [""],
            ["Practice", "Type", "Main service", "Suburb", "Phone", "Email", "Website", "Address", "Owner", "", "", "Map", "healthdirect"],
            [_health_results()],
        ],
        range_name="A1",
        value_input_option="USER_ENTERED",
    )
    ws.update(
        values=[['=ARRAYFORMULA(IF(LEN(J8:J),HYPERLINK(J8:J,"Map"),""))', '=ARRAYFORMULA(IF(LEN(K8:K),HYPERLINK(K8:K,"Open"),""))']],
        range_name="L8",
        value_input_option="USER_ENTERED",
    )


# --- Styling requests -----------------------------------------------------------------------------------------------

def _rgb(hex_colour: str) -> dict:
    return {key: int(hex_colour[i:i + 2], 16) / 255 for key, i in (("red", 0), ("green", 2), ("blue", 4))}


def _clear_styling(sheet: dict) -> list:
    sheet_id = sheet["properties"]["sheetId"]
    requests = [{"deleteBanding": {"bandedRangeId": b["bandedRangeId"]}} for b in sheet.get("bandedRanges", [])]
    requests += [{"deleteConditionalFormatRule": {"sheetId": sheet_id, "index": 0}} for _ in sheet.get("conditionalFormats", [])]
    requests += [{"deleteProtectedRange": {"protectedRangeId": p["protectedRangeId"]}} for p in sheet.get("protectedRanges", [])
                 if p.get("description") in (BOT_COLUMNS_NOTE, SEARCH_TAB_NOTE)]
    requests += [{"unmergeCells": {"range": m}} for m in sheet.get("merges", [])]
    return requests


def _repeat(sheet_id: int, fmt: dict, fields: str, r0=0, r1=None, c0=0, c1=None) -> dict:
    grid = {"sheetId": sheet_id, "startRowIndex": r0, "startColumnIndex": c0}
    if r1 is not None:
        grid["endRowIndex"] = r1
    if c1 is not None:
        grid["endColumnIndex"] = c1
    return {"repeatCell": {"range": grid, "cell": {"userEnteredFormat": fmt}, "fields": fields}}


def _header(sheet_id: int, cols: int, row: int = 0) -> dict:
    fmt = {"backgroundColor": _rgb(HEADER_BLUE), "verticalAlignment": "MIDDLE", "wrapStrategy": "WRAP",
           "textFormat": {"foregroundColor": _rgb("FFFFFF"), "bold": True}}
    return _repeat(sheet_id, fmt, "userEnteredFormat(backgroundColor,verticalAlignment,wrapStrategy,textFormat)", row, row + 1, 0, cols)


def _column_width(sheet_id: int, col: int, pixels: int) -> dict:
    return {"updateDimensionProperties": {"range": {"sheetId": sheet_id, "dimension": "COLUMNS", "startIndex": col, "endIndex": col + 1},
                                          "properties": {"pixelSize": pixels}, "fields": "pixelSize"}}


def _column_hidden(sheet_id: int, col: int, hidden: bool) -> dict:
    return {"updateDimensionProperties": {"range": {"sheetId": sheet_id, "dimension": "COLUMNS", "startIndex": col, "endIndex": col + 1},
                                          "properties": {"hiddenByUser": hidden}, "fields": "hiddenByUser"}}


def _rows_height(sheet_id: int, start: int, end: int, pixels: int) -> dict:
    return {"updateDimensionProperties": {"range": {"sheetId": sheet_id, "dimension": "ROWS", "startIndex": start, "endIndex": end},
                                          "properties": {"pixelSize": pixels}, "fields": "pixelSize"}}


def _colour_rule(sheet_id: int, col: int, condition: dict, colour: str, row: int) -> dict:
    return {"addConditionalFormatRule": {"index": 0, "rule": {
        "ranges": [{"sheetId": sheet_id, "startRowIndex": row, "startColumnIndex": col, "endColumnIndex": col + 1}],
        "booleanRule": {"condition": condition, "format": {"backgroundColor": _rgb(colour)}},
    }}}


def _when_cell_says(sheet_id: int, col: int, values: list[str], colour: str, row: int) -> list:
    return [_colour_rule(sheet_id, col, {"type": "TEXT_EQ", "values": [{"userEnteredValue": value}]}, colour, row) for value in values]


def _bands(sheet_id: int, cols: int, row: int, header: bool = False) -> dict:
    colours = {"firstBandColor": _rgb("FFFFFF"), "secondBandColor": _rgb(BAND_BLUE)}
    if header:  # banding paints over the cells' own colour, so it has to know the header's
        colours["headerColor"] = _rgb(HEADER_BLUE)
    return {"addBanding": {"bandedRange": {
        "range": {"sheetId": sheet_id, "startRowIndex": row, "startColumnIndex": 0, "endColumnIndex": cols},
        "rowProperties": colours,
    }}}


def _table_style(sheet: dict, spec: dict, data_tab: bool) -> list:
    """A data or log tab. Bands and colour rules start at row 1, so rows the bots insert at row 2 fall inside them."""
    sheet_id = sheet["properties"]["sheetId"]
    rows = sheet["properties"]["gridProperties"]["rowCount"]
    headers = spec["table"].headers
    cols = len(headers)
    requests = [
        _header(sheet_id, cols),
        _rows_height(sheet_id, 0, 1, 36),
        _bands(sheet_id, cols, 0, header=True),
        {"setBasicFilter": {"filter": {"range": {"sheetId": sheet_id}}}},
        # One line per row: long text stays in its cell (click the cell to read it all).
        _repeat(sheet_id, {"wrapStrategy": "CLIP", "verticalAlignment": "MIDDLE"}, "userEnteredFormat(wrapStrategy,verticalAlignment)", 1),
    ]
    for i, header in enumerate(headers):
        requests.append(_column_width(sheet_id, i, spec["widths"].get(header, 120)))
    if not data_tab:
        return requests

    requests.append(_rows_height(sheet_id, 1, rows, 26))
    for i, header in enumerate(headers):
        requests.append(_column_hidden(sheet_id, i, header in spec["hide"]))
        if header in spec["money"]:
            fmt = {"numberFormat": {"type": "CURRENCY", "pattern": '"$"#,##0'}}
            requests.append(_repeat(sheet_id, fmt, "userEnteredFormat.numberFormat", 1, None, i, i + 1))
    requests += _when_cell_says(sheet_id, 0, ["Under offer"], AMBER, 0) + _when_cell_says(sheet_id, 0, ["Removed", "Not seen recently"], GREY, 0)
    if "new_since" in spec:
        letter = rowcol_to_a1(1, headers.index(spec["new_since"]) + 1)[:-1]
        new_this_week = f"=IFERROR(DATEVALUE(LEFT(${letter}1,10))>=TODAY()-7,FALSE)"
        requests.append(_colour_rule(sheet_id, 1, {"type": "CUSTOM_FORMULA", "values": [{"userEnteredValue": new_this_week}]}, GREEN, 0))
    # A warning, not a block: it stops accidental typing over the bots' columns. The bots aren't affected.
    requests.append({"addProtectedRange": {"protectedRange": {
        "range": {"sheetId": sheet_id, "startColumnIndex": 0, "endColumnIndex": cols},
        "description": BOT_COLUMNS_NOTE,
        "warningOnly": True,
    }}})
    return requests


def _search_tab_style(sheet: dict, cols: int, widths: list[int], merges: list[tuple[int, int]], picks: list[tuple[int, int]], hidden: list[int]) -> list:
    """What both search tabs share. merges and picks are (first column, one past the last column) on rows 4 and 5."""
    sheet_id = sheet["properties"]["sheetId"]
    requests = [
        {"updateSheetProperties": {"properties": {"sheetId": sheet_id, "gridProperties": {"frozenRowCount": 7}}, "fields": "gridProperties.frozenRowCount"}},
        _repeat(sheet_id, {"textFormat": {"fontSize": 16, "bold": True, "foregroundColor": _rgb(HEADER_BLUE)}}, "userEnteredFormat.textFormat", 0, 1, 0, 1),
        _repeat(sheet_id, {"textFormat": {"foregroundColor": _rgb("555555")}}, "userEnteredFormat.textFormat", 1, 2, 0, 1),
        _repeat(sheet_id, {"textFormat": {"bold": True}, "wrapStrategy": "CLIP"}, "userEnteredFormat(textFormat,wrapStrategy)", 3, 4, 0, cols),
        _header(sheet_id, cols, row=6),
        _rows_height(sheet_id, 6, 7, 32),
        _rows_height(sheet_id, 4, 5, 34),
        _bands(sheet_id, cols, 7),
        _repeat(sheet_id, {"wrapStrategy": "CLIP", "verticalAlignment": "MIDDLE"}, "userEnteredFormat(wrapStrategy,verticalAlignment)", 7),
    ]
    for start, end in merges:
        for row in (3, 4):
            requests.append({"mergeCells": {"mergeType": "MERGE_ALL", "range": {"sheetId": sheet_id, "startRowIndex": row, "endRowIndex": row + 1, "startColumnIndex": start, "endColumnIndex": end}}})
    border = {"style": "SOLID", "color": _rgb("BF9000")}
    unprotected = []
    for start, end in picks:
        fmt = {"backgroundColor": _rgb(PICK_YELLOW), "verticalAlignment": "MIDDLE", "textFormat": {"fontSize": 11, "bold": True}}
        requests.append(_repeat(sheet_id, fmt, "userEnteredFormat(backgroundColor,verticalAlignment,textFormat)", 4, 5, start, end))
        box = {"sheetId": sheet_id, "startRowIndex": 4, "endRowIndex": 5, "startColumnIndex": start, "endColumnIndex": end}
        requests.append({"updateBorders": {"range": box, "top": border, "bottom": border, "left": border, "right": border}})
        unprotected.append(box)
    for i, width in enumerate(widths):
        requests.append(_column_width(sheet_id, i, width))
    for i in range(cols):
        requests.append(_column_hidden(sheet_id, i, i in hidden))
    requests.append({"addProtectedRange": {"protectedRange": {
        "range": {"sheetId": sheet_id},
        "unprotectedRanges": unprotected,
        "description": SEARCH_TAB_NOTE,
        "warningOnly": True,
    }}})
    return requests


def _dropdown(sheet_id: int, column: int, source: str) -> dict:
    rule = {"condition": {"type": "ONE_OF_RANGE", "values": [{"userEnteredValue": source}]}, "showCustomUi": True, "strict": True}
    return {"setDataValidation": {"range": {"sheetId": sheet_id, "startRowIndex": 4, "endRowIndex": 5, "startColumnIndex": column, "endColumnIndex": column + 1}, "rule": rule}}


def _big_count(sheet_id: int) -> dict:
    return _repeat(sheet_id, {"textFormat": {"bold": True, "fontSize": 13}, "horizontalAlignment": "LEFT"}, "userEnteredFormat(textFormat,horizontalAlignment)", 4, 5, 7, 8)


def _find_business_style(sheet: dict) -> list:
    sheet_id = sheet["properties"]["sheetId"]
    requests = _search_tab_style(
        sheet, cols=14,
        widths=[100, 330, 160, 95, 95, 180, 420, 200, 125, 90, 130, 100, 100, 70],
        merges=[(3, 5), (5, 7)],
        picks=[(0, 1), (1, 2), (2, 3), (3, 5), (5, 7)],
        hidden=[11, 12],
    )
    new_this_week = {"type": "CUSTOM_FORMULA", "values": [{"userEnteredValue": "=AND(ISNUMBER($J8),$J8>=TODAY()-7)"}]}
    return requests + [
        _dropdown(sheet_id, 0, f"={LISTS}!$H$2:$H${1 + len(AREAS)}"),
        _dropdown(sheet_id, 1, f"={LISTS}!$A$2:$A${1 + len(BUSINESS_TYPES)}"),
        _dropdown(sheet_id, 2, f"={LISTS}!$D$2:$D${1 + len(MAX_PRICES)}"),
        _dropdown(sheet_id, 3, f"={LISTS}!$G$2:$G${1 + len(SORTS)}"),
        _repeat(sheet_id, {"numberFormat": {"type": "CURRENCY", "pattern": '"$"#,##0'}}, "userEnteredFormat.numberFormat", 7, None, 3, 5),
        _repeat(sheet_id, {"numberFormat": {"type": "DATE", "pattern": "d mmm yyyy"}}, "userEnteredFormat.numberFormat", 7, None, 9, 10),
        _big_count(sheet_id),
        _colour_rule(sheet_id, 9, new_this_week, GREEN, 7),
        *_when_cell_says(sheet_id, 0, ["Under offer"], AMBER, 7),
    ]


def _find_health_style(sheet: dict) -> list:
    sheet_id = sheet["properties"]["sheetId"]
    requests = _search_tab_style(
        sheet, cols=13,
        widths=[290, 160, 170, 130, 130, 230, 190, 260, 200, 100, 100, 60, 100],
        merges=[(1, 3), (3, 5), (5, 7)],
        picks=[(0, 1), (1, 3), (3, 5), (5, 7)],
        hidden=[9, 10],
    )
    return requests + [
        _dropdown(sheet_id, 0, f"={LISTS}!$I$2:$I${1 + len(SECTORS)}"),
        _dropdown(sheet_id, 1, f"={LISTS}!$L$2:$L$1000"),
        _dropdown(sheet_id, 3, f"={LISTS}!$J$2:$J${1 + len(CONTACTS)}"),
        _big_count(sheet_id),
    ]


def _tab_arrangement(by_title: dict) -> list:
    requests = []
    for index, title in enumerate(TAB_ORDER):
        colour = TAB_FIND if title in (FIND_BUSINESS, FIND_HEALTH) else (TAB_LOG if title in ("Changes", "Runs", SKIPPED.tab) else TAB_DATA)
        requests.append({"updateSheetProperties": {
            "properties": {"sheetId": by_title[title]["properties"]["sheetId"], "index": index, "hidden": False,
                           "tabColorStyle": {"rgbColor": _rgb(colour)}},
            "fields": "index,hidden,tabColorStyle",
        }})
    for title in HIDDEN_TABS:
        if title in by_title:
            requests.append({"updateSheetProperties": {
                "properties": {"sheetId": by_title[title]["properties"]["sheetId"], "hidden": True}, "fields": "hidden"}})
    return requests
