# SPDX-License-Identifier: GPL-3.0-or-later

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Adw, Gdk, Gio, GLib, GObject, Gtk
from betternotes.i18n import _

CARD_SIZE = 200
PREVIEW_MAX_CHARS = 80
PREVIEW_MAX_LINES = 5


class NoteCard(Gtk.Overlay):
    """Fixed-size square card widget for displaying a note in the grid."""

    __gsignals__ = {
        'activated': (GObject.SignalFlags.RUN_LAST, None, (str,)),
        'long-pressed': (GObject.SignalFlags.RUN_LAST, None, (str,)),
        'trash-requested': (GObject.SignalFlags.RUN_LAST, None, (str,)),
        'restore-requested': (GObject.SignalFlags.RUN_LAST, None, (str,)),
        'delete-requested': (GObject.SignalFlags.RUN_LAST, None, (str,)),
    }

    def __init__(self, note, is_trash=False, **kwargs):
        super().__init__(**kwargs)
        self._note = note
        self._is_trash = is_trash
        self._selected = False

        # Fixed square size, don't stretch, clip overflow
        self.set_size_request(CARD_SIZE, CARD_SIZE)
        self.set_overflow(Gtk.Overflow.HIDDEN)
        self.set_valign(Gtk.Align.START)
        self.set_halign(Gtk.Align.START)

        # Frame as the base child of the overlay
        frame = Gtk.Frame()
        frame.set_overflow(Gtk.Overflow.HIDDEN)
        frame.add_css_class('note-card')
        frame.add_css_class(f'note-color-{note.color}-card')
        self._frame = frame

        # Vertical layout inside the frame
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        # Scrollable content area (scrollbars hidden — just for clipping)
        inner = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=4,
            vexpand=True,
        )
        inner.add_css_class('note-card-content')

        # Title
        title = note.title or _('Untitled Note')
        title_label = Gtk.Label(
            label=title,
            xalign=0,
            ellipsize=3,  # END
            max_width_chars=22,
        )
        title_label.add_css_class('note-card-title')
        inner.append(title_label)

        inner.append(Gtk.Separator())

        # Preview text — hard-truncated in code
        preview = note.preview_text
        has_more = False
        if preview:
            lines = preview.split('\n')
            if len(lines) > PREVIEW_MAX_LINES:
                lines = lines[:PREVIEW_MAX_LINES]
                has_more = True
            truncated = '\n'.join(lines)
            if len(truncated) > PREVIEW_MAX_CHARS:
                truncated = truncated[:PREVIEW_MAX_CHARS]
                has_more = True

            preview_label = Gtk.Label(
                label=truncated,
                xalign=0,
                yalign=0,
                wrap=True,
                wrap_mode=1,  # WORD_CHAR
                max_width_chars=22,
            )
            preview_label.add_css_class('note-card-preview')
            inner.append(preview_label)

        # Tags
        if note.tags:
            spacer = Gtk.Box(vexpand=True)
            inner.append(spacer)
            tags_label = Gtk.Label(
                label=', '.join(note.tags),
                xalign=0,
                ellipsize=3,
                max_width_chars=22,
            )
            tags_label.add_css_class('note-card-tags')
            inner.append(tags_label)

        outer.append(inner)

        # "More" indicator bar when content was truncated
        if has_more:
            more_bar = Gtk.Box(hexpand=True)
            more_bar.add_css_class('note-card-more')
            more_bar.add_css_class(f'note-card-more-{note.color}')

            dots = Gtk.Label(label='\u2026', xalign=0.5)  # ellipsis char
            dots.add_css_class('note-card-more-label')
            dots.set_hexpand(True)
            more_bar.append(dots)

            outer.append(more_bar)

        frame.set_child(outer)
        self.set_child(frame)

        # Checkmark overlay (top-right corner, hidden by default)
        self._check = Gtk.Image.new_from_icon_name('object-select-symbolic')
        self._check.add_css_class('note-card-check')
        self._check.set_halign(Gtk.Align.END)
        self._check.set_valign(Gtk.Align.START)
        self._check.set_margin_top(8)
        self._check.set_margin_end(8)
        self._check.set_visible(False)
        self.add_overlay(self._check)

        # Click gesture
        click = Gtk.GestureClick()
        click.connect('released', self._on_click)
        self.add_controller(click)

        # Long-press gesture
        long_press = Gtk.GestureLongPress()
        long_press.set_delay_factor(1.0)  # default ~600ms
        long_press.connect('pressed', self._on_long_press)
        self.add_controller(long_press)

        self._setup_context_menu()

    def _on_click(self, gesture, n_press, x, y):
        if n_press == 1:
            self.emit('activated', self._note.id)

    def _on_long_press(self, gesture, x, y):
        self.emit('long-pressed', self._note.id)

    def _setup_context_menu(self):
        menu = Gio.Menu()
        if self._is_trash:
            menu.append(_('Restore'), 'card.restore')
            menu.append(_('Delete Permanently'), 'card.delete')
        else:
            menu.append(_('Open'), 'card.open')
            menu.append(_('Move to Trash'), 'card.trash')

        action_group = Gio.SimpleActionGroup()

        if self._is_trash:
            restore_action = Gio.SimpleAction.new('restore', None)
            restore_action.connect('activate', lambda *a: self.emit('restore-requested', self._note.id))
            action_group.add_action(restore_action)

            delete_action = Gio.SimpleAction.new('delete', None)
            delete_action.connect('activate', lambda *a: self.emit('delete-requested', self._note.id))
            action_group.add_action(delete_action)
        else:
            open_action = Gio.SimpleAction.new('open', None)
            open_action.connect('activate', lambda *a: self.emit('activated', self._note.id))
            action_group.add_action(open_action)

            trash_action = Gio.SimpleAction.new('trash', None)
            trash_action.connect('activate', lambda *a: self.emit('trash-requested', self._note.id))
            action_group.add_action(trash_action)

        self.insert_action_group('card', action_group)

        popover = Gtk.PopoverMenu(menu_model=menu)
        popover.set_parent(self)
        popover.set_has_arrow(False)

        right_click = Gtk.GestureClick(button=Gdk.BUTTON_SECONDARY)
        right_click.connect('released', self._on_right_click, popover)
        self.add_controller(right_click)

    def _on_right_click(self, gesture, n_press, x, y, popover):
        rect = Gdk.Rectangle()
        rect.x = int(x)
        rect.y = int(y)
        rect.width = 1
        rect.height = 1
        popover.set_pointing_to(rect)
        popover.popup()

    @property
    def note_id(self):
        return self._note.id

    @property
    def selected(self):
        return self._selected

    @selected.setter
    def selected(self, value):
        self._selected = value
        if value:
            self._frame.add_css_class('note-card-selected')
            self._check.set_visible(True)
        else:
            self._frame.remove_css_class('note-card-selected')
            self._check.set_visible(False)
