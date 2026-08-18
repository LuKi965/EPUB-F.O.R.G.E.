"""Optional EPUBCheck integration — the authoritative conformance verdict.

EPUBCheck is a Java tool and cannot be vendored, so it is looked up rather than
required. Absence downgrades to a warning: the rebuild is still useful without
it, just unverified.
"""

from __future__ import annotations

import atexit
import json
import functools
import os
import pathlib
import re
import shutil
import subprocess
import tempfile
import threading
from collections import Counter
from dataclasses import dataclass, field

from . import resources, spawn
from .report import Level, Report

ENV_JAR = "EPUBCHECK_JAR"

#: Set to `0` to make every validation start its own JVM, the way it used to.
#: Kept because "turn the clever thing off" is the first question worth asking
#: about any answer that disagrees with the command line's, and the checkbox in
#: the diagnostics panel writes it.
ENV_SHARED = "EPUBFORGE_SHARED_VALIDATOR"
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
    #: The *shape* of each error message, with anything book-specific masked:
    #: ``{'Error while parsing file: element "X" not allowed here': 3}``.
    #:
    #: The identifiers alone stopped being enough after one run. `RSC-005` is
    #: EPUBCheck's catch-all for "this file does not match the schema", and when
    #: eleven books each gained exactly one of them, the code said only that
    #: something in a document was wrong — not which something. A code that
    #: covers a hundred different defects is a smoke alarm that only says
    #: "building".
    #:
    #: So the sentence is kept too, with every quoted literal that is not a
    #: plain markup name replaced by `…`. Element and attribute names are HTML
    #: vocabulary and say nothing about whose book this is; a value, a path or a
    #: fragment of text might, and goes.
    shapes: "dict[str, int]" = field(default_factory=dict)

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
        probe = spawn.run(
            [java, *TUNING, "-version"], capture_output=True, timeout=60
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


# --------------------------------------------------------------------------
# One JVM instead of one per book
# --------------------------------------------------------------------------
#
# Measured here, eight real books between 0.8 MB and 23 MB, JVM options already
# tuned: **4415 ms per book**, and a 1.8 KB book costs 3602 ms of that. The cost
# is neither the JVM (37 ms to start, 125 ms with EPUBCheck's classes loaded)
# nor the book — it is EPUBCheck compiling its RelaxNG and Schematron schemas,
# about three and a half seconds, paid again by every new process.
#
# Through one JVM held open: 4030 ms for the first book, 200–1700 ms for each
# one after. The same eight books go from 35.3 s to 7.5 s.
#
# One process, one book at a time, on purpose. Four one-shot JVMs in parallel
# came to about 9 s for those eight books, so a single warm JVM already wins
# without spending four cores; several warm JVMs would each pay the warm-up.
#
# The rule this is built to: a speed-up must never become a new way to fail.
# Every path out of here that is not a clean answer returns `None`, and `None`
# means "start a process for this one book" — which is exactly what the program
# did before, still works, and is still what the tests compare against.


def _driver_source() -> pathlib.Path:
    return pathlib.Path(__file__).with_name("java") / "ForgeValidator.java"


def _driver_class() -> pathlib.Path | None:
    """The compiled driver, bundled or built once into the cache.

    A packaged build has no compiler — the bundled runtime is a jlink image —
    so the release compiles this at packaging time and ships the class beside
    `epubcheck.jar`. Running from a source checkout there is usually a JDK
    around, and a one-off `javac` into the cache costs a second, once.
    """
    root = resources.bundle_root()
    if root is not None:
        bundled = root / "epubcheck" / "ForgeValidator.class"
        if bundled.is_file():
            return bundled

    source = _driver_source()
    if not source.is_file():
        return None
    cached = pathlib.Path(
        os.path.expanduser("~/.cache/epubforge/driver")
    ) / "ForgeValidator.class"
    if cached.is_file() and cached.stat().st_mtime >= source.stat().st_mtime:
        return cached

    javac = shutil.which("javac")
    jar = _jar_of(find_epubcheck())
    if javac is None or jar is None:
        return None
    try:
        cached.parent.mkdir(parents=True, exist_ok=True)
        built = spawn.run(
            [javac, "-cp", jar, "-d", str(cached.parent), str(source)],
            capture_output=True,
            timeout=300,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return cached if built.returncode == 0 and cached.is_file() else None


def _jar_of(command: list[str] | None) -> str | None:
    """The jar out of a `java … -jar <jar>` command, if that is what it is."""
    if not command or "-jar" not in command:
        return None
    index = command.index("-jar")
    return command[index + 1] if index + 1 < len(command) else None


class SharedValidator:
    """A JVM kept alive across books, with the old path one failure away.

    Not a pool and not a server: one process, started on the first book that
    needs it, serialised by a lock because it validates one book at a time.
    """

    def __init__(self) -> None:
        self._process: subprocess.Popen | None = None
        #: The command the live process was started with. Checked before every
        #: book, because a process that outlives the answer to "which validator
        #: is this" is a process quietly giving the old jar's verdict: point
        #: `EPUBCHECK_JAR` at a different release and nothing would have
        #: noticed. Found by a test that stubbed the lookup and got a real
        #: EPUBCheck run — the stub was read at start-up and never again.
        self._started_with: list[str] | None = None
        self._lock = threading.Lock()
        #: Why it is not being used, if it is not. Shown in diagnostics rather
        #: than kept to itself — "it is slow again and nobody said why" is the
        #: failure mode of every silent fallback.
        self.reason = ""

    def enabled(self) -> bool:
        return os.environ.get(ENV_SHARED, "1") not in ("0", "no", "false")

    def _command(self) -> list[str] | None:
        command = find_epubcheck()
        jar = _jar_of(command)
        if command is None or jar is None:
            self.reason = "EPUBCheck is not a jar this can drive"
            return None
        driver = _driver_class()
        if driver is None:
            self.reason = "the driver class is not built and no javac was found"
            return None
        separator = ";" if os.name == "nt" else ":"
        java = command[0]
        return [
            java,
            *accepted_tuning(java),
            "-cp",
            f"{jar}{separator}{driver.parent}",
            "ForgeValidator",
        ]

    def _start(self, command: list[str] | None) -> subprocess.Popen | None:
        if command is None:
            return None
        try:
            process = spawn.popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            self.reason = f"{type(exc).__name__}: {exc}"
            return None
        # It says `ready` when its classes are loaded. Waiting for that here
        # means the first book's timeout is a timeout on the book rather than
        # on a JVM that had not finished starting.
        ready = _read_line(process, timeout=180)
        if ready != "ready":
            self.reason = "the driver did not come up"
            _kill(process)
            return None
        self.reason = ""
        return process

    def check(self, epub_path: str, json_path: str, timeout: float) -> int | None:
        """EPUBCheck's exit code, or ``None`` — meaning: do it the old way."""
        if not self.enabled():
            self.reason = f"{ENV_SHARED} is off"
            return None
        with self._lock:
            if self._process is not None and self._process.poll() is not None:
                self._process = None  # it died between books
            if self._process is not None and self._command() != self._started_with:
                self.reason = "the validator changed underneath it"
                self._drop()
            if self._process is None:
                self._started_with = self._command()
                self._process = self._start(self._started_with)
                if self._process is None:
                    return None
            payload = "\0".join([epub_path, "--json", json_path, "--quiet"]).encode("utf-8")
            try:
                assert self._process.stdin is not None
                self._process.stdin.write(f"{len(payload)}\n".encode("ascii") + payload)
                self._process.stdin.flush()
            except (OSError, ValueError, AssertionError):
                self.reason = "the driver stopped listening"
                self._drop()
                return None
            answer = _read_line(self._process, timeout)
            if answer is None:
                # Silence past the timeout leaves the pipe in an unknown state:
                # the next answer to arrive would belong to this book and be
                # read as the next one's. Killing it is the only honest move.
                self.reason = f"no answer within {timeout:.0f}s"
                self._drop()
                return None
            try:
                code = int(answer)
            except ValueError:
                self.reason = f"unreadable answer: {answer[:40]!r}"
                self._drop()
                return None
            # -1 is the driver saying the checker threw. That is not an answer
            # about the book, so the book gets its own process.
            return None if code < 0 else code

    def _drop(self) -> None:
        if self._process is not None:
            _kill(self._process)
            self._process = None

    def stop(self) -> None:
        with self._lock:
            if self._process is None:
                return
            try:
                assert self._process.stdin is not None
                self._process.stdin.write(b"bye\n")
                self._process.stdin.flush()
                self._process.wait(timeout=10)
            except (OSError, ValueError, AssertionError, subprocess.TimeoutExpired):
                _kill(self._process)
            self._process = None


def _read_line(process: subprocess.Popen, timeout: float) -> str | None:
    """One line from the process, or ``None`` if it does not arrive in time.

    A blocking `readline` on a pipe has no timeout on Windows, and a validator
    that hangs would hang the window with it. A thread doing the blocking read
    is the portable answer; when it times out the process is killed by the
    caller, which is what frees the thread.
    """
    box: list[str] = []

    def read() -> None:
        assert process.stdout is not None
        line = process.stdout.readline()
        if line:
            box.append(line.decode("utf-8", "replace").strip())

    worker = threading.Thread(target=read, daemon=True)
    worker.start()
    worker.join(timeout)
    return box[0] if box else None


def _kill(process: subprocess.Popen) -> None:
    try:
        process.kill()
        process.wait(timeout=10)
    except (OSError, subprocess.SubprocessError):
        pass


#: The one shared by everything in this process.
SHARED = SharedValidator()

atexit.register(SHARED.stop)


#: How many distinct message shapes one verdict may record.
MAX_SHAPES = 12

#: A plain markup name: what an element or an attribute is called. Short, no
#: spaces, no slashes. Everything else quoted in a message is treated as
#: possibly the book's own and masked.
#: What may be kept unmasked inside an EPUBCheck sentence: a name that belongs
#: to a *vocabulary* — an element, an attribute, a property — rather than to a
#: book. The old pattern allowed leading underscores, `\w` (so underscores and
#: any Unicode letter) and forty characters, and on that reading a package
#: identifier of the form `Author_Title_9789024531790` counted as a markup name.
#: One did: it sat unmasked inside a recorded signature in the **public**
#: repository, carrying an author and a title, and was found only when the
#: private name scanner was taught that book.
#:
#: The rule that separates the two, and the reason it holds: **no HTML, SVG or
#: EPUB element, attribute or property name contains an underscore.** They are
#: hyphenated (`http-equiv`), namespaced (`ns1:file-as`, `xml:lang`) or
#: camel-cased (`viewBox`); publishers' identifiers are none of those things and
#: reach for `_` constantly. The length cap is the second half: the longest name
#: in any of those vocabularies is well under it, and an identifier is usually
#: well over.
_MARKUP_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9]*(?:[-:.][A-Za-z0-9]+)*$")
_MARKUP_NAME_MAX = 24

_QUOTED = re.compile(r"""(["\u201c\u201d'])(.*?)\1""", re.DOTALL)


def message_shape(text: str) -> str:
    """An EPUBCheck sentence with anything book-specific taken out.

    `element "img" not allowed here` keeps its `img`, because that is HTML's
    word and not the publisher's. `value of attribute "id" is invalid: "rozdz-Å›wit"`
    loses the value, because that one came out of somebody's book.

    Getting that line wrong is not a cosmetic mistake: these shapes are recorded
    into signature files that live in the **public** repository, so a quoted
    string kept by accident is a title published on purpose. One was —
    see `_MARKUP_NAME`.

    Truncated, because the tail of a schema error is a list of every element
    that would have been allowed instead, and it is very long and says nothing
    the head has not already said.
    """
    if not text:
        return ""

    def mask(match: "re.Match") -> str:
        inner = match.group(2)
        looks_like_markup = (
            len(inner) <= _MARKUP_NAME_MAX and _MARKUP_NAME.match(inner) is not None
        )
        return f'"{inner}"' if looks_like_markup else '"…"'

    cleaned = " ".join(_QUOTED.sub(mask, text).split())
    return cleaned[:140]


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
        # The warm JVM first; `None` from it means "this one goes the old way",
        # and the old way is the line below, unchanged.
        if SHARED.check(epub_path, json_path, timeout=300) is None:
            spawn.run(
                command + [epub_path, "--json", json_path, "--quiet"],
                capture_output=True,
                timeout=300,
                check=False,
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
    shapes: Counter = Counter()
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
            shape = message_shape(text)
            if shape:
                shapes[f"{identifier or '?'}: {shape}"] += 1
    result.codes = dict(sorted(codes.items()))
    # Capped: a book with two hundred distinct complaints has one problem, and
    # a signature is not the place to enumerate it.
    result.shapes = dict(sorted(shapes.items())[:MAX_SHAPES])

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
