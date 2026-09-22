"""Exact, ordered comparison of Word, Master, and WEB code text."""

from __future__ import annotations

from pathlib import Path
import json
from zipfile import ZipFile
from collections import OrderedDict
import pymupdf

from docx import Document
from lxml import html

from core.manuscript.code_blocks import scan_code_sources
from core.master import Master


def _master_codes(master: Master) -> list[tuple[str, str]]:
    result = []
    for block in master.blocks:
        if block.kind == "code-block":
            result.append((block.id, block.text))
        elif block.kind == "table":
            for ri, row in enumerate(block.rows):
                for ci, value in enumerate(row):
                    if (ri < len(block.cell_kinds) and ci < len(block.cell_kinds[ri])
                            and block.cell_kinds[ri][ci] == "code-block"):
                        result.append((f"{block.id}-r{ri}c{ci}", value))
    return result


def _html_codes(path: Path) -> list[tuple[str, str]]:
    tree = html.parse(str(path))
    nodes = tree.xpath("//pre[contains(concat(' ', normalize-space(@class), ' '), ' code-block ')]")
    result = []
    for node in nodes:
        code = node.find("code")
        result.append((node.get("data-block-id", ""), code.text_content() if code is not None else ""))
    return result


def _leading_whitespace(value: str) -> str:
    return value[:len(value) - len(value.lstrip(" \t"))]


def check_code_fidelity(source_docx: Path, master: Master, web_html: Path) -> dict:
    source = [(item.block_id, item.text) for item in scan_code_sources(Document(source_docx))]
    structured = _master_codes(master)
    rendered = _html_codes(web_html)
    source_ids = [item[0] for item in source]
    master_ids = [item[0] for item in structured]
    html_ids = [item[0] for item in rendered]
    master_map = dict(structured)
    html_map = dict(rendered)
    details = []
    for block_id, original in source:
        mid = master_map.get(block_id)
        out = html_map.get(block_id)
        a = original.split("\n")
        b = mid.split("\n") if mid is not None else []
        c = out.split("\n") if out is not None else []
        details.append({
            "block_id": block_id,
            "line_counts": {"docx": len(a), "master": len(b), "html": len(c)},
            "docx_lines": a,
            "master_lines": b,
            "html_lines": c,
            "line_text_equal": a == b == c,
            "indentation_equal": [_leading_whitespace(x) for x in a] == [_leading_whitespace(x) for x in b] == [_leading_whitespace(x) for x in c],
            "blank_lines_equal": [i for i, x in enumerate(a, 1) if not x] == [i for i, x in enumerate(b, 1) if not x] == [i for i, x in enumerate(c, 1) if not x],
            "exact_equal": original == mid == out,
        })
    count_equal = len(source) == len(structured) == len(rendered)
    order_equal = source_ids == master_ids == html_ids
    return {"counts": {"docx": len(source), "master": len(structured), "html": len(rendered)},
            "order": {"docx": source_ids, "master": master_ids, "html": html_ids},
            "count_equal": count_equal, "order_equal": order_equal, "blocks": details,
            "passed": count_equal and order_equal and all(item["exact_equal"] and item["indentation_equal"] and item["blank_lines_equal"] for item in details)}


def check_output_codes(source_docx: Path, master: Master, outputs: dict) -> dict:
    original = [(item.block_id, item.text) for item in scan_code_sources(Document(source_docx))]
    result = {"original_count": len(original), "master_equal": original == _master_codes(master), "formats": {}}
    for kind, path in outputs.items():
        actual, visual_errors = [], []
        try:
            if kind == "web":
                actual = _html_codes(path)
            elif kind == "epub":
                with ZipFile(path) as book:
                    doc = html.fromstring(book.read("EPUB/chapter.xhtml"))
                    actual = [(node.get("data-block-id"), node.find("code").text_content())
                              for node in doc.xpath("//pre[@class='code-block']")]
            elif kind == "pdf":
                with pymupdf.open(path) as document:
                    layout = json.loads(document.embfile_get("code-layout.json"))
                    blocks = OrderedDict()
                    previous = None
                    for line in layout:
                        if line.get("kind") != "code-block":
                            continue
                        blocks.setdefault(line["id"], []).append(line["text"])
                        if line["line"] != len(blocks[line["id"]]) - 1:
                            visual_errors.append(f'{line["id"]}: 줄 순서 불일치')
                        rect = pymupdf.Rect(line["x"] - 1, line["baseline"] - line["size"] * 1.25,
                                           line["x"] + line["width"] + 2, line["baseline"] + line["size"] * .35)
                        rendered = document[line["page"]].get_textbox(rect)
                        if rendered != line["text"].expandtabs(4):
                            visual_errors.append(f'{line["id"]} {line["line"] + 1}행: PDF 문자/공백 불일치')
                        if previous and previous["id"] == line["id"] and previous["page"] == line["page"]:
                            if abs(line["baseline"] - previous["baseline"] - line["leading"]) > .2:
                                visual_errors.append(f'{line["id"]}: 빈 줄 또는 행 간격 불일치')
                        if rect.x1 > document[line["page"]].rect.width or rect.y1 > document[line["page"]].rect.height:
                            visual_errors.append(f'{line["id"]}: 페이지 밖 코드')
                        previous = line
                    actual = [(key, "\n".join(lines)) for key, lines in blocks.items()]
            result["formats"][kind] = {"count": len(actual), "exact_equal": actual == original,
                                      "line_counts": [len(text.split("\n")) for _, text in actual],
                                      "visual_errors": visual_errors, "passed": actual == original and not visual_errors}
        except Exception as exc:
            result["formats"][kind] = {"passed": False, "error": type(exc).__name__}
    result["passed"] = result["master_equal"] and all(item["passed"] for item in result["formats"].values())
    return result
