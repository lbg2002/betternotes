# SPDX-License-Identifier: GPL-3.0-or-later

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk
from betternotes.i18n import _


class ShortcutsWindow(Gtk.ShortcutsWindow):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        section = Gtk.ShortcutsSection(visible=True, section_name='shortcuts')

        # General group
        general = Gtk.ShortcutsGroup(title='General', visible=True)
        general.append(Gtk.ShortcutsShortcut(
            title=_('New note'),
            accelerator='<Control>n',
            visible=True,
        ))
        general.append(Gtk.ShortcutsShortcut(
            title=_('New plan'),
            accelerator='<Control><Shift>n',
            visible=True,
        ))
        general.append(Gtk.ShortcutsShortcut(
            title='Quit',
            accelerator='<Control>q',
            visible=True,
        ))
        general.append(Gtk.ShortcutsShortcut(
            title='Preferences',
            accelerator='<Control>comma',
            visible=True,
        ))
        general.append(Gtk.ShortcutsShortcut(
            title='Keyboard Shortcuts',
            accelerator='<Control>question',
            visible=True,
        ))
        general.append(Gtk.ShortcutsShortcut(
            title='Select All (in selection mode)',
            accelerator='<Control>a',
            visible=True,
        ))
        general.append(Gtk.ShortcutsShortcut(
            title='Exit Selection Mode',
            accelerator='Escape',
            visible=True,
        ))
        section.append(general)

        # Formatting group
        formatting = Gtk.ShortcutsGroup(title='Text Formatting', visible=True)
        formatting.append(Gtk.ShortcutsShortcut(
            title='Bold',
            accelerator='<Control>b',
            visible=True,
        ))
        formatting.append(Gtk.ShortcutsShortcut(
            title='Italic',
            accelerator='<Control>i',
            visible=True,
        ))
        formatting.append(Gtk.ShortcutsShortcut(
            title='Underline',
            accelerator='<Control>u',
            visible=True,
        ))
        formatting.append(Gtk.ShortcutsShortcut(
            title='Strikethrough',
            accelerator='<Control>d',
            visible=True,
        ))
        section.append(formatting)

        self.add_section(section)
