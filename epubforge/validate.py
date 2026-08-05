"""Optional EPUBCheck integration — the authoritative conformance verdict.

EPUBCheck is a Java tool and cannot be vendored, so it is looked up rather than
required. Absence downgrades to a warning: the rebuild is still useful without
it, just unverified.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field

from . import resources
from .report import Level, Report

ENV_JAR = "EPUBCHECK_JAR"
SEARCH_PATHS = (
    os.path.expanduser("~/.cache/epubforge/epubcheck/epubcheck.jar"),
    "/usr/share/java/epubcheck.jar",
    "/opt/epubcheck/epubcheck.jar",
)


@dataclass
class ValidationResult:
    available: bool
    fatal: int = 0
    errors: int = 0
    warnings: int = 0
    messages: list[str] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return self.available and self.fatal == 0 and self.errors == 0


def find_epubcheck() -> list[str] | None:
    """Return the command prefix that runs EPUBCheck, or ``None``.

    An explicit ``EPUBCHECK_JAR`` wins so a user can point a packaged build at a
    newer release; otherwise a bundled copy is preferred over anything installed
    system-wide, because it is the version this build was tested against.
    """
    jar = os.environ.get(ENV_JAR)
    if jar and os.path.isfile(jar):
        return _java_command(jar)

    bundled = resources.bundled_epubcheck_command()
    if bundled:
        return bundled

    executable = shutil.which("epubcheck")
    if executable:
        return [executable]
    for candidate in SEARCH_PATHS:
        if os.path.isfile(candidate):
            return _java_command(candidate)
    return None


def _java_command(jar: str) -> list[str] | None:
    """Run *jar* on the bundled JRE if there is one, else on the system's."""
    java = resources.java_executable()
    if java is not None:
        return [str(java), "-jar", jar]
    if shutil.which("java") is None:
        return None
    return ["java", "-jar", jar]


def _no_console() -> dict:
    """Keep Windows from opening a console window for the validator.

    A GUI process on Windows has no console, so starting one is starting a
    new window: a black rectangle appears, sits there for as long as the JVM
    runs, and disappears. It does nothing, explains nothing, and the progress
    it looks like it should be showing is in the application window already.

    `CREATE_NO_WINDOW` is the documented way to say no. It exists only on
    Windows, hence the guard; everywhere else this returns nothing and the call
    is unchanged.
    """
    if os.name != "nt":
        return {}
    options: dict = {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)}
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = subprocess.SW_HIDE
    options["startupinfo"] = startupinfo
    return options


def validate(epub_path: str, report: Report | None = None) -> ValidationResult:
    command = find_epubcheck()
    if command is None:
        if report:
            report.add(
                "epubcheck",
                Level.WARN,
                "EPUBCheck was not found; the output has not been independently verified", rule="epubcheck.unavailable",
                detail=f"Install it and set {ENV_JAR}, or put epubcheck on PATH.",
            )
        return ValidationResult(available=False)

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as handle:
        json_path = handle.name
    try:
        subprocess.run(
            command + [epub_path, "--json", json_path, "--quiet"],
            capture_output=True,
            timeout=300,
            check=False,
            **_no_console(),
        )
        with open(json_path, encoding="utf-8") as handle:
            payload = json.load(handle)
    except (subprocess.TimeoutExpired, OSError, json.JSONDecodeError) as exc:
        if report:
            report.add("epubcheck", Level.WARN, f"EPUBCheck could not be run: {type(exc).__name__}", rule="epubcheck.failed")
        return ValidationResult(available=False)
    finally:
        try:
            os.unlink(json_path)
        except OSError:
            pass

    result = ValidationResult(available=True)
    for message in payload.get("messages", []):
        severity = (message.get("severity") or "").upper()
        text = message.get("message", "").strip()
        locations = message.get("locations") or []
        where = locations[0].get("path", "") if locations else ""
        line = f"{severity}: {text}" + (f" ({where})" if where else "")
        if severity == "FATAL":
            result.fatal += 1
        elif severity == "ERROR":
            result.errors += 1
        elif severity == "WARNING":
            result.warnings += 1
        else:
            continue
        result.messages.append(line)

    if report:
        if result.clean:
            report.add(
                "epubcheck",
                Level.INFO,
                f"EPUBCheck passed with 0 errors and {result.warnings} warning(s)", rule="epubcheck.clean",
            )
        else:
            report.add(
                "epubcheck",
                Level.ERROR,
                f"EPUBCheck reported {result.fatal} fatal and {result.errors} error(s)", rule="epubcheck.reported",
                detail="; ".join(result.messages[:10]),
            )
    return result
