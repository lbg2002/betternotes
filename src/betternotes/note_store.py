# SPDX-License-Identifier: GPL-3.0-or-later

import os
import sqlite3
import uuid
from datetime import datetime, timedelta

from gi.repository import GLib

from betternotes.note import Note, Tag
from betternotes.constants import TRASH_RETENTION_DAYS


class NoteStore:

    def __init__(self, db_path=None):
        if db_path is None:
            data_dir = os.path.join(GLib.get_user_data_dir(), 'betternotes')
            os.makedirs(data_dir, exist_ok=True)
            db_path = os.path.join(data_dir, 'notes.db')

        self._db = sqlite3.connect(db_path)
        self._db.execute('PRAGMA journal_mode=WAL')
        self._db.execute('PRAGMA foreign_keys=ON')
        self._db.row_factory = sqlite3.Row
        self._create_tables()
        self._purge_old_trash()

    def _create_tables(self):
        self._db.executescript('''
            CREATE TABLE IF NOT EXISTS notes (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL DEFAULT '',
                content TEXT NOT NULL DEFAULT '',
                color TEXT NOT NULL DEFAULT 'yellow',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                trashed_at TEXT,
                kind TEXT NOT NULL DEFAULT 'note'
            );

            CREATE TABLE IF NOT EXISTS tags (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL UNIQUE
            );

            CREATE TABLE IF NOT EXISTS note_tags (
                note_id TEXT NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
                tag_id TEXT NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
                PRIMARY KEY (note_id, tag_id)
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(
                title, content, content=notes, content_rowid=rowid
            );

            CREATE TRIGGER IF NOT EXISTS notes_ai AFTER INSERT ON notes BEGIN
                INSERT INTO notes_fts(rowid, title, content)
                VALUES (new.rowid, new.title, new.content);
            END;

            CREATE TRIGGER IF NOT EXISTS notes_ad AFTER DELETE ON notes BEGIN
                INSERT INTO notes_fts(notes_fts, rowid, title, content)
                VALUES ('delete', old.rowid, old.title, old.content);
            END;

            CREATE TRIGGER IF NOT EXISTS notes_au AFTER UPDATE ON notes BEGIN
                INSERT INTO notes_fts(notes_fts, rowid, title, content)
                VALUES ('delete', old.rowid, old.title, old.content);
                INSERT INTO notes_fts(rowid, title, content)
                VALUES (new.rowid, new.title, new.content);
            END;
        ''')
        # Safe, additive migration for existing note databases.
        columns = {row[1] for row in self._db.execute('PRAGMA table_info(notes)')}
        if 'kind' not in columns:
            self._db.execute("ALTER TABLE notes ADD COLUMN kind TEXT NOT NULL DEFAULT 'note'")
        self._db.commit()

    # --- Notes CRUD ---

    def create_note(self, title='', content='', color='yellow', kind='note') -> Note:
        if kind not in ('note', 'plan'):
            raise ValueError('Unknown note kind')
        note_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        self._db.execute(
            'INSERT INTO notes (id, title, content, color, created_at, updated_at, kind) '
            'VALUES (?, ?, ?, ?, ?, ?, ?)',
            (note_id, title, content, color, now, now, kind),
        )
        self._db.commit()
        return Note(
            id=note_id, title=title, content=content, color=color,
            created_at=now, updated_at=now, kind=kind,
        )

    def get_note(self, note_id) -> Note | None:
        row = self._db.execute(
            'SELECT * FROM notes WHERE id = ?', (note_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_note(row)

    def get_all_notes(self, include_trashed=False) -> list[Note]:
        if include_trashed:
            rows = self._db.execute(
                'SELECT * FROM notes ORDER BY updated_at DESC'
            ).fetchall()
        else:
            rows = self._db.execute(
                'SELECT * FROM notes WHERE trashed_at IS NULL '
                'ORDER BY updated_at DESC'
            ).fetchall()
        return [self._row_to_note(row) for row in rows]

    def get_trashed_notes(self) -> list[Note]:
        rows = self._db.execute(
            'SELECT * FROM notes WHERE trashed_at IS NOT NULL '
            'ORDER BY trashed_at DESC'
        ).fetchall()
        return [self._row_to_note(row) for row in rows]

    def update_note(self, note_id, **fields):
        if not fields:
            return
        fields['updated_at'] = datetime.now().isoformat()
        set_clause = ', '.join(f'{k} = ?' for k in fields)
        values = list(fields.values()) + [note_id]
        self._db.execute(
            f'UPDATE notes SET {set_clause} WHERE id = ?', values
        )
        self._db.commit()

    def trash_note(self, note_id):
        now = datetime.now().isoformat()
        self._db.execute(
            'UPDATE notes SET trashed_at = ?, updated_at = ? WHERE id = ?',
            (now, now, note_id),
        )
        self._db.commit()

    def restore_note(self, note_id):
        now = datetime.now().isoformat()
        self._db.execute(
            'UPDATE notes SET trashed_at = NULL, updated_at = ? WHERE id = ?',
            (now, note_id),
        )
        self._db.commit()

    def delete_note(self, note_id):
        self._db.execute('DELETE FROM notes WHERE id = ?', (note_id,))
        self._db.commit()

    def trash_notes(self, note_ids):
        if not note_ids:
            return
        placeholders = ','.join('?' * len(note_ids))
        now = datetime.now().isoformat()
        self._db.execute(
            f'UPDATE notes SET trashed_at = ?, updated_at = ? '
            f'WHERE id IN ({placeholders})',
            [now, now] + list(note_ids),
        )
        self._db.commit()

    def restore_notes(self, note_ids):
        if not note_ids:
            return
        placeholders = ','.join('?' * len(note_ids))
        now = datetime.now().isoformat()
        self._db.execute(
            f'UPDATE notes SET trashed_at = NULL, updated_at = ? '
            f'WHERE id IN ({placeholders})',
            [now] + list(note_ids),
        )
        self._db.commit()

    def delete_notes(self, note_ids):
        if not note_ids:
            return
        placeholders = ','.join('?' * len(note_ids))
        self._db.execute(
            f'DELETE FROM notes WHERE id IN ({placeholders})',
            list(note_ids),
        )
        self._db.commit()

    def empty_trash(self):
        self._db.execute('DELETE FROM notes WHERE trashed_at IS NOT NULL')
        self._db.commit()

    def _purge_old_trash(self):
        cutoff = (datetime.now() - timedelta(days=TRASH_RETENTION_DAYS)).isoformat()
        self._db.execute(
            'DELETE FROM notes WHERE trashed_at IS NOT NULL AND trashed_at < ?',
            (cutoff,),
        )
        self._db.commit()

    # --- Search ---

    def search_notes(self, query) -> list[Note]:
        if not query or not query.strip():
            return self.get_all_notes()
        # Escape FTS5 special characters and add prefix matching
        safe_query = query.replace('"', '""')
        fts_query = f'"{safe_query}"*'
        rows = self._db.execute(
            'SELECT n.* FROM notes n '
            'JOIN notes_fts f ON n.rowid = f.rowid '
            'WHERE notes_fts MATCH ? AND n.trashed_at IS NULL '
            'ORDER BY rank',
            (fts_query,),
        ).fetchall()
        return [self._row_to_note(row) for row in rows]

    # --- Tags ---

    def create_tag(self, name) -> Tag:
        tag_id = str(uuid.uuid4())
        self._db.execute(
            'INSERT OR IGNORE INTO tags (id, name) VALUES (?, ?)',
            (tag_id, name),
        )
        self._db.commit()
        row = self._db.execute(
            'SELECT * FROM tags WHERE name = ?', (name,)
        ).fetchone()
        return Tag(id=row['id'], name=row['name'])

    def get_all_tags(self) -> list[Tag]:
        rows = self._db.execute(
            'SELECT t.*, COUNT(nt.note_id) as note_count '
            'FROM tags t '
            'LEFT JOIN note_tags nt ON t.id = nt.tag_id '
            'LEFT JOIN notes n ON nt.note_id = n.id AND n.trashed_at IS NULL '
            'GROUP BY t.id ORDER BY t.name'
        ).fetchall()
        return [Tag(id=r['id'], name=r['name'], note_count=r['note_count']) for r in rows]

    def add_tag_to_note(self, note_id, tag_name):
        tag = self.create_tag(tag_name)
        self._db.execute(
            'INSERT OR IGNORE INTO note_tags (note_id, tag_id) VALUES (?, ?)',
            (note_id, tag.id),
        )
        self._db.commit()

    def remove_tag_from_note(self, note_id, tag_name):
        self._db.execute(
            'DELETE FROM note_tags WHERE note_id = ? AND tag_id = '
            '(SELECT id FROM tags WHERE name = ?)',
            (note_id, tag_name),
        )
        self._db.commit()

    def get_tags_for_note(self, note_id) -> list[str]:
        rows = self._db.execute(
            'SELECT t.name FROM tags t '
            'JOIN note_tags nt ON t.id = nt.tag_id '
            'WHERE nt.note_id = ? ORDER BY t.name',
            (note_id,),
        ).fetchall()
        return [r['name'] for r in rows]

    def get_notes_by_tag(self, tag_name) -> list[Note]:
        rows = self._db.execute(
            'SELECT n.* FROM notes n '
            'JOIN note_tags nt ON n.id = nt.note_id '
            'JOIN tags t ON nt.tag_id = t.id '
            'WHERE t.name = ? AND n.trashed_at IS NULL '
            'ORDER BY n.updated_at DESC',
            (tag_name,),
        ).fetchall()
        return [self._row_to_note(row) for row in rows]

    def delete_tag(self, tag_name):
        self._db.execute('DELETE FROM tags WHERE name = ?', (tag_name,))
        self._db.commit()

    # --- Helpers ---

    def _row_to_note(self, row) -> Note:
        note = Note(
            id=row['id'],
            title=row['title'],
            content=row['content'],
            color=row['color'],
            created_at=row['created_at'],
            updated_at=row['updated_at'],
            trashed_at=row['trashed_at'],
            kind=row['kind'],
        )
        note.tags = self.get_tags_for_note(note.id)
        return note

    def close(self):
        self._db.close()
