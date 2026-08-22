"""Export the final report markdown as PDF (fpdf2) or PPTX (python-pptx).
Lightweight markdown handling: headings, bullets, tables-as-lines, bold strip."""

import io
import re
import datetime

# fpdf core fonts are latin-1; map the common unicode the models emit.
_CHARMAP = {
    "—": "-", "–": "-", "‘": "'", "’": "'", "“": '"',
    "”": '"', "…": "...", "→": "->", "←": "<-", "•": "-",
    " ": " ", "₹": "Rs ", "€": "EUR ", "✅": "[OK]",
    "⚠": "[!]", "✗": "[x]", "❌": "[x]", "✖": "[x]",
}


def _latin(text: str) -> str:
    for k, v in _CHARMAP.items():
        text = text.replace(k, v)
    return text.encode("latin-1", errors="replace").decode("latin-1")


def _strip_inline(text: str) -> str:
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = re.sub(r"`(.+?)`", r"\1", text)
    text = re.sub(r"\[(.+?)\]\((.+?)\)", r"\1 (\2)", text)
    return text


def _parse_md(markdown: str) -> list[tuple[str, str]]:
    """Returns [(kind, text)]: kind in h1|h2|h3|bullet|numbered|text|blank."""
    out = []
    for raw in markdown.splitlines():
        line = raw.rstrip()
        s = line.strip()
        if not s:
            out.append(("blank", ""))
        elif s.startswith("###"):
            out.append(("h3", _strip_inline(s.lstrip("#").strip())))
        elif s.startswith("##"):
            out.append(("h2", _strip_inline(s.lstrip("#").strip())))
        elif s.startswith("#"):
            out.append(("h1", _strip_inline(s.lstrip("#").strip())))
        elif re.match(r"^[-*•]\s+", s):
            out.append(("bullet", _strip_inline(re.sub(r"^[-*•]\s+", "", s))))
        elif re.match(r"^\d+[.)]\s+", s):
            out.append(("numbered", _strip_inline(s)))
        elif set(s) <= {"|", "-", ":", " "}:
            continue  # table separator row
        elif s.startswith("|"):
            out.append(("text", _strip_inline(" | ".join(c.strip() for c in s.strip("|").split("|")))))
        elif s.startswith("---") or s.startswith("==="):
            continue
        else:
            out.append(("text", _strip_inline(s)))
    return out


def to_pdf(title: str, markdown: str) -> bytes:
    from fpdf import FPDF

    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()
    pdf.set_margins(16, 16, 16)

    pdf.set_font("helvetica", "B", 18)
    pdf.multi_cell(0, 9, _latin(title), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("helvetica", "I", 9)
    pdf.set_text_color(120, 120, 120)
    pdf.multi_cell(0, 6, f"Agent Council report - {datetime.date.today().isoformat()}", new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(3)

    for kind, text in _parse_md(markdown):
        text = _latin(text)
        if kind == "blank":
            pdf.ln(2)
        elif kind == "h1":
            pdf.ln(3); pdf.set_font("helvetica", "B", 15); pdf.multi_cell(0, 8, text, new_x="LMARGIN", new_y="NEXT")
        elif kind == "h2":
            pdf.ln(2); pdf.set_font("helvetica", "B", 12.5); pdf.multi_cell(0, 7, text, new_x="LMARGIN", new_y="NEXT")
        elif kind == "h3":
            pdf.ln(1); pdf.set_font("helvetica", "B", 11); pdf.multi_cell(0, 6.5, text, new_x="LMARGIN", new_y="NEXT")
        elif kind == "bullet":
            pdf.set_font("helvetica", "", 10.5)
            pdf.multi_cell(0, 5.8, f"  -  {text}", new_x="LMARGIN", new_y="NEXT")
        elif kind == "numbered":
            pdf.set_font("helvetica", "", 10.5)
            pdf.multi_cell(0, 5.8, f"  {text}", new_x="LMARGIN", new_y="NEXT")
        else:
            pdf.set_font("helvetica", "", 10.5)
            pdf.multi_cell(0, 5.8, text, new_x="LMARGIN", new_y="NEXT")

    return bytes(pdf.output())


def to_pptx(title: str, markdown: str) -> bytes:
    from pptx import Presentation
    from pptx.util import Inches, Pt

    MAX_LINES = 9
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.33), Inches(7.5)

    # title slide
    slide = prs.slides.add_slide(prs.slide_layouts[0])
    slide.shapes.title.text = title[:120]
    if len(slide.placeholders) > 1:
        slide.placeholders[1].text = f"Agent Council report · {datetime.date.today().isoformat()}"

    def new_slide(heading: str):
        s = prs.slides.add_slide(prs.slide_layouts[1])
        s.shapes.title.text = heading[:140]
        body = s.placeholders[1].text_frame
        body.clear()
        return s, body, [0]

    slide, body, count = new_slide("Overview")
    started = False

    def add_line(text: str, level: int = 0, bold: bool = False):
        nonlocal slide, body, count, started
        if count[0] >= MAX_LINES:
            slide, body, count = new_slide(slide.shapes.title.text.rstrip(" (cont.)") + " (cont.)")
        p = body.paragraphs[0] if not started and count[0] == 0 and not body.paragraphs[0].runs else body.add_paragraph()
        p.text = text[:220]
        p.level = min(level, 4)
        p.font.size = Pt(15 if level == 0 else 13)
        p.font.bold = bold
        count[0] += 1
        started = True

    for kind, text in _parse_md(markdown):
        if kind == "blank" or not text:
            continue
        if kind in ("h1", "h2"):
            slide, body, count = new_slide(text)
        elif kind == "h3":
            add_line(text, 0, bold=True)
        elif kind in ("bullet", "numbered"):
            add_line(text, 1)
        else:
            add_line(text, 0)

    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()
