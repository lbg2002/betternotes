# SPDX-License-Identifier: GPL-3.0-or-later
"""Minimal GTK/XWayland UI smoke test for CI (run inside Xvfb + D-Bus)."""
from betternotes.application import BetterNotesApp
from betternotes.note_window import NoteWindow
from betternotes.plan import parse_items
from betternotes.preferences import PreferencesWindow
from betternotes.x11_position import get_window_geometry, move_window_direct, restore_position, compact_position
from gi.repository import Pango, GLib
import time


def pump_for(seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        while GLib.MainContext.default().pending():
            GLib.MainContext.default().iteration(False)
        time.sleep(0.025)


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

# Atomic compact handoff: both windows exist temporarily, but the
# incoming one must have opacity zero until it has the correct position.
settings = app._get_settings()
settings.set_string('compact-shape', 'ball')
window.present()
assert wait_for(lambda: get_window_geometry(window.get_surface()) is not None)
move_window_direct(window.get_surface(), 220, 150)
assert wait_for(lambda: (
    (geo := get_window_geometry(window.get_surface())) is not None
    and abs(geo[0] - 220) < 35 and abs(geo[1] - 150) < 35
))
initial_note = get_window_geometry(window.get_surface())
window._collapse_to_compact()
assert window._compact_window is not None
ball = window._compact_window
assert ball._shape == 'ball'
assert ball.get_opacity() == 0.0
assert window.get_visible(), 'Original note must stay visible during positioning'
assert wait_for(lambda: not window.get_visible(), seconds=6)
assert ball.get_opacity() == 1.0
ball_geo = get_window_geometry(ball.get_surface())
assert ball_geo is not None
monitors = []
model = window.get_display().get_monitors()
for ix in range(model.get_n_items()):
    geo = model.get_item(ix).get_geometry()
    monitors.append((geo.x, geo.y, geo.width, geo.height))
ball_target = compact_position(initial_note, (58, 58), monitors)
assert abs(ball_geo[0] - ball_target[0]) <= 35, (ball_geo, ball_target)
assert abs(ball_geo[1] - ball_target[1]) <= 35, (ball_geo, ball_target)

# Move the handle. Expanded window stays invisible while the WM places it.
move_window_direct(ball.get_surface(), 380, 230)
assert wait_for(lambda: (
    (geo := get_window_geometry(ball.get_surface())) is not None
    and abs(geo[0] - 380) < 35 and abs(geo[1] - 230) < 35
))
moved_handle = get_window_geometry(ball.get_surface())
expanded_goal = restore_position(moved_handle, window._expanded_size, monitors)
window._restore_from_compact()
assert window.get_opacity() == 0.0, 'Editor must not appear at the center'
assert ball.get_visible()

# Reproduce Mutter recentering 1.6s after remapping, before reveal.
recentered = [False]
def simulate_late_recenter():
    assert window.get_opacity() == 0.0
    surface = window.get_surface()
    geo = get_window_geometry(surface)
    mon = monitors[0]
    cx = round(mon[0] + (mon[2] - geo[2]) / 2)
    cy = round(mon[1] + (mon[3] - geo[3]) / 2)
    recentered[0] = move_window_direct(surface, cx, cy)
    return GLib.SOURCE_REMOVE

GLib.timeout_add(1500, simulate_late_recenter)
assert wait_for(lambda: window._compact_window is None, seconds=8)
assert recentered[0], 'The delayed recenter scenario was not simulated'
assert window.get_opacity() == 1.0
actual = get_window_geometry(window.get_surface())
assert actual is not None
assert abs(actual[0] - expanded_goal[0]) <= 75, (actual, expanded_goal)
assert abs(actual[1] - expanded_goal[1]) <= 75, (actual, expanded_goal)
# There should be no user-visible correction timer after expansion.
assert not hasattr(window, '_watch_restore_position')
pump_for(1.2)
stable = get_window_geometry(window.get_surface())
assert abs(stable[0] - expanded_goal[0]) <= 75, (stable, expanded_goal)
assert abs(stable[1] - expanded_goal[1]) <= 75, (stable, expanded_goal)

settings.set_string('compact-shape', 'pill')
# Fold in the new location, not the original creation location.
before_pill = get_window_geometry(window.get_surface())
window._collapse_to_compact()
pill = window._compact_window
assert pill is not None and pill._shape == 'pill'
assert wait_for(lambda: not window.get_visible(), seconds=6)
pill_pos = get_window_geometry(pill.get_surface())
pill_goal = compact_position(before_pill, (188, 46), monitors)
assert abs(pill_pos[0] - pill_goal[0]) <= 35, (pill_pos, pill_goal)
assert abs(pill_pos[1] - pill_goal[1]) <= 35, (pill_pos, pill_goal)
window._restore_from_compact()
assert wait_for(lambda: window._compact_window is None, seconds=8)
assert window.get_opacity() == 1.0

legacy = app.store.create_note(title='Old note', kind='note')
note_window = NoteWindow(application=app, note=legacy)
assert hasattr(note_window, '_text_view')
note_window._save_note()
note_window.present()
assert wait_for(lambda: get_window_geometry(note_window.get_surface()) is not None)
note_window._collapse_to_compact()
assert note_window._compact_window is not None
assert wait_for(lambda: not note_window.get_visible(), seconds=6)
note_window._restore_from_compact()
assert wait_for(lambda: note_window._compact_window is None, seconds=8)
assert note_window.get_opacity() == 1.0

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
