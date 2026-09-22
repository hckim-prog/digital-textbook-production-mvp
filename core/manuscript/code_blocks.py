"""Locate Word code regions without changing their whitespace."""

from __future__ import annotations

from dataclasses import dataclass
import re

from docx.oxml.ns import qn
from docx.table import Table


@dataclass(frozen=True)
class CodeSource:
    block_id: str
    text: str
    body_start: int
    body_end: int
    table_cell: tuple[int, int] | None = None


def paragraph_text(element) -> str:
    """Read w:t, explicit line breaks and tabs in document order."""
    parts: list[str] = []
    for node in element.iter():
        if node.tag == qn("w:t"):
            parts.append(node.text or "")
        elif node.tag == qn("w:tab"):
            parts.append("\t")
        elif node.tag in (qn("w:br"), qn("w:cr")):
            parts.append("\n")
    return "".join(parts)


def cell_text(cell) -> str:
    return "\n".join(paragraph_text(p._p) for p in cell.paragraphs)


_CODE_LINE = re.compile(
    r"\s*(?:"
    r"#include\s*[<\"][^>\"]+[>\"](?:\s*//.*)?|"
    r"using\s+(?:namespace\s+\w+|\w+::\w+)\s*;.*|"
    r"(?:int|void|auto)\s+main\s*\([^)]*\)\s*\{.*|"
    r"(?:[\w:<>*&]+\s+)+[\w]+\s*=\s*.*;.*|"
    r"(?:std::)?(?:cout|cin)\s*(?:<<|>>).*;.*|"
    r"return\b.*;.*|"
    r"[{}]\s*|"
    r"//.*"
    r")\s*"
)


def is_code_paragraph(text: str) -> bool:
    lines = text.split("\n")
    nonblank = [line for line in lines if line.strip()]
    return bool(nonblank) and all(_CODE_LINE.fullmatch(line) for line in nonblank)


def is_code_cell(text: str) -> bool:
    lines = text.split("\n")
    nonblank = [line for line in lines if line.strip()]
    return len(nonblank) >= 2 and sum(bool(_CODE_LINE.fullmatch(line)) for line in nonblank) >= 2


def scan_code_sources(doc) -> list[CodeSource]:
    children = list(doc.element.body.iterchildren())
    sources: list[CodeSource] = []
    index = 0
    while index < len(children):
        child = children[index]
        body_index = index + 1
        if child.tag == qn("w:tbl"):
            table = Table(child, doc)
            for row_index, row in enumerate(table.rows):
                for col_index, cell in enumerate(row.cells):
                    text = cell_text(cell)
                    if is_code_cell(text):
                        single = len(table.rows) == 1 and len(row.cells) == 1
                        block_id = f"b{body_index:05d}" if single else f"b{body_index:05d}-r{row_index}c{col_index}"
                        sources.append(CodeSource(block_id, text, body_index, body_index,
                                                  None if single else (row_index, col_index)))
            index += 1
            continue
        if child.tag != qn("w:p") or not is_code_paragraph(paragraph_text(child)):
            index += 1
            continue
        start = body_index
        parts: list[str] = []
        while index < len(children) and children[index].tag == qn("w:p"):
            current = children[index]
            value = paragraph_text(current)
            if value and not is_code_paragraph(value):
                break
            parts.append(value)
            index += 1
        while parts and not parts[-1]:
            parts.pop()
        if parts:
            sources.append(CodeSource(f"b{start:05d}", "\n".join(parts), start,
                                      start + len(parts) - 1))
        # When the loop stops at a non-code paragraph, process it next.
    return sources
