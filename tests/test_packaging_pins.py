"""F-027 — what the build is allowed to pull in without anybody deciding.

The audit's complaint in one sentence: *versions of parsers are part of the
product's semantics, so `>=` without a lock does not guarantee two builds of one
release produce the same file.* It is right. `lxml` decides how a recovered
document comes out, `cssutils` decides how a stylesheet is serialised, `Pillow`
decides what a transcoded image is.

This does not pretend to be a lockfile and neither do the bounds it checks. What
it pins is the two things that can be checked from a repository: that no
dependency is open at the top end, and that the bundled validator is the version
somebody chose. The real lock, with hashes, has to be generated on the runner
that builds — see `docs/PLAN-PO-AUDYCIE.md`, where it is still open.
"""

from __future__ import annotations

import pathlib
import re
import tomllib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent


def declared() -> dict[str, list[str]]:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    groups = {"dependencies": data["project"]["dependencies"]}
    groups.update(data["project"].get("optional-dependencies", {}))
    return groups


def requirements() -> list[tuple[str, str]]:
    return [
        (group, entry)
        for group, entries in declared().items()
        for entry in entries
    ]


class TestNothingIsOpenAtTheTop:
    @pytest.mark.parametrize(("group", "entry"), requirements())
    def test_every_dependency_has_an_upper_bound(self, group, entry):
        """A new major landing in a release without somebody choosing it is how
        two builds of one version stop producing the same file."""
        assert "<" in entry, f"{entry} in [{group}] can accept any future major"

    @pytest.mark.parametrize(("group", "entry"), requirements())
    def test_and_a_lower_one(self, group, entry):
        assert ">=" in entry, f"{entry} in [{group}] does not say what it needs"


class TestTheBundledValidator:
    def version(self) -> str:
        text = (ROOT / "packaging" / "build.py").read_text(encoding="utf-8")
        return re.search(r'EPUBCHECK_VERSION = "([^"]+)"', text).group(1)

    def test_it_is_the_version_this_project_measured(self):
        """Moved 5.2.1 → 5.3.0 on evidence rather than on the release being
        newer: both were run over every book of the public corpus in two modes
        and returned the same messages. Changing this number means doing that
        again — the corpus ledger records the checker per book precisely so a
        run whose validator changed is not compared with one whose did not."""
        assert self.version() == "5.3.0"

    def test_the_download_url_follows_the_version(self):
        text = (ROOT / "packaging" / "build.py").read_text(encoding="utf-8")
        assert "{EPUBCHECK_VERSION}" in text
        assert re.search(r'EPUBCHECK_URL = \(\s*\n\s*f"https://github\.com/w3c/epubcheck', text)

    def test_the_docstring_does_not_name_a_version_it_no_longer_ships(self):
        """A usage example naming 5.2.1 is a small lie that survives a version
        bump, and this file exists because small lies about versions are the
        finding."""
        text = (ROOT / "packaging" / "build.py").read_text(encoding="utf-8")
        docstring = text.split('"""')[1]
        for stale in re.findall(r"epubcheck-(\d+\.\d+\.\d+)", docstring):
            assert stale == self.version()


class TestTheBuildSaysWhatBuiltIt:
    """The half of a lock that a repository *can* carry: not what the versions
    will be, but a record of what they were."""

    def workflow(self) -> str:
        return (ROOT / ".github" / "workflows" / "build-windows.yml").read_text(encoding="utf-8")

    def test_a_manifest_is_written(self):
        assert "build-manifest.txt" in self.workflow()

    def test_it_records_the_resolved_versions(self):
        assert "pip freeze" in self.workflow()

    def test_it_reaches_the_person_holding_the_binary(self):
        """Written and not attached is written and lost. It has to be in both
        the artifact list and the release."""
        assert self.workflow().count("build-manifest.txt") >= 3
