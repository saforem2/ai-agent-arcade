"""Tests for CORE DNA (dna_cw.py) — the material, derived from the warriors.

The law above all the others in this file is that the hash SELECTS, it never
GENERATES. Everything the derivation can reach was vetted before it shipped,
so the sweeps below are not samples of a large space — they are the whole
space, enumerated. Sixty keys, five rotations, five bucket values of k
crossed with all sixteen rotations: if a property holds here it holds for
every match that will ever be recorded.

The second law is that null DNA is v2. A warrior that does not assemble
falls the entire match back to the record that already shipped, which makes
the v2 test suite v3's first regression test and makes the constants below
worth typing out literally rather than reading back out of the module.

These tests are pure — no numpy, no audio. The rendered half of the contract
(byte-identical null render, the outside note's windows, the pitch-class
distance between two matches, the 30 ms law on derived material) lives in
test_score_cw.py.

Run with: uv run --with pytest python -m pytest test_dna_cw.py
"""
from pathlib import Path

import corewar
import dna_cw as D

ENGINE = Path(__file__).resolve().parent
GAMES = ENGINE.parent / 'games' / 'corewar'

# A one-instruction warrior, a FOR/ROF warrior and an EQU-heavy warrior: the
# three shapes the canonicalizer has to survive, plus a source that does not
# assemble at all.
ONE_LINE = ''';redcode-94
;name Imp
        org     imp
imp     mov.i   $0, $1
        end
'''
FOR_ROF = ''';redcode-94
;name Filler
        org     boot
boot    spl     $1, $0
gap     FOR     12
        dat.f   $0, $0
        ROF
        end     boot
'''
EQU_HEAVY = ''';redcode-94
;name Constants
STEP    equ     1801
BSTEP   equ     STEP
CSTEP   equ     3741
        org     go
go      add.ab  #STEP, ptr
        mov.i   bomb, @ptr
        jmp     go, #CSTEP
ptr     dat     #0, #BSTEP
bomb    dat     #0, #0
        end     go
'''
BROKEN = 'this is not redcode at all\n'


def parse(src):
    return corewar.parse_warrior(src)


def shipped(match, seat):
    return parse((GAMES / match / 'warriors' / f'{seat}.red').read_text())


# ---------------------------------------------------------------------------
# THE GUARANTEE — the whole space, enumerated
# ---------------------------------------------------------------------------

def test_the_guarantee_holds_for_all_sixty_keys():
    """v2's "nothing can land wrong" was never a property of D minor. It is
    a property of the anhemitonic pentatonic SHAPE — no semitone anywhere in
    the necklace and no tritone between any pair — and that shape is
    invariant under transposition and rotation. So the guarantee is not
    weakened by deriving the key; it becomes a theorem, and this is it,
    proved by enumeration over all twelve tonics and all five rotations."""
    for tonic in range(12):
        for rot in range(5):
            pcs = sorted(D.scale_pcs(tonic, rot))
            assert len(set(pcs)) == 5
            gaps = [(pcs[(i + 1) % 5] - pcs[i]) % 12 for i in range(5)]
            assert min(gaps) >= 2, (tonic, rot, gaps)   # no semitone
            for i in range(5):
                for j in range(i + 1, 5):
                    d = (pcs[j] - pcs[i]) % 12
                    assert min(d, 12 - d) != 6, (tonic, rot)   # no tritone
            # and there is always exactly one note left over to kill with
            assert D.death_pc(tonic, rot) not in pcs, (tonic, rot)


def test_the_death_note_falls_back_only_where_it_has_to():
    """The b6 is the death note everywhere except man-gong, which owns its
    b6 as a scale tone; there the b2 takes over, and +1 is absent from all
    five rotations so the fallback is guaranteed to resolve. At D minor the
    rule evaluates to Bb — v2's constant, recovered rather than retyped."""
    fallbacks = {rot for rot in range(5)
                 if D.death_pc(0, rot) == 1}
    assert fallbacks == {3}                               # man-gong alone
    assert D.ROTATIONS[3][0] == 'man-gong'
    for rot in range(5):
        assert 1 not in D.ROTATIONS[rot][1]
    assert D.death_pc(2, 0) == 10                         # D minor -> Bb
    assert D.NOTES[10] == 58.270


def test_the_key_never_leaves_its_register():
    """The tonic is a pitch CLASS. The bass root is always placed in octave
    one, so a match in F# sits in exactly the same frequency window as v2's
    D — the key moves and the mix does not."""
    for tonic in range(12):
        for rot in range(5):
            root = D.scale_freqs(tonic, rot)[0]
            assert D.BASS_LO <= root < D.BASS_HI, (tonic, rot, root)
    # and the whole scale stays inside two octaves of that root
    for tonic in range(12):
        for rot in range(5):
            f = D.scale_freqs(tonic, rot)
            assert list(f) == sorted(f)
            assert f[-1] < f[0] * 4


def test_every_chord_is_a_subset_of_the_scale():
    """The voicing formula makes the guarantee the TYPE of the data rather
    than a claim about it: a chord cannot contain a note outside the
    pentatonic because there is no code path that could put one there."""
    for cad, (roots, voicings) in enumerate(D.CADENCES):
        assert len(set(roots)) == 4, cad
        assert roots[0] == 0, cad                  # every order starts home
        for r, v in zip(roots, voicings):
            assert len(set(v)) == 4, (cad, r)
            assert set(v) <= {0, 1, 2, 3, 4}, (cad, r)
            assert v[0] == r, (cad, r)             # voiced from its own root
        for a, b in zip(roots, roots[1:]):
            assert a != b, cad                     # real root motion


def test_euclid_keeps_the_faction_contrast():
    """Ember anchors the bar and ice plays off it, and that contrast is most
    of what makes the two studios legible with your eyes closed. It has to
    survive EVERY input, not the two matches we happen to have — so the
    whole reachable space is swept: five bucket values of k against all
    sixteen rotation seeds."""
    for k in range(3, D.K_MAX + 1):
        onsets = D.bjorklund(k)
        assert len(onsets) == k
        for h in range(16):
            e = {(x + D.ember_rotation(k, h)) % 16 for x in onsets}
            i = {(x + D.ice_rotation(k, h)) % 16 for x in onsets}
            assert 0 in e, (k, h)
            assert 0 not in i, (k, h)
            assert len(e) == k and len(i) == k


def test_v2s_patterns_are_points_in_the_derived_space():
    """Not a retrofit — a check. E(5,16) rotated 10 IS ember's tresillo and
    E(4,16) rotated 2 IS ice's offbeat garage, which is why v2 can be the
    null case of v3 instead of a special case beside it."""
    assert tuple(sorted((x + 10) % 16 for x in D.bjorklund(5))) == \
        D.V2_EMBER_STEPS
    assert tuple(sorted((x + 2) % 16 for x in D.bjorklund(4))) == \
        D.V2_ICE_STEPS
    assert 10 in {(-x) % 16 for x in D.bjorklund(5)}     # ember can reach it


def test_null_dna_is_v2_to_the_last_constant():
    """The load-bearing property of the whole feature. These are typed out
    rather than read back from the module so that the test would notice if
    the module's own idea of v2 drifted."""
    d = D.DEFAULT
    assert d.derived is False
    assert d.key_name == 'D minor'
    assert d.pent == (36.708, 43.654, 48.999, 55.000, 65.406)
    assert d.death == 58.270
    assert d.chord_degrees == ((0, (0, 1, 3, 4)), (1, (1, 3, 4, 0)),
                               (2, (2, 4, 0, 1)), (3, (3, 4, 0, 1)))
    # Dm7 | F6 | Gsus | A(add4), as frequencies
    P = dict(zip('DFGAC', d.pent))
    assert d.chords == (
        (P['D'], (P['D'], P['F'], P['A'], P['C'])),
        (P['F'], (P['F'], P['A'], P['C'], P['D'])),
        (P['G'], (P['G'], P['C'], P['D'], P['F'])),
        (P['A'], (P['A'], P['C'], P['D'], P['F'])))
    assert d.voices[0].steps == (0, 3, 6, 10, 13)
    assert d.voices[1].steps == (2, 6, 10, 14)
    assert d.voices[0].ghosts == ()
    assert d.voices[1].ghosts == (7, 15)
    assert d.bass_name == 'sustain'
    for v in d.voices:
        assert v.finale() == (3, 4, 0, 0)          # A -> C -> D -> D
        assert set(v.artic) == {'normal'}
    # ...and behaviour cannot move any of it
    assert d.with_behaviour((900, 900), (1, 1)) is d


# ---------------------------------------------------------------------------
# the mapping is total
# ---------------------------------------------------------------------------

def test_dna_is_total_over_every_shape_of_warrior():
    """A one-line imp, a FOR/ROF filler, an EQU chain and a source that does
    not assemble at all. The canonicalizer is `parse_warrior`, so FOR/ROF is
    expanded and EQU substituted before anything is hashed — two sources that
    assemble to the same program get the same theme however they were typed."""
    imp, filler, equs = parse(ONE_LINE), parse(FOR_ROF), parse(EQU_HEAVY)
    assert len(filler.instructions) == 13          # FOR really expanded
    for a in (imp, filler, equs):
        for b in (imp, filler, equs):
            dna = D.match_dna(a, b).with_behaviour((3, 900), (1, 512))
            assert 0 <= dna.tonic < 12 and 0 <= dna.rot < 5
            for v in dna.voices:
                assert len(v.contour) == D.MOTIF_LEN
                assert all(0 <= x < 5 for x in v.contour)
                assert 3 <= v.k <= D.K_MAX
                assert len(v.steps) == v.k
                assert not (set(v.steps) & set(v.ghosts))
    # a warrior that does not assemble is not an error, it is v2
    try:
        parse(BROKEN)
        raise AssertionError('BROKEN was supposed to fail to assemble')
    except corewar.RedcodeError:
        pass
    assert D.match_dna(None, parse(ONE_LINE)) is D.DEFAULT
    assert D.match_dna(parse(ONE_LINE), None) is D.DEFAULT
    assert D.match_dna(None, None) is D.DEFAULT


def test_an_imp_is_a_rising_scale():
    """The degenerate case is the most on-the-nose result in the system: an
    imp is `MOV +1` forever, so its contour is a rising scale. If the walk
    ever stops meaning something, this is the test that says so."""
    degs, arts = D.contour(parse(ONE_LINE))
    assert degs == (1, 2, 3, 4, 0, 1, 2, 3)
    assert set(arts) == {'normal'}                 # $0 is the plain mode


def test_identical_warriors_are_still_told_apart():
    """Two copies of the same program write the same theme, and dress alone
    would then have to carry the match. The inversion rule makes the picture
    audible instead: two imps chase each other in opposite directions, both
    still inside one scale, so no collision is possible."""
    imp = parse(ONE_LINE)
    dna = D.match_dna(imp, imp)
    e, i = dna.voices[0].contour, dna.voices[1].contour
    assert e == (1, 2, 3, 4, 0, 1, 2, 3)
    assert i == (4, 3, 2, 1, 0, 4, 3, 2)
    assert sum(1 for a, b in zip(e, i) if a != b) >= 3
    # ...and a genuinely different pair is left alone
    other = D.match_dna(imp, parse(EQU_HEAVY))
    assert other.voices[1].contour == D.contour(parse(EQU_HEAVY))[0]


# ---------------------------------------------------------------------------
# determinism
# ---------------------------------------------------------------------------

def test_the_same_warriors_give_the_same_theme_either_way_round():
    """A seat swap is the same match, so it has to be the same song — which
    is why the pair fold is over a SORTED pair rather than an XOR. (An XOR
    would also be symmetric, and would collapse every mirror match in the
    catalog onto one key.)"""
    for match in ('match-001', 'match-002'):
        a, b = shipped(match, 'A'), shipped(match, 'B')
        one, two = D.match_dna(a, b), D.match_dna(b, a)
        assert (one.tonic, one.rot, one.cadence, one.bass) == \
               (two.tonic, two.rot, two.cadence, two.bass)
        assert one.hash == two.hash
        assert {v.contour for v in one.voices} == \
               {v.contour for v in two.voices}
    # ...and re-reading the same file twice cannot drift
    a = shipped('match-001', 'A')
    assert D.warrior_hash(a) == D.warrior_hash(shipped('match-001', 'A'))
    # No salted hash(), no float, no RNG. The literals matter: asserting
    # fold(x) == fold(x) is a tautology that a hash reading id() or PYTHONHASH
    # would pass. These are the values this arithmetic produces, and if a
    # different machine or a different Python disagrees, determinism is gone
    # and the byte-identical-WAV promise with it.
    assert D.fold(('MOV.I$0$1',)) == 1046174294
    assert D.pair_hash(1, 2) == 889726634
    assert D.pair_hash(1, 2) == D.pair_hash(2, 1)
    assert D.pair_hash(1, 2) != D.pair_hash(1, 3)


def test_the_two_shipped_matches_are_two_different_songs():
    """The complaint v3 exists to answer: match-001 and match-002 sounded
    like siblings because every constant that chose the notes was a module
    global. They must now differ in the material itself."""
    one = D.match_dna(*[shipped('match-001', s) for s in 'AB'])
    two = D.match_dna(*[shipped('match-002', s) for s in 'AB'])
    assert one.hash != two.hash
    # All four decisions must be independent. Two cuts of this module failed
    # here and both are worth remembering: the first sliced an unmixed fold
    # and put both matches on F#, and the second — with the finalizer in, but
    # before each field got its own lane — separated the tonics and then put
    # both on `ritusen` a whole step apart, which shares four of five pitch
    # classes and is a WORSE sibling than the collision it fixed. Different
    # tonic is not enough; the mode has to move too.
    assert one.tonic != two.tonic, (one.key_name, two.key_name)
    assert one.rot != two.rot, (one.key_name, two.key_name)
    assert not (set(D.scale_pcs(one.tonic, one.rot))
                & set(D.scale_pcs(two.tonic, two.rot)))
    assert (one.rot, one.cadence, one.bass) != (two.rot, two.cadence, two.bass)
    assert one.pent != two.pent
    for a, b in zip(one.voices, two.voices):
        assert a.contour != b.contour


def test_behaviour_buckets_are_stable_under_a_near_miss():
    """A rematch must land in the same bucket rather than one bomb away from
    a different pattern — the whole point of bucketing rather than mapping
    density straight onto k."""
    assert D.density_k(0) == 3 and D.density_k(7.9) == 3
    assert D.density_k(8) == 4 and D.density_k(31) == 4
    assert D.density_k(128) == 6 and D.density_k(511) == 6
    assert D.density_k(512) == 7 and D.density_k(10 ** 6) == 7
    assert D.stride_class(1) == 0 and D.stride_class(2) == 1
    assert D.stride_class(8) == 1 and D.stride_class(9) == 2
    assert D.stride_class(500) == 2 and D.stride_class(501) == 3


# Two programs that differ only in a constant: the opcode sequence, and so
# the contour, is identical, which is the near-mirror case the inversion rule
# exists for. They are NOT the same program, so the rule cannot fall back on
# "the seats are indistinguishable".
NEAR_A = corewar.DWARF
NEAR_B = corewar.DWARF.replace('#4', '#6')


def test_the_mirror_inversion_does_not_depend_on_the_seats():
    """A seat swap is the same match and must be the same song — the reason
    `pair_hash` sorts its inputs. An earlier cut sorted the hash and then
    always inverted seat B, which put the whole guarantee back where it
    started: swap a near-mirror pair and the inversion moved to the other
    warrior, so the two studios traded themes and the match became audibly
    different. Deciding from the WARRIORS closes it."""
    a, b = corewar.parse_warrior(NEAR_A), corewar.parse_warrior(NEAR_B)
    assert D.contour(a)[0] == D.contour(b)[0]      # the near-mirror premise
    assert D.canonical_tokens(a) != D.canonical_tokens(b)
    one, two = D.match_dna(a, b), D.match_dna(b, a)
    # exactly one line was inverted, and it is a real inversion
    assert one.voices[0].contour != one.voices[1].contour
    assert D.invert(one.voices[0].contour) == one.voices[1].contour or \
        D.invert(one.voices[1].contour) == one.voices[0].contour
    # ...and the SAME warrior owns the inverted line whichever seat it sits in
    by_warrior_one = {one.voices[0].hash: one.voices[0].contour,
                      one.voices[1].hash: one.voices[1].contour}
    by_warrior_two = {two.voices[0].hash: two.voices[0].contour,
                      two.voices[1].hash: two.voices[1].contour}
    assert by_warrior_one == by_warrior_two
    assert (one.tonic, one.rot, one.cadence, one.bass) == \
           (two.tonic, two.rot, two.cadence, two.bass)


def test_two_copies_of_one_program_still_get_two_lines():
    """The degenerate mirror. The streams are identical, so no rule can pick
    a warrior — but that is exactly the case where the seats ARE
    indistinguishable, so inverting ice cannot be asymmetric."""
    a = corewar.parse_warrior(NEAR_A)
    m = D.match_dna(a, corewar.parse_warrior(NEAR_A))
    assert m.voices[0].contour != m.voices[1].contour
    assert D.invert(m.voices[0].contour) == m.voices[1].contour


def test_dna_carries_no_percussion_until_the_battle_is_read():
    """`match_dna` runs at extract time, before anything has read the battle,
    and `record_cw` publishes that object on `tl.dna`. It cannot invent the
    patterns yet, and an earlier cut filled the hole with v2's EMBER steps
    for BOTH voices — which silently handed ice a step 0 and broke the
    faction-contrast law for any consumer that trusted it. The hole is now a
    None, which nothing can mistake for material."""
    m = D.match_dna(corewar.parse_warrior(NEAR_A),
                    corewar.parse_warrior(corewar.IMP))
    assert not m.frozen
    for v in m.voices:
        assert v.steps is None and v.ghosts is None
        assert v.k is None and v.rot is None
    frozen = m.with_behaviour((10, 10), (1, 1))
    assert frozen.frozen
    assert 0 in frozen.voices[0].steps and 0 not in frozen.voices[1].steps
    # DEFAULT is not derived, but it IS the shipped record, so it is material
    assert D.DEFAULT.frozen


def test_each_selection_reads_its_own_lane():
    """Four decisions, four independent streams. Slicing one 32-bit word
    looks separable and is not — `% 12` and `% 5` consume the whole word, so
    the fields end up reading overlapping evidence and a shared tonic drags a
    shared mode along with it. Swept over the whole input space each field
    must use its full range, and no two fields may move together."""
    seen = [set(), set(), set(), set()]
    pairs = []
    for i in range(2000):
        mh = D.pair_hash(D.fold((f'MOV.I${i}$1',)), D.fold(('DAT.F$0$0',)))
        vals = (D.field(mh, 0) % 12, D.field(mh, 1) % 5,
                D.field(mh, 2) % len(D.CADENCES),
                D.field(mh, 3) % len(D.BASS_FIGURES))
        for j, v in enumerate(vals):
            seen[j].add(v)
        pairs.append(vals)
    assert [len(s) for s in seen] == [12, 5, len(D.CADENCES),
                                      len(D.BASS_FIGURES)]
    # every (tonic, rotation) combination should be reachable, which it is
    # not when the two share bits
    assert len({(p[0], p[1]) for p in pairs}) == 60
