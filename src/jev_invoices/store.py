"""Every record goes to SQLite and to out/<id>.json, so results survive the process."""

import sqlite3
from pathlib import Path

from .models import InvoiceRecord


class Store:
    def __init__(self, db_path: Path, out_dir: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        out_dir.mkdir(parents=True, exist_ok=True)
        self._out_dir = out_dir
        self._db = sqlite3.connect(db_path, check_same_thread=False)
        with self._db:
            self._db.execute(
                "CREATE TABLE IF NOT EXISTS invoices ("
                "id TEXT PRIMARY KEY, kind TEXT NOT NULL, created_at TEXT NOT NULL, record TEXT NOT NULL)"
            )

    def save(self, record: InvoiceRecord) -> None:
        data = record.model_dump_json(indent=2)
        with self._db:
            self._db.execute(
                "INSERT INTO invoices (id, kind, created_at, record) VALUES (?, ?, ?, ?)",
                (record.id, record.kind, record.created_at.isoformat(), data),
            )
        (self._out_dir / f"{record.id}.json").write_text(data, encoding="utf-8")

    def get(self, record_id: str) -> InvoiceRecord | None:
        row = self._db.execute("SELECT record FROM invoices WHERE id = ?", (record_id,)).fetchone()
        return None if row is None else InvoiceRecord.model_validate_json(row[0])

    def recent(self, limit: int = 50) -> list[InvoiceRecord]:
        rows = self._db.execute(
            "SELECT record FROM invoices ORDER BY created_at DESC, rowid DESC LIMIT ?", (limit,)
        ).fetchall()
        return [InvoiceRecord.model_validate_json(row[0]) for row in rows]
