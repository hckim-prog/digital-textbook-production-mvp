"""Ordered Word inline content, including media, links and equations."""
from pathlib import Path
from lxml import etree
from docx.oxml.ns import qn
from docx.table import Table

MATH = "http://schemas.openxmlformats.org/officeDocument/2006/math"


def math_text(node):
    name = etree.QName(node).localname
    children = {etree.QName(c).localname: c for c in node}
    def part(key):
        return math_text(children[key]) if key in children else ""
    if name == "t":
        return node.text or ""
    if name == "f":
        return "(" + part("num") + ")/(" + part("den") + ")"
    if name in ("sSup", "sSub", "sSubSup"):
        return part("e") + ("_(" + part("sub") + ")" if "sub" in children else "") + ("^(" + part("sup") + ")" if "sup" in children else "")
    if name == "rad":
        return (part("deg") or "2") + "√(" + part("e") + ")"
    if name.endswith("Pr"):
        return ""
    return "".join(math_text(c) for c in node)


def read_inlines(element, doc, assets: Path, saved: dict) -> list[dict]:
    result = []
    def append_text(text, href="", script="", font=""):
        if text:
            item = {"kind": "link" if href else "text", "text": text, "href": href, "script": script}
            if font == 'Symbol':
                item['font'] = font  # Word's private-use characters depend on this font.
            result.append(item)

    def visit(node, href="", script="", font=""):
        name = etree.QName(node).localname
        if node.tag == f"{{{MATH}}}oMath":
            result.append({"kind": "math", "text": math_text(node),
                           "xml": etree.tostring(node, encoding="unicode")})
            return
        if node.tag == qn("w:hyperlink"):
            rid = node.get(qn("r:id"))
            anchor = node.get(qn("w:anchor"))
            href = str(doc.part.rels[rid].target_ref) if rid in doc.part.rels else ("#" + anchor if anchor else "")
        if node.tag == qn("w:r"):
            props = node.find(qn("w:rPr"))
            if props is not None:
                align = props.find(qn("w:vertAlign"))
                script = align.get(qn("w:val"), "") if align is not None else ""
                fonts = props.find(qn('w:rFonts'))
                font = fonts.get(qn('w:ascii'), '') if fonts is not None else ''
        if node.tag == qn("w:t"):
            append_text(node.text or "", href, script, font)
        elif node.tag == qn("w:tab"):
            append_text("\t", href)
        elif node.tag in (qn("w:br"), qn("w:cr")):
            append_text("\n", href)
        elif node.tag == qn("a:blip") or name == "imagedata":
            rid = node.get(qn("r:embed")) or node.get(qn("r:id"))
            if rid and rid in doc.part.rels:
                part = doc.part.rels[rid].target_part
                if rid not in saved:
                    suffix = Path(part.partname).suffix or ".bin"
                    saved[rid] = f"image-{len(saved)+1:04d}{suffix}"
                    (assets / saved[rid]).write_bytes(part.blob)
                result.append({"kind": "image", "asset": saved[rid]})
        elif node.tag not in (qn("w:rPr"), qn("w:pPr")):
            for child in node:
                visit(child, href, script, font)
    visit(element)
    return result


def plain_text(inlines):
    return "".join(item.get("text", "") for item in inlines)


def walk_inlines(items):
    """Yield leaf content in order, including content inside nested tables."""
    for item in items:
        if item['kind'] == 'table':
            for row in item['rich_cells']:
                for cell in row:
                    yield from walk_inlines(cell)
        else:
            yield item


def table_parts(table_id, rows, cell_kinds, rich_cells):
    """Top and nested tables in source order, with stable paths for code IDs."""
    yield table_id, rows, cell_kinds, rich_cells
    for row in rich_cells:
        for cell in row:
            for item in cell:
                if item['kind'] == 'table':
                    yield from table_parts(item['id'], item['rows'], item['cell_kinds'], item['rich_cells'])


def read_table(table, doc, assets, saved, table_id, code_cells):
    rich = [[cell_inlines(cell, doc, assets, saved, f'{table_id}-r{ri}c{ci}', code_cells)
             for ci, cell in enumerate(row.cells)] for ri, row in enumerate(table.rows)]
    rows = [[code_cells.get(f'{table_id}-r{ri}c{ci}', plain_text(cell))
             for ci, cell in enumerate(row)] for ri, row in enumerate(rich)]
    kinds = [['code-block' if f'{table_id}-r{ri}c{ci}' in code_cells else
              ('code-output' if '실행 결과' in value[:15] else 'paragraph')
              for ci, value in enumerate(row)] for ri, row in enumerate(rows)]
    return {'kind': 'table', 'id': table_id, 'rows': rows, 'rich_cells': rich,
            'cell_kinds': kinds, 'text': '\n'.join('\n'.join(row) for row in rows),
            'xml': etree.tostring(table._tbl, encoding='unicode')}


def cell_inlines(cell, doc, assets, saved, cell_id='', code_cells=None):
    result = []
    table_index, seen = 0, False
    for child in cell._tc:
        if child.tag not in (qn('w:p'), qn('w:tbl')):
            continue
        if seen:
            result.append({"kind": "text", "text": "\n"})
        seen = True
        if child.tag == qn('w:tbl'):
            result.append(read_table(Table(child, doc), doc, assets, saved,
                                     f'{cell_id}-t{table_index}', code_cells or {}))
            table_index += 1
        else:
            result.extend(read_inlines(child, doc, assets, saved))
    return result
