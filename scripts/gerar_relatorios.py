"""Gera os dois PDFs a partir de textos editaveis, sem acrescentar resultados."""
import argparse
import json
from pathlib import Path
from html import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, PageBreak

ROOT = Path(__file__).resolve().parents[1]
STYLES = {
    "title": ParagraphStyle("title", fontName="Times-Bold", fontSize=16, leading=19, spaceAfter=9),
    "meta": ParagraphStyle("meta", fontName="Times-Roman", fontSize=10, leading=12, spaceAfter=4),
    "heading": ParagraphStyle("heading", fontName="Times-Bold", fontSize=12, leading=15, spaceBefore=7, spaceAfter=5),
    "body": ParagraphStyle("body", fontName="Times-Roman", fontSize=11.5, leading=15, alignment=TA_JUSTIFY, spaceAfter=7),
    "reference": ParagraphStyle("reference", fontName="Times-Roman", fontSize=9, leading=11.7, spaceAfter=4),
}


def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Times-Roman", 9)
    canvas.setFillColor(colors.black)
    canvas.drawString(54, 30, "Arthur Lima Pereira | RA 133275 | UNIFECAF")
    canvas.drawRightString(letter[0] - 54, 30, str(doc.page))
    canvas.restoreState()


def generate(content, key, target):
    report = content[key]
    story = [Paragraph(escape(report["title"]), STYLES["title"]),
             Paragraph("Arthur Lima Pereira | RA 133275", STYLES["meta"]),
             Paragraph("UNIFECAF | Análise e Desenvolvimento de Sistemas", STYLES["meta"]),
             Paragraph("Cloud DevOps Orchestrating Containers and Micro Services", STYLES["meta"]),
             Spacer(1, 6)]
    if key == "practice" and content.get("repository_url"):
        url = content["repository_url"]
        story.append(Paragraph(f'Repositório: <link href="{escape(url, quote=True)}">{escape(url)}</link>', STYLES["meta"]))
    for i, page in enumerate(report["pages"]):
        if i:
            story.append(PageBreak())
        for block in page:
            kind, text = block
            if kind == "references":
                story.append(Paragraph("Referências", STYLES["heading"]))
                for index in text:
                    ref = content["references"][str(index)]
                    story.append(Paragraph(escape(f"[{index}] {ref['text']}") +
                                           (f' <link href="{escape(ref["url"], quote=True)}" color="black">{escape(ref["label"])}</link>.' if ref.get("url") else ""), STYLES["reference"]))
            elif kind == "video":
                video = content.get("video_url")
                message = (f'Vídeo pitch: <link href="{escape(video, quote=True)}">{escape(video)}</link>'
                           if video else "Vídeo pitch: pendente de gravação e publicação pelo estudante.")
                story.append(Paragraph(message, STYLES["reference"]))
            else:
                story.append(Paragraph(escape(text), STYLES[kind]))
    doc = SimpleDocTemplate(str(target), pagesize=letter, leftMargin=54, rightMargin=54,
                            topMargin=42, bottomMargin=48, title=report["title"], author="Arthur Lima Pereira")
    doc.build(story, onFirstPage=footer, onLaterPages=footer)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--destino", type=Path, default=ROOT / "relatorios")
    args = parser.parse_args()
    args.destino.mkdir(parents=True, exist_ok=True)
    content = json.loads((ROOT / "docs/relatorios.json").read_text(encoding="utf-8"))
    for key, filename in (("theory", "Relatorio_Teorico_Arthur_Lima.pdf"),
                          ("practice", "Relatorio_Pratico_Arthur_Lima.pdf")):
        target = args.destino / filename
        generate(content, key, target)
        print(target)


if __name__ == "__main__":
    main()
