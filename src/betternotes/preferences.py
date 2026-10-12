# SPDX-License-Identifier: GPL-3.0-or-later

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Adw, Gio, Gtk, Pango

from betternotes.colors import COLOR_NAMES
from betternotes.constants import APP_ID
from betternotes.i18n import _
from betternotes.font_settings import sanitize_family


class PreferencesWindow(Adw.PreferencesDialog):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.set_title(_('Preferences'))

        self._settings = None
        self._resetting_font = False
        schema_source = Gio.SettingsSchemaSource.get_default()
        if schema_source and schema_source.lookup(APP_ID, True):
            self._settings = Gio.Settings.new(APP_ID)

        self._build_ui()

    def _build_ui(self):
        # General page
        page = Adw.PreferencesPage(title=_('General'), icon_name='preferences-system-symbolic')

        # Appearance group
        appearance_group = Adw.PreferencesGroup(title=_('Appearance'))

        # Default color
        color_row = Adw.ComboRow(title=_('Default Note Color'))
        color_list = Gtk.StringList()
        for name in COLOR_NAMES:
            color_list.append(name.capitalize())
        color_row.set_model(color_list)

        if self._settings:
            current = self._settings.get_string('default-color')
            try:
                idx = COLOR_NAMES.index(current)
                color_row.set_selected(idx)
            except ValueError:
                pass
            color_row.connect('notify::selected', self._on_color_changed)

        appearance_group.add(color_row)
        page.add(appearance_group)

        # Trash group
        trash_group = Adw.PreferencesGroup(title=_('Trash'))

        retention_row = Adw.SpinRow(
            title=_('Auto-delete after (days)'),
            subtitle=_('Trashed notes are permanently deleted after this many days'),
        )
        adjustment = Gtk.Adjustment(
            lower=1, upper=365, step_increment=1, page_increment=7, value=30,
        )
        retention_row.set_adjustment(adjustment)

        if self._settings:
            retention_row.set_value(self._settings.get_int('trash-retention-days'))
            retention_row.connect('notify::value', self._on_retention_changed)

        trash_group.add(retention_row)
        page.add(trash_group)

        ui_group = Adw.PreferencesGroup(title=_('Appearance'))
        language_row = Adw.ComboRow(title=_('Language'),
                                   subtitle=_('Restart to apply language changes'))
        languages = ['system', 'zh_CN', 'en']
        model = Gtk.StringList()
        for item in [_('Follow system'), _('Chinese (Simplified)'), 'English']:
            model.append(item)
        language_row.set_model(model)
        if self._settings:
            saved = self._settings.get_string('ui-language')
            language_row.set_selected(languages.index(saved) if saved in languages else 0)
            language_row.connect('notify::selected',
                lambda row, spec: self._settings.set_string('ui-language', languages[row.get_selected()]))
        ui_group.add(language_row)

        format_row = Adw.SwitchRow(title=_('Show formatting toolbar'),
                                   subtitle=_('Compact mode'))
        if self._settings:
            self._settings.bind('show-format-toolbar', format_row, 'active',
                                Gio.SettingsBindFlags.DEFAULT)
        ui_group.add(format_row)
        page.add(ui_group)

        # Typography applies immediately to note bodies, plan items and cards.
        # Gtk.FontDialogButton is available since GTK 4.10 (Ubuntu 24.04+).
        font_group = Adw.PreferencesGroup(title=_('Typography'))
        font_group.set_description(_('Applies to notes, checklists and previews'))

        family_row = Adw.ActionRow(title=_('Font family'),
                                   subtitle=_('Choose an installed system font'))
        self._font_button = Gtk.FontDialogButton.new(Gtk.FontDialog())
        self._font_button.set_use_font(False)
        self._font_button.set_use_size(False)
        self._font_button.set_valign(Gtk.Align.CENTER)
        stored_family = (
            sanitize_family(self._settings.get_string('font-family'))
            if self._settings else ''
        )
        self._font_button.set_font_desc(
            Pango.FontDescription.from_string(stored_family or 'Sans')
        )
        family_row.add_suffix(self._font_button)
        family_row.set_activatable_widget(self._font_button)
        self._font_button.connect('notify::font-desc', self._on_font_changed)
        font_group.add(family_row)

        size_row = Adw.SpinRow(
            title=_('Font size'),
            subtitle=_('Pixels — affects note text and plan items'),
        )
        size_row.set_adjustment(Gtk.Adjustment(
            lower=10, upper=32, step_increment=1, page_increment=2, value=14
        ))
        size_row.set_value(self._settings.get_int('font-size') if self._settings else 14)
        size_row.connect('notify::value', self._on_font_size_changed)
        self._size_row = size_row
        font_group.add(size_row)

        reset_row = Adw.ActionRow(title=_('System font and default size'),
                                  subtitle=_('Restore default typography'))
        reset_button = Gtk.Button(label=_('Reset typography'))
        reset_button.add_css_class('flat')
        reset_button.set_valign(Gtk.Align.CENTER)
        reset_button.connect('clicked', self._on_reset_typography)
        reset_row.add_suffix(reset_button)
        reset_row.set_activatable_widget(reset_button)
        font_group.add(reset_row)

        preview = Gtk.Label(label=_('Font preview: 论文计划 ABC 123'),
                            wrap=True, xalign=0)
        preview.add_css_class('plan-font-preview')
        preview.set_margin_top(6)
        preview.set_margin_bottom(6)
        font_group.add(preview)
        page.add(font_group)
        self.add(page)

    def _on_color_changed(self, row, pspec):
        if self._settings:
            idx = row.get_selected()
            if 0 <= idx < len(COLOR_NAMES):
                self._settings.set_string('default-color', COLOR_NAMES[idx])

    def _on_retention_changed(self, row, pspec):
        if self._settings:
            self._settings.set_int('trash-retention-days', int(row.get_value()))

    def _on_font_changed(self, picker, spec):
        if self._settings and not self._resetting_font:
            desc = picker.get_font_desc()
            if desc:
                family = sanitize_family(desc.get_family() or '')
                self._settings.set_string('font-family', family)

    def _on_font_size_changed(self, row, spec):
        if self._settings:
            self._settings.set_int('font-size', int(row.get_value()))

    def _on_reset_typography(self, button):
        if not self._settings:
            return
        self._resetting_font = True
        try:
            self._settings.reset('font-family')
            self._settings.reset('font-size')
            # Avoid writing "Sans" over the truly empty system-default setting.
            self._font_button.set_font_desc(Pango.FontDescription.from_string('Sans'))
            self._size_row.set_value(14)
        finally:
            self._resetting_font = False
