#!/usr/bin/env node
'use strict';

// VOID SEALS — a standalone 113x53-terminal xiangqi opening mockup.
// Each piece occupies one identical 14x14 dot disc. Identity is negative space.

const PLAIN = process.argv.includes('--plain') || !process.stdout.isTTY;
const W = 188; // dots -> 94 terminal columns
const H = 160; // dots -> 40 terminal rows
const EMPTY = 0, BOARD = 1, BLACK = 2, RED = 3;
const px = Array.from({ length: H }, () => new Uint8Array(W));

const put = (x, y, ink) => {
  if (x >= 0 && x < W && y >= 0 && y < H) px[y][x] = ink;
};

const line = (x0, y0, x1, y1, ink = BOARD) => {
  let dx = Math.abs(x1 - x0), sx = x0 < x1 ? 1 : -1;
  let dy = -Math.abs(y1 - y0), sy = y0 < y1 ? 1 : -1;
  let err = dx + dy;
  for (;;) {
    put(x0, y0, ink);
    if (x0 === x1 && y0 === y1) break;
    const e2 = 2 * err;
    if (e2 >= dy) { err += dy; x0 += sx; }
    if (e2 <= dx) { err += dx; y0 += sy; }
  }
};

const X0 = 14, Y0 = 8, DX = 20, DY = 16;

// Board: restrained one-dot lattice, open river, and palace diagonals.
for (let f = 0; f < 9; f++) {
  const x = X0 + f * DX;
  line(x, Y0, x, Y0 + 4 * DY);
  line(x, Y0 + 5 * DY, x, Y0 + 9 * DY);
}
for (let r = 0; r < 10; r++) {
  const y = Y0 + r * DY;
  line(X0, y, X0 + 8 * DX, y);
}
line(X0 + 3 * DX, Y0, X0 + 5 * DX, Y0 + 2 * DY);
line(X0 + 5 * DX, Y0, X0 + 3 * DX, Y0 + 2 * DY);
line(X0 + 3 * DX, Y0 + 7 * DY, X0 + 5 * DX, Y0 + 9 * DY);
line(X0 + 5 * DX, Y0 + 7 * DY, X0 + 3 * DX, Y0 + 9 * DY);

// Small river current marks; deliberately mass-light so the discs dominate.
for (let x = X0 + 8; x < X0 + 8 * DX - 5; x += 13) {
  put(x, Y0 + 72, BOARD);
  put(x + 1, Y0 + 72, BOARD);
  put(x + 3, Y0 + 73, BOARD);
  put(x + 4, Y0 + 73, BOARD);
}

const insideDisc = (x, y) => {
  const dx = x - 6.5, dy = y - 6.5;
  return dx * dx + dy * dy <= 44.5;
};

// `hole` returns true where the solid seal is punched through.
const holes = {
  // General: a compact square palace around a retained central throne.
  G: (x, y) => x >= 3 && x <= 10 && y >= 3 && y <= 10 &&
    !(x >= 5 && x <= 8 && y >= 5 && y <= 8),

  // Advisor: two thick diagonal cuts (palace diagonals).
  A: (x, y) => {
    const d1 = Math.abs(x - y);
    const d2 = Math.abs((x + y) - 13);
    return (d1 <= 1 || d2 <= 1) && x >= 2 && x <= 11 && y >= 2 && y <= 11;
  },

  // Elephant: two broad side-by-side eyes. No central bore, no ring.
  E: (x, y) => {
    const left = ((x - 4.1) / 2.1) ** 2 + ((y - 6.5) / 3.0) ** 2 <= 1;
    const right = ((x - 8.9) / 2.1) ** 2 + ((y - 6.5) / 3.0) ** 2 <= 1;
    return left || right;
  },

  // Chariot: orthogonal rails punched clear through the seal.
  R: (x, y) => (x >= 5 && x <= 8 && y >= 2 && y <= 11) ||
    (y >= 5 && y <= 8 && x >= 2 && x <= 11),

  // Horse: one thick, unmistakable blocked-leg / L path.
  H: (x, y) => (x >= 3 && x <= 5 && y >= 2 && y <= 9) ||
    (x >= 3 && x <= 10 && y >= 8 && y <= 10),

  // Cannon: a single circular bore with a retained shot at its center.
  C: (x, y) => {
    const d = Math.hypot(x - 6.5, y - 6.5);
    return d >= 2.0 && d <= 4.2;
  },

  // Soldier: a large forward wedge; most void, least visual authority.
  S: (x, y) => y >= 2 && y <= 10 &&
    Math.abs(x - 6.5) <= (y <= 6 ? (y - 1) * 0.72 : 1.7),
};

function piece(file, rankFromTop, kind, ink) {
  const cx = X0 + file * DX, cy = Y0 + rankFromTop * DY;

  // Knock out the lattice beneath the token so holes remain true voids.
  for (let sy = 0; sy < 14; sy++) {
    for (let sx = 0; sx < 14; sx++) {
      const gx = cx - 7 + sx, gy = cy - 7 + sy;
      const ddx = sx - 6.5, ddy = sy - 6.5;
      if (ddx * ddx + ddy * ddy <= 57) put(gx, gy, EMPTY);
    }
  }

  for (let sy = 0; sy < 14; sy++) {
    for (let sx = 0; sx < 14; sx++) {
      if (insideDisc(sx, sy) && !holes[kind](sx, sy)) {
        put(cx - 7 + sx, cy - 7 + sy, ink);
      }
    }
  }
}

const back = ['R', 'H', 'E', 'A', 'G', 'A', 'E', 'H', 'R'];
back.forEach((k, f) => piece(f, 0, k, BLACK));
piece(1, 2, 'C', BLACK); piece(7, 2, 'C', BLACK);
for (const f of [0, 2, 4, 6, 8]) piece(f, 3, 'S', BLACK);
for (const f of [0, 2, 4, 6, 8]) piece(f, 6, 'S', RED);
piece(1, 7, 'C', RED); piece(7, 7, 'C', RED);
back.forEach((k, f) => piece(f, 9, k, RED));

const brailleBit = [
  [0x01, 0x08],
  [0x02, 0x10],
  [0x04, 0x20],
  [0x40, 0x80],
];

const ansi = {
  [BOARD]: '\x1b[38;5;242m',
  [BLACK]: '\x1b[38;5;221m', // lacquer-gold black side
  [RED]: '\x1b[38;5;203m',   // vermilion red side
};
const reset = '\x1b[0m';

function render() {
  const rows = [];
  for (let by = 0; by < H; by += 4) {
    const rankIndex = Array.from({ length: 10 }, (_, r) => 2 + r * 4).indexOf(by / 4);
    let row = rankIndex >= 0 ? `${9 - rankIndex}  ` : '   ';
    let active = 0;
    for (let bx = 0; bx < W; bx += 2) {
      let source = 0;
      for (let yy = 0; yy < 4; yy++) for (let xx = 0; xx < 2; xx++) {
        source = Math.max(source, px[by + yy]?.[bx + xx] || 0);
      }
      let bits = 0;
      if (source) {
        for (let yy = 0; yy < 4; yy++) for (let xx = 0; xx < 2; xx++) {
          if ((px[by + yy]?.[bx + xx] || 0) === source) bits |= brailleBit[yy][xx];
        }
      }
      if (!PLAIN && source !== active) {
        row += source ? ansi[source] : reset;
        active = source;
      }
      row += String.fromCodePoint(0x2800 + bits);
    }
    if (!PLAIN && active) row += reset;
    rows.push(row.replace(/[⠀ ]+$/u, ''));
  }
  return rows;
}

function sealRows(kind) {
  const rows = [];
  for (let by = 0; by < 16; by += 4) {
    let row = '';
    for (let bx = 0; bx < 14; bx += 2) {
      let bits = 0;
      for (let yy = 0; yy < 4; yy++) for (let xx = 0; xx < 2; xx++) {
        const x = bx + xx, y = by + yy;
        if (y < 14 && insideDisc(x, y) && !holes[kind](x, y)) bits |= brailleBit[yy][xx];
      }
      row += String.fromCodePoint(0x2800 + bits);
    }
    rows.push(row);
  }
  return rows;
}

const title = 'VOID SEALS  /  BLACK \u25bc';
const footer = 'a         b         c         d         e         f         g         h         i';
const atlas = [
  ['R', 'CHARIOT'], ['H', 'HORSE'], ['E', 'ELEPHANT'], ['A', 'ADVISOR'],
  ['G', 'GENERAL'], ['C', 'CANNON'], ['S', 'SOLDIER'],
];
console.log('   ' + title);
console.log(render().join('\n'));
console.log('          ' + footer);
console.log('');
for (let row = 0; row < 4; row++) {
  console.log('   ' + atlas.map(([k]) => sealRows(k)[row].padEnd(11, ' ')).join(''));
}
console.log('   ' + atlas.map(([, name]) => name.padStart(9, ' ').padEnd(11, ' ')).join(''));
console.log('RED \u25b2  /  opening position  /  every seal: 14\u00d714 dots');
