"""Fills a listing site's enquiry form in a visible browser window.

A plain form is sent here. A form behind a CAPTCHA or a sum is filled, then left for a person to finish in the same
window: the agent never answers one. A security check on the page stops the enquiry. In test mode forms are filled and
nothing is sent. Marketing and "similar businesses" boxes are left unticked.
"""
import logging
import re
import time
from dataclasses import dataclass

log = logging.getLogger(__name__)

SITES = {"bsale", "business2sell", "AnyBusiness", "businessforsale.com.au", "No Agent Business"}
PERSON_WAIT_SECONDS = 600

_OPEN_FORM = re.compile(r"^(send (an )?enquiry|enquire( now)?|contact (the )?(owner|seller|broker|agent))$", re.I)
_CAPTCHA = ("iframe[src*='recaptcha'], iframe[src*='turnstile'], iframe[src*='hcaptcha'], iframe[src*='challenges.cloudflare'], "
            ".g-recaptcha, [data-sitekey]")
_ANSWER = re.compile(r"\b(answer|captcha|security.?code|verification)\b|\d\s*[-+x]\s*\d", re.I)
_CHECK = re.compile(r"verify you are human|are you a robot|checking your browser|unusual traffic|access denied", re.I)
_SENT = re.compile(r"thank you for your enquiry|your (enquiry|message) (has been|was) (sent|received)|enquiry sent|message sent|"
                   r"successfully sent|we have received your", re.I)
_SKIP = re.compile(r"best.?time|search|subject|company", re.I)
_FIELDS = [
    (re.compile(r"first.?name|fname", re.I), "first_name"),
    (re.compile(r"last.?name|surname|lname", re.I), "last_name"),
    (re.compile(r"e-?mail", re.I), "email"),
    (re.compile(r"phone|mobile|contact|\btel\b", re.I), "phone"),
    (re.compile(r"postcode|locality", re.I), "postcode"),
    (re.compile(r"name", re.I), "name"),
]


@dataclass(frozen=True)
class Outcome:
    status: str
    detail: str


def approach(page, url: str, fields: dict, live: bool, person_wait: int = PERSON_WAIT_SECONDS) -> Outcome:
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(2500)
    return complete(page, fields, live, person_wait)


def complete(page, fields: dict, live: bool, person_wait: int = PERSON_WAIT_SECONDS) -> Outcome:
    """Fill the open page's enquiry form, then send it or hand it to a person."""
    if _CHECK.search(f"{page.title()} {_text(page)[:3000]}"):
        return Outcome("Stopped", "The site showed a security check, so the agent stopped.")
    form = _open_form(page)
    if form is None:
        return Outcome("Needs you", "Couldn't find the enquiry form on the listing.")
    _fill(form, fields)
    gated = _gated(page, form)
    if not live:
        return Outcome("Test only", "Form filled, nothing sent." + (" A person would finish this one." if gated else ""))
    if gated:
        return _wait_for_person(page, form, person_wait)
    start = page.url
    form.locator("button[type=submit], input[type=submit]").first.click()
    if _gated(page, form):
        return _wait_for_person(page, form, person_wait)
    if _confirmed(page, form, start, 20):
        return Outcome("Sent", "Sent through the listing's form.")
    return Outcome("Needs you", "Pressed send, but the site didn't confirm it. Check the listing before trying again.")


def _open_form(page):
    form = _enquiry_form(page)
    if form is not None:
        return form
    for control in page.locator("a:visible, button:visible").all():
        if _OPEN_FORM.match((control.text_content() or "").strip()):
            control.click()
            page.wait_for_timeout(1500)
            return _enquiry_form(page)
    return None


def _enquiry_form(page):
    for form in page.locator("form:has(textarea)").all():
        if form.is_visible() and form.locator("input[type=email], input[name*=email]").count():
            return form
    return None


def _fill(form, fields: dict) -> None:
    for control in _controls(form):
        kind = control.evaluate("e => e.tagName === 'TEXTAREA' ? 'textarea' : e.type")
        hint = _hint(control)
        if kind == "textarea":
            control.fill(fields["message"])
        elif kind in ("text", "email", "tel", "number") and not _ANSWER.search(hint) and not _SKIP.search(hint):
            field = "email" if kind == "email" else "phone" if kind == "tel" else next((f for p, f in _FIELDS if p.search(hint)), "")
            if field:
                control.fill(re.sub(r"\D", "", fields[field]) if kind == "number" else fields[field])


def _gated(page, form) -> bool:
    return page.locator(_CAPTCHA).count() > 0 or any(_ANSWER.search(_hint(c)) for c in _controls(form))


def _controls(form) -> list:
    return [c for c in form.locator("input, textarea").all() if c.is_visible()] if form.count() else []


def _hint(control) -> str:
    return " ".join(filter(None, (control.get_attribute(a) for a in ("name", "id", "placeholder", "aria-label"))))


def _wait_for_person(page, form, seconds: int) -> Outcome:
    log.info("Form filled at %s. Finish the check and press send in the browser window.", page.url)
    start = page.url
    if _confirmed(page, form, start, seconds):
        return Outcome("Sent", "A person finished the form.")
    return Outcome("Needs you", "The form was filled but not sent. It has a check only a person can do.")


def _confirmed(page, form, start: str, seconds: int) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if page.is_closed():
            return False
        if page.url != start or _SENT.search(_text(page)) or not form.count() or not form.is_visible():
            return True
        page.wait_for_timeout(1000)
    return False


def _text(page) -> str:
    return page.locator("body").inner_text()
