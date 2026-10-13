"""Read-only resume exporters (PDF + DOCX).

Renders the ALREADY-PERSISTED `representations` document verbatim — same summary,
experiences, chronology, employer/client/IP relationships, metrics and per-claim
provenance shown in-app. This module never reads or writes canonical career_knowledge
and never mutates the representation; it only serializes it into a downloadable file.
"""
import io
from xml.sax.saxutils import escape

CATEGORY_ORDER = ["experience", "military", "projects"]
CATEGORY_LABELS = {
    "experience": "Experience",
    "military": "Military Service",
    "projects": "Independent Projects",
}


def _category(exp: dict) -> str:
    cat = exp.get("category")
    if cat in CATEGORY_LABELS:
        return cat
    track = exp.get("track")
    if track == "intellectual_property":
        return "projects"
    if track == "military":
        return "military"
    return "experience"


def _display_employer(exp: dict) -> str:
    # IP is never rendered as employment (mirrors the in-app representation)
    if exp.get("track") == "intellectual_property":
        return exp.get("organization", "") or ""
    return exp.get("employer", "") or ""


def _meta_line(exp: dict) -> str:
    dates = exp.get("display_dates")
    if dates is None:
        dates = f'{exp.get("start", "")} – {exp.get("end", "")}'.strip(" –")
    if exp.get("client"):
        return f'Client: {exp["client"]}  |  {dates}' if dates else f'Client: {exp["client"]}'
    return dates


def _heading(exp: dict) -> str:
    """Heading per track. IP is PROJECT-FIRST using a verified project name — never a bare
    generic role, never an invented name. Civilian/military are Role — Employer/Org."""
    role = (exp.get("role") or "").strip()
    if exp.get("track") == "intellectual_property":
        project = (exp.get("organization") or "").strip()
        if project:
            parts = [p for p in (project, role) if p]
            return " — ".join(parts)
        # No verified project name: do not emit a bare generic role; label as independent work.
        return f"{role} — Independent Project" if role else "Independent Project"
    emp = (_display_employer(exp) or exp.get("organization", "") or "").strip()
    parts = [p for p in (role, emp) if p]
    return " — ".join(parts)


def _grouped(sections: dict):
    """Yield (label, [experiences]) per non-empty category, in display order."""
    exps = sections.get("experiences", [])
    for cat in CATEGORY_ORDER:
        items = [e for e in exps if _category(e) == cat]
        if items:
            yield CATEGORY_LABELS[cat], items


def build_docx(rep: dict, target_role: str, organization: str) -> bytes:
    from docx import Document
    from docx.shared import Pt, RGBColor

    sections = rep.get("sections", {})
    doc = Document()

    doc.add_heading(target_role or "Resume", level=0)

    if sections.get("summary"):
        doc.add_heading("Professional Summary", level=1)
        doc.add_paragraph(sections["summary"])

    for label, items in _grouped(sections):
        doc.add_heading(label, level=1)
        for e in items:
            title_p = doc.add_paragraph()
            title_r = title_p.add_run(_heading(e))
            title_r.bold = True
            meta_p = doc.add_paragraph()
            meta_r = meta_p.add_run(_meta_line(e))
            meta_r.italic = True
            meta_r.font.size = Pt(9)
            meta_r.font.color.rgb = RGBColor(0x66, 0x66, 0x66)
            for b in e.get("bullets", []):
                bp = doc.add_paragraph(style="List Bullet")
                bp.add_run(b.get("text", ""))

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def build_pdf(rep: dict, target_role: str, organization: str) -> bytes:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.colors import HexColor
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, HRFlowable, ListFlowable, ListItem,
    )

    sections = rep.get("sections", {})
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=letter, topMargin=0.6 * inch, bottomMargin=0.6 * inch,
        leftMargin=0.7 * inch, rightMargin=0.7 * inch, title=target_role or "Resume",
    )
    base = getSampleStyleSheet()
    name = ParagraphStyle("name", parent=base["Title"], fontSize=18, spaceAfter=2,
                          textColor=HexColor("#0B0F17"))
    sec = ParagraphStyle("sec", parent=base["Heading2"], fontSize=11, spaceBefore=10,
                         spaceAfter=4, textColor=HexColor("#0369A1"))
    body = ParagraphStyle("body", parent=base["Normal"], fontSize=10, leading=14)
    role = ParagraphStyle("role", parent=base["Normal"], fontSize=10.5, leading=13,
                          textColor=HexColor("#0B0F17"))
    meta = ParagraphStyle("meta", parent=base["Normal"], fontSize=8.5,
                          textColor=HexColor("#666666"), spaceAfter=2)
    bullet = ParagraphStyle("bullet", parent=base["Normal"], fontSize=9.5, leading=13)

    story = [Paragraph(escape(target_role or "Resume"), name)]
    story.append(HRFlowable(width="100%", thickness=0.6, color=HexColor("#CCCCCC")))

    if sections.get("summary"):
        story.append(Paragraph("Professional Summary", sec))
        story.append(Paragraph(escape(sections["summary"]), body))

    for label, items in _grouped(sections):
        story.append(Paragraph(label, sec))
        for e in items:
            heading = _heading(e)
            if heading:
                story.append(Paragraph(f'<b>{escape(heading)}</b>', role))
            meta_line = _meta_line(e)
            if meta_line:
                story.append(Paragraph(escape(meta_line), meta))
            bl = []
            for b in e.get("bullets", []):
                bl.append(ListItem(Paragraph(escape(b.get("text", "")), bullet), leftIndent=12))
            if bl:
                story.append(ListFlowable(bl, bulletType="bullet", start="•", leftIndent=10))
            story.append(Spacer(1, 5))

    doc.build(story)
    return buf.getvalue()
