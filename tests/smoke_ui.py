# SPDX-License-Identifier: GPL-3.0-or-later
"""Minimal GTK/XWayland UI smoke test for CI (run inside Xvfb + D-Bus)."""
from betternotes.application import BetterNotesApp
from betternotes.note_window import NoteWindow
from betternotes.plan import parse_items

app = BetterNotesApp()
assert app.register(None), 'Unable to register GTK app'
note = app.store.create_note(title='Test Plan', kind='plan', color='blue')
window = NoteWindow(application=app, note=note)
assert hasattr(window, '_plan_box')
window._plan_add(None)
item = window._plan_items[0]
window._plan_widgets[item['id']][1].set_text('Test checkbox item')
window._plan_finish_edit(window._plan_widgets[item['id']][1], item['id'])
row = window._plan_box.get_first_child()
checkbox = row.get_first_child()
checkbox.set_active(True)
assert window._plan_items[0]['done'] is True
assert '<s>' in window._plan_widgets[item['id']][0].get_label()
window._plan_add(None)
window._plan_move(None, window._plan_items[1]['id'], -1)
assert window._plan_items[0]['text'] == ''
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
note_window.close()
window.close()
app.store.close()
print('GTK plan and regular note UI smoke test passed')
