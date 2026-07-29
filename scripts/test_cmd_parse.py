"""Port of FB_RobotTcpClient.ParseCmd, plus the OLD inline parse it replaced,
run against the frames the panel can actually receive on the wire.

`parse_cmd` here is the single Python mirror of the ST method -- imported by
scripts/test_param_shadow_logic.py so the sequencer test and this one cannot
drift apart the way two hand-copied ports would.

IEC semantics used:
  LEN(s)          -> len(s)
  MID(IN, L, P)   -> L characters of IN starting at the 1-based position P
  FIND(IN1, IN2)  -> 1-based position of IN2 in IN1, 0 if absent
  STRING_TO_INT   -> leading-integer parse, 0 on failure

Run:  python scripts/test_cmd_parse.py
Exit: 0 = parse behaves as specified, 1 = drift found.
"""

NO_CMD = -1   # ParseCmd's "this reply carries no CMD frame" return


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


def parse_cmd(rx):
    """FB_RobotTcpClient.ParseCmd: value of the last 'CMD:<digit>' in rx, or
    NO_CMD (-1) when there is no usable frame. -1 rather than 0 because CMD:0
    (withdraw) is itself a valid command."""
    nLast = 0
    for i in range(1, len(rx) - 4 + 1):          # FOR i := 1 TO LEN(sRxMsg) - 4
        if MID(rx, 4, i) == "CMD:":
            nLast = i
    if nLast > 0:
        ch = ord(rx[nLast + 3])                  # 0-based index nLast+3
        if 0x30 <= ch <= 0x39:
            return ch - 0x30
    return NO_CMD


def consume(rx, nRobotCmd):
    """HandleReply's write rule: only overwrite the field when a frame was
    actually found, so an ACK or a SYNC cannot clobber a pending command."""
    cmd = parse_cmd(rx)
    return cmd if cmd >= 0 else nRobotCmd


def old_consume(rx, nRobotCmd):
    """The parse this replaced: anchored at position 1, and assuming the digit
    is the final character -- MID(sRxMsg, LEN-4, 5)."""
    if FIND(rx, "CMD:") == 1 and len(rx) > 4:
        return STRING_TO_INT(MID(rx, len(rx) - 4, 5))
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

# CMD:0 must stay distinguishable from "no frame at all" -- the whole reason
# ParseCmd returns -1 instead of 0.
SENTINEL_CASES = [
    ("CMD:0",           0,      "CMD:0 is a real command, not an absence"),
    ("OK: SET STATE",   NO_CMD, "no frame -> NO_CMD"),
    ("CMD:",            NO_CMD, "unusable frame -> NO_CMD"),
]


def main():
    hdr = f"{'frame':<30} {'expect':>6} {'old':>6} {'new':>6}   note"
    print(hdr)
    print("-" * len(hdr))
    old_bad = new_bad = 0
    for frame, prior, expect, note in CASES:
        o = old_consume(frame, prior)
        n = consume(frame, prior)
        old_bad += o != expect
        new_bad += n != expect
        fmt = lambda v: f"{v}{'' if v == expect else ' X'}"
        print(f"{frame!r:<30} {expect:>6} {fmt(o):>6} {fmt(n):>6}   {note}")

    print()
    for frame, expect, note in SENTINEL_CASES:
        got = parse_cmd(frame)
        flag = "" if got == expect else "  X"
        new_bad += got != expect
        print(f"sentinel: {frame!r:<20} -> {got:>3} (expect {expect:>3}){flag}   {note}")

    print()
    print(f"old parse: {old_bad}/{len(CASES)} wrong")
    print(f"new parse: {new_bad}/{len(CASES) + len(SENTINEL_CASES)} wrong")
    return 1 if new_bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
