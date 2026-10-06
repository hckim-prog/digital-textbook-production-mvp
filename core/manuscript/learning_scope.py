"""Identify study content without rewriting source blocks or saved outlines."""
import re

LABEL = re.compile(r'^(?:장말\s*)?(?:연습\s*문제|확인\s*문제|절\s*확인\s*활동|퀴즈)\s*[:：]?\s*$')
PLACEHOLDER_ONLY = re.compile(r'^\s*[（(]?\s*추후\s*제공\s*[）)]?\s*[.!]?\s*$')


def has_learning_content(blocks, nodes):
    # A generated heading shares its anchor with real prose; only source-title
    # anchors are excluded. Do not impose a length threshold on short lessons.
    titles = {n['start_block_id'] for n in nodes if n.get('use_source_title', True)}
    for block in blocks:
        if block.id in titles or block.kind in {'heading', 'figure', 'figure-caption'}:
            continue
        if block.rows and any(value.strip() for row in block.rows for value in row):
            return True
        if block.text.strip() and not LABEL.fullmatch(block.text.strip()) and not PLACEHOLDER_ONLY.fullmatch(block.text):
            return True
    return False
