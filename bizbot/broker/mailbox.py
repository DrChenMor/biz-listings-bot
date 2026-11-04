"""The agent's Gmail inbox. Needs GMAIL_ADDRESS and GMAIL_APP_PASSWORD (a Google app password for that inbox).

Every enquiry goes out with its own address, like deals+e12@gmail.com, so only mail to one of those addresses is read:
that is what keeps the agent inside threads it started. Reading leaves messages unread for a person.
"""
import email
import imaplib
import os
import re
import smtplib
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email import policy
from email.message import EmailMessage
from email.utils import getaddresses, make_msgid, parseaddr
from pathlib import PurePosixPath

from . import AgentError

IMAP_HOST = "imap.gmail.com"
SMTP_HOST = "smtp.gmail.com"
DAYS = 14
MAX_ATTACHMENT = 25 * 1024 * 1024
KEPT_TYPES = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".csv", ".txt"}

_TAG = re.compile(r"\+e(\d+)@", re.I)
_ADDRESS_HEADERS = ("To", "Cc", "Delivered-To", "X-Original-To")


@dataclass
class Attachment:
    name: str
    data: bytes
    content_type: str


@dataclass
class Mail:
    message_id: str
    enquiry_id: int | None
    sender: str
    subject: str
    body: str
    references: str = ""
    attachments: list[Attachment] = field(default_factory=list)


class Gmail:
    def __init__(self, address: str, password: str):
        self.address, self.password = address, password

    @classmethod
    def connect(cls) -> "Gmail":
        address, password = os.environ.get("GMAIL_ADDRESS", "").strip(), os.environ.get("GMAIL_APP_PASSWORD", "").replace(" ", "")
        if not address or not password:
            raise AgentError("Set GMAIL_ADDRESS and GMAIL_APP_PASSWORD first.")
        return cls(address, password)

    def new_mail(self, known: set[str], days: int = DAYS) -> list[Mail]:
        """Recent mail sent to an enquiry's address, leaving out message IDs already handled."""
        conn = imaplib.IMAP4_SSL(IMAP_HOST)
        try:
            conn.login(self.address, self.password)
            conn.select("INBOX", readonly=True)
            since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%d-%b-%Y")
            _, found = conn.search(None, "SINCE", since)
            fresh = []
            for number in found[0].split():
                _, data = conn.fetch(number, "(BODY.PEEK[HEADER])")
                head = email.message_from_bytes(data[0][1], policy=policy.default)
                if enquiry_of(head) is not None and _message_id(head) not in known:
                    _, data = conn.fetch(number, "(BODY.PEEK[])")
                    fresh.append(parse_mail(data[0][1]))
            return fresh
        except imaplib.IMAP4.error as e:
            raise AgentError(f"Gmail refused that ({e}). Check GMAIL_ADDRESS and GMAIL_APP_PASSWORD.") from None
        finally:
            try:
                conn.logout()
            except (imaplib.IMAP4.error, OSError):
                pass

    def reply(self, mail: Mail, reply_address: str, body: str, attachment: Attachment) -> str:
        """Answer in the same thread, to the person who wrote, and return the new message's ID."""
        message = EmailMessage()
        message["From"] = self.address
        message["Reply-To"] = reply_address
        message["To"] = mail.sender
        message["Subject"] = mail.subject if mail.subject.lower().startswith("re:") else f"Re: {mail.subject}"
        message["In-Reply-To"] = mail.message_id
        message["References"] = f"{mail.references} {mail.message_id}".strip()
        message["Message-ID"] = make_msgid(domain=self.address.split("@", 1)[1])
        message.set_content(body)
        maintype, _, subtype = attachment.content_type.partition("/")
        message.add_attachment(attachment.data, maintype=maintype, subtype=subtype, filename=attachment.name)
        with smtplib.SMTP_SSL(SMTP_HOST, timeout=60) as smtp:
            smtp.login(self.address, self.password)
            smtp.send_message(message)
        return message["Message-ID"]


def parse_mail(raw: bytes) -> Mail:
    message = email.message_from_bytes(raw, policy=policy.default)
    body = message.get_body(preferencelist=("plain", "html"))
    return Mail(
        message_id=_message_id(message),
        enquiry_id=enquiry_of(message),
        sender=parseaddr(str(message.get("Reply-To") or message.get("From") or ""))[1],
        subject=str(message.get("Subject") or ""),
        body=_clean(body.get_content()) if body else "",
        references=str(message.get("References") or ""),
        attachments=[kept for part in message.iter_attachments() if (kept := _attachment(part))],
    )


def enquiry_of(message) -> int | None:
    """The enquiry number in the address this was sent to."""
    addresses = getaddresses([str(value) for header in _ADDRESS_HEADERS for value in message.get_all(header, [])])
    for _, address in addresses:
        if match := _TAG.search(address):
            return int(match[1])
    return None


def _attachment(part) -> Attachment | None:
    name = re.sub(r"[^\w.-]+", "_", PurePosixPath((part.get_filename() or "").replace("\\", "/")).name)[-120:].lstrip(".")
    data = part.get_payload(decode=True) or b""
    if PurePosixPath(name).suffix.lower() not in KEPT_TYPES or len(data) > MAX_ATTACHMENT:
        return None
    return Attachment(name, data, part.get_content_type())


def _message_id(message) -> str:
    return str(message.get("Message-ID") or "").strip()


def _clean(text: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", re.sub(r"<[^>]+>", " ", text)).strip()
