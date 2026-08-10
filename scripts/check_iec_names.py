"""Catch declared identifiers that shadow an IEC 61131-3 standard name.

    python scripts/check_iec_names.py

WHY THIS EXISTS. IEC identifiers are CASE-INSENSITIVE, so a variable called `sIn`
*is* `SIN`, the standard trigonometric function. Declaring one makes the whole POU
fail to parse, and the compiler's diagnosis points at the call sites rather than at
the declaration:

    'SIN' needs exactly '1' Operands
    '(' expected instead of ':='
    Unexpected Token 'sIn' found

That cost a build cycle on 2026-08-10 in FB_LogCsvWriter, whose Csv() method took
a parameter named `sIn`. It is the same trap that stopped the Logs VISU page being
named `Log` (LOG is a standard function) -- CLAUDE.md has documented that one since
2026-07-27, but its list omitted the trig family.

A plain-text grep for these names is useless because they appear legitimately all
over the code as *calls*. This only looks at DECLARATIONS -- the left-hand side of
`name : TYPE` inside a Declaration block, with comments stripped -- so a call to
LEN() or MID() is ignored while a variable *named* LEN is reported.

Exit 0 = clean, 1 = at least one collision.
"""
from __future__ import annotations

import glob
import io
import re
import sys

# IEC 61131-3 standard functions, function blocks and keywords. The trig family is
# the part that is easy to forget and the part that actually bit.
RESERVED = set("""
ABS SQRT LN LOG EXP SIN COS TAN ASIN ACOS ATAN ATAN2 EXPT
ADD MUL SUB DIV MOD MOVE
SHL SHR ROL ROR AND OR XOR NOT
SEL MAX MIN LIMIT MUX
GT GE EQ LE LT NE
LEN LEFT RIGHT MID CONCAT INSERT DELETE REPLACE FIND
TRUNC ROUND SIZEOF ADR BITADR
TON TOF TP CTU CTD CTUD RS SR R_TRIG F_TRIG SEMA
BOOL BYTE WORD DWORD LWORD
SINT INT DINT LINT USINT UINT UDINT ULINT REAL LREAL
TIME LTIME DATE TOD DT TIME_OF_DAY DATE_AND_TIME
STRING WSTRING CHAR WCHAR
POINTER REFERENCE ARRAY STRUCT UNION TYPE
VAR VAR_INPUT VAR_OUTPUT VAR_IN_OUT VAR_GLOBAL VAR_TEMP VAR_STAT
END_VAR CONSTANT PERSISTENT RETAIN AT
IF THEN ELSE ELSIF END_IF CASE OF FOR TO BY DO WHILE REPEAT UNTIL
END_FOR END_WHILE END_REPEAT END_CASE EXIT CONTINUE RETURN JMP
FUNCTION END_FUNCTION FUNCTION_BLOCK END_FUNCTION_BLOCK
PROGRAM END_PROGRAM METHOD END_METHOD PROPERTY END_PROPERTY
ACTION END_ACTION INTERFACE END_INTERFACE
TRUE FALSE NULL THIS SUPER EXTENDS IMPLEMENTS ABSTRACT FINAL
""".split())

# "name : TYPE" or "a, b, c : TYPE" at the start of a line inside a Declaration.
DECL = re.compile(r"^\s*([A-Za-z_][\w, ]*?)\s*:\s*[A-Za-z_]", re.M)


def strip_comments(s: str) -> str:
    s = re.sub(r"\(\*.*?\*\)", " ", s, flags=re.S)
    return re.sub(r"//[^\n]*", " ", s)


def main() -> int:
    files = sorted(glob.glob("Panel_PLC_HMI/**/PLC1/**/*.TcPOU", recursive=True)
                   + glob.glob("Panel_PLC_HMI/**/PLC1/**/*.TcDUT", recursive=True)
                   + glob.glob("Panel_PLC_HMI/**/PLC1/**/*.TcGVL", recursive=True))
    if not files:
        print("no PLC source found -- run this from the repo root")
        return 1

    hits: list[tuple[str, str, str]] = []
    n_decl = 0
    for path in files:
        try:
            txt = io.open(path, encoding="utf-8").read()
        except OSError:
            continue
        for blk in re.findall(r"<Declaration><!\[CDATA\[(.*?)\]\]></Declaration>",
                              txt, re.S):
            for m in DECL.finditer(strip_comments(blk)):
                for name in (x.strip() for x in m.group(1).split(",")):
                    if not name:
                        continue
                    n_decl += 1
                    if name.upper() in RESERVED:
                        hits.append((path, name, name.upper()))

    # Object names are identifiers too -- a POU/DUT/GVL called Log would not build.
    for path in files:
        try:
            txt = io.open(path, encoding="utf-8").read()
        except OSError:
            continue
        for m in re.finditer(r'<(?:POU|DUT|GVL|Method|Property) Name="(\w+)"', txt):
            if m.group(1).upper() in RESERVED:
                hits.append((path, m.group(1), m.group(1).upper()))

    print(f"checked {n_decl} declarations across {len(files)} files")
    if hits:
        print(f"\n{len(hits)} COLLISION(S) -- these will not compile:")
        for path, name, res in hits:
            print(f"  {path}")
            print(f"      {name!r} is the IEC standard name {res}")
        print("\nRename them. The compiler blames the CALL SITES, not the")
        print("declaration, so this is much cheaper to find here.")
        return 1
    print("clean -- no declared identifier or object name shadows an IEC standard name")
    return 0


if __name__ == "__main__":
    sys.exit(main())
