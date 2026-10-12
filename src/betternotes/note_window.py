# SPDX-License-Identifier: GPL-3.0-or-later

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Adw, Gdk, Gio, GLib, GObject, Gtk, Pango

from betternotes.auto_save import AutoSave
from betternotes.colors import COLOR_NAMES
from betternotes.constants import APP_ID
from betternotes.i18n import _
from betternotes.rich_text_serializer import (
    TAG_NAMES,
    deserialize_to_buffer,
    serialize_buffer,
    _ensure_tags,
)
from betternotes.rich_text_toolbar import RichTextToolbar
from betternotes.plan import new_item, parse_items, serialize_items


class NoteWindow(Adw.Window):

    def __init__(self, application, note, **kwargs):
        super().__init__(
            application=application,
            **kwargs,
        )
        self._app = application
        self._note = note
        self._updating_toolbar = False

        self.set_default_size(440 if note.kind == 'plan' else 400, 500)
        self.set_title(note.title or _('Untitled Note'))

        self._build_ui()
        self._load_note()
        self._apply_color(note.color)

        self._auto_save = AutoSave(self._save_note)

        self._setup_actions()
        self._setup_key_controller()

        # Keep note windows always on top via _NET_WM_STATE_ABOVE.
        self.connect('map', self._on_map_keep_above)

    # Standalone Python script that opens its own X connection and sends
    # the proper EWMH ClientMessage to request always-on-top from the WM.
    _KEEP_ABOVE_SCRIPT = '''
import ctypes, ctypes.util, struct, sys, os
xid = int(sys.argv[1])
xlib = ctypes.cdll.LoadLibrary(ctypes.util.find_library("X11"))
xlib.XOpenDisplay.restype = ctypes.c_void_p
xlib.XOpenDisplay.argtypes = [ctypes.c_char_p]
dpy = xlib.XOpenDisplay(os.environ.get("DISPLAY","").encode() or None)
if not dpy:
    sys.exit(1)
xlib.XInternAtom.restype = ctypes.c_ulong
xlib.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
xlib.XDefaultRootWindow.restype = ctypes.c_ulong
xlib.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
wm_state = xlib.XInternAtom(dpy, b"_NET_WM_STATE", False)
wm_above = xlib.XInternAtom(dpy, b"_NET_WM_STATE_ABOVE", False)
root = xlib.XDefaultRootWindow(dpy)
# XClientMessageEvent: use ctypes Structure for correct layout
class XClientMessageEvent(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_int),
        ("serial", ctypes.c_ulong),
        ("send_event", ctypes.c_int),
        ("display", ctypes.c_void_p),
        ("window", ctypes.c_ulong),
        ("message_type", ctypes.c_ulong),
        ("format", ctypes.c_int),
        ("data", ctypes.c_long * 5),
    ]
class XEvent(ctypes.Union):
    _fields_ = [
        ("xclient", XClientMessageEvent),
        ("pad", ctypes.c_char * 192),
    ]
ev = XEvent()
ev.xclient.type = 33  # ClientMessage
ev.xclient.serial = 0
ev.xclient.send_event = 1
ev.xclient.display = dpy
ev.xclient.window = xid
ev.xclient.message_type = wm_state
ev.xclient.format = 32
ev.xclient.data[0] = 1  # _NET_WM_STATE_ADD
ev.xclient.data[1] = wm_above
ev.xclient.data[2] = 0
ev.xclient.data[3] = 1  # source: application
ev.xclient.data[4] = 0
mask = (1 << 20) | (1 << 19)  # SubstructureRedirect | SubstructureNotify
xlib.XSendEvent.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_long, ctypes.POINTER(XEvent)]
xlib.XSendEvent.restype = ctypes.c_int
xlib.XSendEvent(dpy, root, False, mask, ctypes.byref(ev))
xlib.XFlush.argtypes = [ctypes.c_void_p]
xlib.XFlush(dpy)
xlib.XCloseDisplay.argtypes = [ctypes.c_void_p]
xlib.XCloseDisplay(dpy)
'''

    def _on_map_keep_above(self, widget):
        GLib.timeout_add(250, self._apply_always_on_top)

    def _apply_always_on_top(self):
        import subprocess

        surface = self.get_surface()
        if surface is None:
            return GLib.SOURCE_REMOVE

        try:
            gi.require_version('GdkX11', '4.0')
            from gi.repository import GdkX11
            if not isinstance(surface, GdkX11.X11Surface):
                return GLib.SOURCE_REMOVE
            xid = surface.get_xid()
        except (ValueError, ImportError):
            return GLib.SOURCE_REMOVE

        subprocess.Popen(
            ['python3', '-c', self._KEEP_ABOVE_SCRIPT, str(xid)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        return GLib.SOURCE_REMOVE

    def _build_ui(self):
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        # Header bar
        self._header = Adw.HeaderBar()
        self._header.add_css_class('flat')

        # Color picker menu
        color_btn = Gtk.MenuButton(
            icon_name='preferences-color-symbolic',
            tooltip_text=_('Change Color'),
        )
        color_popover = self._build_color_popover()
        color_btn.set_popover(color_popover)
        self._header.pack_start(color_btn)

        # Trash button
        trash_btn = Gtk.Button(
            icon_name='user-trash-symbolic',
            tooltip_text=_('Move to Trash'),
        )
        trash_btn.connect('clicked', self._on_trash)
        self._header.pack_end(trash_btn)

        # Tags button
        tags_btn = Gtk.Button(
            icon_name='tag-symbolic',
            tooltip_text=_('Manage Tags'),
        )
        tags_btn.connect('clicked', self._on_manage_tags)
        self._header.pack_end(tags_btn)

        if self._note.kind == 'note':
            format_btn = Gtk.Button(icon_name='format-text-bold-symbolic',
                                    tooltip_text=_('Show formatting toolbar'))
            format_btn.connect('clicked', self._toggle_format_toolbar)
            self._header.pack_end(format_btn)

        main_box.append(self._header)

        # Title entry
        self._title_entry = Gtk.Entry(
            placeholder_text=_('Note title...'),
        )
        self._title_entry.add_css_class('note-title-entry')
        self._title_entry.connect('changed', self._on_content_changed)
        main_box.append(self._title_entry)

        if self._note.kind == 'plan':
            self._build_plan_ui(main_box)
        else:
            # Rich text editing is unchanged for old notes.
            self._toolbar = RichTextToolbar()
            self._toolbar.connect('format-toggled', self._on_format_toggled)
            self._toolbar_sep = Gtk.Separator()
            self._toolbar.set_visible(self._format_visible())
            self._toolbar_sep.set_visible(self._format_visible())
            main_box.append(self._toolbar)
            main_box.append(self._toolbar_sep)

            scrolled = Gtk.ScrolledWindow(vexpand=True, hexpand=True)
            self._text_view = Gtk.TextView(
                wrap_mode=Gtk.WrapMode.WORD_CHAR,
                left_margin=12, right_margin=12,
                top_margin=8, bottom_margin=8,
            )
            self._text_view.add_css_class('note-text-view')
            self._buffer = self._text_view.get_buffer()
            _ensure_tags(self._buffer)
            self._buffer.connect('changed', self._on_content_changed)
            self._buffer.connect('mark-set', self._on_cursor_moved)
            scrolled.set_child(self._text_view)
            main_box.append(scrolled)

        # Tags display bar
        self._tags_bar = Gtk.FlowBox(
            selection_mode=Gtk.SelectionMode.NONE,
            max_children_per_line=10,
            min_children_per_line=1,
        )
        self._tags_bar.set_visible(False)
        main_box.append(self._tags_bar)

        self.set_content(main_box)

    def _build_plan_ui(self, parent):
        self._plan_items = []
        self._plan_widgets = {}
        self._plan_progress = Gtk.Label(xalign=0)
        self._plan_progress.add_css_class('plan-progress')
        parent.append(self._plan_progress)

        scroll = Gtk.ScrolledWindow(vexpand=True, hexpand=True)
        self._plan_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        self._plan_box.add_css_class('plan-items')
        scroll.set_child(self._plan_box)
        parent.append(scroll)

        add_btn = Gtk.Button(label=_('Add task'))
        add_btn.add_css_class('suggested-action')
        add_btn.add_css_class('plan-add')
        add_btn.connect('clicked', self._plan_add)
        parent.append(add_btn)

    def _plan_find(self, uid):
        return next((item for item in self._plan_items if item['id'] == uid), None)

    def _plan_markup(self, item):
        escaped = GLib.markup_escape_text(item['text'] or _('New task'))
        return '<s>' + escaped + '</s>' if item['done'] else escaped

    def _plan_progress_update(self):
        done = sum(bool(item['done']) for item in self._plan_items)
        total = len(self._plan_items)
        self._plan_progress.set_label(
            _('Completed {done}/{total}').format(done=done, total=total)
        )

    def _plan_refresh(self):
        child = self._plan_box.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self._plan_box.remove(child)
            child = nxt
        self._plan_widgets = {}

        for pos, item in enumerate(self._plan_items):
            uid = item['id']
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
            row.add_css_class('plan-item')

            check = Gtk.CheckButton()
            check.set_active(item['done'])
            check.set_tooltip_text(_('Toggle completed'))
            check.connect('toggled', self._plan_toggle, uid)
            row.append(check)

            label = Gtk.Label(xalign=0, hexpand=True, wrap=True)
            label.set_markup(self._plan_markup(item))
            label.add_css_class('plan-label')
            row.append(label)

            entry = Gtk.Entry(text=item['text'], hexpand=True)
            entry.set_placeholder_text(_('New task'))
            entry.set_visible(False)
            entry.connect('changed', self._plan_text_changed, uid, label)
            entry.connect('activate', self._plan_finish_edit, uid)
            row.append(entry)
            self._plan_widgets[uid] = (label, entry)

            edit = Gtk.Button(icon_name='document-edit-symbolic')
            edit.set_tooltip_text(_('Edit task'))
            edit.connect('clicked', self._plan_start_edit, uid)
            row.append(edit)

            up = Gtk.Button(icon_name='go-up-symbolic')
            up.set_tooltip_text(_('Move up'))
            up.set_sensitive(pos > 0)
            up.connect('clicked', self._plan_move, uid, -1)
            row.append(up)

            down = Gtk.Button(icon_name='go-down-symbolic')
            down.set_tooltip_text(_('Move down'))
            down.set_sensitive(pos + 1 < len(self._plan_items))
            down.connect('clicked', self._plan_move, uid, 1)
            row.append(down)

            delete = Gtk.Button(icon_name='edit-delete-symbolic')
            delete.set_tooltip_text(_('Delete task'))
            delete.connect('clicked', self._plan_delete, uid)
            row.append(delete)
            self._plan_box.append(row)
        self._plan_progress_update()

    def _plan_toggle(self, check, uid):
        item = self._plan_find(uid)
        if item is None:
            return
        item['done'] = check.get_active()
        widgets = self._plan_widgets.get(uid)
        if widgets:
            widgets[0].set_markup(self._plan_markup(item))
        self._plan_progress_update()
        self._on_content_changed()

    def _plan_text_changed(self, entry, uid, label):
        item = self._plan_find(uid)
        if item is not None:
            item['text'] = entry.get_text()
            label.set_markup(self._plan_markup(item))
            self._on_content_changed()

    def _plan_start_edit(self, button, uid):
        widgets = self._plan_widgets.get(uid)
        if widgets:
            label, entry = widgets
            label.set_visible(False)
            entry.set_visible(True)
            entry.grab_focus()
            entry.select_region(0, -1)

    def _plan_finish_edit(self, entry, uid):
        widgets = self._plan_widgets.get(uid)
        if widgets:
            label, field = widgets
            field.set_visible(False)
            label.set_visible(True)

    def _plan_add(self, button):
        item = new_item()
        self._plan_items.append(item)
        self._plan_refresh()
        self._on_content_changed()
        self._plan_start_edit(None, item['id'])

    def _plan_delete(self, button, uid):
        self._plan_items = [item for item in self._plan_items if item['id'] != uid]
        self._plan_refresh()
        self._on_content_changed()

    def _plan_move(self, button, uid, direction):
        index = next((i for i, item in enumerate(self._plan_items)
                      if item['id'] == uid), -1)
        target = index + direction
        if index < 0 or not (0 <= target < len(self._plan_items)):
            return
        self._plan_items[index], self._plan_items[target] = (
            self._plan_items[target], self._plan_items[index]
        )
        self._plan_refresh()
        self._on_content_changed()

    def _format_visible(self):
        settings = self._app._get_settings()
        return settings.get_boolean('show-format-toolbar') if settings else False

    def _toggle_format_toolbar(self, button):
        visible = not self._toolbar.get_visible()
        self._toolbar.set_visible(visible)
        self._toolbar_sep.set_visible(visible)
        settings = self._app._get_settings()
        if settings:
            settings.set_boolean('show-format-toolbar', visible)

    def _build_color_popover(self):
        popover = Gtk.Popover()
        grid = Gtk.FlowBox(
            max_children_per_line=4,
            selection_mode=Gtk.SelectionMode.NONE,
            homogeneous=True,
        )
        grid.set_size_request(160, -1)

        for color_name in COLOR_NAMES:
            btn = Gtk.Button()
            btn.set_size_request(32, 32)
            btn.add_css_class('color-button')
            btn.add_css_class(f'color-{color_name}')
            btn.set_tooltip_text(color_name.capitalize())
            btn.connect('clicked', self._on_color_selected, color_name, popover)
            grid.append(btn)

        popover.set_child(grid)
        return popover

    def _load_note(self):
        self._title_entry.set_text(self._note.title or '')
        if self._note.kind == 'plan':
            self._plan_items = parse_items(self._note.content)
            self._plan_refresh()
        elif self._note.content:
            deserialize_to_buffer(self._buffer, self._note.content)
        self._update_tags_bar()

    def _apply_color(self, color_name):
        # Remove old color classes
        for c in COLOR_NAMES:
            self.remove_css_class(f'note-color-{c}')
        self.add_css_class(f'note-color-{color_name}')
        self._note.color = color_name

    def _on_color_selected(self, btn, color_name, popover):
        popover.popdown()
        self._apply_color(color_name)
        self._app.store.update_note(self._note.id, color=color_name)
        self._app.emit('note-changed', self._note.id)

    def _on_content_changed(self, *args):
        if hasattr(self, '_auto_save'):
            self._auto_save.trigger()

    def _save_note(self):
        title = self._title_entry.get_text()
        content = (serialize_items(self._plan_items) if self._note.kind == 'plan'
                   else serialize_buffer(self._buffer))
        self.set_title(title or _('Untitled Note'))
        self._note.title = title
        self._note.content = content
        self._app.store.update_note(
            self._note.id, title=title, content=content,
        )
        self._app.emit('note-changed', self._note.id)

    def _on_cursor_moved(self, buffer, iter_, mark):
        if mark.get_name() == 'insert':
            self._update_toolbar_state()

    def _update_toolbar_state(self):
        insert = self._buffer.get_iter_at_mark(self._buffer.get_insert())
        active = set()
        for tag in insert.get_tags():
            name = tag.get_property('name')
            if name in TAG_NAMES or name == 'bullet':
                active.add(name)
        self._toolbar.update_state(active)

    def _on_format_toggled(self, toolbar, format_name, is_active):
        if format_name == 'bullet':
            self._toggle_bullet()
            return

        bounds = self._buffer.get_selection_bounds()
        if not bounds:
            return

        start, end = bounds
        tag = self._buffer.get_tag_table().lookup(format_name)
        if tag is None:
            return

        if is_active:
            self._buffer.apply_tag(tag, start, end)
        else:
            self._buffer.remove_tag(tag, start, end)

        self._on_content_changed()

    def _toggle_bullet(self):
        insert = self._buffer.get_iter_at_mark(self._buffer.get_insert())
        line_num = insert.get_line()

        bullet_tag = self._buffer.get_tag_table().lookup('bullet')
        if bullet_tag is None:
            return

        # Get line bounds by line number (safe across modifications)
        _, line_start = self._buffer.get_iter_at_line(line_num)
        _, line_end = self._buffer.get_iter_at_line(line_num)
        if not line_end.ends_line():
            line_end.forward_to_line_end()

        if line_start.has_tag(bullet_tag):
            self._buffer.remove_tag(bullet_tag, line_start, line_end)
            text = self._buffer.get_text(line_start, line_end, True)
            if text.startswith('\u2022 '):
                _, prefix_end = self._buffer.get_iter_at_line(line_num)
                prefix_end.forward_chars(2)
                _, delete_start = self._buffer.get_iter_at_line(line_num)
                self._buffer.delete(delete_start, prefix_end)
        else:
            # Insert bullet prefix first
            _, line_start = self._buffer.get_iter_at_line(line_num)
            self._buffer.insert(line_start, '\u2022 ')
            # Re-fetch iterators after modification
            _, line_start = self._buffer.get_iter_at_line(line_num)
            _, line_end = self._buffer.get_iter_at_line(line_num)
            if not line_end.ends_line():
                line_end.forward_to_line_end()
            self._buffer.apply_tag(bullet_tag, line_start, line_end)

        self._on_content_changed()

    def _on_trash(self, btn):
        self._auto_save.save_now()
        self._app.store.trash_note(self._note.id)
        self._app.emit('note-trashed', self._note.id)
        self.close()

    def _on_manage_tags(self, btn):
        dialog = Adw.AlertDialog(
            heading=_('Manage Tags'),
            body=_('Enter tags separated by commas:'),
        )
        dialog.add_response('cancel', _('Cancel'))
        dialog.add_response('save', 'Save')
        dialog.set_response_appearance('save', Adw.ResponseAppearance.SUGGESTED)

        entry = Gtk.Entry(
            text=', '.join(self._note.tags),
            hexpand=True,
        )
        dialog.set_extra_child(entry)
        dialog.connect('response', self._on_tags_response, entry)
        dialog.present(self)

    def _on_tags_response(self, dialog, response, entry):
        if response != 'save':
            return

        new_tags = {t.strip() for t in entry.get_text().split(',') if t.strip()}
        old_tags = set(self._note.tags)

        for tag in old_tags - new_tags:
            self._app.store.remove_tag_from_note(self._note.id, tag)
        for tag in new_tags - old_tags:
            self._app.store.add_tag_to_note(self._note.id, tag)

        self._note.tags = sorted(new_tags)
        self._update_tags_bar()
        self._app.emit('note-changed', self._note.id)

    def _update_tags_bar(self):
        # Clear existing
        child = self._tags_bar.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            self._tags_bar.remove(child)
            child = next_child

        if not self._note.tags:
            self._tags_bar.set_visible(False)
            return

        self._tags_bar.set_visible(True)
        for tag_name in self._note.tags:
            label = Gtk.Label(label=tag_name)
            label.add_css_class('tag-chip')
            self._tags_bar.append(label)

    def _setup_actions(self):
        if self._note.kind == 'plan':
            return
        action_group = Gio.SimpleActionGroup()
        actions = [
            ('bold', self._action_format, 'bold'),
            ('italic', self._action_format, 'italic'),
            ('underline', self._action_format, 'underline'),
            ('strikethrough', self._action_format, 'strikethrough'),
        ]
        for name, callback, fmt in actions:
            action = Gio.SimpleAction.new(name, None)
            action.connect('activate', callback, fmt)
            action_group.add_action(action)

        self.insert_action_group('win', action_group)

        self._app.set_accels_for_action('win.bold', ['<Control>b'])
        self._app.set_accels_for_action('win.italic', ['<Control>i'])
        self._app.set_accels_for_action('win.underline', ['<Control>u'])
        self._app.set_accels_for_action('win.strikethrough', ['<Control>d'])

    def _action_format(self, action, param, format_name):
        bounds = self._buffer.get_selection_bounds()
        if not bounds:
            return

        start, end = bounds
        tag = self._buffer.get_tag_table().lookup(format_name)
        if tag is None:
            return

        if start.has_tag(tag):
            self._buffer.remove_tag(tag, start, end)
        else:
            self._buffer.apply_tag(tag, start, end)
        self._update_toolbar_state()
        self._on_content_changed()

    def _setup_key_controller(self):
        if self._note.kind == 'plan':
            return
        key_controller = Gtk.EventControllerKey()
        key_controller.connect('key-pressed', self._on_key_pressed)
        self._text_view.add_controller(key_controller)

    def _on_key_pressed(self, controller, keyval, keycode, state):
        if keyval == Gdk.KEY_Return or keyval == Gdk.KEY_KP_Enter:
            # Auto-continue bullet list
            insert = self._buffer.get_iter_at_mark(self._buffer.get_insert())
            line_start = insert.copy()
            line_start.set_line_offset(0)
            bullet_tag = self._buffer.get_tag_table().lookup('bullet')
            if bullet_tag and line_start.has_tag(bullet_tag):
                # Check if current line is empty bullet
                line_end = insert.copy()
                if not line_end.ends_line():
                    line_end.forward_to_line_end()
                text = self._buffer.get_text(line_start, line_end, True)
                if text.strip() == '\u2022':
                    # Empty bullet — remove it and stop list
                    self._buffer.delete(line_start, line_end)
                    self._buffer.remove_tag(bullet_tag, line_start, line_end)
                    return Gdk.EVENT_STOP

                # Insert new bullet on next line
                self._buffer.insert_at_cursor('\n\u2022 ')
                # Apply bullet tag to new line
                new_insert = self._buffer.get_iter_at_mark(
                    self._buffer.get_insert()
                )
                new_line_start = new_insert.copy()
                new_line_start.set_line_offset(0)
                self._buffer.apply_tag(bullet_tag, new_line_start, new_insert)
                return Gdk.EVENT_STOP

        return Gdk.EVENT_PROPAGATE

    def do_close_request(self):
        if hasattr(self, '_auto_save'):
            self._auto_save.save_now()
        return False
