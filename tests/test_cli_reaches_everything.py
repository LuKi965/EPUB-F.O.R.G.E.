"""Every choice this program offers has to be offerable from the command line.

The mirror of `test_gui_reaches_everything.py`, and the audit of 2026-09-03
(A-09) is why it exists: the window had a ratchet, the command line had none,
and nine fields had drifted into "window only" — among them the detectors that
produce most of what a batch asks a person. A person running a shelf from a
script could not switch them off.

Same rule, same shape: a policy field is either set somewhere in
`build_policy`, or it is named below with the argument for why a flag is not
the right way to reach it. A field with neither fails.
"""

from __future__ import annotations

import pathlib
import re

import pytest

from epubforge.cli import build_parser, build_policy
from epubforge.policy import Policy

ROOT = pathlib.Path(__file__).resolve().parent.parent

NOT_ON_THE_COMMAND_LINE: dict[str, str] = {
    "strict": "what --mode strict means; not a field a person sets on its own",
    "rewrite_content": "the same: 'rebuild the container only' is --mode minimal, not a flag",
    "content_dir": (
        "where the package document sits inside the archive — a diagnostic for "
        "reproducing one reader's layout, reachable from the library API, and "
        "not a decision about a book"
    ),
    "package_name": "the same, and for the same reason",
    "verify_text_survives": (
        "K1 is the one gate this program promises never to stand down. The "
        "window offers the tick beside a warning a person reads once; a flag "
        "would sit in a script for ever and switch it off for every book after. "
        "The library API still has the field for a test that needs it"
    ),
}


def policy_fields() -> list[str]:
    text = (ROOT / "epubforge" / "policy.py").read_text(encoding="utf-8")
    body = text.split("class Policy:", 1)[1]
    return re.findall(r"^    ([a-z_][a-z_0-9]*): ", body, re.M)


def build_policy_source() -> str:
    text = (ROOT / "epubforge" / "cli.py").read_text(encoding="utf-8")
    start = text.index("def build_policy(")
    end = text.index("\ndef ", start + 1)
    return text[start:end]


class TestEveryChoiceIsReachable:
    @pytest.mark.parametrize("field", policy_fields())
    def test_a_policy_field_is_either_a_flag_or_argued_away(self, field):
        if field in NOT_ON_THE_COMMAND_LINE:
            assert NOT_ON_THE_COMMAND_LINE[field].strip(), f"{field} is exempt with no reason given"
            return
        assert f"policy.{field}" in build_policy_source(), (
            f"Policy.{field} can be set from the window and not from the command "
            f"line. Either give it a flag or add it to NOT_ON_THE_COMMAND_LINE "
            f"with the argument for why a flag is not how a person reaches it."
        )

    @pytest.mark.parametrize("field", sorted(NOT_ON_THE_COMMAND_LINE))
    def test_no_exemption_outlives_its_field(self, field):
        assert field in policy_fields(), f"{field} is exempt from a rule it is no longer subject to"


def parsed(*flags: str):
    return build_policy(build_parser().parse_args(["build", "x.epub", *flags]))


class TestTheFlagsTheAuditAskedFor:
    """Named one by one: these are the nine the mirror found on its first run,
    and a parametrised green says nothing about which."""

    def test_the_defaults_leave_every_detector_on(self):
        policy = parsed()
        assert policy.detect_undescribed_images and policy.detect_layout_tables
        assert policy.detect_typography and policy.detect_hyphens and policy.detect_substitutions
        assert policy.transcode_images and policy.deobfuscate_fonts and policy.remember_decisions

    @pytest.mark.parametrize(
        "flag, field",
        [
            ("--no-image-questions", "detect_undescribed_images"),
            ("--no-table-questions", "detect_layout_tables"),
            ("--no-typography-questions", "detect_typography"),
            ("--no-hyphen-questions", "detect_hyphens"),
            ("--no-substitution-questions", "detect_substitutions"),
            ("--keep-image-formats", "transcode_images"),
            ("--keep-font-obfuscation", "deobfuscate_fonts"),
            ("--no-remember-decisions", "remember_decisions"),
        ],
    )
    def test_each_flag_switches_exactly_its_field_off(self, flag, field):
        with_flag = parsed(flag)
        without = parsed()
        assert getattr(with_flag, field) is False
        assert getattr(without, field) is True
        # And nothing else moved: the flag is a switch, not a mode.
        for other in policy_fields():
            if other != field:
                assert getattr(with_flag, other) == getattr(without, other), other

    def test_a_flag_never_answers_a_question_on_anybodys_behalf(self):
        """Switching a detector off is not the same as answering "keep" to
        everything it would have asked: the policy has no field that says
        "assume the recommended answer", and this pins that it does not grow
        one by the back door."""
        policy = parsed("--no-image-questions", "--no-table-questions")
        assert not any(
            name for name in policy_fields() if "assume" in name or "auto_answer" in name
        )
        assert isinstance(policy, Policy)
