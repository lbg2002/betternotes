# SPDX-License-Identifier: GPL-3.0-or-later

import os
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Adw, Gdk, Gio, GLib, GObject, Gtk

from betternotes.constants import APP_ID
from betternotes.i18n import _
from betternotes.note_store import NoteStore
from betternotes.main_window import MainWindow


class BetterNotesApp(Adw.Application):

    __gsignals__ = {
        'note-changed': (GObject.SignalFlags.RUN_LAST, None, (str,)),
        'note-created': (GObject.SignalFlags.RUN_LAST, None, (str,)),
        'note-trashed': (GObject.SignalFlags.RUN_LAST, None, (str,)),
        'note-restored': (GObject.SignalFlags.RUN_LAST, None, (str,)),
        'note-deleted': (GObject.SignalFlags.RUN_LAST, None, (str,)),
    }

    def __init__(self, version='0.1.2', **kwargs):
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
            **kwargs,
        )
        self.version = version
        self.store = None
        self._note_windows = {}

    def do_startup(self):
        Adw.Application.do_startup(self)
        self.store = NoteStore()
        self._load_css()
        self._setup_actions()
        self._setup_shortcuts()

    def _load_css(self):
        css_provider = Gtk.CssProvider()
        loaded = False

        # Try gresource first
        try:
            resources = Gio.resources_lookup_data(
                '/com/github/paperhead/BetterNotes/style.css',
                Gio.ResourceLookupFlags.NONE,
            )
            if resources:
                css_provider.load_from_resource('/com/github/paperhead/BetterNotes/style.css')
                loaded = True
        except GLib.Error:
            pass

        # Fallback: load from filesystem (dev mode)
        if not loaded:
            search_paths = [
                # Installed location next to the module
                os.path.join(os.path.dirname(os.path.dirname(
                    os.path.abspath(__file__))), 'style.css'),
                # Source tree
                os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
                    os.path.abspath(__file__)))), 'data', 'resources', 'style.css'),
            ]
            for css_path in search_paths:
                if os.path.exists(css_path):
                    css_provider.load_from_path(css_path)
                    break

        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

    def _setup_actions(self):
        actions = [
            ('new-note', self._on_new_note, None),
            ('about', self._on_about, None),
            ('quit', self._on_quit, None),
            ('preferences', self._on_preferences, None),
            ('shortcuts', self._on_shortcuts, None),
        ]
        for name, callback, param_type in actions:
            action = Gio.SimpleAction.new(name, param_type)
            action.connect('activate', callback)
            self.add_action(action)

    def _setup_shortcuts(self):
        self.set_accels_for_action('app.new-note', ['<Control>n'])
        self.set_accels_for_action('app.quit', ['<Control>q'])
        self.set_accels_for_action('app.shortcuts', ['<Control>question'])
        self.set_accels_for_action('app.preferences', ['<Control>comma'])

    def do_activate(self):
        win = self.get_active_window()
        if win and isinstance(win, MainWindow):
            win.present()
            return
        win = MainWindow(application=self)
        win.present()

    def open_note(self, note_id):
        from betternotes.note_window import NoteWindow

        if note_id in self._note_windows:
            self._note_windows[note_id].present()
            return

        note = self.store.get_note(note_id)
        if note is None:
            return

        win = NoteWindow(application=self, note=note)
        self._note_windows[note_id] = win
        win.connect('close-request', self._on_note_window_closed, note_id)
        win.present()

    def _on_note_window_closed(self, win, note_id):
        self._note_windows.pop(note_id, None)
        return False

    def close_note_window(self, note_id):
        win = self._note_windows.pop(note_id, None)
        if win:
            win.close()

    def _get_settings(self):
        schema_source = Gio.SettingsSchemaSource.get_default()
        if schema_source and schema_source.lookup(APP_ID, True):
            return Gio.Settings.new(APP_ID)
        return None

    def _on_new_note(self, action, param):
        from betternotes.colors import DEFAULT_COLOR

        color = DEFAULT_COLOR
        settings = self._get_settings()
        if settings:
            color = settings.get_string('default-color') or DEFAULT_COLOR

        note = self.store.create_note(title='', content='', color=color)
        self.emit('note-created', note.id)
        self.open_note(note.id)

    def _on_about(self, action, param):
        about = Adw.AboutDialog(
            application_name='BetterNotes',
            application_icon=APP_ID,
            developer_name='Paperhead',
            version=self.version,
            developers=['Paperhead'],
            copyright='Copyright 2026 0xpaperhead',
            license_type=Gtk.License.GPL_3_0,
        )
        about.present(self.get_active_window())

    def _on_quit(self, action, param):
        for win in list(self._note_windows.values()):
            win.close()
        self.quit()

    def _on_preferences(self, action, param):
        from betternotes.preferences import PreferencesWindow
        win = PreferencesWindow()
        win.present(self.get_active_window())

    def _on_shortcuts(self, action, param):
        from betternotes.shortcuts import ShortcutsWindow
        win = ShortcutsWindow(transient_for=self.get_active_window())
        win.present()
