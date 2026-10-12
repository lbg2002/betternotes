# SPDX-License-Identifier: GPL-3.0-or-later

import os
from datetime import date
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Adw, Gdk, Gio, GLib, GObject, Gtk

from betternotes.constants import APP_ID
from betternotes.i18n import _
from betternotes.note_store import NoteStore
from betternotes.main_window import MainWindow
from betternotes.plan import new_item, serialize_items
from betternotes.font_settings import make_font_css


class BetterNotesApp(Adw.Application):

    __gsignals__ = {
        'note-changed': (GObject.SignalFlags.RUN_LAST, None, (str,)),
        'note-created': (GObject.SignalFlags.RUN_LAST, None, (str,)),
        'note-trashed': (GObject.SignalFlags.RUN_LAST, None, (str,)),
        'note-restored': (GObject.SignalFlags.RUN_LAST, None, (str,)),
        'note-deleted': (GObject.SignalFlags.RUN_LAST, None, (str,)),
    }

    def __init__(self, version='0.4.3', **kwargs):
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
            **kwargs,
        )
        self.version = version
        self.store = None
        self._note_windows = {}
        self._reminded_this_session = set()

    def do_startup(self):
        Adw.Application.do_startup(self)
        self.store = NoteStore()
        self._load_css()
        self._setup_live_fonts()
        self._setup_actions()
        self._setup_shortcuts()
        # Lightweight reminder checks only while the application is running.
        GLib.timeout_add_seconds(10, self._check_due_tasks, False)
        GLib.timeout_add_seconds(900, self._check_due_tasks, True)

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

    def _setup_live_fonts(self):
        """One provider per app: updating it restyles *existing* note windows."""
        self._font_provider = Gtk.CssProvider()
        display = Gdk.Display.get_default()
        if display is not None:
            Gtk.StyleContext.add_provider_for_display(
                display, self._font_provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1,
            )
        self._font_settings = self._get_settings()
        if self._font_settings:
            self._font_settings.connect('changed::font-family', self._font_setting_changed)
            self._font_settings.connect('changed::font-size', self._font_setting_changed)
        self._apply_font_settings()

    def _font_setting_changed(self, settings, key):
        self._apply_font_settings()

    def _apply_font_settings(self):
        settings = getattr(self, '_font_settings', None)
        family = settings.get_string('font-family') if settings else ''
        size = settings.get_int('font-size') if settings else 14
        self._font_provider.load_from_data(make_font_css(family, size).encode('utf-8'))

    def _setup_actions(self):
        actions = [
            ('new-note', self._on_new_note, None),
            ('new-plan', self._on_new_plan, None),
            ('new-plan-daily', self._on_new_plan_daily, None),
            ('new-plan-weekly', self._on_new_plan_weekly, None),
            ('new-plan-study', self._on_new_plan_study, None),
            ('export-backup', self._on_export_backup, None),
            ('import-backup', self._on_import_backup, None),
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
        self.set_accels_for_action('app.new-plan', ['<Control><Shift>n'])
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
        self._create_note('note')

    def _on_new_plan(self, action, param):
        self._create_note('plan')

    def _on_new_plan_daily(self, action, param):
        self._create_note('plan', 'daily')

    def _on_new_plan_weekly(self, action, param):
        self._create_note('plan', 'weekly')

    def _on_new_plan_study(self, action, param):
        self._create_note('plan', 'study')

    def _create_note(self, kind, template=None):
        from betternotes.colors import DEFAULT_COLOR

        color = DEFAULT_COLOR
        settings = self._get_settings()
        if settings:
            color = settings.get_string('default-color') or DEFAULT_COLOR

        templates = {
            'daily': (_('Daily plan'), [_('Most important task'), _('Focus work'), _('Daily review')]),
            'weekly': (_('Weekly plan'), [_('Monday goals'), _('Midweek review'), _('Weekly summary')]),
            'study': (_('Study plan'), [_('Read material'), _('Practice'), _('Review notes')]),
        }
        title, items = templates.get(
            template, (_('New plan') if kind == 'plan' else '', [])
        )
        content = serialize_items([new_item(text) for text in items]) if template else ''
        note = self.store.create_note(title=title, content=content, color=color,
                                      kind=kind)
        self.emit('note-created', note.id)
        self.open_note(note.id)

    def _on_export_backup(self, action, param):
        import json
        from betternotes.backup import make_archive
        dialog = Gtk.FileDialog(title=_('Export backup'), initial_name='pinplan-backup.json')
        dialog.save(self.get_active_window(), None, self._backup_save_done)

    def _backup_save_done(self, dialog, result):
        import json
        from betternotes.backup import make_archive
        try:
            chosen = dialog.save_finish(result)
            if not chosen or not chosen.get_path():
                return
            for win in list(self._note_windows.values()):
                if hasattr(win, '_auto_save'):
                    win._auto_save.save_now()
            archive = make_archive(self.store)
            with open(chosen.get_path(), 'w', encoding='utf-8') as file:
                json.dump(archive, file, ensure_ascii=False, indent=2)
            self._backup_notice(_('Backup exported'))
        except GLib.Error:
            return  # User cancelled the file dialog.
        except (OSError, ValueError) as exc:
            self._backup_notice(_('Backup failed: ') + str(exc))

    def _on_import_backup(self, action, param):
        dialog = Gtk.FileDialog(title=_('Import backup'))
        dialog.open(self.get_active_window(), None, self._backup_open_done)

    def _backup_open_done(self, dialog, result):
        import json
        from betternotes.backup import restore_archive
        try:
            chosen = dialog.open_finish(result)
            if not chosen or not chosen.get_path():
                return
            # Flush in-flight edits before restoring additional records.
            for win in list(self._note_windows.values()):
                if hasattr(win, '_auto_save'):
                    win._auto_save.save_now()
            if os.path.getsize(chosen.get_path()) > 20 * 1024 * 1024:
                raise ValueError(_('Backup file is too large'))
            with open(chosen.get_path(), encoding='utf-8') as file:
                archive = json.load(file)
            restored = restore_archive(self.store, archive)
            self.emit('note-created', '')
            self._backup_notice(_('Imported {count} notes').format(count=restored))
        except GLib.Error:
            return
        except (OSError, ValueError, KeyError, TypeError) as exc:
            self._backup_notice(_('Import failed: ') + str(exc))

    def _backup_notice(self, message):
        win = next((win for win in self.get_windows() if isinstance(win, MainWindow)), None)
        if win:
            win._show_toast(message)

    def _check_due_tasks(self, repeat=True):
        from betternotes.plan import parse_items
        today = date.today().isoformat()
        if not self.store:
            return GLib.SOURCE_REMOVE
        for note in self.store.get_all_notes():
            if note.kind != 'plan':
                continue
            for item in parse_items(note.content):
                due = item.get('due', '')
                if item['done'] or not due or due > today:
                    continue
                key = (note.id, item['id'], due)
                if key in self._reminded_this_session:
                    continue
                self._reminded_this_session.add(key)
                notification = Gio.Notification.new(_('Plan due'))
                notification.set_body(
                    (note.title or _('Untitled Note')) + ' · ' + item['text']
                )
                self.send_notification('pinplan-' + note.id + '-' + item['id'],
                                       notification)
        return GLib.SOURCE_CONTINUE if repeat else GLib.SOURCE_REMOVE

    def _on_about(self, action, param):
        about = Adw.AboutDialog(
            application_name='PinPlan · 轻笺',
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
