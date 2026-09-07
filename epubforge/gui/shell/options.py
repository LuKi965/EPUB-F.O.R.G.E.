"""Every setting the drawer can show, declared once.

This is the catalogue the advanced drawer renders and the adapter reads. It is
deliberately *declarative*: a row here says what a setting is called, what kind
of control it needs, which group it belongs to and whether it is risky — and
nothing about what the engine does with it. Turning a preset and a set of
overrides into a `Policy` happens in one place, `backend.policy_for`, with its
own tests.

Two decisions this file makes on purpose:

**Grouping is by consequence, not by module.** "Remove unused files" sits with
the basics because that is where a person looks for it, not with the resource
sweep it shares code with.

**Labels come from the existing catalogue.** The old window's tooltips are
years of careful writing about what each switch does to a book; the redesign
changes where they are shown, not what they say. Only genuinely new settings
get new keys.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Option:
    """One setting: its identity, its control, and how it is spoken about."""

    #: Identity used in `RebuildPlan.overrides` and, for most of them, the name
    #: of the `Policy` field the adapter sets.
    key: str
    category: str
    #: "bool", "choice", "text" or "int".
    kind: str
    label_key: str
    help_key: str
    #: Engine values, in the order they are offered. Labels are looked up as
    #: `f"{label_key}.{value}"`, which is how the old window already spells them.
    choices: tuple[str, ...] = ()
    #: Shown with a warning badge and a sentence about the consequence. A risky
    #: option is never switched on by changing a preset without saying so.
    risky: bool = False
    #: Behind "show expert options": diagnostics and run mechanics, not choices
    #: about a book.
    expert: bool = False
    #: For "int": bounds and step.
    minimum: int = 0
    maximum: int = 0
    step: int = 1
    placeholder_key: str = ""


#: Category id → (icon glyph, label key). The order is the drawer's order.
CATEGORIES = (
    ("basics", "settings", "shell.cat.basics"),
    ("compat", "compat", "shell.cat.compat"),
    ("look", "text", "shell.cat.look"),
    ("words", "book", "shell.cat.words"),
    ("assets", "image", "shell.cat.assets"),
    ("metadata", "tag", "shell.cat.metadata"),
    ("validation", "shield", "shell.cat.validation"),
)


OPTIONS: tuple[Option, ...] = (
    # --- basics ---------------------------------------------------------
    Option("write_ncx", "basics", "bool", "policy.ncx", "policy.ncx.tip"),
    Option("reorganize_files", "basics", "bool", "policy.layout", "policy.layout.tip"),
    Option("remove_junk", "basics", "bool", "policy.junk", "policy.junk.tip"),
    Option("drop_orphans", "basics", "bool", "policy.orphans", "policy.orphans.tip", risky=True),
    Option("strip_scripts", "basics", "bool", "policy.scripts", "policy.scripts.tip", risky=True),
    # --- devices and standard -------------------------------------------
    Option("compat.kindle", "compat", "bool", "compat.kindle", "compat.kindle.tip"),
    Option("compat.kobo", "compat", "bool", "compat.kobo", "compat.kobo.tip"),
    Option("compat.apple", "compat", "bool", "compat.apple", "compat.apple.tip"),
    Option("compat.legacy", "compat", "bool", "compat.legacy", "compat.legacy.tip"),
    Option("kepub", "compat", "bool", "compat.kepub", "compat.kepub.tip"),
    # --- appearance -----------------------------------------------------
    Option("remove_dead", "look", "bool", "policy.dead", "policy.dead.tip", risky=True),
    Option("sweep_style_blocks", "look", "bool", "policy.style-sweep", "policy.style-sweep.tip"),
    Option("translate_class_names", "look", "bool", "policy.class-names", "policy.class-names.tip"),
    Option("relative_units", "look", "bool", "policy.relative.units", "policy.relative.units.tip", risky=True),
    Option("detect_typography", "look", "bool", "policy.detect.typography", "policy.detect.typography.tip"),
    Option("typography", "look", "bool", "policy.typography", "policy.typography.tip", risky=True),
    Option("subset_fonts", "look", "bool", "policy.subset-fonts", "policy.subset-fonts.tip", risky=True),
    # --- the words themselves, and the questions about them --------------
    Option("link_footnotes", "words", "bool", "policy.footnotes", "policy.footnotes.tip"),
    Option("detect_hyphens", "words", "bool", "policy.hyphens", "policy.hyphens.tip"),
    Option(
        "hyphen_review", "words", "choice", "policy.hyphen.review", "policy.hyphen.review.tip",
        choices=("confirmed", "grouped", "each"),
    ),
    Option("detect_substitutions", "words", "bool", "policy.substitutions", "policy.substitutions.tip"),
    Option(
        "empty_paragraph_runs", "words", "choice", "policy.paragraphs.empty",
        "policy.paragraphs.empty.tip", choices=("ask", "keep", "remove"),
    ),
    Option(
        "pdf_running_heads", "words", "choice", "policy.pdf.heads", "policy.pdf.heads.tip",
        choices=("ask", "keep", "remove"),
    ),
    Option("repair_encoding", "words", "bool", "policy.repair.encoding", "policy.repair.encoding.tip"),
    Option("detect_undescribed_images", "words", "bool", "policy.detect.images", "policy.detect.images.tip"),
    Option("detect_layout_tables", "words", "bool", "policy.detect.tables", "policy.detect.tables.tip"),
    Option("ask", "words", "bool", "policy.ask", "policy.ask.tip"),
    Option("remember_decisions", "words", "bool", "policy.remember", "policy.remember.tip"),
    # --- files carried along ---------------------------------------------
    Option("deobfuscate_fonts", "assets", "bool", "policy.fonts", "policy.fonts.tip"),
    Option("transcode_images", "assets", "bool", "policy.images", "policy.images.tip"),
    Option(
        "watermarks", "assets", "choice", "policy.watermark", "policy.watermark.tip",
        choices=("keep", "consolidate", "gather", "remove"),
    ),
    Option("remove_shop_notices", "assets", "bool", "policy.shop.notices", "policy.shop.notices.tip", risky=True),
    # --- what the package says about the book ------------------------------
    Option("meta.title", "metadata", "text", "meta.title", "meta.title.tip", placeholder_key="meta.placeholder"),
    Option("meta.author", "metadata", "text", "meta.author", "meta.author.tip", placeholder_key="meta.placeholder"),
    Option("meta.language", "metadata", "text", "meta.language", "meta.language.tip", placeholder_key="meta.placeholder"),
    Option(
        "accept_reconstructed_metadata", "metadata", "bool",
        "policy.metadata.reconstructed", "policy.metadata.reconstructed.tip",
    ),
    # --- gates -------------------------------------------------------------
    Option("validate", "validation", "bool", "policy.validate", "policy.validate.tip"),
    Option(
        "validate_before_publish", "validation", "choice", "policy.gate", "policy.gate.tip",
        choices=("off", "no-new-errors", "clean"),
    ),
    Option(
        "render_gate", "validation", "choice", "policy.render.gate", "policy.render.tip",
        choices=("off", "report", "stop"),
    ),
    Option("render_all", "validation", "bool", "policy.render.all", "policy.render.all.tip"),
    Option("verify_text_survives", "validation", "bool", "policy.text.invariant", "policy.text.invariant.tip"),
    Option(
        "accept_unverified_render", "validation", "bool",
        "policy.render.unverified", "policy.render.unverified.tip", risky=True,
    ),
    # --- expert: how this run behaves, not what it does to the book --------
    Option("plan_only", "validation", "bool", "policy.plan.only", "policy.plan.only.tip", expert=True),
    Option("reproducible", "validation", "bool", "policy.reproducible", "policy.reproducible.tip", expert=True),
    Option("check_memory", "validation", "bool", "policy.memory", "policy.memory.tip", expert=True),
    Option(
        "memory_limit", "validation", "text", "policy.memory.limit", "policy.memory.limit.tip",
        expert=True, placeholder_key="policy.memory.limit.placeholder",
    ),
    Option(
        "time_budget_seconds", "validation", "int", "policy.time.budget", "policy.time.budget.tip",
        expert=True, minimum=30, maximum=24 * 3600, step=60,
    ),
    Option(
        "content_dir", "basics", "text", "policy.content.dir", "policy.content.dir.tip",
        expert=True, placeholder_key="policy.content.dir.placeholder",
    ),
    Option(
        "package_name", "basics", "text", "policy.package.name", "policy.package.name.tip",
        expert=True, placeholder_key="policy.package.name.placeholder",
    ),
)

BY_KEY = {option.key: option for option in OPTIONS}


def in_category(category: str, *, expert: bool = False) -> tuple[Option, ...]:
    """Options of one category — the everyday ones, or the expert ones."""
    return tuple(
        option for option in OPTIONS
        if option.category == category and option.expert is expert
    )


def searchable(option: Option, translate) -> str:
    """The text a search box matches: label and help, in the active language."""
    return f"{translate(option.label_key)} {translate(option.help_key)}".lower()
