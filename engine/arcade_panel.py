"""Arcade side panel — the interactive column of the wall.

One Textual app replacing the static MOVES and MATCH panes. Three collapsible
sections over the same file bus everyone else speaks:

    MATCH      seats, turn, series record, ply/move, status
    MATERIAL   who is ahead, by how much, said in words not just a sign
    MOVES      per-ply list: mover NAME, piece, from-to, capture/check marks

Reads /tmp/chess/{moves,names,results,fen}.txt on a 0.5s poll and rebuilds the
whole view whenever any of them changes. Full rebuild is deliberate: a reset,
a replay, or ten moves landing at once are all just "the log differs now", so
there is no incremental state to get out of sync.

House rule: no ambient animation. This panel is still.

    uv run --quiet --with textual --with chess python arcade_panel.py
"""
import os
from pathlib import Path

import chess
from textual.app import App, ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Collapsible, Static

D = Path(os.environ.get('ARCADE_LIVE', '/tmp/chess'))
MOVES, NAMES, RESULTS, FEN = (D / 'moves.txt', D / 'names.txt',
                              D / 'results.txt', D / 'fen.txt')
WATCH = (MOVES, NAMES, RESULTS, FEN)

ICE, EMBER = '#78d2eb', '#f0a046'
SLATE, TEXT, FOOT = '#8a93a6', '#d0d8e8', '#5a6272'
VALUE = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3,
         chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 0}
BAR_W = 14
BAR_MAX = 15        # a queen and a rook up: past this the bar is just "winning"


def read(path, default=''):
    try:
        return path.read_text().strip()
    except OSError:
        return default


def stamp():
    """Identity of the file bus right now — cheap change detection."""
    out = []
    for p in WATCH:
        try:
            st = p.stat()
            out.append((st.st_mtime_ns, st.st_size))
        except OSError:
            out.append(None)
    return tuple(out)


class Game:
    """Everything the panel shows, derived from the files in one pass."""

    def __init__(self):
        parts = read(NAMES).split()
        self.white, self.black = (parts + ['WHITE', 'BLACK'])[:2]
        sans = read(MOVES).split()
        self.board = chess.Board()
        self.rows = []
        for i, san in enumerate(sans):
            try:
                mv = self.board.parse_san(san)
            except ValueError:
                break       # a bad log truncates the view; it never crashes it
            piece = self.board.piece_at(mv.from_square)
            capture = self.board.is_capture(mv)
            frm = chess.square_name(mv.from_square)
            to = chess.square_name(mv.to_square)
            self.board.push(mv)
            mark = '#' if self.board.is_checkmate() else ('+' if self.board.is_check() else '')
            if capture:
                mark = '×' + mark
            self.rows.append({
                'no': i // 2 + 1,
                'white': i % 2 == 0,
                'name': self.white if i % 2 == 0 else self.black,
                'piece': piece.symbol().upper() if piece else '?',
                'from': frm, 'to': to, 'mark': mark,
            })
        self.ply = len(self.rows)
        self.series = self._series()

    def _series(self):
        """results.txt lines are `<WHITE> <RESULT> <BLACK>`, filtered to the
        current pairing (order-insensitive: colours swap between games).
        results.txt is cumulative across every pairing that has ever played --
        `winner in tally` alone isn't a pairing filter, since one name from an
        unrelated pairing can still match a current player's name.
        """
        tally = {self.white: 0, self.black: 0}
        pair = {self.white, self.black}
        for line in read(RESULTS).splitlines():
            parts = line.split()
            if len(parts) != 3:
                continue
            w, res, b = parts
            if {w, b} != pair:
                continue
            winner = w if res == '1-0' else b if res == '0-1' else None
            if winner in tally:
                tally[winner] += 1
        return tally

    def material(self):
        """(leader_name, margin, colour). margin 0 means level."""
        score = 0
        for piece in self.board.piece_map().values():
            v = VALUE[piece.piece_type]
            score += v if piece.color == chess.WHITE else -v
        if score > 0:
            return self.white, score, ICE
        if score < 0:
            return self.black, -score, EMBER
        return None, 0, SLATE

    def status(self):
        if self.board.is_checkmate():
            winner = self.black if self.board.turn == chess.WHITE else self.white
            return f'checkmate — {winner} wins', EMBER if self.board.turn else ICE
        if self.board.is_stalemate():
            return 'stalemate — drawn', SLATE
        if self.board.is_insufficient_material():
            return 'drawn — insufficient material', SLATE
        if self.board.is_game_over():
            return f'game over — {self.board.result()}', SLATE
        who = self.white if self.board.turn == chess.WHITE else self.black
        hue = ICE if self.board.turn == chess.WHITE else EMBER
        return (f'{who} to move — CHECK' if self.board.is_check()
                else f'{who} to move'), hue


class ArcadePanel(App):
    CSS = f"""
    Screen {{ background: #1a1e28; color: {TEXT}; }}
    VerticalScroll {{ background: #1a1e28; scrollbar-size: 1 1; }}
    Collapsible {{
        background: #1a1e28; border: none; padding: 0; margin: 0 0 1 0;
    }}
    Collapsible > CollapsibleTitle {{
        background: #1a1e28; color: {SLATE}; text-style: bold; padding: 0 1;
    }}
    Collapsible > CollapsibleTitle:hover {{ color: {TEXT}; }}
    Collapsible > Contents {{ background: #1a1e28; padding: 0 0 0 1; }}
    Static {{ background: #1a1e28; }}
    #moves {{ height: 1fr; min-height: 6; scrollbar-size: 1 1; }}
    #hint {{
        dock: bottom; height: 1; background: #1a1e28; color: {FOOT}; padding: 0 1;
    }}
    """
    BINDINGS = [
        ('j', 'scroll_moves(1)', 'down'),
        ('k', 'scroll_moves(-1)', 'up'),
        ('g', 'moves_home', 'newest'),
        ('G', 'moves_end', 'oldest'),
        ('r', 'refresh_now', 'reload'),
        ('1', 'toggle("c_match")', 'match'),
        ('2', 'toggle("c_material")', 'material'),
        ('3', 'toggle("c_moves")', 'moves'),
    ]

    def compose(self) -> ComposeResult:
        with VerticalScroll():
            with Collapsible(title='MATCH', collapsed=False, id='c_match'):
                yield Static(id='match')
            with Collapsible(title='MATERIAL', collapsed=False, id='c_material'):
                yield Static(id='material')
            with Collapsible(title='MOVES', collapsed=False, id='c_moves'):
                with VerticalScroll(id='moves'):
                    yield Static(id='movelist')
        # Must fit one line inside 36 cols minus the scrollbar, or it wraps and
        # eats a move row. height:1 in the CSS is the belt to this braces.
        yield Static('[dim]1 2 3[/] fold  [dim]jk[/] scroll  [dim]r[/] reload',
                     id='hint')

    def on_mount(self):
        self._stamp = None
        self.refresh_state()
        self.set_interval(0.5, self.refresh_state)

    def action_scroll_moves(self, delta: int):
        self.query_one('#moves', VerticalScroll).scroll_relative(y=delta * 3, animate=False)

    def action_moves_home(self):
        self.query_one('#moves', VerticalScroll).scroll_home(animate=False)

    def action_moves_end(self):
        self.query_one('#moves', VerticalScroll).scroll_end(animate=False)

    def action_toggle(self, section: str):
        c = self.query_one('#' + section, Collapsible)
        c.collapsed = not c.collapsed

    def action_refresh_now(self):
        self._stamp = None
        self.refresh_state()

    def refresh_state(self):
        now = stamp()
        if now == self._stamp:
            return
        self._stamp = now
        try:
            g = Game()
        except Exception as exc:                     # never let a bad file kill the panel
            self.query_one('#match', Static).update(f'[{EMBER}]panel error:[/] {exc}')
            return
        self.query_one('#match', Static).update(self._match(g))
        self.query_one('#material', Static).update(self._material(g))
        self.query_one('#movelist', Static).update(self._moves(g))

    def _match(self, g):
        turn_w = g.board.turn == chess.WHITE and not g.board.is_game_over()
        turn_b = g.board.turn == chess.BLACK and not g.board.is_game_over()
        lines = [
            self._seat(g.white, ICE, g.series.get(g.white, 0), turn_w, 'white'),
            self._seat(g.black, EMBER, g.series.get(g.black, 0), turn_b, 'black'),
            '',
            f'[{FOOT}]ply[/] [{TEXT}]{g.ply}[/]   [{FOOT}]move[/] '
            f'[{TEXT}]{g.ply // 2 + (g.ply % 2)}[/]',
        ]
        text, hue = g.status()
        lines.append(f'[{hue}]{text}[/]')
        return '\n'.join(lines)

    @staticmethod
    def _seat(name, hue, wins, on_move, side):
        arrow = f'[{hue}]▸[/]' if on_move else ' '
        return (f'{arrow} [{hue}]{name[:9]:<9}[/] [{FOOT}]{side:<5}[/] '
                f'[{TEXT}]{wins}[/][{FOOT}] won[/]')

    @staticmethod
    def _material(g):
        leader, margin, hue = g.material()
        if not leader:
            return f'[{SLATE}]level[/]  [{FOOT}]{"·" * BAR_W}[/]'
        filled = max(1, min(BAR_W, round(margin / BAR_MAX * BAR_W)))
        bar = f'[{hue}]{"█" * filled}[/][{FOOT}]{"·" * (BAR_W - filled)}[/]'
        return (f'[{hue}]{leader}[/] [{TEXT}]+{margin}[/]\n{bar}\n'
                f'[{FOOT}]ahead by {margin} point{"" if margin == 1 else "s"}[/]')

    @staticmethod
    def _moves(g):
        if not g.rows:
            return f'[{FOOT}]no moves yet[/]'
        out = []
        for r in reversed(g.rows):          # newest first: the live end needs no scrolling
            hue = ICE if r['white'] else EMBER
            mark = f'[{TEXT}]{r["mark"]}[/]' if r['mark'] else ''
            out.append(f'[{FOOT}]{r["no"]:>3}.[/] [{hue}]{r["name"][:6]:<6}[/] '
                       f'[{TEXT}]{r["piece"]}[/] [{SLATE}]{r["from"]}→{r["to"]}[/] {mark}')
        return '\n'.join(out)


if __name__ == '__main__':
    ArcadePanel().run()
