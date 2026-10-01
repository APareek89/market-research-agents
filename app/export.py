"""Styled exports of the final report markdown.

PDF: fpdf2 — branded cover band, section headings with accent rules, real
tables (striped, dark header), embedded diagram images, page footer.
PPTX: python-pptx — dark title slide, styled section slides, native tables,
embedded diagram images.

Mermaid diagrams are rasterized CLIENT-side (browser canvas) and posted as
PNG data URLs in `diagrams`, consumed in order of appearance.
"""

import base64
import json
from urllib.parse import urlparse
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
        parsed=urlparse(url)
        if parsed.scheme not in {'http','https'} or not parsed.hostname or any(ord(c)<32 for c in url) or len(url)>2048:
            return '[unsupported source link]'
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
    from PIL import Image
    if not isinstance(diagrams or [],list) or len(diagrams or [])>12:
        raise ValueError('At most 12 diagram images are allowed')
    out=[];total=0
    for diagram in diagrams or []:
        if diagram is None or diagram=='':
            out.append(None);continue
        if not isinstance(diagram,str) or not diagram.startswith('data:image/png;base64,') or len(diagram)>2800000:
            raise ValueError('Diagrams must be bounded PNG data URLs')
        try:
            data=base64.b64decode(diagram.split(',',1)[1],validate=True)
            total+=len(data)
            if len(data)>2*1024*1024 or total>6*1024*1024:raise ValueError('Diagram byte limit exceeded')
            with Image.open(io.BytesIO(data)) as image:
                if image.format!='PNG' or image.width*image.height>16000000 or max(image.size)>10000:
                    raise ValueError('Diagram dimensions exceed the limit')
                image.verify()
        except Exception as exc:
            raise ValueError('Invalid or oversized diagram image') from exc
        out.append(data)
    return out

def validate_export(payload):
    if not isinstance(payload,dict):raise ValueError('Invalid export request')
    fmt=payload.get('format','pdf');title=payload.get('title') or 'Market research report';markdown=payload.get('markdown','');diagrams=payload.get('diagrams') or []
    if fmt not in {'pdf','pptx'}:raise ValueError('Choose PDF or PPTX')
    if not isinstance(title,str) or len(title)>160 or not isinstance(markdown,str) or not markdown.strip() or len(markdown)>150000 or len(markdown.splitlines())>3000:
        raise ValueError('Export text is empty or exceeds the limit')
    _decode_diagrams(diagrams)
    return fmt,title,markdown,diagrams


# ---------------- PDF: Typst engine (primary) ----------------

def pdf_engine() -> str:
    try:
        import typst  # noqa: F401
        return "typst"
    except Exception:  # noqa: BLE001
        return "fpdf2"


def _t_escape(text: str) -> str:
    """Escape typst markup-mode specials in a plain text run. '/' included:
    '//' opens a typst comment and would swallow every URL."""
    out = []
    for ch in text:
        if ch in '\\#$*_`@<>[]~/':
            out.append("\\" + ch)
        else:
            out.append(ch)
    return "".join(out)


def _t_inline(text: str) -> str:
    """Markdown inline → typst: **bold** becomes *bold*, the rest escaped."""
    parts = re.split(r"\*\*(.+?)\*\*", text)
    out = []
    for i, p in enumerate(parts):
        out.append(f"*{_t_escape(p)}*" if i % 2 else _t_escape(p))
    return "".join(out)


_T_PREAMBLE = """
#let dark = rgb("#171d24")
#let gold = rgb("#e8b04b")
#let muted = rgb("#6e7a86")
#let rowfill = rgb("#f5f6f8")
#set page("a4", margin: (top: 2.5cm, bottom: 2.3cm, x: 2.1cm),
  header: context { if counter(page).get().first() > 1 [
    #text(8pt, fill: muted)[__HEADER_TITLE__ #h(1fr) Agent Council]
  ] },
  footer: context [ #align(center, text(8.5pt, fill: muted, counter(page).display())) ])
#set text(font: ("Libertinus Serif", "Linux Libertine", "DejaVu Sans"), size: 10.3pt, fill: rgb("#20262d"))
#set par(justify: true, leading: 0.62em)
#show heading.where(level: 1): it => block(above: 1.5em, below: 0.4em)[
  #text(size: 16pt, weight: "bold", fill: dark, it.body)
  #v(-0.5em)
  #line(length: 2.1cm, stroke: 1.4pt + gold)
]
#show heading.where(level: 2): it => block(above: 1.3em, below: 0.4em)[
  #text(size: 12.8pt, weight: "bold", fill: dark, it.body)
  #v(-0.55em)
  #line(length: 1.5cm, stroke: 1.1pt + gold)
]
#show heading.where(level: 3): it => block(above: 1.1em, below: 0.35em)[
  #text(size: 11pt, weight: "bold", fill: dark, it.body)
]
#set list(marker: text(fill: gold, size: 7pt)[■], indent: 0.35em, body-indent: 0.55em)
#set enum(indent: 0.35em, body-indent: 0.55em)
#show link: it => text(fill: rgb("#2e64a0"), it)

#block(width: 100%, fill: dark, inset: (x: 1.35cm, y: 1.15cm), radius: 3pt)[
  #line(length: 1.2cm, stroke: 2pt + gold)
  #v(0.35em)
  #text(size: 19.5pt, weight: "bold", fill: white, font: ("Libertinus Serif", "Linux Libertine", "DejaVu Sans"))[__TITLE__]
  #v(0.25em)
  #text(size: 9pt, fill: gold)[Agent Council · market research, sharpened by review · __DATE__]
]
#v(0.9em)
"""


def _pdf_via_typst(title: str, markdown: str, diagrams: list | None = None) -> bytes:
    import os
    import tempfile

    import typst

    markdown, sources = _extract_sources(markdown)
    items = _parse_md(markdown, keep_bold=True)
    diagram_bytes = _decode_diagrams(diagrams)

    body: list[str] = []
    di = 0
    i = 0
    while i < len(items):
        kind, payload = items[i]
        if kind in ("bullet", "numbered"):
            # consecutive items become one typst list/enum block
            marker = "-" if kind == "bullet" else "+"
            while i < len(items) and items[i][0] == kind:
                text = items[i][1]
                if kind == "numbered":
                    text = re.sub(r"^\d+[.)]\s+", "", text)
                body.append(f"{marker} {_t_inline(text)}")
                i += 1
            body.append("")
            continue
        if kind == "blank":
            body.append("")
        elif kind == "h1":
            body.append(f"= {_t_inline(payload)}")
        elif kind == "h2":
            body.append(f"== {_t_inline(payload)}")
        elif kind == "h3":
            body.append(f"=== {_t_inline(payload)}")
        elif kind == "table":
            rows = payload
            ncols = max(len(r) for r in rows)
            rows = [r + [""] * (ncols - len(r)) for r in rows]
            cells = []
            for ri, r in enumerate(rows):
                for c in r:
                    cell = _t_inline(c)
                    if ri == 0:
                        cell = f'text(fill: white, weight: "bold", size: 8.6pt)[{cell}]'
                    else:
                        cell = f"text(size: 8.8pt)[{cell}]"
                    cells.append(f"[#{cell}]")
            body.append(
                "#block(above: 0.9em, below: 0.9em)[#table(\n"
                f"  columns: {ncols},\n"
                "  inset: (x: 7pt, y: 5.5pt),\n"
                "  stroke: (x, y) => (bottom: 0.5pt + rgb(\"#d2d6db\")),\n"
                "  fill: (x, y) => if y == 0 { dark } else if calc.even(y) { rowfill } else { white },\n"
                "  " + ", ".join(cells) + "\n)]")
        elif kind == "mermaid":
            img = diagram_bytes[di] if di < len(diagram_bytes) else None
            di += 1
            if img is not None:
                body.append(f'#align(center, image("d{di - 1}.png", width: 86%))')
        elif kind == "code":
            body.append('#raw('+json.dumps(payload,ensure_ascii=False)+', block: true)')
        else:
            body.append(_t_inline(payload))
        i += 1

    if sources:
        body.append("= Sources")
        for n, url in enumerate(sources, 1):
            safe = _t_escape(url)
            body.append(f'#text(size: 8.4pt)[[{n}] #link({json.dumps(url,ensure_ascii=False)})[{safe}]] \\')

    doc = (_T_PREAMBLE
           .replace("__HEADER_TITLE__", _t_escape(title[:80]))
           .replace("__TITLE__", _t_inline(title))
           .replace("__DATE__", datetime.date.today().isoformat())
           ) + "\n".join(body)

    with tempfile.TemporaryDirectory() as tmp:
        for n, img in enumerate(diagram_bytes):
            if img is not None:
                with open(os.path.join(tmp, f"d{n}.png"), "wb") as f:
                    f.write(img)
        main = os.path.join(tmp, "report.typ")
        with open(main, "w", encoding="utf-8") as f:
            f.write(doc)
        return bytes(typst.compile(main, root=tmp, font_paths=[str(_FONT_DIR)]))


def to_pdf(title: str, markdown: str, diagrams: list | None = None) -> bytes:
    try:
        return _pdf_via_typst(title, markdown, diagrams)
    except Exception as e:  # noqa: BLE001 — never fail an export on the new engine
        print("[export] primary layout unavailable; using PDF fallback", flush=True)
        return _pdf_via_fpdf(title, markdown, diagrams)


# ---------------- PDF: fpdf2 engine (fallback) ----------------

def _pdf_via_fpdf(title: str, markdown: str, diagrams: list | None = None) -> bytes:
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

    state = {"slide": None, "tf": None, "used": 0.0, "title": "", "section": 0}

    def add_footer(s):
        n = len(prs.slides)
        tf = textbox(s, Inches(0.78), Inches(7.02), Inches(11.8), Inches(0.35))
        p = tf.paragraphs[0]
        p.text = "Agent Council"
        p.font.name = BODY_FONT
        p.font.size = Pt(9)
        p.font.color.rgb = C_MUTED
        tf2 = textbox(s, Inches(11.9), Inches(7.02), Inches(0.7), Inches(0.35))
        p2 = tf2.paragraphs[0]
        p2.text = str(n)
        p2.font.name = BODY_FONT
        p2.font.size = Pt(9)
        p2.font.color.rgb = C_MUTED

    def divider_slide(heading):
        state["section"] += 1
        s = prs.slides.add_slide(blank)
        solid_bg(s, C_DARK)
        tf = textbox(s, Inches(0.95), Inches(2.5), Inches(2.5), Inches(0.5))
        p = tf.paragraphs[0]
        p.text = f"{state['section']:02d}"
        p.font.name = HEAD_FONT
        p.font.size = Pt(22)
        p.font.bold = True
        p.font.color.rgb = C_GOLD
        bar(s, Inches(1.0), Inches(3.15), Inches(1.1), Inches(0.06), C_GOLD)
        tf2 = textbox(s, Inches(0.95), Inches(3.4), Inches(11.4), Inches(2.2))
        p2 = tf2.paragraphs[0]
        p2.text = heading[:140]
        p2.font.name = HEAD_FONT
        p2.font.size = Pt(34)
        p2.font.bold = True
        p2.font.color.rgb = C_WHITE
        # content resumes on a fresh white slide under this section
        state.update(slide=None, tf=None, used=0.0, title=heading, first=True)

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
        add_footer(s)
        body = textbox(s, Inches(0.78), Inches(1.6), Inches(11.8), Inches(5.3))
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
            # content-aware column widths (min share so tiny cols stay readable)
            weights = [max(3, max(len(r[ci]) for r in chunk)) for ci in range(ncols)]
            total = sum(weights)
            for ci in range(ncols):
                t.columns[ci].width = Emu(int(Inches(11.8) * max(weights[ci] / total, 0.55 / ncols)))
            for ci in range(ncols):
                for ri, r in enumerate(chunk):
                    cell = t.cell(ri, ci)
                    cell.text = r[ci][:180]
                    cell.margin_left = Inches(0.09)
                    cell.margin_right = Inches(0.09)
                    cell.margin_top = Inches(0.045)
                    cell.margin_bottom = Inches(0.045)
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
        if kind == "h1":
            divider_slide(payload)
        elif kind == "h2":
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
