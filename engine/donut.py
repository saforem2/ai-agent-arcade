import math, time, sys

A = B = 0
W, H = 34, 10
print('\x1b[2J', end='')
while True:
    z = [0.0] * (W * H)
    b = [' '] * (W * H)
    j = 0.0
    while j < 6.28:
        i = 0.0
        while i < 6.28:
            c, d = math.sin(i), math.cos(j)
            e, f, g = math.sin(A), math.sin(j), math.cos(A)
            h = d + 2
            D = 1 / (c * h * e + f * g + 5)
            l, m, n = math.cos(i), math.cos(B), math.sin(B)
            t = c * h * g - f * e
            x = int(W / 2 + (W * 0.38) * D * (l * h * m - t * n))
            y = int(H / 2 + (H * 0.48) * D * (l * h * n + t * m))
            o = x + W * y
            N = int(8 * ((f * e - c * d * g) * m - c * d * e - f * g - l * d * n))
            if 0 <= y < H and 0 <= x < W and D > z[o]:
                z[o] = D
                b[o] = ".,-~:;=!*#$@"[max(N, 0)]
            i += 0.02
        j += 0.07
    out = '\n'.join(''.join(b[W * k:W * k + W]) for k in range(H))
    sys.stdout.write('\x1b[H\x1b[36m' + out + '\n')
    sys.stdout.flush()
    A += 0.05
    B += 0.025
    time.sleep(0.03)
