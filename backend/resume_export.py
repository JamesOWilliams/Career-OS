"""Read-only resume exporters (PDF + DOCX).

Renders the ALREADY-PERSISTED `representations` document verbatim — same summary,
experiences, chronology, employer/client/IP relationships, metrics and per-claim
provenance shown in-app. This module never reads or writes canonical career_knowledge
and never mutates the representation; it only serializes it into a downloadable file.
"""
import io
from xml.sax.saxutils import escape


def _format_phone(raw: str) -> str:
    """Display-only US phone formatting; stored value is never changed. 10-digit ->
    (XXX) XXX-XXXX, 11-digit leading 1 -> +1 (XXX) XXX-XXXX. Non-standard passes through."""
    s = (raw or "").strip()
    digits = "".join(ch for ch in s if ch.isdigit())
    if len(digits) == 10:
        return f"({digits[0:3]}) {digits[3:6]}-{digits[6:]}"
    if len(digits) == 11 and digits[0] == "1":
        return f"+1 ({digits[1:4]}) {digits[4:7]}-{digits[7:]}"
    return s


def _contact_line(ident: dict) -> str:
    phone = _format_phone(ident.get("phone", ""))
    parts = [p for p in (ident.get("email", ""), phone, ident.get("location", "")) if p]
    return "  ·  ".join(parts)


def _safe_links(ident: dict) -> list:
    out = []
    for l in ident.get("links", []) or []:
        url = (l.get("url") or "").strip()
        if url.lower().startswith("https://"):
            out.append({"label": (l.get("label") or url).strip(), "url": url})
    return out

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
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement
    from docx.opc.constants import RELATIONSHIP_TYPE as RT

    def add_hyperlink(paragraph, url, text):
        r_id = paragraph.part.relate_to(url, RT.HYPERLINK, is_external=True)
        link = OxmlElement("w:hyperlink")
        link.set(qn("r:id"), r_id)
        r = OxmlElement("w:r")
        rpr = OxmlElement("w:rPr")
        color = OxmlElement("w:color"); color.set(qn("w:val"), "0563C1"); rpr.append(color)
        u = OxmlElement("w:u"); u.set(qn("w:val"), "single"); rpr.append(u)
        r.append(rpr)
        t = OxmlElement("w:t"); t.text = text; r.append(t)
        link.append(r)
        paragraph._p.append(link)

    sections = rep.get("sections", {})
    ident = sections.get("identity", {}) or {}
    doc = Document()

    # Identity header: name prominent, then contact, then clickable links.
    doc.add_heading(ident.get("full_name") or target_role or "Resume", level=0)
    contact = _contact_line(ident)
    if contact:
        cp = doc.add_paragraph()
        cr = cp.add_run(contact)
        cr.font.size = Pt(9.5)
        cr.font.color.rgb = RGBColor(0x44, 0x44, 0x44)
    links = _safe_links(ident)
    if links:
        lp = doc.add_paragraph()
        for i, l in enumerate(links):
            if i:
                lp.add_run("   ·   ").font.size = Pt(9)
            add_hyperlink(lp, l["url"], l["label"])

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
        SimpleDocTemplate, Paragraph, Spacer, HRFlowable, ListFlowable, ListItem, KeepTogether,
    )

    sections = rep.get("sections", {})
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=letter, topMargin=0.55 * inch, bottomMargin=0.5 * inch,
        leftMargin=0.7 * inch, rightMargin=0.7 * inch, title=target_role or "Resume",
    )
    base = getSampleStyleSheet()
    name = ParagraphStyle("name", parent=base["Title"], fontSize=18, spaceAfter=2,
                          textColor=HexColor("#0B0F17"))
    sec = ParagraphStyle("sec", parent=base["Heading2"], fontSize=11, spaceBefore=7,
                         spaceAfter=3, textColor=HexColor("#0369A1"))
    body = ParagraphStyle("body", parent=base["Normal"], fontSize=10, leading=13.5)
    contact = ParagraphStyle("contact", parent=base["Normal"], fontSize=9.5,
                             textColor=HexColor("#444444"), spaceAfter=1)
    linkst = ParagraphStyle("linkst", parent=base["Normal"], fontSize=9.5,
                            textColor=HexColor("#0563C1"), spaceAfter=2)
    role = ParagraphStyle("role", parent=base["Normal"], fontSize=10.5, leading=12.5,
                          textColor=HexColor("#0B0F17"))
    meta = ParagraphStyle("meta", parent=base["Normal"], fontSize=8.5,
                          textColor=HexColor("#666666"), spaceAfter=2)
    bullet = ParagraphStyle("bullet", parent=base["Normal"], fontSize=9.5, leading=12.5)

    ident = sections.get("identity", {}) or {}
    story = [Paragraph(escape(ident.get("full_name") or target_role or "Resume"), name)]
    cline = _contact_line(ident)
    if cline:
        story.append(Paragraph(escape(cline), contact))
    links = _safe_links(ident)
    if links:
        link_html = "  ·  ".join(
            f'<a href="{escape(l["url"])}" color="#0563C1">{escape(l["label"])}</a>' for l in links
        )
        story.append(Paragraph(link_html, linkst))
    story.append(HRFlowable(width="100%", thickness=0.6, color=HexColor("#CCCCCC")))

    if sections.get("summary"):
        story.append(Paragraph("Professional Summary", sec))
        story.append(Paragraph(escape(sections["summary"]), body))

    for label, items in _grouped(sections):
        story.append(Paragraph(label, sec))
        for i, e in enumerate(items):
            block = []
            heading = _heading(e)
            if heading:
                block.append(Paragraph(f'<b>{escape(heading)}</b>', role))
            meta_line = _meta_line(e)
            if meta_line:
                block.append(Paragraph(escape(meta_line), meta))
            bl = []
            for b in e.get("bullets", []):
                bl.append(ListItem(Paragraph(escape(b.get("text", "")), bullet), leftIndent=12))
            if bl:
                block.append(ListFlowable(bl, bulletType="bullet", start="•", leftIndent=10))
            block.append(Spacer(1, 3))
            # Keep each entry's heading/date/bullets together; keep the section label with its
            # first entry so no heading is orphaned at the bottom of a page.
            if i == 0:
                story[-1:] = [KeepTogether([story[-1]] + block)]
            else:
                story.append(KeepTogether(block))

    doc.build(story)
    return buf.getvalue()
