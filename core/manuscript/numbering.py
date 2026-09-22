"""Render common Word list formats from numbering definitions."""
import re
from docx.oxml.ns import qn


def val(element, name, default=''):
    node = element.find(qn('w:' + name)) if element is not None else None
    return node.get(qn('w:val'), default) if node is not None else default


def formatted(number, kind):
    if kind in ('lowerLetter', 'upperLetter'):
        result = ''
        while number > 0:
            number, remainder = divmod(number - 1, 26)
            result = chr(97 + remainder) + result
        return result.upper() if kind == 'upperLetter' else result
    if kind in ('lowerRoman', 'upperRoman'):
        result = ''
        for size, mark in ((1000,'M'),(900,'CM'),(500,'D'),(400,'CD'),(100,'C'),(90,'XC'),(50,'L'),(40,'XL'),(10,'X'),(9,'IX'),(5,'V'),(4,'IV'),(1,'I')):
            count, number = divmod(number, size)
            result += mark * count
        return result.lower() if kind == 'lowerRoman' else result
    return str(number)


class Numbering:
    def __init__(self, doc):
        root = doc.part.numbering_part.element
        self.nums = {n.get(qn('w:numId')): n for n in root.findall(qn('w:num'))}
        self.abstracts = {n.get(qn('w:abstractNumId')): n for n in root.findall(qn('w:abstractNum'))}
        self.counters = {}

    def label(self, paragraph):
        prop = paragraph._p.find('./' + qn('w:pPr') + '/' + qn('w:numPr'))
        style = paragraph.style
        while prop is None and style is not None:
            prop = style.element.find('./' + qn('w:pPr') + '/' + qn('w:numPr'))
            style = style.base_style
        if prop is None or val(prop, 'numId') in ('', '0'):
            return '', '', ''
        num_id, level = val(prop, 'numId'), int(val(prop, 'ilvl', '0'))
        num = self.nums.get(num_id)
        abstract = self.abstracts.get(val(num, 'abstractNumId'))
        if abstract is None:
            return num_id, '', '목록 번호 정의를 찾을 수 없어 원본 확인이 필요합니다.'
        levels = {int(n.get(qn('w:ilvl'))): n for n in abstract.findall(qn('w:lvl'))}
        starts = {}
        for override in num.findall(qn('w:lvlOverride')):
            i = int(override.get(qn('w:ilvl')))
            node = override.find(qn('w:lvl'))
            if node is not None:
                levels[i] = node
            if val(override, 'startOverride'):
                starts[i] = int(val(override, 'startOverride'))
        node = levels.get(level)
        if node is None:
            return num_id, '', '목록 단계 정의를 확인해 주세요.'
        counts = self.counters.setdefault(num_id, {})
        counts[level] = counts.get(level, starts.get(level, int(val(node, 'start', '1'))) - 1) + 1
        for lower in list(counts):
            if lower > level and val(levels.get(lower), 'lvlRestart') != '0':
                del counts[lower]
        pattern = val(node, 'lvlText', '%1.')
        kind = val(node, 'numFmt', 'decimal')
        if kind == 'bullet':
            return num_id, '•' if any(ord(c) >= 0xF000 for c in pattern) else pattern, ''
        warning = '' if kind in ('decimal','lowerLetter','upperLetter','lowerRoman','upperRoman','none') else '특수 목록 번호 형식은 원본과 대조해 주세요.'
        label = re.sub(r'%([1-9])', lambda m: formatted(counts.get(int(m[1])-1, int(val(levels.get(int(m[1])-1), 'start', '1'))), val(levels.get(int(m[1])-1), 'numFmt', 'decimal')), pattern)
        return num_id, '' if kind == 'none' else label, warning
