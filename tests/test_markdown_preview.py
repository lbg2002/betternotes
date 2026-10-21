# SPDX-License-Identifier: GPL-3.0-or-later
"""Markdown preview is dependency-free and must never change source strings."""
import unittest
from betternotes.markdown_preview import parse_markdown


def text_of(source):
    return ''.join(chunk for chunk, _ in parse_markdown(source))


class MarkdownPreviewTest(unittest.TestCase):
    def test_headings_bold_italic_strike_and_code(self):
        source = '# 标题\n## Subtitle\n**bold** *italic* ~~deleted~~ `x=1`'
        rows = parse_markdown(source)
        self.assertEqual(text_of(source),
                         '标题\nSubtitle\nbold italic deleted x=1')
        self.assertIn(('标题', ('md-h1',)), rows)
        self.assertIn(('Subtitle', ('md-h2',)), rows)
        self.assertIn(('bold', ('md-bold',)), rows)
        self.assertIn(('italic', ('md-italic',)), rows)
        self.assertIn(('deleted', ('md-strike',)), rows)
        self.assertIn(('x=1', ('md-code',)), rows)

    def test_lists_checkbox_quote(self):
        text = '- [x] Done\n- [ ] Todo\n1. First\n> Quoted'
        result = text_of(text)
        for value in ('☑ Done', '☐ Todo', '1. First', '▏ Quoted'):
            self.assertIn(value, result)

    def test_code_fence_does_not_parse_inner_markdown(self):
        pieces = parse_markdown('```python\n# not a heading\n**literally**\n```')
        self.assertIn(('# not a heading', ('md-block-code',)), pieces)
        self.assertIn(('**literally**', ('md-block-code',)), pieces)
        self.assertNotIn(('literally', ('md-bold',)), pieces)

    def test_links_and_untrusted_html_as_literal(self):
        source = '[docs](https://example.com) <script>alert(1)</script>'
        result = text_of(source)
        self.assertIn('docs (https://example.com)', result)
        self.assertIn('<script>alert(1)</script>', result)

    def test_table_and_empty_source(self):
        source = '| A | B |\n| --- | --- |\n| 1 | 2 |'
        shown = text_of(source)
        self.assertIn('A  │  B', shown)
        self.assertIn('1  │  2', shown)
        self.assertNotIn('---', shown)
        self.assertEqual(parse_markdown(''), [])


if __name__ == '__main__':
    unittest.main()
