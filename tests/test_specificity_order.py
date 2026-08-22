"""Pillar A of the 0.4 plan, fifth slice: descending specificity.

The flagged pair is never the risk — its selectors differ in specificity,
so their mutual order decides no winner. The risk is everything the mover
crosses, at-rule interiors included (read, never cut): an exact
specificity tie is decided by order, and the move would flip it. A tie
blocks the move unless a disproof lands — no shared property (shorthands
respected), different concrete element types, or no element in **this
book's documents** matching both branches. The detector was calibrated
against Calibre's own bundle until the shelf's 586 findings reproduced
exactly.
"""

from __future__ import annotations

from epubforge.stages import style

from tests.test_shelf_refusals import rules_of
from tests.test_duplicate_selectors import build, sheet_of


BODY_TOC = (
    '<div class="toc"><p class="jeden">Spis</p></div>'
    '<div class="rozdzial"><p class="dwa">Treść rozdziału.</p></div>'
    '<h1>Tytuł</h1>'
)

BODY_NESTED = (
    '<div class="toc"><div class="rozdzial"><p class="jeden">Zagnieżdżone.'
    "</p></div></div><h1>Tytuł</h1>"
)


class TestTheProvableMoves:
    def test_a_generic_rule_climbs_above_the_specific_one(self, tmp_path):
        """`h1` after `.rozdzial h1` is the template's shape of the shelf's
        586. Nothing between ties with the mover, so it climbs and the
        finding is gone."""
        sheet = ".rozdzial h1 { color: red; } h1 { margin: 0; }"
        result = build(tmp_path, sheet=sheet, body=BODY_TOC + '<div class="rozdzial"><h1>W rozdziale</h1></div>')
        out = sheet_of(result)
        assert out.index("h1 {") < out.index(".rozdzial h1")
        assert "css.specificity-reordered" in rules_of(result)

    def test_ties_between_bystanders_do_not_block(self, tmp_path):
        """`.toc p` and `.rozdzial p` tie with each other — but neither
        moves, and the mover `p` (0,0,1) ties with nothing on the road.
        Bystanders keep their relative order, so their tie is not the
        mover's problem. This is the shelf template's exact shape."""
        sheet = (
            ".rozdzial p { color: red; } "
            ".toc p { color: blue; } "
            "p { margin: 0; }"
        )
        result = build(tmp_path, sheet=sheet, body=BODY_TOC)
        out = sheet_of(result)
        assert out.index("p {") < out.index(".rozdzial p")
        assert out.index(".rozdzial p") < out.index(".toc p")
        assert "css.specificity-reordered" in rules_of(result)

    def test_a_typeless_tie_this_book_disproves_lets_the_move_go(self, tmp_path):
        """`.dwa` on the road ties with the climbing `.jeden` and neither
        names an element type — only the documents can settle it, and in
        this book no element carries both classes, so the move goes."""
        sheet = (
            ".rozdzial .jeden { margin: 2em; } "
            ".dwa { margin-top: 1em; } "
            ".jeden { margin: 0; }"
        )
        result = build(tmp_path, sheet=sheet, body=BODY_TOC)
        out = sheet_of(result)
        assert out.index(".jeden {") < out.index(".rozdzial .jeden")
        assert "css.specificity-reordered" in rules_of(result)

    def test_different_element_types_cannot_meet(self, tmp_path):
        """The mover `h2` ties in specificity with `h1` on the road, but
        no element is both — the cheapest disproof, no document needed."""
        sheet = (
            ".rozdzial h2 { color: red; } "
            "h1 { color: green; } "
            "h2 { margin: 0; }"
        )
        result = build(
            tmp_path, sheet=sheet,
            body=BODY_TOC + '<div class="rozdzial"><h2>Śródtytuł</h2></div>',
        )
        out = sheet_of(result)
        assert out.index("h2 {") < out.index(".rozdzial h2")
        assert "css.specificity-reordered" in rules_of(result)


    def test_a_tie_without_a_shared_property_is_harmless(self, tmp_path):
        """The tie is real — one element carries both classes — but the
        two rules fight over nothing: one paints, the other spaces. Order
        picks winners only where declarations share a slot, so the move
        goes. The mutation that skips the property disproof fails here."""
        sheet = (
            ".rozdzial .jeden { margin: 2em; } "
            ".dwa { color: blue; } "
            ".jeden { margin: 0; }"
        )
        body = (
            '<div class="rozdzial"><p class="jeden dwa">Obie klasy.</p></div>'
            "<h1>Tytuł</h1>"
        )
        result = build(tmp_path, sheet=sheet, body=body)
        out = sheet_of(result)
        assert out.index(".jeden {") < out.index(".rozdzial .jeden")
        assert "css.specificity-reordered" in rules_of(result)


    def test_a_tie_over_the_same_value_is_harmless(self, tmp_path):
        """The tie is real and the property shared — but both sides say
        `margin: 0`, and a fight both sides win identically is no fight.
        The mutation that compares names without values fails here."""
        sheet = (
            ".rozdzial .jeden { margin: 2em; } "
            ".dwa { margin: 0; } "
            ".jeden { margin: 0; }"
        )
        body = (
            '<div class="rozdzial"><p class="jeden dwa">Obie klasy.</p></div>'
            "<h1>Tytuł</h1>"
        )
        result = build(tmp_path, sheet=sheet, body=body)
        out = sheet_of(result)
        assert out.index(".jeden {") < out.index(".rozdzial .jeden")
        assert "css.specificity-reordered" in rules_of(result)

    def test_an_at_rule_holding_no_conflict_is_crossed(self, tmp_path):
        """The `@media` on the road holds only a colour for `h1`; the
        climbing `h1` carries margins. Its inside is read — not cut — and
        holds no tie worth blocking over, so the move crosses it. This is
        what unblocked six of seven movers in the probe book."""
        sheet = (
            ".rozdzial h1 { margin: 2em; } "
            "@media print { h1 { color: black; } } "
            "h1 { margin: 0; }"
        )
        result = build(tmp_path, sheet=sheet, body=BODY_TOC)
        out = sheet_of(result)
        assert out.index("h1 {") < out.index(".rozdzial h1")
        assert out.index(".rozdzial h1") < out.index("@media")
        assert "css.specificity-reordered" in rules_of(result)


class TestTheBlockedMoves:
    def test_a_move_that_mints_as_much_as_it_fixes_is_refused(self, tmp_path):
        """The mover's list carries two keys: climbing fixes its `b` pair
        and plants its `div h2` branch above a plain `h2` — one finding
        out, one finding in. A move earns its keep by the gate's own
        count, and this one earns nothing. The mutation that accepts any
        lawful move fails here."""
        sheet = (
            ".rozdzial b { margin: 9em; } "
            "h2 { margin: 1em; } "
            "b, div h2 { margin: 2em; }"
        )
        body = (
            '<div class="rozdzial"><p class="jeden">Tu <b>wyraz</b>.</p>'
            "<div><h2>Śródtytuł</h2></div></div>"
        )
        result = build(tmp_path, sheet=sheet, body=body)
        out = sheet_of(result)
        assert out.index(".rozdzial b") < out.index("b, div h2")
        assert "css.specificity-kept" in rules_of(result)
        assert "css.specificity-reordered" not in rules_of(result)

    def test_a_typeless_tie_the_book_confirms_blocks_the_move(self, tmp_path):
        """The same sheet as the disproved-tie case — but here one element
        carries both classes, so the tie is real and order decides it.
        The mutation that skips the document check fails here."""
        sheet = (
            ".rozdzial .jeden { margin: 2em; } "
            ".dwa { margin-top: 1em; } "
            ".jeden { margin: 0; }"
        )
        body = (
            '<div class="rozdzial"><p class="jeden dwa">Obie klasy.</p></div>'
            '<h1>Tytuł</h1>'
        )
        result = build(tmp_path, sheet=sheet, body=body)
        out = sheet_of(result)
        assert ".dwa { margin-top: 1em; } .jeden { margin: 0; }" in out
        assert "css.specificity-kept" in rules_of(result)
        assert "css.specificity-reordered" not in rules_of(result)

    def test_a_tie_the_book_confirms_blocks_the_move(self, tmp_path):
        """`.toc p` stands on the road and ties with the climbing
        `p.jeden` — and in THIS book the containers are nested, so one
        element matches both and their order is the winner. The move
        would flip it; it stays and is counted."""
        sheet = (
            ".rozdzial p.jeden { margin: 2em; } "
            ".toc p { margin: 1em; } "
            "p.jeden { margin: 0; }"
        )
        result = build(tmp_path, sheet=sheet, body=BODY_NESTED)
        out = sheet_of(result)
        assert ".toc p { margin: 1em; } p.jeden { margin: 0; }" in out
        assert "css.specificity-kept" in rules_of(result)
        assert "css.specificity-reordered" not in rules_of(result)

    def test_a_rule_the_mover_does_not_jump_never_blocks(self, tmp_path):
        """The same nested book — but the tying `.toc p` stands ABOVE the
        offender, so the climbing `p.jeden` never crosses it and their
        order survives the move untouched. The move goes; blocking here
        would be caution about nothing."""
        sheet = (
            ".toc p { color: blue; } "
            ".rozdzial p.jeden { color: red; } "
            "p.jeden { margin: 0; }"
        )
        result = build(tmp_path, sheet=sheet, body=BODY_NESTED)
        out = sheet_of(result)
        assert out.index(".toc p") < out.index("p.jeden { margin")
        assert out.index("p.jeden { margin") < out.index(".rozdzial p.jeden")
        assert "css.specificity-reordered" in rules_of(result)

    def test_a_tie_inside_the_offenders_own_list_blocks(self, tmp_path):
        """The offender is a selector list, and its *other* branch ties
        with the mover — the move crosses the offender itself, so that
        tie is just as real. The mutation that checks only the rules
        strictly between fails here."""
        sheet = (
            ".rozdzial .jeden, .dwa { margin: 2em; } "
            ".jeden { margin: 0; }"
        )
        body = (
            '<div class="rozdzial"><p class="jeden dwa">Obie klasy.</p></div>'
            "<h1>Tytuł</h1>"
        )
        result = build(tmp_path, sheet=sheet, body=body)
        out = sheet_of(result)
        assert out.index(".dwa") < out.index(".jeden { margin")
        assert "css.specificity-kept" in rules_of(result)
        assert "css.specificity-reordered" not in rules_of(result)

    def test_a_branch_beyond_the_simple_language_blocks_its_tie(self, tmp_path):
        """`p:first-child` ties with the mover and offers nothing the
        document disproof can read — the tie blocks, conservatively."""
        sheet = (
            ".rozdzial p.jeden { margin: 2em; } "
            "p:first-child { margin: 1em; } "
            "p.jeden { margin: 0; }"
        )
        result = build(tmp_path, sheet=sheet, body=BODY_TOC)
        assert "css.specificity-kept" in rules_of(result)
        assert "css.specificity-reordered" not in rules_of(result)

    def test_an_at_rule_holding_a_conflicting_tie_blocks(self, tmp_path):
        """The crossed `@media` holds an `h1` rule that ties with the
        mover on the same property — its condition is unreadable, but
        whenever it is on, order decides. Read, not cut; blocked."""
        sheet = (
            ".rozdzial h1 { margin: 2em; } "
            "@media print { h1 { margin: 3em; } } "
            "h1 { margin: 0; }"
        )
        result = build(tmp_path, sheet=sheet, body=BODY_TOC)
        out = sheet_of(result)
        assert out.index(".rozdzial h1") < out.index("@media")
        assert "css.specificity-kept" in rules_of(result)

    def test_the_opt_out_counts_instead(self, tmp_path):
        sheet = ".rozdzial h1 { color: red; } h1 { margin: 0; }"
        result = build(tmp_path, sheet=sheet, body=BODY_TOC, sweep=False)
        out = sheet_of(result)
        assert out.index(".rozdzial h1") < out.index("h1 {")
        assert "css.specificity-found" in rules_of(result)


class TestTheGuard:
    def test_a_failed_verification_hands_the_sheet_back(self, tmp_path, monkeypatch):
        monkeypatch.setattr(style, "_structurally_sound", lambda text: False)
        sheet = ".rozdzial h1 { color: red; } h1 { margin: 0; }"
        result = build(tmp_path, sheet=sheet, body=BODY_TOC)
        out = sheet_of(result)
        assert out.index(".rozdzial h1") < out.index("h1 {")
        assert "css.specificity-unverified" in rules_of(result)

    def test_the_moved_rules_survive_to_the_byte(self, tmp_path):
        """A move is a move: the same rules, just elsewhere. The body of
        the moved rule arrives intact, comments and all."""
        sheet = (
            ".rozdzial h1 { color: red; } "
            "h1 { margin: 0; /* uwaga wydawcy */ line-height: 1.2; }"
        )
        result = build(tmp_path, sheet=sheet, body=BODY_TOC)
        out = sheet_of(result)
        assert "margin: 0; /* uwaga wydawcy */ line-height: 1.2;" in out
        assert "css.specificity-reordered" in rules_of(result)
