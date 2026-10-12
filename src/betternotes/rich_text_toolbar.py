# SPDX-License-Identifier: GPL-3.0-or-later

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Adw, GObject, Gtk
from betternotes.i18n import _


class RichTextToolbar(Gtk.Box):
    """Formatting toolbar with Bold/Italic/Underline/Strikethrough/Bullet toggles."""

    __gsignals__ = {
        'format-toggled': (GObject.SignalFlags.RUN_LAST, None, (str, bool)),
    }

    def __init__(self, **kwargs):
        super().__init__(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=4,
            **kwargs,
        )
        self.add_css_class('rich-text-toolbar')

        self._buttons = {}
        self._updating = False

        format_items = [
            ('bold', 'format-text-bold-symbolic', '<Control>b'),
            ('italic', 'format-text-italic-symbolic', '<Control>i'),
            ('underline', 'format-text-underline-symbolic', '<Control>u'),
            ('strikethrough', 'format-text-strikethrough-symbolic', '<Control>d'),
        ]

        for name, icon, accel in format_items:
            btn = Gtk.ToggleButton(
                icon_name=icon,
                tooltip_text=f'{name.capitalize()} ({accel})',
            )
            btn.connect('toggled', self._on_toggled, name)
            self.append(btn)
            self._buttons[name] = btn

        # Separator
        self.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))

        # Bullet list
        btn = Gtk.ToggleButton(
            icon_name='view-list-symbolic',
            tooltip_text=_('Bullet List'),
        )
        btn.connect('toggled', self._on_toggled, 'bullet')
        self.append(btn)
        self._buttons['bullet'] = btn

    def _on_toggled(self, button, format_name):
        if not self._updating:
            self.emit('format-toggled', format_name, button.get_active())

    def update_state(self, active_formats):
        """Update toggle button states based on cursor position."""
        self._updating = True
        for name, btn in self._buttons.items():
            btn.set_active(name in active_formats)
        self._updating = False
