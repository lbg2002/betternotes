# SPDX-License-Identifier: GPL-3.0-or-later
import os
import tempfile
import unittest
from betternotes.note_store import NoteStore
from betternotes.backup import make_archive, restore_archive
from betternotes.plan import new_item, serialize_items, parse_items


class LocalBackupTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.original = NoteStore(db_path=os.path.join(self.folder.name, 'orig.db'))
        self.other = NoteStore(db_path=os.path.join(self.folder.name, 'dest.db'))

    def tearDown(self):
        self.original.close()
        self.other.close()
        self.folder.cleanup()

    def test_restore_with_tags_and_plans(self):
        plan = self.original.create_note(
            title='Research tasks', kind='plan', color='blue',
            content=serialize_items([new_item('submit', due='2026-10-15')])
        )
        self.original.add_tag_to_note(plan.id, 'Academic')
        archive = make_archive(self.original)
        self.assertEqual(restore_archive(self.other, archive), 1)
        restored = self.other.get_note(plan.id)
        self.assertEqual(restored.kind, 'plan')
        self.assertEqual(restored.tags, ['Academic'])
        self.assertEqual(parse_items(restored.content)[0]['due'], '2026-10-15')

    def test_import_is_nondestructive_and_idempotent(self):
        note = self.original.create_note(title='old', color='red')
        self.other.create_note(title='separate')
        archive = make_archive(self.original)
        self.assertEqual(restore_archive(self.other, archive), 1)
        self.other.update_note(note.id, title='changed locally')
        self.assertEqual(restore_archive(self.other, archive), 0)
        self.assertEqual(self.other.get_note(note.id).title, 'changed locally')
        self.assertEqual(len(self.other.get_all_notes()), 2)

    def test_invalid_record_never_writes_partial_notes(self):
        self.original.create_note(title='okay')
        archive = make_archive(self.original)
        archive['notes'].append(dict(archive['notes'][0], id='invalid',
                                     color='not-a-real-color'))
        with self.assertRaises(ValueError):
            restore_archive(self.other, archive)
        self.assertEqual(self.other.get_all_notes(), [])

    def test_legacy_plan_json_keeps_old_items(self):
        items = parse_items('{"items":[{"id":"one","text":"legacy","done":true}]}')
        self.assertEqual(items[0]['due'], '')


if __name__ == '__main__':
    unittest.main()
