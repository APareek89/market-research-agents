"""Server-side extraction of uploaded files. 15 MB per-file limit.
Docs/sheets -> text (capped); images -> base64 data URL for the intake agent's
multimodal call."""

import base64
import csv
import io
import itertools
import zipfile

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
    from pypdf import PdfReader, apply_configuration
    # Context-local limits also apply to nested filters and XObject traversal;
    # another upload or export does not inherit this parser configuration.
    with apply_configuration(
        maximum_declared_stream_length=8*1024*1024,
        array_based_stream_maximum_output_length=8*1024*1024,
        zlib_maximum_output_length=8*1024*1024,
        lzw_maximum_output_length=8*1024*1024,
        run_length_maximum_output_length=8*1024*1024,
        jbig2_maximum_output_length=8*1024*1024,
        zlib_maximum_recovery_input_length=100000,
        page_tree_maximum_entries=500, page_tree_maximum_depth=30,
        xform_maximum_invocations_per_extraction=100,
        outline_maximum_entries=1000, outline_maximum_depth=30,
        jbig2dec_binary=None,
    ):
        reader = PdfReader(io.BytesIO(data))
        pages = []
        decoded_bytes = 0
        for i, page in enumerate(reader.pages[:60]):
            content = page.get_contents()
            decoded_bytes += len(content.get_data()) if content else 0
            if decoded_bytes > 20*1024*1024:
                raise ExtractError('PDF content expands beyond the supported size')
            pages.append(f"[page {i + 1}]\n{page.extract_text() or ''}")
            if sum(map(len,pages)) > TEXT_CHAR_CAP:
                break
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
    wb.close()
    return _cap("\n".join(parts))


def _csv(data: bytes) -> str:
    text = data.decode("utf-8", errors="replace")
    rows = list(itertools.islice(csv.reader(io.StringIO(text)),SHEET_ROW_CAP+1))
    out = [" | ".join(r[:100]) for r in rows[:SHEET_ROW_CAP]]
    if len(rows) > SHEET_ROW_CAP:
        out.append('…[more rows truncated]')
    return _cap("\n".join(out))


def extract_file(filename: str, data: bytes) -> dict:
    """Returns {"kind": "text"|"image", "name": ..., "text": ...} or
    {"kind": "image", "name": ..., "data_url": ...}. Raises ExtractError."""
    if len(data) > MAX_FILE_BYTES:
        raise ExtractError(f"{filename} is over the 15 MB limit.")
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    try:
        if ext in {'docx','xlsx','xlsm'}:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                entries=archive.infolist()
                if len(entries)>2000 or sum(e.file_size for e in entries)>40*1024*1024 or any(e.file_size>15*1024*1024 for e in entries):
                    raise ExtractError('Document expands beyond the supported size')
        if ext == "pdf":
            return {"kind": "text", "name": filename, "text": _pdf(data)}
        if ext == "docx":
            return {"kind": "text", "name": filename, "text": _docx(data)}
        if ext in ("xlsx", "xlsm"):
            return {"kind": "text", "name": filename, "text": _xlsx(data)}
        if ext == "csv":
            return {"kind": "text", "name": filename, "text": _csv(data)}
        if ext in IMAGE_TYPES:
            from PIL import Image
            with Image.open(io.BytesIO(data)) as image:
                if image.width*image.height>16000000 or max(image.size)>10000 or getattr(image,'n_frames',1)>100:
                    raise ExtractError('Image dimensions exceed the supported limit')
                image.verify()
            b64 = base64.standard_b64encode(data).decode()
            return {"kind": "image", "name": filename,
                    "data_url": f"data:{IMAGE_TYPES[ext]};base64,{b64}"}
        if ext in ("txt", "md", "json"):
            return {"kind": "text", "name": filename,
                    "text": _cap(data.decode("utf-8", errors="replace"))}
    except ExtractError:
        raise
    except Exception as e:  # noqa: BLE001
        raise ExtractError(f"Could not read {filename}; the file is invalid or unsupported") from e
    raise ExtractError(
        f"Unsupported file type: {filename}. Supported: PDF, DOCX, XLSX, CSV, TXT/MD, PNG/JPG/GIF/WEBP."
    )
