"""Verifies a frozen build the way a user would exercise it.

Runs the packaged executables against a deliberately broken book with every
environment hint cleared, so a pass proves the bundled Java runtime and
EPUBCheck are what did the work — not something installed on the build machine.

    python packaging/smoke_test.py [dist/EPUB-Forge]
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tests.factory import ENCRYPTION_XML, fake_ttf, make_legacy_epub  # noqa: E402

from epubforge.reader import IDPF_OBFUSCATION  # noqa: E402
from epubforge.stages.fonts import IDPF_PREFIX_LENGTH, deobfuscate, idpf_key  # noqa: E402

IDENTIFIER = "urn:uuid:8f2c1b44-9c1e-4f0a-9c2b-3f6b1a7d5e21"


def executable(dist_dir: Path, name: str) -> Path:
    candidate = dist_dir / (f"{name}.exe" if os.name == "nt" else name)
    if not candidate.is_file():
        raise SystemExit(f"missing executable: {candidate}")
    return candidate


def clean_environment() -> dict[str, str]:
    """Strip anything that could let a system Java or EPUBCheck answer instead."""
    env = dict(os.environ)
    for key in ("EPUBCHECK_JAR", "JAVA_HOME", "JAVA_TOOL_OPTIONS", "CLASSPATH"):
        env.pop(key, None)
    separator = ";" if os.name == "nt" else ":"
    keep = [] if os.name != "nt" else [
        part for part in env.get("PATH", "").split(separator)
        if "windows" in part.lower() or "system32" in part.lower()
    ]
    env["PATH"] = separator.join(keep)
    return env


def run(command: list[str], env: dict[str, str]) -> subprocess.CompletedProcess:
    print(f"$ {' '.join(command)}", flush=True)
    result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=600)
    print(result.stdout)
    if result.stderr.strip():
        print(result.stderr, file=sys.stderr)
    return result


def main() -> int:
    dist_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else PROJECT_ROOT / "dist" / "EPUB-Forge"
    dist_dir = dist_dir.resolve()
    cli = executable(dist_dir, "epubforge")
    executable(dist_dir, "EPUB-Forge")  # presence check only; it is windowed

    env = clean_environment()

    with tempfile.TemporaryDirectory() as workspace:
        work = Path(workspace)
        source = work / "broken.epub"
        obfuscated = deobfuscate(fake_ttf(), idpf_key(IDENTIFIER), IDPF_PREFIX_LENGTH)
        make_legacy_epub(
            str(source),
            font=obfuscated,
            encryption=ENCRYPTION_XML.format(algorithm=IDPF_OBFUSCATION),
        )

        output = work / "rebuilt.epub"
        # `--accept-unverified-render` because the bundle deliberately does not
        # ship a browser and this runner has none: the appearance check cannot
        # run, and since 0.2.24 "cannot run" means "do not write" unless somebody
        # says otherwise. Here that somebody is this script, saying it on purpose
        # — which is the whole point of the switch existing.
        #
        # This is what the check is *for*, and it caught something real on the
        # way in. A first attempt without the flag failed, and the reason was not
        # the flag: `find_renderer` searched `PATH` alone, and nothing a Windows
        # machine installs is on `PATH`. So the released program refused every
        # command-line rebuild on the only platform it ships for. (That fix
        # briefly made Edge reachable; from 0.2.27 it is not searched for at all,
        # because measured against the same damage it answers differently from
        # Chromium and reports no version. The bundle is the answer, not Edge.)
        # No `--accept-unverified-render` any more, and that is the point of
        # this release: the bundle carries its own headless renderer, so the
        # appearance check *runs*. If it does not, this build has 112 MB of
        # Chromium in it that nothing can reach, and the right time to discover
        # that is here rather than on somebody's machine.
        build = run(
            [str(cli), "build", str(source), "-o", str(output), "--strict"], env
        )
        if build.returncode != 0 or not output.is_file():
            raise SystemExit(
                "frozen build did not produce an output file:\n" + build.stdout[-2000:]
            )

        check = run([str(cli), "check", str(output)], env)
        if check.returncode == 3:
            raise SystemExit(
                "the frozen build could not find EPUBCheck — the JRE or jar was not bundled"
            )
        if check.returncode != 0 or "valid" not in check.stdout:
            raise SystemExit("the rebuilt book did not validate")

        # Said out loud rather than inferred from the exit code: the check
        # reports what it did, and "did not run" is a distinct sentence from
        # "ran and found nothing".
        if "render.cannot-run" in build.stdout:
            raise SystemExit(
                "the bundled renderer was not found by the frozen build:\n"
                + build.stdout[-2000:]
            )

    print(
        "smoke test passed: rebuild, EPUBCheck and the renderer all ran from the bundle"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
