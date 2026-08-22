"""Styled exports of the final report markdown.

PDF: fpdf2 — branded cover band, section headings with accent rules, real
tables (striped, dark header), embedded diagram images, page footer.
PPTX: python-pptx — dark title slide, styled section slides, native tables,
embedded diagram images.

Mermaid diagrams are rasterized CLIENT-side (browser canvas) and posted as
PNG data URLs in `diagrams`, consumed in order of appearance.
"""

import base64
import io
import re
import datetime
from pathlib import Path

# Brand palette (matches the app UI)
GOLD = (232, 176, 75)
DARK = (23, 29, 36)
MUTED = (110, 122, 134)
ROW_FILL = (245, 246, 248)

# Emoji/symbols DejaVu lacks — mapped regardless of font.
_CHARMAP = {
    " ": " ", "✅": "[OK]", "⚠": "[!]", "✗": "[x]", "❌": "[x]", "✖": "[x]",
}
# Typographic chars only stripped when stuck on a latin-1 core font.
_LATIN_EXTRA = {
    "—": "-", "–": "-", "‘": "'", "’": "'", "“": '"',
    "”": '"', "…": "...", "→": "->", "←": "<-", "•": "-",
    "₹": "Rs ", "€": "EUR ",
}

_FONT_DIR = Path(__file__).resolve().parent / "assets" / "fonts"
_UNICODE_FONTS = [  # regular, bold — first pair that exists wins
    (str(_FONT_DIR / "DejaVuSans.ttf"), str(_FONT_DIR / "DejaVuSans-Bold.ttf")),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
     "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ("/usr/share/fonts/dejavu/DejaVuSans.ttf",
     "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"),
]


def _clean(text: str, latin_only: bool) -> str:
    for k, v in _CHARMAP.items():
        text = text.replace(k, v)
    if latin_only:
        for k, v in _LATIN_EXTRA.items():
            text = text.replace(k, v)
        text = text.encode("latin-1", errors="replace").decode("latin-1")
    return text


_SOURCE_RE = re.compile(r"\[?\[source:\s*(\S+?)\s*\]\]?", re.IGNORECASE)


def _extract_sources(markdown: str) -> tuple[str, list[str]]:
    """Replace inline `[source: url]` citations with compact [n] markers and
    return the ordered, deduped url list — raw URLs mid-sentence are the single
    biggest readability killer in the exports."""
    sources: list[str] = []

    def repl(m):
        url = m.group(1).rstrip(".,;)")
        if url not in sources:
            sources.append(url)
        return f"[{sources.index(url) + 1}]"

    return _SOURCE_RE.sub(repl, markdown), sources


def _strip_inline(text: str, keep_bold: bool = False) -> str:
    if not keep_bold:
        text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"\1", text)
    text = re.sub(r"`(.+?)`", r"\1", text)
    text = re.sub(r"\[(.+?)\]\((.+?)\)", r"\1", text)
    return text


def _parse_md(markdown: str, keep_bold: bool = False) -> list[tuple]:
    """[(kind, payload)]: h1/h2/h3/bullet/numbered/text -> str;
    table -> list[list[str]]; mermaid/code -> str; blank -> ''."""
    items: list[tuple] = []
    lines = markdown.splitlines()
    i = 0
    while i < len(lines):
        s = lines[i].strip()
        if s.startswith("```"):
            lang = s[3:].strip().lower()
            block = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                block.append(lines[i])
                i += 1
            i += 1
            items.append(("mermaid" if lang == "mermaid" else "code", "\n".join(block)))
            continue
        if s.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(set(c) <= {"-", ":", " "} for c in cells):
                    rows.append([_strip_inline(c) for c in cells])
                i += 1
            if rows:
                items.append(("table", rows))
            continue
        if not s:
            items.append(("blank", ""))
        elif s.startswith("###"):
            items.append(("h3", _strip_inline(s.lstrip("#").strip())))
        elif s.startswith("##"):
            items.append(("h2", _strip_inline(s.lstrip("#").strip())))
        elif s.startswith("#"):
            items.append(("h1", _strip_inline(s.lstrip("#").strip())))
        elif re.match(r"^[-*•]\s+", s):
            items.append(("bullet", _strip_inline(re.sub(r"^[-*•]\s+", "", s), keep_bold)))
        elif re.match(r"^\d+[.)]\s+", s):
            items.append(("numbered", _strip_inline(s, keep_bold)))
        elif s.startswith("---") or s.startswith("==="):
            pass
        else:
            items.append(("text", _strip_inline(s, keep_bold)))
        i += 1
    return items


def _png_size(data: bytes) -> tuple[int, int]:
    import struct
    try:
        if data[:8] == b"\x89PNG\r\n\x1a\n":
            w, h = struct.unpack(">II", data[16:24])
            return int(w), int(h)
    except Exception:  # noqa: BLE001
        pass
    return 1600, 900


def _decode_diagrams(diagrams: list | None) -> list[bytes | None]:
    out = []
    for d in diagrams or []:
        try:
            if isinstance(d, str) and d.startswith("data:image"):
                d = d.split(",", 1)[1]
            out.append(base64.b64decode(d) if d else None)
        except Exception:  # noqa: BLE001
            out.append(None)
    return out


# ---------------- PDF ----------------

def to_pdf(title: str, markdown: str, diagrams: list | None = None) -> bytes:
    import os
    from fpdf import FPDF
    from fpdf.fonts import FontFace

    markdown, sources = _extract_sources(markdown)

    unicode_ok = False
    font_paths = None
    for reg, bold in _UNICODE_FONTS:
        if os.path.exists(reg) and os.path.exists(bold):
            font_paths = (reg, bold)
            unicode_ok = True
            break

    class ReportPDF(FPDF):
        def header(self):
            if self.page_no() == 1:
                return
            self.set_font(BODY, "", 8)
            self.set_text_color(*MUTED)
            self.cell(0, 8, _clean(title, not unicode_ok)[:90], align="L")
            self.set_x(-40)
            self.cell(0, 8, "Agent Council", align="R")
            self.ln(10)

        def footer(self):
            self.set_y(-13)
            self.set_font(BODY, "", 8)
            self.set_text_color(*MUTED)
            self.cell(0, 6, str(self.page_no()), align="C")

    pdf = ReportPDF(format="A4")
    if unicode_ok:
        pdf.add_font("Body", "", font_paths[0])
        pdf.add_font("Body", "B", font_paths[1])
        BODY = "Body"
    else:
        BODY = "helvetica"

    def C(t):
        return _clean(t, not unicode_ok)

    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.set_margins(17, 14, 17)
    pdf.add_page()

    # cover band
    pdf.set_fill_color(*DARK)
    pdf.rect(0, 0, 210, 46, style="F")
    pdf.set_fill_color(*GOLD)
    pdf.rect(17, 12, 14, 1.6, style="F")
    pdf.set_xy(17, 17)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font(BODY, "B", 19)
    pdf.multi_cell(176, 8.5, C(title), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font(BODY, "", 9.5)
    pdf.set_text_color(*GOLD)
    pdf.cell(0, 8, f"Agent Council · market research, sharpened by review · {datetime.date.today().isoformat()}",
             new_x="LMARGIN", new_y="NEXT")
    pdf.set_y(max(pdf.get_y() + 6, 54))
    pdf.set_text_color(*DARK)

    diagram_bytes = _decode_diagrams(diagrams)
    di = 0
    usable_w = 176

    def heading(text, size, accent=False):
        if pdf.get_y() > 250:
            pdf.add_page()
        pdf.ln(3)
        pdf.set_font(BODY, "B", size)
        pdf.set_text_color(*DARK)
        pdf.multi_cell(usable_w, size * 0.5, C(text), new_x="LMARGIN", new_y="NEXT")
        if accent:
            pdf.set_fill_color(*GOLD)
            pdf.rect(17, pdf.get_y() + 0.6, 22, 1.1, style="F")
            pdf.ln(4)
        else:
            pdf.ln(1.2)

    for kind, payload in _parse_md(markdown, keep_bold=True):
        if kind == "blank":
            pdf.ln(1.8)
        elif kind == "h1":
            heading(payload, 16.5, accent=True)
        elif kind == "h2":
            heading(payload, 13, accent=True)
        elif kind == "h3":
            heading(payload, 11.5)
        elif kind == "table":
            rows = payload
            ncols = max(len(r) for r in rows)
            rows = [r + [""] * (ncols - len(r)) for r in rows]
            pdf.set_font(BODY, "", 8.6)
            pdf.set_text_color(*DARK)
            pdf.set_draw_color(210, 214, 219)
            pdf.set_fill_color(*ROW_FILL)  # the "current fill" some fill modes fall back to
            style = FontFace(emphasis="BOLD", color=(255, 255, 255), fill_color=DARK)
            try:
                with pdf.table(first_row_as_headings=True, headings_style=style,
                               line_height=5.6, text_align="LEFT",
                               cell_fill_color=ROW_FILL, cell_fill_mode="EVEN_ROWS",
                               borders_layout="HORIZONTAL_LINES", padding=1.6) as tbl:
                    for r in rows:
                        row = tbl.row()
                        for c in r:
                            row.cell(C(_strip_inline(c)))
            except Exception:  # noqa: BLE001 — a pathological table falls back to text
                for r in rows:
                    pdf.multi_cell(usable_w, 5, C(" | ".join(r)), new_x="LMARGIN", new_y="NEXT")
            pdf.ln(2.5)
        elif kind == "mermaid":
            img = diagram_bytes[di] if di < len(diagram_bytes) else None
            di += 1
            if img:
                iw, ih = _png_size(img)
                w = usable_w - 10
                h = w * ih / iw if iw else 0
                if h > 150:  # cap tall diagrams to the page
                    h = 150
                    w = h * iw / ih
                if pdf.get_y() + h > 270:
                    pdf.add_page()
                pdf.ln(2)
                pdf.image(io.BytesIO(img), x=17 + (usable_w - w) / 2, w=w)
                pdf.ln(3)
        elif kind == "code":
            pdf.set_font("courier", "", 8.2)
            pdf.set_text_color(60, 66, 72)
            for ln in payload.splitlines():
                pdf.multi_cell(usable_w, 4.4, C(ln), new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(*DARK)
            pdf.ln(1.5)
        elif kind == "bullet":
            pdf.set_font(BODY, "", 10.4)
            pdf.set_text_color(*DARK)
            x = pdf.get_x()
            pdf.set_fill_color(*GOLD)
            pdf.rect(x + 1.6, pdf.get_y() + 2.4, 1.5, 1.5, style="F")
            pdf.set_x(x + 5.5)
            pdf.multi_cell(usable_w - 5.5, 5.7, C(payload), new_x="LMARGIN", new_y="NEXT",
                           markdown=True)
            pdf.ln(0.6)
        elif kind == "numbered":
            pdf.set_font(BODY, "", 10.4)
            pdf.set_text_color(*DARK)
            pdf.set_x(pdf.get_x() + 3)
            pdf.multi_cell(usable_w - 3, 5.7, C(payload), new_x="LMARGIN", new_y="NEXT", markdown=True)
            pdf.ln(0.6)
        else:
            pdf.set_font(BODY, "", 10.4)
            pdf.set_text_color(*DARK)
            pdf.multi_cell(usable_w, 5.8, C(payload), new_x="LMARGIN", new_y="NEXT",
                           markdown=True, align="J")

    if sources:
        heading("Sources", 13, accent=True)
        pdf.set_font(BODY, "", 8.4)
        for i, url in enumerate(sources, 1):
            pdf.set_text_color(*MUTED)
            pdf.cell(8, 4.6, f"[{i}]")
            pdf.set_text_color(46, 100, 160)
            pdf.multi_cell(usable_w - 8, 4.6, C(url), new_x="LMARGIN", new_y="NEXT", link=url)
        pdf.set_text_color(*DARK)

    return bytes(pdf.output())


# ---------------- PPTX ----------------

def to_pptx(title: str, markdown: str, diagrams: list | None = None) -> bytes:
    from pptx import Presentation
    from pptx.dml.color import RGBColor
    from pptx.util import Inches, Pt, Emu

    markdown, sources = _extract_sources(markdown)

    C_DARK = RGBColor(*DARK)
    C_GOLD = RGBColor(*GOLD)
    C_MUTED = RGBColor(*MUTED)
    C_WHITE = RGBColor(0xFF, 0xFF, 0xFF)
    C_ROW = RGBColor(*ROW_FILL)
    HEAD_FONT = "Georgia"
    BODY_FONT = "Calibri"
    SW, SH = Inches(13.33), Inches(7.5)
    MAX_UNITS = 11  # rough vertical budget per slide (1 line ≈ 1 unit)

    prs = Presentation()
    prs.slide_width, prs.slide_height = SW, SH
    blank = prs.slide_layouts[6]
    diagram_bytes = _decode_diagrams(diagrams)
    di = 0

    def solid_bg(slide, color):
        slide.background.fill.solid()
        slide.background.fill.fore_color.rgb = color

    def bar(slide, x, y, w, h, color):
        from pptx.enum.shapes import MSO_SHAPE
        sh = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, x, y, w, h)
        sh.fill.solid()
        sh.fill.fore_color.rgb = color
        sh.line.fill.background()
        return sh

    def textbox(slide, x, y, w, h):
        tb = slide.shapes.add_textbox(x, y, w, h)
        tb.text_frame.word_wrap = True
        return tb.text_frame

    # --- title slide ---
    s = prs.slides.add_slide(blank)
    solid_bg(s, C_DARK)
    bar(s, Inches(0.9), Inches(2.1), Inches(1.1), Inches(0.06), C_GOLD)
    tf = textbox(s, Inches(0.85), Inches(2.35), Inches(11.6), Inches(2.6))
    p = tf.paragraphs[0]
    p.text = title[:160]
    p.font.name = HEAD_FONT
    p.font.size = Pt(40)
    p.font.bold = True
    p.font.color.rgb = C_WHITE
    tf2 = textbox(s, Inches(0.9), Inches(5.6), Inches(11), Inches(0.8))
    p = tf2.paragraphs[0]
    p.text = f"Agent Council · market research, sharpened by review · {datetime.date.today().isoformat()}"
    p.font.name = BODY_FONT
    p.font.size = Pt(15)
    p.font.color.rgb = C_GOLD

    state = {"slide": None, "tf": None, "used": 0.0, "title": ""}

    def new_slide(heading):
        s = prs.slides.add_slide(blank)
        solid_bg(s, C_WHITE)
        tf = textbox(s, Inches(0.75), Inches(0.45), Inches(11.9), Inches(0.95))
        p = tf.paragraphs[0]
        p.text = heading[:120]
        p.font.name = HEAD_FONT
        p.font.size = Pt(26)
        p.font.bold = True
        p.font.color.rgb = C_DARK
        bar(s, Inches(0.78), Inches(1.32), Inches(0.9), Inches(0.05), C_GOLD)
        body = textbox(s, Inches(0.78), Inches(1.6), Inches(11.8), Inches(5.5))
        state.update(slide=s, tf=body, used=0.0, title=heading, first=True)

    def ensure(units):
        if state["slide"] is None or state["used"] + units > MAX_UNITS:
            base = (state["title"] or "Overview").replace(" (cont.)", "")
            new_slide(base + (" (cont.)" if state["slide"] is not None and state["title"] else ""))

    def add_para(text, level=0, bold=False, color=None, size=None):
        ensure(1 + len(text) // 110)
        tf = state["tf"]
        p = tf.paragraphs[0] if state.get("first") else tf.add_paragraph()
        state["first"] = False
        p.text = text[:300]
        p.level = min(level, 3)
        p.font.name = BODY_FONT
        p.font.size = Pt(size or (16 if level == 0 else 14))
        p.font.bold = bold
        p.font.color.rgb = color or C_DARK
        p.space_after = Pt(6)
        state["used"] += 1 + len(text) // 110

    def add_table(rows):
        ncols = max(len(r) for r in rows)
        rows = [r + [""] * (ncols - len(r)) for r in rows]
        chunks = [rows[0:1] + rows[i:i + 9] for i in range(1, len(rows), 9)] if len(rows) > 10 else [rows]
        for chunk in chunks:
            # Tables are absolutely positioned — give each a clean slide region
            # so it can never overlap the flowed text above it.
            if state["slide"] is None or state["used"] > 0.5:
                new_slide((state["title"] or "Overview").replace(" (cont.)", "") + " (cont.)"
                          if state["slide"] is not None else (state["title"] or "Overview"))
            top = Inches(1.6)
            h = Inches(0.4 * len(chunk))
            shape = state["slide"].shapes.add_table(len(chunk), ncols, Inches(0.78), top, Inches(11.8), h)
            t = shape.table
            for ci in range(ncols):
                for ri, r in enumerate(chunk):
                    cell = t.cell(ri, ci)
                    cell.text = r[ci][:180]
                    para = cell.text_frame.paragraphs[0]
                    para.font.name = BODY_FONT
                    para.font.size = Pt(11.5)
                    if ri == 0:
                        cell.fill.solid()
                        cell.fill.fore_color.rgb = C_DARK
                        para.font.color.rgb = C_WHITE
                        para.font.bold = True
                    else:
                        cell.fill.solid()
                        cell.fill.fore_color.rgb = C_ROW if ri % 2 == 0 else C_WHITE
                        para.font.color.rgb = C_DARK
            # the body textbox shares this region — anything after the table
            # must open a fresh slide or it would render on top of it
            state["used"] = MAX_UNITS

    def add_image(img: bytes):
        ensure(MAX_UNITS)  # diagrams get their own slide area
        try:
            from PIL import Image  # noqa: F401 — pptx sizes without PIL too
        except Exception:  # noqa: BLE001
            pass
        pic = state["slide"].shapes.add_picture(io.BytesIO(img), Inches(1.2), Inches(1.7), width=Inches(10.9))
        if pic.height > Emu(int(Inches(5.4))):
            ratio = Inches(5.4) / pic.height
            pic.height = Emu(int(pic.height * ratio))
            pic.width = Emu(int(pic.width * ratio))
            pic.left = Emu(int((SW - pic.width) / 2))
        state["used"] = MAX_UNITS  # force a fresh slide for what follows

    for kind, payload in _parse_md(markdown):
        if kind == "blank":
            continue
        if kind in ("h1", "h2"):
            new_slide(payload)
        elif kind == "h3":
            add_para(payload, 0, bold=True, size=17)
        elif kind == "table":
            add_table(payload)
        elif kind == "mermaid":
            img = diagram_bytes[di] if di < len(diagram_bytes) else None
            di += 1
            if img:
                add_image(img)
        elif kind == "code":
            for ln in payload.splitlines()[:10]:
                add_para(ln, 1, size=12, color=C_MUTED)
        elif kind == "bullet":
            add_para(f"•  {payload}", 1)
        elif kind == "numbered":
            add_para(payload, 1)
        else:
            add_para(payload, 0)

    if sources:
        new_slide("Sources")
        for i, url in enumerate(sources[:14], 1):
            add_para(f"[{i}]  {url}", 0, size=12, color=C_MUTED)
        if len(sources) > 14:
            add_para(f"…and {len(sources) - 14} more (see PDF export)", 0, size=12, color=C_MUTED)

    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()
