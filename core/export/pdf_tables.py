"""Keep ordinary rows intact; record rendered cell bounds for independent QA."""
from reportlab.platypus import Table


class PublicationTable(Table):
    def split(self, availWidth, availHeight):
        self._calc(availWidth, availHeight)
        # The frame has 6pt internal padding at each edge. Only rows taller
        # than a fresh frame may split internally (e.g. stacked screenshots).
        frame = getattr(getattr(self.canv, '_doctemplate', None), 'frame', None)
        full_height = frame._aH if frame is not None else 733
        original = self.splitInRow
        self.splitInRow = original if self._rowHeights[0] > full_height else 0
        try:
            parts = super().split(availWidth, availHeight)
            # ReportLab copies the temporary flag to continuation tables.
            # Re-evaluate their first row on the next frame instead.
            for part in parts:
                part.splitInRow = original
            return parts
        finally:
            self.splitInRow = original

    def _drawCell(self, cellval, cellstyle, pos, size):
        key = getattr(cellstyle, 'source_cell', None)
        if key is not None:
            x, y = self.canv.absolutePosition(*pos)
            width, height = size
            top = self.canv._pagesize[1] - y
            self.canv.table_layout.append({
                'id': key[0], 'row': key[1], 'col': key[2],
                'page': self.canv.getPageNumber() - 1,
                'rect': [x, top - height, x + width, top],
            })
        return super()._drawCell(cellval, cellstyle, pos, size)
