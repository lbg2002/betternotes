# SPDX-License-Identifier: GPL-3.0-or-later
import os
import sqlite3
import tempfile
import unittest

from betternotes.note_store import NoteStore
from betternotes.plan import new_item, parse_items, preview_items, serialize_items


class PlanPersistenceTests(unittest.TestCase):
    def test_roundtrip_and_order(self):
        one, two = new_item('写论文'), new_item('Test')
        one['done'] = True
        payload = serialize_items([two, one])
        restored = parse_items(payload)
        self.assertEqual([task['text'] for task in restored], ['Test', '写论文'])
        self.assertEqual([task['done'] for task in restored], [False, True])
        self.assertEqual(preview_items(restored), '[ ] Test\n[x] 写论文')

    def test_invalid_and_duplicate_ids(self):
        self.assertEqual(parse_items('invalid!'), [])
        self.assertEqual(parse_items('{"items":false}'), [])
        items = parse_items('{"items":[{"id":"same","text":"a"},{"id":"same","text":"b"}]}')
        self.assertEqual(len(items), 2)
        self.assertNotEqual(items[0]['id'], items[1]['id'])

    def test_existing_database_additive_migration(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, 'notes.db')
            connection = sqlite3.connect(path)
            connection.execute(
                "CREATE TABLE notes (id TEXT PRIMARY KEY, title TEXT NOT NULL, "
                "content TEXT NOT NULL, color TEXT NOT NULL, "
                "created_at TEXT NOT NULL, updated_at TEXT NOT NULL, trashed_at TEXT)"
            )
            connection.execute(
                "INSERT INTO notes VALUES ('legacy', '老便签', '', 'blue', "
                "'2026-10-01', '2026-10-01', NULL)"
            )
            connection.commit()
            connection.close()

            store = NoteStore(db_path=path)
            original = store.get_note('legacy')
            self.assertEqual(original.kind, 'note')
            self.assertEqual(original.title, '老便签')
            plan = store.create_note(
                title='周计划',
                content=serialize_items([new_item('撰写摘要')]),
                kind='plan',
            )
            self.assertEqual(store.get_note(plan.id).kind, 'plan')
            self.assertIn('撰写摘要', store.get_note(plan.id).preview_text)
            self.assertEqual(len(store.get_all_notes()), 2)
            store.update_note(plan.id, content=serialize_items([new_item('提交论文')]))
            self.assertIn('提交论文', store.get_note(plan.id).preview_text)
            store.close()

            reopened = NoteStore(db_path=path)
            self.assertEqual(reopened.get_note('legacy').kind, 'note')
            self.assertEqual(reopened.get_note(plan.id).kind, 'plan')
            reopened.close()


if __name__ == '__main__':
    unittest.main()
