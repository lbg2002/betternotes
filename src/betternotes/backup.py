# SPDX-License-Identifier: GPL-3.0-or-later
"""Local JSON backup: additive restore, never overwrite existing note IDs."""
from datetime import datetime
from uuid import uuid4

ARCHIVE_FORMAT = 'pinplan-notes'
ARCHIVE_VERSION = 1


def make_archive(store):
    notes = store.get_all_notes(include_trashed=True)
    return {
        'format': ARCHIVE_FORMAT,
        'version': ARCHIVE_VERSION,
        'exported_at': datetime.now().isoformat(),
        'notes': [{
            'id': note.id,
            'title': note.title,
            'content': note.content,
            'color': note.color,
            'kind': note.kind,
            'created_at': note.created_at,
            'updated_at': note.updated_at,
            'trashed_at': note.trashed_at,
            'tags': note.tags,
        } for note in notes],
    }


def restore_archive(store, archive):
    """Merge a validated backup atomically. Existing note IDs are skipped."""
    if not isinstance(archive, dict) or archive.get('format') != ARCHIVE_FORMAT:
        raise ValueError('Not a PinPlan backup')
    if archive.get('version') != ARCHIVE_VERSION:
        raise ValueError('Unsupported backup version')
    records = archive.get('notes')
    if not isinstance(records, list) or len(records) > 10000:
        raise ValueError('Invalid backup note list')
    validated = []
    seen = set()
    for raw in records:
        if not isinstance(raw, dict):
            raise ValueError('Malformed note record')
        uid = raw.get('id')
        if not isinstance(uid, str) or not (0 < len(uid) <= 100) or uid in seen:
            raise ValueError('Missing or duplicate note ID')
        seen.add(uid)
        title, content = raw.get('title'), raw.get('content')
        if not isinstance(title, str) or len(title) > 10000:
            raise ValueError('Invalid note title')
        if not isinstance(content, str) or len(content) > 2_000_000:
            raise ValueError('Invalid note content')
        color = raw.get('color', 'yellow')
        kind = raw.get('kind', 'note')
        if color not in ('yellow','blue','green','pink','orange','purple','red','teal'):
            raise ValueError('Unknown note color')
        if kind not in ('note', 'plan'):
            raise ValueError('Unknown note type')
        tags = raw.get('tags', [])
        if not isinstance(tags, list) or len(tags) > 100 or any(
            not isinstance(tag, str) or len(tag) > 255 for tag in tags
        ):
            raise ValueError('Invalid tags')
        for field in ('created_at', 'updated_at'):
            if not isinstance(raw.get(field), str):
                raise ValueError('Invalid timestamp')
        trashed = raw.get('trashed_at')
        if trashed is not None and not isinstance(trashed, str):
            raise ValueError('Invalid trash timestamp')
        validated.append((uid, title, content, color, kind, raw['created_at'],
                          raw['updated_at'], trashed, tags))
    connection = store._db
    inserted = 0
    try:
        connection.execute('BEGIN IMMEDIATE')
        for uid, title, content, color, kind, created, updated, trashed, tags in validated:
            cursor = connection.execute(
                'INSERT OR IGNORE INTO notes '
                '(id, title, content, color, kind, created_at, updated_at, trashed_at) '
                'VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                (uid, title, content, color, kind, created, updated, trashed)
            )
            if cursor.rowcount == 0:
                continue
            inserted += 1
            for tag in set(tags):
                connection.execute('INSERT OR IGNORE INTO tags (id,name) VALUES (?,?)',
                                   (str(uuid4()), tag))
                connection.execute(
                    'INSERT OR IGNORE INTO note_tags (note_id,tag_id) '
                    'SELECT ?, id FROM tags WHERE name=?', (uid, tag)
                )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    return inserted
