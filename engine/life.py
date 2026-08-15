import random, sys, time

W, H = 46, 13
grid = {(x, y) for x in range(W) for y in range(H) if random.random() < 0.25}
gen = 0
print('\x1b[2J', end='')
while True:
    counts = {}
    for (x, y) in grid:
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if dx or dy:
                    counts[((x + dx) % W, (y + dy) % H)] = counts.get(((x + dx) % W, (y + dy) % H), 0) + 1
    grid = {c for c, n in counts.items() if n == 3 or (n == 2 and c in grid)}
    gen += 1
    if gen % 400 == 0 or len(grid) < 8:
        grid = {(x, y) for x in range(W) for y in range(H) if random.random() < 0.25}
    rows = [''.join('▓' if (x, y) in grid else ' ' for x in range(W)) for y in range(H)]
    sys.stdout.write('\x1b[H\x1b[35m' + '\n'.join(rows) + f'\n GEN {gen:05d}  POP {len(grid):4d}\n')
    sys.stdout.flush()
    time.sleep(0.12)
