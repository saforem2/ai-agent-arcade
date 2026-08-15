"""Pure-Python ICWS'94 Core War engine: Redcode parser + MARS simulator.

Scope (v1)
----------
Two warriors battle in a circular core of 8000 cells under the KOTH
standard variable set (draft section 4.3): core size 8000, max warrior
length 100, max 8000 processes per warrior, 80000 cycles before a tie,
minimum initial separation 100, core filled with ``DAT.F $0, $0``.
Instruction set: DAT MOV ADD SUB MUL DIV MOD JMP JMZ JMN DJN SPL SEQ
(CMP alias) SNE SLT NOP; addressing modes ``# $ @ < > * { }``;
modifiers ``.A .B .AB .BA .F .X .I``. The parser supports labels, EQU,
FOR/ROF, ``;`` comments, ``;redcode-94`` header lines,
``;name``/``;author`` metadata, and ORG/END start offsets.

Out of scope (documented, not implemented):

- P-space — LDP/STP are rejected with a clear error.
- ``;assert`` lines are parsed as comments but NOT enforced (assertion
  expressions use pMARS-only comparison/boolean operators; see below).
- Read/write distance limits equal the core size (unlimited), so the
  draft's Fold() is the identity and is omitted.
- Multi-line EQU continuation (a label-less ``EQU`` line) is rejected
  with a clear error.
- FOR counts must be constant expressions (numbers, EQU symbols,
  predefined labels); pMARS additionally allows labels declared before
  the FOR — this engine rejects them because its label table is built
  after expansion.
- Comparison (==, !=, <, ...) and boolean (&&, ||) operators in
  expressions are pMARS extensions and are not supported.

Parser strictness and deliberate pMARS divergences (all verified
against pMARS 0.9.2; none affect simulator semantics):

- Duplicate labels are a hard RedcodeError here; pMARS only warns and
  keeps the first definition.
- An operandless instruction line (``nop``) assembles with both
  operands $0 — deliberate leniency for agent-written warriors; pMARS
  rejects these. With a comma present, at least one operand is
  required (``mov ,`` errors); a comma with one blank side is treated
  exactly like the single-operand form (draft section 2.2: "the comma
  may be omitted"), so ``dat 5,`` == ``dat 5`` and ``mov , 5`` ==
  ``mov 5``.
- A single operand's missing counterpart is filled with #0 per draft
  section 2.4; pMARS uses $0. Both point the operand at the current
  instruction, so execution is identical; only the assembled mode byte
  differs.
- NOP's default modifier is .B per the draft's ICWS'88 conversion
  table (appendix A.2.1.2); pMARS assembles .F. The modifier is
  meaningless for NOP.
- Assembly is defensive: expression nesting, EQU chain depth, EQU
  expansion size, and FOR nesting/expansion are all capped, so
  pathological input raises a line-numbered RedcodeError instead of a
  RecursionError or a hang.

Spec provenance
---------------
Semantics follow the annotated Draft of the Proposed 1994 Core War
Standard, version 3.3 (Nov 1995), corewar.co.uk/standards/icws94.txt;
inline comments cite draft sections as "draft Sx.y". Two places where
the draft's sample C interpreter (EMI94) contradicts the draft text,
the text wins (both are known typos in the sample code):

- the ARITH macro swaps the .AB/.BA field pairing; section 5.4 and the
  (correct) ARITH_DIV macro pin .AB = "A-number of source to B-number
  of destination" — this engine follows the text;
- EMI94 queues the PC-relative RPA for jumps; the text (sections
  5.5.8-5.5.11, 5.5.15) says jumps queue "the sum of the program
  counter and the A-pointer" — this engine queues (PC + RPA) % M.

FOR/ROF is not part of the draft; it follows pMARS (doc/redcode.ref):
the last label on a FOR line is a 1-based loop index usable in
expressions inside the block, earlier labels alias the block's first
instruction, and ``name&index`` stringization produces per-iteration
labels (imp&N -> imp01) — with indices from ALL enclosing loops
available (x&i&j -> x0102), exactly as pMARS. An unstringized label
defined inside a loop body collides across iterations (hard
duplicate-label error here; pMARS merely warns).

Cycles, steps, and turns
------------------------
Draft section 4.2: "In each cycle, one instruction from each warrior is
executed." Here a *step* is one warrior executing one instruction
(Battle.step()); a *cycle* is both warriors stepping once. Warrior A
always moves first. A battle ends when a warrior's process queue
empties (elimination — the other warrior wins immediately, even
mid-cycle) or when MAX_CYCLES full cycles elapse with both warriors
alive (tie). BattleResult.cycles counts full cycles, so a tie always
reports cycles == MAX_CYCLES (80000).

Determinism
-----------
A battle is a pure function of (warrior A, warrior B, seed, offsets).
When an offset is not given explicitly it is drawn from
random.Random(seed); nothing else is random. Same seed + same sources
produce byte-identical transcripts and final state — the referee's
verification mechanism. Battle.fingerprint() hashes the full state.

Renderer contract
-----------------
Battle.step() returns a BattleEvent namedtuple:

    cycle      full cycles completed before this step (0-based)
    warrior    0 for A, 1 for B
    pc         absolute core address of the executed instruction
    opcode     e.g. "MOV"     modifier   e.g. "I"
    writes     tuple of absolute core addresses written this step, in
               chronological order (operand-evaluation side effects
               first: predecrement/postincrement targets, then the
               instruction's own writes; may contain duplicates)
    spawned    True if SPL added a process
    died       True if the executing process terminated (DAT, or
               DIV/MOD by zero)
    eliminated True if the warrior's process queue is now empty
               (battle over; Battle.winner is set)

The renderer re-simulates from the transcript: parse the same sources,
construct Battle with the same seed/offsets, and step at display speed.
"""

from __future__ import annotations

import hashlib
import random
import re
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

# KOTH standard variable set (draft section 4.3).
CORE_SIZE = 8000
MAX_WARRIOR_LEN = 100
MAX_PROCESSES = 8000
MAX_CYCLES = 80000
MIN_SEPARATION = 100

OPCODES = (
    "DAT", "MOV", "ADD", "SUB", "MUL", "DIV", "MOD",
    "JMP", "JMZ", "JMN", "DJN", "SPL", "SEQ", "SNE", "SLT", "NOP",
)
# CMP is the ICWS'88 name for SEQ (draft section 5.5.12); it is accepted
# and normalized to SEQ at assembly.
OPCODE_ALIASES = {"CMP": "SEQ"}
MODIFIERS = ("A", "B", "AB", "BA", "F", "X", "I")
MODES = "#$@<>*{}"
PSEUDO_OPS = ("ORG", "EQU", "END", "FOR", "ROF")

# Predefined labels (draft section 4.2), seeded as if defined by EQU at
# the start of the program; a warrior may redefine them.
PREDEFINED = {
    "CORESIZE": CORE_SIZE,
    "MAXCYCLES": MAX_CYCLES,
    "MAXLENGTH": MAX_WARRIOR_LEN,
    "MAXPROCESSES": MAX_PROCESSES,
    "MINDISTANCE": MIN_SEPARATION,
}


# Assembly safety caps: pathological input (thousands of nested parens,
# exponential EQU fan-out, deep FOR nests) must fail with a clean
# line-numbered RedcodeError, never a RecursionError or a hang. All
# limits are far beyond anything a 100-instruction warrior can need.
MAX_EXPR_DEPTH = 100       # paren/unary nesting in one expression
MAX_EQU_DEPTH = 100        # chained EQU references
MAX_EQU_TOKENS = 50000     # total EQU-expanded tokens per warrior
MAX_FOR_DEPTH = 50         # nested FOR/ROF blocks
MAX_FOR_LINES = 10000      # total FOR/ROF-expanded lines per warrior


class RedcodeError(Exception):
    """Raised for Redcode assembly/loading errors.

    The message carries a ``line N:`` prefix whenever the error is tied
    to a source line; ``lineno`` holds the 1-based line number or None.
    """

    def __init__(self, message: str, lineno: int | None = None):
        self.lineno = lineno
        if lineno is not None:
            message = f"line {lineno}: {message}"
        super().__init__(message)


class Instruction(NamedTuple):
    """One assembled MARS instruction. Field values are always stored
    normalized to 0..CORE_SIZE-1 (draft section 5.2: the loader converts
    every field value modulo the core size; this engine normalizes at
    assembly, which is equivalent)."""

    opcode: str    # one of OPCODES (SEQ, never the CMP alias)
    modifier: str  # one of MODIFIERS, always explicit after assembly
    a_mode: str    # one of MODES
    a_val: int
    b_mode: str
    b_val: int


# Core fill before warriors are loaded (draft section 4.3, KOTH set).
CORE_FILL = Instruction("DAT", "F", "$", 0, "$", 0)


@dataclass(frozen=True)
class Warrior:
    """An assembled Redcode program.

    name/author come from ;name/;author comment conventions (draft
    section 2.6) or the loader. start is the index into instructions of
    the first process (ORG/END operand, default 0). source is the
    verbatim original assembly text (used for hashing/staging)."""

    name: str
    author: str
    instructions: tuple
    start: int
    source: str


# --------------------------------------------------------------------------
# Classic dummy warriors (used by tests and by the arcade `spar` verb)
# --------------------------------------------------------------------------

IMP = """\
;redcode-94
;name Imp
;author A. K. Dewdney
;strategy Marches through core copying itself one cell forward.
        org     imp
imp     mov.i   $0, $1
        end
"""

DWARF = """\
;redcode-94
;name Dwarf
;author A. K. Dewdney
;strategy Bombs every fourth cell of core with a DAT bomb.
        org     dwarf
dwarf   add     #4, bomb
        mov     bomb, @bomb
        jmp     dwarf
bomb    dat     #0, #0
        end
"""


# --------------------------------------------------------------------------
# Tokenizer and expression evaluator
# --------------------------------------------------------------------------

# Names may carry a .modifier suffix (opcode tokens); every other
# punctuation character is a single-char token (modes, operators, &).
_TOKEN_RE = re.compile(r"[A-Za-z_]\w*(?:\.[A-Za-z]+)?|\d+|[^\w\s]")
_NAME_RE = re.compile(r"[A-Za-z_]\w*\Z")


def _tokenize(text: str, lineno: int) -> list:
    tokens = _TOKEN_RE.findall(text)
    if not tokens and text.strip():
        raise RedcodeError(f"could not tokenize {text.strip()!r}", lineno)
    return tokens


def _trunc_div(a: int, b: int) -> int:
    """C-style integer division (truncation toward zero), as pMARS does
    for assembly-time expressions. b must be non-zero."""
    q = abs(a) // abs(b)
    return q if (a < 0) == (b < 0) else -q


def _trunc_mod(a: int, b: int) -> int:
    """C-style remainder (sign of the dividend). b must be non-zero."""
    return a - _trunc_div(a, b) * b


class _Expr:
    """Recursive-descent evaluator for Redcode address expressions.

    Operators + - * / % with C precedence and left associativity,
    parentheses, unary +/-. The draft's own grammar (section 2.3) is
    acknowledged-flaky on precedence ("fix formal grammar" is on its
    to-do list, and its to-do also says to specify C precedence), so
    C precedence is used, matching pMARS. ``lookup`` resolves a name to
    an integer or raises RedcodeError."""

    def __init__(self, tokens: list, lookup, lineno: int):
        self.tokens = tokens
        self.pos = 0
        self.lookup = lookup
        self.lineno = lineno
        self.depth = 0

    def parse(self) -> int:
        if not self.tokens:
            raise RedcodeError("empty expression", self.lineno)
        value = self._addsub()
        if self.pos != len(self.tokens):
            raise RedcodeError(
                f"unexpected token {self.tokens[self.pos]!r} in expression", self.lineno
            )
        return value

    def _peek(self):
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def _next(self):
        tok = self._peek()
        self.pos += 1
        return tok

    def _descend(self):
        """Guard the two recursive descent points (unary sign, parens)
        against pathological nesting."""
        self.depth += 1
        if self.depth > MAX_EXPR_DEPTH:
            raise RedcodeError(
                f"expression nested too deeply (max {MAX_EXPR_DEPTH})", self.lineno
            )

    def _addsub(self) -> int:
        value = self._muldiv()
        while self._peek() in ("+", "-"):
            op = self._next()
            rhs = self._muldiv()
            value = value + rhs if op == "+" else value - rhs
        return value

    def _muldiv(self) -> int:
        value = self._unary()
        while self._peek() in ("*", "/", "%"):
            op = self._next()
            rhs = self._unary()
            if op == "*":
                value = value * rhs
            elif rhs == 0:
                raise RedcodeError("division by zero in expression", self.lineno)
            elif op == "/":
                value = _trunc_div(value, rhs)
            else:
                value = _trunc_mod(value, rhs)
        return value

    def _unary(self) -> int:
        if self._peek() in ("+", "-"):
            neg = self._next() == "-"
            self._descend()
            value = self._unary()
            self.depth -= 1
            return -value if neg else value
        return self._primary()

    def _primary(self) -> int:
        tok = self._next()
        if tok is None:
            raise RedcodeError("unexpected end of expression", self.lineno)
        if tok == "(":
            self._descend()
            value = self._addsub()
            if self._next() != ")":
                raise RedcodeError("missing ')' in expression", self.lineno)
            self.depth -= 1
            return value
        if tok.isdigit():
            return int(tok)
        if _NAME_RE.fullmatch(tok):
            return self.lookup(tok)
        raise RedcodeError(f"unexpected token {tok!r} in expression", self.lineno)


def _substitute_equ(tokens: list, equs: dict, lineno: int, chain: tuple = (),
                    budget: list | None = None) -> list:
    """Recursively replace tokens that name an EQU symbol with its
    replacement tokens (draft section 2.5: simple text substitution).

    ``budget`` is a shared one-element countdown of total expanded
    tokens per warrior: EQU fan-out is exponential in the chain length,
    so the budget (plus the chain depth cap) is what stands between a
    hostile warrior and an hour-long hang."""
    if budget is None:
        budget = [MAX_EQU_TOKENS]
    out = []
    for tok in tokens:
        if _NAME_RE.fullmatch(tok) and tok in equs:
            if tok in chain:
                raise RedcodeError(f"recursive EQU reference {tok!r}", lineno)
            if len(chain) >= MAX_EQU_DEPTH:
                raise RedcodeError(
                    f"EQU substitution nested too deeply (max {MAX_EQU_DEPTH})", lineno
                )
            out.extend(_substitute_equ(equs[tok], equs, lineno, chain + (tok,), budget))
        else:
            out.append(tok)
            # Only leaf tokens consume budget; substituted tokens were
            # already accounted inside the recursive call.
            budget[0] -= 1
            if budget[0] < 0:
                raise RedcodeError(
                    f"EQU expansion too large (>{MAX_EQU_TOKENS} tokens)", lineno
                )
    return out


# --------------------------------------------------------------------------
# Redcode parser
# --------------------------------------------------------------------------

_EQU_RE = re.compile(r"\s*([A-Za-z_]\w*)\s+EQU\b(.*)\Z", re.IGNORECASE)
_OP_RE = re.compile(r"([A-Za-z]+)(?:\.([A-Za-z]+))?\Z")
_OPCODE_BASES = frozenset(OPCODES) | frozenset(OPCODE_ALIASES)
_RESERVED = _OPCODE_BASES | frozenset(PSEUDO_OPS) | {"LDP", "STP"}


def _split_op_token(tok: str, lineno: int) -> tuple:
    """Split an opcode[.modifier] token, normalizing case and aliases."""
    m = _OP_RE.fullmatch(tok)
    if not m:
        raise RedcodeError(f"expected opcode, got {tok!r}", lineno)
    base = m.group(1).upper()
    if base in ("LDP", "STP"):
        raise RedcodeError(
            f"{base} is not supported: this engine has no P-space (v1 scope)", lineno
        )
    if base in PSEUDO_OPS:
        raise RedcodeError(f"misplaced pseudo-op {base}", lineno)
    if base not in _OPCODE_BASES:
        raise RedcodeError(f"unknown opcode {m.group(1)!r}", lineno)
    modifier = m.group(2).upper() if m.group(2) else None
    if modifier is not None and modifier not in MODIFIERS:
        raise RedcodeError(f"unknown modifier '.{m.group(2)}'", lineno)
    return OPCODE_ALIASES.get(base, base), modifier


def _default_modifier(opcode: str, a_mode: str, b_mode: str) -> str:
    """Default modifier when none is written, per the draft's ICWS'88
    conversion table (draft appendix A.2.1.2, the default per A.2.1)."""
    if opcode == "DAT":
        return "F"
    if opcode in ("MOV", "SEQ", "SNE"):
        if a_mode == "#":
            return "AB"
        if b_mode == "#":
            return "B"
        return "I"
    if opcode in ("ADD", "SUB", "MUL", "DIV", "MOD"):
        if a_mode == "#":
            return "AB"
        if b_mode == "#":
            return "B"
        return "F"
    if opcode == "SLT":
        return "AB" if a_mode == "#" else "B"
    # JMP, JMZ, JMN, DJN, SPL, NOP
    return "B"


class _ForBlock(NamedTuple):
    """An unexpanded FOR/ROF block collected during the statement walk.
    Expansion is deferred until the whole file is read so that nested
    loops expand against the full index environment (pMARS stringization
    may reference indices of ANY enclosing loop)."""

    lineno: int
    start_labels: tuple
    index_label: str | None
    count: int
    body: tuple  # items: (lineno, text) tuples or nested _ForBlocks


def _env_lookup(env: list, name: str) -> int | None:
    """The innermost FOR index binding wins."""
    for label, val in reversed(env):
        if label == name:
            return val
    return None


def _apply_for_env(tokens: list, env: list, lineno: int) -> list:
    """Apply the active FOR index environment to one body line (pMARS
    semantics): an index label used as a bare token becomes its 1-based
    value, and name&idx[&idx...] stringization becomes nameNN[NN...]
    with each idx substituted from any enclosing loop, zero-padded
    (x&i&j with i=2, j=1 becomes x0201)."""
    out = []
    k = 0
    while k < len(tokens):
        tok = tokens[k]
        if tok == "&":
            raise RedcodeError("dangling '&' in FOR/ROF body", lineno)
        if (
            _NAME_RE.fullmatch(tok)
            and k + 1 < len(tokens)
            and tokens[k + 1] == "&"
        ):
            # stringization: name&idx[&idx...]
            parts = []
            m = k + 1
            while m < len(tokens) and tokens[m] == "&":
                name = tokens[m + 1] if m + 1 < len(tokens) else None
                if name is None:
                    raise RedcodeError("dangling '&' in FOR/ROF body", lineno)
                val = _env_lookup(env, name)
                if val is None:
                    raise RedcodeError(
                        f"'{name}' after '&' is not an active FOR index", lineno
                    )
                parts.append(f"{val:02d}")
                m += 2
            out.append(tok + "".join(parts))
            k = m
            continue
        val = _env_lookup(env, tok) if _NAME_RE.fullmatch(tok) else None
        out.append(str(val) if val is not None else tok)
        k += 1
    return out


def _expand_for(items: list, env: list, out: list, depth: int = 0) -> None:
    """Flatten the statement list, expanding FOR blocks against the
    index environment. The expanded LINE count is capped so hostile
    nesting cannot exhaust memory; the 100-instruction limit itself is
    enforced in pass 2 (label-only lines do not count toward it)."""
    for item in items:
        if isinstance(item, _ForBlock):
            if depth >= MAX_FOR_DEPTH:
                raise RedcodeError(
                    f"FOR/ROF nested too deeply (max {MAX_FOR_DEPTH})", item.lineno
                )
            if item.count <= 0 or not item.body:
                # FOR 0 emits nothing; block labels bind to whatever follows.
                if item.start_labels:
                    out.append((item.lineno, " ".join(item.start_labels)))
                continue
            for iteration in range(1, item.count + 1):
                iter_lines: list = []
                sub_env = (
                    env + [(item.index_label, iteration)]
                    if item.index_label
                    else env
                )
                _expand_for(item.body, sub_env, iter_lines, depth + 1)
                if iteration == 1 and item.start_labels:
                    if iter_lines:
                        ln, text = iter_lines[0]
                        iter_lines[0] = (ln, " ".join(item.start_labels) + " " + text)
                    else:
                        iter_lines.append((item.lineno, " ".join(item.start_labels)))
                out.extend(iter_lines)
                if len(out) > MAX_FOR_LINES:
                    raise RedcodeError(
                        f"FOR/ROF expansion too large (>{MAX_FOR_LINES} lines)",
                        item.lineno,
                    )
        else:
            lineno, text = item
            expanded = _apply_for_env(_tokenize(text, lineno), env, lineno)
            out.append((lineno, " ".join(expanded)))
            if len(out) > MAX_FOR_LINES:
                raise RedcodeError(
                    f"FOR/ROF expansion too large (>{MAX_FOR_LINES} lines)", lineno
                )


def _eval_const(tokens: list, equs: dict, lineno: int, what: str, budget: list) -> int:
    """Evaluate a constant expression (FOR counts): EQU symbols and
    predefined labels only, no instruction labels."""
    tokens = _substitute_equ(tokens, equs, lineno, budget=budget)

    def lookup(name):
        raise RedcodeError(f"{what} must be a constant expression, got label {name!r}", lineno)

    return _Expr(tokens, lookup, lineno).parse()


def parse_warrior(source: str, name: str | None = None) -> Warrior:
    """Assemble Redcode source into a Warrior. Raises RedcodeError
    (with a line number whenever possible) on any assembly problem."""
    if not isinstance(source, str) or not source.strip():
        raise RedcodeError("warrior source is empty")

    # Newlines: draft section 2.3 accepts LF, CR, LF CR, and CR LF.
    text = source.replace("\r\n", "\n").replace("\r", "\n")

    # -- collect statements: strip comments, capture metadata, stop at END --
    meta_name = None
    meta_author = None
    raw = []  # (lineno, code-without-comment)
    for lineno, line in enumerate(text.split("\n"), 1):
        code, _, comment = line.partition(";")
        stripped = code.strip()
        if not stripped:
            directive, _, rest = comment.strip().partition(" ")
            directive = directive.lower()
            if directive == "name" and meta_name is None:
                meta_name = rest.strip()
            elif directive == "author" and meta_author is None:
                meta_author = rest.strip()
            continue
        raw.append((lineno, stripped))
        # Draft section 2.5: everything after the line containing END is
        # ignored (pMARS stops reading at a line containing a word END).
        if any(word.upper() == "END" for word in stripped.split()):
            break

    # -- statement walk: EQU, FOR/ROF, ORG, END; FOR expansion is deferred
    # (blocks are collected, then expanded against the full index
    # environment) --
    equs = {key: [str(val)] for key, val in PREDEFINED.items()}
    equ_budget = [MAX_EQU_TOKENS]  # shared across the whole warrior
    program = []  # (lineno, text) tuples and _ForBlocks
    frames = []  # open FOR frames: [lineno, start_labels, index_label, count, body]
    org_tokens = None  # last ORG wins (draft section 2.5)
    end_tokens = None

    def emit(lineno, tokens):
        target = frames[-1][4] if frames else program
        target.append((lineno, " ".join(tokens)))

    for lineno, code in raw:
        tokens = _tokenize(code, lineno)
        equ_match = _EQU_RE.match(code)
        first_upper = tokens[0].upper() if tokens else ""

        if equ_match:
            # "label EQU text": text substitution for all subsequent
            # occurrences (draft section 2.5); replacement may be empty.
            equ_name = equ_match.group(1)
            if equ_name.upper() in _RESERVED:
                raise RedcodeError(
                    f"reserved word {equ_name!r} cannot be redefined with EQU", lineno
                )
            equs[equ_name] = _tokenize(equ_match.group(2), lineno)
        elif first_upper == "EQU":
            raise RedcodeError("EQU requires a label (multi-line EQU is not supported)", lineno)
        elif first_upper == "ROF":
            if not frames:
                raise RedcodeError("ROF without a matching FOR", lineno)
            for_lineno, start_labels, index_label, count, body = frames.pop()
            block = _ForBlock(for_lineno, tuple(start_labels), index_label, count,
                              tuple(body))
            (frames[-1][4] if frames else program).append(block)
        elif "FOR" in [tok.upper() for tok in tokens]:
            for_pos = [tok.upper() for tok in tokens].index("FOR")
            for_labels = tokens[:for_pos]
            if not tokens[for_pos + 1 :]:
                raise RedcodeError("FOR requires a repetition count", lineno)
            for lab in for_labels:
                if not _NAME_RE.fullmatch(lab) or lab.upper() in _RESERVED:
                    raise RedcodeError(f"bad FOR-line label {lab!r}", lineno)
            count = _eval_const(tokens[for_pos + 1 :], equs, lineno, "FOR count",
                                equ_budget)
            if count < 0:
                raise RedcodeError("FOR count must not be negative", lineno)
            # pMARS: the LAST label on a FOR line is the loop index
            # (1-based); earlier labels alias the block's first instruction.
            index_label = for_labels[-1] if for_labels else None
            start_labels = for_labels[:-1]
            frames.append([lineno, start_labels, index_label, count, []])
        elif first_upper == "ORG":
            org_tokens = (lineno, _substitute_equ(tokens[1:], equs, lineno,
                                                  budget=equ_budget))
            if not org_tokens[1]:
                raise RedcodeError("ORG requires an operand", lineno)
        elif first_upper == "END":
            end_tokens = (lineno, _substitute_equ(tokens[1:], equs, lineno,
                                                  budget=equ_budget))
            break  # draft section 2.5: the rest of the file is ignored
        else:
            emit(lineno, _substitute_equ(tokens, equs, lineno, budget=equ_budget))

    if frames:
        raise RedcodeError("FOR without a matching ROF", frames[-1][0])

    # -- expand FOR/ROF blocks to a flat (lineno, text) program --
    flat = []
    _expand_for(program, [], flat)

    # -- pass 1: collect labels, split instructions --
    labels = {}
    parsed = []  # (lineno, opcode, modifier, a_tokens, b_tokens) — b None if no comma
    pending = []  # labels waiting for an instruction (label-only lines)
    for lineno, text in flat:
        tokens = _tokenize(text, lineno)
        line_labels = []
        while tokens:
            tok = tokens[0]
            base = tok.split(".")[0].upper()
            if base in _OPCODE_BASES or base in ("LDP", "STP"):
                break
            if not _NAME_RE.fullmatch(tok):
                raise RedcodeError(f"expected label or opcode, got {tok!r}", lineno)
            if len(tokens) > 1 and not any(
                t.split(".")[0].upper() in _OPCODE_BASES
                or t.split(".")[0].upper() in ("LDP", "STP")
                for t in tokens[1:]
            ):
                # No opcode anywhere later on the line: this token sits in
                # opcode position (a typo'd opcode, most likely) — leave it
                # to _split_op_token so the error names it as such.
                break
            if tok.upper() in _RESERVED:
                raise RedcodeError(f"reserved word {tok!r} cannot be used as a label", lineno)
            line_labels.append(tok)
            tokens.pop(0)
        if not tokens:
            pending.extend(line_labels)  # draft section 2.3: label_list may span lines
            continue
        op_tok = tokens.pop(0)
        opcode, modifier = _split_op_token(op_tok, lineno)
        commas = [i for i, tok in enumerate(tokens) if tok == ","]
        if len(commas) > 1:
            raise RedcodeError("too many commas", lineno)
        if commas:
            a_tokens, b_tokens = tokens[: commas[0]], tokens[commas[0] + 1 :]
        else:
            a_tokens, b_tokens = tokens, None
        for lab in pending + line_labels:
            if lab in labels:
                raise RedcodeError(f"duplicate label {lab!r}", lineno)
            labels[lab] = len(parsed)
        pending = []
        parsed.append((lineno, opcode, modifier, a_tokens, b_tokens))
    for lab in pending:
        # Labels after the last instruction bind one past the end.
        if lab in labels:
            raise RedcodeError(f"duplicate label {lab!r}", lineno)
        labels[lab] = len(parsed)

    if not parsed:
        raise RedcodeError("warrior has no instructions")
    if len(parsed) > MAX_WARRIOR_LEN:
        raise RedcodeError(
            f"warrior has {len(parsed)} instructions (max {MAX_WARRIOR_LEN})"
        )

    # -- pass 2: assemble instructions (labels resolve PC-relative, draft
    # section 2.4) --
    def parse_operand(op_tokens, cur_index, lineno):
        if not op_tokens:
            return None
        mode = "$"  # blank mode assembles as '$' (draft section 2.4)
        if op_tokens[0] in MODES:
            mode = op_tokens.pop(0)
        if not op_tokens:
            raise RedcodeError(f"missing value after mode {mode!r}", lineno)

        def lookup(name):
            if name in labels:
                return labels[name] - cur_index
            raise RedcodeError(f"undefined symbol {name!r}", lineno)

        return mode, _Expr(op_tokens, lookup, lineno).parse()

    instructions = []
    for index, (lineno, opcode, modifier, a_tokens, b_tokens) in enumerate(parsed):
        if b_tokens is None and not a_tokens:
            # Opcode-only line: deliberate engine leniency — both operands
            # $0. (pMARS REJECTS these; the draft grammar calls two blank
            # operands invalid. We accept them so agent-written warriors
            # like a bare `nop` assemble.)
            a_mode, a_val = "$", 0
            b_mode, b_val = "$", 0
        elif b_tokens is None or not a_tokens or not b_tokens:
            if b_tokens is not None and not a_tokens and not b_tokens:
                # A comma but no operands at all ("mov ,") — invalid even
                # under our leniency (draft section 2.2).
                raise RedcodeError("operands may not both be blank", lineno)
            # Single operand (draft section 2.4): for DAT it goes to the
            # B-field with A = #0; for everything else it goes to the
            # A-field with B = #0. A comma with one blank side is treated
            # the same way (draft section 2.2: "the comma may be
            # omitted"), so "dat 5," == "dat 5" and "mov , 5" == "mov 5".
            side = a_tokens if b_tokens is None else (a_tokens or b_tokens)
            if opcode == "DAT":
                a_mode, a_val = "#", 0
                b_mode, b_val = parse_operand(list(side), index, lineno)
            else:
                a_mode, a_val = parse_operand(list(side), index, lineno)
                b_mode, b_val = "#", 0
        else:
            a_mode, a_val = parse_operand(a_tokens, index, lineno)
            b_mode, b_val = parse_operand(b_tokens, index, lineno)
        if modifier is None:
            modifier = _default_modifier(opcode, a_mode, b_mode)
        instructions.append(
            Instruction(
                opcode, modifier, a_mode, a_val % CORE_SIZE, b_mode, b_val % CORE_SIZE
            )
        )

    # -- start offset: END operand wins over ORG, else ORG, else 0 --
    start = 0
    start_spec = end_tokens if (end_tokens and end_tokens[1]) else org_tokens
    if start_spec and start_spec[1]:
        start_lineno, start_tokens = start_spec

        def abs_lookup(name):
            if name in labels:
                return labels[name]  # absolute index for ORG/END
            raise RedcodeError(f"undefined symbol {name!r}", start_lineno)

        start = _Expr(list(start_tokens), abs_lookup, start_lineno).parse()
        if not 0 <= start < len(instructions):
            raise RedcodeError(
                f"start offset {start} is out of range (warrior has "
                f"{len(instructions)} instructions)",
                start_lineno,
            )

    return Warrior(
        name=name if name is not None else (meta_name or ""),
        author=meta_author or "",
        instructions=tuple(instructions),
        start=start,
        source=source,
    )


def format_instruction(ins: Instruction) -> str:
    """Canonical text form of one assembled instruction, e.g.
    ``MOV.I $0, $1``. parse_warrior(format_instruction(...)) round-trips
    at the Instruction-tuple level (values are printed normalized)."""
    return f"{ins.opcode}.{ins.modifier} {ins.a_mode}{ins.a_val}, {ins.b_mode}{ins.b_val}"


# --------------------------------------------------------------------------
# MARS simulator
# --------------------------------------------------------------------------

class BattleEvent(NamedTuple):
    """Record of one executed step (one warrior's turn). See the module
    docstring's "Renderer contract" for field semantics."""

    cycle: int
    warrior: int
    pc: int
    opcode: str
    modifier: str
    writes: tuple
    spawned: bool
    died: bool
    eliminated: bool


class BattleResult(NamedTuple):
    """Outcome of a completed battle.

    winner: 'A', 'B', or None for a tie. cycles: full cycles elapsed
    (both warriors moved once per cycle); a tie reports MAX_CYCLES.
    steps: total single-warrior turns executed. procs_a/procs_b:
    surviving process counts."""

    winner: str | None
    cycles: int
    steps: int
    procs_a: int
    procs_b: int
    off_a: int
    off_b: int
    seed: int


# Field pairs per modifier for MOV/arithmetic, as (source field, dest
# field) with 0 = A-field, 1 = B-field (draft section 5.4). .I behaves
# as .F for arithmetic (draft sections 5.5.3-5.5.7).
_FIELD_PAIRS = {
    "A": ((0, 0),),
    "B": ((1, 1),),
    "AB": ((0, 1),),
    "BA": ((1, 0),),
    "F": ((0, 0), (1, 1)),
    "I": ((0, 0), (1, 1)),
    "X": ((0, 1), (1, 0)),
}

# Fields of the B-instruction tested by JMZ/JMN/DJN (draft sections
# 5.5.9-5.5.11): .A/.BA test the A-number, .B/.AB the B-number,
# .F/.X/.I both.
_TEST_FIELDS = {
    "A": (0,), "BA": (0,),
    "B": (1,), "AB": (1,),
    "F": (0, 1), "X": (0, 1), "I": (0, 1),
}


class Battle:
    """One Core War battle between two assembled warriors.

    Battle(warrior_a, warrior_b, seed=0, off_a=None, off_b=None).
    Offsets not given are drawn from random.Random(seed) with circular
    separation in [MIN_SEPARATION, CORE_SIZE - MIN_SEPARATION]; explicit
    offsets are validated against the same separation and against body
    overlap (ValueError). Warrior A moves first.
    """

    def __init__(
        self,
        warrior_a: Warrior,
        warrior_b: Warrior,
        seed: int = 0,
        off_a: int | None = None,
        off_b: int | None = None,
    ):
        for tag, warrior in (("A", warrior_a), ("B", warrior_b)):
            if not 1 <= len(warrior.instructions) <= MAX_WARRIOR_LEN:
                raise ValueError(
                    f"warrior {tag} has {len(warrior.instructions)} instructions "
                    f"(max {MAX_WARRIOR_LEN})"
                )
            if not 0 <= warrior.start < len(warrior.instructions):
                raise ValueError(f"warrior {tag} start offset out of range")

        self.warriors = (warrior_a, warrior_b)
        self.seed = seed
        rng = random.Random(seed)
        if off_a is None:
            off_a = rng.randrange(CORE_SIZE)
        if off_b is None:
            span = CORE_SIZE - 2 * MIN_SEPARATION + 1
            off_b = (off_a + MIN_SEPARATION + rng.randrange(span)) % CORE_SIZE
        self._check_offsets(warrior_a, warrior_b, off_a, off_b)
        self.off_a = off_a
        self.off_b = off_b

        core = [CORE_FILL] * CORE_SIZE
        for i, ins in enumerate(warrior_a.instructions):
            core[(off_a + i) % CORE_SIZE] = ins
        for i, ins in enumerate(warrior_b.instructions):
            core[(off_b + i) % CORE_SIZE] = ins
        self.core = core
        self.procs = [
            deque([(off_a + warrior_a.start) % CORE_SIZE]),
            deque([(off_b + warrior_b.start) % CORE_SIZE]),
        ]
        self.turn = 0       # warrior to move: 0 = A, 1 = B
        self.cycles = 0     # full cycles completed (both warriors moved)
        self.steps = 0      # single-warrior turns executed
        self.over = False
        self.winner = None  # 0, 1, or None (tie / still running)
        self.max_cycles = MAX_CYCLES
        self.max_processes = MAX_PROCESSES

    @staticmethod
    def _check_offsets(warrior_a, warrior_b, off_a, off_b):
        for tag, off in (("A", off_a), ("B", off_b)):
            if not 0 <= off < CORE_SIZE:
                raise ValueError(f"offset {tag}={off} out of range 0..{CORE_SIZE - 1}")
        gap_ab = (off_b - off_a) % CORE_SIZE
        gap_ba = (off_a - off_b) % CORE_SIZE
        if min(gap_ab, gap_ba) < MIN_SEPARATION:
            raise ValueError(
                f"warrior separation {min(gap_ab, gap_ba)} is below the "
                f"minimum {MIN_SEPARATION}"
            )
        if gap_ab < len(warrior_a.instructions) or gap_ba < len(warrior_b.instructions):
            raise ValueError("warrior bodies overlap in core")

    # -- operand evaluation -------------------------------------------------

    def _eval_operand(self, pc: int, mode: str, num: int, writes: list) -> tuple:
        """Evaluate one operand; returns (PC-relative pointer, instruction
        copy). Mirrors the draft's EMI94 reference interpreter (draft
        sections 5.2 steps 3-6 and 5.3): predecrement updates core before
        the secondary offset is read; postincrement updates core after the
        instruction copy is taken. Side-effect writes are appended to
        ``writes``."""
        if mode == "#":
            # Immediate: the pointer is 0, i.e. the instruction itself
            # (draft section 5.3.1). Read core fresh: an earlier side
            # effect this step may have rewritten the cell at PC.
            return 0, self.core[pc]
        ptr = num  # direct (draft section 5.3.2)
        if mode != "$":
            inter = (pc + num) % CORE_SIZE
            ins = self.core[inter]
            if mode == "<":  # B-number predecrement indirect (section 5.3.6)
                ins = ins._replace(b_val=(ins.b_val - 1) % CORE_SIZE)
                self.core[inter] = ins
                writes.append(inter)
                sec = ins.b_val
            elif mode == "{":  # A-number predecrement indirect (5.3.5)
                ins = ins._replace(a_val=(ins.a_val - 1) % CORE_SIZE)
                self.core[inter] = ins
                writes.append(inter)
                sec = ins.a_val
            elif mode == ">":  # B-number postincrement indirect (5.3.8)
                sec = ins.b_val
            elif mode == "}":  # A-number postincrement indirect (5.3.7)
                sec = ins.a_val
            elif mode == "@":  # B-number indirect (5.3.4)
                sec = ins.b_val
            else:  # mode == "*": A-number indirect (5.3.3)
                sec = ins.a_val
            ptr = (num + sec) % CORE_SIZE
        target = (pc + ptr) % CORE_SIZE
        instr = self.core[target]
        if mode in ">}":
            # Postincrement: bump the intermediate cell AFTER the copy is
            # taken (draft sections 5.3.7-5.3.8).
            ins = self.core[inter]
            if mode == ">":
                ins = ins._replace(b_val=(ins.b_val + 1) % CORE_SIZE)
            else:
                ins = ins._replace(a_val=(ins.a_val + 1) % CORE_SIZE)
            self.core[inter] = ins
            writes.append(inter)
        return ptr, instr

    # -- execution ----------------------------------------------------------

    def step(self) -> BattleEvent | None:
        """Execute one warrior's turn (one instruction). Returns a
        BattleEvent, or None if the battle is already over."""
        if self.over:
            return None
        w = self.turn
        queue = self.procs[w]
        core = self.core
        pc = queue.popleft()
        ir = core[pc]  # instruction register: copied once, before evaluation
        writes = []
        rpa, ira = self._eval_operand(pc, ir.a_mode, ir.a_val, writes)
        rpb, irb = self._eval_operand(pc, ir.b_mode, ir.b_val, writes)

        op = ir.opcode
        mod = ir.modifier
        nxt = (pc + 1) % CORE_SIZE
        jump = (pc + rpa) % CORE_SIZE  # draft text: PC + A-pointer
        dest = (pc + rpb) % CORE_SIZE
        spawned = False
        died = False
        requeue = nxt  # most instructions queue PC + 1

        if op == "DAT":
            # No further processing; the task is not requeued (5.5.1).
            died = True
            requeue = None
        elif op == "MOV":
            # MOV replaces the B-target with the A-value (5.5.2).
            if mod == "I":
                core[dest] = ira
            else:
                cur = core[dest]
                vals = [cur.a_val, cur.b_val]
                src = (ira.a_val, ira.b_val)
                for s, d in _FIELD_PAIRS[mod]:
                    vals[d] = src[s]
                core[dest] = cur._replace(a_val=vals[0], b_val=vals[1])
            writes.append(dest)
        elif op in ("ADD", "SUB", "MUL", "DIV", "MOD"):
            died = self._arith(op, mod, dest, ira, irb, writes)
            requeue = None if died else nxt
        elif op == "JMP":
            requeue = jump  # 5.5.8
        elif op in ("JMZ", "JMN"):
            fields = _TEST_FIELDS[mod]
            tested = (irb.a_val, irb.b_val)
            if op == "JMZ":
                # .F/.X/.I: jump if BOTH numbers are zero (5.5.9).
                cond = all(tested[f] == 0 for f in fields)
            else:
                # .F/.X/.I: jump if EITHER number is non-zero (5.5.10,
                # v3.3: the negation of the JMZ.F condition).
                cond = any(tested[f] != 0 for f in fields)
            requeue = jump if cond else nxt
        elif op == "DJN":
            # Decrement the B-target field(s), then jump if the
            # decremented value is non-zero; .F/.X/.I decrement both and
            # jump if either is non-zero (5.5.11, v3.3). Like EMI94, the
            # tested values come from the IRB register copy.
            cur = core[dest]
            vals = [cur.a_val, cur.b_val]
            tested = [irb.a_val, irb.b_val]
            fields = _TEST_FIELDS[mod]
            for f in fields:
                vals[f] = (vals[f] - 1) % CORE_SIZE
                tested[f] = (tested[f] - 1) % CORE_SIZE
            core[dest] = cur._replace(a_val=vals[0], b_val=vals[1])
            writes.append(dest)
            requeue = jump if any(tested[f] != 0 for f in fields) else nxt
        elif op in ("SEQ", "SNE"):
            # Skip PC+2 if the values compare equal (SEQ) / not equal
            # (SNE); .F/.X/.I compare field pairs, .I whole instructions
            # (5.5.12-5.5.13). SNE is the exact negation of SEQ.
            equal = self._seq_condition(mod, ira, irb)
            if op == "SNE":
                equal = not equal
            requeue = (pc + 2) % CORE_SIZE if equal else nxt
        elif op == "SLT":
            # Skip PC+2 if A-value < B-value; .F/.I: both pairs; .X:
            # crosswise (5.5.14). Values are unsigned 0..M-1.
            if mod == "A":
                cond = ira.a_val < irb.a_val
            elif mod == "B":
                cond = ira.b_val < irb.b_val
            elif mod == "AB":
                cond = ira.a_val < irb.b_val
            elif mod == "BA":
                cond = ira.b_val < irb.a_val
            elif mod == "X":
                cond = ira.a_val < irb.b_val and ira.b_val < irb.a_val
            else:  # F, I
                cond = ira.a_val < irb.a_val and ira.b_val < irb.b_val
            requeue = (pc + 2) % CORE_SIZE if cond else nxt
        elif op == "SPL":
            # Queue PC+1 first, then the split-off target — but only if
            # the queue has room (5.5.15: "If the queue is full, only the
            # next instruction is queued").
            queue.append(nxt)
            if len(queue) < self.max_processes:
                queue.append(jump)
                spawned = True
            requeue = None  # already queued inline
        elif op == "NOP":
            requeue = nxt  # 5.5.16
        else:  # pragma: no cover - parser guarantees a known opcode
            raise AssertionError(f"unhandled opcode {op!r}")

        if requeue is not None:
            queue.append(requeue)

        eliminated = not queue
        if eliminated:
            self.over = True
            self.winner = 1 - w
        event = BattleEvent(
            cycle=self.cycles,
            warrior=w,
            pc=pc,
            opcode=op,
            modifier=mod,
            writes=tuple(writes),
            spawned=spawned,
            died=died,
            eliminated=eliminated,
        )
        self.steps += 1
        if w == 1:
            self.cycles += 1
            if not self.over and self.cycles >= self.max_cycles:
                self.over = True  # winner stays None: tie (draft section 4.2)
        self.turn = 1 - w
        return event

    def _arith(self, op, mod, dest, ira, irb, writes) -> bool:
        """ADD/SUB/MUL/DIV/MOD execution. Returns True if the process
        dies (DIV/MOD with a zero divisor component; draft sections
        5.5.6-5.5.7: that component is unchanged, non-zero components are
        still written, and the task is removed from the queue)."""
        cur = self.core[dest]
        vals = [cur.a_val, cur.b_val]
        src = (ira.a_val, ira.b_val)
        dst = (irb.a_val, irb.b_val)
        died = False
        for s, d in _FIELD_PAIRS[mod]:
            if op == "ADD":
                vals[d] = (dst[d] + src[s]) % CORE_SIZE
            elif op == "SUB":
                vals[d] = (dst[d] - src[s]) % CORE_SIZE
            elif op == "MUL":
                vals[d] = (dst[d] * src[s]) % CORE_SIZE
            elif src[s] == 0:
                died = True  # DIV/MOD by zero: field unchanged, task dies
            elif op == "DIV":
                vals[d] = dst[d] // src[s]
            else:  # MOD
                vals[d] = dst[d] % src[s]
        self.core[dest] = cur._replace(a_val=vals[0], b_val=vals[1])
        writes.append(dest)
        return died

    @staticmethod
    def _seq_condition(mod, ira, irb) -> bool:
        if mod == "A":
            return ira.a_val == irb.a_val
        if mod == "B":
            return ira.b_val == irb.b_val
        if mod == "AB":
            return ira.a_val == irb.b_val
        if mod == "BA":
            return ira.b_val == irb.a_val
        if mod == "F":
            return ira.a_val == irb.a_val and ira.b_val == irb.b_val
        if mod == "X":
            return ira.a_val == irb.b_val and ira.b_val == irb.a_val
        return ira == irb  # .I: whole-instruction compare

    # -- driving ------------------------------------------------------------

    def run(self) -> BattleResult:
        """Step until elimination or the cycle limit, then return the
        result."""
        while not self.over:
            self.step()
        return self.result()

    def result(self) -> BattleResult:
        """Current outcome; winner is None for a tie or an unfinished
        battle."""
        winner = None if self.winner is None else ("A" if self.winner == 0 else "B")
        return BattleResult(
            winner=winner,
            cycles=self.cycles,
            steps=self.steps,
            procs_a=len(self.procs[0]),
            procs_b=len(self.procs[1]),
            off_a=self.off_a,
            off_b=self.off_b,
            seed=self.seed,
        )

    def fingerprint(self) -> str:
        """SHA-256 over cycles/steps/turn/winner, every core cell, and
        both process queues — the full battle state. Two battles with the
        same warriors, seed, and offsets always produce the same
        fingerprint after the same number of steps."""
        h = hashlib.sha256()
        h.update(f"{self.cycles}:{self.steps}:{self.turn}:{self.winner}\n".encode())
        for ins in self.core:
            h.update(format_instruction(ins).encode("ascii"))
            h.update(b"\n")
        h.update(repr(tuple(self.procs[0])).encode())
        h.update(repr(tuple(self.procs[1])).encode())
        return h.hexdigest()


# --------------------------------------------------------------------------
# Referee / renderer helpers
# --------------------------------------------------------------------------

def load_warrior_file(path) -> Warrior:
    """Read and assemble a .red warrior file. The warrior name falls
    back to the file stem when no ;name directive is present."""
    path = Path(path)
    source = path.read_text(encoding="utf-8")
    warrior = parse_warrior(source)
    if not warrior.name:
        warrior = Warrior(
            name=path.stem,
            author=warrior.author,
            instructions=warrior.instructions,
            start=warrior.start,
            source=warrior.source,
        )
    return warrior


def sha256_warrior(source: str) -> str:
    """Content hash of a warrior source. Line endings are normalized to
    LF before hashing so CRLF and LF copies hash identically."""
    normalized = source.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def validate_warrior(source: str) -> list:
    """Human-readable problems with a warrior source; empty list = OK
    to stage."""
    try:
        parse_warrior(source)
    except RedcodeError as exc:
        return [str(exc)]
    return []


def battle_transcript(seed: int, off_a: int, off_b: int, result: BattleResult,
                      round_no: int = 1) -> str:
    """The moves.txt token lines for one round (see the arcade plan):
    ``ROUND n seed=<s> off=<a>,<b>`` then ``ROUND n OUT <1-0|0-1|tie>
    cycles=<n>``."""
    if result.winner == "A":
        score = "1-0"
    elif result.winner == "B":
        score = "0-1"
    else:
        score = "tie"
    return (
        f"ROUND {round_no} seed={seed} off={off_a},{off_b}\n"
        f"ROUND {round_no} OUT {score} cycles={result.cycles}\n"
    )


def quick_battle(source_a: str, source_b: str, seed: int = 0,
                 off_a: int | None = None, off_b: int | None = None) -> BattleResult:
    """Assemble two sources and run a full battle — the perft-style
    convenience hook for tests and referee checks."""
    battle = Battle(parse_warrior(source_a), parse_warrior(source_b),
                    seed=seed, off_a=off_a, off_b=off_b)
    return battle.run()
