# SPDX-License-Identifier: GPL-3.0-or-later

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Adw, Gdk, Gio, GLib, GObject, Gtk

from betternotes.constants import APP_ID
from betternotes.i18n import _
from betternotes.note_card import NoteCard


class MainWindow(Adw.ApplicationWindow):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._app = self.get_application()
        self._current_tag_filter = None
        self._search_query = ''
        self._showing_trash = False
        self._search_timeout_id = None

        # Selection mode state
        self._selection_mode = False
        self._selected_ids = set()

        self.set_title('PinPlan · 轻笺')
        self.set_default_size(900, 650)
        self.set_icon_name(APP_ID)

        self._build_ui()
        self._connect_signals()
        self._setup_key_controller()
        self._refresh_notes()
        self._refresh_tags()

    def _build_ui(self):
        # Main layout
        self._toolbar_view = Adw.ToolbarView()

        # --- Normal header bar ---
        self._header = Adw.HeaderBar()

        # Search button
        self._search_btn = Gtk.ToggleButton(icon_name='system-search-symbolic')
        self._search_btn.connect('toggled', self._on_search_toggled)
        self._header.pack_start(self._search_btn)

        # View switcher (Notes / Trash)
        self._view_stack = Gtk.Stack()
        self._view_switcher = Gtk.StackSwitcher(stack=self._view_stack)
        self._header.set_title_widget(self._view_switcher)

        # Menu
        menu = Gio.Menu()
        menu.append(_('New note'), 'app.new-note')
        menu.append(_('New plan'), 'app.new-plan')
        menu.append(_('Keyboard Shortcuts'), 'app.shortcuts')
        menu.append(_('Preferences'), 'app.preferences')
        menu.append(_('About BetterNotes'), 'app.about')

        menu_btn = Gtk.MenuButton(
            icon_name='open-menu-symbolic',
            menu_model=menu,
        )
        self._header.pack_end(menu_btn)

        self._toolbar_view.add_top_bar(self._header)

        # --- Selection header bar (hidden by default) ---
        self._selection_header = Adw.HeaderBar()
        self._selection_header.set_visible(False)
        self._selection_header.set_show_back_button(False)

        cancel_btn = Gtk.Button(label=_('Cancel'))
        cancel_btn.connect('clicked', lambda b: self._exit_selection_mode())
        self._selection_header.pack_start(cancel_btn)

        self._selection_count_label = Gtk.Label(label='0 selected')
        self._selection_header.set_title_widget(self._selection_count_label)

        select_all_btn = Gtk.Button(label=_('Select All'))
        select_all_btn.connect('clicked', lambda b: self._select_all())
        self._selection_header.pack_end(select_all_btn)

        self._toolbar_view.add_top_bar(self._selection_header)

        # Search bar
        self._search_bar = Gtk.SearchBar()
        self._search_entry = Gtk.SearchEntry(
            placeholder_text=_('Search notes...'),
        )
        self._search_entry.add_css_class('search-entry')
        self._search_entry.connect('search-changed', self._on_search_changed)
        self._search_bar.set_child(self._search_entry)
        self._search_bar.connect_entry(self._search_entry)
        self._toolbar_view.add_top_bar(self._search_bar)

        # Notes page
        notes_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        # Tag filter bar
        tag_scroll = Gtk.ScrolledWindow(
            hscrollbar_policy=Gtk.PolicyType.AUTOMATIC,
            vscrollbar_policy=Gtk.PolicyType.NEVER,
        )
        self._tag_bar = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=6,
        )
        self._tag_bar.set_margin_start(12)
        self._tag_bar.set_margin_end(12)
        self._tag_bar.set_margin_top(6)
        self._tag_bar.set_margin_bottom(6)
        tag_scroll.set_child(self._tag_bar)
        self._tag_scroll = tag_scroll
        self._tag_scroll.set_visible(False)
        notes_page.append(tag_scroll)

        # Notes grid
        notes_scroll = Gtk.ScrolledWindow(vexpand=True)
        self._notes_grid = Gtk.FlowBox(
            selection_mode=Gtk.SelectionMode.NONE,
            homogeneous=False,
            max_children_per_line=6,
            min_children_per_line=2,
            row_spacing=8,
            column_spacing=8,
        )
        self._notes_grid.add_css_class('notes-grid')
        self._notes_grid.set_margin_start(12)
        self._notes_grid.set_margin_end(12)
        self._notes_grid.set_margin_top(8)
        self._notes_grid.set_margin_bottom(8)
        notes_scroll.set_child(self._notes_grid)

        # Empty state
        self._empty_state = Adw.StatusPage(
            icon_name='document-new-symbolic',
            title=_('No Notes Yet'),
            description=_('Press + or Ctrl+N to create your first note'),
        )
        self._empty_state.add_css_class('empty-state')

        self._notes_stack = Gtk.Stack()
        self._notes_stack.add_named(notes_scroll, 'grid')
        self._notes_stack.add_named(self._empty_state, 'empty')
        notes_page.append(self._notes_stack)

        # Trash page
        trash_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        # Trash banner
        self._trash_banner = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=8,
        )
        self._trash_banner.add_css_class('trash-banner')
        trash_label = Gtk.Label(
            label=_('Items in trash are deleted after 30 days'),
            hexpand=True,
            xalign=0,
        )
        self._trash_banner.append(trash_label)
        empty_trash_btn = Gtk.Button(label=_('Empty Trash'))
        empty_trash_btn.add_css_class('destructive-action')
        empty_trash_btn.connect('clicked', self._on_empty_trash)
        self._trash_banner.append(empty_trash_btn)
        trash_page.append(self._trash_banner)

        # Trash grid
        trash_scroll = Gtk.ScrolledWindow(vexpand=True)
        self._trash_grid = Gtk.FlowBox(
            selection_mode=Gtk.SelectionMode.NONE,
            homogeneous=False,
            max_children_per_line=6,
            min_children_per_line=2,
            row_spacing=8,
            column_spacing=8,
        )
        self._trash_grid.set_margin_start(12)
        self._trash_grid.set_margin_end(12)
        self._trash_grid.set_margin_top(8)
        self._trash_grid.set_margin_bottom(8)
        trash_scroll.set_child(self._trash_grid)

        self._trash_empty_state = Adw.StatusPage(
            icon_name='user-trash-symbolic',
            title=_('Trash is Empty'),
            description=_('Deleted notes will appear here'),
        )

        self._trash_stack = Gtk.Stack()
        self._trash_stack.add_named(trash_scroll, 'grid')
        self._trash_stack.add_named(self._trash_empty_state, 'empty')
        trash_page.append(self._trash_stack)

        # Add to view stack
        self._view_stack.add_titled(notes_page, 'notes', _('Notes'))
        self._view_stack.add_titled(trash_page, 'trash', _('Trash'))
        self._view_stack.connect('notify::visible-child', self._on_view_changed)

        self._toolbar_view.set_content(self._view_stack)

        # Toast overlay (must wrap everything for toasts to display)
        self._toast_overlay = Adw.ToastOverlay()
        self._toast_overlay.set_child(self._toolbar_view)

        # FAB overlay
        overlay = Gtk.Overlay()
        overlay.set_child(self._toast_overlay)

        new_menu = Gio.Menu()
        new_menu.append(_('New note'), 'app.new-note')
        new_menu.append(_('New plan'), 'app.new-plan')
        fab = Gtk.MenuButton(
            icon_name='list-add-symbolic',
            tooltip_text=_('Create note or plan'),
            menu_model=new_menu,
        )
        fab.add_css_class('fab')
        fab.add_css_class('suggested-action')
        fab.add_css_class('circular')
        fab.set_halign(Gtk.Align.END)
        fab.set_valign(Gtk.Align.END)
        fab.set_margin_end(24)
        fab.set_margin_bottom(24)
        overlay.add_overlay(fab)
        self._fab = fab

        # Selection action bar (hidden by default, shown as bottom overlay)
        self._selection_bar = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=8,
        )
        self._selection_bar.add_css_class('selection-action-bar')
        self._selection_bar.set_halign(Gtk.Align.CENTER)
        self._selection_bar.set_valign(Gtk.Align.END)
        self._selection_bar.set_margin_bottom(24)
        self._selection_bar.set_visible(False)

        # Notes view action: Move to Trash
        self._sel_trash_btn = Gtk.Button(label=_('Move to Trash'))
        self._sel_trash_btn.add_css_class('destructive-action')
        self._sel_trash_btn.add_css_class('pill')
        self._sel_trash_btn.connect('clicked', self._on_bulk_trash)
        self._selection_bar.append(self._sel_trash_btn)

        # Trash view actions: Restore, Delete Permanently
        self._sel_restore_btn = Gtk.Button(label=_('Restore'))
        self._sel_restore_btn.add_css_class('suggested-action')
        self._sel_restore_btn.add_css_class('pill')
        self._sel_restore_btn.connect('clicked', self._on_bulk_restore)
        self._selection_bar.append(self._sel_restore_btn)

        self._sel_delete_btn = Gtk.Button(label=_('Delete Permanently'))
        self._sel_delete_btn.add_css_class('destructive-action')
        self._sel_delete_btn.add_css_class('pill')
        self._sel_delete_btn.connect('clicked', self._on_bulk_delete)
        self._selection_bar.append(self._sel_delete_btn)

        overlay.add_overlay(self._selection_bar)

        self.set_content(overlay)

    def _setup_key_controller(self):
        key_ctrl = Gtk.EventControllerKey()
        key_ctrl.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        key_ctrl.connect('key-pressed', self._on_key_pressed)
        self.add_controller(key_ctrl)

    def _on_key_pressed(self, controller, keyval, keycode, state):
        mods = state & Gtk.accelerator_get_default_mod_mask()
        if keyval == Gdk.KEY_Escape and self._selection_mode:
            self._exit_selection_mode()
            return True
        if (keyval == Gdk.KEY_a
                and mods == Gdk.ModifierType.CONTROL_MASK):
            if not self._selection_mode:
                self._enter_selection_mode()
            self._select_all()
            return True
        return False

    def _connect_signals(self):
        self._app.connect('note-changed', self._on_note_signal)
        self._app.connect('note-created', self._on_note_signal)
        self._app.connect('note-trashed', self._on_note_signal)
        self._app.connect('note-restored', self._on_note_signal)
        self._app.connect('note-deleted', self._on_note_signal)

    def _on_note_signal(self, app, note_id):
        self._refresh_notes()
        self._refresh_tags()
        self._refresh_trash()

    def _on_search_toggled(self, btn):
        active = btn.get_active()
        self._search_bar.set_search_mode(active)
        if active:
            self._search_entry.grab_focus()
        else:
            self._search_query = ''
            self._search_entry.set_text('')
            self._refresh_notes()

    def _on_search_changed(self, entry):
        self._search_query = entry.get_text()
        # Debounce search
        if self._search_timeout_id:
            GLib.source_remove(self._search_timeout_id)
        self._search_timeout_id = GLib.timeout_add(200, self._do_search)

    def _do_search(self):
        self._search_timeout_id = None
        self._refresh_notes()
        return GLib.SOURCE_REMOVE

    def _on_view_changed(self, stack, pspec):
        is_trash = stack.get_visible_child_name() == 'trash'
        self._showing_trash = is_trash
        if self._selection_mode:
            self._exit_selection_mode()
        self._fab.set_visible(not is_trash)
        if is_trash:
            self._refresh_trash()

    # --- Selection mode ---

    def _enter_selection_mode(self, first_note_id=None):
        if self._selection_mode:
            return
        self._selection_mode = True
        self._selected_ids = set()
        if first_note_id:
            self._selected_ids.add(first_note_id)

        # Swap headers
        self._header.set_visible(False)
        self._selection_header.set_visible(True)

        # Swap FAB / action bar
        self._fab.set_visible(False)
        self._selection_bar.set_visible(True)

        # Show correct action buttons
        self._sel_trash_btn.set_visible(not self._showing_trash)
        self._sel_restore_btn.set_visible(self._showing_trash)
        self._sel_delete_btn.set_visible(self._showing_trash)

        self._update_selection_visuals()

    def _exit_selection_mode(self):
        if not self._selection_mode:
            return
        self._selection_mode = False
        self._selected_ids.clear()

        # Swap headers back
        self._header.set_visible(True)
        self._selection_header.set_visible(False)

        # Swap action bar / FAB back
        self._selection_bar.set_visible(False)
        self._fab.set_visible(not self._showing_trash)

        # Clear visual selection on all cards
        self._clear_card_selection(self._notes_grid)
        self._clear_card_selection(self._trash_grid)

    def _clear_card_selection(self, grid):
        child = grid.get_first_child()
        while child:
            card = child.get_child() if isinstance(child, Gtk.FlowBoxChild) else child
            if isinstance(card, NoteCard):
                card.selected = False
            child = child.get_next_sibling()

    def _toggle_card_selection(self, note_id):
        if note_id in self._selected_ids:
            self._selected_ids.discard(note_id)
        else:
            self._selected_ids.add(note_id)

        if not self._selected_ids:
            self._exit_selection_mode()
            return

        self._update_selection_visuals()

    def _select_all(self):
        grid = self._trash_grid if self._showing_trash else self._notes_grid
        child = grid.get_first_child()
        while child:
            card = child.get_child() if isinstance(child, Gtk.FlowBoxChild) else child
            if isinstance(card, NoteCard):
                self._selected_ids.add(card.note_id)
            child = child.get_next_sibling()
        self._update_selection_visuals()

    def _update_selection_visuals(self):
        count = len(self._selected_ids)
        self._selection_count_label.set_label(
            f'{count} selected'
        )
        # Enable/disable action buttons
        has_selection = count > 0
        self._sel_trash_btn.set_sensitive(has_selection)
        self._sel_restore_btn.set_sensitive(has_selection)
        self._sel_delete_btn.set_sensitive(has_selection)

        # Update card visuals in the active grid
        grid = self._trash_grid if self._showing_trash else self._notes_grid
        child = grid.get_first_child()
        while child:
            card = child.get_child() if isinstance(child, Gtk.FlowBoxChild) else child
            if isinstance(card, NoteCard):
                card.selected = card.note_id in self._selected_ids
            child = child.get_next_sibling()

    def _on_card_activated_or_select(self, card, note_id):
        """Handle click on a card — open note normally, or toggle selection in selection mode."""
        if self._selection_mode:
            self._toggle_card_selection(note_id)
        else:
            # Check if Ctrl is held
            seat = self.get_display().get_default_seat()
            keyboard = seat.get_keyboard() if seat else None
            if keyboard:
                modifiers = keyboard.get_modifier_state()
                if modifiers & Gdk.ModifierType.CONTROL_MASK:
                    self._enter_selection_mode(first_note_id=note_id)
                    return
            self._app.open_note(note_id)

    def _on_card_long_pressed(self, card, note_id):
        """Long-press enters selection mode with this card selected."""
        if not self._selection_mode:
            self._enter_selection_mode(first_note_id=note_id)
        else:
            self._toggle_card_selection(note_id)

    # --- Bulk actions ---

    def _on_bulk_trash(self, btn):
        ids = set(self._selected_ids)
        if not ids:
            return
        self._app.store.trash_notes(ids)
        for note_id in ids:
            self._app.close_note_window(note_id)
        self._exit_selection_mode()
        self._app.emit('note-trashed', '')
        count = len(ids)
        self._show_toast(
            f'{count} note{"s" if count != 1 else ""} moved to trash',
            _('Undo'), self._undo_bulk_trash, ids,
        )

    def _undo_bulk_trash(self, note_ids):
        self._app.store.restore_notes(note_ids)
        self._app.emit('note-restored', '')

    def _on_bulk_restore(self, btn):
        ids = set(self._selected_ids)
        if not ids:
            return
        self._app.store.restore_notes(ids)
        self._exit_selection_mode()
        self._app.emit('note-restored', '')
        count = len(ids)
        self._show_toast(f'{count} note{"s" if count != 1 else ""} restored')

    def _on_bulk_delete(self, btn):
        ids = set(self._selected_ids)
        if not ids:
            return
        count = len(ids)
        dialog = Adw.AlertDialog(
            heading=f'Delete {count} Note{"s" if count != 1 else ""} Permanently?',
            body=_('This action cannot be undone.'),
        )
        dialog.add_response('cancel', _('Cancel'))
        dialog.add_response('delete', 'Delete')
        dialog.set_response_appearance('delete', Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.connect('response', self._on_bulk_delete_confirmed, ids)
        dialog.present(self)

    def _on_bulk_delete_confirmed(self, dialog, response, note_ids):
        if response == 'delete':
            self._app.store.delete_notes(note_ids)
            self._exit_selection_mode()
            self._app.emit('note-deleted', '')
            count = len(note_ids)
            self._show_toast(f'{count} note{"s" if count != 1 else ""} permanently deleted')

    # --- Refresh ---

    def _refresh_notes(self):
        # Clear grid
        child = self._notes_grid.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            self._notes_grid.remove(child)
            child = next_child

        # Get notes
        if self._search_query:
            notes = self._app.store.search_notes(self._search_query)
        elif self._current_tag_filter:
            notes = self._app.store.get_notes_by_tag(self._current_tag_filter)
        else:
            notes = self._app.store.get_all_notes()

        if not notes:
            self._notes_stack.set_visible_child_name('empty')
            return

        self._notes_stack.set_visible_child_name('grid')
        existing_ids = set()
        for note in notes:
            card = NoteCard(note)
            card.connect('activated', self._on_card_activated_or_select)
            card.connect('long-pressed', self._on_card_long_pressed)
            card.connect('trash-requested', self._on_note_trash_requested)
            if self._selection_mode and note.id in self._selected_ids:
                card.selected = True
            existing_ids.add(note.id)
            self._notes_grid.append(card)

        # Prune selected_ids that no longer exist
        if self._selection_mode and not self._showing_trash:
            self._selected_ids &= existing_ids
            if not self._selected_ids:
                self._exit_selection_mode()
            else:
                self._update_selection_visuals()

    def _refresh_trash(self):
        child = self._trash_grid.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            self._trash_grid.remove(child)
            child = next_child

        trashed = self._app.store.get_trashed_notes()
        if not trashed:
            self._trash_stack.set_visible_child_name('empty')
            self._trash_banner.set_visible(False)
            return

        self._trash_stack.set_visible_child_name('grid')
        self._trash_banner.set_visible(True)
        existing_ids = set()
        for note in trashed:
            card = NoteCard(note, is_trash=True)
            card.connect('activated', self._on_card_activated_or_select)
            card.connect('long-pressed', self._on_card_long_pressed)
            card.connect('restore-requested', self._on_note_restore_requested)
            card.connect('delete-requested', self._on_note_delete_requested)
            if self._selection_mode and note.id in self._selected_ids:
                card.selected = True
            existing_ids.add(note.id)
            self._trash_grid.append(card)

        # Prune selected_ids that no longer exist
        if self._selection_mode and self._showing_trash:
            self._selected_ids &= existing_ids
            if not self._selected_ids:
                self._exit_selection_mode()
            else:
                self._update_selection_visuals()

    def _refresh_tags(self):
        # Clear tag bar
        child = self._tag_bar.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            self._tag_bar.remove(child)
            child = next_child

        tags = self._app.store.get_all_tags()
        if not tags:
            self._tag_scroll.set_visible(False)
            return

        self._tag_scroll.set_visible(True)

        # "All" button
        all_btn = Gtk.ToggleButton(label=_('All'))
        all_btn.add_css_class('tag-chip')
        all_btn.set_active(self._current_tag_filter is None)
        all_btn.connect('toggled', self._on_tag_filter, None)
        self._tag_bar.append(all_btn)

        for tag in tags:
            btn = Gtk.ToggleButton(label=f'{tag.name} ({tag.note_count})')
            btn.add_css_class('tag-chip')
            btn.set_active(self._current_tag_filter == tag.name)
            btn.connect('toggled', self._on_tag_filter, tag.name)

            gesture = Gtk.GestureClick(button=Gdk.BUTTON_SECONDARY)
            gesture.connect('pressed', self._on_tag_right_click, tag.name, btn)
            btn.add_controller(gesture)

            self._tag_bar.append(btn)

    def _on_tag_filter(self, btn, tag_name):
        if btn.get_active():
            self._current_tag_filter = tag_name
        else:
            self._current_tag_filter = None
        # Untoggle other tag buttons
        child = self._tag_bar.get_first_child()
        while child:
            if isinstance(child, Gtk.ToggleButton) and child != btn:
                child.set_active(False)
            child = child.get_next_sibling()
        self._refresh_notes()

    def _on_tag_right_click(self, gesture, n_press, x, y, tag_name, btn):
        popover = Gtk.Popover()
        popover.set_parent(btn)

        delete_btn = Gtk.Button(label=_('Delete Tag'))
        delete_btn.add_css_class('flat')
        delete_btn.connect('clicked', lambda b: (popover.popdown(), self._on_delete_tag(tag_name)))
        popover.set_child(delete_btn)

        popover.connect('closed', lambda p: p.unparent())
        popover.popup()

    def _on_delete_tag(self, tag_name):
        dialog = Adw.AlertDialog(
            heading=f'Delete Tag \u2018{tag_name}\u2019?',
            body='This will remove the tag from all notes.',
        )
        dialog.add_response('cancel', _('Cancel'))
        dialog.add_response('delete', 'Delete')
        dialog.set_response_appearance('delete', Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.connect('response', self._on_delete_tag_confirmed, tag_name)
        dialog.present(self)

    def _on_delete_tag_confirmed(self, dialog, response, tag_name):
        if response == 'delete':
            self._app.store.delete_tag(tag_name)
            if self._current_tag_filter == tag_name:
                self._current_tag_filter = None
            self._refresh_tags()
            self._refresh_notes()

    def _on_note_activated(self, card, note_id):
        self._app.open_note(note_id)

    def _on_note_trash_requested(self, card, note_id):
        self._app.store.trash_note(note_id)
        self._app.close_note_window(note_id)
        self._app.emit('note-trashed', note_id)
        self._show_toast(_('Note moved to trash'), _('Undo'), self._undo_trash, note_id)

    def _on_note_restore_requested(self, card, note_id):
        self._app.store.restore_note(note_id)
        self._app.emit('note-restored', note_id)
        self._show_toast(_('Note restored'))

    def _on_note_delete_requested(self, card, note_id):
        dialog = Adw.AlertDialog(
            heading='Delete Note Permanently?',
            body=_('This action cannot be undone.'),
        )
        dialog.add_response('cancel', _('Cancel'))
        dialog.add_response('delete', 'Delete')
        dialog.set_response_appearance('delete', Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.connect('response', self._on_delete_confirmed, note_id)
        dialog.present(self)

    def _on_delete_confirmed(self, dialog, response, note_id):
        if response == 'delete':
            self._app.store.delete_note(note_id)
            self._app.emit('note-deleted', note_id)

    def _on_empty_trash(self, btn):
        dialog = Adw.AlertDialog(
            heading=_('Empty Trash?'),
            body=_('All trashed notes will be permanently deleted.'),
        )
        dialog.add_response('cancel', _('Cancel'))
        dialog.add_response('empty', _('Empty Trash'))
        dialog.set_response_appearance('empty', Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.connect('response', self._on_empty_trash_confirmed)
        dialog.present(self)

    def _on_empty_trash_confirmed(self, dialog, response):
        if response == 'empty':
            self._app.store.empty_trash()
            self._refresh_trash()

    def _undo_trash(self, note_id):
        self._app.store.restore_note(note_id)
        self._app.emit('note-restored', note_id)

    def _show_toast(self, message, button_label=None, callback=None, callback_data=None):
        toast = Adw.Toast(title=message, timeout=5)
        if button_label and callback:
            toast.set_button_label(button_label)
            toast.connect('button-clicked', lambda t: callback(callback_data))
        self._toast_overlay.add_toast(toast)
