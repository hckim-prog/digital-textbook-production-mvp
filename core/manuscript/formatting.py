"""Restore source-backed Symbol font hints after plain-text corrections."""
from copy import deepcopy


def restore_symbol_fonts(master, source):
    """Change display metadata only; never replace a character or a cached edit.

    Word's private-use symbols need their original font. Plain-text AI edits
    discard runs, so recover only unambiguous Symbol hints from the same block.
    This runs after correction/learning baseline validation and before export.
    """
    result = deepcopy(master)
    originals = {b.id: b for b in source.blocks}
    for block in result.blocks:
        original = originals.get(block.id)
        if original is None:
            continue
        fonts = {}
        for item in original.inlines:
            if item.get('kind') != 'text':
                continue
            for char in item.get('text', ''):
                if '\ue000' <= char <= '\uf8ff':
                    fonts.setdefault(char, set()).add(item.get('font', ''))
        symbols = {char for char, hints in fonts.items() if hints == {'Symbol'}}
        if not symbols:
            continue
        restored = []
        for item in block.inlines:
            if item.get('kind') != 'text' or item.get('font'):
                restored.append(item)
                continue
            buffer, symbol_run = '', None
            for char in item.get('text', ''):
                is_symbol = char in symbols
                if buffer and is_symbol != symbol_run:
                    restored.append({**item, 'text': buffer, **({'font': 'Symbol'} if symbol_run else {})})
                    buffer = ''
                buffer += char
                symbol_run = is_symbol
            if buffer:
                restored.append({**item, 'text': buffer, **({'font': 'Symbol'} if symbol_run else {})})
            elif not item.get('text', ''):
                restored.append(item)
        block.inlines = restored
    return result
