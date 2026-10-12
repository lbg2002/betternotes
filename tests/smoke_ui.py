# SPDX-License-Identifier: GPL-3.0-or-later
"""Minimal GTK/XWayland UI smoke test for CI (run inside Xvfb + D-Bus)."""
from betternotes.application import BetterNotesApp
from betternotes.note_window import NoteWindow
from betternotes.plan import parse_items
from betternotes.preferences import PreferencesWindow
from betternotes.x11_position import get_window_geometry, move_window_direct
from gi.repository import Pango, GLib
import time


def wait_for(predicate, seconds=3):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        while GLib.MainContext.default().pending():
            GLib.MainContext.default().iteration(False)
        if predicate():
            return True
        time.sleep(0.02)
    return predicate()


app = BetterNotesApp()
assert app.register(None), 'Unable to register GTK app'
note = app.store.create_note(title='Test Plan', kind='plan', color='blue')
window = NoteWindow(application=app, note=note)
window.present()
assert wait_for(lambda: window.get_surface() is not None)
assert hasattr(window, '_plan_box')
assert window._plan_progress.get_parent().has_css_class('plan-footer-summary')
assert window._plan_fold.get_label() is None
assert window._plan_progress_bar.get_parent().has_css_class('plan-footer')
# Reproduce the crash: two rapid taps before GTK processes focus changes.
window._plan_add(None)
window._plan_add(None)
assert len(window._plan_items) == 1, 'Double click must create one draft'
item = window._plan_items[0]
assert wait_for(lambda: window._plan_widgets[item['id']][1].get_visible())
window._plan_add(None)
assert len(window._plan_items) == 1, 'Repeat tap on empty editor must be safe'
window._plan_widgets[item['id']][1].set_text('Test checkbox item')
window._plan_finish_edit(window._plan_widgets[item['id']][1], item['id'])
assert not window._plan_widgets[item['id']][1].get_visible(), 'Editor should leave on Enter'
window._plan_start_edit(None, item['id'])
window._plan_start_edit(None, item['id'])
assert wait_for(lambda: window._plan_widgets[item['id']][1].get_visible())
window._plan_finish_edit(None, item['id'])
assert not window._plan_widgets[item['id']][1].get_visible()
row = window._plan_box.get_first_child()
checkbox = row.get_first_child()
checkbox.set_active(True)
assert window._plan_items[0]['done'] is True
assert window._plan_progress_bar.get_fraction() == 1
assert '<s>' in window._plan_widgets[item['id']][0].get_label()
assert window._plan_box.get_first_child().has_css_class('plan-item-done')
window._plan_add(None)
assert wait_for(lambda: window._plan_widgets[window._plan_items[-1]['id']][1].get_visible())
window._plan_drop(None, window._plan_items[1]['id'], 0, 0, window._plan_items[0]['id'])
assert window._plan_items[0]['text'] == ''
window._plan_widgets[window._plan_items[0]['id']][1].set_text('Dragged item')
window._plan_finish_edit(None, window._plan_items[0]['id'])
window._plan_fold.set_active(True)
assert window._plan_fold.get_active()
assert window._plan_box.get_first_child().get_next_sibling() is None
window._plan_fold.set_active(False)
window._save_note()
stored = app.store.get_note(note.id)
assert stored.kind == 'plan'
assert len(parse_items(stored.content)) == 2
assert any(i['done'] for i in parse_items(stored.content))
removed_id = window._plan_items[0]['id']
window._plan_delete(None, removed_id)
assert window._plan_undo_button.get_visible()
window._save_note()
assert len(parse_items(app.store.get_note(note.id).content)) == 1
window._plan_undo(None)
assert window._plan_find(removed_id) is not None
assert len(window._plan_items) == 2
assert not window._plan_undo_button.get_visible()

# Enter should commit text and open a new task, not keep the old row editing.
window._plan_add(None)
current_id = window._plan_items[-1]['id']
assert wait_for(lambda: window._plan_widgets[current_id][1].get_visible())
field = window._plan_widgets[current_id][1]
field.set_text('Write the paper')
window._plan_enter(field, current_id)
assert wait_for(lambda: window._plan_widgets[window._plan_items[-1]['id']][1].get_visible())
assert window._plan_find(current_id)['text'] == 'Write the paper'
assert not window._plan_widgets[current_id][1].get_visible()
assert len(window._plan_items) == 4
assert window._plan_widgets[window._plan_items[-1]['id']][1].get_visible()
# Blank trailing draft disappears when clicking out of the editor.
window._plan_finish_edit(None, window._plan_items[-1]['id'])
assert wait_for(lambda: len(window._plan_items) == 3)

# The compact handle is a separate undecorated window with X11 topmost
# handled by the original EWMH mechanism, preserving the original editor.
settings = app._get_settings()
settings.set_string('compact-shape', 'ball')
window._collapse_to_compact()
assert window._compact_window is not None
assert window._compact_window._shape == 'ball'
assert wait_for(lambda: get_window_geometry(window._compact_window.get_surface()) is not None)
# Simulate moving the handle to a different single-screen coordinate.
move_window_direct(window._compact_window.get_surface(), 260, 190)
assert wait_for(lambda: (
    (geo := get_window_geometry(window._compact_window.get_surface())) is not None
    and abs(geo[0] - 260) < 35 and abs(geo[1] - 190) < 35
))
expected_handle = get_window_geometry(window._compact_window.get_surface())
assert not window.get_visible()
window._restore_from_compact()
assert wait_for(lambda: window._compact_window is None, seconds=6)
assert window.get_visible()
# Under a real X11 WM the expanded editor must be placed near the handle,
# not remain centered on the virtual display.
actual = get_window_geometry(window.get_surface())
assert actual is not None
assert abs(actual[0] - expected_handle[0]) < 250, (actual, expected_handle)
assert abs(actual[1] - expected_handle[1]) < 120, (actual, expected_handle)
settings.set_string('compact-shape', 'pill')
window._collapse_to_compact()
assert window._compact_window._shape == 'pill'
window._restore_from_compact()
assert wait_for(lambda: window._compact_window is None, seconds=6)
assert window.get_visible()

legacy = app.store.create_note(title='Old note', kind='note')
note_window = NoteWindow(application=app, note=legacy)
assert hasattr(note_window, '_text_view')
note_window._save_note()
note_window._collapse_to_compact()
assert note_window._compact_window is not None
note_window._restore_from_compact()
assert wait_for(lambda: note_window._compact_window is None, seconds=6)

# Global typography changes should affect already-open editor windows.
settings = app._get_settings()
assert settings is not None, 'CI must expose compiled GSettings schema'
prefs = PreferencesWindow()
assert prefs._font_button.get_font_desc() is not None
settings.set_int('font-size', 20)
settings.set_string('font-family', 'Noto Sans CJK SC')
assert settings.get_int('font-size') == 20
assert settings.get_string('font-family') == 'Noto Sans CJK SC'
prefs._font_button.set_font_desc(Pango.FontDescription.from_string('Monospace'))
assert settings.get_string('font-family') == 'Monospace'
prefs._on_reset_typography(None)
assert settings.get_string('font-family') == ''
assert settings.get_int('font-size') == 14
prefs.close()

# New plans should have an editable title from first creation.
count_before = len(app.store.get_all_notes())
app._create_note('plan')
assert len(app.store.get_all_notes()) == count_before + 1
last_plan = app.store.get_all_notes()[0]
assert last_plan.title, 'Creating plan must not leave an empty title'
assert last_plan.kind == 'plan'
app.close_note_window(last_plan.id)

note_window.close()
window.close()
app.store.close()
print('GTK plan and regular note UI smoke test passed')
