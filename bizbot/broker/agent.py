"""The broker agent's two jobs.

  send_queued   open each queued listing and send, or hand over, its enquiry (needs a visible browser, so runs on a Mac)
  read_inbox    read replies, sign and return a plain NDA, file documents and have them evaluated (can run anywhere)

Anything unusual stops at "Needs you", with the reason, for a person to pick up.
"""
import logging
from datetime import datetime, timezone

from . import AgentError, buyer as buyers, forms
from .buyer import Buyer
from .database import Database
from .mailbox import Attachment, Mail

log = logging.getLogger(__name__)

SEND_LIMIT = 5
_NEW_STATUSES = ("Queued", "Sending", "Stopped", "Closed")


def send_queued(db: Database, live: bool, limit: int | None = None) -> int:
    queued = db.rows("enquiries", status="eq.Queued", order="requested_at", limit=str(limit or SEND_LIMIT))
    if not queued:
        return 0
    from playwright.sync_api import sync_playwright

    buyer = buyers.load(live)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        for enquiry in queued:
            _send(db, page, enquiry, buyer, live)
        browser.close()
    return len(queued)


def _send(db: Database, page, enquiry: dict, buyer: Buyer, live: bool) -> None:
    business = db.rows("businesses", id=f"eq.{enquiry['business_id']}")[0]
    if reason := _cannot_approach(business):
        db.set_status(enquiry, "Needs you", reason)
        return
    message = enquiry_message(business, buyer)
    # Never retried from here, so a crash after pressing send can't contact a broker twice.
    db.set_status(enquiry, "Sending", message=message)
    outcome = forms.approach(page, business["url"], {**buyer.form_fields(enquiry["id"]), "message": message}, live)
    sent = {"sent_at": datetime.now(timezone.utc).isoformat()} if outcome.status == "Sent" else {}
    db.set_status(enquiry, outcome.status, outcome.detail, **sent)


def _cannot_approach(business: dict) -> str:
    if business["status"] in ("Sold", "Removed") or not business["on_sheet"]:
        return "This listing is sold or gone."
    if business["kind"] != "sale" or business["site"] not in forms.SITES or not business["url"]:
        return f"The agent can't send through {business['site']} yet."
    return ""


def enquiry_message(business: dict, buyer: Buyer) -> str:
    return (f"Hello,\n\nI'm interested in {business['name']} and would like more information. Please send through the details, "
            f"along with any confidentiality agreement you need signed first.\n\nRegards,\n{buyer.name}\n{buyer.phone}")


def read_inbox(db: Database, live: bool, mailbox, claude) -> int:
    """Handle new replies. Returns how many were handled."""
    open_enquiries = {e["id"]: e for e in db.rows("enquiries", status=f"not.in.({','.join(_NEW_STATUSES)})")}
    known = {row["message_id"] for row in db.rows("agent_emails", select="message_id", direction="eq.in")}
    handled = 0
    for mail in mailbox.new_mail(known):
        if enquiry := open_enquiries.get(mail.enquiry_id):
            handle_mail(db, mail, enquiry, mailbox, claude, buyers.load(live), live)
            handled += 1
    return handled


def handle_mail(db: Database, mail: Mail, enquiry: dict, mailbox, claude, buyer: Buyer, live: bool) -> None:
    from . import reader, signing

    business = db.rows("businesses", id=f"eq.{enquiry['business_id']}")[0]
    files = _readable(mail.attachments, signing)
    # Read first: if this fails nothing is saved, so the same email is read again next run.
    reading = reader.read_reply(claude, business, mail, files)
    email = db.add("agent_emails", {"enquiry_id": enquiry["id"], "direction": "in", "message_id": mail.message_id, "sender": mail.sender,
                                    "subject": mail.subject, "body": mail.body, "kind": reading["kind"], "summary": reading["summary"]})
    kinds = {name: "nda" for name in reading["nda_files"]} | {name: "document" for name in reading["document_files"]}
    paths = {a.name: _file(db, enquiry, email["id"], a, kinds.get(a.name, "other")) for a in mail.attachments}

    try:
        if reading["link_only"]:
            db.set_status(enquiry, "Needs you", f"The broker wants this done at a link: {reading['summary']}")
        elif reading["kind"] == "nda":
            _sign_and_return(db, mail, enquiry, business, dict(files), reading["nda_files"], mailbox, claude, buyer, live)
        elif reading["kind"] == "documents":
            db.set_status(enquiry, "Documents in", reading["summary"])
            _evaluate(db, enquiry, business, claude, signing)
        elif reading["kind"] == "declined":
            db.set_status(enquiry, "Closed", reading["summary"])
        elif reading["kind"] != "auto_reply":
            db.set_status(enquiry, "Needs you", reading["summary"])
    except AgentError as e:
        db.set_status(enquiry, "Needs you", str(e))
    log.info("Enquiry %s: %s, %d files, now %s", enquiry["id"], reading["kind"], len(paths), enquiry["status"])


def _readable(attachments: list[Attachment], signing) -> list[tuple[str, bytes]]:
    """(name, PDF) for each attachment that can be turned into a PDF."""
    files = []
    for attachment in attachments:
        try:
            files.append((attachment.name, signing.to_pdf(attachment.name, attachment.data)))
        except AgentError as e:
            log.warning("%s", e)
    return files


def _file(db: Database, enquiry: dict, email_id: int | None, attachment: Attachment, kind: str) -> str:
    path = f"enquiry-{enquiry['id']}/{email_id or 'signed'}/{attachment.name}"
    db.upload(path, attachment.data, attachment.content_type)
    db.add("agent_documents", {"enquiry_id": enquiry["id"], "name": attachment.name, "path": path, "kind": kind})
    return path


def _sign_and_return(db: Database, mail: Mail, enquiry: dict, business: dict, files: dict, nda_files: list[str], mailbox, claude, buyer: Buyer, live: bool) -> None:
    from . import reader, signing

    if enquiry["status"] in ("NDA ready", "NDA signed"):
        raise AgentError("The broker sent another NDA after one was signed. A person should read this.")
    name = next((n for n in nda_files if n in files), None)
    if len(nda_files) != 1 or name is None:
        raise AgentError("The reply didn't hold one clear NDA to sign.")
    check = reader.read_nda(claude, name, files[name])
    if not check["plain"]:
        raise AgentError(f"This NDA needs a person to read it: {'; '.join(check['concerns'])}")
    if live and not buyer.signature:
        raise AgentError("No signature is set up. Set BUYER_SIGNATURE_FILE.")
    signed = Attachment(f"Signed {name.rsplit('.', 1)[0]}.pdf".replace(" ", "_"), signing.sign(files[name], check["fields"], buyer.signing_values(), buyer.signature), "application/pdf")
    _file(db, enquiry, None, signed, "signed nda")
    if not live:
        db.set_status(enquiry, "NDA ready", "Test mode: signed copy saved, nothing emailed.")
        return
    body = f"Hello,\n\nPlease find the signed confidentiality agreement attached. I look forward to the information on {business['name']}.\n\nRegards,\n{buyer.name}\n{buyer.phone}"
    message_id = mailbox.reply(mail, buyer.address_for(enquiry["id"]), body, signed)
    db.add("agent_emails", {"enquiry_id": enquiry["id"], "direction": "out", "message_id": message_id, "recipient": mail.sender,
                            "subject": mail.subject, "body": body, "kind": "signed nda"})
    db.set_status(enquiry, "NDA signed", f"Signed and sent back to {mail.sender}.")


def _evaluate(db: Database, enquiry: dict, business: dict, claude, signing) -> None:
    from . import reader

    files = []
    for document in db.rows("agent_documents", enquiry_id=f"eq.{enquiry['id']}", kind="eq.document", order="at"):
        files.append((document["name"], signing.to_pdf(document["name"], db.download(document["path"]))))
    if not files:
        raise AgentError("The reply had information, but no file to evaluate.")
    summary = reader.evaluate(claude, business, files)
    db.save("evaluations", {"business_id": business["id"], "enquiry_id": enquiry["id"], "summary": summary, "model": reader.EVALUATOR_MODEL}, "business_id")
    db.save("tracking", {"business_id": business["id"], "stage": "NDA and numbers"}, "business_id")
    db.set_status(enquiry, "Evaluated", f"{summary['verdict']}: {summary['headline']}")
