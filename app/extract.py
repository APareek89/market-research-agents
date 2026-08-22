"""Server-side extraction of uploaded files. 15 MB per-file limit.
Docs/sheets -> text (capped); images -> base64 data URL for the intake agent's
multimodal call."""

import base64
import csv
import io

MAX_FILE_BYTES = 15 * 1024 * 1024
TEXT_CHAR_CAP = 40000
SHEET_ROW_CAP = 300

IMAGE_TYPES = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
               "gif": "image/gif", "webp": "image/webp"}


class ExtractError(Exception):
    pass


def _cap(text: str) -> str:
    text = text.strip()
    if len(text) > TEXT_CHAR_CAP:
        return text[:TEXT_CHAR_CAP] + "\n…[truncated]"
    return text


def _pdf(data: bytes) -> str:
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(data))
    pages = []
    for i, page in enumerate(reader.pages[:60]):
        pages.append(f"[page {i + 1}]\n{page.extract_text() or ''}")
    return _cap("\n".join(pages))


def _docx(data: bytes) -> str:
    from docx import Document
    doc = Document(io.BytesIO(data))
    parts = [p.text for p in doc.paragraphs if p.text.strip()]
    for table in doc.tables:
        for row in table.rows:
            parts.append(" | ".join(c.text.strip() for c in row.cells))
    return _cap("\n".join(parts))


def _xlsx(data: bytes) -> str:
    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    parts = []
    for ws in wb.worksheets[:5]:
        parts.append(f"[sheet: {ws.title}]")
        for i, row in enumerate(ws.iter_rows(values_only=True)):
            if i >= SHEET_ROW_CAP:
                parts.append(f"…[{ws.max_row - SHEET_ROW_CAP} more rows truncated]")
                break
            parts.append(" | ".join("" if v is None else str(v) for v in row))
    return _cap("\n".join(parts))


def _csv(data: bytes) -> str:
    text = data.decode("utf-8", errors="replace")
    rows = list(csv.reader(io.StringIO(text)))
    out = [" | ".join(r) for r in rows[:SHEET_ROW_CAP]]
    if len(rows) > SHEET_ROW_CAP:
        out.append(f"…[{len(rows) - SHEET_ROW_CAP} more rows truncated]")
    return _cap("\n".join(out))


def extract_file(filename: str, data: bytes) -> dict:
    """Returns {"kind": "text"|"image", "name": ..., "text": ...} or
    {"kind": "image", "name": ..., "data_url": ...}. Raises ExtractError."""
    if len(data) > MAX_FILE_BYTES:
        raise ExtractError(f"{filename} is over the 15 MB limit.")
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    try:
        if ext == "pdf":
            return {"kind": "text", "name": filename, "text": _pdf(data)}
        if ext == "docx":
            return {"kind": "text", "name": filename, "text": _docx(data)}
        if ext in ("xlsx", "xlsm"):
            return {"kind": "text", "name": filename, "text": _xlsx(data)}
        if ext == "csv":
            return {"kind": "text", "name": filename, "text": _csv(data)}
        if ext in IMAGE_TYPES:
            b64 = base64.standard_b64encode(data).decode()
            return {"kind": "image", "name": filename,
                    "data_url": f"data:{IMAGE_TYPES[ext]};base64,{b64}"}
        if ext in ("txt", "md", "json"):
            return {"kind": "text", "name": filename,
                    "text": _cap(data.decode("utf-8", errors="replace"))}
    except ExtractError:
        raise
    except Exception as e:  # noqa: BLE001
        raise ExtractError(f"Could not read {filename}: {e}") from e
    raise ExtractError(
        f"Unsupported file type: {filename}. Supported: PDF, DOCX, XLSX, CSV, TXT/MD, PNG/JPG/GIF/WEBP."
    )
