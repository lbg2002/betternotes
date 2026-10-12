# SPDX-License-Identifier: GPL-3.0-or-later
"""Minimal GTK/XWayland UI smoke test for CI (run inside Xvfb + D-Bus)."""
from betternotes.application import BetterNotesApp
from betternotes.note_window import NoteWindow
from betternotes.plan import parse_items
from betternotes.preferences import PreferencesWindow
from gi.repository import Pango

app = BetterNotesApp()
assert app.register(None), 'Unable to register GTK app'
note = app.store.create_note(title='Test Plan', kind='plan', color='blue')
window = NoteWindow(application=app, note=note)
assert hasattr(window, '_plan_box')
window._plan_add(None)
item = window._plan_items[0]
window._plan_widgets[item['id']][1].set_text('Test checkbox item')
window._plan_finish_edit(window._plan_widgets[item['id']][1], item['id'])
assert not window._plan_widgets[item['id']][1].get_visible(), 'Editor should leave on Enter'
window._plan_start_edit(None, item['id'])
assert window._plan_widgets[item['id']][1].get_visible()
window._plan_finish_edit(None, item['id'])
assert not window._plan_widgets[item['id']][1].get_visible()
row = window._plan_box.get_first_child()
checkbox = row.get_first_child()
checkbox.set_active(True)
assert window._plan_items[0]['done'] is True
assert '<s>' in window._plan_widgets[item['id']][0].get_label()
assert window._plan_box.get_first_child().has_css_class('plan-item-done')
window._plan_add(None)
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
window._plan_delete(None, window._plan_items[0]['id'])
window._save_note()
assert len(parse_items(app.store.get_note(note.id).content)) == 1

legacy = app.store.create_note(title='Old note', kind='note')
note_window = NoteWindow(application=app, note=legacy)
assert hasattr(note_window, '_text_view')
note_window._save_note()

# Global typography changes should affect already-open editor windows.
settings = app._get_settings()
assert settings is not None, 'CI must expose compiled GSettings schema'
prefs = PreferencesWindow()
assert prefs._font_button.get_font_desc() is not None
settings.set_int('font-size', 20)
settings.set_string('font-family', 'Noto Sans CJK SC')
assert settings.get_int('font-size') == 20
assert settings.get_string('font-family') == 'Noto Sans CJK SC'
prefs._font_button.set_font_desc(Pango.FontDescription.from_string('Sans'))
assert settings.get_string('font-family') == 'Sans'
prefs._on_reset_typography(None)
assert settings.get_string('font-family') == ''
assert settings.get_int('font-size') == 14
prefs.close()

note_window.close()
window.close()
app.store.close()
print('GTK plan and regular note UI smoke test passed')
