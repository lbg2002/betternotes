# SPDX-License-Identifier: GPL-3.0-or-later
"""Tiny dependency-free Markdown preview for PinPlan sticky notes.

Source stays in the *existing* rich-text editor/JSON format. This module
only creates a read-only Gtk.TextBuffer view: no HTML engine, WebKit, CSS
downloads, external resources, or changes to persisted note content.

Supported: headings, emphasis, code, links (URL shown), blockquotes,
horizontal rules, bullet/numbered/task lists, fenced blocks, simple tables.
"""
import re

_INLINE = re.compile(
    r'\[([^\]\n]{1,160})\]\((https?://[^\s)\n]{1,500})\)'
    r'|\x60([^\x60\n]+)\x60'
    r'|\*\*(.+?)\*\*|__(.+?)__'
    r'|~~(.+?)~~'
    r'|(?<!\*)\*(?!\*)(.+?)\*(?!\*)'
    r'|(?<!_)_(?!_)(.+?)_(?!_)'
)
_HEAD = re.compile(r'^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$')
_BULLET = re.compile(r'^\s{0,8}[-+*]\s+(.*)$')
_ORDERED = re.compile(r'^\s{0,8}(\d{1,4})[.)]\s+(.*)$')
_QUOTE = re.compile(r'^\s{0,3}>\s?(.*)$')
_RULE = re.compile(r'^\s{0,3}(?:-{3,}|\*{3,}|_{3,})\s*$')
_TABLE_DIVIDER = re.compile(r'^\s*\|?\s*:?-{3,}:?(?:\s*\|\s*:?-{3,}:?)+\s*\|?\s*$')
_TASK = re.compile(r'^\[([ xX])\]\s+(.*)$')


def _inline(text, style=()):
    """Yield (visible text, tag tuple). Never evaluate Markdown as markup."""
    pos = 0
    for match in _INLINE.finditer(text):
        if match.start() > pos:
            yield text[pos:match.start()], style
        groups = match.groups()
        if groups[0] is not None:
            # Links remain fully legible without clickable web content.
            yield groups[0], style + ('md-link',)
            yield ' (' + groups[1] + ')', style + ('md-muted',)
        elif groups[2] is not None:
            yield groups[2], style + ('md-code',)
        elif groups[3] is not None or groups[4] is not None:
            yield groups[3] if groups[3] is not None else groups[4], style + ('md-bold',)
        elif groups[5] is not None:
            yield groups[5], style + ('md-strike',)
        else:
            yield groups[6] if groups[6] is not None else groups[7], style + ('md-italic',)
        pos = match.end()
    if pos < len(text):
        yield text[pos:], style


def parse_markdown(source):
    """Return a flat stream of (visible text, tag tuple), easy to unit test."""
    if not source:
        return []
    output = []
    fenced = False
    lines = source.split('\n')
    for i, original in enumerate(lines):
        line = original
        style = ()
        prefix = ''
        if line.lstrip().startswith('\\\x60\\\x60\\\x60'):
            pass
        if re.match(r'^\s{0,3}(?:\x60{3,}|~{3,})', line):
            fenced = not fenced
            # Skip the language hint / closing fence, not the block contents.
            if i != len(lines) - 1:
                output.append(('\n', ()))
            continue
        if fenced:
            output.append((line, ('md-block-code',)))
        elif _RULE.fullmatch(line):
            output.append(('────────────────────', ('md-muted',)))
        elif _TABLE_DIVIDER.fullmatch(line):
            # Table alignment separator is structural, not content.
            pass
        else:
            heading = _HEAD.match(line)
            quote = _QUOTE.match(line)
            bullet = _BULLET.match(line)
            ordered = _ORDERED.match(line)
            if heading:
                line = heading.group(2)
                style = ('md-h' + str(len(heading.group(1))),)
            elif quote:
                line = quote.group(1)
                prefix = '▏ '
                style = ('md-quote',)
            elif bullet or ordered:
                line = (bullet or ordered).group(1 if bullet else 2)
                task = _TASK.match(line)
                if task:
                    prefix = '☑ ' if task.group(1).lower() == 'x' else '☐ '
                    line = task.group(2)
                else:
                    prefix = '• ' if bullet else ordered.group(1) + '. '
                style = ('md-list',)
            elif line.strip().startswith('|') and line.strip().endswith('|'):
                # Lightweight single-line table representation, no HTML engine.
                line = '  │  '.join(cell.strip() for cell in line.strip().strip('|').split('|'))
                style = ('md-table',)
            if prefix:
                output.append((prefix, style))
            output.extend(_inline(line, style))
        if i < len(lines) - 1:
            output.append(('\n', ()))
    return output


def render_markdown(buffer, source):
    """Build a read-only GTK buffer using Pango tags; never touch editor buffer."""
    from gi.repository import Pango
    tags = {
        'md-h1': {'weight': 700, 'scale': 1.7},
        'md-h2': {'weight': 700, 'scale': 1.4},
        'md-h3': {'weight': 700, 'scale': 1.2},
        'md-h4': {'weight': 700, 'scale': 1.1},
        'md-h5': {'weight': 700},
        'md-h6': {'weight': 700},
        'md-bold': {'weight': 700},
        'md-italic': {'style': Pango.Style.ITALIC},
        'md-strike': {'strikethrough': True},
        'md-code': {'family': 'monospace', 'background': '#dddddd', 'foreground': '#272727'},
        'md-block-code': {'family': 'monospace'},
        'md-link': {'underline': Pango.Underline.SINGLE},
        'md-muted': {'foreground': '#666666'},
        'md-quote': {'style': Pango.Style.ITALIC},
        'md-list': {},
        'md-table': {'family': 'monospace'},
    }
    buffer.set_text('')
    for name, props in tags.items():
        if buffer.get_tag_table().lookup(name) is None:
            buffer.create_tag(name, **props)
    for value, names in parse_markdown(source):
        if not value:
            continue
        start = buffer.get_end_iter().get_offset()
        buffer.insert(buffer.get_end_iter(), value)
        begin = buffer.get_iter_at_offset(start)
        end = buffer.get_end_iter()
        for name in names:
            buffer.apply_tag_by_name(name, begin, end)
