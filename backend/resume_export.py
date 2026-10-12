"""Read-only resume exporters (PDF + DOCX).

Renders the ALREADY-PERSISTED `representations` document verbatim — same summary,
experiences, chronology, employer/client/IP relationships, metrics and per-claim
provenance shown in-app. This module never reads or writes canonical career_knowledge
and never mutates the representation; it only serializes it into a downloadable file.
"""
import io
from xml.sax.saxutils import escape


def _display_employer(exp: dict) -> str:
    # IP is never rendered as employment (mirrors the in-app representation)
    if exp.get("track") == "intellectual_property":
        return exp.get("organization", "") or ""
    return exp.get("employer", "") or ""


def _meta_line(exp: dict) -> str:
    dates = f'{exp.get("start", "")} – {exp.get("end", "")}'.strip(" –")
    if exp.get("client"):
        return f'Client: {exp["client"]}  |  {dates}'
    return dates


def build_docx(rep: dict, target_role: str, organization: str) -> bytes:
    from docx import Document
    from docx.shared import Pt, RGBColor

    sections = rep.get("sections", {})
    doc = Document()

    doc.add_heading(target_role or "Resume", level=0)
    if organization:
        p = doc.add_paragraph()
        r = p.add_run(f"Target: {organization}")
        r.italic = True

    if sections.get("summary"):
        doc.add_heading("Professional Summary", level=1)
        doc.add_paragraph(sections["summary"])

    doc.add_heading("Experience", level=1)
    for e in sections.get("experiences", []):
        emp = _display_employer(e)
        title_p = doc.add_paragraph()
        title_r = title_p.add_run(f'{e.get("role", "")} — {emp}'.strip(" —"))
        title_r.bold = True
        meta_p = doc.add_paragraph()
        meta_r = meta_p.add_run(_meta_line(e))
        meta_r.italic = True
        meta_r.font.size = Pt(9)
        meta_r.font.color.rgb = RGBColor(0x66, 0x66, 0x66)
        for b in e.get("bullets", []):
            bp = doc.add_paragraph(style="List Bullet")
            bp.add_run(b.get("text", ""))
            tag = bp.add_run(f'  [{b.get("source_node_id", "")}]')
            tag.font.size = Pt(7)
            tag.font.color.rgb = RGBColor(0x88, 0x88, 0x88)

    foot = doc.add_paragraph()
    fr = foot.add_run(
        f'Resume Template v{rep.get("template_version", "1.0")} · '
        f'Contract v{rep.get("contract_version", "1.0")} · '
        f'{len(rep.get("claim_provenance", []))} traceable claims'
    )
    fr.font.size = Pt(7)
    fr.italic = True
    fr.font.color.rgb = RGBColor(0x88, 0x88, 0x88)

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
    target = ParagraphStyle("target", parent=base["Normal"], fontSize=9,
                            textColor=HexColor("#555555"), spaceAfter=6)
    sec = ParagraphStyle("sec", parent=base["Heading2"], fontSize=11, spaceBefore=10,
                         spaceAfter=4, textColor=HexColor("#0369A1"))
    body = ParagraphStyle("body", parent=base["Normal"], fontSize=10, leading=14)
    role = ParagraphStyle("role", parent=base["Normal"], fontSize=10.5, leading=13,
                          textColor=HexColor("#0B0F17"))
    meta = ParagraphStyle("meta", parent=base["Normal"], fontSize=8.5,
                          textColor=HexColor("#666666"), spaceAfter=2)
    bullet = ParagraphStyle("bullet", parent=base["Normal"], fontSize=9.5, leading=13)
    foot = ParagraphStyle("foot", parent=base["Normal"], fontSize=7,
                          textColor=HexColor("#888888"), spaceBefore=10)

    story = [Paragraph(escape(target_role or "Resume"), name)]
    if organization:
        story.append(Paragraph(f"Target: {escape(organization)}", target))
    story.append(HRFlowable(width="100%", thickness=0.6, color=HexColor("#CCCCCC")))

    if sections.get("summary"):
        story.append(Paragraph("Professional Summary", sec))
        story.append(Paragraph(escape(sections["summary"]), body))

    story.append(Paragraph("Experience", sec))
    for e in sections.get("experiences", []):
        emp = _display_employer(e)
        story.append(Paragraph(f'<b>{escape(e.get("role",""))}</b> — {escape(emp)}', role))
        story.append(Paragraph(escape(_meta_line(e)), meta))
        items = []
        for b in e.get("bullets", []):
            txt = (
                f'{escape(b.get("text",""))} '
                f'<font size=7 color="#888888">[{escape(b.get("source_node_id",""))}]</font>'
            )
            items.append(ListItem(Paragraph(txt, bullet), leftIndent=12))
        if items:
            story.append(ListFlowable(items, bulletType="bullet", start="•", leftIndent=10))
        story.append(Spacer(1, 5))

    story.append(HRFlowable(width="100%", thickness=0.4, color=HexColor("#DDDDDD")))
    story.append(Paragraph(
        f'Resume Template v{rep.get("template_version","1.0")} · '
        f'Contract v{rep.get("contract_version","1.0")} · '
        f'{len(rep.get("claim_provenance",[]))} traceable claims',
        foot,
    ))

    doc.build(story)
    return buf.getvalue()
