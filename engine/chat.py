"""Shared chat-bus helpers. One append-only file, one line per message.

Line format:  <epoch>\t<name>\t<text>
Tabs and newlines are stripped from text so a line is always one message.
"""
import os, time
from pathlib import Path

D = Path(os.environ.get('ARCADE_LIVE', '/tmp/chess'))
CHAT = D / 'chat.log'
ROLES = D / 'roles.txt'
NAMES = D / 'names.txt'
SEATS = D / 'seats.txt'

# 'director' stays alongside 'host' (2e rename, docs/design-history.md §14)
# so an old archived room or a name like "director-grok" still classifies
# as facilitator, not watcher.
FACILITATOR_HINTS = ('ref', 'referee', 'director', 'host', 'facilitator', 'arbiter', 'td', 'arcade')
MAX_LEN = 500


def clean(text, limit=MAX_LEN):
    """Terminal-safe text. str.isprintable() is False for every C0/C1 control —
    including ESC — so a poster cannot smuggle escape sequences into a pane that
    paints whatever it reads. Whitespace collapses, so one message is one line.
    """
    s = ' '.join(''.join(c for c in str(text) if c.isprintable() or c == ' ').split())
    if limit and len(s) > limit:
        s = s[:limit - 1].rstrip() + '…'
    return s


def whoami():
    n = os.environ.get('CHESS_NAME') or os.environ.get('USER') or 'anon'
    return clean(n, 24) or 'anon'


def say(text, name=None, ts=None):
    name = clean(name or whoami(), 24) or 'anon'
    text = clean(text)
    if not text:
        return None
    line = f'{int(ts or time.time())}\t{name}\t{text}\n'
    with CHAT.open('a') as fh:      # O_APPEND: concurrent writers never interleave
        fh.write(line)
    return line


def read(limit=None):
    """Return [(epoch, name, text)] oldest-first, tolerant of partial lines."""
    try:
        raw = CHAT.read_text(errors='replace').splitlines()
    except OSError:
        return []
    if limit:
        raw = raw[-limit:]
    out = []
    for ln in raw:
        parts = ln.split('\t', 2)
        if len(parts) != 3:
            continue
        try:
            # Re-clean on read: anything can append to the bus, and the renderer
            # must never paint bytes it did not sanitise itself.
            out.append((int(parts[0]), clean(parts[1], 24), clean(parts[2])))
        except ValueError:
            continue
    return out


def roles():
    """name(lower) -> role. roles.txt lines `<name> <role>` override the heuristic."""
    m = {}
    try:
        for ln in ROLES.read_text().splitlines():
            p = ln.split()
            if len(p) >= 2:
                m[p[0].lower()] = p[1].lower()
    except OSError:
        pass
    return m


def role_of(name, override=None, players=None):
    """One of: white | black | facilitator | watcher."""
    key = name.lower()
    if override and key in override:
        return override[key]
    if players is None:
        players = player_names()
    # agents introduce themselves as "kimi-white" while names.txt says "KIMI",
    # so match on either being a prefix of the other.
    for role, who in (('white', players[0].lower()), ('black', players[1].lower())):
        if who and (key.startswith(who) or who.startswith(key)):
            return role
    if any(h in key for h in FACILITATOR_HINTS):
        return 'facilitator'
    return 'watcher'


def player_names():
    try:
        p = NAMES.read_text().split()
        if len(p) == 2:
            return p[0], p[1]
    except OSError:
        pass
    return 'WHITE', 'BLACK'


def seats():
    """{'white': name, 'black': name} from seats.txt, written by `arcade
    start` as `<NAME> white` / `<NAME> black` lines. Empty dict if the file
    is missing (an older deployed match, or manual/dev use before `arcade
    start` wrote one) or has neither line -- callers treat that as
    "seat-checking unavailable," not "nobody is seated."
    """
    m = {}
    try:
        for ln in SEATS.read_text().splitlines():
            parts = ln.split()
            if len(parts) >= 2 and parts[1].lower() in ('white', 'black'):
                name = clean(parts[0], 24)
                if name:
                    m[parts[1].lower()] = name
    except OSError:
        pass
    return m


def require_seated():
    """Game-5 retro fix: a signer who isn't one of the two seated players
    must be hard-refused, not silently staged and discarded later (that cost
    a tempo when CHESS_NAME was unset and the wrong identity got staged).

    Returns True if whoami() matches a seats.txt entry, or if seats.txt is
    unavailable (nothing to check against -- never lock everyone out over a
    missing file). Returns False and prints an actionable message naming the
    seated players otherwise; callers exit(1) on False.
    """
    s = seats()
    if not s:
        return True
    who = whoami()
    named = {n.lower() for n in s.values()}
    if who.lower() in named:
        return True
    roster = ' / '.join(f'{n} ({role})' for role, n in s.items())
    print(f'REFUSED: you are signing as "{who}", but the seated players are: {roster}.')
    print('Fix your identity first: export CHESS_NAME=<your seat name> (must match seats.txt exactly)')
    return False
