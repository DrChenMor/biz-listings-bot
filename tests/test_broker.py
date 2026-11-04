import shutil
from dataclasses import replace
from email.message import EmailMessage
from io import BytesIO
from types import SimpleNamespace

import pytest
from PIL import Image
from pypdf import PdfReader
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from bizbot.broker import AgentError, agent, forms, is_live, mailbox, reader, signing
from bizbot.broker.buyer import TEST_BUYER, load
from bizbot.broker.database import Database

BUSINESS = {"id": "bsale:1", "name": "Dog Grooming", "status": "Available", "on_sheet": True, "kind": "sale", "site": "bsale", "url": "https://bsale.example/1"}
FIELDS = [
    {"field": "signature", "page": 1, "label": "Signature:", "occurrence": 1, "place": "right"},
    {"field": "name", "page": 1, "label": "Name:", "occurrence": 1, "place": "right"},
    {"field": "date", "page": 1, "label": "Date:", "occurrence": 1, "place": "right"},
]


def nda_pdf() -> bytes:
    sheet = BytesIO()
    drawing = canvas.Canvas(sheet, pagesize=A4)
    drawing.drawString(72, 760, "Confidentiality Agreement")
    for y, label in ((170, "Signature:"), (150, "Name:"), (130, "Date:")):
        drawing.drawString(72, y, label)
    drawing.save()
    return sheet.getvalue()


def page_text(pdf: bytes) -> str:
    return PdfReader(BytesIO(pdf)).pages[0].extract_text()


class MemoryDatabase(Database):
    def __init__(self):
        self.tables = {"businesses": [dict(BUSINESS)], "enquiries": [], "agent_emails": [], "agent_documents": [], "activity": []}
        self.saved, self.files = {}, {}

    def rows(self, table, **filters):
        wanted = {k: v[3:] for k, v in filters.items() if str(v).startswith("eq.")}
        return [r for r in self.tables[table] if all(str(r.get(k)) == v for k, v in wanted.items())]

    def add(self, table, row):
        self.tables[table].append({"id": len(self.tables[table]) + 1, **row})
        return self.tables[table][-1]

    def change(self, table, row_id, **fields):
        next(r for r in self.tables[table] if r["id"] == row_id).update(fields)

    def save(self, table, row, key):
        self.saved[table] = row

    def upload(self, path, data, content_type):
        self.files[path] = data

    def download(self, path):
        return self.files[path]


class SendingMailbox:
    def __init__(self):
        self.sent = []

    def reply(self, mail, reply_address, body, attachment):
        self.sent.append((mail.sender, reply_address, attachment))
        return "<out@agent>"


def setup_enquiry(status="Sent"):
    db = MemoryDatabase()
    return db, db.add("enquiries", {"business_id": "bsale:1", "status": status})


def reply_with(name="nda.pdf", data=None) -> mailbox.Mail:
    attachment = mailbox.Attachment(name, data or nda_pdf(), "application/pdf")
    return mailbox.Mail("<1@broker>", 1, "broker@agency.example", "Your enquiry", "Please sign the attached.", attachments=[attachment])


def reading(kind, nda=(), documents=(), link_only=False):
    return {"kind": kind, "summary": f"A {kind} reply", "nda_files": list(nda), "document_files": list(documents), "link_only": link_only}


def test_the_agent_stays_in_test_mode_unless_told_otherwise(monkeypatch):
    monkeypatch.delenv("AGENT_LIVE", raising=False)
    assert not is_live() and load(False) is TEST_BUYER
    monkeypatch.setenv("AGENT_LIVE", "yes")
    assert is_live()


def test_each_enquiry_gets_its_own_address():
    assert TEST_BUYER.address_for(12) == "test.buyer+e12@example.com"
    assert TEST_BUYER.form_fields(12)["email"] == "test.buyer+e12@example.com"


def test_going_live_needs_a_complete_buyer_profile(monkeypatch):
    monkeypatch.setenv("BUYER_PROFILE", '{"name": "Sam"}')
    with pytest.raises(AgentError, match="email, phone, postcode"):
        load(True)


def test_a_reply_is_matched_to_its_enquiry_and_keeps_only_document_files():
    message = EmailMessage()
    message["From"] = "Pat Broker <pat@agency.example>"
    message["To"] = "deals+e7@gmail.com"
    message["Subject"] = "Re: Dog Grooming"
    message["Message-ID"] = "<abc@agency.example>"
    message.set_content("Hello")
    message.add_attachment(b"%PDF", maintype="application", subtype="pdf", filename="../../N D A.pdf")
    message.add_attachment(b"MZ", maintype="application", subtype="octet-stream", filename="run-me.exe")
    mail = mailbox.parse_mail(message.as_bytes())
    assert (mail.enquiry_id, mail.sender, mail.message_id) == (7, "pat@agency.example", "<abc@agency.example>")
    assert [a.name for a in mail.attachments] == ["N_D_A.pdf"]


def test_mail_to_the_plain_address_belongs_to_no_enquiry():
    message = EmailMessage()
    message["To"] = "deals@gmail.com"
    message.set_content("Newsletter")
    assert mailbox.parse_mail(message.as_bytes()).enquiry_id is None


def test_signing_writes_beside_the_labels():
    signed = signing.sign(nda_pdf(), FIELDS, {"name": "Sam Lee", "date": "1 November 2026"}, None)
    text = page_text(signed)
    assert "TEST SIGNATURE" in text and "Sam Lee" in text and "1 November 2026" in text


def test_a_missing_label_stops_the_signing():
    with pytest.raises(AgentError, match="Couldn't find"):
        signing.sign(nda_pdf(), [{**FIELDS[0], "label": "Signed for the buyer"}], {}, None)


def test_a_field_the_profile_cant_answer_stops_the_signing():
    field = {"field": "abn", "page": 1, "label": "Name:", "occurrence": 1, "place": "right"}
    with pytest.raises(AgentError, match="abn"):
        signing.sign(nda_pdf(), [FIELDS[0], field], {"abn": ""}, None)


def test_an_nda_with_nowhere_to_sign_is_not_signed():
    with pytest.raises(AgentError, match="where the buyer signs"):
        signing.sign(nda_pdf(), FIELDS[1:], {"name": "Sam", "date": "today"}, None)


@pytest.mark.skipif(not shutil.which("soffice"), reason="needs LibreOffice")
def test_other_files_become_pdfs():
    assert signing.to_pdf("note.txt", b"Hello").startswith(b"%PDF")


def test_a_file_type_that_cant_be_read_is_reported():
    with pytest.raises(AgentError):
        signing.to_pdf("photo.png", b"x")


def test_a_plain_nda_is_signed_but_not_emailed_in_test_mode(monkeypatch):
    db, enquiry = setup_enquiry()
    box = SendingMailbox()
    monkeypatch.setattr(reader, "read_reply", lambda *a: reading("nda", nda=["nda.pdf"]))
    monkeypatch.setattr(reader, "read_nda", lambda *a: {"plain": True, "concerns": [], "fields": FIELDS})
    agent.handle_mail(db, reply_with(), enquiry, box, None, TEST_BUYER, live=False)
    assert enquiry["status"] == "NDA ready" and box.sent == []
    signed = next(data for path, data in db.files.items() if "signed" in path)
    assert "Test Buyer" in page_text(signed)
    assert {d["kind"] for d in db.tables["agent_documents"]} == {"nda", "signed nda"}


def test_a_plain_nda_goes_back_to_the_broker_when_live(monkeypatch):
    db, enquiry = setup_enquiry()
    box = SendingMailbox()
    buyer = replace(TEST_BUYER, name="Sam Lee", email="deals@gmail.com")
    monkeypatch.setattr(reader, "read_reply", lambda *a: reading("nda", nda=["nda.pdf"]))
    monkeypatch.setattr(reader, "read_nda", lambda *a: {"plain": True, "concerns": [], "fields": FIELDS})
    agent.handle_mail(db, reply_with(), enquiry, box, None, buyer, live=True)
    assert enquiry["status"] == "Needs you" and box.sent == []  # no signature set up

    db, enquiry = setup_enquiry()
    png = BytesIO()
    Image.new("RGBA", (40, 12), (0, 0, 0, 255)).save(png, "PNG")
    agent.handle_mail(db, reply_with(), enquiry, box, None, replace(buyer, signature=png.getvalue()), live=True)
    assert enquiry["status"] == "NDA signed"
    assert box.sent[0][:2] == ("broker@agency.example", "deals+e1@gmail.com")
    assert [e["direction"] for e in db.tables["agent_emails"]] == ["in", "out"]


def test_an_nda_that_isnt_plain_goes_to_a_person(monkeypatch):
    db, enquiry = setup_enquiry()
    box = SendingMailbox()
    monkeypatch.setattr(reader, "read_reply", lambda *a: reading("nda", nda=["nda.pdf"]))
    monkeypatch.setattr(reader, "read_nda", lambda *a: {"plain": False, "concerns": ["A $500 fee"], "fields": FIELDS})
    agent.handle_mail(db, reply_with(), enquiry, box, None, TEST_BUYER, live=True)
    assert enquiry["status"] == "Needs you" and "A $500 fee" in enquiry["detail"] and box.sent == []


def test_a_second_nda_goes_to_a_person(monkeypatch):
    db, enquiry = setup_enquiry("NDA signed")
    monkeypatch.setattr(reader, "read_reply", lambda *a: reading("nda", nda=["nda.pdf"]))
    agent.handle_mail(db, reply_with(), enquiry, SendingMailbox(), None, TEST_BUYER, live=True)
    assert enquiry["status"] == "Needs you"


def test_documents_are_filed_and_evaluated(monkeypatch):
    db, enquiry = setup_enquiry("NDA signed")
    verdict = {"verdict": "Worth a closer look", "headline": "Steady profit"}
    seen = {}
    monkeypatch.setattr(reader, "read_reply", lambda *a: reading("documents", documents=["im.pdf"]))
    monkeypatch.setattr(reader, "evaluate", lambda client, business, files: seen.update(files=[n for n, _ in files]) or verdict)
    agent.handle_mail(db, reply_with("im.pdf"), enquiry, SendingMailbox(), None, TEST_BUYER, live=False)
    assert enquiry["status"] == "Evaluated" and seen["files"] == ["im.pdf"]
    assert db.saved["evaluations"]["summary"] == verdict and db.saved["tracking"]["stage"] == "NDA and numbers"


@pytest.mark.parametrize("kind, link_only, status", [("declined", False, "Closed"), ("question", False, "Needs you"), ("nda", True, "Needs you"), ("auto_reply", False, "Sent")])
def test_other_replies_end_up_in_the_right_place(monkeypatch, kind, link_only, status):
    db, enquiry = setup_enquiry()
    monkeypatch.setattr(reader, "read_reply", lambda *a: reading(kind, link_only=link_only))
    agent.handle_mail(db, reply_with(), enquiry, SendingMailbox(), None, TEST_BUYER, live=False)
    assert enquiry["status"] == status


def test_a_failed_read_leaves_the_email_to_try_again(monkeypatch):
    db, enquiry = setup_enquiry()

    def fail(*args):
        raise AgentError("Claude stopped early")

    monkeypatch.setattr(reader, "read_reply", fail)
    with pytest.raises(AgentError):
        agent.handle_mail(db, reply_with(), enquiry, SendingMailbox(), None, TEST_BUYER, live=False)
    assert db.tables["agent_emails"] == []


def test_sold_or_unsupported_listings_are_not_approached():
    assert agent._cannot_approach({**BUSINESS, "status": "Sold"})
    assert agent._cannot_approach({**BUSINESS, "site": "healthdirect"})
    assert agent._cannot_approach(BUSINESS) == ""


def test_the_enquiry_states_only_the_buyers_details():
    message = agent.enquiry_message(BUSINESS, TEST_BUYER)
    assert "Dog Grooming" in message and TEST_BUYER.name in message and TEST_BUYER.phone in message


class FakeStream:
    def __init__(self, stop_reason):
        self.message = SimpleNamespace(stop_reason=stop_reason, content=[SimpleNamespace(type="text", text='{"kind": "nda"}')])

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def get_final_message(self):
        return self.message


def fake_claude(stop_reason):
    return SimpleNamespace(messages=SimpleNamespace(stream=lambda **kwargs: FakeStream(stop_reason)))


def test_claudes_answer_is_read_only_when_it_finished():
    assert reader._ask(fake_claude("end_turn"), "model", "system", [], {}, 100) == {"kind": "nda"}
    with pytest.raises(AgentError):
        reader._ask(fake_claude("refusal"), "model", "system", [], {}, 100)


@pytest.fixture(scope="module")
def browser():
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as p:
        try:
            chromium = p.chromium.launch()
        except Exception:
            pytest.skip("Chromium isn't installed")
        yield chromium
        chromium.close()


FORM = """<form onsubmit="window.sent = true; document.body.innerHTML = '<p>Thank you for your enquiry</p>'; return false">
  <input name="nameHere" placeholder="Name"><input type="email" name="emailHere"><input type="number" name="phone">
  <input name="localityHere" placeholder="Postcode"><textarea name="message"></textarea>
  <input type="checkbox" name="similarBusiness">{extra}<button type="submit">Send</button></form>"""
ANSWERS = {**TEST_BUYER.form_fields(1), "phone": "0400 000 000", "message": "Hello"}


def open_page(browser, html):
    page = browser.new_page()
    page.set_content(html)
    return page


def value(page, name):
    return page.input_value(f"[name={name}]")


def test_test_mode_fills_a_plain_form_and_sends_nothing(browser):
    page = open_page(browser, FORM.format(extra=""))
    outcome = forms.complete(page, ANSWERS, live=False)
    assert outcome.status == "Test only" and not page.evaluate("window.sent")
    assert (value(page, "nameHere"), value(page, "localityHere"), value(page, "message")) == ("Test Buyer", "6000", "Hello")
    assert value(page, "phone") == "0400000000" and value(page, "emailHere") == "test.buyer+e1@example.com"
    assert not page.is_checked("[name=similarBusiness]")


def test_a_plain_form_is_sent_when_live(browser):
    page = open_page(browser, FORM.format(extra=""))
    assert forms.complete(page, ANSWERS, live=True).status == "Sent" and page.evaluate("window.sent")


@pytest.mark.parametrize("extra", ['<div class="g-recaptcha" data-sitekey="x"></div>', '<input name="answer" placeholder="4 + 4 = ?">'])
def test_a_form_with_a_check_is_filled_and_left_for_a_person(browser, extra):
    page = open_page(browser, FORM.format(extra=extra))
    outcome = forms.complete(page, ANSWERS, live=True, person_wait=1)
    assert outcome.status == "Needs you" and not page.evaluate("window.sent")
    assert value(page, "nameHere") == "Test Buyer"
    if "answer" in extra:
        assert value(page, "answer") == ""


PERSON_TICKS = """<div class="g-recaptcha" data-sitekey="x"></div><textarea name="g-recaptcha-response" style="display:none"></textarea>
  <script>setTimeout(() => document.querySelector('[name=g-recaptcha-response]').value = 'token', 1500)</script>"""
PERSON_ANSWERS = """<input name="answer" placeholder="4 + 4 = ?"><script>setTimeout(() => document.querySelector('[name=answer]').value = '8', 1500)</script>"""


@pytest.mark.parametrize("extra", [PERSON_TICKS, PERSON_ANSWERS])
def test_the_agent_presses_send_once_a_person_has_done_the_check(browser, extra):
    page = open_page(browser, FORM.format(extra=extra))
    outcome = forms.complete(page, ANSWERS, live=True, person_wait=15)
    assert outcome.status == "Sent" and "agent pressed send" in outcome.detail and page.evaluate("window.sent")


def test_test_mode_never_waits_for_the_check(browser):
    page = open_page(browser, FORM.format(extra=PERSON_TICKS))
    assert forms.complete(page, ANSWERS, live=False).status == "Test only"
    page.wait_for_timeout(2500)
    assert not page.evaluate("window.sent")


def test_a_security_check_stops_the_enquiry(browser):
    page = open_page(browser, "<p>Verify you are human</p>" + FORM.format(extra=""))
    assert forms.complete(page, ANSWERS, live=True).status == "Stopped"
    assert value(page, "nameHere") == "" and not page.evaluate("window.sent")


def test_a_page_with_no_form_goes_to_a_person(browser):
    assert forms.complete(open_page(browser, "<p>Nothing here</p>"), ANSWERS, live=True).status == "Needs you"
