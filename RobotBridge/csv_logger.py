"""
Daily CSV logging handler.

A `logging.Handler` that writes records to  logs/YYYY-MM-DD.csv
with one row per event, columns:  timestamp,severity,source,message

Rolls over automatically at midnight (checked on every emit — cheap).
The `source` column comes from the logger name, which makes it easy to
route both PLC-side events (log_pump uses logger name "plc.<sSource>")
and Python-side bridge events (via `logging.getLogger(__name__)`)
through the same file.
"""
from __future__ import annotations

import csv
import logging
import time
from pathlib import Path


class DailyCsvHandler(logging.Handler):
    """Append log records to `<dir>/<YYYY-MM-DD>.csv` — new file each day."""

    def __init__(self, base_dir: Path):
        super().__init__()
        self._dir = Path(base_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._current_date: str | None = None
        self._file = None
        self._writer = None

    def emit(self, record: logging.LogRecord) -> None:
        try:
            today = time.strftime("%Y-%m-%d", time.localtime(record.created))
            if today != self._current_date:
                self._rotate(today)
            self._writer.writerow([
                self._format_ts(record),
                record.levelname,
                record.name,
                record.getMessage(),
            ])
            self._file.flush()
        except Exception:
            self.handleError(record)

    @staticmethod
    def _format_ts(record: logging.LogRecord) -> str:
        base = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(record.created))
        return f"{base}.{int(record.msecs):03d}"

    def _rotate(self, today: str) -> None:
        if self._file is not None:
            self._file.close()
        path = self._dir / f"{today}.csv"
        already_exists = path.exists() and path.stat().st_size > 0
        self._file = path.open("a", newline="", encoding="utf-8")
        self._writer = csv.writer(self._file)
        if not already_exists:
            # Header row on brand-new file so a spreadsheet-open works out of the box.
            self._writer.writerow(["timestamp", "severity", "source", "message"])
        self._current_date = today

    def close(self) -> None:
        try:
            if self._file is not None:
                self._file.close()
                self._file = None
        finally:
            super().close()
