"""
PLC-log ring-buffer pump.

Polls GVL_Log.nWriteIdx via ADS every `poll_ms`. When it has advanced,
drains the new slots and re-emits each entry via the standard `logging`
pipeline — the DailyCsvHandler picks them up and writes CSV rows.

Design notes
------------
- Ring is 256 entries deep. If the PLC writes > 256 events between polls,
  the earliest ones are overwritten. This module detects that (advance
  > RING_SIZE) and logs a synthetic WARNING row so the loss is visible.
- On startup, we jump `_last_idx` to `nWriteIdx - RING_SIZE` (or 0 if the
  ring hasn't wrapped yet). Result: the bridge sees the last ~256 events
  the PLC produced, even if it started long after the PLC did.
- One ADS read per field is used for clarity. At 500 ms polling with
  transition-only PLC logging, that's a few reads per second — well
  within ADS budget.
"""
from __future__ import annotations

import logging
import threading
from typing import Optional

import pyads

log = logging.getLogger("log_pump")

RING_SIZE = 256

# PLC E_LogSev value -> Python logging level
_SEVERITY_MAP = {
    0: logging.DEBUG,
    1: logging.INFO,
    2: logging.WARNING,
    3: logging.ERROR,
}


class PlcLogPump:
    """Background thread that drains GVL_Log into Python's `logging` pipeline."""

    def __init__(self, plc: pyads.Connection, poll_ms: int = 500):
        self._plc = plc
        self._poll_s = poll_ms / 1000.0
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._last_idx: int = 0

    def start(self) -> None:
        self._stop.clear()
        try:
            current = self._plc.read_by_name("GVL_Log.nWriteIdx", pyads.PLCTYPE_UDINT)
            # Skip anything older than the ring can still hold — we can't read
            # those slots anyway (they've been overwritten).
            self._last_idx = max(0, current - RING_SIZE)
            if current > 0:
                log.info(
                    "log_pump: PLC nWriteIdx=%d at start; draining last %d entries",
                    current, current - self._last_idx,
                )
        except Exception as e:  # noqa: BLE001
            log.warning("log_pump: initial read failed (%s); starting from 0", e)
            self._last_idx = 0

        self._thread = threading.Thread(target=self._loop, name="log_pump", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self._drain_once()
            except Exception:  # noqa: BLE001 — never let the thread die
                log.exception("log_pump: drain cycle failed")
            self._stop.wait(self._poll_s)

    # ---- internals ----------------------------------------------------

    def _drain_once(self) -> None:
        current = self._plc.read_by_name("GVL_Log.nWriteIdx", pyads.PLCTYPE_UDINT)
        if current == self._last_idx:
            return
        if current < self._last_idx:
            # PLC restarted (nWriteIdx reset to 0). Re-anchor and drain from there.
            log.info("log_pump: nWriteIdx went backwards (%d -> %d) — PLC restart? "
                     "Re-anchoring.", self._last_idx, current)
            self._last_idx = 0

        advance = current - self._last_idx
        if advance > RING_SIZE:
            lost = advance - RING_SIZE
            log.warning(
                "log_pump: ring overflow — PLC wrote %d entries between polls, "
                "%d oldest lost. Consider a shorter plc_ring_poll_ms.",
                advance, lost,
            )
            self._last_idx = current - RING_SIZE

        for idx in range(self._last_idx, current):
            slot = idx % RING_SIZE
            self._read_and_emit(slot)

        self._last_idx = current

    def _read_and_emit(self, slot: int) -> None:
        prefix = f"GVL_Log.aLog[{slot}]"
        try:
            sev_raw = self._plc.read_by_name(f"{prefix}.eSev", pyads.PLCTYPE_UINT)
            source  = self._plc.read_by_name(f"{prefix}.sSource", pyads.PLCTYPE_STRING)
            msg     = self._plc.read_by_name(f"{prefix}.sMsg", pyads.PLCTYPE_STRING)
        except Exception as e:  # noqa: BLE001
            log.warning("log_pump: failed to read ring slot %d: %s", slot, e)
            return

        level = _SEVERITY_MAP.get(sev_raw, logging.INFO)
        # Route to a per-source child logger so the CSV "source" column
        # naturally carries the PLC's sSource. "plc.<source>" prefix keeps
        # PLC events visually distinct from Python-side events.
        logger = logging.getLogger(f"plc.{source or 'anon'}")
        logger.log(level, msg)
