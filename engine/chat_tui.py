"""The room — a styled tail-follow view of <live dir>/chat.log.

Same board-as-object language as tui.py: the whole pane is painted PANEL, nothing
borrows the terminal theme. Speakers carry the hue of their seat (White ice,
Black ember, facilitator gold, watchers slate) so a glance tells you who is
talking without reading. Deliberately still — this hangs on a wall of animated
panes, so the only motion is a new line arriving and a slow fade-in on it.
"""
import os, shutil, sys, time
from pathlib import Path

# Shared across games: deployed copies live IN the live dir, so the script's own
# parent is the right default for every game (ARCADE_LIVE still wins when set).
# Before this, an unset ARCADE_LIVE silently tailed /tmp/chess from every table.
D = Path(os.environ.get('ARCADE_LIVE') or Path(__file__).resolve().parent)
sys.path.insert(0, str(D))
import chat

PANEL = (26, 30, 40)
ICE, EMBER = (120, 210, 235), (240, 160, 70)
GOLD, SLATE = (226, 186, 96), (138, 147, 166)
TEXT, TDIM, LABEL = (208, 216, 232), (122, 132, 152), (98, 108, 128)
FOOT = (90, 98, 114)

ROLE_HUE = {'white': ICE, 'black': EMBER, 'facilitator': GOLD, 'watcher': SLATE}
FADE_SECS = 1.2     # how long a freshly arrived line glows in
R = '\x1b[0m'


def bg(c): return f'\x1b[48;2;{c[0]};{c[1]};{c[2]}m'
def fg(c): return f'\x1b[38;2;{c[0]};{c[1]};{c[2]}m'


def blend(a, b, t):
    t = max(0.0, min(1.0, t))
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def say_hint():
    """Point at the wrapper that actually lives in this live dir."""
    for g in ('game.sh', 'game_xq.sh', 'game_cw.sh'):
        if (D / g).exists():
            return f" {g} say '<message>'"
    return " game.sh say '<message>'"


def wrap(text, width):
    if width < 8:
        return [text[:width]]
    out, cur = [], ''
    for word in text.split():
        if not cur:
            cur = word
        elif len(cur) + 1 + len(word) <= width:
            cur += ' ' + word
        else:
            out.append(cur)
            cur = word
        while len(cur) > width:          # a single unbreakable token
            out.append(cur[:width])
            cur = cur[width:]
    if cur:
        out.append(cur)
    return out or ['']


def layout(msgs, width, now):
    """Flatten messages into styled rows: [(text, colour, is_header, age)]."""
    # Wide panes get a hanging indent under the speaker; narrow ones can't spare
    # the columns, so the body sits almost flush and the header alone carries rank.
    ind = ' ' * (7 if width >= 44 else 2)
    body_w = max(8, width - len(ind) - 2)
    rows, prev_who, prev_ts = [], None, 0
    override, players = chat.roles(), chat.player_names()
    for ts, who, text in msgs:
        hue = ROLE_HUE[chat.role_of(who, override, players)]
        age = now - ts
        # Consecutive lines from one speaker share a header — keeps the room calm.
        if who != prev_who or ts - prev_ts > 180:
            if rows:
                rows.append(('', PANEL, False, age))
            stamp = time.strftime('%H:%M', time.localtime(ts))
            rows.append((f'{stamp}  {who[:width - 8].upper()}', hue, True, age))
        for ln in wrap(text, body_w):
            rows.append((ind + ln, TEXT, False, age))
        prev_who, prev_ts = who, ts
    return rows


def render(msgs, mtime):
    cols, height = shutil.get_terminal_size((40, 20))
    now = time.time()
    rows = layout(msgs, cols, now) or [
        (' nobody has said anything yet', FOOT, False, 999),
        (say_hint(), FOOT, False, 999)]
    avail = max(1, height - 2)
    if len(rows) > avail:
        # Open on a speaker, never mid-sentence: slide the cut forward to the next
        # header. If that one message still overflows, fall back to a plain tail.
        cut = len(rows) - avail
        snap = next((i for i in range(cut, len(rows)) if rows[i][2]), None)
        rows = rows[snap:] if snap is not None else rows[cut:]
        rows = rows[-avail:]
    while rows and not rows[0][0]:
        rows.pop(0)
    pad = avail - len(rows)

    out = []

    def line(body=''):
        return bg(PANEL) + body + bg(PANEL) + '\x1b[K' + R

    count = len(msgs)
    out.append(line(f' {fg(LABEL)}ROOM{R}{bg(PANEL)}{fg(FOOT)}  ·  '
                    f'{count} message{"" if count == 1 else "s"}'))
    for _ in range(pad):
        out.append(line())
    for text, col, header, age in rows:
        if not text:
            out.append(line())
            continue
        # New arrivals surface out of the panel rather than snapping in.
        k = min(1.0, age / FADE_SECS) if age >= 0 else 1.0
        c = blend(PANEL, col, 0.35 + 0.65 * k)
        bold = '\x1b[1m' if header else ''
        out.append(line(f' {bold}{fg(c)}{text}'))
    stamp = time.strftime('%H:%M:%S', time.localtime(mtime)) if mtime else '--:--:--'
    out.append(line(f' {fg(FOOT)}last {stamp}'))
    # No trailing newline on the last row: emitting one would scroll the pane and
    # push the header off the top every frame.
    sys.stdout.write('\x1b[H\x1b[?25l' + '\n'.join(out[:height]) + bg(PANEL) + '\x1b[J' + R)
    sys.stdout.flush()


def main():
    sys.stdout.write('\x1b[2J')
    seen_mtime, seen_size, msgs = -1, -1, []
    dirty_until = 0.0
    while True:
        try:
            st = chat.CHAT.stat()
            mtime, size = st.st_mtime, st.st_size
        except OSError:
            mtime, size = 0, 0
        if (mtime, size) != (seen_mtime, seen_size):
            seen_mtime, seen_size = mtime, size
            msgs = chat.read()
            dirty_until = time.time() + FADE_SECS + 0.2
        # Idle at 2Hz; only run the fade animation while something is fading.
        render(msgs, seen_mtime)
        time.sleep(0.08 if time.time() < dirty_until else 0.5)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        sys.stdout.write('\x1b[0m\x1b[?25h\n')
    except Exception as e:
        sys.stdout.write(f'\x1b[0m\x1b[?25h\nCHAT CRASH: {e}\n')
        raise
