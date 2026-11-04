"""Writes the buyer's details and signature onto an NDA.

The reader says which printed labels belong to the buyer; this finds those words on the page and writes beside them. If a
label can't be found, or the profile doesn't hold the answer, nothing is signed and a person takes over.
"""
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

from . import AgentError

TEXT_SIZE = 10
SIGNATURE_WIDTH, SIGNATURE_HEIGHT = 120, 36
_LABEL_GAP, _ABOVE_GAP = 6, 13
_CONVERTIBLE = {".doc", ".docx", ".xls", ".xlsx", ".csv", ".txt"}


@dataclass(frozen=True)
class Spot:
    text: str
    x: float
    y: float
    size: float


def to_pdf(name: str, data: bytes) -> bytes:
    """A PDF of an attachment, using LibreOffice for Word, Excel and text files."""
    suffix = Path(name).suffix.lower()
    if suffix == ".pdf":
        return data
    office = shutil.which("soffice")
    if suffix not in _CONVERTIBLE or not office:
        raise AgentError(f"Couldn't turn {name} into a PDF.")
    with tempfile.TemporaryDirectory() as folder:
        source = Path(folder) / f"attachment{suffix}"
        source.write_bytes(data)
        try:
            subprocess.run([office, f"-env:UserInstallation=file://{folder}/profile", "--headless", "--convert-to", "pdf", "--outdir", folder, str(source)],
                           check=True, capture_output=True, timeout=120)
            return source.with_suffix(".pdf").read_bytes()
        except (subprocess.SubprocessError, OSError):
            raise AgentError(f"Couldn't turn {name} into a PDF.") from None


def sign(pdf: bytes, fields: list[dict], values: dict, signature: bytes | None) -> bytes:
    """A copy of the PDF with each field written in. `signature` is a PNG; without one, test words are written."""
    if not any(f["field"] == "signature" for f in fields):
        raise AgentError("Couldn't find where the buyer signs.")
    reader = PdfReader(BytesIO(pdf))
    writer = PdfWriter(clone_from=reader)
    for number, page in enumerate(writer.pages, 1):
        wanted = [f for f in fields if f["page"] == number]
        if wanted:
            box = page.mediabox
            sheet = BytesIO()
            drawing = canvas.Canvas(sheet, pagesize=(float(box.width), float(box.height)))
            spots = _spots(reader.pages[number - 1])
            for field in wanted:
                x, y = _position(spots, field)
                _write(drawing, x - float(box.left), y - float(box.bottom), field["field"], values, signature)
            drawing.save()
            page.merge_page(PdfReader(BytesIO(sheet.getvalue())).pages[0])
    if any(not 1 <= f["page"] <= len(writer.pages) for f in fields):
        raise AgentError("The NDA check named a page that isn't in the file.")
    finished = BytesIO()
    writer.write(finished)
    return finished.getvalue()


def _spots(page) -> list[Spot]:
    """Each run of text on the page, with where it starts."""
    spots = []

    def collect(text, cm, tm, font, size):
        if text.strip():
            spots.append(Spot(text, cm[0] * tm[4] + cm[2] * tm[5] + cm[4], cm[1] * tm[4] + cm[3] * tm[5] + cm[5], (size or TEXT_SIZE) * abs(tm[0] or 1) * abs(cm[0] or 1)))

    page.extract_text(visitor_text=collect)
    return spots


def _position(spots: list[Spot], field: dict) -> tuple[float, float]:
    """Where to write for this label: after it, or just above it."""
    label = " ".join(field["label"].split()).lower()
    seen = 0
    for spot in spots:
        text = " ".join(spot.text.split())
        start = text.lower().find(label)
        while start >= 0:
            seen += 1
            if seen == field["occurrence"]:
                if field["place"] == "above":
                    return spot.x + stringWidth(text[:start], "Helvetica", spot.size), spot.y + _ABOVE_GAP
                return spot.x + stringWidth(text[: start + len(label)], "Helvetica", spot.size) + _LABEL_GAP, spot.y
            start = text.lower().find(label, start + 1)
    raise AgentError(f'Couldn\'t find "{field["label"]}" on page {field["page"]} of the NDA.')


def _write(drawing, x: float, y: float, field: str, values: dict, signature: bytes | None) -> None:
    if field != "signature":
        if not values.get(field):
            raise AgentError(f"The NDA asks for the buyer's {field}, which isn't in the buyer profile.")
        drawing.setFont("Helvetica", TEXT_SIZE)
        drawing.drawString(x, y, values[field])
    elif signature:
        drawing.drawImage(ImageReader(BytesIO(signature)), x, y - 8, width=SIGNATURE_WIDTH, height=SIGNATURE_HEIGHT, mask="auto", preserveAspectRatio=True, anchor="sw")
    else:
        drawing.setFont("Helvetica-Oblique", TEXT_SIZE)
        drawing.drawString(x, y, "TEST SIGNATURE")
