import time, sys

FONT = {
    '0': ["███", "█ █", "█ █", "█ █", "███"],
    '1': [" █ ", "██ ", " █ ", " █ ", "███"],
    '2': ["███", "  █", "███", "█  ", "███"],
    '3': ["███", "  █", "███", "  █", "███"],
    '4': ["█ █", "█ █", "███", "  █", "  █"],
    '5': ["███", "█  ", "███", "  █", "███"],
    '6': ["███", "█  ", "███", "█ █", "███"],
    '7': ["███", "  █", "  █", "  █", "  █"],
    '8': ["███", "█ █", "███", "█ █", "███"],
    '9': ["███", "█ █", "███", "  █", "███"],
    ':': ["   ", " █ ", "   ", " █ ", "   "],
}
print('\x1b[2J', end='')
while True:
    now = time.strftime('%H:%M:%S')
    rows = [' '.join(FONT[ch][r] for ch in now) for r in range(5)]
    date = time.strftime('%A %d %B %Y').upper()
    pad = max(0, (len(rows[0]) - len(date)) // 2)
    out = '\n\n  ' + '\n  '.join(rows) + '\n\n  ' + ' ' * pad + date
    sys.stdout.write('\x1b[H\x1b[33m' + out + '\n')
    sys.stdout.flush()
    time.sleep(0.5)
