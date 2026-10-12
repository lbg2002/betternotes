# SPDX-License-Identifier: GPL-3.0-or-later
"""Typography should be lightweight, stable and safe for CSS generation."""
import unittest

from betternotes.font_settings import make_font_css, normalize_size, sanitize_family


class FontSettingsTests(unittest.TestCase):
    def test_font_family_unicode(self):
        self.assertEqual(sanitize_family('  思源黑体  '), '思源黑体')
        self.assertIn('font-family: "Noto Sans CJK SC"', make_font_css('Noto Sans CJK SC', 17))
        self.assertIn('font-family: "思源黑体"', make_font_css('思源黑体', 18))

    def test_system_default(self):
        css = make_font_css('', 14)
        self.assertNotIn('font-family:', css)
        self.assertIn('font-size: 14px', css)

    def test_safe_escaping_and_range(self):
        for injected in ['Bad"; color: red', 'Test\\Name', 'evil{a}', 'A\nB']:
            self.assertEqual(sanitize_family(injected), '')
            self.assertNotIn('color: red', make_font_css(injected, 99))
        self.assertEqual(normalize_size(2), 10)
        self.assertEqual(normalize_size(99), 32)
        self.assertEqual(normalize_size('invalid'), 14)
        self.assertIn('font-size: 32px;', make_font_css(size=100))


if __name__ == '__main__':
    unittest.main()
