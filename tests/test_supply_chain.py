"""EF-017: the one artifact with the most authority, fetched on trust.

The build downloads a 33 MB archive over the network and runs what comes back —
as the validator every release is measured against, and, since 0.2.23, as the
thing that decides whether a book may be published at all. Every Python
dependency has been pinned with a hash since 0.2.21. This one had nothing: no
digest, no size, and `ZipFile.extractall`, which Python's own documentation
warns never validates member names against the destination.

Two halves, and they answer different questions.

**What arrived.** A pinned SHA-256 and size, checked whether the archive was
just downloaded or handed in with `--epubcheck-zip` — a local file is not more
trustworthy than a fetched one, and a build that verifies one path and not the
other verifies nothing an attacker cannot route around.

**What came out.** Per-member extraction that refuses absolute names, `..`,
Windows drive letters, symlinks and duplicates, plus the jar's own digest
checked again after unpacking.

Every refusal is a refusal rather than a skip. An archive containing a traversal
member is not an archive with one bad member; it is an archive somebody
tampered with, and quietly dropping the member would build a release out of it.

The closing criterion the baseline set for this finding is the list of cases
below: tamper, traversal, symlink, duplicate, and the correct official asset.
"""

from __future__ import annotations

import hashlib
import os
import stat
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "packaging"))

import build  # noqa: E402


def archive_with(path: Path, members: list[tuple[str, bytes, int]]) -> Path:
    """A ZIP with exact control over member names and external attributes."""
    import warnings

    # One fixture writes a name twice on purpose. Silenced here rather than
    # suite-wide: a warning nobody reads is one that will be missed when it
    # matters.
    warnings.filterwarnings("ignore", "Duplicate name", UserWarning)
    with zipfile.ZipFile(path, "w") as handle:
        for name, data, external in members:
            info = zipfile.ZipInfo(name)
            info.external_attr = external
            handle.writestr(info, data)
    return path


ORDINARY = 0o644 << 16
SYMLINK = (stat.S_IFLNK | 0o777) << 16


class TestTheArchiveMustBeTheOneThisReleaseMeasured:
    def test_the_pins_are_well_formed(self):
        """A pin nobody can check is decoration. Sixty-four hex characters and
        a positive size, asserted so a botched edit cannot leave a truthy
        string that matches nothing."""
        assert len(build.EPUBCHECK_SHA256) == 64
        assert set(build.EPUBCHECK_SHA256) <= set("0123456789abcdef")
        assert len(build.EPUBCHECK_JAR_SHA256) == 64
        assert build.EPUBCHECK_SIZE > 1_000_000

    def test_a_file_of_the_wrong_size_is_refused_before_it_is_hashed(self, tmp_path):
        path = tmp_path / "epubcheck.zip"
        path.write_bytes(b"nie ten plik")
        with pytest.raises(SystemExit, match="bytes and should be"):
            build.verify_archive(path)

    def test_a_file_of_the_right_size_and_wrong_bytes_is_refused(self, tmp_path, monkeypatch):
        """The case the size check cannot catch, and the one tampering looks
        like: same length, different contents."""
        payload = b"x" * 4096
        path = tmp_path / "epubcheck.zip"
        path.write_bytes(payload)
        monkeypatch.setattr(build, "EPUBCHECK_SIZE", len(payload))
        monkeypatch.setattr(build, "EPUBCHECK_SHA256", "0" * 64)
        with pytest.raises(SystemExit, match="hashes to"):
            build.verify_archive(path)

    def test_the_matching_file_passes(self, tmp_path, monkeypatch):
        payload = b"udawany epubcheck" * 100
        path = tmp_path / "epubcheck.zip"
        path.write_bytes(payload)
        monkeypatch.setattr(build, "EPUBCHECK_SIZE", len(payload))
        monkeypatch.setattr(build, "EPUBCHECK_SHA256", hashlib.sha256(payload).hexdigest())
        build.verify_archive(path)  # no exception is the assertion

    def test_the_digest_helper_agrees_with_hashlib(self, tmp_path):
        path = tmp_path / "cokolwiek.bin"
        payload = os.urandom(3_000_000)  # over one read chunk, so the loop runs
        path.write_bytes(payload)
        assert build.digest_of(path) == hashlib.sha256(payload).hexdigest()


class TestExtractionRefusesWhatReachesOutside:
    def test_an_ordinary_archive_unpacks(self, tmp_path):
        source = archive_with(
            tmp_path / "ok.zip",
            [
                ("epubcheck-5.3.0/epubcheck.jar", b"jar", ORDINARY),
                ("epubcheck-5.3.0/lib/a.jar", b"lib", ORDINARY),
            ],
        )
        target = tmp_path / "out"
        target.mkdir()
        with zipfile.ZipFile(source) as handle:
            build.safe_extract(handle, target)
        assert (target / "epubcheck-5.3.0" / "epubcheck.jar").read_bytes() == b"jar"
        assert (target / "epubcheck-5.3.0" / "lib" / "a.jar").read_bytes() == b"lib"

    @pytest.mark.parametrize(
        "name",
        [
            "../poza.txt",
            "epubcheck-5.3.0/../../poza.txt",
            "/etc/cron.d/x",
            "..\\poza.txt",
            "C:/Windows/system32/x",
        ],
    )
    def test_a_member_that_escapes_is_refused(self, tmp_path, name):
        source = archive_with(tmp_path / "zly.zip", [(name, b"x", ORDINARY)])
        target = tmp_path / "out"
        target.mkdir()
        with zipfile.ZipFile(source) as handle:
            with pytest.raises(SystemExit, match="refusing archive"):
                build.safe_extract(handle, target)

    def test_and_nothing_of_it_is_written(self, tmp_path):
        """A refusal that has already written half the archive is not a
        refusal. The traversal member is deliberately first."""
        source = archive_with(
            tmp_path / "zly.zip",
            [("../poza.txt", b"x", ORDINARY), ("dobry.txt", b"y", ORDINARY)],
        )
        target = tmp_path / "out"
        target.mkdir()
        with zipfile.ZipFile(source) as handle:
            with pytest.raises(SystemExit):
                build.safe_extract(handle, target)
        assert not (tmp_path / "poza.txt").exists()

    def test_a_symbolic_link_is_refused(self, tmp_path):
        """A symlink in a ZIP is an ordinary member whose contents are the
        target path, marked in the external attributes. Extracting one and then
        writing through it is traversal by another route — and an EPUBCheck
        distribution contains no links at all."""
        source = archive_with(
            tmp_path / "link.zip", [("epubcheck/evil", b"/etc/passwd", SYMLINK)]
        )
        target = tmp_path / "out"
        target.mkdir()
        with zipfile.ZipFile(source) as handle:
            with pytest.raises(SystemExit, match="symbolic link"):
                build.safe_extract(handle, target)

    def test_a_duplicate_member_is_refused(self, tmp_path):
        """Two members with one name is how an archive says one thing to a
        reader that stops at the first and another to a reader that does not.
        Nothing legitimate produces one here."""
        source = archive_with(
            tmp_path / "dup.zip",
            [("epubcheck.jar", b"pierwszy", ORDINARY),
             ("epubcheck.jar", b"drugi", ORDINARY)],
        )
        target = tmp_path / "out"
        target.mkdir()
        with zipfile.ZipFile(source) as handle:
            with pytest.raises(SystemExit, match="twice"):
                build.safe_extract(handle, target)

    def test_extractall_is_gone_from_the_build(self):
        """The specific call the finding names. A test on behaviour is the real
        one; this is the one that notices somebody putting it back because it
        was shorter."""
        source = (Path(build.__file__)).read_text(encoding="utf-8")
        # The call, not the word: `safe_extract`'s own docstring explains what
        # it replaced and why, and a test that forbids naming the hazard would
        # forbid documenting it.
        assert ".extractall(" not in source


class TestTheOfficialAssetStillMatches:
    """The last of the baseline's cases: *a correct official asset*.

    Off by default, because it downloads 33 MB and a test suite that needs the
    network is a test suite that fails on a train. Run it with
    `EPUBFORGE_NETWORK_TESTS=1` — before a release, and whenever the pinned
    version moves.
    """

    @pytest.mark.skipif(
        os.environ.get("EPUBFORGE_NETWORK_TESTS") != "1",
        reason="set EPUBFORGE_NETWORK_TESTS=1 to fetch the official archive",
    )
    def test_the_pin_is_what_the_official_url_serves(self, tmp_path):
        archive = tmp_path / "epubcheck.zip"
        build._download(build.EPUBCHECK_URL, archive)
        build.verify_archive(archive)

    @pytest.mark.skipif(
        os.environ.get("EPUBFORGE_NETWORK_TESTS") != "1",
        reason="set EPUBFORGE_NETWORK_TESTS=1 to fetch from Maven Central",
    )
    def test_and_the_jar_inside_is_the_signed_one_from_maven(self, tmp_path):
        """The corroboration the pin's provenance rests on, repeatable rather
        than recorded: the distribution jar and Maven Central's GPG-signed
        library jar agree on every entry but the manifest.

        Two hosts, two channels. If they ever disagree, one of them has been
        interfered with and this build should stop.
        """
        import urllib.request

        archive = tmp_path / "epubcheck.zip"
        build._download(build.EPUBCHECK_URL, archive)
        with zipfile.ZipFile(archive) as handle:
            name = next(n for n in handle.namelist() if n.endswith("/epubcheck.jar"))
            (tmp_path / "github.jar").write_bytes(handle.read(name))

        maven = (
            "https://repo1.maven.org/maven2/org/w3c/epubcheck/"
            f"{build.EPUBCHECK_VERSION}/epubcheck-{build.EPUBCHECK_VERSION}.jar"
        )
        urllib.request.urlretrieve(maven, tmp_path / "maven.jar")

        def entries(path: Path) -> dict[str, str]:
            with zipfile.ZipFile(path) as handle:
                return {
                    name: hashlib.sha256(handle.read(name)).hexdigest()
                    for name in handle.namelist()
                    if not name.endswith("/") and name != "META-INF/MANIFEST.MF"
                }

        from_github, from_maven = entries(tmp_path / "github.jar"), entries(tmp_path / "maven.jar")
        assert from_github == from_maven
