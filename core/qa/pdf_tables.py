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
        # Text extraction drops trailing zero-width glyphs. Read the actual
        # drawing operations instead, retaining their Unicode and source order.
        # Invisible text (render mode 3) is not evidence of visible content.
        for span in page.get_texttrace():
            if span['type'] == 3 or span.get('opacity', 1) == 0:
                continue
            for codepoint, glyph, origin, bounds in span['chars']:
                rect = pymupdf.Rect(bounds)
                center = (rect.tl + rect.br) / 2
                matches = [key for key, cell_bounds in by_page[page_no] if cell_bounds.contains(center)]
                if len(matches) > 1:
                    raise ValueError('Overlapping PDF table cells')
                value = chr(codepoint)
                if matches:
                    key = matches[0]
                    cells[key] += value
                    if key[0] not in seen:
                        stream.append(table_marker(key[0]))
                        seen.add(key[0])
                elif rect.y1 <= 800:
                    stream.append(value)
    return ''.join(stream), cells
