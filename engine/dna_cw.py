"""CORE DNA — the match's own material, computed from the two warriors.

v2's diagnosis was right about the method and wrong about the constants:
`PENT`, `CHORDS`, `EMBER_STEPS` and `ICE_STEPS` were module globals, so every
match was the same song wearing a different battle. v3 changes exactly one
layer. Everything that decides WHAT is played becomes a function of the two
`.red` files; everything that decides HOW it is played stays welded to the
catalog. The grid, the anti-noise law, the arranger and the two studios do
not move.

    THE HASH SELECTS FROM A VETTED SPACE. IT NEVER GENERATES A PITCH.

That is the safety guarantee restated for derived material: every table in
this file was checked before it shipped, and the code's only power is to
index into one. The worst match this system can emit is a plain song, never
a wrong one.

THE FAMILY. 12 tonics x 5 pentatonic rotations = 60 keys. v2's "nothing can
land wrong" was never a property of D minor — it was a property of the
anhemitonic pentatonic SHAPE, the unique 5-note necklace with no semitone
and no tritone anywhere in it, and that property is invariant under
transposition and rotation. `test_the_guarantee_holds_for_all_sixty_keys`
turns it from an assertion about one hand-picked set into a swept theorem.
Register does not float with the key: the tonic is a pitch CLASS and the
bass root always lands in octave 1, so a match in F# sits in exactly the
same frequency window as v2's D.

THE DEATH NOTE generalizes as a rule rather than a constant: the b6 of the
tonic, falling back to the b2 when the rotation already owns its b6
(man-gong only; +1 is absent from all five rotations, so the fallback always
resolves). At D that is Bb — v2's value, recovered.

DETERMINISM. Selection is pure integer arithmetic: canonicalize, tokenize,
DJB2-fold, index. No floats in any decision, no RNG, no Python `hash()`
(salted per process), no dependence on dict ordering. "Same match ->
byte-identical WAV, on any machine" is then a property of the arithmetic
rather than a property of libm.

NULL DNA IS V2. `DEFAULT` reproduces v2's constants exactly, and it is what
a warrior that fails to assemble falls back to. The worst case in the whole
system is the record that already shipped.

Design record: design/corewar-mockups/atlas/music-consult/v3-DECISION.md,
which takes Opus's 60-key space, death-note rule, contour walk, mirror
inversion and Euclidean percussion, and Kimi's canonicalizer, integer fold,
voicing formula and bass figures.
"""

# ---------------------------------------------------------------------------
# the key space
# ---------------------------------------------------------------------------
# The twelve pitch classes in octave 1, at the same three-decimal precision
# v2 typed by hand. THIS TABLE IS THE OCTAVE-1 CLAMP: every entry lies in
# [32.70, 61.74) Hz, so a bass root can never drift out of the register the
# mix was built around however the key moves. D=36.708, F=43.654, G=48.999,
# A=55.000 and A#=58.270 are v2's PENT and BB, unchanged.
NOTES = (32.703, 34.648, 36.708, 38.891, 41.203, 43.654,
         46.249, 48.999, 51.913, 55.000, 58.270, 61.735)
PC_NAMES = ('C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B')
BASS_LO, BASS_HI = 32.70, 61.74

# The five modes of the anhemitonic pentatonic {0,2,4,7,9}. Rotation is the
# strongest anti-sibling lever available, and it costs nothing: all five are
# the same interval necklace read from a different starting point, so all
# five inherit the guarantee.
ROTATIONS = (
    ('minor',    (0, 3, 5, 7, 10)),
    ('major',    (0, 2, 4, 7, 9)),
    ('egyptian', (0, 2, 5, 7, 10)),
    ('man-gong', (0, 3, 5, 8, 10)),
    ('ritusen',  (0, 2, 5, 7, 9)),
)

# The chord loop, in degree space. Each entry is (root degrees, voicings).
# Voicing on root degree k is uniform `{k, k+1, k+3, k+4} mod 5`, which makes
# "every chord is a four-note subset of the pentatonic" the TYPE of the data
# rather than a claim about it. Entry 0 is v2's Dm7 | F6 | Gsus | A(add4) and
# carries its hand-voicings verbatim, because null DNA has to be v2 to the
# byte; the formula agrees with it on the tonic chord and re-voices the other
# three. Every order starts on the tonic, uses four distinct roots, and moves
# by a real interval at every step.
def _voice(k):
    return (k % 5, (k + 1) % 5, (k + 3) % 5, (k + 4) % 5)


def _cadence(roots, voicings=None):
    return (tuple(roots), tuple(voicings) if voicings
            else tuple(_voice(k) for k in roots))


CADENCES = (
    _cadence((0, 1, 2, 3), ((0, 1, 3, 4), (1, 3, 4, 0),      # v2, verbatim
                            (2, 4, 0, 1), (3, 4, 0, 1))),
    _cadence((0, 2, 3, 4)),
    _cadence((0, 3, 1, 4)),
    _cadence((0, 4, 2, 3)),
    _cadence((0, 3, 4, 2)),
    _cadence((0, 2, 4, 3)),
    _cadence((0, 1, 3, 4)),
    _cadence((0, 4, 1, 2)),
)

# ---------------------------------------------------------------------------
# the motif walk
# ---------------------------------------------------------------------------
# Each opcode is a move in degree space, accumulated mod 5. SPL and DAT are
# the two largest moves on purpose: a fork is the biggest thing a warrior does
# and a bomb is the most terminal, so both are heard as a leap rather than a
# step, and a program's shape survives into its theme.
#
# Read the sign honestly: it is bookkeeping, not direction. Degrees live on a
# 5-cycle, so -4 and +1 are the SAME move and the emitted contour cannot tell
# them apart — DAT does not fall, it leaps the other way round the wheel. What
# the walk actually preserves is the MAGNITUDE class of each opcode and the
# fact that different opcodes move differently; a direction-preserving walk
# would need a register that is not modular, and is logged as possible v3.1.
# The shipped contours are gated by the vetted-space rule either way.
DELTA = {'MOV': 1, 'ADD': 2, 'SUB': -2, 'MUL': 3, 'DIV': -3, 'MOD': -1,
         'JMP': 0, 'JMZ': -1, 'JMN': 1, 'DJN': -2, 'SPL': 4, 'SEQ': 0,
         'SNE': 1, 'SLT': -1, 'NOP': 0, 'DAT': -4}

# Articulation from the A-operand's addressing mode. The code writes how a
# note is held; it never writes when one starts.
ARTIC = {'#': 'staccato', '$': 'normal', '@': 'long', '*': 'long',
         '<': 'grace', '>': 'grace', '{': 'grace', '}': 'grace'}
ARTIC_LEN = {'staccato': 0.55, 'normal': 1.0, 'long': 1.6, 'grace': 1.0}

MOTIF_LEN = 8                      # degrees read from warrior.start

# ---------------------------------------------------------------------------
# percussion and bass vocabulary
# ---------------------------------------------------------------------------
# Bombs-per-active-bar, bucketed so that a rematch of the same two warriors
# lands in the same bucket rather than one onset away from a different one.
DENSITY_BUCKETS = ((8, 3), (32, 4), (128, 5), (512, 6))
K_MAX = 7

# Ghost placement, chosen by the median stride's class — the same four
# classes v2 already reads to pick a ghost's VOICE (32nd roll / open hat /
# chop / sparse tick), now also choosing where the ghosts sit. Bank 0 is
# v2's ICE_GHOSTS.
GHOST_BANKS = ((7, 15), (3, 11), (5, 13), (1, 9))
STRIDE_EDGES = (1, 8, 500)         # -> classes 0,1,2,3

# The bass figure, as (step, length in steps, degree offset from the chord
# root, octave multiplier). Figure 0 is v2's: one sustained root for the
# whole bar. The other three are Kimi's, and all four move only within the
# pentatonic, so the figure can colour the low end without ever inventing a
# pitch.
#
# THE REGISTER LAW, stated exactly: the bass ROOT clamps to octave 1 — that is
# what the NOTES table above guarantees, for all sixty keys. A FIGURE may then
# voice up to one octave above that root, and two of these four deliberately
# do: `root-fifth` reaches degree 3 and `octave-bounce` doubles at x2. The
# clamp is on where the harmony sits, not a ceiling on every sample the bass
# emits; the mix was built around a low band with a fifth and an octave in it.
BASS_FIGURES = (
    ('sustain', ((0, 16, 0, 1),)),
    ('pedal-8ths', tuple((s, 2, 0, 1) for s in range(0, 16, 2))),
    ('root-fifth', ((0, 4, 0, 1), (4, 4, 3, 1),
                    (8, 4, 0, 1), (12, 4, 3, 1))),
    ('octave-bounce', ((0, 4, 0, 1), (4, 4, 0, 2),
                       (8, 4, 0, 1), (12, 4, 0, 2))),
)

# v2's two patterns, kept as literals because DEFAULT has to be v2 to the
# byte. They are also both points in the derived space, and a test proves it:
# E(5,16) rotated 10 and E(4,16) rotated 2.
V2_EMBER_STEPS = (0, 3, 6, 10, 13)
V2_ICE_STEPS = (2, 6, 10, 14)
V2_ICE_GHOSTS = (7, 15)
# v2's leitmotif: A -> C -> D -> D, which is degrees 3,4,0,0 and resolves
# home. The finale law (first four degrees, last forced to 0) leaves it
# unchanged, which is how it stays v2 under a derived rule.
V2_CONTOUR = (3, 4, 0, 0, 3, 4, 0, 0)


# ---------------------------------------------------------------------------
# integer hashing — no floats, no RNG, no salted hash()
# ---------------------------------------------------------------------------
M32 = 0xFFFFFFFF


def rotl32(x, r):
    x &= M32
    return ((x << r) | (x >> (32 - r))) & M32


def fold(tokens):
    """Kimi's DJB2 fold. Pure integer, so the fingerprint is identical on
    every machine — which is the whole reason ruling 3 rejected a sin-hash.
    A float fingerprint would have made "same match, byte-identical WAV"
    depend on libm agreeing with itself across platforms."""
    h = 5381
    for i, tok in enumerate(tokens):
        v = 0
        for c in tok:
            v = (v * 33 + ord(c)) & M32
        h = ((h * 33) ^ v ^ (i + 1)) & M32
    return h


def canonical_tokens(w):
    """The assembled warrior as a canonical token stream.

    `corewar.parse_warrior` has already done exactly the canonicalization
    ruling 3 asks for — comments and `;name`/`;author` headers stripped,
    FOR/ROF expanded, EQU substituted, opcodes and modifiers made explicit,
    field values normalized mod the core size — so two sources that assemble
    to the same program hash the same however they were typed."""
    if w is None:
        return ()
    out = [f'org:{int(w.start)}']
    for ins in w.instructions:
        out.append(f'{ins.opcode}.{ins.modifier}'
                   f'{ins.a_mode}{ins.a_val}{ins.b_mode}{ins.b_val}')
    return tuple(out)


def warrior_hash(w):
    return fold(canonical_tokens(w))


# The pair salt. It exists because the first cut of this module put the two
# shipped matches on the SAME tonic — F# minor against F# ritusen, three of
# five pitch classes shared — which is a one-in-twelve coincidence rather
# than a bias, and the director ruled on 2026-08-14 to re-key rather than
# live with it.
#
# Read the value honestly. 13 IS ARBITRARY, and it WAS chosen deliberately:
# salts 0..255 were swept and the smallest was taken that puts the two
# shipped matches on a different tonic AND a different rotation with no
# shared pitch class. That is not a needle — 43 of those 256 qualify — so
# the sweep picked a common outcome rather than tuning the hash until the
# answer was pretty. Note also what a salt CANNOT do on its own: the tonic is
# `hash % 12`, so an additive salt applied before the mixing shifts both
# matches equally and preserves a collision for all 2^32 values. The work is
# done by `avalanche` below and by the per-field lanes further down; this
# constant only re-rolls their input.
#
# Changing it re-keys EVERY match in the catalog. Every archived master would
# have to be re-rendered, and every one of them would be a different song.
PAIR_SALT = 13


def avalanche(h):
    """The murmur3 finalizer, in pure integers.

    `match_dna` slices this hash four ways — `% 12`, `>> 4`, `>> 8`, `>> 12`
    — and the raw fold's low bits are not independent enough of each other
    for four slices that must not correlate. Mixing once here is what makes
    "the key, the mode, the cadence and the bass figure are four separate
    decisions" true rather than hoped for."""
    h &= M32
    h ^= h >> 16
    h = (h * 0x85EBCA6B) & M32
    h ^= h >> 13
    h = (h * 0xC2B2AE35) & M32
    return (h ^ (h >> 16)) & M32


def pair_hash(ha, hb):
    """Symmetric by construction: a seat swap is the same match, so it must
    be the same song. Sorted rather than XORed, because a mirror match would
    collapse an XOR to zero and hand every mirror in the catalog the same
    key."""
    lo, hi = (ha, hb) if ha <= hb else (hb, ha)
    return avalanche(((lo * 0x9E3779B1 + rotl32(hi, 16)) & M32) ^ PAIR_SALT)


# One independent lane per selection. Slicing a single 32-bit word four ways
# looks separable and is not: `% 12` and `% 5` are not powers of two, so each
# consumes the WHOLE word rather than the four bits it appears to read, and
# the four fields end up reading overlapping evidence. Re-mixing the pair hash
# under four distinct constants gives each decision its own stream, so a match
# that shares a tonic with another has no elevated chance of sharing its mode,
# its cadence or its bass figure too. Values are arbitrary odd 32-bit
# constants (golden-ratio derived), not tuned; like PAIR_SALT, changing any of
# them re-keys the entire catalog.
FIELD_SALTS = (0x9E3779B1, 0x85EBCA77, 0xC2B2AE3D, 0x27D4EB2F)


def field(mh, i):
    return avalanche(mh ^ FIELD_SALTS[i])


# ---------------------------------------------------------------------------
# the vocabulary generators
# ---------------------------------------------------------------------------
def bjorklund(k, n=16):
    """Euclidean rhythm: k onsets spread as evenly as n slots allow. E(5,16)
    and E(4,16) are v2's two patterns up to rotation, which is the evidence
    that v2 was already one point in this space rather than an exception
    outside it."""
    if k <= 0:
        return ()
    if k >= n:
        return tuple(range(n))
    a = [[1] for _ in range(k)]
    b = [[0] for _ in range(n - k)]
    while len(b) > 1 and len(a) > 1:
        m = min(len(a), len(b))
        rest = a[m:] if len(a) > m else b[m:]
        a = [a[i] + b[i] for i in range(m)]
        b = rest
    seq = [x for g in a + b for x in g]
    return tuple(i for i, v in enumerate(seq) if v)


def scale_pcs(tonic, rot):
    return tuple((tonic + off) % 12 for off in ROTATIONS[rot][1])


def scale_freqs(tonic, rot):
    """The five degrees as frequencies, ascending from the tonic's own
    octave-1 root. A degree that wraps past B climbs an octave, exactly as
    v2's C (65.406) sits above its D (36.708)."""
    out = []
    for off in ROTATIONS[rot][1]:
        pc = tonic + off
        out.append(NOTES[pc % 12] * (2.0 if pc >= 12 else 1.0))
    return tuple(out)


def death_pc(tonic, rot):
    """The b6 of the tonic, or the b2 when the rotation already owns its b6.
    Only man-gong does, and +1 is absent from all five rotations, so the
    fallback is guaranteed to resolve. Swept over all sixty keys: the death
    note is outside the scale every time."""
    offs = ROTATIONS[rot][1]
    return (tonic + (1 if 8 in offs else 8)) % 12


def _bucket(x, edges):
    for i, e in enumerate(edges):
        if x <= e:
            return i
    return len(edges)


def density_k(density):
    """Onset count for E(k,16), from the median bombs-per-active-bar."""
    for edge, k in DENSITY_BUCKETS:
        if density < edge:
            return k
    return K_MAX


def stride_class(stride):
    """v2's four ghost classes: a stride of 1 is an imp carpet, a huge one
    is a scanner reaching across the core."""
    return _bucket(stride, STRIDE_EDGES)


def ember_rotation(k, h):
    """Ember's pattern ALWAYS contains step 0 — it is the faction that
    anchors the bar. Drawing the rotation from the onsets' own negatives
    makes that structural rather than a filter that might reject everything."""
    cands = sorted({(-x) % 16 for x in bjorklund(k)})
    return cands[h % len(cands)]


def ice_rotation(k, h):
    """Ice's pattern NEVER contains step 0 — it is the offbeat faction, and
    that contrast is most of what makes the two studios legible with your
    eyes closed. A Euclidean set with k <= 7 has no two adjacent onsets, so
    bumping the rotation by one always escapes step 0 within a few tries."""
    onsets = bjorklund(k)
    r = h % 16
    for _ in range(16):
        if all((x + r) % 16 for x in onsets):
            return r
        r = (r + 1) % 16
    return r


def contour(w):
    """Opcodes as signed moves in degree space, walked eight instructions
    from `warrior.start` and cycling if the warrior is shorter.

    A three-line imp is `MOV +1` eight times, which is (1,2,3,4,0,1,2,3) —
    a rising scale. An imp IS a rising scale, so the degenerate case is the
    most on-the-nose result the mapping produces."""
    if w is None or not w.instructions:
        return V2_CONTOUR, ('normal',) * MOTIF_LEN
    ins = w.instructions
    start = int(w.start) % len(ins)
    degs, arts, d = [], [], 0
    for i in range(MOTIF_LEN):
        cur = ins[(start + i) % len(ins)]
        d = (d + DELTA.get(cur.opcode, 0)) % 5
        degs.append(d)
        arts.append(ARTIC.get(cur.a_mode, 'normal'))
    return tuple(degs), tuple(arts)


def invert(degrees):
    return tuple((-d) % 5 for d in degrees)


# ---------------------------------------------------------------------------
# the DNA objects
# ---------------------------------------------------------------------------
class VoiceDNA:
    """One faction's derived material. The theme is the warrior's; the dress
    is the faction's, and nothing in here can reach the dress."""

    __slots__ = ('hash', 'contour', 'artic', 'steps', 'ghosts', 'k', 'rot')

    def __init__(self, h, degrees, artic, steps, ghosts, k, rot):
        self.hash = h
        self.contour = tuple(degrees)
        self.artic = tuple(artic)
        # None, not a placeholder pattern: percussion is not known until the
        # battle has been read. See `MatchDNA.frozen`.
        self.steps = None if steps is None else tuple(steps)
        self.ghosts = None if ghosts is None else tuple(ghosts)
        self.k = k
        self.rot = rot

    def finale(self):
        """The winner's four notes, the last forced home. v2's A->C->D->D is
        degrees (3,4,0,0), so the law leaves the shipped record unchanged and
        gives every derived theme the same resolution."""
        line = list(self.contour[:4])
        while len(line) < 4:
            line.append(0)
        line[-1] = 0
        return tuple(line)


class MatchDNA:
    """Everything the score needs to know about WHAT this match plays."""

    __slots__ = ('derived', 'tonic', 'rot', 'cadence', 'pent', 'death',
                 'death_pc', 'chord_degrees', 'chords', 'voices', 'bass',
                 'hash')

    def __init__(self, derived, tonic, rot, cadence, bass, voices, h=0):
        self.derived = derived
        self.tonic = tonic
        self.rot = rot
        self.cadence = cadence
        self.bass = bass
        self.voices = tuple(voices)
        self.hash = h
        self.pent = scale_freqs(tonic, rot)
        self.death_pc = death_pc(tonic, rot)
        self.death = NOTES[self.death_pc]
        roots, voicings = CADENCES[cadence]
        self.chord_degrees = tuple(zip(roots, voicings))
        self.chords = tuple(
            (self.pent[r], tuple(self.pent[d] for d in v))
            for r, v in self.chord_degrees)

    # -- naming, for the log and the design record ------------------------
    @property
    def key_name(self):
        return f'{PC_NAMES[self.tonic]} {ROTATIONS[self.rot][0]}'

    @property
    def death_name(self):
        return PC_NAMES[self.death_pc]

    @property
    def bass_name(self):
        return BASS_FIGURES[self.bass][0]

    @property
    def bass_figure(self):
        return BASS_FIGURES[self.bass][1]

    def bass_steps(self):
        return tuple(s for s, _d, _o, _m in self.bass_figure)

    @property
    def frozen(self):
        """True once the percussion is real material rather than an absence.

        `match_dna` runs at extract time, before anything has read the battle,
        so the DNA it returns knows the key and the themes but CANNOT yet know
        the patterns — and `record_cw` publishes that object on `tl.dna` where
        anyone may pick it up. An earlier cut filled the gap with v2's ember
        pattern for both voices, which silently handed ice a step 0 and broke
        the faction-contrast law for any consumer that trusted it. The gap is
        now a None that cannot be mistaken for material, and `Score.set_dna`
        refuses an unfrozen DNA rather than rendering one."""
        return all(v.steps is not None for v in self.voices)

    def with_behaviour(self, density=(0, 0), stride=(0, 0)):
        """Freeze the percussion from what the two armies actually did.

        The patterns are chosen ONCE, offline, for the whole match — which is
        why deriving them does not violate the anti-noise law. The battle
        still only selects which of the frozen slots fire and how hard; it
        never gains the power to place one."""
        if not self.derived:
            return self
        out = []
        for w, v in enumerate(self.voices):
            k = density_k(density[w])
            if w == 0:
                r = ember_rotation(k, v.hash >> 5)
                ghosts = ()
            else:
                r = ice_rotation(k, v.hash >> 5)
                ghosts = GHOST_BANKS[stride_class(stride[w])]
            steps = tuple(sorted((x + r) % 16 for x in bjorklund(k)))
            ghosts = tuple(g for g in ghosts if g not in steps)
            out.append(VoiceDNA(v.hash, v.contour, v.artic,
                                steps, ghosts, k, r))
        return MatchDNA(True, self.tonic, self.rot, self.cadence, self.bass,
                        out, self.hash)


def warrior_dna(w, h=None):
    """The half of a voice that the CODE writes: contour and articulation.
    The other half — the percussion — is written by the battle, so it is
    absent here rather than guessed at. `with_behaviour` supplies it."""
    degrees, arts = contour(w)
    return VoiceDNA(warrior_hash(w) if h is None else h, degrees, arts,
                    None, None, None, None)


def match_dna(wa, wb):
    """The whole derivation, from two assembled warriors to one song.

    Either warrior being None — a source that does not assemble, which
    `read_warriors` already tolerates — falls the whole match back to DEFAULT,
    and DEFAULT is the record that already shipped."""
    if wa is None or wb is None:
        return DEFAULT
    ta, tb = canonical_tokens(wa), canonical_tokens(wb)
    ha, hb = fold(ta), fold(tb)
    mh = pair_hash(ha, hb)
    tonic = field(mh, 0) % 12
    rot = field(mh, 1) % 5
    cadence = field(mh, 2) % len(CADENCES)
    bass = field(mh, 3) % len(BASS_FIGURES)
    va, vb = warrior_dna(wa, ha), warrior_dna(wb, hb)
    # Two copies of the same program write the same theme, so dress alone
    # would have to carry the whole match. Inverting one line instead makes
    # the picture audible: two imps in Core War chase each other, and now the
    # music does too — still inside one scale, so no collision is possible.
    #
    # WHICH line inverts is decided by the WARRIORS, never by the seats. An
    # earlier cut always inverted seat B, which meant a near-mirror pair
    # swapped seats and became an audibly different song — the exact property
    # `pair_hash` sorts its inputs to protect. The rule here is seat-free by
    # construction: invert the lexicographically larger canonical stream, and
    # when the two streams are identical the seats are indistinguishable, so
    # inverting ice cannot be asymmetric.
    apart = sum(1 for x, y in zip(va.contour, vb.contour) if x != y)
    if apart < 3:
        flip = 0 if ta > tb else 1
        v = (va, vb)[flip]
        v = VoiceDNA(v.hash, invert(v.contour), v.artic,
                     v.steps, v.ghosts, v.k, v.rot)
        va, vb = (v, vb) if flip == 0 else (va, v)
    return MatchDNA(True, tonic, rot, cadence, bass, (va, vb), mh)


# NULL DNA IS V2, EXACTLY. Tonic D, minor rotation, cadence 0 with its
# hand-voicings, the sustained bass, both patterns as v2 typed them, and the
# A->C->D->D leitmotif in both studios. A test asserts the constants match
# and another asserts the rendered WAV is byte-identical.
DEFAULT = MatchDNA(
    False, 2, 0, 0, 0,
    (VoiceDNA(0, V2_CONTOUR, ('normal',) * MOTIF_LEN,
              V2_EMBER_STEPS, (), 5, 10),
     VoiceDNA(0, V2_CONTOUR, ('normal',) * MOTIF_LEN,
              V2_ICE_STEPS, V2_ICE_GHOSTS, 4, 2)))
