"""Read actual PDF glyphs by cell bounds, never from stored source text."""
from collections import defaultdict
import json
import pymupdf


def table_marker(block_id):
    return '\x00TABLE:' + block_id + '\x00'


def read_tables(document):
    layout = json.loads(document.embfile_get('table-layout.json'))
    by_page = defaultdict(list)
    cells = defaultdict(str)
    for item in layout:
        key = (item['id'], item['row'], item['col'])
        cells[key] += ''
        by_page[item['page']].append((key, pymupdf.Rect(item['rect'])))
    stream, seen = [], set()
    for page_no, page in enumerate(document):
        for block in page.get_text('rawdict')['blocks']:
            for line in block.get('lines', []):
                for span in line['spans']:
                    for char in span['chars']:
                        rect = pymupdf.Rect(char['bbox'])
                        center = (rect.tl + rect.br) / 2
                        matches = [key for key, bounds in by_page[page_no] if bounds.contains(center)]
                        if len(matches) > 1:
                            raise ValueError('Overlapping PDF table cells')
                        if matches:
                            key = matches[0]
                            cells[key] += char['c']
                            if key[0] not in seen:
                                stream.append(table_marker(key[0]))
                                seen.add(key[0])
                        elif rect.y1 <= 800:
                            stream.append(char['c'])
    return ''.join(stream), cells
