"""
Retention policy for the daily CSV logs.

Two independent caps:
  1) Age  — delete files older than `retention_days`.
  2) Size — delete oldest files while total exceeds `retention_mb`.

Beckhoff IPCs typically ship with modest SSDs, so an unbounded log dir
would eventually fill the system drive. This module keeps the /logs
tree bounded without any external service (systemd timer, cron, etc.).

Designed to run BOTH at bridge startup (initial sweep) AND periodically
from a background thread — see robot_bridge.start_periodic_retention.
"""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

log = logging.getLogger(__name__)


def run_retention(dir_path: Path, retention_days: int, retention_mb: int) -> None:
    """Enforce both caps once, in that order (age first, then size)."""
    dir_path = Path(dir_path)
    if not dir_path.is_dir():
        return

    cutoff_s = time.time() - retention_days * 86400
    files = sorted(dir_path.glob("*.csv"), key=lambda p: p.stat().st_mtime)

    # ----- age-based deletion -----
    survivors = []
    for f in files:
        try:
            mtime = f.stat().st_mtime
        except FileNotFoundError:
            continue
        if mtime < cutoff_s:
            log.info("retention: deleting %s (older than %d days)", f.name, retention_days)
            f.unlink(missing_ok=True)
        else:
            survivors.append(f)

    # ----- size-based deletion -----
    limit_bytes = retention_mb * 1024 * 1024
    total = sum(f.stat().st_size for f in survivors if f.exists())
    # Keep at least one file (usually today's — never delete the file we're
    # actively writing into).
    while total > limit_bytes and len(survivors) > 1:
        victim = survivors.pop(0)
        try:
            size = victim.stat().st_size
        except FileNotFoundError:
            continue
        log.info("retention: deleting %s (total > %d MB)", victim.name, retention_mb)
        victim.unlink(missing_ok=True)
        total -= size


def start_periodic_retention(
    dir_path: Path,
    retention_days: int,
    retention_mb: int,
    interval_s: float = 3600.0,
) -> threading.Event:
    """Kick off a daemon thread that reruns run_retention every `interval_s`.
    Returns an Event; set() it to stop the thread."""
    stop_flag = threading.Event()

    def _loop():
        # Run once immediately on startup, then wait interval_s between sweeps
        while not stop_flag.is_set():
            try:
                run_retention(dir_path, retention_days, retention_mb)
            except Exception:  # noqa: BLE001 — swallow so the thread never dies silently
                log.exception("retention: sweep failed")
            stop_flag.wait(interval_s)

    t = threading.Thread(target=_loop, name="retention", daemon=True)
    t.start()
    return stop_flag
