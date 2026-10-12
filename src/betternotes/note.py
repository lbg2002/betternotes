# SPDX-License-Identifier: GPL-3.0-or-later

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Note:
    id: str
    title: str
    content: str  # JSON-serialized rich text
    color: str
    created_at: str
    updated_at: str
    trashed_at: Optional[str] = None
    tags: list[str] = field(default_factory=list)
    kind: str = 'note'

    @property
    def is_trashed(self) -> bool:
        return self.trashed_at is not None

    @property
    def preview_text(self) -> str:
        """Extract plain text preview from rich-text JSON content."""
        if self.kind == 'plan':
            from betternotes.plan import parse_items, preview_items
            return preview_items(parse_items(self.content))[:200]
        if not self.content:
            return ''
        try:
            import json
            data = json.loads(self.content)
            lines = []
            for block in data.get('blocks', []):
                text = ''.join(run.get('text', '') for run in block.get('runs', []))
                lines.append(text)
            return '\n'.join(lines)[:200]
        except (json.JSONDecodeError, TypeError, KeyError):
            return self.content[:200]


@dataclass
class Tag:
    id: str
    name: str
    note_count: int = 0
