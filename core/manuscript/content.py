"""Ordered Word inline content, including media, links and equations."""
from pathlib import Path
from lxml import etree
from docx.oxml.ns import qn

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
    def append_text(text, href="", script=""):
        if text:
            result.append({"kind": "link" if href else "text", "text": text, "href": href, "script": script})

    def visit(node, href="", script=""):
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
        if node.tag == qn("w:t"):
            append_text(node.text or "", href, script)
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
                visit(child, href, script)
    visit(element)
    return result


def plain_text(inlines):
    return "".join(item.get("text", "") for item in inlines)


def cell_inlines(cell, doc, assets, saved):
    result = []
    for index, paragraph in enumerate(cell.paragraphs):
        if index:
            result.append({"kind": "text", "text": "\n"})
        result.extend(read_inlines(paragraph._p, doc, assets, saved))
    return result
