"""Rule-based reading of listing text: prices, turnover, profit, age, reason for sale, and a short note.

No AI here on purpose: plain patterns cost nothing to run. Anything they miss stays readable
in the Key features and Description columns.
"""
import re

_NUMBER = r"(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
# The lookahead stops "$2026FY" (a year typed after a dollar sign) from reading as $2,026.
_MONEY = re.compile(r"\$\s?" + _NUMBER + r"(?:\s?(k|m|mil|million)\b)?(?![A-Za-z0-9])", re.I)
_BARE_PRICE = re.compile(r"^\s*(\d{1,3}(?:,\d{3})+|\d{4,})\b")
_YEAR = re.compile(r"(?:19|20)\d{2}")
_PER_WEEK = re.compile(r"^\s*(?:(?:per|a|/|p\.?)\s*(?:week|wk)\b|pw\b|p/w\b|weekly\b)", re.I)
_PER_MONTH = re.compile(r"^\s*(?:(?:per|a|/|p\.?)\s*(?:month|mth)\b|pm\b|p/m\b|monthly\b)", re.I)
# Words between a keyword and an amount that mean the amount is the asking price, not turnover or profit.
_PRICE_WORDS = re.compile(r"asking|price|priced|offers|\bsav\b|stock|rent|lease", re.I)

_TURNOVER_WORDS = r"turnover|revenue|gross sales|annual sales|sales|takings"
_PROFIT_WORDS = r"adjusted net profit|net profit|ebitda|ebit|profit|net income|sde|owner'?s? (?:earnings|benefit|income|return)|return to (?:the )?owners?"
_TURNOVER = re.compile(rf"\b(?:{_TURNOVER_WORDS}|averaging)\b", re.I)
_PROFIT = re.compile(rf"\b(?:{_PROFIT_WORDS})\b", re.I)
# Words allowed between an amount and its keyword, as in "$13K weekly sales" or "~$160K net profit".
_LEAD_IN = r"^\s*((?:(?:weekly|per week|a week|monthly|per month|annual|yearly|approx\.?|approximately|in|of)\s+)*)(?:net\s+)?(?:{words})\b"
_PHONE = re.compile(r"(?:\+?61\s?|\b0)[2-478](?:[ -]?\d){8}\b|\b1[38]00(?:[ -]?\d){6}\b|\b13(?:[ -]?\d){4}\b")
_PROFIT_TYPES = [
    ("adjusted", "Adjusted net profit"),
    ("pebitda", "PEBITDA"),
    ("ebitda", "EBITDA"),
    ("ebit", "EBIT"),
    ("owner", "Owner earnings"),
    ("return", "Owner earnings"),
    ("sde", "Owner earnings"),
]

_ESTABLISHED_YEAR = re.compile(
    r"\b(?:since|established(?: in)?|est\.?|founded(?: in)?|trading since|operating since)\s*(?:in\s+)?((?:19|20)\d{2})\b",
    re.I,
)
_YEARS_TRADING = re.compile(
    r"\b(\d{1,2})\+?\s*years?\s+(?:of\s+)?(?:trading|operation|operating|history|established|in business)\b", re.I
)

_PRICE_BASIS = [
    (r"\+\s*s\.?a\.?v\.?|plus\s+(?:stock|sav)", "+ stock (SAV)"),
    (r"\bwiwo\b|walk[\s-]*in[\s,-]*walk[\s-]*out", "Walk in walk out"),
    (r"\binc(?:l|luding)?\.?\s*(?:stock|sav)", "Incl. stock"),
    (r"\+\s*gst|plus gst", "+ GST"),
    (r"\bneg(?:otiable)?\b|\bo\.?n\.?o\.?\b|\boffers?\b", "Negotiable / offers"),
    (r"\bp\.?o\.?a\.?\b|contact|enquire|on application", "Price on application"),
]

_SALE_REASONS = [
    (r"\bretir", "Retirement"),
    (r"relocat|moving (?:interstate|overseas|away)|leaving (?:wa|perth|the state)", "Relocation"),
    (r"health reasons|ill[- ]health", "Health"),
    (r"other (?:business )?(?:interests|commitments|ventures|projects)|focus on (?:other|another)", "Other commitments"),
    (r"family reasons|family commitments", "Family"),
    (r"motivated|urgent sale|must (?:be )?sell|quick sale|priced to sell", "Motivated seller"),
    (r"deceased estate|estate sale", "Estate sale"),
]


def money(text: str) -> int | None:
    """First dollar amount in the text, e.g. "$1.2m + SAV" -> 1200000."""
    match = _MONEY.search(text or "")
    return _amount(match) if match else None


def price(price_text: str) -> int | None:
    """Asking price as a number. Also accepts a bare "625,000" with no dollar sign."""
    value = money(price_text)
    if value is None and (match := _BARE_PRICE.match(price_text or "")):
        value = int(match.group(1).replace(",", ""))
    return value


def turnover(text: str) -> int | None:
    value, _ = _amount_before(_TURNOVER_WORDS, text)
    if value is None:
        value, _ = _amount_after(_TURNOVER, text)
    return value


def profit(text: str) -> tuple[int | None, str]:
    value, wording = _amount_before(_PROFIT_WORDS, text)
    if value is None:
        value, wording = _amount_after(_PROFIT, text)
    if value is None:
        return None, ""
    wording = wording.lower()
    label = next((name for word, name in _PROFIT_TYPES if word in wording), "Net profit")
    return value, label


def established(text: str) -> str:
    match = _ESTABLISHED_YEAR.search(text or "")
    if match:
        return match.group(1)
    match = _YEARS_TRADING.search(text or "")
    return f"{match.group(1)}+ years" if match else ""


def price_basis(price_text: str) -> str:
    return ", ".join(label for pattern, label in _PRICE_BASIS if re.search(pattern, price_text or "", re.I))


def sale_reasons(text: str) -> str:
    return ", ".join(label for pattern, label in _SALE_REASONS if re.search(pattern, text or "", re.I))


def status(title: str, price_text: str) -> str:
    text = f"{title} {price_text}".lower()
    if "under offer" in text or "under contract" in text:
        return "Under offer"
    # Only a price or title that says the business itself is sold ("SOLD", "Sold - Cafe ...", "Legal Practice -
    # Sold! Another Wanted"), not one that mentions selling ("first 10 locations sold", "must be sold").
    title = title or ""
    if (
        re.match(r"^\W*sold\b", price_text or "", re.I)
        or re.match(r"^\W*sold\b", title, re.I)
        or re.search(r"[-–|(\[]\s*sold\b", title, re.I)
        or re.search(r"\bsold\W+another\s+wanted", f"{title} {price_text}", re.I)
    ):
        return "Sold"
    return "Active"


def perth_metro(postcode: str, ranges: list[tuple[int, int]]) -> str:
    if not postcode.isdigit():
        return ""
    return "Yes" if any(low <= int(postcode) <= high for low, high in ranges) else "No"


def build_notes(listing: dict) -> str:
    """One-line summary built from the extracted fields."""
    parts = []
    if listing.get("status") not in (None, "", "Active"):
        parts.append(f"[{listing['status']}]")
    what = listing.get("category") or listing.get("industry") or "Business"
    where = ", ".join(x for x in (listing.get("suburb"), listing.get("region")) if x)
    parts.append(f"{what} in {where}." if where else f"{what}.")
    if listing.get("price_text"):
        parts.append(f"Asking {listing['price_text']}.")
    if listing.get("turnover_aud"):
        parts.append(f"Turnover ~${listing['turnover_aud']:,}/yr.")
    if listing.get("profit_aud"):
        parts.append(f"{listing.get('profit_type') or 'Profit'} ~${listing['profit_aud']:,}/yr.")
        if listing.get("price_aud"):
            parts.append(f"Price is {listing['price_aud'] / listing['profit_aud']:.1f}x profit.")
    if listing.get("established"):
        parts.append(f"Est. {listing['established']}.")
    if listing.get("sale_reason"):
        parts.append(f"Selling because: {listing['sale_reason']}.")
    return " ".join(parts)


def _amount(match: re.Match) -> int:
    value = float(match.group(1).replace(",", ""))
    suffix = (match.group(2) or "").lower()
    if suffix == "k":
        value *= 1_000
    elif suffix:
        value *= 1_000_000
    return int(round(value))


def phones(text: str) -> list[str]:
    """Australian phone numbers written in the text (usually the broker's), each once."""
    found, seen = [], set()
    for number in _PHONE.findall(text or ""):
        digits = re.sub(r"\D", "", number)
        digits = "0" + digits[2:] if digits.startswith("61") else digits
        if digits not in seen:
            seen.add(digits)
            found.append(number.strip())
    return found


def _amount_before(words: str, text: str) -> tuple[int | None, str]:
    """An amount followed by its keyword: "$13K weekly sales" (yearly: x52), "~$160K net profit"."""
    lead_in = re.compile(_LEAD_IN.format(words=words), re.I)
    for match in _MONEY.finditer(text or ""):
        if _YEAR.fullmatch(match.group(1)) and not match.group(2):
            continue
        hit = lead_in.match(text[match.end(): match.end() + 40])
        if not hit:
            continue
        value = _amount(match)
        if "week" in hit.group(1).lower():
            value *= 52
        elif "month" in hit.group(1).lower():
            value *= 12
        if value >= 1_000:
            return value, hit.group(0)
    return None, ""


def _amount_after(keyword: re.Pattern, text: str, window: int = 80) -> tuple[int | None, str]:
    """Yearly amount that follows a keyword in the same clause, e.g. "Turnover: approx $281,700".

    Returns the amount and the wording from the keyword up to the amount.
    """
    for found in keyword.finditer(text or ""):
        tail = text[found.end(): found.end() + window].split("\n")[0]
        # Skip years written like money, as in "Turnover: $2026 – $329,300".
        match = next((m for m in _MONEY.finditer(tail) if not _YEAR.fullmatch(m.group(0).lstrip("$ "))), None)
        if not match:
            continue
        between = tail[: match.start()]
        # A comma or a new sentence in between usually means the amount belongs to something else,
        # e.g. "sales are cash, so there are no debtors, and $250,000 in forward orders".
        if _PRICE_WORDS.search(between) or re.search(r"[,;]\s|\.\s+(?=[A-Z])", between):
            continue
        value = _amount(match)
        after = tail[match.end():]
        if _PER_WEEK.search(after):
            value *= 52
        elif _PER_MONTH.search(after):
            value *= 12
        if value >= 1_000:
            return value, found.group(0) + between
    return None, ""
