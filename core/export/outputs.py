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
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle, PageBreak
import pymupdf

from core.master import Master
from core.export.pdf_layout import CodeBlock
from core.export.themes import resolve, stylesheet, READER_JS
from core.manuscript.structure import validate
from core.cancellation import check_cancelled




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


def html_body(master: Master, reader=False, cancelled=None):
    check_cancelled(cancelled)
    outline = validate(master, master.outline) if master.outline else []
    parts = [f"<div class='book-title'>{escape(master.title)}</div>" if outline else f"<h1>{escape(master.title)}</h1>"]
    if reader:
        parts = [f'<a class="skip-link" href="#book-content">본문으로 이동</a><div class="book-shell"><header class="book-title"><span class="edition">DIGITAL TEXTBOOK</span><div class="cover-title">{escape(master.title)}</div></header>']
    if outline:
        def toc(parent=None):
            return '<ol>' + ''.join(f'<li><a href="#{n["id"]}">{escape(n["title"])}</a>{toc(n["id"]) if any(c["parent_id"] == n["id"] for c in outline) else ""}</li>' for n in outline if n["parent_id"] == parent) + '</ol>'
        nav = '<nav class="book-toc" aria-label="목차"><strong>목차</strong>' + toc() + '</nav>'
        parts.append('<aside class="reader-sidebar"><details open><summary>목차</summary>' + nav + '</details></aside>' if reader else nav)
    if reader:
        if not outline: parts.append('<aside class="reader-sidebar">목차 정보가 없는 원고입니다.</aside>')
        parts.append('<main id="book-content" class="book-content">')
    starts = {}
    for n in outline:
        starts.setdefault(n["start_block_id"], []).append(n)
    for b in master.blocks:
        check_cancelled(cancelled)
        source_heading = None
        for n in starts.get(b.id, []):
            if n["use_source_title"]:
                source_heading = n
            else:
                parts.append(f'<h{n["level"]} id="{n["id"]}" data-outline-id="{n["id"]}">{escape(n["title"])}</h{n["level"]}>')
        attrs = f'data-source-id="{b.id}" data-kind="{b.kind}" data-group="{escape(b.group)}"'
        content = ""
        if b.kind in ("code-block", "code-output"):
            content = _code_markup(b.id, b.text, b.kind)
            content += inline_html([{"kind": "image", "asset": name} for name in b.assets])
        elif b.kind == "table":
            rows = []
            for ri, row in enumerate(b.rows):
                check_cancelled(cancelled)
                cells = []
                for ci, value in enumerate(row):
                    kind = b.cell_kinds[ri][ci] if ri < len(b.cell_kinds) and ci < len(b.cell_kinds[ri]) else "paragraph"
                    rich = b.rich_cells[ri][ci] if ri < len(b.rich_cells) and ci < len(b.rich_cells[ri]) else []
                    cell = _code_markup(f"{b.id}-r{ri}c{ci}", value, kind) if kind in ("code-block", "code-output") else (inline_html(rich) if rich else escape(value).replace("\n", "<br />"))
                    cells.append(f"<td>{cell}</td>")
                rows.append("<tr>" + "".join(cells) + "</tr>")
            content = '<div class="table-wrap"><table>' + "".join(rows) + "</table></div>"
        else:
            value = inline_html(b.inlines) if b.inlines else escape(b.text).replace("\n", "<br />")
            if not b.inlines:
                value += inline_html([{"kind": "image", "asset": name} for name in b.assets])
            label = f'<span class="list-label">{escape(b.list_label)}</span>' if b.list_label else ""
            tag = f'h{source_heading["level"]}' if source_heading else ("h2" if b.kind == "heading" and not outline else "div")
            heading_attrs = f' id="{source_heading["id"]}" data-outline-id="{source_heading["id"]}"' if source_heading else ""
            content = f'<{tag}{heading_attrs} class="{b.kind}">{label}{value}</{tag}>'
        parts.append(f'<section id="{b.id}" {attrs}>{content}</section>')
    if reader: parts.append("</main></div>")
    return "\n".join(parts)


def web(master, source_assets, dest, theme="auto", cancelled=None):
    check_cancelled(cancelled)
    design = resolve(master, theme)
    dest.mkdir(parents=True, exist_ok=True)
    if source_assets.is_dir():
        shutil.copytree(source_assets, dest / "assets", dirs_exist_ok=True)
    out = dest / "index.html"
    out.write_text(f"<!doctype html><html lang='ko'><head><meta charset='utf-8'/><meta name='viewport' content='width=device-width, initial-scale=1'/><meta name='book-theme' content='{design['id']}'/><title>{escape(master.title)}</title><style>{stylesheet(design)}</style></head><body>{html_body(master, reader=True, cancelled=cancelled)}<script>{READER_JS}</script></body></html>", encoding="utf-8", newline="\n")
    check_cancelled(cancelled)
    return out


def _pdf_fonts():
    for name, filename in (("Malgun", "malgun.ttf"), ("MalgunBold", "malgunbd.ttf"), ("CodeMono", "consola.ttf"), ("Symbols", "seguisym.ttf")):
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


def pdf(master, source_assets, dest, filename="textbook.pdf", theme="auto", cancelled=None):
    check_cancelled(cancelled)
    design = resolve(master, theme)
    _pdf_fonts()
    dest.mkdir(parents=True, exist_ok=True)
    styles = getSampleStyleSheet()
    for style in styles.byName.values():
        style.fontName, style.wordWrap = "Malgun", "CJK"
        if hasattr(style, "fontSize"):
            style.leading = max(getattr(style, "leading", 12), style.fontSize * 1.55)
    accent = colors.HexColor(design['accent'])
    tint = colors.HexColor(design['tint'])
    ink = colors.HexColor(design['ink'])
    styles['BodyText'].fontSize = design['body']
    styles['BodyText'].leading = design['leading']
    styles['BodyText'].textColor = ink
    styles['Title'].fontName = 'MalgunBold'
    styles['Title'].fontSize, styles['Title'].leading = 30, 43
    styles['Title'].alignment = 0
    styles['Title'].textColor = accent
    for level,size in [(1,23),(2,16),(3,12),(4,11)]:
        st=styles[f'Heading{level}'];st.fontName='MalgunBold';st.fontSize=size;st.leading=size*1.5
        st.textColor=accent if level!=2 else ink
        st.spaceBefore=20;st.spaceAfter=12
    styles['Heading1'].borderWidth=1
    styles['Heading1'].borderColor=accent
    styles['Heading1'].borderPadding=12
    code_layout = []
    outline = validate(master, master.outline) if master.outline else []
    starts = {}
    for n in outline:
        starts.setdefault(n["start_block_id"], []).append(n)
    bookmarks = []
    class OutlineDocument(SimpleDocTemplate):
        def handle_flowable(self, flowables):
            check_cancelled(cancelled)
            return super().handle_flowable(flowables)

        def afterFlowable(self, flowable):
            entry = getattr(flowable, "outline_entry", None)
            if entry:
                bookmarks.append([entry["level"], entry["title"], self.page])

    def picture(name, max_width=473):
        check_cancelled(cancelled)
        path = source_assets / name
        width, height = ImageReader(str(path)).getSize()
        scale = min(max_width / width, 550 / height, 1)
        return Image(str(path), width=width * scale, height=height * scale, hAlign="LEFT")

    def flow(items, style, max_width=473):
        output, buffer = [], []
        def flush():
            if buffer:
                output.append(Paragraph("".join(buffer), style))
                buffer.clear()
        for item in items:
            check_cancelled(cancelled)
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

    story = [Spacer(1, 90), Paragraph("DIGITAL TEXTBOOK", styles['Heading3']),
             Spacer(1, 18), Paragraph(pdf_text(master.title), styles["Title"]),
             PageBreak()]
    for b in master.blocks:
        check_cancelled(cancelled)
        if b is not master.blocks[0] and any(n["level"] == 1 for n in starts.get(b.id, [])):
            story.append(PageBreak())
        source_heading = None
        for n in starts.get(b.id, []):
            if n["use_source_title"]:
                source_heading = n
            else:
                heading = Paragraph(pdf_text(n["title"]), styles[f'Heading{n["level"]}'])
                heading.outline_entry = n
                story.append(heading)
        if b.kind in ("code-block", "code-output"):
            story.append(CodeBlock(b.id, b.text, code_layout, kind=b.kind, accent=design["accent"]))
            story.extend(picture(name) for name in b.assets)
        elif b.kind == "table" and b.rows:
            col_count = max(map(len, b.rows))
            cell_width = 473 / col_count - 14
            cells = []
            for ri, row in enumerate(b.rows):
                check_cancelled(cancelled)
                rendered_row = []
                for ci, value in enumerate(row):
                    kind = b.cell_kinds[ri][ci] if ri < len(b.cell_kinds) and ci < len(b.cell_kinds[ri]) else ""
                    rich = b.rich_cells[ri][ci] if ri < len(b.rich_cells) and ci < len(b.rich_cells[ri]) else [{"kind": "text", "text": value}]
                    rendered_row.append([CodeBlock(f"{b.id}-r{ri}c{ci}", value, code_layout, kind=kind, accent=design["accent"])] if kind in ("code-block", "code-output") else flow(rich, styles["BodyText"], cell_width))
                cells.append(rendered_row)
            table = Table(cells, colWidths=[473 / col_count] * col_count, splitInRow=1)
            table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), .4, colors.HexColor("#cedadd")),
                                       ("ROWBACKGROUNDS", (0, 0), (-1, -1), [tint, colors.white]),
                                       ("VALIGN", (0, 0), (-1, -1), "TOP"),
                                       ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]))
            story.append(table)
        else:
            items = list(b.inlines) if b.inlines else [{"kind": "text", "text": b.text}] + [{"kind": "image", "asset": name} for name in b.assets]
            if b.list_label:
                items.insert(0, {"kind": "text", "text": b.list_label + " "})
            style = styles[f'Heading{source_heading["level"]}'] if source_heading else (styles["Heading2"] if b.kind == "heading" and not outline else styles["BodyText"])
            rendered = flow(items, style)
            if source_heading and rendered:
                rendered[0].outline_entry = source_heading
            story.extend(rendered)
        story.append(Spacer(1, 8))
    out = dest / filename
    def footer(canvas, document):
        canvas.setFont("Malgun", 8)
        canvas.setStrokeColor(accent)
        canvas.setLineWidth(1)
        canvas.line(55, 813, 540, 813)
        canvas.setFillColor(accent)
        canvas.drawRightString(540, 25, str(document.page))
    OutlineDocument(str(out), pagesize=(595, 842), leftMargin=55, rightMargin=55,
                      topMargin=52, bottomMargin=45).build(story, onFirstPage=footer, onLaterPages=footer)
    check_cancelled(cancelled)
    document = pymupdf.open(out)
    if bookmarks:
        document.set_toc(bookmarks)
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


def epub_file(master, source_assets, dest, filename="textbook.epub", theme="auto", cancelled=None):
    check_cancelled(cancelled)
    design = resolve(master, theme)
    dest.mkdir(parents=True, exist_ok=True)
    book = epub.EpubBook()
    book.set_identifier(master.source_hash)
    book.set_title(master.title)
    book.set_language("ko")
    page = epub.EpubHtml(title=master.title, file_name="chapter.xhtml", lang="ko")
    page.content = f"<html xmlns='http://www.w3.org/1999/xhtml'><head><title>{escape(master.title)}</title><link rel='stylesheet' href='style.css' type='text/css'/></head><body>{html_body(master, cancelled=cancelled)}</body></html>"
    book.add_item(page)
    book.add_item(epub.EpubItem(uid="style", file_name="style.css", media_type="text/css", content=stylesheet(design, web=False).encode()))
    for path in source_assets.glob("*") if source_assets.is_dir() else []:
        check_cancelled(cancelled)
        media = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif", ".svg": "image/svg+xml"}.get(path.suffix.lower())
        if media:
            book.add_item(epub.EpubItem(uid=path.stem, file_name=f"assets/{path.name}", media_type=media, content=path.read_bytes()))
    book.toc, book.spine = (page,), ["nav", page]
    if master.outline:
        outline = validate(master, master.outline)
        def entries(parent=None):
            result = []
            for n in outline:
                if n["parent_id"] == parent:
                    link = epub.Link("chapter.xhtml#" + n["id"], n["title"], n["id"])
                    children = entries(n["id"])
                    result.append((link, children) if children else link)
            return result
        book.toc = entries()
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    out = dest / filename
    epub.write_epub(str(out), book)
    check_cancelled(cancelled)
    return out
