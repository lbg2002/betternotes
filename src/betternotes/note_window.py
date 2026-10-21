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
from betternotes.markdown_preview import render_markdown
from betternotes.plan import new_item, parse_items, serialize_items



class CompactNoteWindow(Gtk.Window):
    """Small, independent always-on-top handle for a hidden note editor.

    The editor stays alive (and retains its size, scroll position and text).
    Keeping the handle in a separate undecorated toplevel avoids trying to
    resize a mapped Adw.Window below its minimum headerbar dimensions.
    """

    def __init__(self, original, shape):
        super().__init__(application=original._app, decorated=False, resizable=False)
        self._original = original
        self._shape = shape if shape in ('ball', 'pill') else 'ball'
        self._drag_started = False
        self._drag_moving = False
        self.add_css_class('pinplan-compact-window')
        self.set_title(original._note.title or _('Untitled Note'))
        self.set_default_size(58 if self._shape == 'ball' else 188,
                              58 if self._shape == 'ball' else 46)

        button = Gtk.Button()
        button.add_css_class('pinplan-compact-handle')
        button.add_css_class('pinplan-compact-' + self._shape)
        button.add_css_class('pinplan-mini-' + original._note.color)
        button.set_tooltip_text(_('Click to expand · right-click for main window'))
        if self._shape == 'ball':
            button.set_child(Gtk.Image.new_from_icon_name(
                'view-list-symbolic' if original._note.kind == 'plan'
                else 'document-edit-symbolic'))
        else:
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            box.set_halign(Gtk.Align.CENTER)
            box.append(Gtk.Image.new_from_icon_name(
                'view-list-symbolic' if original._note.kind == 'plan'
                else 'document-edit-symbolic'))
            title = Gtk.Label(label=original._note.title or _('Untitled Note'),
                              ellipsize=Pango.EllipsizeMode.END, max_width_chars=14)
            box.append(title)
            button.set_child(box)
        self.set_child(button)
        button.connect('clicked', self._on_clicked)
        drag = Gtk.GestureDrag()
        drag.connect('drag-begin', self._on_drag_begin)
        drag.connect('drag-update', self._on_drag_update)
        button.add_controller(drag)
        # Even when minimized to a circle, the dashboard remains reachable.
        secondary = Gtk.GestureClick()
        secondary.set_button(Gdk.BUTTON_SECONDARY)
        secondary.connect('pressed', self._on_compact_secondary_click)
        button.add_controller(secondary)

    def _on_compact_secondary_click(self, gesture, n_press, x, y):
        self._original._app.show_main_window()

    def _on_drag_begin(self, gesture, start_x, start_y):
        self._drag_started = False
        self._drag_moving = False

    def _on_drag_update(self, gesture, dx, dy):
        if self._drag_started or abs(dx) + abs(dy) < 7:
            return
        self._drag_started = True
        surface = self.get_surface()
        if surface is None or not isinstance(surface, Gdk.Toplevel):
            return
        ok, x, y = gesture.get_start_point()
        if not ok:
            return
        event = gesture.get_current_event()
        when = event.get_time() if event else Gdk.CURRENT_TIME
        # Native compositor/WM move, rather than manually changing coordinates.
        # GDK expects surface-local press coordinates.
        surface.begin_move(gesture.get_device(), Gdk.BUTTON_PRIMARY, x, y, when)
        self._drag_moving = True

    def _on_clicked(self, button):
        if self._drag_started:
            self._drag_started = False
            return
        if self._original:
            self._original._restore_from_compact()


class NoteWindow(Adw.Window):

    def __init__(self, application, note, **kwargs):
        super().__init__(
            application=application,
            **kwargs,
        )
        self._app = application
        self._note = note
        self._updating_toolbar = False
        self._compact_window = None
        self._compact_closing = False

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
        return self._keep_window_above(self)

    def _keep_window_above(self, window):
        import subprocess

        surface = window.get_surface()
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


    def _collapse_to_compact(self, button=None):
        """Instantly replace the editor with a small draggable window.

        Window placement belongs entirely to the desktop compositor. Avoid
        X11 root geometry, retry timers, opacity staging and delayed mapping:
        all of those introduced visible jumps and long input latency under
        GNOME Mutter.
        """
        if self._compact_window is not None:
            return
        if hasattr(self, '_auto_save'):
            self._auto_save.save_now()
        settings = self._app._get_settings()
        shape = settings.get_string('compact-shape') if settings else 'ball'
        compact = CompactNoteWindow(self, shape)
        self._compact_closing = False
        self._compact_window = compact
        compact.connect('map', self._on_compact_mapped)
        compact.connect('close-request', self._on_compact_close_requested)
        self.set_visible(False)
        compact.present()

    def _on_compact_mapped(self, window):
        # Only the _NET_WM_STATE_ABOVE hint is asynchronous; visibility and
        # user interaction do not wait for this window-manager operation.
        GLib.timeout_add(250, self._keep_window_above, window)

    def _on_compact_close_requested(self, compact):
        if not self._compact_closing and self._compact_window is compact:
            # Handle a compositor close without leaving a hidden note behind.
            self._compact_window = None
            self.present()
        return False

    def _restore_from_compact(self):
        """Reveal the original editor immediately; let Mutter place it."""
        compact = self._compact_window
        if compact is None:
            return
        self._compact_window = None
        self._compact_closing = True
        try:
            compact.close()
        finally:
            self._compact_closing = False
        # No position corrections after this call. With normal GNOME window
        # placement settings, the editor can appear at screen center.
        self.present()

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

        collapse = Gtk.Button(icon_name='go-down-symbolic',
                              tooltip_text=_('Collapse to floating handle'))
        collapse.add_css_class('flat')
        collapse.connect('clicked', self._collapse_to_compact)
        # Adjacent to the color picker for both ordinary notes and plans.
        self._header.pack_start(collapse)

        # Accessible even when the dashboard was closed, in both note types.
        home_btn = Gtk.Button(icon_name='go-home-symbolic',
                              tooltip_text=_('Open main window'))
        home_btn.add_css_class('flat')
        home_btn.connect('clicked', self._open_main_window)
        self._header.pack_start(home_btn)

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
            self._markdown_preview_button = Gtk.ToggleButton(
                icon_name='view-reveal-symbolic',
                tooltip_text=_('Preview Markdown'),
            )
            self._markdown_preview_button.add_css_class('flat')
            self._markdown_preview_button.connect('toggled',
                                                  self._toggle_markdown_preview)
            self._header.pack_end(self._markdown_preview_button)
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
            self._note_editor_scroll = scrolled

            # Markdown is strictly a preview; editing and auto-save continue
            # to use the existing rich-text buffer and JSON storage unchanged.
            # Both views live in one Stack, without loading a web engine.
            preview_scroll = Gtk.ScrolledWindow(vexpand=True, hexpand=True)
            preview = Gtk.TextView(
                editable=False, cursor_visible=False,
                wrap_mode=Gtk.WrapMode.WORD_CHAR,
                left_margin=12, right_margin=12,
                top_margin=8, bottom_margin=8,
            )
            preview.add_css_class('note-text-view')
            preview.add_css_class('markdown-preview')
            preview.set_focusable(False)
            self._markdown_view = preview
            preview_scroll.set_child(preview)
            self._markdown_stack = Gtk.Stack(vexpand=True, hexpand=True)
            self._markdown_stack.add_named(scrolled, 'source')
            self._markdown_stack.add_named(preview_scroll, 'preview')
            self._markdown_stack.set_visible_child_name('source')
            main_box.append(self._markdown_stack)

        # Tags display bar
        self._tags_bar = Gtk.FlowBox(
            selection_mode=Gtk.SelectionMode.NONE,
            max_children_per_line=10,
            min_children_per_line=1,
        )
        self._tags_bar.set_visible(False)
        main_box.append(self._tags_bar)

        self.set_content(main_box)


    def _open_main_window(self, button=None):
        self._app.show_main_window()

    def _toggle_markdown_preview(self, button):
        if self._note.kind != 'note':
            return
        enabled = button.get_active()
        if enabled:
            source = self._buffer.get_text(
                self._buffer.get_start_iter(),
                self._buffer.get_end_iter(), True,
            )
            render_markdown(self._markdown_view.get_buffer(), source)
            self._markdown_stack.set_visible_child_name('preview')
        else:
            self._markdown_stack.set_visible_child_name('source')
            self._text_view.grab_focus()
        # Markdown preview remains read-only; rich-text formatting controls
        # are hidden while previewing and not modified in persistent settings.
        self._toolbar.set_visible(not enabled and self._format_visible())
        self._toolbar_sep.set_visible(not enabled and self._format_visible())
        button.set_icon_name('document-edit-symbolic' if enabled
                             else 'view-reveal-symbolic')
        button.set_tooltip_text(_('Edit Markdown') if enabled
                                else _('Preview Markdown'))

    def _build_plan_ui(self, parent):
        self._plan_items = []
        self._plan_widgets = {}
        self._plan_undo_stack = []
        self._plan_refresh_busy = False
        self._plan_editing_uid = None
        self._plan_pending_uid = None

        footer_summary = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        footer_summary.add_css_class('plan-footer-summary')
        self._plan_progress = Gtk.Label(xalign=0, hexpand=True)
        footer_summary.append(self._plan_progress)

        self._plan_undo_button = Gtk.Button(icon_name='edit-undo-symbolic')
        self._plan_undo_button.add_css_class('flat')
        self._plan_undo_button.add_css_class('plan-undo-button')
        self._plan_undo_button.set_tooltip_text(_('Undo deleted task'))
        self._plan_undo_button.set_visible(False)
        self._plan_undo_button.connect('clicked', self._plan_undo)
        footer_summary.append(self._plan_undo_button)

        self._plan_fold = Gtk.ToggleButton(icon_name='view-conceal-symbolic')
        self._plan_fold.add_css_class('flat')
        self._plan_fold.add_css_class('plan-fold')
        settings = self._app._get_settings()
        self._plan_fold.set_active(
            settings.get_boolean('hide-completed') if settings else False
        )
        self._plan_fold.set_icon_name(
            'view-reveal-symbolic' if self._plan_fold.get_active()
            else 'view-conceal-symbolic'
        )
        self._plan_fold.set_tooltip_text(
            _('Show completed') if self._plan_fold.get_active()
            else _('Hide completed')
        )
        self._plan_fold.connect('toggled', self._plan_fold_toggled)
        footer_summary.append(self._plan_fold)

        # One scrollable surface; a small plus floats in the bottom corner.
        scroll = Gtk.ScrolledWindow(vexpand=True, hexpand=True)
        self._plan_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        self._plan_box.add_css_class('plan-items')
        self._plan_box.set_vexpand(True)
        blank_click = Gtk.GestureClick()
        blank_click.connect('released', self._plan_blank_clicked)
        self._plan_box.add_controller(blank_click)
        scroll.set_child(self._plan_box)

        overlay = Gtk.Overlay()
        overlay.set_child(scroll)
        add_btn = Gtk.Button(icon_name='list-add-symbolic')
        add_btn.add_css_class('circular')
        add_btn.add_css_class('suggested-action')
        add_btn.add_css_class('plan-add-fab')
        add_btn.set_tooltip_text(_('Add task'))
        add_btn.set_halign(Gtk.Align.END)
        add_btn.set_valign(Gtk.Align.END)
        add_btn.set_margin_end(14)
        add_btn.set_margin_bottom(14)
        add_btn.connect('clicked', self._plan_add)
        overlay.add_overlay(add_btn)
        parent.append(overlay)

        # Keep title immediately followed by checklist items. Progress,
        # collapse-completed and undo controls live at the bottom instead.
        footer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        footer.add_css_class('plan-footer')
        self._plan_progress_bar = Gtk.ProgressBar()
        self._plan_progress_bar.add_css_class('plan-completion-progress')
        footer.append(self._plan_progress_bar)
        footer.append(footer_summary)
        parent.append(footer)

    def _plan_blank_clicked(self, gesture, count, x, y):
        # Only a click on the empty surface commits editing; clicking text
        # itself should begin (not immediately finish) inline editing.
        picked = self._plan_box.pick(x, y, Gtk.PickFlags.DEFAULT)
        if picked is self._plan_box or picked is None:
            for uid, widgets in list(self._plan_widgets.items()):
                if widgets[1].get_visible():
                    self._plan_finish_edit(None, uid)

    def _plan_find(self, uid):
        return next((item for item in self._plan_items if item['id'] == uid), None)

    def _plan_markup(self, item):
        escaped = GLib.markup_escape_text(item['text'] or _('New task'))
        text = '<s>' + escaped + '</s>' if item['done'] else escaped
        if item.get('due'):
            text += '\\n<small>📅 ' + GLib.markup_escape_text(item['due']) + '</small>'
        return text

    def _plan_progress_update(self):
        done = sum(bool(item['done']) for item in self._plan_items)
        total = len(self._plan_items)
        self._plan_progress.set_label(
            _('Completed {done}/{total}').format(done=done, total=total)
        )
        self._plan_fold.set_sensitive(done > 0)
        self._plan_progress_bar.set_fraction(done / total if total else 0)

    def _plan_fold_toggled(self, toggle):
        toggle.set_icon_name(
            'view-reveal-symbolic' if toggle.get_active()
            else 'view-conceal-symbolic'
        )
        toggle.set_tooltip_text(
            _('Show completed') if toggle.get_active() else _('Hide completed')
        )
        settings = self._app._get_settings()
        if settings:
            settings.set_boolean('hide-completed', toggle.get_active())
        self._plan_refresh()

    def _plan_refresh(self):
        if self._plan_refresh_busy:
            return
        self._plan_refresh_busy = True
        try:
            self._plan_editing_uid = None
            self._plan_render_items()
        finally:
            self._plan_refresh_busy = False

    def _plan_render_items(self):
        # Focus-leave signals can fire while removing old GTK rows.
        # The refresh guard prevents reentrant modification of the widget tree.
        child = self._plan_box.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self._plan_box.remove(child)
            child = nxt
        self._plan_widgets = {}
        collapsed = self._plan_fold.get_active()

        for item in self._plan_items:
            if collapsed and item['done']:
                continue
            uid = item['id']
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
            row.add_css_class('plan-item')
            if item['done']:
                row.add_css_class('plan-item-done')

            check = Gtk.CheckButton()
            check.set_active(item['done'])
            check.set_tooltip_text(_('Toggle completed'))
            check.connect('toggled', self._plan_toggle, uid)
            row.append(check)

            label = Gtk.Label(xalign=0, hexpand=True, wrap=True)
            label.set_markup(self._plan_markup(item))
            label.add_css_class('plan-label')

            # Clicking text edits; dragging the same text moves the entire row.
            text_btn = Gtk.Button()
            text_btn.set_child(label)
            text_btn.set_hexpand(True)
            text_btn.add_css_class('flat')
            text_btn.add_css_class('plan-text-button')
            text_btn.set_tooltip_text(_('Click to edit · drag to reorder'))
            text_btn.connect('clicked', self._plan_start_edit, uid)
            drag = Gtk.DragSource()
            drag.set_actions(Gdk.DragAction.MOVE)
            drag.connect('prepare', self._plan_drag_prepare, uid)
            text_btn.add_controller(drag)
            drop = Gtk.DropTarget.new(GObject.TYPE_STRING, Gdk.DragAction.MOVE)
            drop.connect('drop', self._plan_drop, uid)
            text_btn.add_controller(drop)
            context = Gtk.GestureClick(button=Gdk.BUTTON_SECONDARY)
            context.connect('pressed', self._plan_open_date_menu, uid, text_btn)
            text_btn.add_controller(context)
            row.append(text_btn)

            entry = Gtk.Entry(text=item['text'], hexpand=True)
            entry.set_placeholder_text(_('New task'))
            entry.set_visible(False)
            entry.connect('changed', self._plan_text_changed, uid, label)
            entry.connect('activate', self._plan_enter, uid)
            focus = Gtk.EventControllerFocus()
            focus.connect('leave', lambda controller, key=uid: self._plan_finish_edit(None, key))
            entry.add_controller(focus)
            row.append(entry)
            self._plan_widgets[uid] = (label, entry)

            delete = Gtk.Button(icon_name='user-trash-symbolic')
            delete.add_css_class('flat')
            delete.add_css_class('plan-delete')
            delete.set_tooltip_text(_('Delete task'))
            delete.connect('clicked', self._plan_delete, uid)
            row.append(delete)
            self._plan_box.append(row)
        self._plan_progress_update()

    def _plan_drag_prepare(self, source, x, y, uid):
        return Gdk.ContentProvider.new_for_value(uid)

    def _plan_drop(self, target, dragged_uid, x, y, dest_uid):
        if not isinstance(dragged_uid, str):
            return False
        positions = {item['id']: i for i, item in enumerate(self._plan_items)}
        if dragged_uid not in positions or dest_uid not in positions:
            return False
        old, new = positions[dragged_uid], positions[dest_uid]
        if old == new:
            return True
        item = self._plan_items.pop(old)
        self._plan_items.insert(new, item)
        self._plan_refresh()
        self._on_content_changed()
        return True

    def _plan_open_date_menu(self, gesture, count, x, y, uid, button):
        item = self._plan_find(uid)
        if item is None:
            return
        popover = Gtk.Popover()
        popover.set_parent(button)
        layout = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        layout.set_margin_top(8)
        layout.set_margin_bottom(8)
        layout.set_margin_start(8)
        layout.set_margin_end(8)
        label = Gtk.Label(label=_('Choose due date'))
        layout.append(label)
        calendar = Gtk.Calendar()
        layout.append(calendar)
        calendar.connect('day-selected', self._plan_date_chosen, uid, popover)
        clear = Gtk.Button(label=_('Clear due date'))
        clear.connect('clicked', self._plan_clear_date, uid, popover)
        layout.append(clear)
        popover.set_child(layout)
        popover.connect('closed', lambda obj: obj.unparent())
        popover.popup()

    def _plan_date_chosen(self, calendar, uid, popover):
        item = self._plan_find(uid)
        if item is not None:
            item['due'] = calendar.get_date().format('%Y-%m-%d')
            popover.popdown()
            GLib.idle_add(self._plan_refresh)
            self._on_content_changed()

    def _plan_clear_date(self, button, uid, popover):
        item = self._plan_find(uid)
        if item is not None:
            item['due'] = ''
            popover.popdown()
            GLib.idle_add(self._plan_refresh)
            self._on_content_changed()

    def _plan_toggle(self, check, uid):
        item = self._plan_find(uid)
        if item is None:
            return
        item['done'] = check.get_active()
        # Update background, strikethrough and fold visibility atomically.
        self._plan_refresh()
        self._on_content_changed()

    def _plan_text_changed(self, entry, uid, label):
        item = self._plan_find(uid)
        if item is not None:
            item['text'] = entry.get_text()
            label.set_markup(self._plan_markup(item))
            self._on_content_changed()

    def _plan_start_edit(self, button, uid):
        # A Gtk.Button may still be dispatching a double-click. Do not hide
        # its own widget during the clicked signal; defer it to the main loop.
        GLib.idle_add(self._plan_activate_editor, uid)

    def _plan_activate_editor(self, uid):
        if self._plan_refresh_busy:
            return GLib.SOURCE_REMOVE
        if self._plan_pending_uid == uid:
            self._plan_pending_uid = None
        widgets = self._plan_widgets.get(uid)
        if not widgets:
            return GLib.SOURCE_REMOVE
        label, entry = widgets
        if entry.get_visible():
            entry.grab_focus()
            return GLib.SOURCE_REMOVE
        # Finish the previous editor without destroying widgets in focus signals.
        previous = self._plan_editing_uid
        if previous and previous != uid:
            self._plan_finish_edit(None, previous)
        label.get_parent().set_visible(False)
        entry.set_visible(True)
        self._plan_editing_uid = uid
        entry.grab_focus()
        entry.select_region(-1, -1)
        return GLib.SOURCE_REMOVE

    def _plan_enter(self, entry, uid):
        item = self._plan_find(uid)
        add_next = item is not None and bool(item['text'].strip())
        self._plan_finish_edit(entry, uid)
        if add_next:
            # The current entry has stopped editing before the next is created.
            self._plan_add(None)

    def _plan_finish_edit(self, entry, uid):
        if self._plan_refresh_busy:
            return
        widgets = self._plan_widgets.get(uid)
        if not widgets:
            return
        label, field = widgets
        if not field.get_visible():
            return
        # Disable the editor before focus changes can dispatch another leave.
        field.set_visible(False)
        label.get_parent().set_visible(True)
        if self._plan_editing_uid == uid:
            self._plan_editing_uid = None
        item = self._plan_find(uid)
        if item is not None and not item['text'].strip():
            # Removing a Gtk.Entry directly from its own focus-out callback
            # can cause GTK criticals/crashes. Drop the draft after dispatch.
            GLib.idle_add(self._plan_remove_empty_draft, uid)
        else:
            self._on_content_changed()

    def _plan_remove_empty_draft(self, uid):
        if self._plan_refresh_busy:
            return GLib.SOURCE_CONTINUE
        item = self._plan_find(uid)
        widgets = self._plan_widgets.get(uid)
        if self._plan_pending_uid == uid:
            self._plan_pending_uid = None
        if (item is not None and not item['text'].strip()
                and (not widgets or not widgets[1].get_visible())):
            self._plan_items = [i for i in self._plan_items if i['id'] != uid]
            self._plan_refresh()
            self._on_content_changed()
        return GLib.SOURCE_REMOVE

    def _plan_add(self, button):
        # Two clicks may arrive before the first editor has been focused by
        # the next GTK idle iteration. Reuse that pending draft.
        if self._plan_pending_uid:
            pending = self._plan_find(self._plan_pending_uid)
            if pending is not None and not pending['text'].strip():
                return
            self._plan_pending_uid = None
        # A repeated tap must not destroy a still-focused empty draft.
        for uid, (label, entry) in list(self._plan_widgets.items()):
            if entry.get_visible():
                item = self._plan_find(uid)
                if item is not None and not item['text'].strip():
                    entry.grab_focus()
                    return
                self._plan_finish_edit(None, uid)
        item = new_item()
        self._plan_items.append(item)
        self._plan_pending_uid = item['id']
        self._plan_refresh()
        GLib.idle_add(self._plan_activate_editor, item['id'])

    def _plan_delete(self, button, uid):
        for index, item in enumerate(self._plan_items):
            if item['id'] == uid:
                # Preserve full metadata and order (including due date).
                self._plan_undo_stack.append((index, dict(item)))
                self._plan_undo_stack = self._plan_undo_stack[-20:]
                self._plan_items.pop(index)
                self._plan_undo_button.set_visible(True)
                self._plan_refresh()
                self._on_content_changed()
                return

    def _plan_undo(self, button):
        if not self._plan_undo_stack:
            return
        index, item = self._plan_undo_stack.pop()
        if not self._plan_find(item['id']):
            self._plan_items.insert(min(index, len(self._plan_items)), item)
        self._plan_undo_button.set_visible(bool(self._plan_undo_stack))
        self._plan_refresh()
        self._on_content_changed()

    def _format_visible(self):
        settings = self._app._get_settings()
        return settings.get_boolean('show-format-toolbar') if settings else False

    def _toggle_format_toolbar(self, button):
        if self._markdown_preview_button.get_active():
            # Preview never changes the rich-text source or formatting state.
            return
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
        compact = self._compact_window
        if compact is not None:
            self._compact_window = None
            self._compact_closing = True
            compact.close()
            self._compact_closing = False
        if hasattr(self, '_auto_save'):
            self._auto_save.save_now()
        return False
