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
import http.client
import os
import shutil
import stat
import subprocess
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

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


def stage_epubcheck(archive: Path | None) -> None:
    target = BUNDLE_DIR / "epubcheck"
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)

    if archive is None:
        archive = BUNDLE_DIR / f"epubcheck-{EPUBCHECK_VERSION}.zip"
        if not archive.is_file():
            _download(EPUBCHECK_URL, archive)
    log(f"extracting {archive.name}")

    with zipfile.ZipFile(archive) as handle:
        handle.extractall(BUNDLE_DIR / "_epubcheck_raw")

    # The release zip nests everything under epubcheck-<version>/.
    raw = BUNDLE_DIR / "_epubcheck_raw"
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
    log(f"epubcheck staged ({sum(f.stat().st_size for f in target.rglob('*') if f.is_file()) >> 20} MiB)")


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
