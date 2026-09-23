"""PDF code lines are rendered with fixed indentation, without paragraph reflow."""
from reportlab.platypus import Flowable
from reportlab.lib.colors import HexColor
from reportlab.pdfbase.pdfmetrics import stringWidth


def runs(text):
    current, font = "", None
    for char in text:
        selected = "CodeMono" if ord(char) < 128 else "Malgun"
        if selected != font and current:
            yield font, current
            current = ""
        font = selected
        current += char
    if current:
        yield font, current


def line_width(text, size):
    return sum(stringWidth(value, font, size) for font, value in runs(text.expandtabs(4)))


class CodeBlock(Flowable):
    def __init__(self, block_id, text, evidence, first_line=0, size=None, kind="code-block", accent="#087f78"):
        super().__init__()
        self.block_id, self.lines, self.evidence = block_id, text.split("\n"), evidence
        self.first_line, self.size = first_line, size
        self.kind = kind
        self.accent = accent
        self.spaceBefore, self.spaceAfter = 5, 7

    def wrap(self, available_width, available_height):
        self.width = available_width
        if self.size is None:
            longest = max((line_width(line, 9) for line in self.lines), default=0)
            self.size = min(9, 9 * (available_width - 16) / max(longest, 1))
        if self.size < 6:
            raise ValueError("PDF 코드가 너무 길어 읽을 수 있는 크기로 배치할 수 없습니다: " + self.block_id)
        self.leading = self.size * 1.6
        self.height = self.leading * len(self.lines) + 12
        return self.width, self.height

    def split(self, available_width, available_height):
        self.wrap(available_width, available_height)
        count = int((available_height - 12) / self.leading)
        if count < 1 or count >= len(self.lines):
            return []
        return [CodeBlock(self.block_id, "\n".join(self.lines[:count]), self.evidence, self.first_line, self.size, self.kind, self.accent),
                CodeBlock(self.block_id, "\n".join(self.lines[count:]), self.evidence, self.first_line + count, self.size, self.kind, self.accent)]

    def draw(self):
        canvas = self.canv
        canvas.saveState()
        canvas.setFillColorRGB(.96, .97, .98)
        canvas.rect(0, 0, self.width, self.height, fill=1, stroke=0)
        canvas.setFillColor(HexColor(self.accent))
        canvas.rect(0, 0, 2, self.height, fill=1, stroke=0)
        canvas.setFillColorRGB(.12, .15, .20)
        for offset, original in enumerate(self.lines):
            y = self.height - 8 - self.size - offset * self.leading
            x = 8
            for font, value in runs(original.expandtabs(4)):
                canvas.setFont(font, self.size)
                canvas.drawString(x, y, value)
                x += stringWidth(value, font, self.size)
            absolute_x, absolute_y = canvas.absolutePosition(8, y)
            self.evidence.append({"id": self.block_id, "kind": self.kind, "line": self.first_line + offset,
                                  "text": original, "page": canvas.getPageNumber() - 1,
                                  "x": absolute_x, "baseline": canvas._pagesize[1] - absolute_y,
                                  "width": x - 8, "size": self.size, "leading": self.leading})
        canvas.restoreState()
