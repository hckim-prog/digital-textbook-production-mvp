from __future__ import annotations

from collections import Counter
from hashlib import sha256, md5
from html import escape
from pathlib import Path
import json
import re
from zipfile import ZipFile

from docx import Document
from docx.oxml.ns import qn
from lxml import html
from PIL import Image
import pymupdf

from core.master import Master, file_hash
from core.manuscript.code_blocks import paragraph_text, scan_code_sources
from core.manuscript.content import MATH
from core.manuscript.structure import validate


def compact(value):
    # Natural prose only. Exact code whitespace is checked separately.
    return re.sub(r"\s+", "", value)


def block_text(block):
    return "\n".join("\n".join(row) for row in block.rows) if block.kind == "table" else block.text


def image_digest(path):
    with Image.open(path) as picture:
        return md5(picture.convert("RGB").tobytes()).digest()


def check(master: Master, source: Path, assets: Path, outputs: dict[str, Path], original_master=None) -> dict:
    counts = Counter(b.kind for b in master.blocks)
    names = [name for block in master.blocks for name in block.assets]
    missing = [name for name in names if not (assets / name).is_file()]
    original_ok = source.is_file() and file_hash(source) == master.source_hash
    output_ok = {kind: path.is_file() and path.stat().st_size > 0 for kind, path in outputs.items()}
    checks, warnings = [], [warning for block in master.blocks for warning in block.warnings]
    def add(format_name, label, passed, detail=""):
        checks.append({"format": format_name, "label": label, "passed": bool(passed), "detail": detail})
    add("원본", "원본 파일 보존", original_ok)
    add("원고", "이미지 자산", not missing, f"{len(names)}개")
    outline = validate(master, master.outline) if master.outline else []
    if outline:
        add("원고", "장·절·소단원 관계와 범위", True, f"장 {sum(n['level'] == 1 for n in outline)} · 절 {sum(n['level'] == 2 for n in outline)} · 소단원 {sum(n['level'] == 3 for n in outline)}")
    if source.suffix.lower() == ".docx":
        doc = Document(source)
        source_text = paragraph_text(doc.element.body)
        word_text = []
        for block in (original_master or master).blocks:
            if block.kind == "table" and block.rich_cells:
                inline = [item for row in block.rich_cells for cell in row for item in cell]
                word_text.append("".join(i.get("text", "") for i in inline if i["kind"] != "math"))
            elif block.inlines:
                word_text.append("".join(i.get("text", "") for i in block.inlines if i["kind"] != "math"))
            else:
                word_text.append(block_text(block))
        add("원고", "본문·숫자·이진수 누락", compact(source_text) == compact("".join(word_text)))
        source_images = []
        for node in doc.element.body.iter():
            if node.tag == qn("a:blip") or node.tag.endswith("}imagedata"):
                rid = node.get(qn("r:embed")) or node.get(qn("r:id"))
                if rid in doc.part.rels:
                    source_images.append(sha256(doc.part.rels[rid].target_part.blob).hexdigest())
        actual_images = [file_hash(assets / name) for name in names if (assets / name).is_file()]
        add("원고", "이미지 개수와 순서", source_images == actual_images, f"원본 {len(source_images)} / 준비 {len(actual_images)}")
        code_table_count = sum(item.table_cell is None and list(doc.element.body)[item.body_start - 1].tag == qn("w:tbl") for item in scan_code_sources(doc))
        table_count = sum(child.tag == qn("w:tbl") for child in doc.element.body) - code_table_count
        add("원고", "표 구조", table_count == counts.get("table", 0), f"{table_count}개 (코드 전용 표는 코드 블록으로 보존)")
        source_links = {str(doc.part.rels[node.get(qn("r:id"))].target_ref) for node in doc.element.body.findall(".//" + qn("w:hyperlink")) if node.get(qn("r:id")) in doc.part.rels}
        add("원고", "링크 주소", source_links <= {link for b in master.blocks for link in b.links})
        source_math = len(doc.element.body.findall(f".//{{{MATH}}}oMath"))
        inline = [i for b in master.blocks for i in b.inlines] + [i for b in master.blocks for row in b.rich_cells for cell in row for i in cell]
        actual_math = sum(i["kind"] == "math" for i in inline)
        add("원고", "수식 보존", source_math == actual_math, f"{source_math}개" + (" · 선형 표기 검토 필요" if source_math else ""))
    expected_links = {link for b in master.blocks for link in b.links if link.startswith(("http://", "https://", "mailto:"))}
    for kind, path in outputs.items():
        label = "HTML" if kind == "web" else kind.upper()
        add(label, "파일 생성", output_ok[kind])
        if not output_ok[kind]:
            continue
        try:
            if kind in ("web", "epub"):
                if kind == "web":
                    tree = html.parse(str(path)).getroot()
                    read_asset = lambda name: (path.parent / "assets" / name).read_bytes()
                else:
                    with ZipFile(path) as book:
                        files = {name: book.read(name) for name in book.namelist()}
                    tree = html.fromstring(files["EPUB/chapter.xhtml"])
                    read_asset = lambda name: files["EPUB/assets/" + name]
                sections = tree.xpath("//section[@data-source-id]")
                if outline:
                    headings = tree.xpath("//*[@data-outline-id]")
                    expected_outline = [(n["id"], f'h{n["level"]}', n["title"]) for n in outline]
                    # Number labels are separately retained in the original source heading.
                    for heading in headings:
                        for marker in heading.xpath(".//span[@class='list-label']"):
                            marker.drop_tree()
                    actual_outline = [(n.get("data-outline-id"), n.tag, n.text_content()) for n in headings]
                    add(label, "장·절·소단원 제목과 순서", actual_outline == expected_outline)
                    toc_links = tree.xpath("//nav[@class='book-toc']//a/@href")
                    add(label, "목차 연결", toc_links == ['#' + n['id'] for n in outline])
                    if kind == "epub":
                        nav = html.fromstring(files["EPUB/nav.xhtml"])
                        links = nav.xpath("//nav//a/@href")
                        add(label, "EPUB 탐색 목차", links == ['chapter.xhtml#' + n['id'] for n in outline])
                add(label, "본문과 순서", [s.get("data-source-id") for s in sections] == [b.id for b in master.blocks])
                missing_text = []
                for block, node in zip(master.blocks, sections):
                    for marker in node.xpath(".//span[@class='list-label']"):
                        marker.drop_tree()
                    if compact(node.text_content()) != compact(block_text(block)):
                        missing_text.append(block.id)
                add(label, "본문·표·숫자·수식 내용", not missing_text, ", ".join(missing_text))
                actual = [node.get("src", "").split("/")[-1] for node in tree.xpath("//img")]
                add(label, "이미지 개수·순서·파일", actual == names and all(sha256(read_asset(name)).hexdigest() == file_hash(assets / name) for name in names), f"{len(actual)}개")
                add(label, "표 개수", len(tree.xpath("//table")) == counts.get("table", 0))
                add(label, "링크", expected_links <= {n.get("href") for n in tree.xpath("//a")}, f"{len(expected_links)}개 주소")
                add(label, "설명·이미지·캡션 연결", [node.get("data-group", "") for node in sections] == [b.group for b in master.blocks])
            elif kind == "pdf":
                with pymupdf.open(path) as document:
                    if outline:
                        add(label, "장·절·소단원 책갈피", [(n[0], n[1]) for n in document.get_toc()] == [(n['level'], n['title']) for n in outline])
                    text = compact("".join(page.get_textbox(pymupdf.Rect(0, 0, page.rect.width, 800)) for page in document))
                    cursor, missing_text = 0, []
                    for block in master.blocks:
                        expected = compact(block_text(block))
                        if not expected:
                            continue
                        found = text.find(expected, cursor)
                        if found < 0:
                            missing_text.append(block.id)
                        else:
                            cursor = found + len(expected)
                    add(label, "본문·표·수식·숫자·순서", not missing_text, ", ".join(missing_text))
                    images = [i["digest"] for page in document for i in page.get_image_info(hashes=True)]
                    expected_images = [image_digest(assets / name) for name in names]
                    add(label, "이미지 개수·순서·화소", images == expected_images, f"{len(images)}개")
                    actual_links = {link.get("uri") for page in document for link in page.get_links()}
                    add(label, "링크", expected_links <= actual_links, f"{len(expected_links)}개 주소")
        except Exception as exc:
            add(label, "결과물 열기 및 내용 검사", False, type(exc).__name__)
    return {"source_hash_ok": original_ok, "block_counts": dict(counts), "image_count": len(names),
            "hyperlink_count": len(expected_links), "missing_images": missing, "output_ok": output_ok,
            "checks": checks, "warnings": sorted(set(warnings)), "passed": all(item["passed"] for item in checks)}


def save_report(report, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def quality_html(report, path, source_name, outputs):
    rows = "".join(f"<tr><td>{escape(item['format'])}</td><td>{escape(item['label'])}</td><td>{'확인 완료' if item['passed'] else '확인 필요'}</td><td>{escape(item['detail'])}</td></tr>" for item in report["checks"])
    warnings = "".join(f"<li>{escape(text)}</li>" for text in report.get("warnings", []))
    title = "확인 완료" if report["passed"] and not warnings else "확인할 항목이 있습니다"
    links = "".join(f"<li>{'HTML' if kind == 'web' else kind.upper()}: {escape(str(file))}</li>" for kind, file in outputs.items())
    path.write_text(f"""<!doctype html><html lang="ko"><meta charset="utf-8"><title>결과물 품질 확인</title>
<style>body{{font-family:'Malgun Gothic',sans-serif;max-width:980px;margin:2rem auto;line-height:1.7;padding:1rem}}table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #ccd3dd;padding:.6rem;text-align:left}}</style>
<h1>결과물 품질 확인: {title}</h1><p>{escape(source_name)}</p><ul>{warnings}</ul>
<table><tr><th>대상</th><th>검사 항목</th><th>결과</th><th>상세</th></tr>{rows}</table><h2>저장한 결과물</h2><ul>{links}</ul></html>""", encoding="utf-8")
