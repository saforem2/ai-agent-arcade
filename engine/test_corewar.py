"""Tests for corewar.py. Run with: uv run --with pytest pytest test_corewar.py"""

import pytest

from corewar import (
    Battle,
    BattleEvent,
    BattleResult,
    CORE_FILL,
    CORE_SIZE,
    DWARF,
    IMP,
    Instruction,
    MAX_CYCLES,
    MAX_PROCESSES,
    MAX_WARRIOR_LEN,
    MIN_SEPARATION,
    RedcodeError,
    battle_transcript,
    format_instruction,
    load_warrior_file,
    parse_warrior,
    quick_battle,
    sha256_warrior,
    validate_warrior,
)


def I(opcode, modifier, a_mode, a_val, b_mode, b_val):
    """Shorthand for an expected Instruction."""
    return Instruction(opcode, modifier, a_mode, a_val % CORE_SIZE, b_mode, b_val % CORE_SIZE)


def asm(source):
    return parse_warrior(source)


def battle_a(source, **kwargs):
    """Warrior A (from source, at off_a=0) vs an immortal `jmp $0`
    spinner as warrior B at off_b=4000."""
    kwargs.setdefault("off_a", 0)
    kwargs.setdefault("off_b", 4000)
    return Battle(asm(source), asm("jmp $0"), **kwargs)


def step_a(battle, n=1):
    """Advance n turns of warrior A (2n steps, A moves first). Returns
    the events of A's turns."""
    events = []
    for _ in range(2 * n):
        if battle.over:
            break
        ev = battle.step()
        if ev is not None and ev.warrior == 0:
            events.append(ev)
    return events


# ---------------------------------------------------------------------------
# Parser: instructions, operands, default modifiers
# ---------------------------------------------------------------------------

def test_parse_basic_instruction():
    w = asm("mov.i $0, $1")
    assert w.instructions == (I("MOV", "I", "$", 0, "$", 1),)
    assert w.start == 0


def test_parse_case_insensitive_opcode_and_modifier():
    w = asm("MoV.i 0, 1")
    assert w.instructions == (I("MOV", "I", "$", 0, "$", 1),)


def test_parse_cmp_is_seq_alias():
    w = asm("cmp 0, 1")
    assert w.instructions[0].opcode == "SEQ"


def test_parse_all_modes():
    w = asm("nop #0, $0\nnop @0, <0\nnop >0, *0\nnop {0, }0")
    modes = [(ins.a_mode, ins.b_mode) for ins in w.instructions]
    assert modes == [("#", "$"), ("@", "<"), (">", "*"), ("{", "}")]


def test_parse_negative_values_normalize_mod_coresize():
    w = asm("jmp -2")
    assert w.instructions[0].a_val == CORE_SIZE - 2


@pytest.mark.parametrize(
    "source,expected_modifier",
    [
        ("dat 0, 0", "F"),
        ("mov #0, 1", "AB"), ("mov 0, #1", "B"), ("mov 0, 1", "I"),
        ("seq #0, 1", "AB"), ("seq 0, #1", "B"), ("seq 0, 1", "I"),
        ("sne #0, 1", "AB"), ("sne 0, #1", "B"), ("sne 0, 1", "I"),
        ("add #0, 1", "AB"), ("add 0, #1", "B"), ("add 0, 1", "F"),
        ("sub 0, 1", "F"), ("mul 0, 1", "F"), ("div 0, 1", "F"), ("mod 0, 1", "F"),
        ("slt #0, 1", "AB"), ("slt 0, 1", "B"), ("slt 0, #1", "B"),
        ("jmp 0", "B"), ("jmz 0, 0", "B"), ("jmn 0, 0", "B"),
        ("djn 0, 0", "B"), ("spl 0", "B"), ("nop 0, 0", "B"),
    ],
)
def test_default_modifiers(source, expected_modifier):
    # Draft appendix A.2.1.2 (ICWS'88 conversion table).
    assert asm(source).instructions[0].modifier == expected_modifier


def test_single_operand_dat_goes_to_b_field():
    # Draft section 2.4: one-operand DAT assembles the operand into B, A = #0.
    assert asm("dat 5").instructions == (I("DAT", "F", "#", 0, "$", 5),)


def test_single_operand_other_goes_to_a_field():
    # Draft section 2.4: other one-operand instructions get B = #0.
    assert asm("jmp 5").instructions == (I("JMP", "B", "$", 5, "#", 0),)


def test_opcode_only_line_defaults_to_zero_operands():
    # pMARS-style leniency: both operands $0 (draft grammar would reject).
    assert asm("nop").instructions == (I("NOP", "B", "$", 0, "$", 0),)


def test_format_roundtrip_all_opcodes():
    sources = [
        "dat.f #0, #0", "mov.i $1, $2", "add.ab #3, @4", "sub.ba <5, >6",
        "mul.x *7, {8", "div.f }9, #10", "mod.a $11, $12", "jmp.b $13, #0",
        "jmz.f $14, $15", "jmn.x $16, $17", "djn.i $18, $19", "spl.b $20, #0",
        "seq.i $21, $22", "sne.b $23, $24", "slt.ab #25, $26", "nop.b $0, $0",
    ]
    for src in sources:
        ins = asm(src).instructions[0]
        assert asm(format_instruction(ins)).instructions[0] == ins


# ---------------------------------------------------------------------------
# Parser: labels, EQU, FOR/ROF, ORG/END, metadata
# ---------------------------------------------------------------------------

def test_labels_are_pc_relative():
    w = asm("start jmp loop\nnop\nloop jmp start")
    assert w.instructions[0] == I("JMP", "B", "$", 2, "#", 0)   # loop is +2
    assert w.instructions[2] == I("JMP", "B", "$", CORE_SIZE - 2, "#", 0)  # start is -2


def test_label_only_line_and_multiple_labels():
    w = asm("first\nsecond mov first, second")
    assert w.instructions[0].a_val == 0
    assert w.instructions[0].b_val == 0


def test_equ_text_substitution_and_predefined():
    w = asm("step EQU 4\ntgt EQU step * 2\nmov #tgt, #MAXLENGTH")
    assert w.instructions[0] == I("MOV", "AB", "#", 8, "#", 100)


def test_equ_recursive_reference_errors():
    with pytest.raises(RedcodeError, match="recursive EQU"):
        asm("a EQU b\nb EQU a\nmov a, 0")


def test_for_rof_plain_expansion():
    w = asm("FOR 3\nnop\nROF")
    assert w.instructions == (I("NOP", "B", "$", 0, "$", 0),) * 3


def test_for_rof_index_label_in_expressions():
    # pMARS redcode.ref: last FOR-line label is the 1-based loop index,
    # earlier labels alias the block start.
    w = asm("base\nindex FOR 3\nmov.i base, base + index - 1\nROF")
    assert w.instructions == (
        I("MOV", "I", "$", 0, "$", 0),
        I("MOV", "I", "$", CORE_SIZE - 1, "$", 0),
        I("MOV", "I", "$", CORE_SIZE - 2, "$", 0),
    )


def test_for_rof_stringization():
    # pMARS redcode.ref: imp&N expands to imp01, imp02, ...
    w = asm("N FOR 5\nimp&N mov.i imp&N, imp&N + 1\nROF")
    assert w.instructions == (I("MOV", "I", "$", 0, "$", 1),) * 5


def test_for_rof_nested():
    w = asm("FOR 2\nFOR 2\nnop\nROF\nROF")
    assert len(w.instructions) == 4


def test_for_rof_zero_count_emits_nothing():
    w = asm("FOR 0\nnop\nROF\njmp 0")
    assert w.instructions == (I("JMP", "B", "$", 0, "#", 0),)


def test_for_without_rof_errors():
    with pytest.raises(RedcodeError, match="FOR without a matching ROF"):
        asm("FOR 2\nnop")


def test_rof_without_for_errors():
    with pytest.raises(RedcodeError, match="ROF without a matching FOR"):
        asm("nop\nROF")


def test_for_count_with_label_errors():
    with pytest.raises(RedcodeError, match="constant expression"):
        asm("FOR undefined_label\nnop\nROF")


def test_duplicate_label_inside_for_errors():
    # pMARS: unstringized labels in a loop body collide across iterations.
    with pytest.raises(RedcodeError, match="duplicate label"):
        asm("FOR 2\nloop nop\nROF")


def test_for_rof_nested_stringization_outer_index():
    # pMARS parity (BUG-1 regression): stringization may use indices of
    # ANY enclosing loop — x&i&j with i=1..2, j=1..2 -> x0101..x0202.
    w = asm("i FOR 2\nj FOR 2\nx&i&j dat #i, #j\nROF\nROF")
    assert w.instructions == (
        I("DAT", "F", "#", 1, "#", 1),
        I("DAT", "F", "#", 1, "#", 2),
        I("DAT", "F", "#", 2, "#", 1),
        I("DAT", "F", "#", 2, "#", 2),
    )


def test_for_rof_nested_stringized_labels_are_referenceable():
    w = asm("i FOR 2\nj FOR 2\nx&i&j dat #i, #j\nROF\nROF\njmp x0202")
    # x0202 is instruction 3; jmp is instruction 4 -> offset -1.
    assert w.instructions[4] == I("JMP", "B", "$", CORE_SIZE - 1, "#", 0)


def test_for_rof_partial_stringization_still_rejected():
    # Stringizing with only the inner index collides across outer
    # iterations; a hard error here (pMARS only warns) — documented
    # strictness.
    with pytest.raises(RedcodeError, match="duplicate label"):
        asm("i FOR 2\nj FOR 2\nz&j dat #i, #j\nROF\nROF")


def test_for_rof_stringization_unknown_index_rejected():
    with pytest.raises(RedcodeError, match="not an active FOR index"):
        asm("FOR 2\nx&y dat 0, 0\nROF")


def test_org_and_end_operands():
    assert asm("org 1\nnop\njmp 0").start == 1
    assert asm("org start\nnop\nstart jmp start").start == 1
    # END operand wins over ORG (draft section 2.5).
    assert asm("org 0\nnop\njmp 0\nend 1").start == 1


def test_end_stops_parsing():
    # Everything after END is ignored (draft section 2.5), even garbage.
    w = asm("nop\nend\nthis is not redcode at all {{{")
    assert w.instructions == (I("NOP", "B", "$", 0, "$", 0),)


def test_org_out_of_range_errors():
    with pytest.raises(RedcodeError, match="out of range"):
        asm("org 5\nnop\njmp 0")


def test_metadata_name_and_author():
    w = asm(";redcode-94\n;name Test Warrior\n;author J. Random\n;strategy does nothing\nnop")
    assert w.name == "Test Warrior"
    assert w.author == "J. Random"


def test_errors_carry_line_numbers():
    with pytest.raises(RedcodeError) as excinfo:
        asm("nop\nnop\nmoo 0, 1")
    assert "line 3" in str(excinfo.value)


def test_unknown_opcode_and_modifier_error():
    with pytest.raises(RedcodeError, match="unknown opcode"):
        asm("moo 0, 1")
    with pytest.raises(RedcodeError, match="unknown modifier"):
        asm("mov.q 0, 1")


def test_undefined_symbol_errors():
    with pytest.raises(RedcodeError, match="undefined symbol"):
        asm("mov nowhere, 0")


def test_ldp_stp_rejected_with_clear_error():
    for op in ("ldp", "stp"):
        with pytest.raises(RedcodeError, match="no P-space"):
            asm(f"{op} #0, 1")


def test_empty_source_and_comment_only_source_error():
    with pytest.raises(RedcodeError):
        asm("")
    with pytest.raises(RedcodeError):
        asm(";redcode-94\n;name Nothing\n")


def test_expression_arithmetic_and_division_by_zero():
    w = asm("dat #(2 + 3 * 4), #(10 % 4)\ndat #-(7 / 2), #(2 * (3 + 4))")
    assert w.instructions[0].a_val == 14
    assert w.instructions[0].b_val == 2
    assert w.instructions[1].a_val == CORE_SIZE - 3  # C-style truncation: -3
    assert w.instructions[1].b_val == 14
    with pytest.raises(RedcodeError, match="division by zero"):
        asm("dat #(1 / 0), #0")


# ---------------------------------------------------------------------------
# Parser: robustness caps and review regressions (RISK-1, RISK-2, nits)
# ---------------------------------------------------------------------------

def test_deep_parens_raise_redcodeerror_not_recursionerror():
    src = "mov " + "(" * 500 + "0" + ")" * 500 + ", 0"
    with pytest.raises(RedcodeError, match="nested too deeply"):
        parse_warrior(src)


def test_deep_unary_minus_raises_redcodeerror_not_recursionerror():
    src = "mov " + "-" * 500 + "5, 0"
    with pytest.raises(RedcodeError, match="nested too deeply"):
        parse_warrior(src)


def test_long_equ_chain_raises_redcodeerror_not_recursionerror():
    src = "\n".join(f"a{i} EQU a{i+1}" for i in range(500))
    src += "\na500 EQU 7\nmov a0, 0"
    with pytest.raises(RedcodeError, match="EQU"):
        parse_warrior(src)


def test_exponential_equ_fanout_capped():
    # 8 references per level, 11 levels -> 8^11 tokens if uncapped.
    # Must fail fast with a clean RedcodeError, not hang.
    src = "x0 EQU 1\n" + "\n".join(
        f"x{i} EQU " + " ".join([f"x{i-1}"] * 8) for i in range(1, 12)
    ) + "\nmov x11, 0"
    with pytest.raises(RedcodeError, match="EQU expansion too large"):
        parse_warrior(src)


def test_deep_for_nesting_capped():
    src = "\n".join("FOR 1" for _ in range(200)) + "\nnop\n"
    src += "\n".join("ROF" for _ in range(200))
    with pytest.raises(RedcodeError, match="FOR/ROF nested too deeply"):
        parse_warrior(src)


def test_moderate_nesting_still_parses():
    # 40 levels of parens/unary are under the caps and must keep working.
    src = "dat #" + "(" * 40 + "1" + ")" * 40 + ", #-" + "(" * 30 + "2" + ")" * 30
    w = parse_warrior(src)
    assert w.instructions[0].a_val == 1
    assert w.instructions[0].b_val == CORE_SIZE - 2


def test_equ_on_reserved_opcode_name_rejected():
    with pytest.raises(RedcodeError, match="reserved word"):
        parse_warrior("MOV EQU 5\nmov 0, 0")
    with pytest.raises(RedcodeError, match="reserved word"):
        parse_warrior("dat EQU 0")


def test_equ_predefined_label_may_be_redefined():
    # Predefined labels are "as if defined with EQU at the start" (draft
    # section 2.5), so warriors may override them.
    w = asm("CORESIZE EQU 4\ndat #CORESIZE, #0")
    assert w.instructions[0].a_val == 4


def test_comma_with_both_operands_blank_errors():
    with pytest.raises(RedcodeError, match="blank"):
        parse_warrior("mov ,")


def test_comma_with_blank_side_matches_single_operand_form():
    # Draft section 2.2: "the comma may be omitted" when either operand
    # is blank — so a trailing/leading comma changes nothing.
    assert parse_warrior("dat 5,").instructions == parse_warrior("dat 5").instructions
    assert parse_warrior("mov 5,").instructions == parse_warrior("mov 5").instructions
    assert parse_warrior("mov , 5").instructions == parse_warrior("mov 5").instructions


def test_org_end_errors_carry_line_numbers():
    with pytest.raises(RedcodeError) as excinfo:
        parse_warrior("nop\nnop\norg 9")
    assert excinfo.value.lineno == 3
    with pytest.raises(RedcodeError) as excinfo:
        parse_warrior("nop\nend 5")
    assert excinfo.value.lineno == 2


# ---------------------------------------------------------------------------
# MARS: per-instruction semantics vectors
# ---------------------------------------------------------------------------

def test_dat_kills_process_and_loses_battle():
    b = battle_a("dat 0, 0")
    (ev,) = step_a(b)
    assert ev.died and ev.eliminated and ev.opcode == "DAT"
    assert b.over
    assert b.result().winner == "B"
    assert b.result().cycles == 0  # died in the first partial cycle


def test_mov_i_copies_whole_instruction():
    b = battle_a("mov.i $0, $2\njmp 0")
    step_a(b)
    assert b.core[2] == I("MOV", "I", "$", 0, "$", 2)


def test_mov_ab_from_immediate():
    b = battle_a("mov #7, 2\njmp 0\ndat #1, #1")
    step_a(b)
    assert b.core[2] == I("DAT", "F", "#", 1, "#", 7)


@pytest.mark.parametrize(
    "modifier,expected",
    [
        ("A", I("DAT", "F", "#", 11, "#", 44)),
        ("B", I("DAT", "F", "#", 33, "#", 22)),
        ("AB", I("DAT", "F", "#", 33, "#", 11)),
        ("BA", I("DAT", "F", "#", 22, "#", 44)),
        ("F", I("DAT", "F", "#", 11, "#", 22)),
        ("X", I("DAT", "F", "#", 22, "#", 11)),
    ],
)
def test_mov_field_modifiers(modifier, expected):
    src = f"mov.{modifier} 1, 2\ndat #11, #22\ndat #33, #44"
    b = battle_a(src)
    step_a(b)
    assert b.core[2] == expected


def test_add_sub_mul_wraparound():
    b = battle_a("add #4, 3\nsub.ab #4, 2\nmul.ab #6, 1\ndat #0, #7999")
    step_a(b)
    assert b.core[3].b_val == (7999 + 4) % CORE_SIZE  # 3: wraps mod 8000
    step_a(b)
    assert b.core[3].b_val == 3 - 4 + CORE_SIZE  # 7999: wraps downward
    step_a(b)
    assert b.core[3].b_val == (7999 * 6) % CORE_SIZE


def test_div_and_mod():
    b = battle_a("div.ab #6, 2\nmod.ab #6, 1\ndat #0, #43")
    step_a(b)
    assert b.core[2].b_val == 43 // 6
    step_a(b)
    assert b.core[2].b_val == 7 % 6


def test_div_by_zero_kills_process_leaving_field_unchanged():
    # Draft section 5.5.6: zero divisor -> B-value unchanged, task removed.
    b = battle_a("div.ab #0, 1\ndat #0, #42")
    (ev,) = step_a(b)
    assert ev.died and ev.eliminated
    assert b.core[1] == I("DAT", "F", "#", 0, "#", 42)


def test_div_f_partial_write_then_death():
    # Draft section 5.5.6: with a zero A component, that component is
    # unchanged, the other is divided normally, and the task still dies.
    b = battle_a("div.f 1, 2\ndat #0, #2\ndat #10, #20")
    (ev,) = step_a(b)
    assert ev.died
    assert b.core[2] == I("DAT", "F", "#", 10, "#", 10)


def test_jmp_transfers_control():
    b = battle_a("jmp 2\nnop\nnop")
    step_a(b)
    assert b.procs[0][0] == 2


def test_jmz_and_jmn_conditions():
    # JMZ.B jumps when the B-number is zero; JMN.B when it is not.
    b = battle_a("jmz 3, 1\ndat #0, #0\nnop\nnop")
    step_a(b)
    assert b.procs[0][0] == 3
    b = battle_a("jmz 3, 1\ndat #0, #9\nnop\nnop")
    step_a(b)
    assert b.procs[0][0] == 1
    b = battle_a("jmn 3, 1\ndat #0, #9\nnop\nnop")
    step_a(b)
    assert b.procs[0][0] == 3


def test_jmz_f_needs_both_zero_jmn_f_needs_either_nonzero():
    # Draft sections 5.5.9-5.5.10 (v3.3 wording).
    b = battle_a("jmz.f 3, 1\ndat #0, #9\nnop\nnop")
    step_a(b)
    assert b.procs[0][0] == 1  # B nonzero: no jump
    b = battle_a("jmn.f 3, 1\ndat #0, #9\nnop\nnop")
    step_a(b)
    assert b.procs[0][0] == 3  # B nonzero: jump
    b = battle_a("jmn.f 3, 1\ndat #0, #0\nnop\nnop")
    step_a(b)
    assert b.procs[0][0] == 1  # both zero: no jump


def test_djn_predecrement_then_jump_while_nonzero():
    # Draft section 5.5.11: decrement first, jump if the result is non-zero.
    b = battle_a("djn 2, 1\ndat #0, #2\nnop\nnop")
    step_a(b)
    assert b.core[1].b_val == 1
    assert b.procs[0][0] == 2  # jumped
    # Second pass over the djn (loop it back): 1 -> 0, falls through.
    b = battle_a("djn 0, 1\ndat #0, #1")
    step_a(b)
    assert b.core[1].b_val == 0
    assert b.procs[0][0] == 1  # fell through


def test_spl_queue_insertion_order():
    # Draft section 5.5.15: PC+1 is queued before the split target, so
    # the parent's continuation runs before the child.
    b = battle_a("spl 2\nnop\nnop")
    events = step_a(b, 3)
    assert events[0].spawned
    assert [ev.pc for ev in events] == [0, 1, 2]


def test_seq_sne_skip_semantics():
    b = battle_a("seq 1, 2\ndat #0, #0\ndat #0, #0\nnop")
    step_a(b)
    assert b.procs[0][0] == 2  # equal -> skip to PC+2
    b = battle_a("seq 1, 2\ndat #0, #0\ndat #0, #1\nnop")
    step_a(b)
    assert b.procs[0][0] == 1  # different -> PC+1
    b = battle_a("sne 1, 2\ndat #0, #0\ndat #0, #1\nnop")
    step_a(b)
    assert b.procs[0][0] == 2  # different -> skip


def test_seq_i_compares_whole_instruction():
    b = battle_a("seq.i 1, 2\ndat #0, #0\ndat.f $0, $0\nnop")
    step_a(b)
    assert b.procs[0][0] == 1  # same numbers, different modes: not equal


def test_slt_skip_semantics():
    b = battle_a("slt #1, 1\ndat #0, #5\nnop\nnop")
    step_a(b)
    assert b.procs[0][0] == 2  # 1 < 5: skip to PC+2
    b = battle_a("slt #5, 1\ndat #0, #1\nnop\nnop")
    step_a(b)
    assert b.procs[0][0] == 1  # 5 < 1 false
    # .X is crosswise: skip if src.A < dst.B and src.B < dst.A.
    b = battle_a("slt.x 1, 2\ndat #1, #3\ndat #5, #2\nnop")
    step_a(b)
    assert b.procs[0][0] == 2  # 1 < 2 and 3 < 5


def test_b_indirect_addressing():
    b = battle_a("mov.i 1, @2\ndat #0, #0\ndat #7, #10\njmp 0")
    step_a(b)
    assert b.core[12] == I("DAT", "F", "#", 0, "#", 0)  # dest = 2 + 10
    assert b.core[2].b_val == 10  # plain indirect: no side effect


def test_b_predecrement_indirect():
    b = battle_a("mov.i 1, <2\ndat #0, #0\ndat #7, #10\njmp 0")
    (ev,) = step_a(b)
    assert b.core[2].b_val == 9  # decremented before use
    assert b.core[11] == I("DAT", "F", "#", 0, "#", 0)  # dest = 2 + 9
    assert 2 in ev.writes and 11 in ev.writes


def test_b_postincrement_indirect():
    b = battle_a("mov.i 1, >2\ndat #0, #0\ndat #7, #10\njmp 0")
    step_a(b)
    assert b.core[12] == I("DAT", "F", "#", 0, "#", 0)  # dest = 2 + 10 (old value)
    assert b.core[2].b_val == 11  # incremented after use


def test_a_indirect_predec_postinc():
    # * uses the A-number; { } are its predecrement/postincrement forms.
    b = battle_a("mov.i 1, *2\ndat #0, #0\ndat #10, #7\njmp 0")
    step_a(b)
    assert b.core[12] == I("DAT", "F", "#", 0, "#", 0)
    b = battle_a("mov.i 1, {2\ndat #0, #0\ndat #10, #7\njmp 0")
    step_a(b)
    assert b.core[2].a_val == 9
    assert b.core[11] == I("DAT", "F", "#", 0, "#", 0)
    b = battle_a("mov.i 1, }2\ndat #0, #0\ndat #10, #7\njmp 0")
    step_a(b)
    assert b.core[12] == I("DAT", "F", "#", 0, "#", 0)
    assert b.core[2].a_val == 11


def test_immediate_b_writes_to_self():
    # Immediate B-mode points at the current instruction (draft 5.3.1).
    b = battle_a("mov.ab #5, #0")
    step_a(b)
    assert b.core[0] == I("MOV", "AB", "#", 5, "#", 5)


def test_postincrement_happens_after_source_copy():
    # EMI94 order (draft 5.3.7-5.3.8): the A-instruction copy is taken
    # before the intermediate cell is incremented — so when both are the
    # same cell, the copy carries the pre-increment values.
    b = battle_a("mov.i }0, 2\nnop\nnop")
    step_a(b)
    assert b.core[0].a_val == 1  # intermediate cell incremented
    assert b.core[2] == I("MOV", "I", "}", 0, "$", 2)  # copy is pre-increment


def test_djn_f_decrements_both_jumps_if_either_nonzero():
    b = battle_a("djn.f 2, 1\ndat #1, #0\nnop\nnop")
    step_a(b)
    assert b.core[1] == I("DAT", "F", "#", 0, "#", CORE_SIZE - 1)
    assert b.procs[0][0] == 2  # B-number wrapped to 7999: non-zero, jump
    b = battle_a("djn.f 2, 1\ndat #1, #1\nnop\nnop")
    step_a(b)
    assert b.core[1] == I("DAT", "F", "#", 0, "#", 0)
    assert b.procs[0][0] == 1  # both zero after decrement: fall through


def test_nop_queues_next_without_writes():
    b = battle_a("nop")
    (ev,) = step_a(b)
    assert ev.writes == ()
    assert b.procs[0][0] == 1


def test_core_is_dat_filled():
    b = battle_a("nop")
    assert b.core[100] == CORE_FILL == I("DAT", "F", "$", 0, "$", 0)


def test_battle_event_shape():
    b = battle_a("spl 2\nnop\nnop")
    (ev,) = step_a(b)
    assert isinstance(ev, BattleEvent)
    assert ev.cycle == 0 and ev.warrior == 0 and ev.pc == 0
    assert ev.opcode == "SPL" and ev.modifier == "B"
    assert ev.spawned and not ev.died and not ev.eliminated


def test_spl_process_cap():
    # Queue is capped at MAXPROCESSES; when full, SPL queues only PC+1
    # (draft section 5.5.15).
    b = battle_a("spl 1\njmp -1")
    while not b.over and len(b.procs[0]) < MAX_PROCESSES:
        step_a(b)
        if b.steps > 100000:
            break
    assert len(b.procs[0]) == MAX_PROCESSES
    # One more SPL: spawned must be False, queue stays at the cap.
    while not b.over and b.procs[0][0] != 0:
        step_a(b)
    (ev,) = step_a(b)
    assert ev.opcode == "SPL" and not ev.spawned
    assert len(b.procs[0]) == MAX_PROCESSES


# ---------------------------------------------------------------------------
# Whole battles: known answers, determinism, validation
# ---------------------------------------------------------------------------

def test_imp_vs_imp_ties_at_cycle_limit():
    result = quick_battle(IMP, IMP, seed=1, off_a=0, off_b=100)
    assert result.winner is None
    assert result.cycles == MAX_CYCLES
    assert result.procs_a == 1 and result.procs_b == 1


def test_dwarf_kills_imp_deterministically():
    result = quick_battle(DWARF, IMP, seed=1, off_a=0, off_b=1000)
    assert result.winner == "A"
    assert result.cycles == 2984
    assert result.procs_b == 0


def test_same_seed_byte_identical_transcript_and_state():
    battles = []
    for _ in range(2):
        b = Battle(parse_warrior(DWARF), parse_warrior(IMP), seed=123)
        b.run()
        battles.append(b)
    assert battles[0].off_a == battles[1].off_a
    assert battles[0].off_b == battles[1].off_b
    assert battles[0].fingerprint() == battles[1].fingerprint()
    t1 = battle_transcript(123, battles[0].off_a, battles[0].off_b, battles[0].result())
    t2 = battle_transcript(123, battles[1].off_a, battles[1].off_b, battles[1].result())
    assert t1 == t2


def test_seeded_offsets_stay_within_limits():
    for seed in range(10):
        b = Battle(parse_warrior(IMP), parse_warrior(IMP), seed=seed)
        gap = (b.off_b - b.off_a) % CORE_SIZE
        assert MIN_SEPARATION <= gap <= CORE_SIZE - MIN_SEPARATION


def test_explicit_offset_validation():
    imp = parse_warrior(IMP)
    with pytest.raises(ValueError, match="separation"):
        Battle(imp, imp, off_a=0, off_b=MIN_SEPARATION - 1)
    with pytest.raises(ValueError, match="separation"):
        Battle(imp, imp, off_a=0, off_b=CORE_SIZE - MIN_SEPARATION + 1)
    with pytest.raises(ValueError, match="out of range"):
        Battle(imp, imp, off_a=0, off_b=CORE_SIZE)
    # Exactly MIN_SEPARATION is fine.
    Battle(imp, imp, off_a=0, off_b=MIN_SEPARATION)


def test_max_warrior_length_enforced():
    source = f"FOR {MAX_WARRIOR_LEN + 1}\nnop\nROF"
    with pytest.raises(RedcodeError, match="instruction"):
        parse_warrior(source)
    assert validate_warrior(source) != []
    ok = f"FOR {MAX_WARRIOR_LEN}\nnop\nROF"
    assert len(parse_warrior(ok).instructions) == MAX_WARRIOR_LEN


def test_battle_transcript_format():
    res = BattleResult("A", 100, 200, 1, 0, 0, 100, 7)
    assert battle_transcript(7, 0, 100, res, round_no=2) == (
        "ROUND 2 seed=7 off=0,100\nROUND 2 OUT 1-0 cycles=100\n"
    )
    res = BattleResult("B", 50, 100, 0, 3, 0, 100, 7)
    assert "ROUND 1 OUT 0-1 cycles=50\n" in battle_transcript(7, 0, 100, res)
    res = BattleResult(None, 80000, 160000, 1, 1, 0, 100, 7)
    assert "OUT tie cycles=80000" in battle_transcript(7, 0, 100, res)


def test_sha256_warrior_normalizes_line_endings():
    lf = "mov.i $0, $1\n"
    crlf = "mov.i $0, $1\r\n"
    cr = "mov.i $0, $1\r"
    assert sha256_warrior(lf) == sha256_warrior(crlf) == sha256_warrior(cr)
    assert sha256_warrior(lf) != sha256_warrior("mov.i $0, $2\n")


def test_validate_warrior_ok_and_problems():
    assert validate_warrior(IMP) == []
    problems = validate_warrior("moo 0, 1")
    assert len(problems) == 1 and "unknown opcode" in problems[0]
    assert validate_warrior("ldp #0, 1") != []


def test_load_warrior_file(tmp_path):
    path = tmp_path / "imp.red"
    path.write_text(IMP)
    w = load_warrior_file(path)
    assert w.name == "Imp"
    assert w.instructions == (I("MOV", "I", "$", 0, "$", 1),)
    # Name falls back to the file stem when no ;name is present.
    bare = tmp_path / "silly.red"
    bare.write_text("mov.i $0, $1\n")
    assert load_warrior_file(bare).name == "silly"


def test_imp_and_dwarf_bundled_warriors_assemble():
    imp = parse_warrior(IMP)
    dwarf = parse_warrior(DWARF)
    assert imp.name == "Imp" and imp.start == 0
    assert dwarf.name == "Dwarf" and dwarf.start == 0
    assert len(dwarf.instructions) == 4
