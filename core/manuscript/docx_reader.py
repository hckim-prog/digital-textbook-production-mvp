from __future__ import annotations

from pathlib import Path
import re
import shutil

from docx import Document
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

from core.master import Block, Master, file_hash
from core.manuscript.code_blocks import cell_text, scan_code_sources
from core.manuscript.numbering import Numbering
from core.manuscript.content import read_inlines, cell_inlines, plain_text


def _kind(text: str, style: str) -> str:
    s = style.lower()
    t = text.strip()
    if "heading" in s or "제목" in s:
        return "heading"
    if "caption" in s or "캡션" in s:
        return "figure-caption"
    if "code" in s or "소스" in s:
        return "code-block"
    if "output" in s or "실행 결과" in t[:8]:
        return "code-output"
    if "list" in s or "목록" in s:
        return "bullet-list"
    if re.match(r"^\d+[.)]\s", t):
        return "procedure-step"
    if "[LMM 활용]" in t or "[LLM 활용]" in t:
        return "llm-usage"
    if "연습문제" in t[:10]:
        return "exercise"
    if "장 요약" in t[:10]:
        return "chapter-summary"
    return "paragraph"


def read_docx(source: Path, work_dir: Path, progress=None) -> Master:
    source = source.resolve()
    if source.suffix.lower() != ".docx" or not source.is_file():
        raise ValueError("읽을 수 있는 DOCX 원고를 선택해 주세요.")
    before = file_hash(source)
    if progress:
        progress({"phase": "원고 읽는 중", "percent": 5})
    work_dir.mkdir(parents=True, exist_ok=True)
    copy = work_dir / "source.docx"
    if copy.resolve() == source:
        raise ValueError("작업 경로가 원본 경로와 같습니다.")
    shutil.copy2(source, copy)
    assets = work_dir / "assets"
    assets.mkdir(exist_ok=True)
    doc = Document(copy)
    code_sources = scan_code_sources(doc)
    standalone_code = {item.body_start: item for item in code_sources if item.table_cell is None}
    covered_paragraphs = {position for item in code_sources if item.body_end > item.body_start
                          for position in range(item.body_start + 1, item.body_end + 1)}
    table_code = {(item.body_start, *item.table_cell): item for item in code_sources if item.table_cell is not None}
    blocks: list[Block] = []
    saved: dict[str, str] = {}
    numbering = Numbering(doc)
    for index, child in enumerate(doc.element.body.iterchildren(), 1):
        block_id = f"b{index:05d}"
        if index in covered_paragraphs:
            continue
        if index in standalone_code:
            region = standalone_code[index]
            inline = [item for element in list(doc.element.body)[region.body_start - 1:region.body_end]
                      for item in read_inlines(element, doc, assets, saved)]
            blocks.append(Block(block_id, "code-block", standalone_code[index].text, "Word code",
                                assets=[i["asset"] for i in inline if i["kind"] == "image"]))
            continue
        if child.tag == qn("w:tbl"):
            table = Table(child, doc)
            rich_cells = [[cell_inlines(cell, doc, assets, saved) for cell in row.cells] for row in table.rows]
            rows = [[table_code[(index, ri, ci)].text if (index, ri, ci) in table_code else cell.text
                     for ci, cell in enumerate(row.cells)] for ri, row in enumerate(table.rows)]
            for ri, row in enumerate(rows):
                for ci in range(len(row)):
                    if (index, ri, ci) not in table_code:
                        rows[ri][ci] = plain_text(rich_cells[ri][ci])
            cell_kinds = [["code-block" if re.search(r"#include|\bint main\s*\(|std::|\bcout\b|\bcin\b", cell)
                           else "code-output" if "실행 결과" in cell[:15] else "paragraph" for cell in row] for row in rows]
            for ri, ci in ((ri, ci) for ri, row in enumerate(rows) for ci, _ in enumerate(row)):
                if (index, ri, ci) in table_code:
                    cell_kinds[ri][ci] = "code-block"
            if blocks and "실행결과는다음과같다" in blocks[-1].text.replace(" ", "") and len(rows) == 1:
                cell_kinds = [["code-output" for _ in row] for row in rows]
            flat = [item for row in rich_cells for cell in row for item in cell]
            blocks.append(Block(block_id, "table", rows=rows, cell_kinds=cell_kinds, rich_cells=rich_cells,
                                assets=[i["asset"] for i in flat if i["kind"] == "image"],
                                links=[i["href"] for i in flat if i["kind"] == "link" and i.get("href")]))
            continue
        if child.tag != qn("w:p"):
            continue
        paragraph = Paragraph(child, doc)
        inline = read_inlines(child, doc, assets, saved)
        text = plain_text(inline)
        style = paragraph.style.name if paragraph.style else ""
        links = list(dict.fromkeys(i["href"] for i in inline if i["kind"] == "link" and i.get("href")))
        images = [i["asset"] for i in inline if i["kind"] == "image"]
        kind = _kind(text, style)
        number, label, number_warning = numbering.label(paragraph)
        if number and kind == "paragraph":
            kind = "procedure-step" if re.search(r"클릭|선택|입력|설치|실행|누른다|설정한다", text) else "numbered-list"
        if not text.strip() and images:
            kind = "figure"
        if not text.strip() and not images:
            continue
        group = block_id if kind == "procedure-step" else ""
        if kind == "figure" and blocks and blocks[-1].kind == "procedure-step":
            group = blocks[-1].id
        blocks.append(Block(block_id, kind, text, style, number=number, assets=images, links=links, group=group,
                            inlines=inline, list_label=label,
                            warnings=([number_warning] if number_warning else []) + (["수식을 선형 표기로 표시합니다. 원본 수식 정보는 보관됩니다."] if any(i["kind"] == "math" for i in inline) else [])))
        if progress:
            progress({"phase": "이미지와 본문 준비 중", "percent": min(95, 10 + int(index / len(doc.element.body) * 85))})
    if file_hash(source) != before:
        raise RuntimeError("작업 중 원본 DOCX가 변경됐습니다. 원본 파일을 확인해 주세요.")
    return Master(source.stem, source.name, before, blocks)
