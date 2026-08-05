"""Verify FlowerPyHmi's ADS symbol contract against the Panel PLC source.

FlowerPyHmi lives in a SEPARATE git repo outside this one, so nothing keeps
the two in step automatically. This resolves every symbol FlowerPyHmi polls
or writes against the panel PLC's actual GVL + DUT declarations and reports
anything that no longer exists (or is exposed without the HMI pragma).

Run:  python scripts/check_pyhmi_contract.py
Exit: 0 = contract intact, 1 = drift found.
"""

from __future__ import annotations

import pathlib
import re
import sys

PLC = pathlib.Path(__file__).resolve().parents[1] / (
    "Panel_PLC_HMI/167_01_Saad_PLC/167_01_Saad_PLC/PLC1"
)
PYHMI = pathlib.Path(__file__).resolve().parents[2] / "FlowerPyHmi"


# --------------------------------------------------------------- PLC parsing
def _decl(path):
    """Pull the CDATA declaration text out of a TwinCAT XML object."""
    m = re.search(r"<Declaration><!\[CDATA\[(.*?)\]\]></Declaration>",
                  path.read_text(encoding="utf-8", errors="replace"), re.S)
    return m.group(1) if m else ""


def _members(body):
    """name -> type, for the `name : TYPE;` lines in a STRUCT / VAR_GLOBAL."""
    out = {}
    for line in body.splitlines():
        line = re.sub(r"//.*$", "", line)
        line = re.sub(r"\(\*.*?\*\)", "", line)
        m = re.match(r"\s*([A-Za-z_]\w*)\s*:\s*([^;:=]+?)\s*(?::=.*)?;", line)
        if m:
            out[m.group(1)] = m.group(2).strip()
    return out


def load_plc():
    structs, gvls = {}, {}
    for p in (PLC / "DUTs").glob("*.TcDUT"):
        d = _decl(p)
        m = re.search(r"TYPE\s+(\w+)\s*:\s*STRUCT(.*?)END_STRUCT", d, re.S)
        if m:
            structs[m.group(1)] = _members(m.group(2))
        else:                                    # enum / alias -> scalar leaf
            m = re.search(r"TYPE\s+(\w+)\s*:", d)
            if m:
                structs[m.group(1)] = None
    for p in (PLC / "GVLs").glob("*.TcGVL"):
        d = _decl(p)
        m = re.search(r"VAR_GLOBAL(.*?)END_VAR", d, re.S)
        if m:
            gvls[p.stem] = {
                "vars": _members(m.group(1)),
                "hmi": "TcHmiSymbol.AddSymbol" in d,
            }
    return structs, gvls


BASE = re.compile(
    r"^(BOOL|BYTE|WORD|DWORD|U?[SLD]?INT|INT|REAL|LREAL|TIME|STRING(\(\d+\))?"
    r"|T_\w+|E_\w+)$", re.I)


def resolve(symbol, structs, gvls):
    """Walk a dotted symbol path. Returns None if OK, else an error string."""
    parts = symbol.split(".")
    gvl = parts[0]
    if gvl not in gvls:
        return f"no such GVL '{gvl}'"
    if not gvls[gvl]["hmi"]:
        return f"GVL '{gvl}' lacks the TcHmiSymbol.AddSymbol pragma"

    scope, path = gvls[gvl]["vars"], gvl
    for part in parts[1:]:
        name = re.sub(r"\[.*?\]$", "", part)
        if scope is None:
            return f"'{path}' is a scalar; cannot contain '.{name}'"
        if name not in scope:
            return f"'{path}' has no member '{name}'"
        typ = scope[name]
        path = f"{path}.{name}"
        arr = re.match(r"ARRAY\s*\[.*?\]\s*OF\s+(\w+)", typ, re.I)
        if arr:
            typ = arr.group(1)
        scope = None if BASE.match(typ) else structs.get(typ, "MISSING")
        if scope == "MISSING":
            return f"'{path}' is type '{typ}', which no DUT declares"
    return None


# ------------------------------------------------- FlowerPyHmi symbol set
def pyhmi_symbols():
    sys.path.insert(0, str(PYHMI))
    from flower_py_hmi import master_auto as ma, piston_auto as pa
    from flower_py_hmi import piston as pi, plc_log as pl, robot as rb

    read, write = [], []
    read += [f"{ma.MASTER_AUTO_ROOT}.{f.name}" for f in ma.MASTER_AUTO_READ_FIELDS]
    read += [f"{ma.MASTER_AUTO_CFG_ROOT}.{f.name}" for f in ma.MASTER_AUTO_CFG_FIELDS]
    read += [f"{rb.ROBOT_ROOT}.{f.name}" for f in rb.ROBOT_READ_FIELDS]
    read += [rb.robot_param_symbol(f.name) for f in rb.ROBOT_STATE_FIELDS]
    read += [rb.robot_param_symbol(f.name) for f in rb.ROBOT_PARAM_FIELDS]
    read += [ma.PLATE_SEN_L_SYMBOL, ma.PLATE_SEN_R_SYMBOL]
    read += [pl.LOG_ENABLED_SYMBOL, pl.LOG_DEBUG_SYMBOL, pl.LOG_WRITE_IDX_SYMBOL]
    for p in pi.PISTONS:
        read += [p.field_symbol(f.name) for f in pi.PISTON_FIELDS if f.readable]
    for a in pa.AUTO_PISTONS:
        read += [a.field_symbol(f.name) for f in pa.AUTO_READ_FIELDS]
        read += [a.cfg_symbol(f.name) for f in pa.AUTO_CFG_FIELDS]

    # Write-only symbols never appear in the poll cycle.
    write += [rb.robot_param_symbol(f) for f in rb.ROBOT_REQUEST_FLAGS.values()]
    write += [rb.robot_param_symbol(f) for f in ("bSetParam", "sSetName", "nSetVal")]

    # Master-auto commands and per-step sim flags. These were MISSING until
    # 2026-08-05, and the omission mattered: they are this app's entire write
    # path to the master cycle, so a renamed or retyped one of them is exactly
    # the failure this script exists to catch. Nothing polls them, so nothing
    # else would notice -- a sim button would just silently stop working, and
    # pytest cannot see it because the mock has no PLC symbols at all.
    write += [ma.master_auto_symbol(f) for f in
              ("bStart", "bStop", "bReset",
               ma.SIM_START_ASSEMBLY_FIELD, ma.START_CYCLE_FIELD)]
    write += [ma.master_auto_symbol(f"bSimStep_{k}") for k, _ in ma.SIM_STEPS]
    return read, write


def main():
    structs, gvls = load_plc()
    read, write = pyhmi_symbols()
    print(f"PLC: {len(structs)} DUTs, {len(gvls)} GVLs "
          f"({sum(g['hmi'] for g in gvls.values())} HMI-exposed)")
    print(f"FlowerPyHmi: {len(read)} polled + {len(write)} write-only symbols\n")

    bad = []
    for kind, syms in (("READ", read), ("WRITE", write)):
        for s in syms:
            err = resolve(s, structs, gvls)
            if err:
                bad.append((kind, s, err))

    if bad:
        print(f"DRIFT — {len(bad)} symbol(s) do not resolve:\n")
        for kind, s, err in bad:
            print(f"  [{kind}] {s}\n         {err}")
        return 1
    print(f"OK — all {len(read) + len(write)} symbols resolve against the panel PLC.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
