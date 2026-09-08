"""Persisted imported collection (CSV/JSON) under the user data directory."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import List

from core.collection_import import row_to_record, rows_from_records
from core.models import SOURCE_LOCAL, ReleaseRow
from core.paths import migrate_user_file

LOCAL_COLLECTION_FILE = migrate_user_file("local_collection.json")


class LocalCollectionStore:
    """Load and save an offline collection as JSON."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or LOCAL_COLLECTION_FILE
        self._data: dict = {
            "version": 1,
            "source": SOURCE_LOCAL,
            "imported_from": None,
            "imported_at": None,
            "rows": [],
        }
        self._load()

    def _load(self) -> None:
        try:
            if self.path.exists():
                with self.path.open("r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict) and loaded.get("version") == 1:
                    self._data.update(loaded)
        except Exception:
            pass

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    def has_rows(self) -> bool:
        return bool(self._data.get("rows"))

    def count(self) -> int:
        return len(self._data.get("rows") or [])

    def imported_from(self) -> str | None:
        return self._data.get("imported_from")

    def load_rows(self) -> List[ReleaseRow]:
        records = self._data.get("rows") or []
        if not records:
            return []
        return rows_from_records(records, source=SOURCE_LOCAL)

    def save_rows(self, rows: List[ReleaseRow], *, imported_from: str | None = None) -> None:
        self._data = {
            "version": 1,
            "source": SOURCE_LOCAL,
            "imported_from": imported_from or self._data.get("imported_from"),
            "imported_at": time.time(),
            "rows": [row_to_record(r) for r in rows],
        }
        self._save()

    def clear(self) -> None:
        self._data = {
            "version": 1,
            "source": SOURCE_LOCAL,
            "imported_from": None,
            "imported_at": None,
            "rows": [],
        }
        self._save()
        if self.path.exists():
            try:
                self.path.unlink()
            except OSError:
                pass
