"""Optional EPUBCheck integration — the authoritative conformance verdict.

EPUBCheck is a Java tool and cannot be vendored, so it is looked up rather than
required. Absence downgrades to a warning: the rebuild is still useful without
it, just unverified.
"""

from __future__ import annotations

import json
import functools
import os
import shutil
import subprocess
import tempfile
from collections import Counter
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
    #: Which EPUBCheck rules the errors were, counted: ``{"RSC-005": 2}``.
    #:
    #: EPUBCheck gives every message an identifier from a fixed vocabulary —
    #: `OPF-014`, `RSC-005`, `HTM-004` — and the identifier is the only part of
    #: a message that is neither the book's text nor a path inside it. That is
    #: what makes it recordable: a corpus signature may say *what broke* without
    #: saying anything about whose book broke it.
    #:
    #: Written because a run reported "14 errors introduced across 13 books" and
    #: there was nothing further to ask. Every one of those books is on somebody
    #: else's disk; without the identifiers the next step is to request the
    #: books, which the corpus exists so as never to have to do.
    codes: "dict[str, int]" = field(default_factory=dict)

    @property
    def clean(self) -> bool:
        return self.available and self.fatal == 0 and self.errors == 0


#: What a JVM assumes when nobody tells it otherwise: that it owns the machine.
#: It sizes its garbage collector and its compiler threads from the core count,
#: which is right for a server running for a week and wrong for a process that
#: validates one book and exits.
#:
#: Measured, on one book, four validations at a time:
#:
#: ===========================  ======
#: nothing                       17.4s
#: TieredStopAtLevel=1            7.7s
#: ActiveProcessorCount=1        12.8s
#: UseSerialGC                   16.0s
#: all three                      7.0s
#: ===========================  ======
#:
#: `TieredStopAtLevel=1` is the large one and it helps a single validation too:
#: EPUBCheck runs for a few seconds, and the optimising compiler never earns
#: back what it costs to run. The other two stop eight concurrent JVMs from
#: each starting a garbage collector sized for every core on the machine —
#: which on an eight-core desktop is over a hundred threads fighting for eight.
#:
#: `-Xmx512m` was measured too and made no difference at all, so it is not here:
#: a heap cap that buys nothing can still make a large book fail to validate,
#: and a false error is worse than a slow answer.
TUNING = (
    "-XX:TieredStopAtLevel=1",
    "-XX:ActiveProcessorCount=1",
    "-XX:+UseSerialGC",
)


@functools.lru_cache(maxsize=8)
def accepted_tuning(java: str) -> tuple[str, ...]:
    """The options above, if this JVM takes them, or nothing at all.

    HotSpot *fails to start* on an `-XX:` option it does not recognise, so a
    flag that is wrong for somebody's Java would not make validation slower, it
    would make it impossible. Other runtimes exist — OpenJ9 is the common one —
    and a user may point `EPUBCHECK_JAR` at whatever java is on their path.

    Asked once per interpreter, and answered by the only authority there is:
    starting that java with those options and seeing whether it comes up.
    """
    try:
        probe = subprocess.run(
            [java, *TUNING, "-version"], capture_output=True, timeout=60, **_no_console()
        )
    except (OSError, subprocess.SubprocessError):
        return ()
    return TUNING if probe.returncode == 0 else ()


def _tuned(command: list[str] | None) -> list[str] | None:
    """Insert the options into a `java -jar …` invocation, and nothing else."""
    if command and len(command) >= 3 and command[1] == "-jar":
        return [command[0], *accepted_tuning(command[0]), *command[1:]]
    return command


def find_epubcheck() -> list[str] | None:
    """Return the command prefix that runs EPUBCheck, or ``None``.

    An explicit ``EPUBCHECK_JAR`` wins so a user can point a packaged build at a
    newer release; otherwise a bundled copy is preferred over anything installed
    system-wide, because it is the version this build was tested against.
    """
    jar = os.environ.get(ENV_JAR)
    if jar and os.path.isfile(jar):
        return _tuned(_java_command(jar))

    bundled = resources.bundled_epubcheck_command()
    if bundled:
        return _tuned(bundled)

    executable = shutil.which("epubcheck")
    if executable:
        return [executable]
    for candidate in SEARCH_PATHS:
        if os.path.isfile(candidate):
            return _tuned(_java_command(candidate))
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


def _detail(result: "ValidationResult", content_untouched: bool) -> str:
    """What EPUBCheck said, and — where it matters — whose fault it is."""
    said = "; ".join(result.messages[:10])
    if not content_untouched:
        return said
    return (
        f"{said} — this rebuild left every content document byte for byte as it "
        "was, so an error inside one of them was already in the source. The full "
        "rebuild corrects them; this mode is not allowed to."
    )


def validate(
    epub_path: str,
    report: Report | None = None,
    *,
    content_untouched: bool = False,
) -> ValidationResult:
    """Run EPUBCheck over *epub_path* and record what it said.

    *content_untouched* says the rebuild left the content documents byte for
    byte as they were — the container-only mode. It changes nothing about the
    check and everything about how to read the result: an error inside a
    document is then the source's error, carried through because that mode
    promised not to touch it. Without saying so, the report shows an error the
    reader will assume this program introduced.
    """
    command = find_epubcheck()
    if command is None:
        if report:
            report.add(
                "epubcheck",
                Level.WARN,
                "epubcheck.unavailable",
                values={"variable": ENV_JAR},
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
            report.add(
                "epubcheck",
                Level.WARN,
                "epubcheck.failed",
                values={"error": type(exc).__name__},
            )
        return ValidationResult(available=False)
    finally:
        try:
            os.unlink(json_path)
        except OSError:
            pass

    result = ValidationResult(available=True)
    codes: Counter = Counter()
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
        # Warnings are left out on purpose. These are recorded to explain a
        # failure, and a book that validates clean would otherwise carry a list
        # of identifiers nobody is going to read.
        if severity in ("FATAL", "ERROR"):
            identifier = (message.get("ID") or message.get("id") or "").strip()
            if identifier:
                codes[identifier] += 1
    result.codes = dict(sorted(codes.items()))

    if report:
        if result.clean:
            report.add(
                "epubcheck",
                Level.INFO,
                "epubcheck.clean",
                values={"warnings": result.warnings},
            )
        else:
            report.add(
                "epubcheck",
                Level.ERROR,
                "epubcheck.reported",
                values={"fatal": result.fatal, "errors": result.errors},
                detail=_detail(result, content_untouched),
            )
    return result
