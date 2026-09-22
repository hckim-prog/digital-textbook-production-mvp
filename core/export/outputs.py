from __future__ import annotations

from html import escape
from pathlib import Path
import json
import re
import shutil

from ebooklib import epub
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
import pymupdf

from core.master import Master
from core.export.pdf_layout import CodeBlock

CSS = """body{font-family:'Malgun Gothic',sans-serif;max-width:850px;margin:2rem auto;line-height:1.75;padding:0 1rem;color:#202b3a}
img{max-width:100%;height:auto;display:block;margin:1rem 0}
pre.code-block,pre.code-output{font-family:Consolas,'Cascadia Code',monospace;white-space:pre;overflow-x:auto;max-width:100%;tab-size:4;line-height:1.55;background:#f3f5f7;padding:1rem}
pre code{font-family:inherit;white-space:inherit}table{border-collapse:collapse;width:100%;margin:1rem 0}td{border:1px solid #bcc5d1;padding:.55rem;vertical-align:top}
.procedure-step{border-left:3px solid #3971a9;padding-left:1rem}.paragraph,.figure-caption{margin:.6rem 0}.figure-caption{color:#4a5b70;font-size:.94em}
.math-expression{font-family:'Cambria Math',serif;white-space:pre-wrap}.list-label{margin-right:.6em}
"""


def _code_markup(block_id, text, kind="code-block"):
    return f'<pre class="{kind}" data-block-id="{escape(block_id, quote=True)}"><code>{escape(text, quote=False)}</code></pre>'


def inline_html(items):
    parts = []
    for item in items:
        kind = item["kind"]
        if kind == "image":
            parts.append(f'<img src="assets/{escape(item["asset"], quote=True)}" alt="원고 이미지" />')
            continue
        value = escape(item.get("text", "")).replace("\n", "<br />")
        if kind == "link":
            href = item.get("href", "")
            if href.startswith(("http://", "https://", "mailto:", "#")):
                value = f'<a href="{escape(href, quote=True)}">{value}</a>'
        if kind == "math":
            value = f'<span class="math-expression" data-omml="{escape(item.get("xml", ""), quote=True)}">{value}</span>'
        script = item.get("script")
        if script in ("superscript", "subscript"):
            tag = "sup" if script == "superscript" else "sub"
            value = f"<{tag}>{value}</{tag}>"
        parts.append(value)
    return "".join(parts)


def html_body(master: Master):
    parts = [f"<h1>{escape(master.title)}</h1>"]
    for b in master.blocks:
        attrs = f'data-source-id="{b.id}" data-kind="{b.kind}" data-group="{escape(b.group)}"'
        content = ""
        if b.kind in ("code-block", "code-output"):
            content = _code_markup(b.id, b.text, b.kind)
            content += inline_html([{"kind": "image", "asset": name} for name in b.assets])
        elif b.kind == "table":
            rows = []
            for ri, row in enumerate(b.rows):
                cells = []
                for ci, value in enumerate(row):
                    kind = b.cell_kinds[ri][ci] if ri < len(b.cell_kinds) and ci < len(b.cell_kinds[ri]) else "paragraph"
                    rich = b.rich_cells[ri][ci] if ri < len(b.rich_cells) and ci < len(b.rich_cells[ri]) else []
                    cell = _code_markup(f"{b.id}-r{ri}c{ci}", value, kind) if kind in ("code-block", "code-output") else (inline_html(rich) if rich else escape(value).replace("\n", "<br />"))
                    cells.append(f"<td>{cell}</td>")
                rows.append("<tr>" + "".join(cells) + "</tr>")
            content = "<table>" + "".join(rows) + "</table>"
        else:
            value = inline_html(b.inlines) if b.inlines else escape(b.text).replace("\n", "<br />")
            if not b.inlines:
                value += inline_html([{"kind": "image", "asset": name} for name in b.assets])
            label = f'<span class="list-label">{escape(b.list_label)}</span>' if b.list_label else ""
            tag = "h2" if b.kind == "heading" else "div"
            content = f'<{tag} class="{b.kind}">{label}{value}</{tag}>'
        parts.append(f'<section id="{b.id}" {attrs}>{content}</section>')
    return "\n".join(parts)


def web(master, source_assets, dest):
    dest.mkdir(parents=True, exist_ok=True)
    if source_assets.is_dir():
        shutil.copytree(source_assets, dest / "assets", dirs_exist_ok=True)
    out = dest / "index.html"
    out.write_text(f"<!doctype html><html lang='ko'><head><meta charset='utf-8'/><title>{escape(master.title)}</title><style>{CSS}</style></head><body>{html_body(master)}</body></html>", encoding="utf-8", newline="\n")
    return out


def _pdf_fonts():
    for name, filename in (("Malgun", "malgun.ttf"), ("CodeMono", "consola.ttf"), ("Symbols", "seguisym.ttf")):
        path = Path("C:/Windows/Fonts") / filename
        if not path.is_file():
            raise RuntimeError("결과물에 필요한 Windows 글꼴을 찾을 수 없습니다: " + filename)
        if name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(name, str(path)))


def pdf_text(value):
    normal = pdfmetrics.getFont("Malgun").face.charToGlyph
    symbols = pdfmetrics.getFont("Symbols").face.charToGlyph
    result = []
    for char in value:
        if char == "\n":
            result.append("<br/>")
        elif ord(char) not in normal and ord(char) in symbols:
            result.append('<font name="Symbols">' + escape(char) + '</font>')
        else:
            result.append(escape(char))
    return "".join(result)


def pdf(master, source_assets, dest, filename="textbook.pdf"):
    _pdf_fonts()
    dest.mkdir(parents=True, exist_ok=True)
    styles = getSampleStyleSheet()
    for style in styles.byName.values():
        style.fontName, style.wordWrap = "Malgun", "CJK"
        if hasattr(style, "fontSize"):
            style.leading = max(getattr(style, "leading", 12), style.fontSize * 1.55)
    code_layout = []

    def picture(name, max_width=480):
        path = source_assets / name
        width, height = ImageReader(str(path)).getSize()
        scale = min(max_width / width, 550 / height, 1)
        return Image(str(path), width=width * scale, height=height * scale, hAlign="LEFT")

    def flow(items, style, max_width=480):
        output, buffer = [], []
        def flush():
            if buffer:
                output.append(Paragraph("".join(buffer), style))
                buffer.clear()
        for item in items:
            if item["kind"] == "image":
                flush()
                output.append(picture(item["asset"], max_width))
                continue
            text = pdf_text(item.get("text", ""))
            if item["kind"] == "link" and item.get("href", "").startswith(("http://", "https://", "mailto:")):
                text = f'<link href="{escape(item["href"], quote=True)}" color="#2356a0">{text}</link>'
            if item.get("script") in ("superscript", "subscript"):
                tag = "super" if item["script"] == "superscript" else "sub"
                text = f"<{tag}>{text}</{tag}>"
            buffer.append(text)
        flush()
        return output

    story = [Paragraph(pdf_text(master.title), styles["Title"]), Spacer(1, 14)]
    for b in master.blocks:
        if b.kind in ("code-block", "code-output"):
            story.append(CodeBlock(b.id, b.text, code_layout, kind=b.kind))
            story.extend(picture(name) for name in b.assets)
        elif b.kind == "table" and b.rows:
            col_count = max(map(len, b.rows))
            cell_width = 480 / col_count - 14
            cells = []
            for ri, row in enumerate(b.rows):
                rendered_row = []
                for ci, value in enumerate(row):
                    kind = b.cell_kinds[ri][ci] if ri < len(b.cell_kinds) and ci < len(b.cell_kinds[ri]) else ""
                    rich = b.rich_cells[ri][ci] if ri < len(b.rich_cells) and ci < len(b.rich_cells[ri]) else [{"kind": "text", "text": value}]
                    rendered_row.append([CodeBlock(f"{b.id}-r{ri}c{ci}", value, code_layout, kind=kind)] if kind in ("code-block", "code-output") else flow(rich, styles["BodyText"], cell_width))
                cells.append(rendered_row)
            table = Table(cells, colWidths=[480 / col_count] * col_count)
            table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), .4, colors.lightgrey),
                                       ("VALIGN", (0, 0), (-1, -1), "TOP"),
                                       ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]))
            story.append(table)
        else:
            items = list(b.inlines) if b.inlines else [{"kind": "text", "text": b.text}] + [{"kind": "image", "asset": name} for name in b.assets]
            if b.list_label:
                items.insert(0, {"kind": "text", "text": b.list_label + " "})
            style = styles["Heading2"] if b.kind == "heading" else styles["BodyText"]
            story.extend(flow(items, style))
        story.append(Spacer(1, 8))
    out = dest / filename
    def footer(canvas, document):
        canvas.setFont("Malgun", 8)
        canvas.setFillColor(colors.grey)
        canvas.drawRightString(540, 25, str(document.page))
    SimpleDocTemplate(str(out), pagesize=(595, 842), leftMargin=55, rightMargin=55,
                      topMargin=42, bottomMargin=45).build(story, onFirstPage=footer, onLaterPages=footer)
    document = pymupdf.open(out)
    # ReportLab 4.x writes supplementary Unicode mappings as five hex digits.
    # PDF ToUnicode destinations require UTF-16BE surrogate pairs instead.
    for page in document:
        for font in page.get_fonts():
            kind, value = document.xref_get_key(font[0], 'ToUnicode')
            if kind != 'xref':
                continue
            xref = int(value.split()[0])
            cmap = document.xref_stream(xref)
            repaired = re.sub(rb'(<[0-9A-Fa-f]{2}>\s*)<([0-9A-Fa-f]{5,6})>',
                              lambda m: m[1] + b'<' + chr(int(m[2], 16)).encode('utf-16-be').hex().upper().encode() + b'>', cmap)
            if repaired != cmap:
                document.update_stream(xref, repaired)
    document.embfile_add("code-layout.json", json.dumps(code_layout, ensure_ascii=False).encode("utf-8"))
    document.saveIncr()
    document.close()
    return out


def epub_file(master, source_assets, dest, filename="textbook.epub"):
    dest.mkdir(parents=True, exist_ok=True)
    book = epub.EpubBook()
    book.set_identifier(master.source_hash)
    book.set_title(master.title)
    book.set_language("ko")
    page = epub.EpubHtml(title=master.title, file_name="chapter.xhtml", lang="ko")
    page.content = f"<html xmlns='http://www.w3.org/1999/xhtml'><head><title>{escape(master.title)}</title><link rel='stylesheet' href='style.css' type='text/css'/></head><body>{html_body(master)}</body></html>"
    book.add_item(page)
    book.add_item(epub.EpubItem(uid="style", file_name="style.css", media_type="text/css", content=CSS.encode()))
    for path in source_assets.glob("*") if source_assets.is_dir() else []:
        media = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif", ".svg": "image/svg+xml"}.get(path.suffix.lower())
        if media:
            book.add_item(epub.EpubItem(uid=path.stem, file_name=f"assets/{path.name}", media_type=media, content=path.read_bytes()))
    book.toc, book.spine = (page,), ["nav", page]
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    out = dest / filename
    epub.write_epub(str(out), book)
    return out
