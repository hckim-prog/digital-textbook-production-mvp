import json

import pymupdf
from reportlab.platypus import Paragraph
from reportlab.lib.styles import getSampleStyleSheet

from core.export.outputs import pdf
from core.export.pdf_tables import PublicationTable
from core.master import Block, Master, file_hash
from core.qa.checks import check


def test_ordinary_row_moves_instead_of_splitting():
    table = PublicationTable([[Paragraph('word ' * 70, getSampleStyleSheet()['BodyText'])]],
                             colWidths=[180], splitInRow=1)
    from reportlab.pdfgen.canvas import Canvas
    import io
    table.canv = Canvas(io.BytesIO())
    assert table.wrap(180, 733)[1] < 733
    assert table.split(180, 50) == []


def test_oversize_row_cells_preserved_and_missing_glyph_detected(tmp_path):
    source = tmp_path / 'source.txt'
    source.write_text('test', encoding='utf-8')
    rows = [['첫 번째 열', '두 번째 열'],
            ['LEFT ' + '가나다 ' * 800, 'RIGHT 마지막 셀 12345']]
    master = Master('표 검증', source.name, file_hash(source), [
        Block('before', 'paragraph', '표 앞 본문'),
        Block('table', 'table', rows=rows),
        Block('after', 'paragraph', '표 뒤 본문'),
    ])
    path = pdf(master, tmp_path, tmp_path / 'pdf')
    report = check(master, source, tmp_path, {'pdf': path})
    assert report['passed'], report['checks']
    with pymupdf.open(path) as doc:
        layout = json.loads(doc.embfile_get('table-layout.json'))
        assert len({item['page'] for item in layout}) >= 2
        page = next(page for page in doc if page.search_for('12345'))
        page.add_redact_annot(page.search_for('12345')[0], fill=(1, 1, 1))
        page.apply_redactions()
        doc.saveIncr()
    damaged = check(master, source, tmp_path, {'pdf': path})
    assert not damaged['passed']
    assert any(c['label'] == '표 셀별 내용·페이지 연결' and not c['passed'] for c in damaged['checks'])
