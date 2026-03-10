from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "marketing" / "team_quickstart_guide.md"
OUTPUT = ROOT / "marketing" / "team_quickstart_guide.pdf"


def build_styles():
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="BodyTight",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=10.5,
            leading=14,
            spaceAfter=6,
            textColor=colors.HexColor("#1F2937"),
        )
    )
    styles.add(
        ParagraphStyle(
            name="BulletTight",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=10.5,
            leading=14,
            leftIndent=14,
            firstLineIndent=-8,
            spaceAfter=4,
            textColor=colors.HexColor("#1F2937"),
        )
    )
    styles.add(
        ParagraphStyle(
            name="TitlePage",
            parent=styles["Title"],
            fontName="Helvetica-Bold",
            fontSize=22,
            leading=28,
            textColor=colors.HexColor("#0F2747"),
            spaceAfter=10,
        )
    )
    styles.add(
        ParagraphStyle(
            name="SubTitle",
            parent=styles["Heading2"],
            fontName="Helvetica",
            fontSize=11.5,
            leading=16,
            textColor=colors.HexColor("#4B5563"),
            spaceAfter=16,
        )
    )
    styles["Heading1"].fontName = "Helvetica-Bold"
    styles["Heading1"].fontSize = 15
    styles["Heading1"].leading = 20
    styles["Heading1"].textColor = colors.HexColor("#0F2747")
    styles["Heading1"].spaceBefore = 10
    styles["Heading1"].spaceAfter = 8
    styles["Heading2"].fontName = "Helvetica-Bold"
    styles["Heading2"].fontSize = 12.5
    styles["Heading2"].leading = 17
    styles["Heading2"].textColor = colors.HexColor("#123B68")
    styles["Heading2"].spaceBefore = 8
    styles["Heading2"].spaceAfter = 6
    return styles


def normalize_inline(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("`", "<font name='Courier'>").replace("</font><font name='Courier'>", "")
    )


def format_inline_code(text: str) -> str:
    parts = text.split("`")
    if len(parts) == 1:
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    out = []
    for idx, part in enumerate(parts):
        safe = part.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        if idx % 2 == 1:
            out.append(f"<font name='Courier'>{safe}</font>")
        else:
            out.append(safe)
    return "".join(out)


def draw_header_footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#D7E3F4"))
    canvas.setLineWidth(0.5)
    canvas.line(doc.leftMargin, A4[1] - 18 * mm, A4[0] - doc.rightMargin, A4[1] - 18 * mm)
    canvas.setFont("Helvetica-Bold", 10)
    canvas.setFillColor(colors.HexColor("#0F2747"))
    canvas.drawString(doc.leftMargin, A4[1] - 14 * mm, "TuringEdge Recovery OS")
    canvas.setFont("Helvetica", 8.5)
    canvas.setFillColor(colors.HexColor("#6B7280"))
    canvas.drawRightString(A4[0] - doc.rightMargin, 10 * mm, f"Page {canvas.getPageNumber()}")
    canvas.restoreState()


def markdown_to_story(lines: list[str]):
    styles = build_styles()
    story = [
        Spacer(1, 8 * mm),
        Paragraph("TuringEdge Recovery OS", styles["TitlePage"]),
        Paragraph("Team Quick-Start Guide", styles["SubTitle"]),
        Paragraph(
            "A simple internal explainer for understanding the product and starting work quickly.",
            styles["BodyTight"],
        ),
        Spacer(1, 3 * mm),
    ]
    skip_title_block = True
    for raw in lines:
        line = raw.rstrip()
        if skip_title_block and line.startswith("# "):
            continue
        if skip_title_block and line.startswith("## Team Quick-Start Guide"):
            skip_title_block = False
            continue
        if not line.strip():
            story.append(Spacer(1, 2))
            continue
        if line.startswith("# "):
            story.append(Paragraph(format_inline_code(line[2:].strip()), styles["Heading1"]))
            continue
        if line.startswith("## "):
            story.append(Paragraph(format_inline_code(line[3:].strip()), styles["Heading1"]))
            continue
        if line.startswith("### "):
            story.append(Paragraph(format_inline_code(line[4:].strip()), styles["Heading2"]))
            continue
        if line[:3].isdigit() and line[1:3] == ". ":
            story.append(Paragraph(format_inline_code(line), styles["BulletTight"]))
            continue
        if line[:2].isdigit() and line[1:2] == ".":
            story.append(Paragraph(format_inline_code(line), styles["BulletTight"]))
            continue
        if line.startswith("- "):
            story.append(Paragraph(f"• {format_inline_code(line[2:].strip())}", styles["BulletTight"]))
            continue
        story.append(Paragraph(format_inline_code(line), styles["BodyTight"]))
    return story


def main():
    text = SOURCE.read_text(encoding="utf-8")
    lines = text.splitlines()
    doc = SimpleDocTemplate(
        str(OUTPUT),
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=24 * mm,
        bottomMargin=16 * mm,
        title="TuringEdge Recovery OS Team Quick-Start Guide",
        author="OpenAI Codex",
    )
    doc.build(markdown_to_story(lines), onFirstPage=draw_header_footer, onLaterPages=draw_header_footer)
    print(OUTPUT)


if __name__ == "__main__":
    main()
