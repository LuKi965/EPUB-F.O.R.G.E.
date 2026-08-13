"""F-027 — what the build is allowed to pull in without anybody deciding.

The audit's complaint in one sentence: *versions of parsers are part of the
product's semantics, so `>=` without a lock does not guarantee two builds of one
release produce the same file.* It is right. `lxml` decides how a recovered
document comes out, `cssutils` decides how a stylesheet is serialised, `Pillow`
decides what a transcoded image is.

The bounds are half of it: no dependency open at the top end, and the bundled
validator the version somebody chose. The other half is the lock itself, which a
repository cannot generate for itself — hashes are per *artifact*, and artifacts
are per platform and per interpreter, so a lock resolved on this machine locks
the wrong files for a Windows release. `.github/workflows/lock.yml` resolves it
on the runner that builds; the result is committed here, and the classes at the
bottom of this file are what keeps it honest once it is.
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


class TestTheLockItself:
    """Generated on Windows by `lock.yml`, committed by hand, checked here.

    A lock is worth exactly what is checked about it. Committed and then left
    to drift, it is worse than none: it looks like a guarantee, and the build
    installs from it while `pyproject.toml` says something else. So every claim
    it makes is asserted rather than assumed — that it has hashes at all, that
    it covers what this project declares, and that what it pins is inside the
    bounds beside it.
    """

    def lock(self, name: str = "requirements.lock") -> str:
        path = ROOT / name
        assert path.is_file(), (
            f"{name} is missing. Run the 'Generate the dependency lock' "
            f"workflow, download the artifact and commit it — it cannot be "
            f"produced here, because hashes are per platform."
        )
        return path.read_text(encoding="utf-8")

    def pinned(self, name: str = "requirements.lock") -> dict[str, str]:
        return {
            match.group(1).lower().replace("_", "-"): match.group(2)
            for match in re.finditer(r"^([A-Za-z0-9._-]+)==([^\s\\]+)", self.lock(name), re.M)
        }

    def blocks(self, name: str = "requirements.lock") -> dict[str, list[str]]:
        """`{package: [hash, ...]}`, read the way pip reads it: a pin owns
        every continuation line under it."""
        found: dict[str, list[str]] = {}
        current = None
        for line in self.lock(name).splitlines():
            pin = re.match(r"^([A-Za-z0-9._-]+)==", line)
            if pin:
                current = pin.group(1).lower().replace("_", "-")
                found[current] = []
            if current is not None and "--hash=sha256:" in line:
                found[current] += re.findall(r"--hash=sha256:([a-f0-9]{64})", line)
            elif line and not line[0].isspace() and not pin:
                current = None
        return found

    def test_both_locks_are_present(self):
        assert self.lock()
        assert self.lock("pyinstaller.lock")

    def test_every_pin_carries_hashes(self):
        """`--require-hashes` is the whole point: without a hash on every line
        pip refuses the file outright, so a lock missing one is not a stricter
        install, it is a build that falls back to the ranges."""
        for name in ("requirements.lock", "pyinstaller.lock"):
            for package, hashes in self.blocks(name).items():
                assert hashes, f"{package} in {name} is pinned without a hash"

    @pytest.mark.parametrize(
        "entry", [entry for group, entry in requirements() if group != "dev"]
    )
    def test_it_covers_what_this_project_declares(self, entry):
        """A lock that is missing a dependency installs it unpinned, or not at
        all — and `--require-hashes` turns the second into a failed build on the
        day somebody adds a package and forgets to regenerate."""
        name = re.split(r"[<>=!\[; ]", entry, 1)[0].strip().lower().replace("_", "-")
        assert name in self.pinned(), f"{name} is declared and not in requirements.lock"

    @pytest.mark.parametrize(("group", "entry"), requirements())
    def test_what_it_pins_is_inside_the_bounds_beside_it(self, group, entry):
        """The failure this catches: `pyproject.toml` is tightened, the lock is
        not regenerated, and the build installs a version the project says it
        does not support — with hash checking on, so it looks rigorous."""
        from packaging.requirements import Requirement
        from packaging.version import Version

        requirement = Requirement(entry)
        name = requirement.name.lower().replace("_", "-")
        version = self.pinned().get(name)
        if version is None:
            pytest.skip(f"{name} is not in the lock; that is the test above")
        assert requirement.specifier.contains(Version(version)), (
            f"the lock pins {name}=={version}, which [{group}] does not allow "
            f"({entry}). Regenerate the lock."
        )

    def test_the_packaging_tool_is_locked_too(self):
        """PyInstaller is installed by the build workflow rather than declared
        as a dependency, so a lock covering everything except the thing that
        does the packaging covers everything except the interesting part."""
        assert "pyinstaller" in self.pinned("pyinstaller.lock")

    def test_the_lock_does_not_carry_a_note_saying_it_cannot_be_installed(self):
        """**Measured on 0.2.22.** `pyinstaller.lock` ended with pip-compile's
        own warning — *"the following packages were not pinned, but pip requires
        them to be pinned"* — followed by `# setuptools`. The tool wrote down,
        in the file, that the file could not be installed with `--require-hashes`,
        and nothing read it. The Windows build then did exactly what the note
        said: pip exited 1, the step went green anyway, and the release was
        packaged by a PyInstaller that was never installed.

        The fix at the source is `--allow-unsafe` in `lock.yml`; this is the
        part that notices if it comes back.
        """
        for name in ("requirements.lock", "pyinstaller.lock"):
            text = self.lock(name).lower()
            assert "were not pinned" not in text, (
                f"{name} contains pip-compile's unpinned-packages warning. That "
                f"file cannot be installed with --require-hashes. Regenerate it "
                f"with --allow-unsafe."
            )

    def test_everything_a_locked_package_needs_is_locked_beside_it(self):
        """The general form of the same defect, and the one that does not
        depend on pip-compile phrasing its warning the same way next year: a
        lock is a closure. If `A` is in the file and needs `B`, `B` is in the
        file — otherwise pip resolves `B` fresh, has no hash for it, and refuses
        the whole install."""
        import importlib.metadata

        from packaging.requirements import Requirement

        for name in ("requirements.lock", "pyinstaller.lock"):
            pinned = self.pinned(name)
            if name == "pyinstaller.lock":
                pinned = {**self.pinned(), **pinned}
            for package in list(pinned):
                try:
                    metadata = importlib.metadata.metadata(package)
                except importlib.metadata.PackageNotFoundError:
                    continue  # not installed here; the lock is still checked above
                for raw in metadata.get_all("Requires-Dist") or []:
                    requirement = Requirement(raw)
                    if requirement.marker and not requirement.marker.evaluate():
                        continue
                    if requirement.extras:
                        continue
                    needed = requirement.name.lower().replace("_", "-")
                    assert needed in pinned, (
                        f"{name} pins {package}, which needs {needed}, and "
                        f"{needed} is pinned nowhere. --require-hashes will "
                        f"refuse the install."
                    )

    def test_the_two_locks_do_not_contradict_each_other(self):
        """They are resolved separately and installed one after the other, so a
        package appearing in both at different versions means the second install
        silently downgrades the first — or fails, with hash checking on."""
        first, second = self.pinned(), self.pinned("pyinstaller.lock")
        for package in set(first) & set(second):
            assert first[package] == second[package], (
                f"{package} is {first[package]} in requirements.lock and "
                f"{second[package]} in pyinstaller.lock"
            )

    def test_the_build_installs_from_it_strictly(self):
        """A lock nothing installs from is a text file."""
        workflow = (ROOT / ".github" / "workflows" / "build-windows.yml").read_text(encoding="utf-8")
        assert "--require-hashes -r requirements.lock" in workflow
        assert "--require-hashes -r pyinstaller.lock" in workflow
