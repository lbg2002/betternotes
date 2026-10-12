# SPDX-License-Identifier: GPL-3.0-or-later
"""Live typography CSS shared by note, checklist and gallery widgets.

The application keeps the selected font in GSettings, never in note content.
A blank family follows the desktop font. Font size is in CSS pixels.
"""


def sanitize_family(value):
    if not isinstance(value, str):
        return ''
    value = value.strip()
    if not value or len(value) > 128:
        return ''
    # Reject CSS metacharacters rather than trusting a manually edited setting.
    if any(ord(ch) < 32 or ch in '"\\{};' for ch in value):
        return ''
    return value


def normalize_size(value):
    try:
        return min(32, max(10, int(value)))
    except (TypeError, ValueError):
        return 14


def make_font_css(family='', size=14):
    family = sanitize_family(family)
    size = normalize_size(size)
    declaration = f'font-family: "{family}";' if family else ''
    return (
        ".note-text-view, .plan-label, .plan-item entry, "
        ".note-card-title, .plan-font-preview {"
        f"{declaration} font-size: {size}px; "
        "}"
        ".note-card-preview {"
        f"{declaration} font-size: {max(10, round(size * 0.86))}px; "
        "}"
        ".note-title-entry {"
        f"{declaration} font-size: {round(size * 1.29)}px; "
        "}"
        ".plan-progress {"
        f"{declaration} font-size: {max(10, round(size * 0.86))}px; "
        "}"
    )
