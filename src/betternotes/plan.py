# SPDX-License-Identifier: GPL-3.0-or-later
"""JSON checklist persistence. No new runtime dependencies or database table."""
import json
from datetime import date
from uuid import uuid4


def new_item(text='', done=False, due=''):
    return {'id': str(uuid4()), 'text': text, 'done': bool(done), 'due': due}


def valid_due(value):
    if not isinstance(value, str) or not value:
        return ''
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        return ''


def parse_items(content):
    if not content:
        return []
    try:
        payload = json.loads(content)
    except (ValueError, TypeError):
        return []
    if not isinstance(payload, dict) or not isinstance(payload.get('items'), list):
        return []
    result = []
    ids = set()
    for raw in payload['items']:
        if not isinstance(raw, dict):
            continue
        item_id = str(raw.get('id') or uuid4())
        if item_id in ids:
            item_id = str(uuid4())
        ids.add(item_id)
        result.append({
            'id': item_id,
            'text': str(raw.get('text', '')),
            'done': bool(raw.get('done', False)),
            'due': valid_due(raw.get('due', '')),
        })
    return result


def serialize_items(items):
    return json.dumps({'items': items}, ensure_ascii=False, separators=(',', ':'))


def preview_items(items):
    return '\n'.join(('[x] ' if i['done'] else '[ ] ') + i['text']
                     for i in items)
