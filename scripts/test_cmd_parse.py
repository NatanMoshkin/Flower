"""Port of the OLD inline CMD parse vs the NEW ParseCmd method, run against
the frames the panel can actually receive on the wire.

IEC semantics used:
  LEN(s)          -> len(s)
  MID(IN, L, P)   -> L characters of IN starting at the 1-based position P
  FIND(IN1, IN2)  -> 1-based position of IN2 in IN1, 0 if absent
  STRING_TO_INT   -> leading-integer parse, 0 on failure
"""


def MID(s, L, P):
    if L < 0 or P < 1:
        return ""
    return s[P - 1:P - 1 + L]


def FIND(hay, needle):
    return hay.find(needle) + 1


def STRING_TO_INT(s):
    out, i = "", 0
    while i < len(s) and (s[i] in "+-" and i == 0 or s[i].isdigit()):
        out += s[i]
        i += 1
    try:
        return int(out)
    except ValueError:
        return 0


def old_parse(rx, nRobotCmd):
    """FIND(sRxMsg,'CMD:') = 1 AND LEN > 4  ->  MID(sRxMsg, LEN-4, 5)"""
    if FIND(rx, "CMD:") == 1 and len(rx) > 4:
        nRobotCmd = STRING_TO_INT(MID(rx, len(rx) - 4, 5))
    return nRobotCmd


def new_parse(rx, nRobotCmd):
    """Last 'CMD:' occurrence, exactly one validated digit."""
    nLast = 0
    for i in range(1, len(rx) - 4 + 1):          # FOR i := 1 TO LEN(sRxMsg) - 4
        if MID(rx, 4, i) == "CMD:":
            nLast = i
    if nLast > 0:
        ch = ord(rx[nLast + 3])                  # 0-based index nLast+3
        if 0x30 <= ch <= 0x39:
            nRobotCmd = ch - 0x30
    return nRobotCmd


CASES = [
    # (frame,               prior nRobotCmd, expected nRobotCmd, note)
    ("CMD:1",                0, 1, "plain start command"),
    ("CMD:0",                1, 0, "robot withdraws the command"),
    ("CMD:2",                0, 2, "reset error"),
    ("CMD:1\n",              0, 1, "trailing newline"),
    ("CMD:1 ",               0, 1, "trailing space"),
    ("CMD:0CMD:1",           0, 1, "coalesced replies, newest wins"),
    ("CMD:1CMD:0",           1, 0, "coalesced replies, newest wins"),
    ("OK: SET STATE",        0, 0, "stale robot Lua reply - must not clobber"),
    ("OK: SET J_SPEED",      1, 1, "param ACK must not clobber pending cmd"),
    ("SYNC:J_SPEED=10,L_SPEED=10", 1, 1, "SYNC must not clobber"),
    ("CMD:",                 1, 1, "truncated frame - leave field alone"),
    ("CMD",                  1, 1, "shorter than the tag"),
    ("",                     1, 1, "empty receive"),
]

hdr = f"{'frame':<30} {'expect':>6} {'old':>6} {'new':>6}   note"
print(hdr)
print("-" * len(hdr))
old_bad = new_bad = 0
for frame, prior, expect, note in CASES:
    o = old_parse(frame, prior)
    n = new_parse(frame, prior)
    old_bad += o != expect
    new_bad += n != expect
    flag = lambda v: f"{v}{'' if v == expect else ' X'}"
    print(f"{frame!r:<30} {expect:>6} {flag(o):>6} {flag(n):>6}   {note}")

print()
print(f"old parse: {old_bad}/{len(CASES)} wrong")
print(f"new parse: {new_bad}/{len(CASES)} wrong")
raise SystemExit(1 if new_bad else 0)
