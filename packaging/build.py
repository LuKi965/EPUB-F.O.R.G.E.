"""Builds the self-contained EPUB-Forge distribution.

Stages a minimal Java runtime and EPUBCheck into ``packaging/_bundle``, then
runs PyInstaller over ``epubforge.spec``. The result needs no Python, no Java and
no separate EPUBCheck install on the target machine.

    python packaging/build.py                  # full bundle
    python packaging/build.py --skip-java      # smaller, no validation
    python packaging/build.py --epubcheck-zip epubcheck-5.3.0.zip
"""

from __future__ import annotations

import argparse
import hashlib
import http.client
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

PACKAGING_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGING_DIR.parent
BUNDLE_DIR = PACKAGING_DIR / "_bundle"
DIST_DIR = PROJECT_ROOT / "dist"

#: The validator this program ships, pinned rather than "latest".
#:
#: A validator version is part of the product's semantics: the same book gets
#: the same verdict only if the thing giving verdicts is the same. The corpus
#: ledger records `checker` per book for exactly this reason, and a run whose
#: checker changed is not comparable with the one before it.
#:
#: Moved 5.2.1 → 5.3.0 in 0.2.21, on evidence rather than on the release being
#: newer: both versions were run over every book of the public corpus in two
#: modes and agreed on every message — zero errors either side, no code present
#: in one and not the other.
EPUBCHECK_VERSION = "5.3.0"
EPUBCHECK_URL = (
    f"https://github.com/w3c/epubcheck/releases/download/v{EPUBCHECK_VERSION}/"
    f"epubcheck-{EPUBCHECK_VERSION}.zip"
)

#: What the release archive must weigh and hash, or the build stops.
#:
#: **EF-017.** Until this existed the build fetched a 33 MB archive over the
#: network and ran whatever came back — as the validator every release is
#: measured against, and as the thing that decides whether a book is publishable.
#: Every Python dependency has been pinned with a hash since 0.2.21; the one
#: artifact with the most authority over the output had nothing.
#:
#: **Where these numbers come from, since a pin is only worth its provenance.**
#: The archive was downloaded from the URL above on 2026-08-14 and these are its
#: bytes. That much is trust-on-first-use, which detects tampering from now on
#: and cannot detect it from before. So it was corroborated through a second,
#: independent channel: `epubcheck.jar` inside this archive was compared entry
#: by entry with `org.w3c:epubcheck:5.3.0` from Maven Central, which is
#: GPG-signed and served by a different host. **All 746 entries matched byte for
#: byte**, the manifest aside — the distribution jar differs from the library
#: jar only in its `Class-Path`. The code this build ships is therefore the code
#: in the signed artifact, checked rather than assumed.
#:
#: Maven's own digest for that library jar, recorded so the comparison can be
#: repeated: `0e9e8bc2eb47a58c1254016d7f360646bfe04397b137cac2f4e53e361ed1415b`.
EPUBCHECK_SHA256 = "6c07e68584b2e2ce2f89fe06e1246dfead3eb36b46b340e7d93524f29dcff6c5"

#: The renderer, bundled since 0.2.26 because the owner asked the right question.
#:
#: `chrome-headless-shell` rather than Chrome, and the difference is the point:
#: it is the headless-only build, with no browser interface compiled into it, so
#: it **cannot** open a window. He watched 0.2.25 open an Edge window that
#: displayed nothing, which is a fair thing to find suspicious in a program you
#: have trusted with your library, and no flag can promise as much as a binary
#: that has no window code in it.
#:
#: It also settles a defect I hit three times: the appearance check compares two
#: renderings, so run against whatever browser a machine happens to have, it
#: measures the browser. Edge disagreed with Chromium about three of four damage
#: shapes and reported an empty version string. A check whose answer depends on
#: the reader's machine is not a check; a pinned engine is.
#:
#: Licence: BSD-3-Clause, which permits redistribution — he checked that before
#: asking.
#:
#: **Provenance, to the same standard as EPUBCheck above.** Downloaded from the
#: URL below on 2026-08-16; those are its bytes. Corroborated in the one way this
#: host allows without a second channel: Google Cloud Storage publishes its own
#: digest for the object in the `x-goog-hash` header, computed by the storage
#: layer rather than by whoever uploaded it, and the MD5 it declares
#: (`1388c013fbb31c53c42664cb57a160b0`) matches the bytes that arrived. That is
#: weaker than EPUBCheck's entry-by-entry comparison against a GPG-signed jar on
#: a different host, and it is stated as weaker rather than dressed up: Chrome
#: for Testing publishes no signature and no sha256 sidecar.
CHROMIUM_VERSION = "141.0.7390.54"
CHROMIUM_URL = (
    "https://storage.googleapis.com/chrome-for-testing-public/"
    f"{CHROMIUM_VERSION}/win64/chrome-headless-shell-win64.zip"
)
CHROMIUM_SHA256 = "1264ee192ca001359b4527d195d635c4f33312543a90e31359bac38931d34f81"
CHROMIUM_SIZE = 111_772_375

#: And the executable once it is out of the archive, checked again after
#: extraction — the same two questions as EPUBCheck's pair: what arrived over
#: the wire, and what the unpacking produced.
CHROMIUM_EXE_SHA256 = "71e23a5445ccabff5c9b595874e067628bb25d7518c5d12be82dd4c44e733bb1"
EPUBCHECK_SIZE = 33_071_108

#: And the jar once it is out of the archive, checked again after extraction.
#: Two checks rather than one because they answer different questions: the first
#: is about what arrived over the wire, the second about what came out of the
#: unpacking — and the unpacking is the step this finding is also about.
EPUBCHECK_JAR_SHA256 = "f7f96617c929371821609b88c8484d6dc9f24fe916499863c46094c5fb778a65"

#: Derived with `jdeps --print-module-deps` over epubcheck.jar and its lib/, then
#: widened to cover the reflective XML and logging lookups jdeps cannot see, and
#: verified by running EPUBCheck on the resulting runtime.
JRE_MODULES = ",".join(
    [
        "java.base",
        "java.compiler",
        "java.desktop",
        "java.logging",
        "java.management",
        "java.naming",
        "java.prefs",
        "java.scripting",
        "java.security.jgss",
        "java.sql",
        "java.xml",
        "jdk.unsupported",
        "jdk.xml.dom",
    ]
)


def log(message: str) -> None:
    print(f"[build] {message}", flush=True)


def run(command: list[str]) -> None:
    log(" ".join(str(part) for part in command))
    subprocess.run(command, check=True)


def find_tool(name: str) -> str:
    """Locate a JDK tool via JAVA_HOME, falling back to PATH."""
    java_home = os.environ.get("JAVA_HOME")
    if java_home:
        candidate = Path(java_home) / "bin" / (f"{name}.exe" if os.name == "nt" else name)
        if candidate.is_file():
            return str(candidate)
    found = shutil.which(name)
    if found:
        return found
    raise SystemExit(
        f"{name} not found. Install a JDK 17+ and set JAVA_HOME, or pass --skip-java."
    )


def _download(url: str, target: Path, attempts: int = 4) -> None:
    """Fetch *url* to *target*, retrying a connection that simply drops.

    The release build for 0.2.20 died here: `http.client.RemoteDisconnected:
    Remote end closed connection without response`, on the first byte, after the
    whole test suite had passed on the runner. Nothing about the release was
    wrong — a CDN closed a socket, and a release with seven audit findings in it
    sat unbuilt because of it.

    Written to the final name only once the bytes are all here, so a half
    download cannot be mistaken for a cached archive on the next run: the file's
    existence is what tells this function to skip the fetch.
    """
    import time

    staging = target.with_suffix(target.suffix + ".part")
    for attempt in range(1, attempts + 1):
        try:
            log(f"downloading {url}" + (f" (attempt {attempt})" if attempt > 1 else ""))
            urllib.request.urlretrieve(url, staging)
            staging.replace(target)
            return
        except (urllib.error.URLError, OSError, http.client.HTTPException) as exc:
            staging.unlink(missing_ok=True)
            if attempt == attempts:
                raise SystemExit(f"could not download {url}: {exc}") from exc
            pause = 2**attempt
            log(f"  {type(exc).__name__}: {exc} — retrying in {pause}s")
            time.sleep(pause)


def digest_of(path: Path) -> str:
    """SHA-256 of a file, read in pieces so a 33 MB archive costs a buffer."""
    running = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            running.update(chunk)
    return running.hexdigest()


def verify_archive(path: Path) -> None:
    """Refuse an EPUBCheck archive that is not the one this build was measured
    against. Size first, because it is free and it names the likelier accident.
    """
    size = path.stat().st_size
    if size != EPUBCHECK_SIZE:
        raise SystemExit(
            f"{path.name} is {size} bytes and should be {EPUBCHECK_SIZE}. "
            f"Refusing to build against an EPUBCheck this release has not measured."
        )
    found = digest_of(path)
    if found != EPUBCHECK_SHA256:
        raise SystemExit(
            f"{path.name} hashes to {found} and should hash to {EPUBCHECK_SHA256}. "
            f"Refusing to build against an EPUBCheck this release has not measured."
        )
    log(f"{path.name} verified against the pinned digest")


def safe_extract(archive: zipfile.ZipFile, target: Path) -> None:
    """Unpack member by member, refusing anything that reaches outside *target*.

    `extractall` was here, and `extractall` is the documented hazard: Python's
    own manual warns that it never validates member names against the
    destination. A member called `../../../../etc/cron.d/x` writes there. This
    is a build step that runs on a release machine and unpacks bytes fetched
    over a network, which is the exact shape the warning is about.

    Refused rather than skipped, and that is the choice worth stating: an
    archive containing a traversal is not an archive with one bad member, it is
    an archive somebody tampered with. Quietly dropping the member and carrying
    on would build a release out of it.
    """
    seen: set[str] = set()
    root = target.resolve()
    for info in archive.infolist():
        name = info.filename
        if name.endswith("/"):
            continue

        # `\\` because a ZIP written on Windows can carry them and `PurePosixPath`
        # would read the whole thing as one long file name.
        if "\\" in name or name.startswith("/") or (len(name) > 1 and name[1] == ":"):
            raise SystemExit(f"refusing archive: member name is not relative: {name!r}")
        if ".." in PurePosixPath(name).parts:
            raise SystemExit(f"refusing archive: member escapes the directory: {name!r}")

        # A symlink in a ZIP is a regular member whose contents are the target
        # path, marked in the high bits of the external attributes. Following
        # one on extraction writes wherever it points, which is traversal by
        # another route — and nothing in an EPUBCheck distribution is a link.
        if stat.S_ISLNK(info.external_attr >> 16):
            raise SystemExit(f"refusing archive: member is a symbolic link: {name!r}")

        if name in seen:
            raise SystemExit(f"refusing archive: member appears twice: {name!r}")
        seen.add(name)

        destination = (target / name).resolve()
        # The belt to the braces above: whatever the name looked like, the path
        # it resolves to has to be inside the directory being written.
        if not destination.is_relative_to(root):
            raise SystemExit(f"refusing archive: member escapes the directory: {name!r}")

        destination.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(info) as source, open(destination, "wb") as handle:
            shutil.copyfileobj(source, handle)


def stage_epubcheck(archive: Path | None) -> None:
    target = BUNDLE_DIR / "epubcheck"
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)

    if archive is None:
        archive = BUNDLE_DIR / f"epubcheck-{EPUBCHECK_VERSION}.zip"
        if not archive.is_file():
            _download(EPUBCHECK_URL, archive)
    # Checked whether it was just downloaded or handed in with --epubcheck-zip.
    # A local file is not more trustworthy than a fetched one; it is only more
    # convenient, and a build that verifies one path and not the other verifies
    # nothing an attacker cannot route around.
    verify_archive(archive)
    log(f"extracting {archive.name}")

    # A fresh directory per run, so a member left behind by an earlier build
    # cannot be picked up by this one.
    raw = Path(tempfile.mkdtemp(prefix="epubcheck-", dir=BUNDLE_DIR))
    with zipfile.ZipFile(archive) as handle:
        safe_extract(handle, raw)

    # The release zip nests everything under epubcheck-<version>/.
    roots = [p for p in raw.iterdir() if p.is_dir()] or [raw]
    source = next((p for p in roots if (p / "epubcheck.jar").is_file()), None)
    if source is None:
        raise SystemExit("epubcheck.jar not found inside the archive")
    for item in source.iterdir():
        destination = target / item.name
        if item.is_dir():
            shutil.copytree(item, destination)
        else:
            shutil.copy2(item, destination)
    shutil.rmtree(raw)

    # And once more on what actually came out. The archive's digest says the
    # bytes were right; this says the unpacking produced the jar those bytes
    # describe, which is the half of the finding that is about extraction.
    staged_jar = target / "epubcheck.jar"
    found = digest_of(staged_jar)
    if found != EPUBCHECK_JAR_SHA256:
        raise SystemExit(
            f"epubcheck.jar hashes to {found} and should hash to "
            f"{EPUBCHECK_JAR_SHA256} — the archive verified and the extraction "
            f"did not produce the expected jar."
        )
    log(f"epubcheck staged ({sum(f.stat().st_size for f in target.rglob('*') if f.is_file()) >> 20} MiB)")
    stage_validator_driver(target)


def stage_chromium(archive: Path | None = None) -> None:
    """Put the headless renderer beside the program, pinned and checked twice.

    The same shape as `stage_epubcheck`, deliberately: verify the archive
    whether it was fetched or handed in, unpack it one entry at a time through
    `safe_extract`, then check the executable that came out. Two digests because
    they answer two questions — what arrived over the wire, and what the
    unpacking produced — and EF-017 is about the second one as much as the first.
    """
    target = BUNDLE_DIR / "chromium"
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)

    if archive is None:
        archive = BUNDLE_DIR / f"chrome-headless-shell-{CHROMIUM_VERSION}.zip"
        if not archive.is_file():
            _download(CHROMIUM_URL, archive)
    verify_chromium_archive(archive)
    log(f"extracting {archive.name}")

    raw = Path(tempfile.mkdtemp(prefix="chromium-", dir=BUNDLE_DIR))
    with zipfile.ZipFile(archive) as handle:
        safe_extract(handle, raw)

    roots = [p for p in raw.iterdir() if p.is_dir()] or [raw]
    source = next(
        (p for p in roots if (p / "chrome-headless-shell.exe").is_file()), None
    )
    if source is None:
        raise SystemExit("chrome-headless-shell.exe not found inside the archive")
    for item in source.iterdir():
        destination = target / item.name
        if item.is_dir():
            shutil.copytree(item, destination)
        else:
            shutil.copy2(item, destination)
    shutil.rmtree(raw)

    staged = target / "chrome-headless-shell.exe"
    found = digest_of(staged)
    if found != CHROMIUM_EXE_SHA256:
        raise SystemExit(
            f"chrome-headless-shell.exe hashes to {found} and should hash to "
            f"{CHROMIUM_EXE_SHA256} — the archive verified and the extraction "
            f"did not produce the expected binary."
        )
    size = sum(f.stat().st_size for f in target.rglob("*") if f.is_file()) >> 20
    log(f"chromium staged ({size} MiB)")


def verify_chromium_archive(path: Path) -> None:
    """Refuse a renderer this release has not measured. Size first: free, and it
    names the likelier accident."""
    size = path.stat().st_size
    if size != CHROMIUM_SIZE:
        raise SystemExit(
            f"{path.name} is {size} bytes and should be {CHROMIUM_SIZE}. "
            f"Refusing to build against a renderer this release has not measured."
        )
    found = digest_of(path)
    if found != CHROMIUM_SHA256:
        raise SystemExit(
            f"{path.name} hashes to {found} and should hash to {CHROMIUM_SHA256}. "
            f"Refusing to build against a renderer this release has not measured."
        )
    log(f"{path.name} verified against the pinned digest")


def stage_validator_driver(target: Path) -> None:
    """Compile the one class that lets a JVM validate more than one book.

    Here rather than at runtime, because the bundled runtime is a jlink image
    and a jlink image has no compiler. Measured on eight real books: 35.3 s
    with a JVM per book, 8.4 s through one held open. Without this class the
    packaged build still validates — it just pays the JVM every time, which is
    the behaviour it had before and not a broken build.
    """
    source = PROJECT_ROOT / "epubforge" / "java" / "ForgeValidator.java"
    if not source.is_file():
        log("no validator driver source; the build will start a JVM per book")
        return
    try:
        javac = find_tool("javac")
    except SystemExit:
        log("no javac; the build will start a JVM per book")
        return
    run([javac, "-cp", str(target / "epubcheck.jar"), "-d", str(target), str(source)])
    if not (target / "ForgeValidator.class").is_file():
        raise SystemExit("javac reported success and produced no class")
    log("validator driver compiled")


def jlink_compression(jlink: str) -> str:
    """`--compress=zip-N` only exists from JDK 21; older releases take a digit."""
    try:
        output = subprocess.run(
            [jlink, "--version"], capture_output=True, text=True, timeout=60, check=False
        )
        major = int((output.stdout or output.stderr).strip().split(".")[0])
    except (OSError, ValueError, subprocess.SubprocessError):
        major = 0
    return "--compress=zip-6" if major >= 21 else "--compress=2"


def stage_jre() -> None:
    target = BUNDLE_DIR / "jre"
    if target.exists():
        shutil.rmtree(target)

    jlink = find_tool("jlink")
    run(
        [
            jlink,
            "--add-modules", JRE_MODULES,
            "--strip-debug",
            "--no-header-files",
            "--no-man-pages",
            jlink_compression(jlink),
            "--output", str(target),
        ]
    )
    if os.name != "nt":
        # PyInstaller copies data files without the executable bit.
        for binary in (target / "bin").iterdir():
            binary.chmod(binary.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    log(f"jre staged ({sum(f.stat().st_size for f in target.rglob('*') if f.is_file()) >> 20} MiB)")


def restore_executable_bits() -> None:
    """PyInstaller strips +x from staged data files; the JRE needs it back."""
    if os.name == "nt":
        return
    bin_dir = DIST_DIR / "EPUB-Forge" / "_internal" / "jre" / "bin"
    if not bin_dir.is_dir():
        return
    for binary in bin_dir.iterdir():
        binary.chmod(binary.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    log("restored executable bits on the bundled JRE")


def directory_size(path: Path) -> int:
    """Bytes on disk, not counting symlinks twice — Qt ships chains of them."""
    return sum(
        f.stat().st_size
        for f in path.rglob("*")
        if f.is_file() and not f.is_symlink()
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-java", action="store_true", help="build without the JRE and EPUBCheck")
    parser.add_argument("--epubcheck-zip", type=Path, help="use a local EPUBCheck release archive")
    parser.add_argument(
        "--chromium-zip", type=Path,
        help="use a local chrome-headless-shell archive instead of fetching it",
    )
    parser.add_argument("--clean", action="store_true", help="discard staged bundles and build cache first")
    args = parser.parse_args()

    if args.clean:
        for path in (BUNDLE_DIR, DIST_DIR, PROJECT_ROOT / "build"):
            if path.exists():
                shutil.rmtree(path)
        log("cleaned")

    BUNDLE_DIR.mkdir(parents=True, exist_ok=True)

    if args.skip_java:
        for name in ("jre", "epubcheck"):
            stale = BUNDLE_DIR / name
            if stale.exists():
                shutil.rmtree(stale)
        log("skipping Java bundle; the build will have no EPUBCheck")
    else:
        stage_epubcheck(args.epubcheck_zip)
        stage_chromium(args.chromium_zip)
        stage_jre()

    icon = PACKAGING_DIR / "epubforge.ico"
    if not icon.is_file():
        run([sys.executable, str(PACKAGING_DIR / "make_icon.py")])

    run(
        [
            sys.executable, "-m", "PyInstaller",
            "--noconfirm",
            "--distpath", str(DIST_DIR),
            "--workpath", str(PROJECT_ROOT / "build"),
            str(PACKAGING_DIR / "epubforge.spec"),
        ]
    )
    restore_executable_bits()

    result = DIST_DIR / "EPUB-Forge"
    if not result.is_dir():
        raise SystemExit("PyInstaller did not produce dist/EPUB-Forge")
    log(f"done: {result} ({directory_size(result) >> 20} MiB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
