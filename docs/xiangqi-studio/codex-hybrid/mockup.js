#!/usr/bin/env node
'use strict';

// SOFT LACQUER: native CJK identity inside braille-mass discs.
// Standalone proposal; does not depend on or modify the arcade repository.

const args = new Set(process.argv.slice(2));
const plain = args.has('--plain') || !process.stdout.isTTY;
const forcedCompact = args.has('--compact');
const forcedMicro = args.has('--micro');
const dense = args.has('--dense');
const soft = args.has('--soft');
const envRows = Number(process.env.LINES || 53);
const envCols = Number(process.env.COLUMNS || 113);
const roomy = !forcedCompact && !forcedMicro && envRows >= 44 && envCols >= 84;
const micro = forcedMicro || (!roomy && !forcedCompact && (envRows < 22 || envCols < 58));
const compact = forcedCompact || (!roomy && !micro);

const RESET = '\x1b[0m';
const COLORS = {
  board: '\x1b[38;5;239m',
  black: '\x1b[1;38;5;221m',
  red: '\x1b[1;38;5;203m',
  label: '\x1b[38;5;246m',
};

function paint(text, role) {
  return plain ? text : `${COLORS[role]}${text}${RESET}`;
}

function displayWidth(text) {
  let n = 0;
  for (const ch of text) n += /[\u2E80-\u9FFF\uF900-\uFAFF]/u.test(ch) ? 2 : 1;
  return n;
}

function padDisplay(text, width) {
  return text + ' '.repeat(Math.max(0, width - displayWidth(text)));
}

const blackBack = [...'車馬象士將士象馬車'];
const redBack = [...'俥傌相仕帥仕相傌俥'];
const positions = [];

blackBack.forEach((face, file) => positions.push({ file, rank: 0, face, side: 'black' }));
for (const file of [1, 7]) positions.push({ file, rank: 2, face: '砲', side: 'black' });
for (const file of [0, 2, 4, 6, 8]) positions.push({ file, rank: 3, face: '卒', side: 'black' });
for (const file of [0, 2, 4, 6, 8]) positions.push({ file, rank: 6, face: '兵', side: 'red' });
for (const file of [1, 7]) positions.push({ file, rank: 7, face: '炮', side: 'red' });
redBack.forEach((face, file) => positions.push({ file, rank: 9, face, side: 'red' }));

function token(face) {
  if (micro) return [face];
  if (compact) return [`⣾${face}⣷`];
  if (dense) return [' ⣠⣶⣄ ', `⣿ ${face} ⣿`, ' ⠙⠛⠋ '];
  if (soft) return ['  ⣴⣦  ', `⣾ ${face} ⣷`, '  ⠻⠟  '];
  return [' ⣠⣶⣄ ', `⣾ ${face} ⣷`, ' ⠙⠛⠋ '];
}

function putWide(row, col, text, role = 'board') {
  let x = col;
  for (const ch of text) {
    const wide = /[\u2E80-\u9FFF\uF900-\uFAFF]/u.test(ch);
    row[x] = { ch, role };
    if (wide) row[x + 1] = { ch: '', role, continuation: true };
    x += wide ? 2 : 1;
  }
}

function renderRoomy() {
  const width = 77;
  const height = 41;
  const x0 = 7, y0 = 2, dx = 8, dy = 4;
  const cells = Array.from({ length: height }, () =>
    Array.from({ length: width }, () => ({ ch: ' ', role: 'board' }))
  );

  // Horizontal ranks.
  for (let rank = 0; rank < 10; rank++) {
    const y = y0 + rank * dy;
    for (let x = x0; x <= x0 + 8 * dx; x++) cells[y][x] = { ch: '─', role: 'board' };
  }
  // Vertical files, broken at the river except for the banks.
  for (let file = 0; file < 9; file++) {
    const x = x0 + file * dx;
    for (let y = y0; y <= y0 + 9 * dy; y++) {
      if (file !== 0 && file !== 8 && y > y0 + 4 * dy && y < y0 + 5 * dy) continue;
      cells[y][x] = { ch: '│', role: 'board' };
    }
  }
  for (let rank = 0; rank < 10; rank++) {
    for (let file = 0; file < 9; file++) {
      cells[y0 + rank * dy][x0 + file * dx] = { ch: '┼', role: 'board' };
    }
  }
  // Palace crosses.
  for (const [top, bottom] of [[0, 2], [7, 9]]) {
    for (let k = 1; k < 2 * dy; k++) {
      const y = y0 + top * dy + k;
      const left = x0 + 3 * dx + Math.round(k * (2 * dx) / (2 * dy));
      const right = x0 + 5 * dx - Math.round(k * (2 * dx) / (2 * dy));
      cells[y][left] = { ch: '╲', role: 'board' };
      cells[y][right] = { ch: '╱', role: 'board' };
    }
  }

  for (const p of positions) {
    const cx = x0 + p.file * dx;
    const cy = y0 + p.rank * dy;
    const art = token(p.face);
    const top = cy - 1;
    for (let ay = 0; ay < art.length; ay++) {
      const w = displayWidth(art[ay]);
      const left = cx - Math.floor(w / 2);
      for (let x = left; x < left + w; x++) cells[top + ay][x] = { ch: ' ', role: 'board' };
      putWide(cells[top + ay], left, art[ay], p.side);
    }
  }

  const out = [];
  for (let y = 0; y < height; y++) {
    const rank = Array.from({ length: 10 }, (_, r) => y0 + r * dy).indexOf(y);
    let line = rank >= 0 ? paint(`${9 - rank}  `, 'label') : '   ';
    for (let x = 0; x < width; x++) {
      const cell = cells[y][x];
      if (!cell.continuation) line += paint(cell.ch, cell.role);
    }
    out.push(line.replace(/\s+$/u, ''));
  }
  out.push('          a       b       c       d       e       f       g       h       i');
  return out;
}

function renderCompact() {
  const out = [];
  const files = 'a     b     c     d     e     f     g     h     i';
  const map = new Map(positions.map(p => [`${p.file},${p.rank}`, p]));
  for (let rank = 0; rank < 10; rank++) {
    let line = paint(`${9 - rank}  `, 'label');
    for (let file = 0; file < 9; file++) {
      const p = map.get(`${file},${rank}`);
      line += p ? paint(padDisplay(token(p.face)[0], 6), p.side) : paint(padDisplay('┼', 6), 'board');
    }
    out.push(line);
    if (rank !== 9) out.push('   ' + paint('│     '.repeat(9), 'board'));
  }
  out.push('   ' + files);
  return out;
}

function renderMicro() {
  const out = [];
  const map = new Map(positions.map(p => [`${p.file},${p.rank}`, p]));
  for (let rank = 0; rank < 10; rank++) {
    let line = paint(`${9 - rank}  `, 'label');
    for (let file = 0; file < 9; file++) {
      const p = map.get(`${file},${rank}`);
      line += p ? paint(padDisplay(p.face, 4), p.side) : paint(padDisplay('┼', 4), 'board');
    }
    out.push(line);
    if (rank !== 9) out.push('   ' + paint('│   '.repeat(9), 'board'));
  }
  out.push('   a   b   c   d   e   f   g   h   i');
  return out;
}

const density = dense ? 'DENSE' : soft ? 'SOFT' : 'BALANCED';
const mode = micro ? 'MICRO NATIVE TEXT' : compact ? 'COMPACT 1-ROW TOKEN' : `ROOMY 3-ROW ${density} DISC`;
console.log(paint(`BRAILLE LACQUER  /  BLACK ▼  /  ${mode}`, 'label'));
console.log((micro ? renderMicro() : compact ? renderCompact() : renderRoomy()).join('\n'));
console.log(paint('RED ▲  /  native traditional faces; braille supplies mass only', 'label'));
