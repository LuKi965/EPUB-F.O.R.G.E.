# Changelog

Maturity is stated in words, not encoded in the number: `__stage__` sits beside
`__version__` and appears wherever the version does — `alpha` today. MINOR
moves when the stage does, against the entry conditions in `CONTRIBUTING.md` —
or when the owner names a release after a completed, audited plan, which is
what `0.3.0` was (the plan carried the name before the release did). PATCH
moves on every release, whatever it contains, so there is no judgement call to
make and therefore no way for one to drift upwards.

The number says nothing about how significant a change was. That is what the
entries below are for.

The version lives in `epubforge/__init__.py` and is the single source for
`pyproject.toml`, `epubforge --version`, the window title and the Windows
installer — bump it there and everything follows.

---

### A note on how books are named here

Every book this changelog cites is somebody's paid-for copy on the owner's
disk, and this repository is public. They are numbered — *Book 1*, *Book 2* —
rather than titled. The numbering is stable across entries, so an argument that
runs over several releases stays followable; which number is which title is
recorded once, privately, and nowhere here.

The corpus signatures never held a title in the first place: they are counts and
hashes by design, and the file name of each is the hash of the book rather than
its name, because a listing of titles in a public place says more about a shelf
than about a tool.

### A note on the numbers below

Releases 0.2.0 through 0.8.1 were numbered under two earlier schemes, both of
which used MINOR as a rough measure of "how much got done". Nothing was ever
tagged or published under those numbers, so they were renumbered rather than
left to imply a maturity the software does not have. The history is kept as
written; only the current version was reset.

## Unreleased

### Properties CSS does not have are removed, in both modes

The first slice of the 0.4 plan's stylesheet rebuild, and the largest single
mountain in its measured baseline: of 41 997 findings Calibre's own CSS lint
raises over the rebuilt shelf, 36 791 are declarations of properties that do
not exist — Word's `mso-font-charset` and its siblings, thousands per book,
parked inside `@font-face` blocks. Every conforming CSS parser drops such a
declaration before any reader sees it, so removal cannot change a pixel; the
render gate verifies that per book anyway. The authority is deliberately the
gate's own: the vendored `known-css-properties` catalogue is the dataset the
lint rule reads, so the program decides by the same measure it is judged by.

Three doors stay open. A vendor-prefixed name never reaches the judgement —
`-epub-hyphens` is honoured by shipping readers, and a reader's private
prefix invented tomorrow cannot be in any catalogue. `panose-1` is kept, the
CSS 2.1 font descriptor Calibre itself writes and suppresses in its own
lint. And `adobe-*` stays with its existing mode-aware handling: bare and
unlisted, but old RMSDK engines honour it, so "no parser knows it" would be
a lie there. A rule left empty by the removal goes whole, `@font-face`
included, and the whole removal sits behind the same opt-out as the sweep.

Alongside it, the `<!-- … -->` comment wrapper an HTML-era converter left
around `<style>` content is stripped — 312 of the baseline's 314 parse
errors; every CSS parser since 1997 was ignoring it. Only the leading and
trailing shield is taken: an arrow inside somebody's `content:` string is
content and stays.

## 0.3.0 — alpha — 2026-08-20

The number `0.2.30` was never released — the owner skipped it (D-032) when its
content outgrew a patch: the whole of the 0.3 plan landed inside it. This is
that release, under the plan's own name, verified position by position by the
seventh audit before the tag.

It began as the first release whose entire content came from **running the
program over the owner's whole shelf** rather than from reading its code — one
strict run over 160 books, nine refusals, six of them this program's doing —
and grew into the plan those findings fed: readable class names, print
plumbing removed, footnotes linked on request, and two new questions in the
decision queue. All of it is below.

### Content in the head was being made visible

A `<p>` where only a `<meta>` belongs cannot stay there — XHTML5 does not allow
it — so this program moved it to the top of the body, on the stated grounds that
"a browser starts the body at the first thing that does not belong in the head,
so it was already the first thing on the page".

That is true of an **HTML** parser. These documents are XHTML and parse as XML,
where the paragraph stays in the head and the head is not drawn. It was on no
page at all. On *Book 10* three such paragraphs came out of the head and pushed
eighteen pages down by about 105 px each, dropping the last paragraph of each
off the bottom of the screen. The render gate refused the book, which is how
this was found.

Content moved out of an XML document's head is now taken out of the drawing
rather than into it: the text stays in the file, in reading order, and the page
looks exactly as it did. A document the book declares as HTML keeps the old
behaviour, because there the paragraph really was being shown.

### The cover repair was pushing the cover off the bottom

The block of CSS added to a cover page that had none gave `html, body` a height
of 100% and left the browser's default 8px body margin in place — which makes
the page taller than the window, so the centred cover sits below the fold and
its bottom edge is cut. Two books, `91.2% → 82.0%` and `56.2% → 44.5%` of the
page's ink, both refused by the render gate.

The comment above those rules claimed they "can only ever make the image smaller
than it already is". Measured, they also moved it. The generated cover page had
`margin: 0` from the start; the block added to an existing page now has it too,
which is what the two paths were supposed to share.

### A table of contents naming one place several times made the book invalid

`playOrder` is a property of the place, not of the entry, and the NCX
specification says so: entries naming the same target must carry the same
number. Written as a running counter they did not, and EPUBCheck answered
`different playOrder values … refer to same target`.

It surfaces on a book that arrives with the same `id` on several headings —
a converter's doing, older than this program. Numbering now follows the target.
Repointing those entries at the headings they were *probably* meant for is a
different question and deliberately not answered here: it is a guess about the
source, and this program does not repair by guessing.

### CSS inside a document is repaired like CSS in a file

A `<style>` element got two things — remote `@import` stripping and url
repointing — and none of the stylesheet repairs. So a dead `url()` in a
`<style>` block stayed dead, which is the exact defect the dead-url work exists
to prevent, in the one place it never looked. Two of the nine refusals came out
of that gap.

Both now go through the same chain.

### A declaration written like an HTML attribute is dropped, not corrected

`p.sgc-1 {text-align="center"}`, from a converter. EPUBCheck: `Token "=" not
allowed here, expecting :`.

Dropped rather than corrected, and that is the careful choice: every reader
already discards the declaration, so removing it changes nothing anybody has
seen, while turning the `=` into a `:` would start centring text that has never
been centred. Which the publisher wanted is a question about their intent, and
the answer that happens with nobody there to ask is the one that changes
nothing. Gated like every other removal: `preserve` keeps it and says so.

### The dead-rule sweep reaches the styles written into chapters — by default

Converters leave most of their litter not in stylesheets but in `<style>`
blocks pasted into every chapter: measured across 160 books, 66 116 rules that
no selector in the book can ever reach, against 6 303 in the sheets. They are
removed now, in **both modes** — the owner's line, verbatim: preserve keeps the
book's layout, not the converter's litter. Unticking one box (or
`--keep-style-junk`) keeps everything and only counts.

What is removed is narrow on purpose: only rules whose dead names are a
converter's (`sgc-`, `calibre`, `mso`, `kix`…) or whose whole block is stamped
verbatim into three or more chapters. Anything else dead is kept and counted,
which is what makes the prefix list safe to be incomplete. The same broom now
reaches the separate stylesheet files too, in both modes — the litter is the
same litter wherever the converter left it.

For a while during development there was a third bucket: a dead name one edit
away from a name the book *uses* became a "possible typo" question. The owner
asked the question that removed it — why hunt for typos in a book being
rebuilt? — and the arithmetic agreed: a dead rule draws nothing, so keeping or
removing it looks identical; the only thing the question could *do* is make
the rule start applying, which changes how the book looks, against this
program's own promise. Across 160 books it asked exactly zero questions while
its machinery produced two real defects. It never shipped.

Measured before it was allowed in: the full shelf several times over, the two books
with the largest cuts (49 545 and 8 525 rules) redrawn page by page on the
pinned engine — 334 measurements, not one pixel of content lost.

### Footnotes a converter abandoned halfway are joined on request

Measured on the shelf before it was designed: 19 books have working
footnotes — never touched — and the dominant defect is a converter that
linked part of a notes section and dropped the rest, leaving bare `[N]`
markers in running text while notes numbered `N` wait a few files over.
Seven books, 205 markers; the other 153 books have nothing of the kind and
are never asked a single question.

When both ends of the bridge exist, one question per book shows the first
pairs and offers to join them. On "link", the marker's own characters are
wrapped in an anchor — the text is identical before and after, to the
character — and the note paragraph receives an id when it has none. A marker
already inside a link is a working footnote and is nobody's business here;
a number matching no note stays as it is; a numbered list in an ordinary
chapter does not make a notes section. Without an answer nothing changes,
and unticking one box declines the question in advance.

### Class names a person can read — the epubforge dictionary

`calibre7`, `sgc-1`, `Hoofdtekst9a`: a converter names its styles after
itself, and whoever opens the file later learns nothing from any of them.
Such names now become the epubforge dictionary's, by default in both modes
(unticking the box or `--keep-class-names` keeps them): `ef-akapit-3`, `ef-naglowek-1` — or, where
one to three atomic declarations carry the whole truth, a name that *is* the
rule: `ef-kursywa`. Under an English window the same book names itself
`ef-paragraph-3`, `ef-italic`: the name's language follows the interface,
because whoever hand-edits the file later is whoever built it.

The category is never guessed: it comes from what the class is attached to in
this book — a class seen only on `<h2>` is a heading, a class seen on a
heading *and* a paragraph proves neither and lands in `ef-inne`. The number
is the order of first use in reading order, and means nothing else. The
rules' values are untouched to the character; identical rule bodies collapse
to one name; the report carries the full old-to-new map. A book with a script
or with attribute selectors on `class` is left alone entirely — there a name
can live beyond this rename's reach.

### Word's print plumbing is taken out of the styles

`div.Section2 { page: Section2 }` — measured at 7 694 live rules across 160
books. The `page` property maps a block onto a named print page; no EPUB
reading system applies it to reflowing text, so it draws nothing anywhere and
never has. It is removed now, in both modes, behind the same opt-out as the
rest of the sweep; a rule left empty by the removal goes whole. Two boundaries
hold: `page-break-*` is real styling readers honour and is never touched, and
a pre-paginated publication keeps its `page:` — there it is paged media and
the property is in its element.

### Three teeth the seventh audit found missing, grown the same day

The seventh audit verified everything in this release and measured three
gaps beside its verdicts, all three closed here. Two tests about strict
refusing to publish an invalid file failed on a machine without EPUBCheck —
they were about the validator and did not say so; they carry the `validates`
marker now, and on a machine without the validator the gate's own refusal
(`BLOCKED`) keeps them honest. The GUI's status-colour repair had no test —
the colour table is module-level now, one invariant test holds the two
tables to the same set of statuses, and the audit's own reproduction
(painting every status in real Qt) is a test too. And a comment in the
render gate claimed the render suite would catch the cover block losing
`margin: 0` — the audit measured that mutation leaving all 43 render tests
green. The claim was made true rather than softened: a new ink test
measures the 8px shift the missing margin causes (EF-057's own shape), and
the mutation now fails exactly that test.

### A typo of the publisher's own hand becomes a question

`text-align="center"` — an `=` where CSS wants a colon — has been dropped in
strict since EF-059, on the grounds that no reader ever applied it. That
reasoning holds for a converter's rule, and the shelf's one measured case sits
in a `sgc-` rule, converter-signed. But the same typo in a rule nobody's
generator named could be a publisher's slip of the finger, and whether they
wanted the line gone or wanted it working is a question about intent, not a
fact about the file.

So the two now part ways (pillar 4 of the 0.3 plan). A line in a
generator-signed rule or a stamped boilerplate block keeps the measured path:
strict drops it, preserve keeps it, silently either way. A line no generator
signed becomes a question with three answers — leave it, remove it, or enable
it, where enabling turns the `=` into a `:` and formatting nobody has ever
seen starts applying, on a person's word. The safe default is leaving it, and
an "enable" answer never switches on the converter junk standing beside it in
the same sheet. One consequence is stated rather than hidden: a kept invalid
line means strict declines to publish the file, and the report says exactly
why — that is the person's choice carried out honestly, not a defect.

### Eleven contents entries, one landing place — asked, not guessed

The finding (EF-058) predates this release: a source document carried one id
eleven times, the rebuild untangles the copies correctly, and the eleven
contents entries that pointed at the shared id kept pointing at its first
occurrence — eleven entries, one landing place, exactly as broken as the
source. The earlier fix stopped EPUBCheck's `playOrder` complaint; the
entries themselves stayed tangled, and deliberately so: assigning the n-th
entry to the n-th occurrence is probable, and probable is not the standard
`REPAIRED` demands.

The audit named the honest way out — the reference rules' third verb, ask —
and that is what happens now (pillar 4 of the 0.3 plan). When the counts
agree, one question shows each entry's label beside the text it would start
leading to, assigned by document order, and says in as many words that the
assignment is probable rather than certain. On a person's word the entries
are repointed, in the navigation document and the NCX alike; without an
answer every entry keeps jumping where it jumped yesterday, and the report
carries a count. When the counts do not agree, no ordering is even probable,
so nobody is asked at all. The knowledge this runs on — which duplicate
became which name — existed for one moment inside the id repair and
evaporated; it is now kept for the navigation stage, which is the whole of
the plumbing.

### A generator's own words survive the translation

The seventh audit put its finger on a loss the dictionary was inflicting:
`sgc-toc-title` — Sigil's own record that it generated a table of contents —
was coming out as `ef-akapit-1`, a name that says less than the one it
replaced and, worse, says something false. The owner's verdict was the
obvious one in hindsight: a role word the generator wrote into its own name
is the tool's note of purpose, the same class of fact as the cover repair's
refit marker, and it should be translated rather than discarded.

Measured first: of 566 distinct generator class names on the shelf, 96 carry
any word at all, and after machine vocabulary is set aside five families
remain — the contents family (`toc`, with `title` and `level`), hyperlinks,
tables, and print headers and footers. Those now translate: `sgc-toc-title`
becomes `ef-spis-tresci`, `sgc-toc-level-2` becomes `ef-spis-tresci-2` with
the digit carried from the source because there it means the level, and the
English window says `ef-contents`. One contradiction closes the door: a
class carried only by images is not a table of contents whatever its name
claims. Alongside it, the audit's other half: a block class whose
declarations dress like a heading — bold, uppercase, or a font a third
larger — now lands in `inne`, which claims nothing, instead of `akapit`,
which was fourteen times a lie on this shelf.

### Three findings from the seventh audit, closed the same day

The audit verified all nine positions and left three measured findings, none
blocking. All three are closed: the two strict-refusal tests that failed on
a machine without EPUBCheck carry the `validates` marker now, so the real
gate answers for them everywhere and refusal stays honest — `BLOCKED` for
want of a validator is still a refusal. The GUI's status colours live in a
module-level table mirrored against `STATUS_KEYS` by an invariant test, so
the next status added to one table and not the other fails a test instead
of a person. And the render suite holds the line its comment in `_judge`
claimed it held: a new test measures in ink what dropping `margin: 0` from
the added cover block does — the image slides down and off the page bottom —
where until now only guards that read the text of the CSS stood watch, the
class of guard EF-057 originally got past.

### The hidden paragraph is now hidden without CSS too

The fifth audit took apart the reasoning behind hiding head-content with an
inline `display: none` alone: a book's stylesheet can override that just as it
can override the `hidden` attribute — they are vulnerable to *different*
overrides, not more and less. And the attribute says something CSS cannot: to
receivers that never apply a stylesheet — text extraction, braille lines,
read-aloud — a CSS-hidden element is content, and this content was never on any
page. The moved element now carries both signals.

### The cover limit now actually limits

Found by the new test the audit asked for — the one that measures the cover
page's ink instead of reading the CSS. `max-height: 100%` is a percentage of
the containing block, and the cover image in real books sits inside a `<div>`
whose height is auto — against which the percentage computes to **no limit at
all**. The rule this program has been adding since the cover findings was inert
on exactly the shape it was written for, and nobody saw it because the gate
compares against the source and the source overflowed identically.

It is `max-height: 100vh` now, in both cover blocks: the viewport is definite
from anywhere. The page-with-text fallback keeps its old inline rule on
purpose — capping an in-flow image to the window there would change how the
book looks, and that decision is not this program's to make.

### The gate no longer reads that repair as damage

The direct consequence of the fix above, found by the sixth audit before any
user could: a cover that overflowed two screens shows *fewer pixels* once it
fits on one, the gate measures that as lost ink, and 22 of 82 real covers in
the most common shape (`div` + `img`, nothing sized) were **refused for being
repaired**. The louder the repair, the harder the refusal.

The page the repair touches carries a marker sentence — it always has, as a
comment for whoever opens the file — and the gate now reads it back: on a page
this program refitted on purpose, the only thing still held against the book is
coming out *blank*. A fact the program wrote down beats a fact guessed back out
of pixels — the same principle the reference repairs already state.

Two cleverer versions were built first and measured out of existence on the
same 82 covers: reading cut-vs-fit out of the ink's edges fell to artwork with
white of its own (17 of 40), and predicting where the ink must sit from the
image file fell to dark covers, whose "paper" is the cover's own colour (37 of
82). Every pixel-side rule inherits that limit of the ink measure itself. The
CSS the marker vouches for is guarded where guarding works: by the render
suite's ink tests and their mutations, once, rather than per book by a gate
that cannot tell fitting from losing.

### A recorded signature was carrying somebody's title

Not from the shelf run — from the gate that guards it. The private name scanner
was taught the seven books behind the findings above and failed immediately, on
a file that had been in this repository for releases: a corpus signature holding
an EPUBCheck sentence with a package identifier of the form
`Author_Title_9789024531790` still in it.

Signatures mask every quoted string that is not "a plain markup name", and the
pattern for that allowed underscores and forty characters — under which a
publisher's identifier is a markup name. It is not: no HTML, SVG or EPUB element,
attribute or property name contains an underscore. Four signatures were carrying
a title; all four have been re-masked, and a test now reads every recorded
signature and fails on the shape rather than on the particular title.

### An old-style anchor counts as an anchor again

`<a name="fn1">` is how a document written before XHTML 1.1 spells an anchor,
and this program converts it to `id="fn1"` — but *after* it has already decided
which links resolve. So a live link into such an anchor was reported as pointing
at nothing, and in strict mode that report is what decides whether the book may
be published at all.

## 0.2.29 — alpha — 2026-08-17

### The K1 gate was disarmed, twice, and both times by us

A rule that removes nothing was excusing a loss it had nothing to do with: a
book carrying a watermark had the gate stood down across the whole file. The
fix narrowed the excuse to the loss the rule actually names.

The correction to that correction was worse than the fault. Folding both sides
of the comparison through the whole C1 block let a book come out **18 545
characters shorter** with the gate silent — those characters were its quotation
marks and dashes, read as Latin-1 by whoever converted it. The set folded away
now holds only what cp1252 leaves undefined: five positions, not thirty-two.

The rule that came out of it is wider than the defect: what you fold out of a
comparison must be something that **cannot be text**, not something the writer
happens to delete. The two sets look identical. They are not.

### Punctuation a conversion broke is repaired, not deleted

Those characters are not damaged beyond recognition — the cp1252 table is
one-to-one, `0x93` is always a left quotation mark. Until now every one of them
was deleted as unwritable. Now they are translated, **after a question**, once
per document, with a census by character: "1174 dashes" is something a person
can answer and 1174 separate questions is not. The table is built by the codec
at import, not transcribed by hand.

Answering *leave them* now actually leaves them. It used to say that and delete
them anyway further down, which is worse than not offering the option.

### A run's own figures were flattering it

Three separate ways, all found and fixed in one day:

- **A net difference cancelled an added error.** One rule's error disappearing
  and another appearing in the same book left the total unmoved, so the column
  meant to catch *newly introduced* errors stayed empty. It counts by code now.
- **An excuse covered the whole book.** One rule in the report was excusing
  every error in the file. It now covers only errors of the shape that rule
  names — and the first attempt at that, a list of six attribute names taken
  from whatever the sample happened to show, was itself the same mistake in
  miniature: a control run turned up 42 supposedly introduced errors, 41 of
  them the same class as the names on the list.
- **The summary described the file on disk rather than the run.** A rebuild
  that ran and a signature that was written are not the same event.

### Output no longer differs between machines

Four books in a hundred and sixty came out differently on Windows than on
Linux, with identical rules, text and validator verdict. The difference was one
line: `0101-01-01` against `101-01-01`. `strftime("%Y")` hands the year to the
platform's C library, and the two disagree below the year 1000 — with Linux
producing the invalid one. Years are formatted directly now.

### Every transformation that changes characters of text goes through a contract

Precondition, mutation, postcondition and undo as data and functions rather
than as habit. A false precondition is an ordinary answer — this book does not
have that. A false postcondition costs the transformation its work: the
document goes back **byte for byte**, because reverting by inverse operation
needs knowledge of what changed, which is the very thing missing here.

Five rules run through it, and they are not the convenient ones — they are the
complete set of transformations that alter characters a reader will see:
encoding repair, hyphen joining, shop-notice removal, and moving or deleting a
watermark marker. Everything else in the program moves markup, styles and
metadata, where a mistake is something the validator sees. Here it is something
the reader sees, and only on that page.

Where the postcondition does not come out, the marker or the sentence **stays in
the book**. A shop footer you can see and report costs less than a sentence of
the novel whose absence you notice a page later.

### The balance sheet had been missing its riskiest entries

The ledger — the addable record of what a rebuild did, as opposed to the report
that describes it — was silent on the three transformations that take
reader-visible characters away: the shop sentence and the watermark in both its
modes. They had a sentence in the report and no line in the balance.

Two verbs in its vocabulary turned out never to have been written by anything.
`reconstructed` covered the one transformation that publishes a *parser's
reading* as a fact about the book — after a damaged package is recovered,
nothing in the output says the title was not always there. `carried` covered a
deliberate keep, and the one that costs something is a visible notice holding
somebody's e-mail address, which ships in a file that gets sent on. Both are
entered now, and a test refuses any verb that nothing writes.

### Two guards that were not guarding anything

An independent verification pass over forty-three findings came back with no
regressions — and with two places where a test named after a defect did not
actually hold it.

The clock: a stage walking six hundred documents is supposed to be interruptible
from inside, not only between stages. The test asserted that `checkpoint` was
**called** often enough. Take the clock out of `checkpoint` and the calls remain,
because cancellation still goes through them, and all fifty tests pass. The
assertion now is that a stage with a short limit **stops without finishing** —
which is the thing the finding was ever about.

The balance sheet: removing an unreferenced file writes a ledger entry, and that
was held by a test injecting its own file-losing stage. The real path — the one
somebody switches on to sweep a book — was never run with an assertion about the
entry. It is now, along with the entry naming which file went.

### A rule that was applied once instead of everywhere

A second, stricter verification pass found three fixes with nothing holding
them. The most instructive is a check that already existed: *an entry for
something the fixture never had is a note about nothing.* It guarded the list
of deliberate omissions and not the list of open defects — so a construct added
to the test fixture precisely because its absence made losses invisible could be
deleted again with the whole completeness suite staying green.

The check came from a finding about a dead entry in the first list. The rule was
general; the application was not. Both lists have it now.

Two more of the same family: the summary that describes *this* run rather than
the last recorded one had no test setting the two in conflict, and a docstring
corrected to match the default policy had nothing keeping it in step if the
default moved.

### Smaller

- `meta http-equiv` and `meta content=` are the fifth and sixth shapes of EPUB 2
  markup the detector knows; three books in the mixed collection were passing as
  clean.
- The `<head>` window is found by looking for `</head>`, not by reading a fixed
  4096 bytes — Word exports put more than that in front of the encoding
  declaration.
- `--plan` rebuilds a book, runs every gate, prints the full ledger of
  high-risk changes and **writes nothing**. Distinct from `--dry-run`, which
  does not read a book at all. Available from the window.
- The suite no longer needs a JDK, only a JRE.

## 0.2.28 — alpha — 2026-08-16

Seria porządkowa według specyfikacji właściciela, kroki 0–9, domknięta.
Trzydzieści trzy ustalenia w rejestrze, z tego **jedno** zostaje otwarte.

### Dokument pakietu jest poprawnym XML-em, cokolwiek niesie książka

WP-18, i najważniejsza pozycja tego wydania — bo dotyczy książek, które program
**zapisywał jako nieotwieralne**, w trybie domyślnym, meldując `succeeded`.

EF-038 mówiło, że pakiet powstaje przez sklejanie stringów (58 × `lines.append`)
i traktowało metodę jako ryzyko. Zanim przepisałem 475 linii, sprawdziłem, czy ta
metoda faktycznie produkuje zepsuty dokument. **Nie produkuje.** Czternaście
wrogich wejść — `<script>`, `]]>`, deklaracja XML, podwójny myślnik tam, gdzie
komentarz XML go nie uniesie, pięć tysięcy znaków, emoji spoza BMP — wychodzi
jako poprawny XML, bo każda wartość idzie przez `escape` albo `quoteattr`.

Zepsute wychodziło co innego: **znak sterujący**. Nie ma czym go zaescapować —
XML 1.0 w ogóle nie ma dla niego zapisu. Zmierzone:

| tryb | książka z `0x0B` w tytule |
|---|---|
| `preserve` (domyślny) | **zapisana**, pakiet się nie parsuje, status `succeeded` |
| `strict` | odmowa |

I rzecz, która przesądziła o wyborze naprawy: **przepisanie na drzewo by tego nie
naprawiło.** lxml na tych znakach rzuca wyjątkiem zamiast je zapisać, więc wynik
przesunąłby się z „nieotwieralna książka" na „wywrotka" — lepiej, i nadal nie
książka.

Naprawa siedzi w jednym miejscu: `escape` i `quoteattr` przesłonięte w
`writer.py`. Reguła, o której trzeba pamiętać w pięćdziesięciu siedmiu
miejscach, zostanie pominięta w pięćdziesiątym ósmym.

**Usterka okazała się szersza niż ustalenie.** Po naprawie writera `nav.xhtml`
i `toc.ncx` **nadal** wychodziły niepoprawne — są generowane przez etap nawigacji
z tych samych metadanych, przez inny helper. Oba zapisywane, oba nieotwieralne.
Dlatego test sprawdza teraz **całe archiwum**, a nie plik, który ustalenie akurat
wymieniło.

Nigdy po cichu: raport nazywa pola, z których znaki zniknęły. Program edytuje
czyjś tytuł, więc to mówi.

### Widoczne ślady księgarni — do usunięcia, jeśli o to poprosisz

WP-17 / D-019. Dotąd widoczna notka księgarni była **zawsze** zachowywana, na tej
podstawie, że zdanie, które kupujący ma przeczytać, to jego sprawa. Odwrócone:
jest jego sprawą właśnie dlatego, że to on kupił książkę — a taka wstawka potrafi
siedzieć w biegnącym tekście tuż przed pierwszym zdaniem powieści albo dokładać
całą stronę.

Zastrzeżenie, które przy tej funkcji musi paść: program **nie zdejmuje DRM**
i nie służy do obchodzenia zabezpieczeń. Usuwa wstawki księgarni z plików, do
których użytkownik ma prawo, i zakłada, że je ma.

Nowy przełącznik, **domyślnie wyłączony**, osobny od „znaków wodnych" (tamten
pyta, jak widoczny może być ukryty znacznik; ten pyta, czy wolno skasować
zdanie). Nie sięga go **żaden** preset, nawet ścisły: zgodność nie jest powodem
do kasowania czyjegoś zdania.

Sercem jest lista fraz i to, czego na niej **nie ma**. Zabierane są wyłącznie
zdania nazywające **sprzedaż**. Odrzucone kandydatury, każda z powodem: gołe
„kopia"/`copy` (siedzi w `copyright`), goły adres e-mail (stopka redakcyjna go
ma), gołe „licencja"/`license` (Gutenberg pisze to o sobie w każdym tomie),
„wszelkie prawa zastrzeżone" (to jest strona praw autorskich).

**Usuwanie zdaniami, nie elementami** — i tu test złapał mnie na realnym błędzie
w pierwszej wersji. Stempel bywa sklejony z otwarciem powieści bez kropki między
nimi, więc podział po zdaniach zostawia to jako **jeden** kawałek — a wyrzucenie
kawałka zabiera pierwszą linijkę książki. Teraz usuwana jest fraza plus ciągnące
się za nią identyfikatory, a to, co zostanie, jest badane ponownie: proza
zostaje.

Reguła jest świadomie zachowawcza w jedną stronę: **zostawione nazwisko
kupującego to skaza, którą widać i można zgłosić; skasowane zdanie powieści to
uszkodzenie, którego można nie zauważyć aż do tej strony.**

Raport wypisuje każde usunięte zdanie **co do słowa**, nie liczbę — to jedyny
przełącznik w programie kasujący tekst widoczny dla czytelnika, więc masz czym
sprawdzić, że zabrał zdanie księgarni, a nie zdanie z książki. Żadna strona nie
jest usuwana.

### Reszta serii

Kroki 0–8 opisane w pozycjach poniżej: katalog pytań (EF-032), podział
`stages/content.py` (EF-031), formatowanie absolutne (EF-029, EF-033), słownik
łączników z instalatorem (EF-028), oraz **EF-036 obalone** — wszystkie pięć
„narzędzi autora" jest osiągalnych z okna, więc siedzą w pakiecie dlatego, że
kontrakt tego wymaga.

**Liczby tego wydania:** 2652 testy przechodzą, 46 pominiętych, zero porażek.
Korpus publiczny: 19 książek × 3 tryby, zero błędów EPUBCheck, dwie świadome
odmowy w trybie ścisłym. Sygnatury korpusu **bajtowo identyczne** przez cały
podział `content.py`.

### Słownik jako drugi dowód dla łączników — pierwsza połowa

WP-10, część detekcyjna. Detektor miał jeden dowód: *czy ta sama książka pisze
to słowo bez łącznika gdzie indziej*. To jest mocny dowód i **nie ma go
dokładnie tam, gdzie jest potrzebny** — przy słowie, które w książce występuje
raz. Sześć realnych artefaktów z Książki 2 ginęło bez śladu z tego powodu.

Słownik odpowiada na jedno pytanie, nie na wszystkie: **czy pierwsza połówka
jest słowem**. Zmierzone na prawdziwym `pl_PL`:

| słowo | lewa | złączone | wniosek |
|---|---|---|---|
| `doboro-wym` | **nie** | tak | artefakt, bez pytania kogokolwiek |
| `przeko-naniem` | **nie** | tak | artefakt |
| `wspo-minał` | **nie** | tak | artefakt |
| `czarno-czerwone` | tak | tak | nie da się rozstrzygnąć |

Złożenie, którego pierwsza połowa nie jest słowem, **nie istnieje** — więc
łącznik wstawiła konwersja. To rozstrzyga trzy z sześciu artefaktów właściciela
bez zadawania mu ani jednego pytania, a na książce korpusu publicznego
wychwyciło kandydata, którego wcześniej nikt nie widział.

Silnik: **`spylls`** — hunspell przepisany na czysty Python, czyta te same
`.dic`/`.aff`. Wybrany dlatego, że wiązanie C do hunspella **nie buduje się
nawet na Linuksie z kompletem narzędzi**, więc na Windowsie nie miałoby szans.

**Czego ta połowa nie robi**, i to jest świadome: kształty złożeniowe nadal nie
trafiają do kolejki jako `UNCERTAIN`. Pomiar mówi dlaczego — `nie-wielkich`
(artefakt) i `pseudo-naukowy` (słowo, którego ruszać nie wolno) są **nie do
odróżnienia** przez żaden sygnał, jaki ten program ma: obie połówki są słowami,
złączona forma jest słowem, kształt ten sam. Promowanie całej gałęzi wstawiłoby
każde `pseudo-`, `eks-` i `pół-` do kolejki jako pytanie. Próg mierzy się na
korpusie właściciela, nie zgaduje (D-012).


### Pytania mówią wreszcie tym językiem, co okno

EF-032, i to jest defekt, który trudno zobaczyć z polskiej maszyny. Raport ma
dwujęzyczny katalog od 0.2.4 i renderuje z `rule` + `values` w chwili
wyświetlenia. Pytania — czyli **jedyne miejsce, w którym ten program naprawdę
rozmawia z człowiekiem** — nie miały ani katalogu, ani renderowania: każde było
polskim literałem w tym module, który akurat je podnosił.

Więc użytkownik angielski dostawał okno po angielsku, a potem, w momencie
decydowania o czymś nieodwracalnym w swojej książce, akapit po polsku.

Nowy `epubforge/question_texts.py`: pięć pytań, dziesięć opcji, oba języki,
klucze nazywające **sytuację, a nie brzmienie**, żeby przeredagowanie pytania
było edycją jednego pliku.

Mechanizm celowo mniejszy niż w raporcie, i warto powiedzieć dlaczego, bo
wygląda na niekonsekwencję. Raport jest pisany raz i czytany w dowolnym języku,
więc trzyma dane i renderuje przy każdym odczycie. Pytanie jest zadane,
odpowiedziane i znika — renderuje się raz, w chwili zadawania.

Skąd język: `gui.strings.set_language` przestawia teraz oba naraz, więc nie ma
jak przestawić jednego bez drugiego. Poza oknem — `EPUBFORGE_LANG`, ta sama
zmienna, którą `cli.py` już czytał na końcową uwagę.

Test, który pilnuje tego naprawdę, dotyczy **cichej** awarii: klucz obecny
w jednym katalogu i nieobecny w drugim nie psuje się głośno — fallback podaje
polski i wszystko wygląda na działające, dopóki ktoś na to nie patrzy. Więc
sprawdzane jest, że oba katalogi mają te same klucze **i te same placeholdery**,
oraz że w `hyphens.py` i `pipeline.py` nie został ani jeden polski `summary=`.

### `stages/content.py` przestał być dwoma modułami w jednym pliku

EF-031. 3865 linii i dwie niezwiązane ze sobą roboty. `StyleStage` mieszka teraz
w `stages/style.py`, a granica jest ta, którą testy i tak już rysowały: tam
wchodzi tekst CSS i wychodzi tekst CSS, i nie dotyka to żadnego dokumentu
treści. `ContentStage` obok robi odwrotnie.

```
content.py   3865 → 2900 linii
style.py            987 linii
```

Przeniesienie, nie przepisanie — kod jest przeniesiony dosłownie, a osiemnaście
stałych i pomocników poszło razem z nim dlatego, że **pomiar** przed cięciem
pokazał, że używa ich wyłącznie ten jeden etap. Współdzielone (`strip_remote_imports`,
`_css_length`, `_colour`, `_selector_classes`) zostają w `content.py`, bo
`ContentStage` też ich używa; `style.py` importuje z `content.py`, nigdy
odwrotnie. Z zewnątrz nie zmienia się nic: `stages/__init__.py` nadal podaje oba
etapy z jednego miejsca.

**Dowód, i jest mocniejszy niż zielona suita.** WP-14 wymagał sygnatur korpusu
bajtowo identycznych, więc: `test_public_corpus` i `test_corpus_gutenberg`
przebudowały 19 książek w trzech trybach i porównały je z sygnaturami zapisanymi
**przed** podziałem — przechodzą bez nagrywania czegokolwiek od nowa, a pliki
sygnatur mają tę samą sumę SHA-256.

Granicy pilnuje teraz test, nie opis: `style.py` nie ma prawa importować `lxml`,
a cztery przeniesione stałe nie mają prawa wrócić do `content.py`. Bez tego
moduły zrastają się z powrotem po jednym wygodnym imporcie — dokładnie tak
powstało tamte 3865 linii.

Przy okazji **EF-037**: docstring `render_fidelity` mówił „opt-in check", a
`Policy.render_gate` domyślnie mówi `stop` (D-016). Prawdą jest domyślna.
Docstring nie jest drugim miejscem, w którym zapada polityka.

**EF-036 obalone.** Ustalenie mówiło, że pięć modułów to „narzędzia autora
w pakiecie runtime". Sprawdzone po kolei: `repair` (scalanie kopii), `survey`
(przegląd biblioteki), `corpus` i `fixtures` (zakładka Korpus), `edge_cases`
(`gui/tabs.py:709`) — **wszystkie pięć jest osiągalnych z okna**. Siedzą
w pakiecie dokładnie dlatego, że S-04 każe wszystko udostępnić z okna. To nie
jest dług do spłacenia, to jest kontrakt działający.

### Piksele przestały być cichą regułą

WP-13, i dwa ustalenia, które przy pisaniu okazały się **tym samym błędem
widzianym dwa razy**: przepisaniem cudzego arkusza na podstawie tego, co wydawca
prawdopodobnie miał na myśli, zamiast tego, co strona pokazuje.

**EF-029 — mierzone i nigdy niewypowiadane.** `absolute_font_sizes` było liczone
w inwentarzu od dnia, w którym przegląd powstał, i **nigdy** nie zamieniało się
w komunikat ani w naprawę. Najczęstsza pozostałość po składzie do druku na
półce była pod nosem programu przez całe jego życie. Teraz `css.absolute-units`
podaje liczbę **per plik**, w każdym trybie, niezależnie od tego, czy cokolwiek
ma być z tym zrobione.

Naprawa — `--relative-units` i przełącznik w oknie, **domyślnie wyłączone** —
idzie na **`rem`, nie na `em`**, i to jest cała jej bezpieczność. `em` liczy się
od rodzica:

```css
body { font-size: 20px }    p { font-size: 16px }
```

`16px → 1em` w takim `body` wychodzi jako 20px. Każde zagnieżdżenie w książce
kumuluje się inaczej i żadna staranność w arytmetyce tego nie ratuje, bo wyrażenie
regularne nie widzi, która reguła trafia do której. `rem` liczy się od elementu
głównego, nie kumuluje się i wychodzi dokładnie jako `rozmiar/16` — wszędzie.
Zmierzone na Chromium 141, wobec wydruku sprzed konwersji:

| konwersja | piksele różne |
|---|---|
| `rem` (trzy viewporty) | **0,000000%** |
| `em`, ta sama arytmetyka | 0,242292% |

I sama obietnica, bo funkcja, której obietnicy nikt nie zmierzył, jest tylko
opowieścią. Ustawienie czytnika przesunięte z 16 na 24:

| książka | piksele różne |
|---|---|
| bez konwersji | **0,0000%** — ustawienie czcionki jej nie dotyczy |
| po konwersji | 0,1998% — książka za nim idzie |

Druga liczba **nie jest defektem**: poza ustawieniem domyślnym strona celowo
przestaje wyglądać tak samo, i o to w tym chodzi. Dlatego to jest przełącznik,
a nie naprawa. Proporcje dobrane przez wydawcę przeżywają — wszystkie rozmiary
przesuwają się o ten sam czynnik.

Cztery miejsca po przecinku, i to nie jest liczba wzięta z powietrza: 16 jest
potęgą dwójki, więc każdy całkowity piksel dzieli się na najwyżej cztery miejsca
i wychodzi **dokładnie** — 11px to 0,6875rem, a nie zaokrąglenie. Arkusz, który
sam ustala rozmiar elementu głównego w pikselach, zostaje nietknięty i mówi
dlaczego: `rem` jest tam już przypięty, więc przepisanie reszty przerobiłoby
arkusz, nie uwalniając ani jednego rozmiaru.

**EF-033 — poprawka, która prostowała kursywę.** `font-style: regular` nie jest
CSS-em, więc parser odrzuca **całą deklarację** i element dziedziczy. Podmiana
na `normal` nie przywraca intencji wydawcy — ona **nadpisuje**, a nadpisanie
i dziedziczenie to to samo wyłącznie dopóki dziedziczona wartość i tak jest
normalna:

```css
.list { font-style: italic; }
.list .name { font-style: regular; }   /* odrzucone: zostaje kursywa */
```

Nazwiska są pochyłe od dnia wydania książki, a poprawka je prostowała. Wydawca
prawdopodobnie chciał inaczej; ten program nie odbudowuje książek do tego, co
wydawca prawdopodobnie chciał, tylko do tego, jak wyglądają (S-03).

Podmiana zachodzi teraz wyłącznie w arkuszu, w którym **nic** nie ustawia
kursywy ani pogrubienia — łącznie ze skrótem `font: italic 12px serif`, którego
sprawdzenie samego `font-style` by nie zobaczyło. W pozostałych deklaracja
zostaje taka, jaka jest, i raport mówi dlaczego. Zostawienie nie kosztuje nic,
bo i tak była ignorowana.

Świadomie własność **arkusza**, nie selektora: policzenie, do których elementów
sięga selektor, wymaga rozwiązania kaskady przez wszystkie dokumenty, a odpowiedź
i tak byłaby nieprawdziwa w chwili, gdy dołączy drugi arkusz albo atrybut
`style`. Arkusz bez kursywy w ogóle nie może wytworzyć złego przypadku,
cokolwiek kaskada zrobi — to jest słabsze pytanie, za którym ten program potrafi
stanąć.

### Słownik jedzie z instalatorem — druga połowa

WP-10, część pakująca. Pierwsza połowa nauczyła detektor pytać słownik; ta
sprawia, że **jest kogo pytać** na maszynie, na której nikt niczego nie
instalował ręcznie.

`pl_PL` i `en_US` pobierane przy budowaniu wydania i **przypięte sumą SHA-256**,
tą samą regułą co EPUBCheck i Chromium (EF-017, D-018): nic nie jedzie
w instalatorze, czego to wydanie nie zmierzyło. Angielski dlatego, że program
mówi po angielsku i druga półka to 67 książek nl/en.

Jedna świadoma asymetria wobec EPUBCheck i silnika, bo czyta się jak przeoczenie:
**brak słownika nie zatrzymuje budowania**, zła suma zatrzymuje. Słownik jest
drugą opinią jednego detektora, a odmowa wydania z powodu chwilowo
nieosiągalnego pliku wymieniałaby małą stratę dowodu na całkowitą stratę
wydania. Zła suma to co innego — to nie jest brak dowodu, to jest dowód, którego
nikt nie sprawdził.

Raport mówi teraz wprost, kiedy zabrakło słownika (`hyphens.no-dictionary`),
i mówi to **przed** liczbami i niezależnie od tego, czy coś znalazł: przebieg
bez słownika widział mniej niż przebieg ze słownikiem, a raport, który tego nie
napisze, pozwala słabszej odpowiedzi wyglądać na czystą książkę.

**Przy okazji, i to jest właściwa treść tej pozycji:** ta sama reguła
natychmiast wsiąkła do sygnatur korpusu i przesunęła jedną książkę — bo
`hyphens.no-dictionary` jest prawdą o *maszynie*, nie o książce. To jest błąd
WP-12 postawiony na głowie: wtedy sygnatury dawały się odtworzyć wyłącznie tam,
gdzie była Java, teraz dawałyby się odtworzyć wyłącznie tam, gdzie **nie ma**
słownika. Dlatego filtr przestał być literałem `epubcheck.` w dwóch miejscach
i został nazwany — `corpus.describes_the_machine` — a test pilnuje kategorii,
nie pojedynczej reguły. Sygnatury nie były przepisywane: po naprawie zgadzają
się co do bajtu ze stanem sprzed słownika, bo żadna książka się nie zmieniła.

### K1 wreszcie stoi w bramie, która decyduje o zapisie

WP-11. Dwie połowy jednego ustalenia, i druga jest ta, która boli.

**Liczba nigdy nie była liczona.** `balance.Side.text_characters` było
deklarowane, zapisywane do każdego raportu i **nigdy nie przypisywane** — pole,
które mówi, ile tekstu weszło i ile wyszło, odpowiadało zerem od dnia, w którym
je napisano.

**Kontrola nigdy nie stała w bramie.** `fidelity.text_survives` istniało
i było osiągalne wyłącznie z osobnej komendy i z korpusu. Więc brama publikacji
— rzecz, która decyduje, czy czyjaś książka trafi na dysk — pytała EPUBCheck,
czy plik jest poprawny, pytała renderer, czy strony wyglądają tak samo, i **nie
pytała, czy tekst jeszcze tam jest**. Książka może stracić akapit i być
bezbłędnie poprawna; może stracić akapit i narysować się prawie tak samo, bo
strona, która go straciła, nie musi być wśród próbkowanych.

Odtworzone: wstrzyknięty etap kasujący jeden akapit bez słowa w rejestrze —
książka wychodziła, bilans się zamykał, status `SUCCEEDED`.

**Trzy rzeczy wyszły dopiero przy podłączaniu tego do bramy**, i każda zmieniła
naprawę:

1. `text_survives` porównuje **zbiory słów**. To jest uczciwy pomiar po fakcie
   i zła brama: rozwinięcie `<span>` łączy dwie połówki słowa w jedno, więc
   słowo znika, choć każdy znak leży dokładnie tam, gdzie leżał. Dwadzieścia
   dwa testy powiedziały to w minutę. Brama używa więc reguły z korpusu —
   podciąg znaków — czyli tej, która chodzi po stu sześćdziesięciu prawdziwych
   książkach.
2. Etap typograficzny **celowo podmienia znaki** (trzy kropki na wielokropek,
   cudzysłowy na konwencję książki). Porównanie idzie więc przez
   `typography.canonical` — fold, którym ten program już się posługuje, żeby
   ocenić, czy reguła typograficzna zachowała tekst. Litery, cyfry, znaczące
   znaki interpunkcyjne i granice słów się nie składają, więc zgubione słowo
   nadal przepada.
3. **Strata, o którą poprosiłeś, to nie jest strata.** Usunięcie znaku wodnego
   i złączenie przeciętego słowa zabierają znaki; zebranie znacznika do głowy
   dokumentu przestawia je. Wszystkie cztery dzieją się po Twojej zgodzie
   i wszystkie są w rejestrze — więc brama je **nazywa**, a nie odrzuca. To ta
   sama zasada, na której stoi bilans.

Liczenie znaków idzie wyrażeniem regularnym, nie parsowaniem — parsowanie tutaj
obciąża budżet dokumentu po raz drugi, a `BudgetExceeded` jest `BaseException`,
więc książka z głęboko zagnieżdżonym znacznikiem przestawała być odrzucana przez
etap, który ma ją odrzucać, i wybuchała w liczniku do raportu. **Liczba w
raporcie nie ma prawa decydować, czy książka się przebuduje.**

**Zmierzony koszt na Książce 2** (65 dokumentów, 683 703 znaki): 1,87 s → 2,20 s,
czyli **+17,2%** przy dopuszczalnych 20%. Znaki przed = po, co do jednego.

Kontrola jest przełącznikiem w oknie, jak każda inna.


### Żaden test nie pada dlatego, że maszyna nie ma Javy

WP-12. Zmierzone przed zmianą: przy `EPUBCHECK_JAR` wskazującym w próżnię i bez
cache'u pięć zwykłych plików testowych dawało **28 porażek i 4 błędy** — żaden
z nich nie był o EPUBCheck-u. Tryb ścisły prosi o bramkę `clean`, bramka
odpowiada „walidatora, którego ta bramka potrzebuje, nie ma", książka się nie
publikuje, a test, który chciał przebudowanej książki, nie dostaje jej. Wszystko
poprawne i nic z tego nie jest tematem tamtych testów.

**Neutralizacja, nie emulacja** — inaczej niż przy silniku rysującym, i to jest
wybór, nie przeoczenie. Silnik zastępuje się *odpowiedzią* („obie strony rysują
się tak samo"), bo to jest przypadek zwykły. Tutaj nie ma odpowiednika: „EPUBCheck
mówi, że ta książka jest poprawna" nie jest domyślną, tylko werdyktem, po który
bramka istnieje. Twierdzenie go na maszynie, która nigdy nie zapytała, sprawiłoby,
że każdy test publikacji przechodzi z powodu niemającego nic wspólnego z książką.
Więc bramka jest **wyłączana** dla testów, które nie są o niej — co jest uczciwe,
bo nikt niczego nie zwalidował — a pliki, które są o walidacji, dostają ją z
powrotem i pomijają się same.

Przy okazji wyszło, że **sygnatury korpusu były zależne od maszyny**: zapisywały
reguły `epubcheck.*` i liczyły je w sumach poziomów, więc przebieg bez Javy
raportował trzynaście książek na trzynaście jako zmienione, choć żadna książka
się nie zmieniła. Werdykt EPUBCheck-a jest zapisywany osobno i zostaje;
z sygnatury rebuildu wyszedł. Pole, którego ten przebieg nie umiał zmierzyć,
mówi teraz o tym wprost, zamiast udawać różnicę.

**Wynik:** bez Javy i bez silnika **2370 przechodzi, 141 pominiętych, zero
porażek**; w pełnym środowisku 2465 przechodzi, 46 pominiętych.


### Każdy identyfikator wychodzi ze schematem, z którym wszedł

WP-9. Trzy defekty w jednym kawałku writera, widoczne dopiero na książce, która
niesie **więcej niż jeden** identyfikator — czyli nigdy na fixture'ach, bo każdy
miał jeden.

**`identifier-type` tylko dla identyfikatora głównego.** ISBN zadeklarowany jako
`opf:scheme="ISBN"` wychodził jako goły `dc:identifier`: numer przeżywał,
stwierdzenie, że *to jest ISBN*, nie. Teraz pisane dla każdego, który deklaruje
schemat.

**Dwa numerowania jednej rzeczy.** Elementy numerowane po identyfikatorach
*niegłównych*, mapa identyfikatorów po *wszystkich* — więc trzeci element
wychodził jako `id-1`, a refinement celujący w niego mówił `id-2`. Refinement
bez celu to nie jest zachowane stwierdzenie, to jest niepoprawne. Zostało jedno
numerowanie.

**`Identifier` nie miał pola `source_id`,** a writer pytał o nie przez
`getattr(identifier, "source_id", None)` — co odpowiada `None` na zawsze i
czyta się jak ostrożność. Więc żadnego refinementu przy identyfikatorze nie dało
się przekierować: `<meta refines="#sklep" property="display-seq">` przy
identyfikatorze sklepowym był raportowany jako *wskazujący węzeł, który nie
przetrwał* i **kasowany, na każdej książce, która go miała**.

**`file-as` i `role` w rejestrze zmian.** Gdy źródło ich nie podało, uzupełnia je
ten program — i to jest jego twierdzenie o książce, nie twierdzenie książki o
sobie. Domyślne są dobre i zostają; nowe jest to, że wychodzą jako `ADDED`
w rejestrze, więc porównując dwa pakiety da się odróżnić jedno od drugiego.

Zmierzone na korpusie publicznym: jedna książka zmieniła wynik i zmiana jest
czystym zyskiem — doszedł `identifier-type` przy ISBN-ie, nic nie ubyło, zero
refinementów bez celu.


### Okładka rozpoznawana po manifeście, i reguła, która wreszcie działa

WP-8. Trzy ustalenia, które okazały się jednym błędem popełnionym w dwóch
miejscach: okładka była rozpoznawana po ścieżce, która zdążyła się zmienić,
i naprawiana regułą, która nie mogła zadziałać.

**EF-024.** `_cover_fits_the_page` rozwiązywał każdy `<img src>` względem
*pierwotnej* ścieżki dokumentu — w miejscu potoku, w którym `src` jest już
przepisany na nową. Powstawała ścieżka, która niczego nie nazywa; `path_map`
odpowiadał `None` dla niej i `None` dla okładki; `None != None` jest fałszem;
i warunek mający trzymać regułę okładki na okładce przepuszczał wszystko.
Zmierzone na *Pan Tadeusz*: okładka z manifestu nie występuje w żadnym
dokumencie tej książki, a regułę dostawało **dziewięć ilustracji**.
Pytanie zadaje teraz manifest — a manifest nie przesuwa się razem z plikami.

**EF-026.** To, co dokładał, to `max-width: 100%; max-height: 100%` inline.
Druga z tych deklaracji jest procentem, a procentowa wysokość rozwiązuje się
względem bloku zawierającego — bez wysokości na `html` i `body` nie ma do czego
jej odnieść. Reguła trzymająca wysoką okładkę na jednej stronie była martwa
dokładnie tam, gdzie była potrzebna. Strona okładki, którą program **generuje**,
miała tę wysokość od zawsze: dwie drogi do jednego efektu i jedna z nich nie
prowadziła nigdzie. Teraz obie biorą te same trzy reguły z `epubforge/covers.py`.

**EF-034.** Jeden komunikat opisywał dwa różne fakty: stronę, której wcięcie
przyszło z arkusza, i stronę, która nie linkuje żadnego arkusza i nie miała
wcięcia do usunięcia. Obie dostawały zdanie o usuniętym wcięciu. Teraz są dwa
komunikaty, EN i PL.

**Nowe ostrzeżenie:** `<img width="1472" height="2341">` na okładce jest
raportowane i **zostawiane**. To instrukcja wydawcy; zmiana jest decyzją
o wyglądzie książki, a takich program nie podejmuje sam.

Zmierzone na obu książkach wzorcowych, trzy viewporty (600×800, 758×1024,
1072×1448), przypięty silnik: **zero stron ze stratą**. Grafiki tytułowe
Książki 1 nie dostają już reguły okładki; `body.cover img { max-height: 98% }`
Książki 2 nadal uszanowane.


### The engine, and nothing but the engine

The owner's answer to 0.2.27 was that I had half-done what he asked: *mamy
WBUDOWANE Chromium, na cholerę nam w ogóle „opcjonalny" Edge.* He is right.
Demoting `EPUBFORGE_CHROME` left the whole apparatus standing — the `PATH`
search, the Program Files paths, Playwright's download directory, and an
override that could put any of them back in front of the engine we ship.

All of it is gone. Every one of those paths existed for a single reason, that
this program had no engine of its own, and that reason ended when 0.2.26 put
one in the installer. What they bought in the meantime was an answer that
depended on the desk the program was standing on.

One door is left, and only one: a build that carries **no** engine — a
checkout, a `pip` install, this project's own render tests — reads
`EPUBFORGE_CHROME`. It cannot apply to a release, because a release always
carries one.

### Attributes an element was never allowed to carry

Seven shapes of `RSC-005` survived a `preserve` rebuild on the second shelf —
errors *this program produced*, in books that arrived without them. Two were
attributes nobody ever defined (`font17`, `p`: an exporter writing its own
bookkeeping into the markup); the rest were legacy attributes on elements that
never took them (`clear` on a `<p>`, `size` on a `<span>`, `link` on a `<div>`).

Naming them one by one would have fixed those seven and left the next seven, so
the rule runs the other way: **an attribute an element is not allowed to carry
is one no engine reads.** That is what makes removing it safe, and it is also
why leaving it is an error rather than a quirk. Where the attribute still meant
something to a page it is translated into CSS first — `clear` becomes
`clear: both`, `<hr size="3">` becomes a height — so the appearance survives the
removal. Anything with a vocabulary of its own is not touched: `data-`, `aria-`,
`epub:`, RDFa, and every element outside the XHTML namespace.

That last exemption is not theoretical. The first version had no namespace rule
and stripped `viewBox` off an `<svg>`, which is a drawing losing its coordinate
system. The suite caught it in one run.

Two more shapes from the same shelf, both fixed by putting the content where
the reader was already seeing it: a link loose inside a `<table>` but not in a
cell is lifted out in front of the table (which is where every HTML parser has
foster-parented it for twenty years), and flow content that landed in `<head>`
moves to the top of `<body>` (where a browser has always started it). Measured
on a synthetic book carrying all of them: **12 EPUBCheck errors in, 1 out** —
and the one left is the fixture's own missing image.


## 0.2.27 — alpha — 2026-08-16

Both defects the owner reported on 0.2.26, and a false alarm his corpus run
found that neither of us was looking for.

### At a glance

| what it was | the scale of it |
| --- | --- |
| A black console window flashing about once a second while a batch ran | one per screenshot; the flags to prevent it existed and lived in the wrong module |
| `EPUBFORGE_CHROME` still starting Edge, months after the reason for setting it | a variable set once outranked the engine the release ships and measured against |
| Edge was still being searched for | it disagreed with Chromium about 3 of 4 damage shapes and reports no version at all |
| The balance reported a lost metadata entry on 21 of 93 books | none of them had lost anything; a second `<dc:title>` moves to `subtitle` and both are written |
| The balance's metadata arm read a field the model does not have | so the vocabulary loss it was written to catch could have happened again in silence |
| EPUBCheck ran twice on the same bytes in strict mode | ~4.5 s a book, and `epubcheck.clean` printed twice in every report |

### The console window

A frozen GUI application on Windows has no console of its own. Every child
process it starts therefore *gets* one: Windows creates a console window for
the child, on top of whatever the person was looking at, for as long as the
child runs. For the validator that was one window per book, and it was fixed
where it was found, inside `validate`, in 0.2.14. For the renderer it is one
window per **screenshot** — which the owner watched flash roughly once a second
for as long as a batch ran, and described exactly right: distracting, and
suspicious to anybody standing near the screen.

The flags were already written and already correct. They were written in the
module where the problem was first noticed, and `render` was written afterwards
by somebody — me — who did not know to look for them. So they now live in
`epubforge/spawn.py`, every child process in the package goes through it, and a
test reads the whole package to make sure the third module to spawn something
cannot repeat this.

### Which engine draws, and who is told

His words: *"nie posprzątałeś kodu po syfie z Edge i aplikacja wciąż otwiera mi
Edge przez zmienną EPUBFORGE_CHROME"*. He was right, and the order was mine.

`EPUBFORGE_CHROME` came first on the reasoning that somebody who names an
engine has said which one they mean. What that missed is that an environment
variable is not somebody saying something *now*. It is somebody having said it
once — in his case for a build that carried no engine at all, because there was
nothing else to point it at — and it keeps applying long after the reason has
gone. Nothing on the screen said it was still in force.

So from this release **the carried engine wins**. Not because Edge is bad, but
because a comparison of two renderings is a statement about the *book* only if
both were drawn by the same engine, and the carried one is the only engine that
is identical on every machine this ships to. It is pinned by digest, it is what
this release's numbers were measured against, and it has no window code
compiled into it.

The variable is not ignored:

- where nothing is carried — a checkout, a `pip` install, this project's own
  render tests — it wins exactly as it always did;
- where something is carried and the variable disagrees, the carried engine
  draws and both the window and the console **say so**, naming the path that
  was passed over;
- `EPUBFORGE_CHROME_OVERRIDE=1` alongside it restores the old order, which is a
  sentence nobody types by accident.

And the clearing-up he asked for: **Edge is no longer searched for at all.** Not
tidiness — measurement. On the same four kinds of damage it disagreed with
Chromium about three, and it reports no version string, which also defeats the
check that two runs are comparable at all. An engine that answers differently is
not a fallback; it is a second opinion quietly replacing the first.

### A quarter of his library told it had lost something

The 0.2.26 corpus run reported `package.balance-unexplained` on 21 of 93 books,
and on 3 of the 67 in the second collection. All 24 validate clean, keep every
character of their text, and had lost nothing whatsoever.

Every one of them is an EPUB 2 whose package carries two `<dc:title>` elements.
The reader keeps the first as the title and moves the second into `subtitle`;
the writer emits both, with their `title-type` refinements, and EPUBCheck
accepts the result. The balance counted `titles` and not `subtitle`, watched two
become one, and called it a loss.

A false alarm at that rate is worse than no check: it teaches whoever reads the
report to skip past the one line that means something. That is the second time
this has happened — 0.2.25's was the legacy NCX — and the class of it is the
same both times: a counter that models the file rather than the model.

While fixing it, a worse thing turned up underneath. The counter also read
`metadata.extra`, which **does not exist**. The model spells that vocabulary
`extra_meta`, `extra_properties`, `extra_refinements` and `dublin_core_extra`;
`getattr` with a default turned the mistake into a quiet zero. So the balance's
metadata arm was counting four fields out of twenty-nine, while its own
docstring said it existed to catch F-011 — *a whole vocabulary vanishing while
the title stays put* — which is exactly the loss it could not have seen. It now
counts every field of `Metadata`, and a test holds the two lists to the model so
that a field added later is either counted or named as bookkeeping.

### Asked once

In strict mode the publication gate validates the staging file one line before
`os.replace` renames it into place. The window's *check the result* pass then
validated the same archive under its final name: same bytes, one name apart,
about four and a half seconds of JVM to be told a second time — and
`epubcheck.clean` written into the report twice. The gate now records the
verdict it got, and both callers that would have asked again look at it first.

### What the corpus run says otherwise

The rest of it is the 0.2.24 → 0.2.26 work landing, measured on the 67-book
collection: EPUBCheck errors 19 → 14, carried defects 122 → 117, books strict
mode refused to publish 14 → 10. `RSC-011` (8 occurrences) and `RSC-007` (1)
are gone entirely. Four books that strict refused now publish clean.

What has not moved is the count of errors this program **introduces**: 3, the
same as 0.2.24. They are all one family — presentational and junk attributes
(`clear`, `align`, `valign`, `size`, and two that are simply not attributes:
`font17`, `p`) and misplaced elements (`<a>` directly inside `<table>`, `<p>`
inside `<head>`) — surviving a rebuild into a document where EPUB 3 does not
allow them. That is the next work package rather than a note; it needs the
owner's ruling on which of them are the publisher's decisions and which are a
converter's debris, because removing the first kind changes how a page looks.

## 0.2.26 — alpha — 2026-08-16

Two defects from the owner's first batch on 0.2.25, and the renderer he was
right to ask about.

### At a glance

| what it was | the scale of it |
| --- | --- |
| The balance reported an error about a removal he had asked for | both books refused; `omit the legacy NCX` is a setting, not a loss |
| `WinError 145` while deleting a temporary directory | arrived in the report as "the rebuilt book could not be written" |
| An Edge window opening and displaying nothing | `--headless` is the deprecated spelling; recent builds start normally |
| The appearance check measured whichever browser the machine had | Edge disagreed with Chromium about 3 of 4 damage shapes and reported no version |
| The installer now carries `chrome-headless-shell` | pinned by SHA-256; +112 MB, and it has no window to open |

### New / fixed

**New:** the installer bundles its own headless rendering engine, pinned and
verified exactly as EPUBCheck is. **Fixed:** a false alarm in the input→output
balance that refused books over a setting the owner had chosen, and a Windows
crash during temporary-directory cleanup that turned into a lost rebuild.

### Everything, by subject

#### Both defects came in through the same door

0.2.25 fixed browser discovery on Windows. That switched on a code path which
had **never once run there** — Edge was never found before — and the owner's
first batch hit two defects in it at once. Neither was in the render code
itself; both were in what the render path touches.

**The balance cried wolf.** With *omit the legacy NCX* ticked — his setting,
his choice — the source's `toc.ncx` left the book, the balance saw one resource
fewer in `other` with nothing accounting for it, and reported an error. Both
books refused, over a removal he had asked for.

A false alarm from a check like this is worse than no check. It teaches the
person reading the report to skip past the one message that means something, and
this program's entire claim is that its messages mean something. The removal is
now in the change ledger where the balance can see it, and rewriting the NCX
under a new name is recorded as a move rather than a loss.

**`WinError 145` took the book with it.** *Katalog nie jest pusty*, raised while
deleting a temporary directory, arrived in the report as *"the rebuilt book
could not be written"*. Windows will not remove a directory while anything still
holds a handle inside it — a browser that has just exited, an indexer, a virus
scanner — and none of those is a reason for somebody to lose their book. The
three temporary directories in that path now tolerate a failed cleanup.

#### The window that opened and showed nothing

He watched Edge open a blank window during a rebuild and said, correctly, that
most people would find that suspicious in itself. It is not cosmetic: it is a
program doing something on somebody's screen that looks like it should not be
happening, in a tool asking to be trusted with a library.

The cause is a flag. `--headless` is the deprecated spelling and recent Chrome
and Edge builds no longer honour it that way — the browser simply starts
normally. It is `--headless=new` now.

#### And then the better question: why not carry our own?

That was his, and it is a better answer than the one this had been working
towards. Since 0.2.24 the program treated "no browser" as a situation to be
handled — ask, consent, refuse — and the situation was avoidable. The licence
(BSD-3-Clause) permits redistribution, and he had checked that before asking.

So the installer now carries **`chrome-headless-shell`**, which is not Chrome:
it is the headless-only build, with no browser interface compiled into it. It
*cannot* open a window. That is a property of the binary rather than a promise
about a flag, which is a stronger thing to be able to say.

It also settles a defect this release had hit three times in three costumes.
The appearance check compares two renderings; run against whatever browser a
machine happens to have, it measures the browser. On the Windows runner, Edge
disagreed with Chromium about **three of the four damage shapes** the check
exists to catch, reported an empty version string, and took the test suite from
200 seconds to 961. A check whose answer depends on the reader's machine is not
a check. A pinned engine is, and it is what the audit asked for by name.

Pinned and verified the same way EPUBCheck is, for the same reason: the archive
by SHA-256 and size before unpacking, the executable by SHA-256 after. The
provenance is stated as weaker than EPUBCheck's rather than dressed up —
Chrome for Testing publishes no signature and no digest sidecar, so the
corroboration available is Google Cloud Storage's own `x-goog-hash` for the
object, computed by the storage layer rather than by whoever uploaded it, and it
matches the bytes that arrived.

**The cost is the installer: about 112 MB more.** He was shown that number
before choosing, along with the alternative of fetching it on first use the way
EPUBCheck does, and chose to have it in the box.

Your own browser still wins if you name one in `EPUBFORGE_CHROME`. The order is
the environment variable, then what we shipped, then what is installed — the
first because somebody who names an engine has said which one they mean, the
second because otherwise the numbers in a report are about somebody else's Edge.

The smoke test no longer passes `--accept-unverified-render`. It cannot: the
whole point of this release is that the check runs from the bundle, and if it
does not, the build carries 112 MB nothing can reach. The right time to find
that out is in the build.


## 0.2.25 — alpha — 2026-08-16

The release that came out of pointing the program at the owner's own library and
reading what it said, rather than at what the suite said about it.

### At a glance

| what it was | the scale of it |
| --- | --- |
| `preserve` adding EPUBCheck errors the source did not have | 12 error shapes across 10 of a 67-book collection, with the suite green throughout |
| The generated navigation linking outside the reading order | 4 books, all with the cover in `<guide>` and never in the spine — legal EPUB 2, invalid EPUB 3 |
| `<col>` carried straight under `<table>` | legal in XHTML 1.1, an error in XHTML5, and the rebuild is what moved it |
| An image renamed under a document that was promised not to be touched | container-only mode, where the two promises collide |
| A removal with no ledger entry | orphan sweeping deleted a file on a finding alone — found by the new balance within a minute of it existing |
| Nothing measured what went in against what came out | now a balance across resources, spine and metadata, with a loss nothing explains an error |
| 189 hyphen candidates with no evidence either way | one question per class carrying the words, instead of 189 questions |
| The supply-chain smoke test had never actually run | 33.1 MB fetched, pin verified, in 1.2 s |

### New / fixed

**New:** an input→output balance that refuses to let a resource disappear
without a ledger entry, a grouped review for hyphen candidates the book itself
does not settle, and `Policy.for_measurement()` for the three paths that rebuild
into a temporary directory and delete the result. **Fixed:** three ways a rebuild
turned a conforming EPUB 2 into a non-conforming EPUB 3, all three found in the
owner's corpus data rather than in the test suite.

### Everything, by subject

#### Three defects the corpus found and the suite could not

The owner supplied two corpus runs — 93 books from his library and 67 from a
separate collection, each rebuilt in all three modes with EPUBCheck on the source
and on every output. His own summary carried one line worth chasing:

    1 EPUBCheck error(s) in modes that rewrite content

On the 93 that was a defect carried from the source. On the 67 it was twelve
error shapes across ten books that the sources did not have — and the suite was
green the whole time, because the invariant "no mode adds an error" was asserted
on **one fixture**. That is the difference between a claim and a measurement.

The books themselves are not mine to have, only the error shapes. The shapes
turned out to be precise enough: each was rebuilt as a fixture, and each was then
asked the only question that matters — *does this program introduce the error, or
does it carry markup that EPUB 2 tolerated and EPUB 3 does not?* Five of six were
carried, one of those five the program already repairs, and three were ours.

**`RSC-011`: the navigation pointing outside the reading order.** Four books,
and all four had the same shape: an EPUB 2 whose cover page sits in the manifest
and in `<guide>` and deliberately **not** in the spine. That is ordinary and
legal there. EPUB 3 does not allow a navigation document to link to anything
outside the spine, so the generated nav turned a conforming book into an invalid
one.

The mechanism to handle this already existed — a target outside the spine is
added back as `linear="no"`, which is exactly what that attribute is for, and
inserted where the contents put it rather than appended. It walked the table of
contents alone. Landmarks and the page list are navigation too, and EPUBCheck
does not distinguish: all three end up in the same document. So the fix is one
line of input, not a second mechanism standing beside the first.

**`RSC-005`: `<col>` directly under `<table>`.** XHTML 1.1 allows it; XHTML5,
which is what an EPUB 3 content document is, requires it inside a `<colgroup>`.
The source validated, the output did not, and the version upgrade is what moved
it — so it is ours to repair. Consecutive `col` elements move together into one
group, which is what they meant, and the column widths apply exactly as before.

**`RSC-007`: an image renamed under a document promised not to be touched.** An
image whose bytes were PNG and whose name and manifest entry said JPEG was
renamed to match — in container-only mode, whose entire promise is that content
documents come out byte for byte. A document saying `src="cover.jpg"` cannot be
left untouched *and* have its target renamed. One of the two promises has to
give, and it is not going to be the one that mode exists for. The manifest is
this program's to write, so the declared type is still corrected there; only the
file keeps its name.

**The invariant moved to where it can fail.** Every book of the public corpus,
every mode, EPUBCheck on the source and on each output, compared by error
*shape* rather than count — a rebuild that removes one error and adds a different
one leaves the count alone. A corpus book carrying both repairable shapes went in
with it, and the test was then checked the only way a test can be: by reverting
each fix separately and watching it fail.

One asymmetry is written into it rather than smoothed over. The container-only
mode is judged on what it writes and nothing else, because an EPUB 2 document
carrying markup XHTML5 rejects comes out still carrying it — by that mode's own
promise — and holding it to the same rule as the modes that rewrite documents
would be demanding that it break that promise.

#### The balance: what went in against what came out

BA-2026-003 asked for a machine-readable account of every high-risk change, and
0.2.24 delivered a ledger. A ledger answers *what did this rebuild do*. It cannot
answer *did anything go missing*, because reading it for that means trusting
every removal to have written itself down — which is trusting the thing under
suspicion.

The balance runs the other way. It counts the source, counts what is about to be
written, and requires every category that shrank to be explained by an entry in
the ledger. Documents, images, fonts, stylesheets, other resources, spine items,
metadata entries. A resource that vanishes with nothing accounting for it stops
being a quiet omission and becomes a failed reconciliation, reported as an error
and carried in the JSON. Report schema 3 → 4.

It found a real one within a minute of existing: **sweeping orphans deleted a
file on the strength of a finding alone**, with no ledger entry. That switch is
off by default precisely because the reachability graph behind it is knowingly
incomplete, which makes it exactly the kind of removal the ledger is for.

What it deliberately does not do is balance every element of every document. A
rebuild rewrites markup by design, and a count of `<div>`s in against `<div>`s
out would fail on every book while saying nothing about whether a reader lost
anything.

The test that matters is the one that injects a stage which drops an
**unreferenced image**. A dropped document is already caught by K1, which sees
the characters go; a dropped *referenced* image is caught by the invariant gate,
which sees the dangling reference. An unreferenced image trips neither: no text
goes, nothing dangles, the book validates. It is the quietest possible loss,
which makes it the right one to hold a balance to — and it is the owner's own
rule, twice stated, that losing an ornament is damage to the book too.

#### One question instead of a hundred and eighty-nine

BA-2026-001's remaining half. The detector asks about a hyphenated word when the
book itself settles it — writes the same word without a hyphen somewhere else.
Measured across 32 books: 67 like that, against 101 "likely" and 88 "uncertain",
and reading those two lists nearly every entry is a real compound —
`marksizm-leninizm`, `savoir-vivre`, `ping-pong`.

Asking about all 189 is a queue nobody finishes, and that over-eagerness is what
the finding warned about. Dropping them silently is the other failure: some of
them are real breaks. So the weaker classes are now one question apiece, carrying
the words themselves — because "101 words might be broken" is not something a
person can answer and "these 101 words" is. `confirmed` remains the default and
behaves exactly as 0.2.24 did; `each` goes through them one at a time for
somebody who wants to.

#### A regression the owner's data caught before he did

0.2.24 made a missing browser mean "do not write" under the default gate. His
corpus run reported `render.cannot-run` on all 93 books, because his machine has
no browser — and the survey, the fidelity harness and `render-check` all rebuild
a book into a temporary directory to measure it and then delete it.

A survey of his library would have come back as 93 refusals and no measurements.
A tool that refuses to look at a library because it cannot verify an output it is
about to delete is a tool nobody can run. `Policy.for_measurement()` names that
situation once — gates off, output discarded — instead of the same four overrides
copied into four places, which is how many copies of a rule there should never
be.

#### The supply chain, actually exercised

The EPUBCheck download test has existed since 0.2.24 behind
`EPUBFORGE_NETWORK_TESTS=1` and had never been run. It has now: **33.1 MB from
the official release URL in 1.2 s, matching the pinned SHA-256 and size**, and
the corroborating comparison against Maven Central's signed jar passes entry by
entry. A pin nobody has ever checked against the thing it pins is a comment.

#### Benchmarks, on three sizes

| book | time | peak RSS | resident afterwards |
| --- | ---: | ---: | ---: |
| small synthetic | 0.0 s | 36 MiB | 36 MiB |
| 1.6 MB purchased | 0.8 s | 48 MiB | 45 MiB |
| 2.6 MB purchased | 1.8 s | 61 MiB | 56 MiB |
| 108 MB of text, 601 documents | 39.2 s | 547 MiB | 142 MiB |

The last column is `memory.release()` from 0.2.24 doing its job: without it that
row ends at 462 MiB resident, none of which is live objects.


## 0.2.24 — alpha — 2026-08-15 — kamień milowy [WP-1] [WP-2] [WP-3]

An external audit read this program on 2026-08-14 and left fifteen findings
grouped into three work packages; this release is all fifteen of them, and the
several that turned out to be the same mistake made in different places.

### At a glance

| what it was | the scale of it |
| --- | --- |
| A budget with its own test file and zero callers | depth limit 10, document 80 levels deep, calls made: none, book published |
| A deadline asked only *before* each stage | limit 0.05 s, stage 0.20 s, book published |
| A book published after part of the archive was never read | every loss refuses now; the owner's decision, and there is no switch |
| Metadata deleted by prefix | three entire vocabularies — `schema:`, `rendition:`, `media:` |
| Tag-soup recovery reported as though it were a reading | `<dc:title>ORIGINAL<dc:language>pl</dc:title>` → a title of `ORIGINALpl`, language gone, not one word in the report |
| The validator was downloaded and taken on trust | 33 MB over the network, no checksum, `extractall` |
| A misdirected reference read as a dead one | the file is in the book, one directory over |
| `srcset` was never in the reference graph | every candidate but the first was invisible to the rebuild |
| A ceiling in the wrong unit | 2 GiB of *content* promised a 24 GB process; the largest book went 2042 → 700 MiB |
| Nothing could ask a question and remember the answer | one queue, three kinds of question, answers kept beside the book |
| Hyphens a conversion left inside words | 67 confirmed across 32 books, 46 of them in a single one |
| Nothing checked that the rebuilt page still looks like itself | two screenshots per document at two sizes; 0 refusals on 32 real books, 4 of 4 deliberate breakages caught |
| Two tests asked the machine they ran on rather than the program | ZIP timestamps, and a font classifier measured only on host fonts |
| Nothing stopped a rule about one particular book from being written | now an AST test over the whole package |

### New / fixed

**New:** a health check and a two-copy merge for books the rebuild refuses, a
change ledger that can be totalled rather than read, a decision queue with
remembered answers, a hard-hyphen detector, a memory estimate that refuses
before it allocates, and a render-fidelity gate that compares the drawn page.
**Fixed:** every boundary in the audit's first two packages — budgets,
deadlines, incomplete archives, metadata loss, recovery reported as fact, an
unverified validator, and two classes of reference the rebuild could not see.

### Everything, by subject

#### The limits that were written but never wired in

Three P0 findings, all three reproduced here in a full environment before any
code was touched, and all three reproduced.

**`Budget.document` had a test file and no callers.** The reproduction is one
line: a depth limit of 10, a document 80 levels deep, zero calls made, and the
book published. The test proved the limit worked; nothing proved it was used.
The check now sits in `reader.parse_xml` and `xhtml.parse_document` — every
parse in the program goes through one of the two — and it reads the active
budget from a `ContextVar` rather than from a passed argument, because the
version with an argument is precisely what produced a limit with no callers.

Wiring it in exposed the second half: the stage caught the refusal with
`except Exception`, reported `xhtml.unparseable`, and published the book. The
limit worked perfectly and the output came out anyway, filed under a finding
about something else entirely. `BudgetExceeded` now derives from
`BaseException`, like `KeyboardInterrupt`. A limit any local `except` can
swallow is not a limit.

**The deadline was asked only before each stage** — that is, it measured
everything except the part that takes time. Limit 0.05 s, stage 0.20 s, book
published. There is a checkpoint after every stage and one before publication.

**A book is no longer published when part of the archive was never read.**
`allow_incomplete` is gone rather than defaulted off. The first proposal kept
the switch for losses that are "only decorative"; the owner rejected it with a
sentence better than the proposal — losing an ornament is damage to the book
too, and contradicts what this program is for. What replaces the switch is a
report that says what the lost file was, whether the book's own manifest listed
it, and how many documents point at it.

Found on the way: `Policy.preset` silently accepted the name of a field that
does not exist, so a typo in a setting name did nothing and told nobody.

#### Metadata that vanished, and a guess presented as a reading

**F-011 was two lines in the writer.** The first, `startswith("calibre:")`,
removed only what nothing else carried — the two Calibre entries this model
understands are consumed into fields by the reader and never reach it. The
second, `startswith(("schema:", "rendition:", "media:"))`, meant "do not write
`schema:accessMode` twice" and did "delete three entire vocabularies whether or
not this rebuild had anything to say about them".

The fix is not a longer list. The writer now reads back the `<meta>` lines it
has already emitted and skips only what it actually said; a hand-maintained
list of "properties we generate" is a second copy of the emitters, and it was
the copy that drifted. A skip now carries its own finding, because silence and
a decision look identical in the output.

**F-004: `recover=True` accepted a package with interleaved tags,** turned
`<dc:title>ORIGINAL<dc:language>pl</dc:language></dc:title>` into a title of
`ORIGINALpl`, lost the language, and published the book without a word in the
report. That is not a repair; that is libxml2's opinion about somebody's book
promoted to a fact.

The strict parser is asked first, so "the file says" and "the parser guessed"
have stopped being the same answer. The owner's decision was neither to refuse
nor to publish quietly, but to show the difference and offer a correction: the
report names the fields that came out of a guess — exactly the ones the window
and the command line already let you override — and the status stops being a
clean success.

#### A ledger that can be totalled

The report said a great deal about *why* and almost nothing about *what* in a
form anything could add up. "4 of 10 rules removed — 17% of this stylesheet" is
a good sentence, and it is a sentence: nothing can ask it how many removals
there were in total, how many are irreversible, and how many were a heuristic
rather than a calculation. Those are the questions you ask before running a
batch over your own shelf.

A change is now a record beside the finding that explains it, with a closed
vocabulary: `Action` (removed/replaced/moved/added/carried/reconstructed),
`Automation` (deterministic/heuristic/asked), `Risk` (none/appearance/content),
and `reversible` — whether the output alone carries enough to undo it.

Deliberately **not** every change. A register of every edit is a log, and the
findings are already that log. What goes into the ledger is the set the audit
names — removal, recovery, relocation — because that is where a mistake costs a
reader. A test holds the boundary from the other side: rebuilding a clean book
may not fill the ledger with noise.

Report JSON schema 2 → 3. Two fields added, nothing removed, nothing changed
meaning.

Also here, a test that was missing: the window checked against a **built**
window rather than against its strings. The owner asked whether the new
features were in the window. They were — but what guarded that were tests for
the existence of labels and CLI commands, which is exactly the class of mistake
the audit caught five times.

#### What is left when the rebuild refuses

Two features the owner chose. The rebuild refuses a source it did not read in
full, and there is no switch that turns that off. That is right, and it is not
help; this is the half that helps.

**A health check** answers "is this file whole" by extracting every entry,
because a ZIP's directory sits at the end of the file and an interrupted
download can leave it intact. An archive's claims about itself are exactly what
a truncated copy still has correct. Worth running on the day of purchase, when
downloading again takes a minute.

**A merge** turns two copies damaged in different places into one whole book.
It is the only operation in this program that recovers something rather than
lowering a requirement. Every entry is copied whole, byte for byte, from an
archive that yields it cleanly and with its own CRC. Nothing is reconstructed
and nothing is averaged.

Where two intact copies disagree about the same entry, the merge **refuses**
instead of choosing: two different intact answers mean two different books, or
one book after somebody's edit, and picking one produces a book that neither
copy was.

Human in the loop, as required: the plan is computed and shown in full — which
entry comes from where, what is missing everywhere, where the copies conflict —
and the save button stays disabled until the plan has been seen. An existing
destination is never overwritten: this operation exists because a file was
damaged, so destroying another one on the way would be the same defect.

In the window (Diagnostics, fourth question; File menu, merge) and on the
command line (`epubforge health`, `epubforge merge`).

#### The validator was taken on trust

The build downloaded 33 MB over the network and ran whatever arrived — as the
validator every release is measured with, and, since 0.2.23, as the thing that
decides whether a book may be published at all. Every Python dependency has
been pinned with a hash since 0.2.21. This one artefact, with more power over
the result than any of them, had nothing: no checksum, no size, and
`ZipFile.extractall`, which Python's own documentation warns against.

**What arrives** — a pinned SHA-256 and size, checked whether the archive was
just downloaded or handed over with `--epubcheck-zip`. A local file is not more
trustworthy than a downloaded one, only more convenient, and a build that
verifies one path and not the other verifies nothing that cannot be walked
around.

**Where the numbers come from,** because a pin is worth exactly its provenance.
The archive was fetched on 2026-08-14, which is trust-on-first-use: it detects
substitution from now on and not retroactively. So it was confirmed through a
second, independent channel — `epubcheck.jar` from that archive compared entry
by entry against `org.w3c:epubcheck:5.3.0` from Maven Central, GPG-signed and
served from a different host. **All 746 entries byte-for-byte identical**,
except the manifest: the distribution jar differs from the library one only in
`Class-Path`. The code this build ships is the code from the signed artefact,
checked rather than assumed.

**What comes out** — extraction one entry at a time, rejecting absolute names,
`..`, drive letters, symlinks and duplicates, plus a re-check of the JAR's own
checksum after unpacking. Refusal, not skipping: an archive with an entry that
escapes the directory is not an archive with one bad entry, it is a substituted
archive, and skipping quietly would build a release out of it.

Tests follow the audit's closing criteria — substitution, directory escape,
symlink, duplicate — plus the genuine official artefact, that last one behind
`EPUBFORGE_NETWORK_TESTS=1`, because a test suite that needs the network is a
test suite that fails on a train.

#### A reference in the wrong place is not a dead reference

The owner asked how the program knows an `<a href>` is dead rather than merely
misdirected, when the content is physically there in the book. It did not know.
It was asking the wrong question: strict mode looked for the target at the
address written, and unlinked what it did not find there.

A reference whose target does not exist at the address given, but does exist
elsewhere in the book under that name, is now **relocated** rather than
neutralised — rule `xhtml.reference-relocated` — and only a target that is
nowhere in the book at all is treated as dead.

**EF-021, found by that change and older than it:** `srcset` was never in the
reference graph. The rebuild rewrote the `src` of an `<img>` and left every
candidate in its `srcset` pointing wherever it had pointed before. It was
invisible because strict mode used to delete the whole `<img>` when its `src`
was dead, taking the `srcset` with it; the moment a reference stopped being
deleted, the gallery fixture regressed and said so. `srcset` is parsed as the
list it is — the comma may be inside a URL, so the whole non-space run is the
URL — rewritten candidate by candidate, and only genuinely dead candidates are
dropped.

The signature test also gets back an assertion that had to be suspended for one
release: strict mode publishes that book again.

#### The ceiling that was in the wrong unit

The audit asked for a benchmark before anything was done about memory, and it
was right, because the measurement turned out to answer a different question
from the one everybody was reading.

Peak RSS of a whole rebuild, each in its own process, four purchased books and
two synthetic ones:

| text MB | binaries MB | peak RSS, before | peak RSS, now |
| ---: | ---: | ---: | ---: |
| 1.0 | 0.5 | 52 MB | 45 MB |
| 1.3 | 11.6 | 78 MB | 78 MB |
| 0.2 | 14.9 | 75 MB | 76 MB |
| 0.2 | 23.3 | 88 MB | 88 MB |
| 25.4 | 0.0 | 339 MB | 147 MB |
| 152.1 | 0.0 | 1861 MB | 700 MB |

So the reader's ceiling of 2 GiB of *content* was a promise that the process
may reach twenty-four gigabytes. It was never a memory bound; it was a content
bound nobody had converted. A machine with 2 GiB free dies at around 160 MB of
text, and dies by being killed: no report, no diagnosis, no file, and on
Windows no message anybody can act on.

`epubforge/memory.py` is the conversion. Sizes come from the ZIP central
directory, so a book is measured without being unpacked and a refusal costs
milliseconds — unpacking to find out whether there is room to unpack is exactly
the failure it prevents. The model is deliberately pessimistic; the guard's
margin is 13–35% across the six measured books, and the cost of it being too
careful is one switch.

Checked across the owner's whole shelf: with 15 GiB free, with 2 GiB and with
1 GiB, it refuses none of the 32 books, and the most expensive comes out at
104 MiB. It is a safeguard for a pathological case, not a threshold anybody
will walk into.

**Then the same measurement, by stage, found the 1600 MiB of transient
allocation, and the answer was embarrassingly simple: one mistake made twice.**
The profile stage cost 1681 MiB because it joined the book's entire text into a
single string, and `fingerprint.identify` made a second copy of that and
lowercased both — four copies of the book's text alive at once, for a function
that counts pattern occurrences. It takes an iterable of documents now and
checks them one at a time. That is slightly *more* correct as well: a trace can
no longer span two documents, so a pattern matching across the `\n` that joined
them was matching something no tool ever wrote.

The hyphen stage cost 1345 MiB for the same reason, one day old and mine: a
list of the whole book's texts plus a `Counter` over **every** word. On the
synthetic fixture 80.6% of words were unique — 11.4 million keys — against
17.6% of 103k words in a real book. The fixture was pathological and it pointed
at a real class: a dictionary, a concordance or bad OCR all break the
assumption that real books have small vocabularies. Only the words some
candidate will ask about are counted now — three forms per candidate, and there
are 67 candidates across 32 books. Two passes, both generators; the book's text
is never a list anywhere.

Measured after, the same book: **profile 518 MiB, hyphens 0, peak 700 MiB**
against 2042. Identical answers — same rules, same output; ten shelf books
rebuilt twice give ten byte-identical pairs. The 2 GiB content ceiling now
implies a ~9 GB process instead of ~24 GB: better, and still not a memory
limit.

Two negative results are recorded rather than dropped, because both sounded
reasonable. **Bounding the parse-tree cache does not work.** `Context.parsed()`
holds every parsed tree until the end of the rebuild, and 601 trees measure
281 MiB; a 16-entry LRU gave a peak of 2051 MiB against 2042 — no gain, plus
the re-parsing cost that avoiding was the whole point of F-030. Reverted.
**And lazy binaries would save about 1× the binary bytes** on a book that was
never at risk and nothing at all on the one that is.

The multipliers moved three times in two days — 12.0 when first fitted, 14.0
when a stage was added that reads every content document, 4.6 once the
transient allocation was gone. That drift is why `test_memory.py` pins every
row of the table: the constants are a *safety* estimate, and one that quietly
goes stale fails in the one direction that matters.

Switchable off, the owner's standing rule, with its own budget field — "reachable
from the window" does not stop at a checkbox. An empty field means "ask the
system and leave a fifth spare". In the window: the rebuild tab. On the command
line: `--no-memory-check` and `--memory-limit 4G`. The estimate is in the
diagnostics too, on a "memory" line, so it can be asked before a run.

Still open, and written down rather than left implied: the parse trees are
281 MiB of the remaining 518.

#### One queue for every question

The only thing this program knew how to ask about was a dead fragment, and even
that question had no stable identity, no recommendation, no stated cost and no
way to answer once and be remembered. A resolver that raised was caught by a
bare `except` and read as "leave it" — so a front end that crashed and a person
who deliberately chose to leave something alone were the same event in the
record. A hundred considered decisions and one broken window looked identical,
in a report the owner reads as evidence that his book was left alone on purpose.

`epubforge/decisions.py`: a question has a stable id — derived from its kind,
its place and its subject, not from a counter, because a counter shifts when a
chapter is renumbered and yesterday's answer lands on a different question
today — plus a group, options with the consequence of each, a recommendation,
reversibility and risk. Answers are stored beside the book and discarded
wholesale if the book file has changed.

Three kinds share it, which is the audit's closing criterion for this finding:
the dead reference, the hard hyphen, and the metadata conflict. The third is
the one that showed the API was worth building, because it needed no new
machinery at all — it is F-004's conflict, reported since F-004 closed, which
meant a person got a warning and, in the same breath, no way to do anything
about it. It is one question per field: somebody may know the title and have no
idea about the identifier, and a single question about the whole book would
force one answer to cover both.

#### Hyphens a conversion left inside words

The detector answers one question: *what is the evidence that this hyphen is
not the author's*. Inside a single file there is only one strong answer — the
same book writes that word without a hyphen somewhere else.

The order took two attempts. The first version checked the linking vowel `-o-`
before weighing the evidence, and therefore found neither `obo-jętna` nor
`doboro-wym`, because both end in `-o`. A structural fact — a digit, a capital,
a reduplication — settles it; a tendency loses to a page of the same book.

Measured across the owner's 32 books: 67 confirmed, 101 "likely", 88
"uncertain". Read through, almost every entry in the last two lists is a real
word: `marksizm-leninizm`, `savoir-vivre`, `ping-pong`. A queue of 189
questions that are mostly not defects is a queue nobody finishes, and it is
exactly the over-eager heuristic the finding itself warned about. So only the
confirmed ones are asked about; the rest are counted and shown.

The 67 confirmed cluster in 8 books, and 46 of them in one — the same book the
audit named as the mandatory fixture for this finding. The detector found it
independently.

Nothing is joined without an answer. A recommendation is an opinion; a batch
run, the corpus and every library caller get a book with every hyphen the
publisher put in it. The text change goes through the same guard typography
uses, strengthened: the before-text with exactly the agreed replacements
applied must equal the after-text, character for character. Anything else and
the document goes back unchanged.

Detection is not gated on the typography flag, and that is deliberate. The flag
guards a stage that *edits* text without being asked; counting broken words
edits nothing, and a book with forty-six of them should say so either way.

#### The gate that looks at the drawn page

Every fidelity check until now compares structure — text, shapes, media,
reading order, declared style — and every one of them passes on a book that
came out cropped, stretched, blank, or with its dedication pushed past the
bottom edge. The audit's sentence is exact: the suite proves the output
validates, and does not prove it still looks like itself.

The question is put in the only form it can honestly be put in. Not "is this
page well set" — that needs a designer — but "does it look the way it looked
before this program touched it". Two screenshots, page by page, two viewports,
paired by reading order.

The renderer is Chromium driven headless from the command line. **It is not a
dependency of the program** — rebuilding a book draws nothing, and an installer
carrying a browser in order to repair an EPUB would be absurd. The module finds
a browser if the machine has one and says in sentences what is missing if it
does not. The engine version travels with every result, because a comparison
between two engine versions measures the engine.

**Reading the direction of a change is the whole problem, and it took four
attempts.** All three failures are written into the code, because each sounded
reasonable and each fell over on the first real book it saw.

1. *Every significant difference is a defect.* A 1472×2341 cover with no size
   styling: at a 600×800 window the source draws it at natural size and the
   reader sees a corner, while the rebuild fits it to the page. A fifth of the
   pixels differ and the book is *better*.
2. *Read the direction from where the ink sits.* Works on a cover, falls over
   on a title page, which is mostly white — ink measures where the letters are,
   not where the image is.
3. *Pair pages by index.* Measured on a real book: 70 documents in reading
   order in, 71 out, because the rebuild generated a cover document the source
   did not have. Every page after the first was being compared with its
   neighbour. A gate that compares the wrong pages and refuses to publish a
   book on that basis is worse than no gate. It is a `difflib` alignment over
   name stems now, handling insertion and deletion the way a diff does.

What settles it is the one quantity that carries direction: a page that has
lost something shows **less**. Two refinements came from real books.
*Coverage alone does not distinguish loss from refitting* — a purchased book's
title page dropped 46% of its coverage while the reader gained the whole image;
content cannot appear on top of something already drawn unless it was there all
along and could not be seen, so an ink box whose top-left corner moves up or
left is a refit. *Content that disappears takes its area with it* — a page with
identical text, identical layout and an ink box identical to two decimal places
came out 10% lighter because the rebuild settled on a different font. Ink alone
called that a loss; ink together with area does not, and a page that really
lost a paragraph fails both.

One check was removed after being measured: "the content now reaches the bottom
edge". A text block pushed off the page leaves its last visible line wherever it
falls — measured at 34%, 50%, 67% and 83% displacement, the bottom of the ink
sat at 0.891, 0.889, 0.884 and 0.879, never the 0.995 required. It would have
fired on images and only by luck on text. Loss catches all four.

Result after all of that: **0 refusals across 32 real books** — 25 with no
change in appearance at all, 7 with a change that is not a loss — with all four
deliberate-breakage tests still caught: a blank page, half the text gone,
content pushed past the bottom at four distances, and a squashed image.

**The owner's question about this, and the answer, are the reason it ships the
way it does.** He asked: if the program repairs `wybo-rowy` into `wyborowy`,
the text after that word moves — so what is comparing screenshots supposed to
mean? It means what it measures. Reflow moves ink; it does not remove it.
Measured on his own book: all 46 confirmed hyphens joined, all 65 documents
drawn at two sizes — 7 of 130 comparisons moved at all, the largest by 1.64% of
pixels, and the drawn content changed by five thousandths of a percentage
point, upwards. Zero losses reported.

The gate asks three things: did a document disappear from the reading order,
did a page come out blank, and did content and the room it occupies decrease
together. It has no opinion about fonts or line breaking.

His three decisions, all three implemented as given:

- **"stop" by default.** On a detected loss nothing is written, and the file
  already at that name is left untouched. The switch has three states —
  off / report / stop — because when a program refuses somebody a file, a
  person decides.
- **Screenshots only for pages with a loss,** beside the result, in a
  `<name>.zrzuty` directory. His argument: without them, "this page has less on
  it" has to be taken on faith.
- **12 pages by default, with an option to draw the whole book,** which he
  asked for outright — a sample is somebody else's choice about which pages of
  his book are worth looking at.

With no browser present the program rebuilds and says plainly that verification
is **mandatory**, has not been performed, and may be knowingly skipped — along
with what it looked for and how to point it at a browser. That is his
instruction and it is a principle rather than a preference: a missing tool is
not a reason to hold somebody's book hostage to a dependency this program
deliberately does not carry.

The cheap refusal goes first: EPUBCheck costs seconds and drawing costs half a
minute, so a book the validator rejects is never drawn.

Two things this forced. The suite stopped fitting in ten minutes, because two
thousand tests that rebuild a book started paying for a browser — `conftest`
suppresses browser detection everywhere except files about rendering, exactly
as `test_corpus_signatures.py` disables EPUBCheck, and the policy default is
unchanged with `test_render_gate.py` watching it. And corpus signatures stopped
being a function of the book and the program and started depending on whether
the measuring machine had a browser, so the corpus rebuilds with the gate off.

In the window: diagnostics, fifth question. On the command line:
`epubforge render-check`.

#### Which test books, and what a fixture may not become

The audit called two purchased books "mandatory fixtures", recorded three
findings as blocked for want of files, and nowhere said which files. The
owner's answer was honest: he had no idea which test files were meant. That is
a defect here, not in his reading — the program asked for something and gave
nobody a way to find out what.

A role is now declared in code and described in sentences: what the book has to
contain, and which findings cannot be closed without it. What is committed is
`tests/fixtures/ksiazka-{1,2}.json` — a digest, a size and six numbers. No
title, no author, not one character of text; the mapping from a role to a real
book lives in private notes. Nothing has to be copied anywhere: the private
corpus shelf and the directories in `EPUBFORGE_FIXTURES` / `EPUBFORGE_CORPUS`
are searched, so a book already on the shelf is a fixture by virtue of being
there.

Matching is by digest and by nothing else. The version that matched on
structural resemblance was written first and measured second: on the owner's
own shelf it handed a completely different novel to a role, confidently and
with a reassuring caption. "EPUB 2, 29 documents, 3 images, 7 fonts, one
stylesheet" describes one publisher's export settings, not a book. A wrong
fixture is worse than no fixture, because the test would then be measuring a
book nobody chose. Resemblance produces a shortlist for a person to confirm,
never an answer.

**And the owner's question underneath all of this, made into a test.** He asked
directly whether the program treats a named book literally — "if it is *this*
book, do X" — or as an example of a shape. It has to be the second, because the
first would make the program worthless: the point is repairing every book you
add, not owning a list. Two things were true and only one of them was worth
anything. There is no book identity anywhere in the code today; and nothing
stopped one being added tomorrow. So:

- no module outside three (`fixtures`, `cli`, `gui/tabs`) may import the
  fixture catalogue — checked through the AST, not by grepping text;
- no recorded digest appears anywhere in the package;
- the same book with its title, author and identifier replaced produces an
  identical set of rules, with a guard that there were more than five rules,
  because two rebuilds that did nothing agree about nothing;
- the same book under two file names produces identical output, because
  matching on the file name is the cheapest way to smuggle in a rule "about a
  book";
- the list of three modules is a ratchet: the failure it guards against is not
  somebody writing a rule about a particular novel, it is `fixtures` becoming
  importable from one more place per release;
- the rule catalogue names no work and no publisher.

The digest stored beside a role is provenance for a measurement — it says which
copy the numbers were taken on — and not a condition in a rule. The profile
itself is a shape and deliberately matches more than one book; identification
is the digest's job.

In the window: the Corpus tab, "Test books" and "Assign a test book…". On the
command line: `epubforge fixtures`.

#### Two tests that asked the machine they ran on

**Timestamps in ZIP.** The mutation generator wrote entries through `writestr`
with a name alone, so every entry got a stamp from the clock. The test beside it
compared whole archives byte for byte and called the generator repeatable —
which was true only while both runs fell inside one two-second tick, that being
the resolution of the format's timestamp. It passed nearly always, and that is
the bad kind of "nearly": a genuine loss of repeatability would have looked
exactly like the flutter everybody had learned to re-run. There is a fixed
stamp now, plus a test that asks what the old one meant to ask — two runs on
either side of a clock tick — and a second one checking that nothing in the
archive is stamped from the clock at all.

**Host fonts.** The classifier reads the OS/2 table and was exercised only on
system fonts. On a machine without them the test asserted nothing and reported
a pass — on the audit's own container that was every case but three, so
`classify` ran with branch coverage at the level of a comment. Synthetic sfnt
files built in that file now cover every branch, including the one the module
was written around: PANOSE styles 14 and 15 describe stroke termination rather
than the presence of a serif, and fall through to `sFamilyClass`. The real
fonts stay; a synthetic font does not replace a real one and is not offered as
one. The difference is between "this never ran anywhere" and "this runs
everywhere, and on a real Lato additionally where Lato is".


## 0.2.23 — alpha — 2026-08-13 — kamień milowy [audyt]

The release that closes the last of the audit's fourteen system invariants, and
the milestone that closes the 0.2.19 engineering audit itself.

### EPUBCheck, asked before the file is published

**K.2 invariant 12**, and the only one of the fourteen left undone. The reason
recorded for leaving it was cost — a JVM per book, a few seconds each — and the
reason stopped being true (below).

**Where the gate stands is the whole design.** `write_epub` builds the archive
under a temporary name beside the destination and then calls `os.replace`,
which is atomic; that is how a disk filling up halfway stopped being able to
leave a truncated file where a good book had been. So "validate the file and
delete it if it is bad" would delete the *previous* good book at that name. The
gate is handed the staging file one line before the replace, and a refusal
never reaches the destination at all. **A file already at that name is left
byte for byte as it was**, which is asserted rather than intended.

Three settings, because two would have forced a bad choice — and the corpus
said so within the hour of the gate being switched on:

| setting | refuses | default in |
| --- | --- | --- |
| `off` | nothing; validates on request and reports | preserve, minimal |
| `no-new-errors` | only what this rebuild added, source validated too | — |
| `clean` | anything EPUBCheck calls an error, whoever made it | strict |

`clean` was tried as the general default and withdrawn the same hour: a chapter
linking to a file the book does not contain is valid EPUB 2, invalid EPUB 3,
and arrived that way from the publisher. Refusing it would break the promise
preserve exists to keep. `no-new-errors` is the honest form of the question,
with one caveat stated wherever it is offered: a 2.0 source is judged by EPUB 2
rules and a 3.3 rebuild by EPUB 3 rules, so "new" can also mean "EPUB 3 has a
rule EPUB 2 did not". The refusal names the source's version for that reason.

**With no validator installed, `clean` refuses and `no-new-errors` publishes.**
That asymmetry is a decision: `clean` is an absolute claim about the file and a
claim nobody checked is not a claim — passing it would be 0.2.19's fail-open
defect wearing a gate's name. `no-new-errors` is a comparison, and there is
nothing to compare; the invariant gate, the read-back and the fidelity checks
still ran.

**Strict now refuses two of the twelve public corpus books**, for defects they
arrived with and that strict cannot repair without guessing. That is the gate
telling the truth rather than a regression, and it is in both READMEs under
Limits because it is worth knowing before rather than after.

### What the gate found in its first hour

- **A `<picture>` outliving the `<img>` inside it.** Strict removes a reference
  to a file the book does not contain; where that reference was the `<img>` of
  a `<picture>`, the wrapper stayed behind — and a `<picture>` with no `<img>`
  is invalid and displays nothing either way. Across the whole public corpus in
  all three modes this was the only place any mode introduced an EPUBCheck
  error. Fixed: the wrapper goes with it.
- **A stylesheet pointing at a font the book never had.** Strict neutralises a
  dead reference in a document and does not yet do it in a stylesheet, so it
  cannot make such a book conformant and now says so instead of publishing it.
  Named here rather than fixed quietly: it is a real gap and it belongs in its
  own change.

A test now runs the entire public corpus through every mode and asserts that
**no mode adds an EPUBCheck error to any book in it**. That is the measurement
the gate exists to keep true.

### One JVM instead of one per book

The owner asked whether making EPUBCheck a gate before publication really means
a JVM per book, and if so whether it can be sped up or replaced. Measured
rather than guessed, on eight real books between 0.8 MB and 23 MB with the JVM
options already tuned:

| | |
| --- | --- |
| bare JVM start | 37 ms |
| JVM with EPUBCheck's classes loaded | 125 ms |
| a 1.8 KB book, end to end | 3602 ms |
| eight real books, a process each | 35.3 s |

A 1.8 KB book costing three and a half seconds is the whole finding. The cost
is not the JVM, and it is not the book — it is EPUBCheck compiling its RelaxNG
and Schematron schemas at every start. **So the answer to (A) is yes and the
answer is not a flag**: the flags were tuned two releases ago and buy tenths of
a second. It is not throwing the JVM away between books.

Those eight books through one process held open: **8.4 s**, the first book
paying 4.0 s and the rest 0.2–1.7 s each. This suite went from 153 s to 100 s
on the same change.

As for (B), a non-JVM EPUBCheck: there isn't one. EPUBCheck is the reference
implementation the specification's own test suite runs against, the alternatives
are wrappers around this same jar, and a second implementation of the rules
would be this program marking its own homework. The question stops mattering at
8.4 s.

What the driver does **not** do is check anything itself. It calls EPUBCheck's
own entry point with the argv the command line would have used, so the JSON is
written by EPUBCheck's code and the fast answer is the same answer — held to
that by tests on clean books, broken books and damaged archives.

Every way it can fail ends in a fresh process for that one book: no driver
class, no compiler, a process that died, an answer that is not a number,
silence past the timeout, or the checker throwing. And it now notices when the
validator changes underneath it — a live process used to answer from the jar it
was started with for the rest of the session, so pointing `EPUBCHECK_JAR` at a
new release would have changed nothing and said nothing.

The checkbox is in the diagnostics panel and `--separate-validator-process` is
on the command line, because "turn the fast path off" is the first thing worth
trying when a verdict looks wrong.

## 0.2.22 — alpha — 2026-08-13

### The build that reported success while installing nothing

Found on the first Windows run of this release, and it is the worst kind of
defect in a build: the step was green.

`pip install --require-hashes -r pyinstaller.lock` exited 1, because the lock
did not pin `setuptools` and PyInstaller needs it. PowerShell does not stop for
a native command that failed, so the step passed, the manifest printed a `pip
freeze` with no PyInstaller in it, and the failure would have surfaced four
steps later as the packaging step dying of something that looked unrelated.

The lock said so itself. `pip-compile` had written *"the following packages were
not pinned, but pip requires them to be pinned"* into the file, and nothing read
it — including the test file whose whole subject is that lock.

Fixed in three places, because one would have been the symptom: `--allow-unsafe`
in `lock.yml` so the lock is generated complete, an explicit exit-code check on
every `pip` call plus an `import PyInstaller` next to the install so the step
fails where the failure is, and a test that refuses a lock carrying that
warning.

### Two tests that were measuring the platform

Both passed on Linux and failed on Windows, and in both cases the program was
doing exactly what the test was written to check.

- A destination whose parent is a file: Linux calls that `NotADirectoryError`,
  Windows calls it `FileNotFoundError: [WinError 3]`. The test asserted the
  Linux spelling. What it should assert — and now does — is that the
  filesystem's own answer reached the report at all.
- A budget of zero seconds was expected to be over budget immediately. Windows'
  monotonic clock ticks about every 16 ms, so no time had passed yet. The test
  now backdates the budget's start, which is the thing its name claims to
  measure and measures it the same everywhere.

A third, on Linux, failed once in two full runs and passed alone: two rebuilds
compared byte for byte, either side of a `dcterms:modified` second boundary. The
comparison now runs under `reproducible`, because a test asserting identical
bytes must exclude the one field this program is documented to move.

### The audit

The release that closes the 0.2.19 engineering audit. Thirty findings, every one
with a command that decides whether it is done — and, in the last stretch, the
rest of the audit: the compliance grades, the fidelity model, the security
budgets, the test-gap matrix, the fourteen system invariants and the roadmap.

### A link this program cannot resolve is not a link it may rewrite

**F-010.** A `noteref` to `przypisy.xhtml#fn-17` whose fragment was dropped
points at `przypisy.xhtml`, so tapping footnote seventeen lands on footnote one.
Not a broken link a reader can see — a *working* link to the wrong place, made
by this tool and reported as a repair.

Three states now, and no others: `PRESERVED`, `REPAIRED` — which requires a
mapping this rebuild produced and can point at — and `UNRESOLVED`. Neither mode
touches the last one. What the modes disagree about is the result: preserve
publishes the book with the publisher's own broken link and says so, strict
refuses to publish it.

And where somebody is at the window, the program **asks** rather than guessing.
The dialog shows the link, its own text — for a footnote, the number the reader
sees — and the anchors the target document really has. One answer can cover the
whole book. The same question is available at a terminal behind `--ask`.

### What the rebuild was losing without saying so

- **A navigation section this program has no rule for** was regenerated into
  nothing. A list of illustrations, a list of tables: entries a publisher wrote,
  gone from the output. Carried now, with `epub:type`, `hidden` and `aria-label`
  intact.
- **293 of 294 page links, on every Project Gutenberg title.** They are written
  as `epub:type="landmarks"` with every entry typed `normal`, and landmarks were
  deduplicated by type alone. Found by the fidelity harness on the third book it
  was pointed at; no validator has an opinion about a book that came out with
  three hundred fewer links in it.
- **A file called `chapter.bak`**, deleted on the strength of its extension,
  with no test of whether the book used it and no switch to turn it off.
- **`<?xml-stylesheet?>`**, removed with nothing put in its place, so a book
  styled the old way came out unstyled.
- **`linearGradient` spelled `lineargradient`** after an HTML recovery — SVG is
  case-sensitive and HTML is not, so a gradient rendered as flat colour in a
  file that validates.
- **A container offering two renditions** produced one publication plus somebody
  else's chapters. Each rendition is now rebuilt into its own file.
- **Metadata refinements with no field in the model**, and `<link>` inside
  `<metadata>`. Carried, and a refinement is re-pointed at whatever id the
  rebuilt package gives that node.

### Proof rather than assertion

The **fidelity harness** compares a book with its rebuild: every word of the
text, the count of headings and pictures and paragraphs, every image and font
byte for byte, the reading order, and the declarations that reach each element.
Reachable as `epub-forge fidelity` and as a third question in the window's
Diagnostics tab. It found the Gutenberg loss above in its first hour.

**Fuzz and property tests** — sixty deliberately damaged archives per run,
asserting that the program does not crash, does not leave a file on disk while
reporting failure, answers inside a minute, and can read back whatever it
writes. They found two crashes in their first minute: a corrupt deflate stream
and an empty entry, both of which escaped as exceptions and would have ended a
batch.

**A reproducible mode**, because a mechanism nobody can ask for is a thing the
author knows rather than a feature. Two rebuilds of one book are byte-identical:
the modification date comes from the source, and a book with no identifier gets
one derived from its content instead of a fresh `uuid4` — which matters, because
font obfuscation is keyed on the publication identifier.

**A stage is held to what it says about itself.** One that declares it only
measures the book is fingerprinted before and after; if it changed anything, the
run is blocked. And a document is parsed once per version of its bytes rather
than five times.

### Smaller, and worth knowing

- A ZIP entry name is a name and an `href` is a URL. Percent-decoding the entry
  name changed which file a path meant — `a%2Fb.xhtml` became `a/b.xhtml`, a
  file moved into a directory.
- The dependency lock, with hashes, generated on the runner that builds.
- The output is read back by this program's own reader before it is called done.


## 0.2.21 — alpha — 2026-08-13

Four more of the audit's findings, and a plan in the private notes with a clause
that makes it checkable rather than remembered: every item names a command whose
output decides whether it is done, and `tools/audyt-status.py` runs the lot. A
position with no such command is open by definition, however much code was
written for it. That rule exists because this project once announced a release
that had not happened.

### A moved file takes its references with it, or it is not moved

**F-003.** A standalone `diagram.svg` referring to `../assets/pic.png` was moved
to `images/` along with the picture and came out still saying
`../assets/pic.png`. An `<image>` that does not load, inside a file EPUBCheck has
no reason to open.

Adding SVG to the carried-XML rewriter — both `href` spellings, plus `url()`
inside the SVG's own `<style>` — closes the type somebody thought of. The rule
underneath closes the ones nobody has: **a file whose references cannot be
rewritten is not moved at all.** It stays where the publisher put it, which costs
a tidy directory listing and keeps a book that works.

Two corrections while writing it, both from the tests rather than from thinking.
The loose reference scanner is *markup*-shaped — it knows `href`, `src`, `url()`,
`@import` — so `fetch("../data/quiz.json")` matched nothing and a rule against
moving files blind was blind to the commonest case of it; a second, cruder test
asks whether a file's text contains another packaged file's name. And pinning the
script was useless while the JSON it named still moved: what cannot be rewritten
has to keep **both** sides of the sentence true.

### A commit gate, so a book that makes no sense cannot become a file

**F-006, second half.** 0.2.20 closed the read side. The write side had nothing:
the archive verifier reads entry order, mimetype and CRCs — properties of a
*ZIP* — and had no opinion about whether the book made sense. A spine entry
naming a document a stage removed produced a technically perfect archive,
published atomically. The writer even noticed that case and carried on, which is
the same fail-open shape as the reader's skipped entry.

`epubforge/invariants.py` checks what this program is responsible for: the
reading order resolves and holds no document twice, the generated navigation and
landmarks lead somewhere, fallback chains end and do not cycle, the cover exists.
A violation blocks before `os.replace`.

The scope is deliberately narrower than *everything must resolve*, and a test
pins the line: a dead link inside a content document is usually the source's own,
`preserve` keeps it on purpose and says so by name. Making that fatal would
refuse a large fraction of real books for a defect they arrived with — the first
draft of the read-side gate's mistake, repeated.

The rule catalogue corrected the first design inside a minute. Nine invariant ids
passed as a *variable* is exactly what `test_no_call_site_computes_its_identifier`
forbids — it exists because a tagging pass once spliced one into a concatenation
and two releases went out reporting `compat.appliedapple, kindle` — and their
Polish translation was a copy of the English `{detail}`. Nine ids with one
sentence between them were not nine rules; they were one rule with nine shapes,
and the shapes belong in the values.

### EPUBCheck 5.3.0, on evidence rather than on being newer

**F-027.** Both versions were run over every book of the public corpus in two
modes and returned the same messages — zero errors either side, no code present
in one and absent in the other. A validator version is part of this product's
semantics, which is why the corpus ledger records it per book.

Dependencies gain upper bounds: `lxml` decides how a recovered document comes
out, `cssutils` how a stylesheet is serialised, `Pillow` what a transcoded image
is. These are **not** a lockfile and the comment beside them says so — what they
buy is that a new major cannot land in a release without somebody choosing it.
The honest record of what built a binary is taken when it is built, so the
release workflow writes `build-manifest.txt` with the commit, the Python version,
the EPUBCheck version and `pip freeze`, and attaches it beside the installer. An
incident nobody can reproduce is an incident nobody can fix. A real lock with
hashes has to be generated on the runner and is still open.

### Every reserved `META-INF` file gets a decision instead of a skip

**F-012.** One `startswith("META-INF/")` skipped the lot, and skipped is not a
decision — it is the absence of one. A book carrying rights metadata or an
organisation's signature came back without them and without a finding.

`rights.xml` and `metadata.xml` are carried byte for byte: they say things about
the publication this rebuild does not change and has no business editing.
`container.xml` and `encryption.xml` are ours to write. A file nobody here
recognises is carried rather than judged — the one thing worse than keeping it is
deciding on its behalf that it did not matter.

**Signatures are removed, and said out loud.** The owner's decision, taken after
asking what the thing actually is. A signature is computed over exact bytes, and
this program rewrites the package document even in the mode that leaves content
byte for byte, so none can survive a rebuild and none can be re-made without the
signer's private key. Keeping it is the one genuinely bad option: a tool that
checks the signature reports not "unsigned" but *the signature does not match* —
true, and reading as an accusation of tampering where there was a repair.
`META-INF/manifest.xml` goes the same way, because ours would be wrong the moment
anything is renamed and a stale inventory is worse than none.

### Still open, and named

F-019/F-020 (a resource budget: entry counts, XML depth, pixels × frames, a
deadline), F-002 (ZIP names, OCF paths and URLs are all `str`), F-004 (HTML
recovery lowercases `linearGradient` and drops a processing instruction), and
F-017/F-028 (the fidelity harness — the beta condition, and the one thing 1544
tests do not prove). Two owner decisions are recorded: multiple renditions get
rebuilt individually rather than refused, and the fidelity harness comes in
stages with screenshots second.

## 0.2.20 — alpha — 2026-08-11

### An outside audit, and nine of nine

An engineering audit of commit `003d254` came back with thirty findings and a
one-word answer to *would you run ten thousand random EPUBs through this
unattended and ship the results*: **no**. Nine of the thirty were checkable here
in an afternoon. **All nine reproduced exactly as written.** That number is the
important one and it is recorded before anything else in this entry, because
this project has a habit of checking confident reports and finding them wrong,
and this one was not wrong about anything it could be checked on.

Seven are fixed below. Each has a test in `tests/test_audit_0219.py` naming what
was measured on 0.2.19, written before the fix, in the order the audit asked
for.

**A book could be written with a chapter missing.** The worst of them, and the
one this project had argued itself into on purpose. When an archive entry cannot
be read — too large, broken stream — the reader said so and carried on, and
`rebuild()` wrote whatever was left. Measured: an EPUB whose only chapter
exceeded the per-entry limit produced `succeeded-with-problems`, a file on disk,
and **no chapter** — `mimetype`, `container.xml`, the package, the nav, the NCX.
A complete, openable, empty book, reported as a qualified success.

The argument against it was already in the file, four lines away, guarding the
archive-wide limit: *for a tool whose first rule is that no character is lost,
half a book is a worse outcome than a refusal.* It was right there and applied
to one of the two limits. Now a source that cannot be read in full stops the
rebuild before any stage runs, and `--allow-incomplete` is how a person says go
on anyway — the owner's standing rule about deletions, pointed at a refusal.

The first draft of that set was too wide, and the suite caught it inside the
hour: it counted `reader.name-dropped` as a lost resource, which would refuse
every book carrying a `__MACOSX` shadow or a `../` entry. Those are not
publication resources going missing. Removed from the set, and the reasoning
written next to it.

**Two manifest items with one id.** A manifest with two `id="dup"` items and a
spine naming it produced a book reading the *second* document, silently. The
output's ids are unique, so nothing downstream could see the question had been
asked. Last-one-wins is a decision and it is not this program's to make; the
ambiguity now stops the rebuild and the finding names both candidates.

**A remote item with a bad fallback crashed the reader.** `AttributeError:
'RemoteResource' object has no attribute 'path'` — a traceback where a finding
belonged, and in a batch, the end of the batch. A remote item has an `href` and
no `path`; that is the whole point of the class.

**A document's own language was overwritten.** A chapter declaring `lang="fr"`
in a book whose package says `en` came out saying `en`, taking the hyphenation,
the speech synthesiser's accent and the dictionary with it. A bilingual edition
is not an error to be tidied.

The fix was half right and the public corpus said so within the hour, which is
the best argument for that corpus this project has produced. "Believe the
document" is not the rule either: three Polish Gutenberg books wrap Polish text
in `<html lang="en">`, because the boilerplate says `en` and nobody edits it, and
believing that hands a text-to-speech engine an English voice for *Pan Tadeusz*.
So the rule is the one already applied to the package's own declaration, one
level down — **the text decides.** On the six public books it separates them
exactly: a 233 946-character Polish novel declaring `en` is corrected, and the
18 726-character English Gutenberg licence beside it *in the same book* keeps
`en`. That is the bilingual case arrived at from the other direction.

**WebP is a core media type, and converting it cost an animation its frames.**
A two-frame animated WebP came out a one-frame PNG. Two defects at once: EPUB
3.3 lists `image/webp` among the core media types, so nothing needed converting;
and the conversion that was not needed decoded one frame and saved it.

Not a reading of the prose — the EPUBCheck this repository ships validates a
book holding a bare `image/webp` with no fallback and reports zero errors under
EPUB 3.3 rules, and a foreign resource used without a fallback is an error. The
validator saying nothing is the validator saying the type is core. Alongside it:
any multi-frame image is now kept as it came in rather than flattened, because
a moving picture converted to a still one has not been converted.

**A package path this may not write.** `content_dir='../evil&dir'` and
`package_name='p"q.opf'` produced four archive members beginning `../`, a
`container.xml` lxml refuses to parse, and an internal verifier that pronounced
the archive good. `Policy` is public API; nothing in the CLI or the GUI can reach
this, and that is not a reason to accept it. Both fields are validated at
construction *and* in the writer — a dataclass field assigned afterwards never
sees `__post_init__`, which is how the original reproduction was written — the
container is XML-escaped, and the verifier now parses what it wrote and checks
the rootfile it names is in the archive.

**A third `dc:title` stopped existing.** Three untagged titles came out as two:
first stayed, second became the subtitle, third was dropped — and the finding
said "3 collapsed", which reads like an accounting of where they went. EPUB 3
allows as many as the publisher wrote.

**The ONIX code was not a code.** `scheme="onix:codelist5">ISBN<` announces a
vocabulary of two-digit codes and then says something that is not in it. ISBN-13
is `15`, ISBN-10 is `02`, and the digits decide rather than the word. A source
that already carries a code keeps it, whatever it is — rewriting somebody's ONIX
code because it is not one of the three spelled out here would be inventing
metadata rather than repairing it.

### What the audit found that is not fixed here

Named, not buried. F-002 (ZIP names, OCF paths and URLs are all `str`), F-003
(a standalone SVG's references are not repointed when relayout moves it —
reproduced, still open), F-004 (HTML recovery lowercases `linearGradient` and
drops an XML processing instruction), F-006's other half (a full pre-commit
validation gate; this release closes the read-side half), F-017 and F-028 (the
approximate cascade authorising deletions, and a test suite that does not
measure rendering). These are architecture-scale and each is in `docs/ROADMAP.md`
with what it would take. The audit's own advice was not to start there, and it
is right.

## 0.2.19 — alpha — 2026-08-10

### The same book twice was measured twice, raced with itself, and counted twice

Both shelves came back on 0.2.18 and the line the release was written around
did what it said it would: **`text_lost: 1 → 0`**. The book is *The Wheel of
Time*, 26 million characters, every document in the reading order including the
navigation, and its signature now reads `minimal.text_added: -32 → 0`,
`text_invariant: false → true`, `+nav.contents-page-kept`. Diagnosed without the
book, fixed without the book, confirmed by the book. The Polish shelf came out
0 / 10 / 14 for the third release running — **green streak 3**.

What the same run found is ours, and it is the shelf's oldest known fact biting
from an angle nobody had looked from. This shelf holds 67 files and 63 books:
four of them are byte-identical copies, because it was pulled off the internet
whole. A signature is named after the hash of a book's bytes, so a copy and its
original are one signature — right, and written down since the shelf arrived.

The working directory was named the same way.

    room = scratch / identifier_for(book)

Books are measured side by side, and that directory exists *because* they are:
two threads writing `scratch/preserve.epub` would each validate a file the other
had just replaced. Keying it by identity closed that for every book except the
one case where two threads really do hold the same identity. Windows said so
out loud — four `PermissionError`s, one thread replacing a file the other still
had open, and the run recorded `failed: 4`. That was the lucky outcome. The
same race on Linux produces no error and a plausible wrong answer, which is the
failure this directory was created to prevent, restated in the fix that was
supposed to be the prevention.

The room is now unique per measurement rather than per book, and above it
`compare` no longer measures identical bytes twice at all: a duplicate is
reported as a duplicate, naming the file it copies, and three JVM starts are
not spent to re-learn what the first copy already said.

Underneath sat the quieter half. Every total in the ledger is read out of
`signatures/{identifier}.json`, once per **result** — so four duplicate results
read four signatures a second time and added their errors again. The mixed
shelf's ledger says `carried: 129` for 0.2.17 and 0.2.18; the books say 122. It
says `errors: 54` where there are 53, and `RSC-005 ×44` where there are 42.
Small numbers, and wrong in the direction that flatters nobody — but this
ledger's whole purpose is to be the thing that is not remembered, and a total
that counts some books twice cannot do that job. Counted per book now, with
`duplicates` stated in the entry so `books` and every figure beneath it can be
seen to disagree on purpose.

Both 0.2.18 entries are recorded exactly as the run measured them, inflation and
all, with the true figures in the note. The ledger records what the tool said on
the day; the correction belongs in the next run, where it can be checked.

### The ledger blamed us for the books, on the line the last release fixed

0.2.18 fixed a summary line headed **"Ours, by EPUBCheck rule"** that added every
code it saw without subtracting what the source already carried. It fixed the
report. It did not fix the ledger, which computes the same field by the same
wrong rule six functions further down — so `runs.json` blames the mixed shelf's
release for **34 `RSC-005`, 8 `RSC-011` and 5 `RSC-007`** whose honest total is
two rules and ten errors.

The two now subtract the same thing. A report and a ledger that disagree about
whose fault a defect is mean one of them is lying, and it was the one written
down and kept.

### Four defects the second shelf found, all of them ours

With the blame arithmetic honest, what is left on the mixed shelf in the modes
that open documents is small enough to read one line at a time. Four of those
lines are answered here.

**The same `id` twice in one document — 8 errors, 2 books.** `bookmark63` …
`bookmark86`, which is Word's naming, and `heading_id_3`/`heading_id_5`, which is
a converter's. Invalid in XHTML 1.1 exactly as in HTML 5, so nothing about the
upgrade caused it and nothing about the upgrade excuses carrying it. The pass
that made ids valid XML names now makes them unique in the same walk. **The first
one keeps its name**: every parser resolves `#bookmark63` to the first element
carrying it, so renaming the copies cannot move a link and renaming the first
would. For the same reason the copies stay out of the rename map — that map
exists to repoint references, and a reference to a duplicate was never pointing
at the copy.

**`RSC-011: Found a reference to a resource that is not a spine item` — 4 books,
all three modes.** Absent from every source's own verdict, because EPUB 2
navigated by NCX and had no such rule. EPUB 3 does: what the contents lead to has
to be in the reading order. The publisher's intent is not in doubt — the document
is in the manifest and in the contents, so it is meant to be reachable; it is out
of the spine, so page-turning is meant not to arrive at it. `linear="no"` is the
standard's own word for that pair, and it is what a colophon or a rights notice
usually wants. The entry is kept and the document is spined, placed where the
contents imply rather than appended, so a cover listed first comes out first.
Dropping the entry is the shorter patch and it deletes the only way to reach a
page the book still contains.

That repair drags one measurement behind it, and the measurement was already
wrong. `spine_text_characters` is documented as *"what a person actually reads,
in reading order"* and counted every spine item, `linear="no"` included — which
is the spine's own word for **not** in the reading order. Left alone, four books
would have reported text appearing from nowhere for a repair that moves no word
a reader reads, and the ledger would have called the shelf red for it. The
figure now agrees with its own first sentence. The cost, stated rather than
hidden: if anything ever marked a real chapter `linear="no"`, K1 would stop
seeing its text — one code path sets that flag, only for a document the source
itself kept out of the spine, and it reports itself by name.

**`target`, looked for in the one place it was not.** It was removed from `<a>`,
where an EPUB has no window to open anything in. Two books kept the error through
`preserve` and lost it in `strict` — which is not the attribute being handled but
the element carrying it being unwrapped by a strict-only cleanup, and the tell
that it was sitting on something else entirely. A converter copies attributes
wholesale; `target` on a `<span>` renders exactly as `target` on an `<a>` does,
which is not at all. Removed wherever it appears.

**`CSS-001`: the text direction in a style sheet.** EPUB 3 bars `direction` and
`unicode-bidi` from style sheets outright, because a reading system has to know
which way the text runs before it has resolved any CSS; the markup carries it
instead. Easy to satisfy and easy to satisfy wrongly: `direction: ltr` is
boilerplate Word and Sigil write into every book they touch and taking it out
cannot move a letter, while `direction: rtl` is holding an Arabic or Hebrew book
the right way round and taking *that* out mirrors the page. Same rule, same
message from the validator, opposite consequences. The default value goes;
anything else stays and is reported as the deviation it is. **Conformance does
not outrank the page** — a book that validates and reads backwards is not the
better outcome.

## 0.2.18 — alpha — 2026-08-10

### `text_lost: 1` — found, reproduced and fixed without the book

The mixed shelf's ledger carried one line that mattered more than the 120
EPUBCheck errors above it: **one book lost 32 characters of spine text in
container-only mode**, the mode whose promise is that content files come out
byte for byte, and which reported `xhtml.untouched` on that very book.

It did not need the book. The signature and the inventory between them said
enough: 24 MB, EPUB 3, **9 809 documents and 9 809 spine items** — so every
document is in the reading order, including the navigation — one TOC entry, no
cover. `preserve` and `strict` came out at delta 0; only `minimal` was short.
A fixture of that shape reproduced it on the first run, to the character.

The protection for this case already existed and had been written for it: a
navigation document that is also a spine item is *two things at once* — the
machine-readable navigation, and a contents page the reader can turn to — and
regenerating it serves the first and destroys the second. It was guarded by
`book.nav_path != nav_path`. In container-only mode nothing is renamed, so the
generated document lands on **the same path** the source's nav already holds:
the two are equal, the guard is skipped, and the publisher's page is
overwritten in place. The book's own word for "contents" — `Inhoudsopgave` —
went, and ours arrived.

The guard now asks the question it meant to ask: *is this nav a page anybody
can turn to?* When it is, and the paths collide, the generated nav moves aside
instead. One nav document, as EPUB 3 requires; the publisher's page still in
the reading order beside it; K1 holds in all three modes.

The public corpus confirmed it independently: one of the twelve fixtures in
this repository has the same shape, and its signature moved
`minimal.text_added: 51 → 0`. The generated navigation had been leaking its own
text into that book's reading order all along, in the mode that promises to add
nothing, and the recorded signature said so every run without anybody reading
it that way.

Two things worth keeping in view. The report said `xhtml.untouched` while
another stage rewrote a content file — true of the stage that says it and false
of the book, which is a claim worth narrowing. And the whole find came from a
ledger line nobody had to be clever about: it said `text_lost: 1`, and I had
read past it to a bigger number that turned out not to be ours at all.


### A second shelf, recorded and held to the same rules

The regression net was one shelf — 93 Polish books — and the ledger tests said
so in a hardcoded path. A second arrived and found two defects within a minute,
both invisible on the first, because the first has no book carrying the HTML
3.2 `<body>` palette. A net made of one kind of book catches one kind of
regression, which is roadmap point [1] restated by experience rather than by
argument.

`tests/corpus_mixed/` now holds it: 67 Dutch and English books out of Sigil,
Word and Calibre, with their own `expected/` and their own `runs.json`. Its
scope is not the Polish shelf's, so its ledger and its streak are its own —
merging them would compare runs over different books and call the difference a
regression.

`tests/shelves.py` enumerates shelves rather than naming them, so adding a
third is dropping a folder in. Every ledger test runs over each: that a scope
is recorded, that signatures exist to compare against, that the streak rule can
read it, and that a signature carries no word of anybody's book. That last one
failed on its first run and the test was wrong, not the data — `.epub` matched
inside the rule name `xhtml.epub2-only-markup`.

Two facts about the mixed shelf are pinned so a future gap cannot hide behind
them: 67 books produce 63 signatures, because a signature is named after the
hash of the book and a collection pulled off the internet at random has
duplicates in it; and `text_lost: 1`, which is unresolved. One book loses 32
characters of spine text in **container-only mode** — the mode that promises
the content files byte for byte, and which reports `xhtml.untouched` on that
very book. The documents came out untouched and the text got shorter, so it
points at the spine or the navigation. It needs the book.


### The summary said "Ours" about defects that were the books'

A shelf of 67 Dutch and English books came back with 120 EPUBCheck errors,
and under them a line reading **"Ours, by EPUBCheck rule: CSS-001 ×2, CSS-008
×2, RSC-005 ×110, RSC-007 ×6, RSC-011 ×12, RSC-020 ×2."** Its own ledger, two
lines above, said `introduced: 3`.

Both numbers came out of the same function. For the modes that rewrite content
it added **every** code it saw to the blamed list, with no subtraction of what
the source already carried — while the bucket beside it was computed correctly.
The heading was a lie and it worked: it sent me looking for defects in this tool
that belonged to the books, and I had already started fixing two of them.

The giveaway was there and I missed it. `CSS-008`, `CSS-001`, `RSC-011` and
`RSC-020` appear in **all three modes including container-only**, which opens no
documents and can therefore introduce nothing of that kind. An error present in
that mode is the source's, by definition.

Fixed both ways round: only codes and shapes the source did not have are
collected, and the heading now says what it means — *"Not in the source, by
EPUBCheck rule"*. A report that misstates whose fault something is, is worse
than one that stays quiet.

### `--compat legacy` declares fonts the way Adobe RMSDK reads them

The owner's call on the other half of that Calibre report: if EPUB 3 does not
need the older media type, it belongs in a backwards-compatibility profile
anyway. Right — the type this tool writes, `font/ttf`, is what EPUB 3.3
registers and what EPUBCheck wants, and RMSDK shipped before RFC 8081 and looks
the type up in a fixed list. A font declared by a name that list does not hold
is a font that does not load.

So `legacy` gains `legacy-font-types`: `font/ttf` becomes
`application/x-font-truetype`, `font/otf` becomes `application/vnd.ms-opentype`.
Only under that profile, reported as a preserved deviation, and never by
default — every measure in a compatibility profile is a step away from the
standard taken for a named device.


### A font stack gains the family the font declares about itself

Calibre's book check on a rebuilt book reported eleven "unexpected missing
generic font family". It is right, and the finding was already there —
`css.font-stack-generic-missing`, reported and deliberately not acted on,
because choosing between `serif` and `sans-serif` from a font's *name* is
guesswork and guessing at somebody's typography is how a tool that means well
ruins a book.

The premise was wrong wherever the book embeds the font. The answer is not a
guess and never was: it is written in the font's own **OS/2 table** — PANOSE,
ten bytes the type designer filled in, which every TrueType and OpenType file
carries because Windows needs it for font substitution. `epubforge/fonts_meta.py`
reads it, and a stack whose named font the book embeds now gains the generic
family that font declares. Where the font is not embedded, or where it declines
to say, nothing is added and the finding stays exactly what it was — that case
really is a guess.

It got the first real font it was pointed at wrong, which is worth writing down.
PANOSE serif styles 14 (Flared) and 15 (Rounded) describe how a stem *ends*,
not whether the letter has a serif, and sans-serif families use them: Lato is
15, and calling it a serif is worse than saying nothing. They fall through to
`sFamilyClass`, which says 8, and is right.

**The other half of that Calibre report is not ours.** Seven fonts flagged as
"MIME type inconsistent with the extension": we declare `font/ttf`, which is
the EPUB 3.3 core media type registered by RFC 8081, and Calibre guesses from
the extension against an older table that expects `application/x-font-truetype`.
EPUBCheck accepts our output without a word and the corpus runs clean. Old
Adobe RMSDK does only know the pre-RFC type, which makes it a candidate for the
`legacy` compatibility profile — a deliberate concession to a named device, not
a defect to fix.


### A Dutch and English shelf produced 120 errors where the Polish one produced none

Sixty-seven books out of Sigil, Word and Calibre, in languages this tool had
never been measured on. The modes that open documents came out with **120
EPUBCheck errors**; the Polish shelf of 93 produces zero. Two shapes accounted
for fifty-eight of them and both were ours.

**The rest of the HTML 3.2 `<body>` palette.** `bgcolor` was translated from the
first version and `text`, `link`, `vlink` and `bordercolor` were not — forty-two
errors between them. `text` is the body's colour and translates exactly.
`bordercolor` becomes `border-color`. The link colours are dropped and counted
rather than guessed at: CSS says them with pseudo-classes, an inline style
cannot hold one, and writing `a:link { }` into a shared stylesheet would reach
documents nobody looked at. Also `target` on a link — an EPUB has no windows,
EPUB 3 does not allow the attribute, and removing it changes nothing visible —
and `value` on elements that never had a use for it, which is what a converter
does when it copies attributes wholesale. On `<li>` inside `<ol>` it stays,
because there it numbers the item.

**`<meta name="…">` with no `content`.** Sixteen books, all out of Sigil or
Word, which write the name and leave the value for later. HTML requires the
pair and EPUBCheck refuses the document without it. It is **completed**, not
removed: the publisher named something, an empty value is the honest reading of
"named it and said nothing", and dropping the element would throw the name away
too.

### The rebuild got its speed back, and then some

The owner noticed the corpus, the survey and the inventory had all slowed down
again. Two causes, both introduced by recent work, and both measured rather
than guessed at.

**The cascade was parsed forty times per book.** Six passes over each document
ask for the CSS that applies to it, and every one of them re-parsed the same
stylesheet through cssutils. On a twenty-chapter book sharing one sheet that is
**eleven of the fifteen seconds** a rebuild took. Books share a stylesheet
almost by definition, so the parsed result is now cached on the sources it was
built from — keyed on the sources rather than the document, because two
documents with the same links and the same inline `<style>` have the same
cascade. **15.8 s → 1.8 s** on that book.

**The fingerprint ran thirty-five regular expressions over every book.** 0.31
seconds each on a two-megabyte book — nothing on one book, eleven minutes on
two thousand. Each signal now carries the plain lowercase substrings its
pattern requires, tested with `in` against a once-lowercased haystack before
the expression runs at all. **0.31 s → 0.08 s**, and 0.04 s for a book carrying
no trace at all. A test holds the needles to their patterns, because a needle
the pattern does not actually require would switch a signal off and nothing
would say so.

### Corpus 0.2.17: clean again, and the streak is 2

Same 0 introduced / 10 inherent / 14 carried as 0.2.16, on a release that moved
thresholds and rewrote two detectors. That is the useful part: the quote
labels, the Polish floor and the suspended hyphen all changed and this shelf did
not notice, because none of those defects were ever visible on it. The shelf
that did notice is the one above.

Two consecutive clean releases at the same scope, which is the 1.0 condition —
on this shelf.


## 0.2.17 — alpha — 2026-08-10 — kamień milowy [7]

> **Correction to the published release notes.** This section was written
> across a working day and two of its paragraphs were overtaken by decisions
> made later in the same day, which is exactly what an entry assembled in
> pieces does when nobody re-reads the whole of it before the build runs. As
> published, v0.2.17's notes say both that a contradicted `dc:language` is
> corrected and that it "is never corrected", and they say quotes are "not in
> yet" when they shipped in this very release. The text below is the corrected
> record; the release page still carries the original, and this note is here so
> the two can be told apart rather than quietly reconciled.

### The corpus came back clean, and said so itself

93 books on 0.2.16: **0 errors introduced** by any mode that opens a document,
14 carried from the source as always, and 10 that container-only mode cannot
reach without opening one. 0.2.15's ledger note ended *"0.2.16 will say it for
itself, and if it does not, this note is the prediction that was wrong."* It
said it — every one of the ten was named by `xhtml.epub2-only-markup` before
EPUBCheck was asked, which is the gate the `inherent` bucket depends on.

Green streak: **1**. The alpha condition wants three consecutive releases at
the same scope, so this is the first of three, not the finish.

The fingerprint's first real measurement: 46 of 93 books carry a trace it
recognises — gutenberg 17, sigil 17, calibre 16, from-mobi 5, indesign 4,
pdf-or-ocr 3, word 3, several books carrying more than one. The other 47 carry
none, which is what a shop EPUB looks like after the shop has finished with it,
and it means half this shelf will tell roadmap [7] nothing about where it came
from.

### A library of 2 200 books found two defects in the measurement

Not in the tool — in what the tool was measuring with, which is worse, because
roadmap [7] was about to set its thresholds from those numbers.

**`QUOTE_FORMS` had seven entries and six keys.** `”` was written twice, once as
`pl-close` and once as `en-close`, and the second won. So `pl-close` was a label
nothing could ever produce, and every Polish closing quote was counted as
English — which made a book set in perfectly ordinary Polish `„…”` measure as
*mixing two conventions*. The "35 of 93 books mix quote forms" figure from the
previous entry was inflated by exactly this.

The repair is not a corrected table but a different shape of table. A character
is a **shape**; a convention is a **pair** of shapes, and that is where the
nationality belongs. `typography.QUOTE_MARKS` names marks by what they look
like, `CONVENTIONS` names the pairs, and `convention()` scores whole pairs
against the whole tally. Taking the dominant opening and the dominant closing
separately does not work and it is worth saying why: `“` is the English opening
mark *and* the German closing one, so sorted into both buckets it beats itself
and an ordinary English book comes out undecided. Polish and German share an
opening mark and differ only in the closing one — a per-character table cannot
tell them apart at all.

**2 187 of those books declare `en`, and 1 815 of them carry `„`.** English
typesetting does not use that mark. These are Polish books with `dc:language`
left at Calibre's default, and nothing had ever looked. That is K11 — *the
source's declaration is not a fact* — and it is not a typographic nicety: a
reading system speaks `dc:language` to its text-to-speech engine and hyphenates
by it, so the book is read aloud in an English voice and broken across lines by
English rules. Both are immediately obvious to a reader and invisible to every
validator.

`metadata.language-corrected` **corrects it**, as a fix, with the measured
rate. That is the owner's call and it overruled mine: I had it reporting only,
on the argument that knowing a declaration is wrong is not the same as knowing
the right answer. He is right — *if a book declares `en` and is plainly written
in Polish, then barring English insertions the declaration is simply wrong* —
and leaving a wrong one in place is not neutrality, it is leaving the book to
be read aloud in the wrong voice until somebody fixes it by hand.

It fires only where the evidence is decisive, and the threshold is measured
rather than guessed. Real Polish prose — not a diacritic-dense pangram — runs
about **69** Polish-only letters per thousand characters. The first floor was
5, a book roughly 7% Polish; an English novel carrying a single Polish
quotation scores **4.4**, so two of them would have had the book relabelled.
That is not a threshold, it is a coin toss next to a cliff. It is 35 now —
"more than half the book" — so a 60/40 Polish-English book is corrected and a
40/60 one is left alone, which is right: that book is bilingual, and calling it
Polish would be as wrong as calling it English.

Beyond the floor: over the book's own documents, never the navigation page this
tool generates, never below a page of prose, and only for a language whose
letters are their own proof. `--language` still wins.

The first version had neither guard and reported a Japanese manga as Polish:
the only document short enough to swing the average was the navigation page
*this tool had just generated*, whose title in a Polish report is "Spis treści"
— one `ś` in seventeen characters. Measuring our own output and calling it the
book is the mistake the profile stage's own docstring warns about, and it took
one fixture to make it.

The correction lives in the metadata stage, which owns `dc:language`, and the
typography stage reads what it settled — which is how the conjunction rule
reaches the books that need it at all.

What the library is *not* good for is worth recording too: 2 199 of its 2 200
books carry a `calibre` trace, 2 187 are EPUB 3, 2 187 declare the same
language. One generator, one format, one declaration — no use at all as a
regression net, whose value comes from variety of provenance. It was taken for
the distribution and it paid for itself twice in the first minute.

### A second collection: 67 books, and the third defect the data found

Not Polish, not one generator: 40 Dutch, 22 English, 66 of 67 EPUB 2, and — for
the first time — **layered files**. Five books carry calibre *and* sigil *and*
word; ten carry calibre and sigil; eight sigil and word. The fingerprint was
built on the argument that files are layered and this is the first shelf that
proves it.

And it broke the broken-hyphen detector, which is how a good collection earns
its keep. `PDF_HYPHEN_FLOOR` classified **50 of the 67** as PDF-or-OCR
conversions. Two of them carry any PDF or OCR trace at all.

The pattern was "letter, hyphen, space, letter" — a hyphen frozen where a line
used to break, which is what a PDF conversion leaves behind. It was also
matching the **suspended** hyphen, which is correct orthography and not damage:
`in- en uitvoer`, `pre- and post-war`, `wielo- i jednorazowy`. One word is
elided and the hyphen stands in for it. Polish barely uses the construction,
which is why 93 Polish books scored zero and nothing looked wrong.

The two are told apart by what follows the space: a frozen hyphen by the rest
of the same word, a suspended one by a conjunction. So the conjunctions are
named — and named across six languages rather than gated on the declared one,
because the declaration has already been shown to lie.

### [7] first rules: the stage that changes text, and checks that it did not

`epubforge/stages/typography.py`, behind `--typography` and a tickbox, off
everywhere, reached by no preset. Every other switch in `policy.py` decides how
markup is arranged around a text nothing may touch; this one lets a stage
retype the text, and no reader should discover that because a default changed.

**K1 is not switched off for it — it is replaced by something stronger.** The
stage folds each document's text to the canonical form before and after its own
work and compares the two. A document that fails goes back exactly as it came
in and the report says so (`typography.reverted`, a warning). A rule cannot
ship a defect past that; it can only produce a reverted document and a line
admitting it. Two of the tests are exactly that: a deliberately broken rule
that eats a word, and one that bites the end off a sentence.

Two rules to start with, and the shelf chose them:

* **three dots become an ellipsis.** Not four — a run of four is somebody's own
  punctuation, and an ellipsis is not longer than itself.
* **single-letter Polish conjunctions get a hard space**, so `w`, `i`, `a`, `o`,
  `u`, `z` do not end a line. Gated on the language the *metadata stage
  settled* — the declared one unless the text plainly contradicted it — which is
  what lets this rule reach the books written for it at all.
* **straight quotes are retyped into the book's own convention.** See above.

Container-only mode ignores the flag. Byte-for-byte is a promise about the
content files and it outranks a switch.

### [7] groundwork: the safety apparatus, before any rule touches a character

`epubforge/typography.py`. Typography is the only stage that changes text on
purpose, so it is the only one K1 — *no character of the book's text is lost* —
cannot police as written. Switching K1 off for it would trade the one invariant
that has ever caught a silent data defect for the convenience of the stage most
likely to cause one. So both sides are folded to a canonical form and compared
there: a curly quote folded to a straight one still has to be present, and a
lost word still reads as a lost word. `biało-czerwony` glued into
`białoczerwony` — the failure of every hyphenation repair ever written — is
caught by the fold rather than by a rule that remembers to look.

Where a rule may reach is one iterator, not a condition inside every rule:
`<pre>`, `<code>`, `<kbd>`, `<samp>`, `<script>`, `<style>`, `<ruby>`, MathML,
SVG, anything in another language than the publication, and anything whose
computed `white-space` preserves it. The tail text after `</code>` **is**
editable, because a tail belongs to the parent's flow — and the first version
got the mirror of that wrong, letting one character out of a protected block.

And `dominant()`, which answers what the book already does rather than what is
correct. A book consistently using `«…»` has made a decision (K5); the job is
to repair inconsistency, not taste. Two thirds, not a majority — at 51% a book
is not consistent, it is arguing with itself, and picking the winner would
impose an opinion on nearly half the text.

**The shelf reordered the plan.** The roadmap's three risk classes were written
before there were numbers. There are now: zero-width characters **0 books**,
mojibake **0**, hyphens frozen at a line end **0 above the floor**. Class 1
(safe) and class 3 (reconstruction) have almost no customers here. What does:
`...` typed for `…` and dominant in **34** books, and more than twenty unbound
conjunctions in **39**. (The "two quote forms mixed in 35" from this same
measurement was the duplicate-key defect above, not a fact about the books.) So the first rules are
class 2 — quotes, ellipsis, conjunctions — and not the easy class first.

One surprise worth recording: 213 591 soft hyphens, in four books. That is a
publisher pre-computing hyphenation points on purpose. Not damage, and nothing
will remove them.


## 0.2.16 — alpha — 2026-08-09 — kamień milowy [6]

### [6] `fingerprint.py` — what made this book, and how sure we are

Roadmap point [6], and the last thing standing before [7]. The detection
already existed, in `inventory.py`, as a flat table of regular expressions
producing a flat sorted list of names — which could not express the two things
that actually matter.

**How strong a trace is.** `_idGenParaOverride` is a class name InDesign
invents; nothing else writes it and no human types it. `vellum` is the name of
a typesetting program and also the word for parchment. The old table scored
them identically, so a book about bookbinding came out of a program it never
went near. Weights are now written down as data, next to the pattern, so the
judgement can be argued with instead of reverse-engineered from behaviour.

**Where it appeared.** The whole file used to be searched as one string, so
`<meta name="generator" content="calibre">` counted for exactly as much as the
word "calibre" in a chapter. The package document is a program writing its own
name; a chapter is prose. Same pattern, two weights, and the weaker one no
longer clears the floor on its own.

The result is a **list with confidences**, most confident first, because files
are layered — InDesign to Calibre to Sigil — and "90% calibre, 95% indesign"
is not an uncertain answer, it is an accurate description of a real file.
Confidences combine as `1 - Π(1 - w)`, so two weak traces corroborate into
something stronger than either while nothing ever reaches certainty; the value
is capped at 0.999 so a report never claims a fact it inferred from regular
expressions.

Each trace carries its evidence as **the string that was found** —
`calibre:series`, `MsoNormal`, `class=ftN` — rather than a sentence about it,
so anyone who doubts the claim can search the book for exactly that, and so it
reads the same in both report languages.

`ProfileStage` now reports it (`profile.made-by`), and the inventory uses this
detector instead of its own — one implementation of one idea, which is the
lesson the watermark taught the expensive way. Nothing acts on the answer yet;
[7] is where a rule first decides how careful to be based on it.

One consequence worth stating: books recognised only by a bare word in their
text no longer count as that generator, so corpus family coverage may fall.
That is the false positive going away, not the detector getting worse.

### "Released" now has a definition a machine can check

This version was bumped, written up, committed and pushed — and then described
as released. It was not: no build had run, no tag existed, nothing was
downloadable. The same turn closed roadmap point [6] and never froze it, and
that turned out not to be new: `frozen/*` stopped covering the roadmap after
0.2.8, though [3] closed in 0.2.11 and [4] and [5] in 0.2.14.

The fault was not forgetfulness. It was that "released" had no definition
anything could check, so it defaulted to whatever the last commit message
claimed. `packaging/release_check.py` gives it the strictest available one —
**the tag exists on the remote** — and splits the question in two: what this
repository can say about itself (version, changelog, both READMEs), which
`tests/test_release_state.py` now fails the build over, and what only the
remote can confirm (tag, frozen branch), read with `git ls-remote`.

> **Correction, made the same day and after this version's notes were
> published.** The paragraph here first said the build is dispatched by the
> owner in a browser and that this environment cannot release. Both halves were
> wrong. `git push --tags` is refused by the proxy with a 403 — a fact about one
> command, and the tag is created by the workflow rather than pushed — and the
> `actor` on a workflow run reads `LuKi965` because that is the account the
> token belongs to, not because a person clicked anything. This release was
> dispatched from here through the GitHub API. The published notes for 0.2.16
> still carry the sentence as it was at build time; this is the record that
> corrects it.

A release that closes a roadmap point says so in its changelog heading —
`## 0.2.16 — alpha — 2026-08-09 — kamień milowy [6]` — because that is the one
line nobody forgets to write, and the marker is what tells the script the
freeze is owed. `packaging/branches.py` restores step 4 of the cycle, which had
been pointing at a script that no longer existed; `frozen/*` is never in its
output, which is the entire purpose of the prefix.

`frozen/v0.2.11-profil-ksiazki` and `frozen/v0.2.14-martwy-css-i-spany` exist
now, at the exact commits the local tags still recorded after the remote ones
were deleted.

### `--strict` was deleting captions that were never going anywhere

The argument for touching `position: absolute` has always been a rendering
argument, not a conformance one — EPUBCheck has never called it an error. A
block taken out of the flow is not paginated with the text, a reader can lose
the page it was on, and a real dedication came out **blank**. That is why
`_page_bottom_kept` exists and why it translates rather than deletes.

The argument has a precondition that was never written down: it holds when the
element's containing block is the page. Put the same declaration inside an
ancestor the publisher positioned —

```css
.cover   { position: relative; }
.caption { position: absolute; bottom: 8px; }
```

— and the caption cannot go anywhere. It resolves against a box that is itself
in the flow and travels with it. That is not a defect; it is how CSS puts words
over a picture, and it works on every reader at every screen size. `--strict`
deleted it anyway, which drops the caption below the image everywhere,
including on all the readers where it was fine. Nothing was broken and the
repair broke it.

The case is now recognised during the document pass and reported as
`css.position-contained`; the declaration is kept in every mode. `position:
fixed` is deliberately excluded — it resolves against the viewport, so a
positioned ancestor is not its containing block and promises it nothing.

The guard is whole-stylesheet rather than per-rule, and errs toward keeping:
the sheet is shared between documents and the excision is textual, so matching
selectors to elements precisely enough to remove *some* of them would mean a
second cascade engine written to justify a deletion nobody needs.

### Where the shop's watermark goes is now a question with four answers

The tool consolidated a shop's tracking token — one CSS rule instead of an
inline `!important` in every document, plus `aria-hidden` so assistive software
skipped it — and the claim attached to that was that the token then costs the
book nothing. That claim was wrong, and the owner said so: `aria-hidden` binds
a conforming accessibility tree, and it does not bind the text-to-speech engine
built into an e-reader. That engine reads what is laid out on the page, and a
token at `font-size: 0` is still laid out. A book that recites twenty
characters of base64 at the end of every chapter is a broken book, whatever
size the characters are set at.

So `--watermarks` (and a matching dropdown in the window) now takes four
values:

* **keep** — the markup comes out as it went in.
* **consolidate** — the default, and what the tool did before: the token stays
  in the text, the repeated styling becomes one rule.
* **gather** — the token leaves the body and lands in the `<head>` of the same
  document as `<meta name="epubforge-watermark" content="…">`. Nothing renders
  it, nothing speaks it, nothing paginates around it, and the shop still finds
  it in the file it stamped, in the document it stamped.
* **remove** — the token is deleted.

Neither of the last two is a default and no preset reaches either, for one
reason: **K1**. *No character of the book's text is lost* is this project's
spine, and taking the token out of the reading order loses a character of the
reading order. That is a small, deliberate, well-argued loss and it is still a
loss, so it is something a person chooses rather than something that happens to
them — the owner's standing rule about deletion, applied to a case that is not
quite deletion. `remove` reports itself as a **warning** rather than a fix,
because it is the one place the tool destroys something a publisher put in the
file.

`--keep-watermark-markup` still works and now means `--watermarks keep`.

### A hammer instead of a star

The icon was an open book with a four-pointed spark, which was a perfectly good
mark for a tidying utility and said nothing about a forge. Same tile, same
book, same ember colour, same corner — a hammer in it.

### A third bucket, for what container-only mode is not allowed to reach

0.2.15 recorded the message shapes for the first time and named all four
remaining defects — a non-integer `width` (7) and `height` (4), `valign` (6),
and `value` on a list item outside an ordered list (5). Every one is markup
XHTML 1.1 allowed and HTML5 does not, in a document that mode promises not to
open, and every one is translated into CSS by the modes that do open documents.

Counting those against the release makes the corpus permanently unclean for
keeping a promise — which is exactly the mistake `carried` was invented to
correct, one floor up. So the ledger gains `inherent`, and it does not count
against a clean run.

**The safeguard is the whole design.** The obvious criterion — "the full
rebuild came out clean, so the difference must be the contract" — would have
excused 0.2.11's missing `properties="svg"`: a package container-only mode
generated and got wrong while `preserve` got it right, on nineteen books. So
the excuse is gated on the tool having **named the construct itself**, by
reporting `xhtml.epub2-only-markup`. An error it does not understand is still
counted against it, and the detector now covers all four shapes rather than the
two it was written from.

Checked against 0.2.15's own signatures: all ten are named, so under this rule
that run reads clean. **It is not rewritten to say so.** The ledger records what
the tool said on the day — the same reason 0.2.9 was left standing under a rule
already known to be wrong. 0.2.16 will say it for itself, or this note is a
prediction that was wrong.

**Also:** the About dialog said MIT. It has said GPL since 0.2.14 everywhere
else, which is the kind of thing that only gets found by somebody opening the
window.

## 0.2.15 — alpha — 2026-08-09

### Container-only mode now says what it cannot reach

The corpus found eleven books gaining exactly one `RSC-005` each in the mode
that opens no documents, and the sentence behind it — see below — was always the
same: `<img width="50%">`, which XHTML 1.1 allowed and HTML5 does not. This mode
edits the head and nothing else, so it stays, and the output is an invalid
EPUB 3 through no fault of the content.

That is not a defect to chase, it is a limit to state. A reader who runs a
validator gets a schema complaint with no hint that the answer is "rebuild in
another mode", and now the report says it: **markup legal in EPUB 2 and not in
EPUB 3 stays untouched in this mode: img[width]** — with the pointer to
`preserve`, which moves it into CSS and renders the same.

Checked against six real books of that shape: six warnings, six EPUBCheck
errors, and the construct named in the warning matched the validator's message
in every one. It names what it found rather than claiming to know the whole
class — anything not listed still shows up in a validator, and that is the
honest limit of a check written from six examples.

### The identifier stopped being enough, so the sentence is kept too

0.2.14 over the same ninety-three books: filling the empty `<title>` closed four
of the fourteen errors container-only mode introduced. **Eleven books now gain
exactly one each, and all eleven are `RSC-005`** — which turns out to be
EPUBCheck's catch-all for *this file does not match the schema*. Eleven books
breaking on one identifier said only that something in a document was wrong. A
code that covers a hundred defects is a smoke alarm that says "building".

So a verdict now records the message as well, with every quoted literal that is
not a plain markup name replaced by `…`. `element "img" not allowed here` keeps
its `img`, because that is HTML's word; `value of attribute "id" is invalid:
"…"` loses the value, because that one came out of somebody's book. Element and
attribute names are vocabulary; values, paths and fragments are not.

It answered on the first shelf it met — mine, six errors across thirty-two
books:

```
4  RSC-005: value of attribute "height" is invalid; must be an integer
2  RSC-005: value of attribute "width" is invalid; must be an integer
```

`<img width="50%">`. XHTML 1.1 allowed a percentage there; HTML5 wants an
integer. The modes that rewrite content move it into CSS and come out clean;
container-only mode does not open the document, so it stays.

Which makes it a decision rather than a defect, and the same shape as `carried`
against `introduced` one floor up: the book arrives valid as EPUB 2 and leaves
invalid as EPUB 3, because the package was upgraded around content the mode
promises not to touch. The options are written down in the roadmap; the choice
waits for the full list of shapes from the next run, because a criterion built
on `width` and `height` alone would be built on two thirds of the evidence.

A verdict that found something and cannot explain it is no longer reused — the
same rule the identifiers got, for the same reason. A clean verdict carries no
explanation and needs none.

## 0.2.14 — alpha — 2026-08-09 — kamień milowy [4] [5]

### Roadmap point [5], and a switch on everything that deletes

**Anything the tool removes is now optional to untick.** The owner asked for it
as a standing rule rather than about any one feature: *whatever the application
ever deletes should be either optional to untick, or something it asks about
first.* He is right, and the reason is in this file's own history — every
removal here looked obviously safe until a real book showed it was not. One
checkbox, **Usuwaj to, co nic nie robi**, ticked by "force the standard" and
untickable there as well; `--remove-dead` and `--keep-dead` on the command line.
Unticked, the report still counts what it found and where.

**[5] itself: unwrap, never delete, and only 90 spans deserve it.** Measured
over 12 475 spans in thirty-two commercial books before a line was written:
97.1% do something, 21 carry an attribute that means something, 90 have a rule
that reaches them and says nothing, and 256 have no rule at all.

That last group is why the measurement came first. Its largest class is
`dropcap` — **219 of them**, the drop caps whose stylesheet point [4] had just
reconnected. A rule keyed on "nothing styles it" would have deleted 219 drop
caps the moment after they were repaired. `antique`, `hagrid`, `sans` are the
same shape: a class nobody defines is a record of what the publisher meant, not
rubbish. `hagrid` on a span says how a character should sound.

So the condition is **a rule exists and everything it says is inert** — a
statement about the stylesheet rather than about our ignorance of it. The 90
that qualify are all one thing, conversion from PDF: `.reset { margin: 0;
padding: 0 }` on an inline box where those are the defaults, and `.black
{ color: #010000 }`, which is black moved by one part in 255 because the
converter copied the exact ink out of the page. The span is unwrapped; the text
inside stays exactly where it was.

On the real books: *Book 1* loses **one** span, not
219. *Book 2*, whose 1 906 spans are all deliberate italics, loses none.

**A text-ordering bug fell out of it.** The unwrap helper attached the removed
element's tail to the element *before* it, so `<p>x<span>b<i>i</i>t</span>c</p>`
put the `c` in front of the `<i>` — every character still present and two of
them in the wrong order. K1 compares a stream in order, so it would have read as
text lost. Fixed, with a test that reads the order back out.

### The licence is now GNU GPL v3 or later

Changed from MIT at the owner's decision. You may use, study, change and
redistribute; whatever you make of it has to be GPL too, with its source open.
A closed product built on this code is not permitted. The change is
prospective — anything anybody took under MIT stays under MIT, and with no
forks in existence, nobody did.

The `LICENSE` file is the verbatim FSF text; `pyproject.toml` carries the SPDX
expression. Attribution now says what actually happened: concept, design,
decisions and direction by the owner; the code written by language models under
his direction, on his account, to his choices.

Worth recording because it constrains any future change: the application already
links **two LGPL libraries** — Qt/PySide6 and cssutils. Their terms apply
whatever licence this project carries, and require that a distributed binary let
those libraries be replaced.

**Also:** both READMEs now carry a language button at the top instead of a line
of italics buried under the navigation.

### …and the other half: rules for markup the book has not got

Polish shops ship one house stylesheet into every title they sell, and most of
it is for things the particular book does not contain. Measured over the same
thirty-two books: **3 995 rules, 64% of all CSS bytes**, naming a class or id
that appears in no document of the book they were shipped in — `td.proc4`,
`td.proc5`, `td.proc10` in a novel with no tables; `hr.dotted_line`, `hr.blue`,
`hr.pointa` in one with no horizontal rules. *Book 3*: 178 of 207 rules.
*Book 2*, which somebody made with care: 2 of 37.

`preserve` reports and keeps every byte; `strict` removes. That split was in the
roadmap before any of this existed, against a source document that wanted the
removal in `preserve` too, and the reasoning has not aged: a selector matching
nothing *in the documents we parsed* is not the same claim as a selector
matching nothing.

Four narrowings, each a case that would otherwise be got wrong:

* a selector list dies only when **every** branch does — `.dead, .alive` is a
  rule about `.alive`;
* a branch naming no class and no id is never dead, because deciding a bare `p`
  from a parse puts a book's whole running-text styling one bug away;
* an attribute selector, a pseudo-class or a `*` is never dead, because what it
  reaches cannot be settled by name;
* a book carrying a script is left alone entirely — a script can add a class,
  and then "matches nothing" is a statement about the file, not the reading.

**Nothing is reformatted, and that is not a nicety.** Rebuilding these sheets
through a CSS serialiser was measured too, and it dropped `@media` blocks
outright in **21 of 72** stylesheets. A removal whose method deletes a media
query while claiming to delete an unused rule is not a removal. So a scanner
finds where each top-level rule begins and ends, the dead spans are cut, and
every byte outside them survives as written — comments, indentation, vendor
hacks and the publisher's section headings. At-rules are never entered.

The cut is then checked rather than trusted: the sheet is re-parsed and the
survivors compared against the originals minus the ones marked dead, by a CSS
parser rather than by the scanner that did the cutting. A sheet that does not
match is put back untouched. On the measured shelf, 72 of 72 matched.

### Roadmap point [4]: the publisher's own rule, put back where the page can see it

Not unused classes — those cost nothing and are the small half of it. The half
the owner named: **a stylesheet that is correct and reaches no document.** The
archive still holds the rule, the page no longer sees it, and a typeset book
renders as raw HTML in the middle.

Measured on thirty-two commercial books before a line of it was written, and
that is the only reason it is this narrow — the first probe produced a false
positive that would have pasted a duplicate stylesheet into thirty-seven
chapters of *Book 1*. What survived the measurement:

* the document uses a class,
* nothing it links — no sheet, no `<style>` — defines that class,
* **exactly one** stylesheet in the book does, and this document does not link
  it.

Then there is nothing left to guess: the rule exists, it was written for that
class, and only one candidate can have meant it. On a real shelf that is **52
documents across 7 of the 32 books**, every one of them a single rule:

| book | class | rule |
|---|---|---|
| *Book 1* | `dropcap` | **37 chapters** open with `<span class="dropcap">`; the linked sheet defines only `.dropcap_small` |
| *Book 4* | `coverimage2` | `height: 100vh` |
| *Book 5* | `cover` | `margin: 0` |
| three titles from one publisher | `cover` | `height: 97%`, on a cover page linking no stylesheet at all |
| *Book 6* | `photo` | `text-align: center` |

**Four of the seven are covers**, and the rules are exactly the ones that make a
cover fill the screen. That is the owner's correction arriving as a
measurement: the exemption I proposed for cover pages would have skipped the
majority of the real cases.

The rule is copied into the document, not the sheet linked: a sheet is 20 kB of
somebody else's decisions, and what was lost is the one rule for the class the
page actually uses. Two sheets disagreeing is a choice between two publishers'
intentions on a page neither was written for, so nothing is done. A rule that
fetches something with `url()` stays where it is — its reference is relative to
the sheet, and rebasing a background three directories away turns a missing drop
cap into a missing picture. No case on the measured shelf needed one.

What is deliberately **not** reported: "this document uses a class nothing
defines". It fires on almost every book ever made — 34 documents in one, 134 in
another — because converters leave class names behind that nothing ever styled.
That is dead markup, not dead CSS, and it costs the reader nothing.


### The identifiers paid for themselves in one run, and a reader overruled a docstring

**All fourteen errors container-only mode introduced were `RSC-005`.** The
0.2.13 run recorded EPUBCheck's message identifiers for the first time, and the
thirteen books nobody could diagnose turned out to break on one rule. On the one
book of that shape I could reach — the owner's *Book 7*, sent separately —
`RSC-005` reads *Element "title" must not be empty*.

That makes them ours, not the source's. EPUB 2 allowed an empty `<title>`;
EPUB 3 does not, and this mode rebuilds the package as EPUB 3 around content it
refuses to open. The book was legal when it arrived and illegal when it left,
without a byte of its content changing. So an empty title is now filled on the
bytes, from the document's own heading — **the second edit this mode makes
inside a document, and the same kind of edit as the first**: a `<title>` is not
rendered in the body, so nothing on the page can move. Thirteen books diagnosed
and fixed without anybody sending a book, which is the entire reason the
identifiers were added.

The same repair had been happening silently in the modes that rewrite content
since long before this. It has a name now — `xhtml.title-filled` — reported once
per book rather than once per document.

**A page pinned to the foot of the page is put there in the flow, not deleted.**
The declaration used to survive outside `strict` on this reasoning, quoted from
the code: *publishers use it deliberately — a rule named `.dol` ("bottom") pins a
dedication to the foot of the page, and that is intent, not a mistake.* That was
an inference from a class name.

Then the owner put all three modes on a reader. In the mode that kept the
declaration, **the dedication page was blank**: `div.dol { position: absolute;
bottom: 0 }` took the only content on that page out of the flow and pagination
went round it. In `strict`, where the declaration was dropped, the page was
there — with the dedication at the top, which is not what anybody asked for.

The first fix here deleted the declaration everywhere, and that was wrong for a
reason this file's own module docstring has stated since the beginning: *a
construct that carries visual meaning is translated into the conforming
equivalent that renders the same way, never simply deleted.* The owner put it
plainly — what matters is not the rule, it is that the page keeps looking the
way the publisher wanted. Deleting it was the tool breaking its own rule.

So it is translated. `margin-top: auto` inside a flex column puts a block at the
foot of the page exactly as `bottom: 0` was meant to, and keeps it in the flow,
so pagination cannot lose it. Written into the one document that needs it and
never into the shared stylesheet: flexing every `<body>` in a book would stop
adjacent margins collapsing on every page of it, which is a change to the whole
book in service of one page. The publisher's declaration stays where it is,
superseded rather than removed.

Narrow, and only where the translation is provably faithful: reflowable books;
the positioned element the sole element child of `<body>`, which is what "this
page is that block" means; `bottom` set and `top` unset. Everything else — a
block stretched between both edges, centred, or sitting among siblings — is
kept and reported, because guessing at somebody's layout is how a tool that
means well ruins a book. Fixed-layout is untouched: the viewport is declared,
nothing paginates, and out-of-flow positioning is how the format works.

`strict` translates it too rather than deleting it. The in-flow form is
conforming, so the two stopped disagreeing here.

Blast radius, measured rather than guessed: **one book in ninety-three** uses
out-of-flow positioning at all, and it is the book the page vanished from.

**Also:** the Polish README links to the English one again. It had done since
0.2.3 and stopped when the README was rewritten.

## 0.2.13 — alpha — 2026-08-09

### 0.2.12 measured: half the introduced errors gone, and a run that can now say which

**Ninety-three books, three modes: 24 carried and 20 introduced became 14 and
14.** The `properties="svg"` fix closed every book I had locally. Thirteen books
I have never seen still gain one EPUBCheck error each in container-only mode,
and the run could not say *what* they gain, because a signature recorded how
many errors and not which.

**So it records which.** EPUBCheck stamps every message with an identifier from
its own fixed vocabulary — `RSC-005`, `OPF-014`, `HTM-004` — and that identifier
is the one part of a message that is neither the book's text nor a path inside
it. Recording it keeps the promise the corpus was built on and still answers the
question. A run now ends with a line naming the rules: *Ours, by EPUBCheck rule:
OPF-014 ×13.* A verdict recorded before the identifiers existed is no longer
reused, because a private corpus never changes its books and would otherwise
keep serving countless old counts for ever.

**The green streak counts only across releases where the measurement did not
change.** Agreed with the owner, after he pointed out that three green metrics
had happened long ago and the counter kept going back to zero. He was right, and
the cause was systematic: every run but one asked a larger question than the run
before it — 38 books, then 70, 87, 91, 93, then the same 93 in a third mode — and
each of those reset the count. The only way to reach "green across three
consecutive releases" was to stop adding books. A release that widened the
measurement is now passed over rather than counted against, `widenings()` names
them so the gap is on the record, and the ledger records which modes a run
measured — because `minimal` widened the corpus without moving the book count by
one and nothing noticed. What stops a real defect hiding in the gap is that it
does not go away: the next run at unchanged scope finds it, and that one counts.
The streak today is nonetheless zero, honestly — 0.2.11 and 0.2.12 measured the
same books in the same modes and both introduced errors.

**The cover needs its stylesheet, and I had said otherwise.** Asked how to catch
Calibre's characteristic damage — a stylesheet that is correct but reaches no
document — I proposed exempting the cover page, reasoning that a page holding one
image does not need one. The owner corrected it: a cover is a fixed number of
pixels and screens are not, so without a rule sizing it the reader falls back to
the image's own dimensions and the same file is a stamp on one device and cropped
on the next. The cover is the *worst* candidate for an exemption — it is where a
missing stylesheet shows first, on the first screen of the book.

The mechanism was already there in two places and under no test at all, which is
how something important gets broken by accident. `tests/test_cover_scaling.py`
now pins all three halves of it: an author's sizing survives every mode
untouched, wherever it lives; a cover nothing sizes gets `max-width`/`max-height`
added and reported; a cover page we generate is born with them. No rule is ever
dropped for being used by one document — a cover rule is used by exactly one
document by definition, so a pruner that counts uses is a pruner that deletes
precisely this. That is the difference between this and a tool that clears
everything without looking.

### 0.2.7 measured, and the one rule id that named the wrong stage

The owner's run on 0.2.7 — **91 books, zero EPUBCheck errors, zero fatal, no
text lost, nothing unwritten.** The seven books 0.2.6 could not make conformant
come out clean, and the four generated edges were built from the window. It is
also the first run the application logged into the ledger by itself; every entry
above it was typed in by hand. The green streak starts at `0.2.7` and needs two
more. *(Superseded: under the rule agreed after 0.2.12, a release that widened
the corpus is passed over rather than counted, and 0.2.7 widened it twice —
91 books, then 93. The streak reads zero today, from 0.2.11 and 0.2.12.)*

Coverage stands at eight families of ten. `word` and `pdf-or-ocr` are one book
short each, and those two have to be real: a provenance family exists because a
converter leaves defects nobody would think to invent, so a synthetic "Google
Docs export" would test my idea of Google Docs rather than Google Docs.

The survey over those 91 books caught something no test did. Of 135 rule ids,
**one** was reported under a stage its prefix did not name:
`css.remote-import-removed`, emitted by the content stage, whose findings carry
`stage: "xhtml"`. The prefix is not decoration — it is how a report is grouped
and filtered — and the repair genuinely happens in two places, so it now has two
ids: `xhtml.` for an import inside a `<style>` element, `css.` for one in a
linked sheet. Two ids are not duplication when they send you to two different
places to look.

The check that found it was ninety-one real books on the one machine that has
them, which is the slowest feedback available and not available to anyone else.
It is now an AST walk over the stage modules, in a tenth of a second, and it
fails if the pair is broken back apart.

## 0.2.12 — alpha — 2026-08-08

**One real defect, and three thresholds a real shelf settled.** The release the
profile was cut to make possible: ninety-three books measured, and every number
in it either moved or was confirmed by them rather than by six.

### At a glance

| | |
|---|---|
| 44 errors split into 24 carried, 20 introduced | and the 20 were a real defect |
| Container-only mode, 19 valid books in, errors out | it rebuilt an EPUB 3 package without checking its claims |
| 29 books of 93 had no paragraph paradigm | `margin: 1em 0` was invisible to the measurement |
| `SPACED` declared on 1 paragraph out of 3413 | a ratio over a sample of one is 1.0 |
| `BODY_TEXT_SHARE = 0.60` | confirmed: 0.57 below it, 0.62 above, the threshold in the gap |

### Everything, by subject

### A verdict has to rest on most of the book

Nine books held a paradigm decided by under a tenth of their text, one of them
by a single paragraph out of 3413 — and one of the three `MIXED` findings, the
signal this whole measurement exists for, rested on 3.5% of its book.

`PARADIGM_COVERAGE` is new and the shelf chose it. Coverage across the 93 is
sharply bimodal: 38 books under 10%, **nothing at all between 10% and 33%**, 41
in the 90–100% band. Half is a plain sentence — most of the book — and it sits
inside the empty stretch, so nothing hangs on the exact figure. The coverage
travels beside the verdict now, because it is what says whether to believe it.

### The mode that promises to break nothing was breaking something

0.2.10 taught the corpus to tell a defect *carried* from a defect *created*.
The first run under that rule split the 44 errors into **24 carried and 20
introduced** — and the second number is a real defect in container-only mode,
across 19 books whose sources were clean.

`The property "svg" should be declared in the OPF file.` Calibre wraps a cover
in `<svg>` and writes an EPUB 2 package, where no such declaration exists. We
rebuild the package as EPUB 3, where it is required — and the code that works
manifest properties out lives in the branch container-only mode skips. So the
mode regenerated a package that made a claim it had not checked.

The fix costs nothing: that branch already parses every document to collect
ids, and reading properties writes no bytes. The promise is intact — the
documents come out byte for byte identical, and a test says so.

**Under the old rule this was invisible.** All 44 errors were one number, and
the honest reading of that number was "the sources' own defects, carried
faithfully" — which was true of 24 of them and quite wrong about the other 20.

### A third of a real shelf had no paragraph paradigm at all

Of 93 books, 61 came out consistent and 3 `MIXED`. The remaining 29 came out
`UNKNOWN`, and that is a measurement failure rather than a fact about the books:
this looked for `margin-top` and `margin-bottom` written in full, and most
people write `margin: 1em 0`.

It never showed on the six Project Gutenberg books this was built against,
because their stylesheet happens to use the longhand. Six books cannot find a
gap that six books do not have — which is the whole argument for the corpus,
demonstrated on the first shelf it met.

The shorthand is expanded now, in all four of its forms.

**What the shelf did say**, and it is the number this release was cut for: after
the four-bucket fix, only **3 books in 93 came out `MIXED`** — and the inventory,
which arrived after this paragraph was first written, showed one of those three
resting on 3.5% of its book. Two survive the coverage floor above. The count was
right and the confidence in it was not, which is the same mistake at a smaller
scale as the one the floor exists to stop.

83 have a consistent body-text shape, 74 carry dead classes and 58 carry
duplicate ones — which is point [4] justified in figures rather than in
expectation: median 30 dead classes per book, maximum 210.

## 0.2.11 — alpha — 2026-08-08 — kamień milowy [3]

**Roadmap point [3]: the book is measured, and nothing is touched.** The
foundation points [4], [5] and [7] each need, built where the roadmap said it
would be cheapest to build it — with zero risk of regression, and with every
threshold calibrated against real books before anything depends on one.

### At a glance

| | |
|---|---|
| A profile computed once, between metadata and content | read by nothing yet, on purpose |
| "Changes nothing" | held to bytes, not to intent |
| Six real books moved a threshold on day one | which is what the constants were named for |
| Three of six single-source books read `MIXED` | so the rule was wrong, not the books |
| The profile goes into the inventory | because that is the file a private shelf can send |

**New:** `epubforge/profile.py`, `ProfileStage`, nine `INFO` findings in both
languages, a `profile` block in every inventory entry, and a `stages` argument
to `rebuild()` that exists for one test.

### Everything, by subject

### Roadmap point [3]: the book measured, and nothing touched

A statistical profile of a book, computed once, so that points [4], [5] and [7]
share one answer to *is this construction this book's rule or its exception*
instead of guessing separately three times over. What it measures: the shape of
the body text and whether the book has one at all, how paragraphs are separated,
which classes are dead and which are duplicates, where the scene breaks, the
`<br/>` runs and the unmarked headings are.

**It changes nothing in anybody's book**, and that is held to bytes rather than
to intent: a rebuild with the stage and a rebuild without it, every resource
compared. `rebuild()` takes an explicit stage list now, for that question and no
other.

### The first six real books moved a threshold, exactly as planned

The roadmap said every number here would be a named constant because the first
contact with a real shelf would change them. It took six books.

The paradigm rule counted a paragraph that was indented *and* spaced on both
sides, which made "this publisher indents and leaves a little air"
indistinguishable from "half this book came from somewhere else". Three of the
six Project Gutenberg books — single-source by construction — came out `MIXED`.
That is what said the rule was wrong rather than the books.

There are four buckets now: `INDENTED`, `SPACED`, `BOTH` for a book that
consistently does both, and `MIXED` for one that cannot make up its mind — which
is the only one that means two files were glued together. All six now land on a
consistent verdict and none is `MIXED`.

The spacing floor moved with it. Gutenberg writes
`p { text-indent: 1em; margin: 0.25em }`, and a quarter of an em is four pixels:
breathing room, not a paragraph break. `SPACING_FLOOR_EM` is `0.5` and sits
*above* the indent floor, because the eye reads the two differently. Six books is
thin calibration and the constant says so.

### The numbers have to land where somebody can send them

A survey says "twelve books came out `MIXED`". A threshold needs the
distribution behind that count, and the inventory is the file that carries
per-book numbers and nothing else — no titles, no text, safe to send from a
private shelf. Every entry now holds a `profile` block, measured from the parse
the inventory was doing anyway.

That is the whole reason this release exists rather than waiting: six books is
thin calibration, ninety-three is not, and none of them are on this machine.

### The rule catalogue caught a cleverness

Three findings were raised from a loop over a table of `(count, rule id)`, which
is three lines shorter and makes the whole set invisible to a search for the id.
`tests/test_rules.py` requires the id to be a literal at the call site and failed
on the first run. Unrolled.

## 0.2.10 — alpha — 2026-08-08

**The corpus marked itself down for keeping a promise.** One release, one
subject: the run summary could not tell a defect carried from a defect created,
so the mode that promises not to touch content was scored for the defects it
faithfully carried.

### At a glance

| | |
|---|---|
| 44 errors, 31 books, all in `minimal` | `preserve` and `strict`: zero on the same 93 |
| Nothing had ever measured the sources | so both kinds of error counted as ours |
| Alpha needs three green releases in a row | the corpus could never be green again |
| A signature now records the source's verdict | read once; a book's id *is* its hash |
| 0.2.9's entry in the ledger | left exactly as measured, not back-dated |

### Everything, by subject

### The corpus marked itself down for keeping a promise

The first run to measure `minimal` over the owner's library reported **44
EPUBCheck errors across 31 books** and called itself unclean. `preserve` and
`strict` came out at **zero** on the same 93 books, with signatures identical to
the 0.2.7 run apart from one rule id renamed on purpose.

All 44 sit in the one mode that promises *not* to touch content. A container-only
rebuild leaves every document byte for byte, so a source whose XHTML is invalid
stays invalid — deliberately, because the alternative is editing content in the
mode that exists to promise it will not. Nothing had ever measured the sources,
so the summary had no way to tell a defect carried from a defect created, and
counted both as ours.

Left alone this made the alpha condition unreachable: "green across three
consecutive releases" could never happen again, because the corpus was scoring a
kept promise as a failure.

* **A signature now records the source's own EPUBCheck verdict.** A book's
  identifier *is* the hash of its bytes, so this can never go stale for a book
  that still exists: read once, then reused for as long as EPUBCheck does not
  change. One extra validation per book, once, ever.
* **`minimal` is judged on what it introduced**, `preserve` and `strict` on what
  they left behind. The check keeps its teeth — container-only mode may carry a
  defect and may never create one.
* The run summary says whose errors they were, because a bare "44 errors" reads
  as failure and this was not one.

The 0.2.9 run is in the ledger exactly as it was measured, `clean: false` and
all. It is not back-dated: I cannot validate books I do not have, and editing a
measurement to match a hypothesis is the one thing that ledger exists to
prevent. The streak is empty and starts again from the first run under the
corrected rule.

## 0.2.9 — alpha — 2026-08-07

**0.2.8 made the corpus run slower and pushed the machine to 95%.** That is
this release's whole subject: a regression I shipped, reported within the hour,
and it was mine rather than the hardware's.

### At a glance

| | |
|---|---|
| Eight JVMs, each sized for the whole machine | over a hundred GC and JIT threads for eight cores |
| 95% CPU and a longer wall clock | a computer working hard at coordinating itself |
| `-XX:TieredStopAtLevel=1` | the large one: 17.4s → 7.7s, four at a time |
| `-XX:ActiveProcessorCount=1`, `-XX:+UseSerialGC` | the rest: 7.0s together |
| `-Xmx512m` | measured, changed nothing, **not shipped** |

**Fixed:** a single validation drops from 10.1s to 5.3s, so this helps one book
in the window as much as it helps ninety-three in the corpus. The full corpus
run here went 88.5s → 53.2s on four throttled cores; the effect is larger the
more cores a machine has, because oversubscription is what it removes.

### Everything, by subject

### A JVM assumes it owns the machine, and eight of them cannot all be right

Making the corpus parallel without saying anything to the JVM was the mistake.
Each one sizes its garbage collector and its compiler threads from the core
count — correct for a server running for a week, wrong for a process that
validates one book and exits, and catastrophic eight at a time.

Measured rather than reasoned about, one book, four validations at once:

| options | wall |
|---|---|
| none | 17.4s |
| `TieredStopAtLevel=1` | 7.7s |
| `ActiveProcessorCount=1` | 12.8s |
| `UseSerialGC` | 16.0s |
| all three | 7.0s |

`TieredStopAtLevel=1` is the large one and it is not about parallelism at all:
EPUBCheck runs for a few seconds, and the optimising compiler never earns back
what it costs to run. The other two stop each JVM from starting a collector
sized for every core on the machine.

`-Xmx512m` was measured in the same pass and made no difference whatsoever, so
it is not shipped. A heap cap that buys nothing can still make a large book fail
to validate, and a false error is worse than a slow answer.

HotSpot *fails to start* on an `-XX:` option it does not recognise, so the
options are probed once per interpreter — that java, those flags, `-version` —
and dropped as a group if it does not come up. A user may point `EPUBCHECK_JAR`
at any runtime they like, and OpenJ9 is not HotSpot.

The options are invisible to `checker_identity()`, which decides whether a
recorded verdict may be reused: JIT and GC settings cannot change a verdict, and
treating them as a different validator would have discarded every cached answer
in the corpus.

## 0.2.8 — alpha — 2026-08-07 — **kamień milowy: prywatny korpus**

**Roadmap point [1] is closed.** Not on a total — sixty-four books were once
called enough — but on the condition the roadmap actually states: every family
represented, counted by a program rather than remembered.

### At a glance

| | |
|---|---|
| 93 books, ten families of ten | zero errors, zero fatal, no text lost |
| The corpus justified a family with a mode it never ran | `minimal` is measured now |
| The run sat at 6% CPU on eight cores | a reused verdict skips the JVM entirely |
| Every book built into `scratch/preserve.epub` | side by side that is a race, so each gets its own |
| Two run ledgers tracked by accident | evidence for nothing, gone |

**Closed:** the first roadmap milestone. **Faster:** a check where nothing moved
is **5–6×** quicker, measured — work removed rather than spread out. **New:**
`--workers N`, `checker_identity()`, `workers_for()`.

### Everything, by subject

### Roadmap point [1] is closed, measured rather than remembered

**93 books, every family represented, the run clean** — zero EPUBCheck errors,
zero fatal, no text lost, nothing unwritten. Two books closed the last two
families; the other 91 measured identically to the run before, so nothing broke
on the way.

### The corpus was justifying a family with a mode it never ran

The family table asks for fixed-layout books and comics as "a test of whether
minimal mode engages", and the corpus measured `preserve` and `strict` only. The
family was filled for a purpose nothing measured — the same shape as counting
books instead of counting families, one floor up.

`minimal` is now measured. The first run after this re-measures every book once
and prints `minimal: not measured before` against each: not a regression, a
reading that did not exist. That line is deliberate — the change first made
every book report its whole `minimal` block as a difference, ninety lines each,
ninety-three times, for a change in what is measured rather than in how a book
rebuilds.

### The corpus ran at 6% CPU, and a third more work just landed on it

On an eight-core desktop: one JVM at a time, fifteen threads idle. Four fifths
of the wall time is EPUBCheck, and 93 books across three modes is 279 starts of
it, one after another.

* **A recorded verdict is reused when it cannot have changed.** EPUBCheck is a
  pure function of the jar and the bytes it reads; both are compared, and either
  one moving means it runs again. The jar is identified by the hash of its
  bytes, recorded beside the verdict — a version string is cheaper to read and
  worse to trust. On a check where nothing has moved this skips every JVM start
  there is: **5–6× faster**, measured, and it is work removed rather than work
  spread out, so it does not depend on the machine.
* **Books are measured side by side**, threads rather than processes: the
  expensive part is a subprocess wait, and a process pool inside a frozen
  Windows GUI without `freeze_support` relaunches the application once per
  worker. Capped at eight, because each JVM wants a few hundred megabytes.
* Everything about the *source* is now read once per book rather than once per
  mode — two inventory passes and a spine-text parse that had been thrown away
  and redone three times over a file that had not changed.

Results still come back in shelf order however the pool finishes, and every book
gets its own scratch directory: they all built into `scratch/preserve.epub`
before, which side by side is two threads checking a file the other had just
overwritten — a race that produces a plausible wrong answer rather than a crash.

`--workers N` on the command line for anyone who wants to pick.

## 0.2.7 — alpha — 2026-08-06

**The first conversions the corpus ever held broke three things, and the
detector could not see three families it was asked to count.** A plain release:
the InkBOOK fix needs a build to be confirmed on the device, and the owner needs
one whose family numbers can be trusted before going out to fill the gaps.

### At a glance

| | |
|---|---|
| Seventeen files made for six empty families | seven of them landed nowhere |
| `fixed_layout` reads a declaration a comic never makes | so three comics counted as zero |
| The first comic rule called Pan Tadeusz a comic | a share of documents measures how a book was split |
| Five MOBI back-conversions, one error each | `value` on a bullet in `<ul>` |
| A stylesheet fetched from Google, in a Word family book | EPUB 3 allows one remote resource, and it is a font |
| A link to an anchor no document defines | what a PDF reflow leaves in a page-number strip |
| `rendition:` used and never declared | the InkBOOK case, closed on the device |
| The pathological family needed a command line | it needed a button, and now has one |
| Coverage was printed only where nobody was looking | the window shows it |

**Fixed:** three conformance defects that only converted books produce, and
three family detectors that could not see the books made for them. **New:**
`strip_remote_imports()`, `xhtml.dead-fragment-dropped`,
`css.remote-import-removed`, and a `.gitattributes` so a signature diff shows
what changed.

### Everything, by subject

### A corpus family you could only fill from a command line

`pathological` sat at zero across four releases while every coverage report
named it as what was missing. The books have to be built — no publisher ships
one with four hundred chapters and no cover — and the thing that built them was
`tools/make_edge_cases.py`, importing from `tests/public_corpus.py`: a checkout,
a Python and a terminal.

The person who can fill that family runs Windows and the installer. "Just run
the script" was, to him, an instruction to do nothing, and I gave it four times.

* The four books moved into `epubforge/edge_cases.py` — one definition, two ways
  in: **Korpus → „Dołóż brzegi"** and the same script. Run twice it leaves four
  files, not eight, because the corpus counts books and a duplicate would
  inflate the family being filled.
* **Family coverage is now shown in the window.** It was written from the start
  and printed only by the command line, so the one question the inventory exists
  to answer was the one part not on screen.

A feature reachable only through a development environment is, to the person who
needs it, a feature that does not exist.

### The window now speaks one language at a time

Three places where it did not, all found while fixing the above:

* `coverage_report` had an English heading and English closing sentence over a
  table of Polish descriptions, whichever way the interface was set. Both
  languages now, chosen by the setting.
* The survey renderer wrote its own headings — "wersje źródła", "awarii etapu" —
  straight into the output, so an English window printed an English report under
  Polish headings.
* `tr()` used plain `str.format`, so a count in the interface could not agree
  with its noun: "Gotowe — 1 książek". It uses the message catalogue's formatter
  now, and `{count:książka|książki|książek}` works in window strings.

### Three defects the corpus found the day it first held conversions

Seventeen files arrived, made specifically to fill six empty families. Seven of
them came out of the rebuild with an EPUBCheck error the previous seventy books
had never produced — one error each, in `preserve` and in `strict`, none in
`minimal`:

| what | where it came from | how many |
|---|---|---|
| `value` on a bullet in `<ul>` | Calibre's MOBI back-conversion | 5 |
| a link to an anchor no document defines | Calibre's PDF reflow | 1 |
| `@import url(https://…)` — a stylesheet fetched from Google | Google Docs export | 1 |

None is our regression. Each sits in the source and survived because the
rebuild had no rule for it, which is exactly the failure the provenance
families exist to expose. The book that carried five of them went from **nine**
source errors to one; now it goes to zero.

* HTML 5 allows `value` on a list item only inside `<ol>`, where it sets the
  number. Inside `<ul>` it numbers nothing and no renderer has ever drawn it, so
  it goes — and stays where it means something.
* The file each dangling link names is present; the anchor inside it is not.
  What a PDF conversion leaves when it writes a page-number strip and gives only
  some pages an id. The fragment goes and the link lands at the top of the right
  document instead of nowhere.
* EPUB 3 permits one remote resource — a font declared on its manifest item —
  and a stylesheet is not one. The `font-family` declarations are untouched, so
  the book falls back exactly as it would have. No e-reader was going to fetch
  that font from Google anyway, and one that tried would be reporting the
  owner's reading to a third party.

### Six empty families, and a detector that could not see three of them

Of the seventeen new files, **seven landed nowhere**. That was a fault in the
measurement, not in the effort: a coverage number reading zero for a family
somebody has just filled sends them out to do the work twice.

* **`pdf-or-ocr`** — Calibre's PDF input rewrites `pdftohtml`'s class names to
  its own, so `ft0` is gone. It writes `PDF Reflow conversion` into a
  `<meta name="generator">` and names the pictures it lifts `index-<page>_<n>`.
* **`word`** — the family is "Word / Google Docs" and only Word had patterns.
  `kix` is what Google calls the editor inside Docs, and it numbers every list
  it exports with it.
* **`fixed-layout`** — a comic converted from CBZ declares nothing about layout:
  EPUB 2, reflowable, one `<img>` per document. `fixed_layout` reads the
  declaration, so three comics counted as zero.

The first rule written for the comics counted image pages as a *share* of the
spine, and called Pan Tadeusz a comic: that edition packs its whole text into
three documents and its three engraved plates into three more, which is 50%. A
share of documents measures how a book was split into files. What separates a
comic from an illustrated novel is that a comic has no prose at all, and that is
now measured directly — eighteen books in reach, three comics at **one**
character per page, the thinnest ordinary book at 2686.

Coverage after the fixes: eight families of ten. `word` and `pdf-or-ocr` are one
book short each; `pathological` is one button away — **Korpus → „Dołóż brzegi"**,
for the reason given above.

### The run ledger says 0.2.6 was not green, because it was not

The ledger held one 0.2.6 entry, clean, over seventy books. The same release
over eighty-seven found fourteen EPUBCheck errors. Both are recorded, and the
streak is empty — the entry conditions for alpha ask for three consecutive
green releases across the corpus, and that count starts again from 0.2.7.

A `.gitattributes` also arrives, because sixteen signature files written on
Windows showed all sixty of their lines as changed when one number had moved. A
diff that says "everything changed" is a diff nobody reads, which is the
opposite of what a signature is for.

### The InkBOOK case: a prefix we used and did not declare

Four rounds of bisection on the device, and the answer is one attribute:

```xml
<package prefix="schema: http://schema.org/">                          ← hangs
<package prefix="rendition: …/rendition/# schema: http://schema.org/"> ← opens
```

We emit `rendition:layout`, `rendition:orientation` and `rendition:spread`
without declaring `rendition:`. EPUB 3 reserves the prefix, so no declaration
is required and EPUBCheck says nothing. That reader resolves prefixes from the
`prefix` attribute and from nowhere else.

It explains the paradox the case opened with. The file with 148 validation
errors opened because it declared `rendition:`; ours with none hung because it
did not. Conformance was never the subject.

The argument for declaring reserved prefixes **was already written down in this
file**, beside `schema:` — "declaring it is redundant under 3.3 and legal, so
it costs nothing and restores those readers". The same reasoning, the same
situation, `rendition:` instead of `schema:`, and it was applied to half the
cases.

The attribute is now computed from the finished document: every
`property="x:y"` and `scheme="x:y"` that ends up in the package gets `x`
declared. Deciding it up front meant deciding it twice — once where the
attribute is built and once wherever a property is emitted — and those two are
what drifted.

Excluded on the device along the way, each by a variant differing in one thing:
the entire archive level (K0 settled that our packaging is fine), the container,
the navigation document, the NCX, dotted manifest identifiers, the missing
`dcterms` declaration, EPUB 3 refinements, the `schema:` accessibility block
from both sides, and whitespace between elements. Two of those were my own
loudest hypotheses — `S_IFREG` and the pretty-printing — and both were wrong.

### "Table of Contents" headed every Polish book this program made

The generated navigation document carried English headings — "Table of
Contents", "Landmarks", "Page List" — inside books whose own `lang` attribute
says `pl`. These are the only words this program puts in front of a reader
*inside their book*, and they were English in every file it has ever produced.
The bilingual report made it worse rather than better: the one piece of text
nobody could change was the piece printed in the book itself.

`NAV_HEADINGS` holds them per language, falling back to English for a language
nobody has written — the same rule the message catalogue uses, and for the same
reason: a heading in the wrong language is a blemish, and a book that fails to
build is not.

Found while diffing our rebuild against a file an InkBOOK Focus opens, which is
not what that comparison was looking for and is the more useful of the two
findings.

### E, F and G all failed, which is a result

The friend tested all three. None opens, and that exhausts the archive level:
timestamps, Unix attributes, `S_IFREG`, directory layout and compression are
all excluded. The case file has said since it was written what to do when this
happens, and `tools/bisect_reader.py` does it.

A container-only rebuild leaves **71 of 75 entries byte for byte** as they were,
so four files carry the difference. The tool writes five variants, ours in every
respect except that each differs from the original in exactly one of the four —
plus a control holding only the original's files, because if the device refuses
that one the packaging is at fault and the other four prove nothing.

Four steps, one answer, and no debugger on a device nobody can attach one to.

### The corpus keeps a log of its runs, because a signature cannot

Stamping the release into each signature made a partial run visible and still
could not answer the condition it was added for. A signature holds a book's
**latest** measurement, so re-measuring a book erases the release it was green
on before — after the owner's full run on 0.2.6, the 0.2.5 evidence was simply
gone. "Green across three consecutive releases" is a question about history,
and history is exactly what per-book files do not keep.

`tests/corpus/runs.json` is appended on every `--record`: the release, the
date, how many books, and whether it came out clean. `green_streak()` reads
that, and takes a minimum book count — a run over three books says nothing
about a corpus of eighty-six, and letting it extend a streak would be the same
mistake as counting books instead of families.

The ledger lives **beside** the signature folder rather than in it, because
that folder means one file per book: the owner's inventory landed there once by
accident and broke the analysis on the spot. `signature_files()` now recognises
a signature by its name — sixteen hex characters — so a stray document cannot
pass for a book that never existed.

**Where the corpus stands: 86 books, and the streak is `0.2.5 → 0.2.6`.** One
more clean release closes half the last alpha condition; the other half is the
six empty families.

### The watermark fix, checked against the shelf it was written for

The owner's full run on 0.2.6, 70 books: **zero EPUBCheck errors, zero fatal,
no text lost, nothing unwritten**. Of the 63 that are not Project Gutenberg,
the inventory now finds a watermark in **42** — it found four before the fix,
on a smaller sample of the same library. 35 carry the hidden marker, 13 a
readable notice, and all 63 a legal page.

Nineteen books changed against their recorded signature. All nineteen were the
ones still measured on 0.2.4, and every change was a rule identifier appearing
— none disappeared, no counter moved, nothing outside `rules` differed at all.
That is what naming the 57 untagged findings was supposed to look like from the
outside.

## 0.2.6 — alpha — 2026-08-06

**The inventory now measures the kind of watermark Polish shops actually use,
which is the one it could not see.** A plain release: the owner has his library
to hand and needs a build whose numbers can be trusted before running it.

### At a glance

| | |
|---|---|
| The inventory saw 4 watermarked books where the pipeline saw 29 | one definition now, held by a test |
| A style attribute made optional inside a tag pattern | matched empty against tags that had one |
| The bookshop family counted the watermark only | the roadmap says "znak wodny, **strony prawne**" |
| A signature never said which release measured it | stamped, so a partial run reads as partial |
| The stamp then reported every book as changed | it says *when*, so it is out of the diff |

**Fixed:** `watermark.marks()` is the single definition, used by the inventory
and the content stage both. **New:** `releases()` and `green_streak()` answer
the alpha condition from the files instead of from memory.

### Everything, by subject


### The corpus says which release measured it

Entry into alpha asks for the corpus to be green "across three consecutive
releases", and a signature said nothing about which release produced it — so
the condition could only be answered from memory. That is the same shape as the
family count, which was answered from memory and was wrong.

Every signature carries the release now. A partial run stamps only the books it
touched and the rest keep the release they were last measured on, so a mixed
corpus reads as mixed instead of quietly topping up a streak it did not earn.
`releases()` and `green_streak()` report it.

The owner's first partial run, on 0.2.5: **38 books, zero EPUBCheck errors,
zero fatal, no text lost, nothing unwritten.** Nine of them are books the corpus
had not seen before. All 29 books measured on both 0.2.4 and 0.2.5 gained rule
identifiers and lost none — the shape you would expect from naming the 57
findings that had none, and the reason to record the distribution at all.

### The inventory could not see the kind of watermark shops actually use

The owner said every book he buys is watermarked. The inventory said four out
of thirty-two. He was right and the inventory was wrong, and the proof was
already in the same archive: on those same books the **pipeline** found and
consolidated a marker in **twenty-nine** of them.

Polish shops watermark with an opaque token hidden by an inline style, not with
a sentence. The inventory looked only for a readable notice and recorded the
answer in a field called `watermarked` — a name that claimed the whole idea
while measuring a third of it.

The cause is the familiar one: two implementations of one concept. `watermark.marks()`
is the only one now, and both the inventory and the content stage go through
it. `tests/test_corpus_coverage.py` runs both over the same book and fails if
they disagree, which is the check that would have caught this without a shelf
of real books.

One bug found on the way: the pattern made the style attribute optional inside
the tag, so it matched the empty string against tags that *did* carry one and
scored every marker as unstyled — which is to say, as nothing. The attributes
are captured whole and the style picked out of them afterwards.

### Half a definition counted a family as empty

The roadmap says the bookshop family is recognised by "znak wodny, **strony
prawne**" and only the watermark was implemented. Against a real shelf that
found **4 books out of 32** that were plainly bought from a shop: 28 commercial
Polish EPUBs with no visible watermark fell through, and the coverage report
called the family short. A number that says a family is empty when it is nearly
full sends someone out to buy books they already own — worse than no number.

The legal page is measured now: an ISBN, or the rights boilerplate for editions
that carry none. Checked in both directions — it fires on a commercial edition
and on none of the six Project Gutenberg books, whose licence page reads as a
purchase notice to both detectors and which are excluded by name.

## 0.2.5 — alpha — 2026-08-06

**A finding's sentence now lives in exactly one place, and the report speaks
whichever language the interface does — including the paragraph underneath.**
A plain release rather than a milestone one: the owner needs a build to measure
the corpus with, and `CONTRIBUTING.md` says PATCH moves on every release,
whatever it contains.

### At a glance

| | |
|---|---|
| The English sentence lived at the call site *and* in the catalogue | 137 call sites, one home now |
| An identifier spliced into a string concatenation went unnoticed | `compat.appliedapple, kindle`, two releases |
| 20 tests asserted English fragments | now assert identifiers |
| Saved JSON and the console were English whatever the setting said | both follow it |
| A third of a Polish report was the untranslated paragraph | 11.3%, and all of it data |
| The corpus milestone was counted by books, not by families | coverage is measured now |

**New:** `epubforge inventory --json` reports corpus coverage family by family;
`--report-language` on the command line. **Fixed:** `compat.applied` was
reported under a computed identifier; `renders_fully` judged a finding by its
headline alone and put the English line back under a complete Polish one.

**`schema` is 2** — `message` is rendered from the catalogue so its English
wording moved; `rule` did not change and is the field to match on.

### Everything, by subject


### One sentence, one home (EF-018 in the shape the roadmap asked for)

A call site used to pass the sentence *and* the identifier, so the English text
lived twice: once at the call site and once in the catalogue that translates
it. Two homes for one fact is one home too many, and the drift is not
hypothetical — a tagging pass had spliced an identifier into the middle of a
string concatenation, and findings went out under `compat.appliedapple, kindle`
without a single test noticing.

A call site now passes what the catalogue cannot know and nothing else:

```python
self.note(ctx, Level.FIX, "css.invalid-value-corrected", values={"count": 5})
```

137 call sites converted. Both sentences — the finding and the paragraph
beneath it — come from `rules.py`, in either language, from one place.

Two tests replace the grep that missed the mangled call: the identifier must be
a literal, and no call site may write a sentence. Both parse the source rather
than matching text on it, which is why they catch what a regular expression
over `rule="…"` could not.

**Twenty tests asserted English fragments** — "reorganised", "pointing
nowhere", "contain block-level content". Those are the fragile tests EF-018
exists to remove, so they assert identifiers now. That was the first of the
three reasons the roadmap gave for doing any of this, and it had gone unfixed
while the other two were being celebrated.

**`schema` is 2.** The English `message` is rendered from the catalogue now, so
its wording changed for most findings; `rule` did not change and is the field
to match on. `description` and `detail_description` are added, nothing removed.

The divergence from the roadmap's exact spelling — a string rather than an
`M.*` module constant — is written down in `docs/ROADMAP.md` with its reason,
because the roadmap's own preamble says an unrecorded change of mind comes back
in six months as an accidental regression.

### The paragraph under a finding speaks Polish too

The headline was translated and the paragraph beneath it was not. On a real
book that paragraph was **a third of the report's text**, so calling the report
translated was premature — and saying so in a release note was worse.

Sixty-one of the sixty-nine details are translated. The eight that are not are
named in `tests/test_rules.py` with the reason: they are not prose. A list of
tag names, a generated UUID, the caller's own value, EPUBCheck's output — there
is nothing in them to translate, and a Polish entry would be a copy of the
English one, which is exactly what a stalled translation looks like.

Two findings were hiding behind conditional expressions and are now two
findings, the same split the navigation stage got and for the same reason: an
id chosen by an expression is an id nothing can see was raised. A book whose
watermark carries somebody's e-mail address is a different thing to report than
one that does not.

**Our own phrases travel into findings as data**, and that produced a Polish
sentence with an English clause inside it: `reader.name-dropped` ends in a
reason written in `ocf.py`. Those reasons are a closed vocabulary — twelve
phrases this program itself chose — so they are translated on the way out. A
value that is not one of them, a file name or a count, passes through
untouched, which is why the mapping can be applied to every value without
asking which ones are words.

Measured across the six Gutenberg books under all three profiles: **11.3% of a
Polish report is still English, and every character of it is data** — tag
names, `schema:` metadata values, and the locations of heading jumps.

### The corpus milestone was closed on the wrong number

`docs/ROADMAP.md` point 1 does not ask for thirty books. It asks for books
chosen **by provenance** — ten families with a count each — and says why in the
same paragraph: what a book was made by decides what is wrong with it, so three
hundred files off one shelf can teach less than ten off ten. Sixty-four books
were collected, nobody ever counted the families, and the milestone was called
finished on the only number anyone had counted. The roadmap even names a family
it knows is empty (`pdf-or-ocr`), which should have been the clue.

`epubforge inventory <folder> --json inventory.json` now prints coverage family
by family and writes it beside the measurements as `inventory-coverage.json`.
The inventory already recognised the generator traces; what was missing was the
comparison against what the roadmap asked for, and a visible zero for a family
that has nothing to show.

One trait had to be measured that was not: a visible watermark, which is what
makes a bookshop file a bookshop file — those carry no generator trace of their
own. Project Gutenberg's licence page reads as a purchase notice to that
detector and is excluded by name, because nobody bought that book.

The coverage file is counts only, no titles and no content, so it can be sent
from a disk whose books cannot be.

### The report speaks whichever language the interface does

The window had both languages and everything it wrote had one. The saved JSON,
the batch document and the console table were English whatever the setting
said — which is not bilingual, it is Polish in one place and English in three.
That is the shape of the complaint that found it, and it was right.

`to_json(language)` and `batch_to_json(language)` add a `description` field
rendered from the finding's `rule` and `values`; the window passes its own
setting to both. The English `message` does not move and is present in either
document: it is the field a script greps, and replacing it with Polish would be
a broken interface wearing a feature's name. English readers get `description`
too, in English, so no consumer has to special-case a language.

The command line has nowhere to remember a setting, so `--report-language`
decides, defaulting to the window's stored choice, then `LANG`, then English. A
person who set the interface to Polish did not mean "Polish, except on the
command line".

One renderer serves all three now — `Report.headline` — because the console
built its own line out of `finding.message`, which is exactly how it stayed
English while everything around it was translated.

### The release procedure updates the README

Step zero, not the last step: the version, the test count, the alpha conditions
and the list of limitations. It had drifted two releases behind and still said
the report was English-only, which stopped being true in the same release that
made the claim look most convincing. A limitation that is no longer true is
worse than a stale number — it tells someone a thing is missing when it is
there.

### A correction to the 0.2.4 notes

Those notes said "all 79 call sites are converted". That is not what the number
means and it was not true: 79 findings carried an identifier and 57 did not, so
those still printed English in a Polish report. The ratchet counts what is
tagged, not what is left, which is exactly how a migration can look finished
from inside. The wording is corrected, the 57 are done (below), and the
published 0.2.4 release notes carry the wrong sentence where it cannot be
edited after the fact.

### EF-018 is closed, and this time the number means it

Every finding this program can report has an identifier: **136 call sites, 135
catalogued ids, none left over in either direction**. The 57 that had none were
the whole reader, the whole content stage and every stylesheet finding — which
is why a Polish report was still half English no matter how good the catalogue
got.

Both catalogues state their own specifics now, so the English line underneath a
translated one is gone entirely. Measured rather than assumed: across the
fifteen books of the two public corpora, rebuilt under all three profiles, 389
findings, **none without an identifier, none falling back to English, no
placeholder printed at the reader**.

What is still English: the `detail` line under a finding. It is prose rather
than a sentence with a number in it, and translating it is a separate piece of
work rather than the same one continued.

### Thirty-seven English lines that are no longer needed

A translated finding used to carry its English original underneath, because the
specifics — how many entries, which file, which media type — lived in the
sentence and a generic description could not state them. A finding now carries
its values beside its message, and 44 catalogue entries became templates that
state them in either language. Where the template says everything the message
said, the second line is gone.

Polish counts agree with their nouns. English gets away with "(s)"; Polish has
three forms, chosen by the number, and "1 plików" is a mistake rather than a
clumsy phrasing. `{count:plik|pliki|plików}` in a catalogue entry picks the
right one — one for exactly 1, the *few* form for numbers ending 2–4 outside
the teens, the *many* form for the rest.

Two ratchets now, not one: how many sites carry an id, and how many entries
state their own specifics. Either may rise and neither may fall.

## 0.2.4 — alpha — 2026-08-05

**Every finding this program can make now has a name that survives being
reworded, and that name is what the Polish report translates.** The catalogue
was the last of the two unmet alpha conditions; the other was the translation,
and it could not have been done without it.

### At a glance

| | |
|---|---|
| A finding's identity was its English sentence | 79 call sites, 78 catalogued ids |
| The report could not be translated at all | now Polish, 78 of 78 findings |
| A corpus diff said `report.fix: 5 → 6` | now names the rule that moved |
| A container-only rebuild emitted `../` hrefs | 70 of 70 manifest entries, EPUBCheck silent |
| Archive entries declared no file type | every file this program ever wrote |
| A milestone freeze was a thing to remember | now four written steps |

**New:** `tools/device_variants.py`, which builds the archive-level variants
that bisect a reader refusing a valid book. **Fixed:** the package document no
longer walks away from the files it describes.

### Everything, by subject

### Seventy manifest hrefs that climbed out of their own directory

A container-only rebuild put the package document in `EPUB/` and left every
file it describes in `OEBPS/`, because `content_dir` decides where the package
goes and `reorganize_files` decides where the resources go — and `minimal`
turns off only the second. Every manifest entry then had to climb back out:
`href="../OEBPS/images/cover.jpg"`, seventy times over.

That is legal. The path never leaves the container, and EPUBCheck passes it
without a message of any kind — verified on the file this was found in, before
and after. It is also the shape of a zip-slip attack, which is exactly what a
reader guards against, and a reader that refuses the path refuses the book.

When the files do not move, the package document does not move either: it
stays where the source had it, and says so (`package.layout-kept`). The
invariant — no manifest href begins with `../` — is now a test across all three
profiles, because nothing else was ever going to catch it.

Found while writing up why an InkBOOK Focus hangs on our output; whether it is
*the* cause there is still unknown, and the investigation is written down in
`docs/sprawy/INKBOOK-FOCUS.md` rather than carried in anyone's head.
`tools/device_variants.py` rebuilds the archive-level variants that bisect a
reader like it — one file per property the specification leaves free, plus the
control file without which no result means anything.

### Every archive entry now says it is a file

`create_system = 3` on a ZIP entry means "the mode field holds Unix
attributes", and the mode this program wrote was `0o644` — permissions with the
file-type bits left at zero, which is neither a regular file nor a directory.
Every EPUB this program has ever produced said that about every entry in it.
Nothing on a desktop cares. A reader that reads the field and believes it is a
different matter, and both files known to open on the device that started this
were `0o100644`.

The content directory may also be the archive root now, which is where Calibre
puts the package document and where some readers were built to look for it.
Making it configurable was four lines and exposed three wrong ones: joining a
directory that is empty produced `/content.opf` and `/images/…`, a leading
slash that is not a container path at all, and EPUBCheck said so 214 times.
All four join sites go through `paths.content_path` now.

### A finding now has a name that does not change (EF-018, in progress)

The identity of a finding used to be its English sentence. Three consequences,
all of which had already happened: rewording a message broke a test that was
never about the wording; `survey.py` had to strip numbers and quoted fragments
with regular expressions before it could count anything, which is a symptom
rather than a solution; and the report could not be translated at all, because
a sentence that *is* the identity cannot be replaced by its Polish equivalent
without changing what it identifies.

`epubforge/rules.py` is the catalogue — `nav.repointed`,
`xhtml.doctype-modernised` — with one line each saying what the finding means.
That mapping is the thing a translation replaces, and the reason it exists.
`Finding.rule` carries it, `--report` output carries it, and `survey.py` groups
by it wherever it is present: where the identity exists, the guessing stops.

There are more than a hundred call sites, so this lands over several changes.
`tests/test_rules.py` holds it to a ratchet — the number of tagged sites may
rise and may not fall, an id nothing raises fails the suite, and an id raised
but not catalogued fails it too. **79 call sites carry an id**, the catalogue
and the code agree in both directions, and the exemption list is empty.

One call site turned out to be two findings sharing one call. Replacing a
navigation document the source had is routine; generating one it never had is a
correction. They carried different levels and different messages through a
conditional expression, which is how they came to share an identity neither of
them could have.

### The report speaks Polish

The second of the two unmet alpha conditions. The window has been bilingual for
a while and the report has not, and the reason was structural rather than
effort: a sentence that *is* the identity of a finding cannot be swapped for its
Polish equivalent without changing what it identifies. The catalogue is what
made this possible, and it is exactly what a translation replaces.

All 78 findings have a Polish description. `report.to_text("pl")` and the window
use it; English is unchanged, byte for byte, because a translation that alters
the original is a rewrite wearing a translation's name.

The original message stays underneath the translated line. Thirty-seven of the
seventy-eight still interpolate their values straight into the sentence — how
many entries, which file, which media type — and dropping that to gain Polish
would trade information for language. Turning those into templates with their
values alongside is what removes the second line; until then it is there and
said out loud rather than quietly lost.

A copied English line in the Polish catalogue fails the suite: that is the shape
a stalled translation takes, and it looks finished.

### A corpus diff now names the behaviour, not the counter

Signatures record which rules fired and how often, so a book whose signature
moves reads as `+a11y.missing-alt ×3, −nav.entry-dropped` instead of
`report.fix: 5 → 6`. The second says a number went up; finding out which
behaviour changed meant rebuilding the book by hand. This is what the
identifiers were for.

Both corpora are re-recorded to carry the distribution.

### The milestone cycle is a procedure now, not a memory

Releasing a milestone is four steps in one turn: build and release, freeze
`frozen/vX.Y.Z-<name>`, open the next milestone's branch, and print the list of
branches that can be deleted. Written into `CONTRIBUTING.md` because step two
was deferred once and produced a branch called `claude/safety-gate` that had
been moved onto `main` repeatedly and held work with nothing to do with the
Safety Gate. A label on a moving target is not a freeze.

`tools/branches.py` prints what is safe to delete — merged into the trunk, not a
`frozen/` marker, not in use — because remote deletion is refused from the build
environment with the same 403 that refuses a tag push, so a person does it.

## 0.2.3 — alpha — 2026-08-05

**Thirty-two real books and six from Project Gutenberg were pointed at this
release, and they found five defects that no fixture could have.** Four books
came out invalid; one of them turned a source EPUBCheck passed cleanly into 235
errors. All five are closed.

### At a glance

| | |
|---|---|
| The publisher's contents page was destroyed | K1 violation, 4 of 32 books |
| Replacing the navigation left dead references | invalid output, 27 links in one book |
| Container-only mode stranded entities | book would not open, 4 of 32 books |
| Metadata written the EPUB 3 way was dropped | 11 of 32 books |
| Manifest properties were withdrawn silently | every book with a false declaration |

**New:** one JSON report for a whole run, in the window (Ctrl+Shift+S) and on
the command line. **Fixed:** the report panel stayed blank when the queue held
a single book.

### Everything, by subject

### Container-only mode carries its entities with it

A legacy DOCTYPE declares entities two ways, and the second is the one that
matters: every XHTML 1.1 document may write `&nbsp;` because `xhtml11.dtd`
declares it. Under EPUB 3 nothing fetches that DTD, so taking the declaration
away without taking the entity with it stranded the reference — *Fatal Error
while parsing file: The entity "nbsp" was referenced, but not declared*.

One book had **235 EPUBCheck errors against a source that had none**, and 228
of them were consequences: seven documents would not parse, so every navigation
link into them was reported as an undefined fragment. There were never 221 dead
anchors; there were seven unparseable files.

The named entities now travel with the DOCTYPE, rewritten to numeric references
— the same character, needing no declaration. What this mode promises is that
the book looks the same; bytes were only ever a convenient way of keeping that
promise. A name nothing can resolve stops the swap and is reported, because a
book that will not open is worse than one that is merely invalid.

Four of thirty-two real books were affected. All four: EPUBCheck clean.

### One report for a whole run

Saving a report per book is right for one book and unusable for thirty: the
question a batch raises is *which* of them needs attention. `batch_to_json`
writes one document — run totals first, then every book in full, worst first,
so it can be read from the top and abandoned as soon as it stops being
interesting. In the window under *Zapisz raport zbiorczy…* (Ctrl+Shift+S), and
on the command line whenever `--report` names a file rather than a directory.

That fixed a defect of the same shape: `--report out.json` with five books
wrote all five to one path in turn, leaving a report about whichever book came
last — indistinguishable from a report about the run.

### Two findings of mine that were not defects, and two that were

**Both findings reported in 0.2.1 were mine, and neither was a defect.** They
were announced as losses neither audit had caught. Checking them against
EPUBCheck rather than against my own fixture:

| Reported as | Actually |
|---|---|
| `item/@properties="scripted"` dropped | a **correction**. The fixture declared `scripted` on a document with no script, and EPUBCheck errors on the *source*: "The property 'scripted' should not be declared in the OPF file" |
| `itemref/@properties` dropped | a **false positive in the oracle**. Every token was still there; the writer sorts them, and the oracle compared `properties` as a string when it is an unordered set of tokens |

The fixture also declared `page-spread-center` without its `rendition:` prefix,
which EPUBCheck calls an undefined property. Two invalid constructs in a fixture
whose entire job is to be valid.

`TOKEN_LISTS` in `tests/opf_graph.py` fixes the oracle, with two tests: one that
reorders every `properties` attribute in the package and expects silence, and
one that removes a single token and expects a finding. An oracle that produces
false findings spends the credibility the true ones need.

**Two real defects came out of checking.**

A manifest property withdrawn because the document does not bear it out is now
**reported**. It was silent, which meant a publisher got a package differing
from theirs with nothing to explain it. `minimal` still keeps a false
declaration, because it promises to touch nothing and that promise covers
declarations that are wrong.

And the scripting check itself was broken: `any(root.iter(qname("script")))`
truth-tests the *elements*, and an lxml element with no children is falsy. A
document whose only script was `<script>void 0;</script>` came out undeclared —
a reading system would have been told it needs no scripting support. lxml had
been emitting a `FutureWarning` about this exact construct the whole time. The
suite now runs clean under `-W error::FutureWarning`.

Tests: 498 → 503.

### Two defects found by thirty-two real books

Commercial Polish editions, run through all three modes. Four of the thirty-two failed, all four in the same
two ways, and neither defect had a test because neither can happen to a book
written to be a test.

**The publisher's contents page was being destroyed.** A nav document is
allowed to sit in the reading order, and when it does it is two things at once:
the machine-readable navigation, and a page the publisher wrote that the reader
can turn to. Regenerating it served the first and destroyed the second —
"Spis treści", "Punkty orientacyjne" and the publisher's own chapter labels
replaced by ours. Text the source had and the output did not, which is K1, on
four books out of thirty-two.

The page now stays as an ordinary content document and the regenerated
navigation goes in beside it, outside the reading order. One nav document, as
EPUB 3 requires; the publisher's page, as the reader expects. Reported as
`PRESERVED`.

**Replacing a nav document left references pointing at nothing.** The
regenerated nav listed the page it had just deleted, and in one book
twenty-seven chapters carried a "back to contents" link to it:

```
ERROR: Referenced resource "EPUB/text/0015-table_of_contents.xhtml"
       could not be found in the EPUB. (EPUB/nav.xhtml)
```

The output was invalid, and the report said nothing. References in the
navigation tables, the landmarks, the page list and inside content documents
now follow the document that replaced it, and the repointing is reported.

All four books: EPUBCheck clean, K1 satisfied. The `nav-in-spine.epub`
signature moves deliberately — `text_added: 47 → 0`, the source's text now
preserved to the character.

Tests: 503 → 524.

### Metadata written the EPUB 3 way was being dropped

Only
`<meta name= content=>` — the EPUB 2 spelling — was carried through. Anything
said as `<meta property="…">` that the model had no field for went silently,
and the vocabulary is open by design: "not recognised" says something about
this program and nothing about the book.

Apple's `ibooks:specified-fonts` is what exposed it, on eleven of thirty-two
real books. Unknown properties are now carried with their qualifiers, and the
prefix declaration comes with them — without one the property is not a property
but an error, which EPUBCheck reports as *Undeclared prefix*. Only prefixes the
output actually uses are declared, so regenerating that attribute rather than
copying it still holds.

Tests: 524 → 529.

### One edit in container-only mode, dead anchors, and a blank report panel

**The container-only mode makes exactly one edit inside a document now.** A
legacy DOCTYPE makes its output an invalid EPUB 3 — *Irregular DOCTYPE: found
"-//W3C//DTD XHTML 1.1//EN"* — and a DOCTYPE says nothing about how a page
renders, so replacing it is the one change that cannot alter what the reader
sees. Done on the bytes, because opening the document is what this mode
promises not to do. A DOCTYPE declaring its own entities is left alone: those
entities are used, and `<!DOCTYPE html>` does not define them, so swapping it
would turn a merely invalid book into one that will not parse.

The byte-identity test was not relaxed to accommodate this — it normalises the
DOCTYPE on both sides and still demands every other byte match.

**The same mode was leaving dead anchors in the navigation.** Whether a
fragment exists is checked against ids collected while rewriting documents, and
this mode does not rewrite them, so every anchor was assumed live. Reading the
ids costs a parse and changes nothing.

**The report panel stayed blank for a queue of one.** Drawing it was left to
`itemSelectionChanged`, which does not fire when the row is already selected —
so with a single book the report only appeared after a second was added and the
user clicked between them.

Tests: 529 → 534.

### The DOCTYPE swap could strand an entity

The swap above had a hole, and a real book found it. A legacy DOCTYPE declares entities two ways — an internal subset, which was
guarded, and the external DTD it names, which was not. Every XHTML 1.1 document
may write `&nbsp;` because `xhtml11.dtd` declares it, so replacing the
declaration stranded the reference: *Fatal Error while parsing file: The entity
"nbsp" was referenced, but not declared*. A book that will not open, from one
that was merely invalid. The swap now happens only when the document uses no
named entity beyond the five XML built-ins.

Numeric references are unaffected, and `&amp;` and its four siblings do not
block the swap — treating them as a reason to stop would mean never modernising
anything.

Tests: 534 → 537.

## 0.2.2 — alpha

**EF-004 closed.** The last three constructs the model had no room for now
survive a rebuild, and both oracles' defect lists are empty.

| | |
|---|---|
| `<collection>` | carried whole — role, other attributes, nested collections, links, and any `<metadata>` verbatim, because the role vocabulary is open and there is nothing honest to model field by field |
| remote manifest items | declared, never fetched. Dropping one meant the output no longer declared a resource the source did |
| the second `belongs-to-collection` | every membership is kept with its own type and position; a book in a boxed set *and* a series used to keep whichever came first |

A `set`-typed collection now comes back as a set. The old test asserted it came
back *absent* — which read as a decision ("a boxed edition is not a series") but
was the single series field showing through. Not being a series is a reason to
keep it as a set, not to drop it.

**Six real books joined the corpus** — Project Gutenberg, public domain,
committed with the source, three of them Polish. They earned it on the first
run by exposing a defect in the measurement itself: `text_invariant` was false
on all six, and no text had been lost. The field compared character counts for
*equality*, so generating a cover page — two characters — reported a broken
invariant. K1 says no character is lost; it does not say none may be added, and
nothing else in the program was checking K1 at runtime.

It now checks what K1 actually claims: every character of the source's reading
order still appears in the output's, in order. Four tests say so, including one
that reorders text without changing its length — which the count could never
have caught, and neither could a book written to be a test.

Tests: 461 → 498.

## 0.2.1 — alpha

**A stronger oracle, and the first part of EF-004 closed with it.**

`tests/opf_graph.py` reads the package document as a graph: nodes with values
and qualifiers, edges for `refines`, `fallback`, `media-overlay`, spine and
collection membership, and a multiset rather than a set. The oracle it replaces
asked whether the *name* of a construct still appeared somewhere, which is why
a book with two `<collection>` elements could come back with one and pass. Node
identity survives the things a rebuild is entitled to do — moving a file,
renumbering it, transcoding an image — and nothing else.

It found two losses that neither audit listed:

| | |
|---|---|
| `item/@properties="scripted"` | `preserve` dropped the property that tells a reading system the document contains scripting |
| `itemref/@properties` | `page-spread-center` lost, so a fixed-layout page no longer says which side of the fold it belongs on |

**Media Overlays now survive, and this was worse than a loss.** Three separate
omissions combined into one invalid book:

- the SMIL file was carried as opaque bytes and moved to `misc/`, which left its
  own `src` attributes pointing at files that were no longer there;
- `item/@media-overlay` was never read, and EPUBCheck rejects a SMIL file whose
  document does not point back at it;
- `media:duration` was skipped because it is a refinement, and refinements were
  assumed to belong to collections.

`item/@fallback` is fixed in the same change, and it was the most invisible kind
of defect: the field existed on the model and had no line in the writer, so it
was read and then quietly dropped. A `fallback` or `media-overlay` naming an id
the manifest does not define is now reported rather than guessed at.

Both oracles carry a ratchet in the other direction too: an entry describing a
loss that no longer happens fails the suite until it is deleted. Four entries
were removed by that rule while this change was being written, which is the
point of having it.

`media-overlays.epub` in the public corpus has a new signature, deliberately.

Tests: 428 → 461.

## 0.2.0 — alpha

**Safety Gate complete.** Ten tasks, seven of the eight P0 findings from
`audit_consolidation/` closed, and every one verified with the reproduction that
exposed it rather than with a test written afterwards. The program can no longer
lie about the outcome of a run, and can no longer destroy somebody else's file
on the way.

What changed, in one line each — the detail is under 0.1.7 and 0.1.8:

| | |
|---|---|
| EF-001 | a stage that raises no longer ends in a file |
| EF-002 | a batch settles every destination before writing, and refuses a collision |
| EF-003 | the write is atomic; a failure leaves the previous output byte-identical |
| EF-005 | nothing is deleted unless asked, until the dependency graph can prove it unused |
| EF-006 | no accessibility claim without evidence for every graphic |
| EF-007 | a nav document in the reading order stays in the reading order |
| EF-008 | container names read through a model; collisions detected, not resolved by luck |
| EF-011 | the exit code says what happened |
| EF-019 | an existing destination is not replaced without `--force` |
| EF-023 | the corpus regression runs for everybody, not for one shelf |

Tests: 307 → 413.

### The maturity claim, and what it is standing on

`CONTRIBUTING.md` lists three conditions for leaving pre-alpha. **Three of the
three are unmet, and this release is being called alpha anyway** — a decision by
the project owner, recorded here rather than left for somebody to discover.

| Condition | Actual state |
|---|---|
| corpus ≥ 30 books, metrics green across three consecutive releases | 64 books exist, recorded on 0.1.6. Releases 0.1.7 and 0.1.8 deliberately changed the output, so the signatures need re-recording and the three-release run has not happened. |
| message catalogue ready, report translated | Neither. The report is English-only and findings have no stable identifiers (EF-018). |
| **no known defects that lose data silently** | **False.** EF-004 is open and confirmed: Media Overlays, remote resources, `fallback`, `media:duration` and one of two collections still disappear with zero errors reported. |

The third is not a formality. A book with read-aloud narration loses its
synchronisation, passes EPUBCheck, and says nothing about it. Anyone handed this
release should know that; the README limits section says so too.

What alpha does mean here, honestly stated: the failure modes that could destroy
your work are closed, and the ones that remain are about **completeness of the
output**, not about safety. That is a real threshold, and it is the one worth
crossing before giving the program to other people. It is simply not the
threshold the version table describes.

Closing EF-004 is the whole of the next block of work.

## 0.1.8 — pre-alpha

Closes the last of the P0 findings. Archive entry names are read through a model
instead of being folded into shape by one expression and stored.

### Fixed
- **Two archive entries with one name no longer resolve by iteration order**
  (EF-008). The later one won and the earlier one was gone, silently. When both
  bodies are identical nothing is lost and the run continues with a note; when
  they differ, one of the two documents cannot be represented whatever the tool
  does, so the read stops rather than picking for you.
- **A name that climbs out of the container is dropped, not copied through.**
  An entry literally called `../outside.bin` used to survive a `minimal` rebuild
  into the output. This tool never unpacks an archive, so it was never at risk
  itself — whoever unpacked the result was.
- **Names that differ only by case, or only by Unicode normalisation, are
  reported.** Both are legal and distinct inside the archive, and both are one
  file on a filesystem that folds case or normalisation — which is most of them
  outside Linux. The book is not refused, because it reads perfectly well where
  it was made; the warning names the pair.
- Every name the reader has to rewrite — backslash separators, a leading slash,
  a drive letter, `.` or `..` segments, percent-encoding — now appears in the
  report. Folding them silently meant a name that had been changed looked
  exactly like one that had not.

### Added
- `epubforge/ocf.py` — container names as a value with an account of what was
  changed, and collision detection under four views: identical, percent-decoded,
  NFC, case-folded.
- `tests/test_ocf_paths.py`.
- **A corpus regression that runs for everybody** (EF-023). The private corpus is
  the strongest net this project has and it runs on one machine in the world;
  everywhere else the test skipped. `tests/public_corpus.py` builds nine books
  from what the 64-book survey established about real ones, byte-deterministically
  so their signatures mean the same thing on every machine, and
  `tests/corpus_public/` holds those signatures at 40 KB.

  Three of the nine exist because the measured library contains **no** example:
  right-to-left, Media Overlays and fixed layout. Those are where the model is
  thinnest — reading direction has already been lost once, in every mode
  including the one that promises to touch nothing — and until now nothing in
  the repository exercised them at all.

  Real public-domain books would be a better second corpus and remain wanted;
  this environment cannot reach Project Gutenberg to fetch any.

## 0.1.7 — pre-alpha

First of the Safety Gate releases. Nothing here adds a capability; all of it
stops the program from doing something it should never have been able to do.
The findings are from `audit_consolidation/`, where each one has a runnable
reproduction.

### Changed
- **Unreferenced files are no longer deleted by default** (EF-005). The
  reference graph does not follow `img@srcset`, `<picture><source srcset>` or
  links made from inside an SVG, so "nothing points at this" was not the same
  claim as "nothing needs this" — measured, not supposed: a valid PNG used only
  through `srcset` was deleted while the markup pointing at it stayed. The
  output validated and rendered a hole. `--drop-orphans` brings the old
  behaviour back for anyone who wants it; the flag that used to exist,
  `--keep-orphans`, is gone rather than left as a silent no-op.
- **The exit code says what happened** (EF-011). A book that produced an ERROR
  was written, announced in green as `written`, and exited 0 unless
  `--strict-exit` was passed — so a script read a damaged book as a finished
  one. Now: `0` clean, `1` nothing written, `2` written with errors. The message
  distinguishes `written` from `written with errors`, and `--strict-exit` now
  means what its name suggests — warnings count too.
- **An existing file at the destination is no longer replaced without asking**
  (EF-019). The source file has always been protected by an explicit guard, and
  that guard was the reason nobody looked at the rest: pointing `-o` at any
  other file replaced it, silently, exit 0. `--force` is the way to say yes.
- **The write is all or nothing** (EF-003). `write_epub` opened the destination
  directly, so a failure partway through left a truncated file under the name
  the user knew — measured before the fix: 2338 bytes became 1196. The archive
  is now built under a temporary name beside the destination, closed, read back
  and checked for the things a half-written container gets wrong, and only then
  moved into place with `os.replace`. A `KeyboardInterrupt` is treated the same
  as a disk filling up.
- **A batch settles every destination before it writes anything** (EF-002).
  Destinations were derived one book at a time from the basename, so nothing in
  the program ever held two of them at once and had the chance to notice they
  were the same. Two books called `tom-1.epub` under different authors resolved
  to one file: the second overwrote the first, both were announced as written,
  exit 0. The run is now refused with both source paths named. `--dry-run`
  prints the plan and writes nothing.
- **A navigation document that was part of the reading order stays there**
  (EF-007). A visible table of contents is a nav document in the spine — the
  page a reader can turn to. Regenerating it removed the old resource, and
  removing a resource removes its spine entry with it, so the page vanished:
  two spine items in, one out, no error and no warning. Position and `linear`
  are now carried over and the change is reported.
- **Accessibility metadata is no longer asserted without evidence** (EF-006).
  Two claims were being made on the strength of not having looked. A document
  whose only graphic was an inline `<svg>` with no title, desc or ARIA label
  came out declaring `alternativeText`, because the survey counted `<img>`
  elements and an inline SVG is not one. And `accessibilityHazard: none` was
  decided from video and script alone, so a CSS keyframe animation, an animated
  GIF and an animating SVG all passed as motionless. Inline SVG is now counted
  and examined; a graphic in an unknown state blocks the positive claim; and
  anything that might move makes the hazard `unknown` rather than `none`.
  These are the publisher's assertions under EPUB Accessibility 1.1 — a false
  one tells a reader who depends on it that the book is usable.
- **A stage that raises no longer ends in a file** (EF-001). The exception
  became an ERROR line, the remaining stages ran on a model the failure had
  left half-modified, and the writer produced a book that looked finished.
  Nothing about the file said otherwise — not its size, not its structure, not
  EPUBCheck. That is what made this the worst defect in the program rather than
  merely one of them: every other failure could leave the building through it.
  The run now stops, nothing is written, and the report names the stage.

### Added
- `Result.status` — `succeeded`, `succeeded-with-problems`, `blocked` or
  `failed`. Front ends used to work this out from `output_path is not None`,
  which cannot tell "finished" from "crashed, and we wrote the pieces anyway".
  A refusal (DRM, writing over the source) is now `blocked` rather than sharing
  a label with a malfunction.
- `tests/test_cli_contract.py` — the command line had no tests at all, which is
  precisely where two of these defects lived. Exit codes and refusals are a
  contract with whoever runs the program, and are now pinned as one.
- `tests/test_failure_injection.py` — parameterised over every stage in the real
  pipeline, so a stage added later is covered the day it is added. It also
  covers the write itself: a failure at three different points, a container
  that reads back wrong, and the temporary file not being left behind.
- `epubforge/plan.py` — destinations, collisions and occupied targets as a value
  that can be inspected before anything happens.

## 0.1.6 — pre-alpha

The other half of the same afternoon's data: the three books a 64-book survey
could not read, and the three complaints from the person running it.

### Fixed
- **Three books died on a comment.** `ValueError: Input object is not an XML
  element: lxml.etree._Comment` — one Polish shop writes its order number into
  `<metadata>` as an XML comment, Sigil leaves it there, and the metadata loop
  called `itertext()` on it. lxml refuses to walk a comment, so the rebuild
  ended before anything else could run. Nothing else about those books was
  unusual.

  The comment now **survives the rebuild**, which is the only consistent answer:
  it carries an order number, that is a watermark by any other name, and this
  tool does not remove watermarks. One containing `--` is dropped instead of
  mangled — XML has no escape for it — and nothing else in the package changes.
- **The cover was shown at its own pixel size when nothing sized it.** Found in
  a book a Calibre edit had left with the cover stylesheet in the archive root
  and the cover page still linking `../Styles/cover.css`: the link dangles, no
  rule reaches the image, and a 1600px cover meets a six-inch screen. Where
  **nothing** sizes the cover — no rule anywhere in the chain, no `width`
  attribute, no inline style — it now gets `max-width: 100%; max-height: 100%`.
  Both can only ever shrink an image below its natural size, so the worst case
  is a reader ignoring them. A cover the publisher did size is untouched.

### Changed
- **No more console window on Windows.** Ticking "check with EPUBCheck" starts
  a JVM, and a GUI process starting a console binary gets a console: a black
  rectangle that appears, does nothing, and disappears — once per book, so 64
  times on a library run. Started with `CREATE_NO_WINDOW` now. The progress it
  looked like it should be showing is in the window, and the status line says
  when the validator is the thing taking the time.
- **The corpus tab explains what it is for.** It was described in terms of what
  it stores rather than what it does, and it read as though it were signing the
  user's files. It is a safety net for this program: it notices when a change
  here alters what the rebuild produces for books nobody ever handed over. The
  status word for that is now "inny wynik" — a different result — because
  "changed" sounded like the book had been changed.
- The mode tooltip says outright that **every mode rebuilds the container**, and
  that the choice is only about what happens to the content. "Keep the
  appearance" reads like "leave the file alone", and it never meant that.

## 0.1.5 — pre-alpha

Everything here came out of one afternoon's data from somebody else's shelf: a
65-book survey, an inventory, one corpus signature and five EPUBs. Nothing in
this release was found by the test suite.

### Fixed
- **A cover that was already centred got "centred" anyway — and a cover the
  publisher had aligned on purpose got overruled.** `text-align` and
  `text-indent` are inherited, and the repair only ever looked at the paragraph
  itself. A page built as `body.cover { text-align: center }` around a bare
  `<div><img/></div>` shows nothing on the `<div>`, so the tool concluded
  nobody had chosen an alignment and wrote its own — a reported fix that
  changed nothing. The same blindness runs the other way and is the reason this
  is a defect rather than noise: a rule naming the container is a decision
  about the image inside it, and it was being overwritten. Both properties now
  resolve along the ancestor chain, and a decision made a level up counts as a
  decision. Where the alignment was chosen but a running-text indent still
  leaks in, only the indent is removed, and that is reported as what it is.
- **`text_invariant` in a corpus signature was false on books whose text was
  untouched.** The rebuild generates the navigation document EPUB 3 requires,
  and that document is a list of chapter titles — text, to anything counting
  characters across content documents. Every EPUB 2 book in a corpus therefore
  reported that its text had changed. The comparison is now over spine
  documents only, which is what K1 has always meant.
- **The same book built on Windows and on Linux came out with different
  bytes.** `zipfile` stamps every entry with the system it ran on — 0 for
  Windows, 3 for everything else — in both the local header and the central
  directory. Nothing about the book differed; every file inside was identical.
  It surfaced the only way it could: a corpus signature recorded on one machine
  and checked on another reported that the output had changed, for every book,
  forever. Proven rather than guessed — forcing the field to 0 here reproduces
  the Windows hash exactly, in both modes. Now pinned to 3, matching the Unix
  permission bits the writer already sets.

  **Signatures recorded on Windows before 0.1.5 will show `output` changed
  once.** That change is this fix and nothing else.
- **The corpus read only the top level of a folder.** Libraries are filed in
  subfolders, so a shelf of hundreds was measured as one book and reported as a
  success. The survey has always walked the tree; the corpus now agrees with
  it, and books are labelled by their path so two shelves may hold the same
  filename.
- **Save in the library tab wrote the previous result under the new name.**
  Running a survey, switching to inventory and pressing Save produced the
  survey called `spis.json`. Changing anything that would alter the answer now
  withdraws the old one.

### Changed
- A survey reports **why** books failed, not just how many. `crashed: 3` with
  nothing else is an alarm nobody can act on. Reasons are grouped by what went
  wrong and counted; paths are stripped out of them, and filenames still travel
  only with `--with-names`. The window shows them too, which is where they were
  missing.
- `schema` in a survey JSON is now `2`.

## 0.1.4 — pre-alpha

### Fixed
- **Entities a book declared for itself became visible text on the page.** A
  document may declare its own entities in the DOCTYPE's internal subset — a
  habit of DocBook and TeX pipelines, and of some publishers. EPUB 3 replaces
  that DOCTYPE with one declaring nothing, so the subset has to go; but the
  references stayed behind, resolved to nothing, and the ampersand was escaped.
  The reader saw `&mypauza;` where a dash belonged. Silently, in `preserve`
  mode, with a report entry about a different kind of entity entirely.

  They are now resolved before the subset is dropped, and by this tool rather
  than by the parser: handing it to libxml2 means turning `resolve_entities`
  back on, which is what shuts XXE and runaway expansion. External declarations
  are never resolved, nesting is bounded, and a document that tries to grow
  tenfold is refused whole. Both outcomes are reported.
- The K1 helper mis-parsed a *source* document carrying an internal subset:
  `lxml.html` cannot find `<body>` past one and returns the stray `]>` as text,
  so the invariant would have failed over punctuation while the real damage was
  identical on both sides and invisible.

### Added
- **The library, survey, inventory and corpus features are in the window**, not
  only on the command line. Three tabs: rebuild, library (survey or inventory
  over a folder), and corpus (record signatures, or check against them). The
  long jobs run off the UI thread with progress, and nothing is written beside
  anybody's books.
- `epubforge/corpus.py` and `epubforge corpus` — the corpus was previously a
  pytest fixture, which meant the person holding the books needed a checkout to
  help. It is a feature now; the test suite is a thin wrapper over it.

### Changed
- **The window scales.** It asked for a fixed 1180×760, which opens taller than
  a 1366×768 laptop screen; it now takes a share of the available desktop with
  a floor low enough for the layout to survive. The options column sits in a
  scroll area rather than being cut off — with the run button inside it — and
  neither splitter can collapse a panel to nothing.
- The title said "EPUB F.O.R.G.E. 0.1.1 (pre-alpha) - EPUB F.O.R.G.E.", because
  Qt appends `applicationDisplayName` to a title that already carried the name.
- The status line follows the tab. "Drop EPUB files anywhere in this window" is
  good advice on one tab and untrue on the other two.

## 0.1.3 — pre-alpha

The first release driven by data from a real library rather than from reasoning
about one. A survey of 32 books arrived, and it immediately said two things.

### Added
- `epubforge inventory` — what the books *are*, as against what the tool does to
  them. Provenance (traces of Calibre, InDesign, Word, a PDF conversion — as a
  list, since files are layered), damage counts, and a typographic census.
  A survey can only name defects the tool already knows about, so it cannot
  surprise anybody; an inventory is what says which rules are worth writing at
  all. Output is counts and character frequencies, keyed by a hash; `--map`
  writes the hash-to-filename mapping separately and is the only file that names
  anything.

  It reads through `read_epub` rather than scanning bytes, and that is the whole
  design. Three measurements are wrong by construction on raw markup and wrong
  in a way nobody notices, because a number that is too high still looks like a
  number: `&nbsp;` counted as six characters instead of one non-breaking space,
  source indentation counted as doubled spacing, and a hyphen before a line
  break read as evidence of the very thing that would license the riskiest rule
  we have planned. Tests pin each one.
- `Book.source_package` keeps the package document as it arrived. Half of what
  identifies a generator is written there — `calibre:series`, InDesign's
  identifiers — and the model has normalised it away by the time anything else
  could look.

### Removed
- The report no longer says a book has no print page numbers. Across 32 real
  books it fired on all 32, which is what an absence looks like when it is the
  norm rather than a defect: the publisher is the only one who can supply them,
  so the entry named a fact nobody could act on and pushed the findings that
  mattered further down the page. A finding that is always true is not a
  finding.
- The inventory does not count runs of ordinary spaces, though the sketch it
  grew from did. HTML collapses whitespace, so a double space is invisible to a
  reader and cannot be damage; counting it on markup measures how the file was
  indented and nothing else.

## 0.1.2 — pre-alpha

### Fixed
- `docs/KORPUS.md` told the reader to run `epubforge survey`, which does not
  work after installing: the application directory is not on `PATH`, so the
  command that the whole document is built around fails with "not recognised".
  The document also interleaved two different procedures — one needing only the
  installed application, one needing a Python checkout — without saying which
  was which, so there was no way to follow it end to end. It is now split into
  two labelled paths with numbered steps, and every command is one that works
  as written.
- The installer adds a Start-menu shortcut opening a prompt with the
  application on `PATH` for that window. Scoped to the session deliberately:
  editing the real `PATH` is a change to somebody's machine and this needs no
  such thing.

## 0.1.1 — pre-alpha

A third audit, and the structural conclusion it reached is worth more than any
individual fix: **the model is a contract.** The rebuild emits the package
document from the model, which is what makes the output correct however broken
the input was — and the price is that a construct never read into the model
disappears without a trace. No warning, no report entry, no validator error,
because the result is perfectly valid. Just poorer. That is K12, and it now has
a test that can see it.

### Fixed
- **The reading direction was lost in every mode, including `minimal`.**
  `page-progression-direction` was not read or written anywhere, so a Hebrew,
  Arabic or manga edition came out opening the wrong way — silently, in the one
  mode that promises to touch nothing. `package/@dir` went with it. Everything
  expressed as `<meta>` survived a rebuild and everything expressed as an
  attribute of a structural element did not; no test could tell the difference
  because both outputs were valid EPUB.
- **Transliterated titles and names were dropped.** `alternate-script` is how a
  library catalogue links "Natsume Sōseki" to 夏目漱石. After the previous
  release, `_read_collection` was the only reader of refinements, and the code
  said as much in a comment — a true statement that turned out to cost
  something.
- **Running out of the archive budget produced half a book instead of a
  refusal.** The whole-archive budget was passed to the per-entry limit, so
  exhausting it looked like a run of oversized entries: the loop continued, four
  of six images vanished, the result was a valid EPUB, and the fifth image was
  blamed for "expanding past the limit" when it was an ordinary one megabyte.
  The two are different questions and now have different answers — a monstrous
  entry is skipped, an exhausted budget refuses the book. A regression the
  0.8.1 fix introduced.
- `page-spread-center` without its `rendition:` prefix is EPUB 3.0 spelling and
  an undefined property in 3.3. Found by the new fixture, and it made the
  output invalid for any book written to the older specification.
- `dc:type`, `dc:coverage` and `dc:relation` are carried through instead of
  dropped. They had no field in the model, which is not a reason to discard a
  publisher's statement about their own work.

### Added
- `epubforge survey` — what breaks across a whole library, ranked by how many
  books show each defect, writing nothing. A hundred separate reports are a
  hundred things to read; this is one answer to the question of what to fix
  next. Findings are normalised before counting, so "corrected 5 declarations"
  and "corrected 12" are one row rather than two. **Filenames are omitted unless
  `--with-names` is given**: a survey is meant to be shareable, and a list of
  titles says more about a shelf than about the tool.
- `tests/kitchen_sink.py` and `tests/test_package_completeness.py`: a package
  carrying one of everything EPUB 3.3 §5 allows, and a test comparing the
  constructs going in against those coming out. Whatever disappears must be
  repaired or listed with a reason — and two further tests keep the list honest,
  one rejecting an entry without a reason and one rejecting an entry for
  something the fixture never had.
- K12 in `CONTRIBUTING.md`, completing a set: K4 governs what the tool claims on
  the way out, K11 what it believes on the way in, K12 what it drops in between.
- A note on the **scope of K1**: it is a character-stream invariant, so it
  cannot see two paragraphs merged into one. That matters at the typography
  stage, where joining paragraphs broken by a PDF conversion is planned and is
  among the riskiest things this tool could do. Corpus signatures now record a
  block count, so such a change has somewhere to show up.
- `docs/KORPUS.md` — how to put a personal library to work without a single book
  leaving the disk.
- The test suite runs a second time under a different `PYTHONHASHSEED` in CI.
  Iterating a set is the classic way for K2 to quietly stop holding, and a
  single-process run can never notice.

## 0.1.0 — pre-alpha

### Changed
- **Version reset to 0.1.0, and maturity moved out of the number.** Two earlier
  schemes both used MINOR as a measure of how much had been built, so a day's
  work put the tool at 0.8 — which reads as four fifths of the way to a release
  it is nowhere near. The second attempt slowed the increments and left the
  inflated number in place, which fixed the symptom.

  The number now counts releases and nothing else: PATCH moves on every one,
  with no judgement call to make. Maturity is a separate word, `__stage__`,
  shown wherever the version is shown — `epub-forge 0.1.0 (pre-alpha)` — and
  MINOR moves only when that word does, against written entry conditions for
  alpha, beta and 1.0. Nothing had been tagged or released under the old
  numbers, so nothing points at them.

  Everything below this line was built during 0.1.x; the old headings are kept
  as written rather than rewritten, since they are a record of what happened.

## 0.8.1

A second audit, and a pattern worth naming: four of the five serious defects
found across both audits have the same shape — **the code asked the source
about something the source is under no obligation to be truthful about, or did
not ask everything it could have.** That is now K11 in `CONTRIBUTING.md`, the
sibling of K4: K4 governs what the tool claims on the way out, K11 what it
believes on the way in.

This release is a PATCH under the versioning rule adopted here: it repairs
defects and strengthens tests without changing what the tool sets out to do.

### Fixed
- **The archive size limits could be bypassed by lying.** They read
  `file_size` and `compress_size` from the ZIP header, which is not a fact
  about the archive — it is whatever its author wrote there. Patch the field
  and the guard waves the entry through; the decompressor then produces the
  real payload, and the CRC check that eventually complains only runs after the
  memory has already been allocated. Measured here: a 300 MiB entry declaring
  itself as 1000 bytes cost **601.7 MiB** of peak allocation, and a 10 GB one
  would have killed the process before anything noticed.

  The ceiling is now enforced while decompressing, in chunks, so the same file
  is refused at **2.6 MiB**. The header check stays as a cheap first pass — an
  archive that admits to holding a 300 MiB entry is still turned away without
  reading a byte — but it is no longer the only one.
- **The series number could come from the wrong collection.** EPUB 3 allows a
  book to belong to several: the seventh Chronicle, published inside a boxed
  set as part one. The 0.8.0 fix separated a `set` from a `series` by *name*,
  but the number was still taken from whichever `group-position` appeared
  first, so that book came out as "Chronicles, volume 1". Collections are now
  resolved whole, and the number comes from the collection the name came from.
  This was a regression introduced by the previous fix.
- **The K1 helper silently skipped documents.** It selected content by file
  extension and excluded navigation by looking for "nav" in the filename.
  Neither is a fact about an EPUB: the manifest decides what a content document
  is, `.xml` occurs in the wild, and a chapter called
  `navigare-necesse-est.xhtml` is a chapter. Both guesses failed in the same
  direction — they *excluded* real content, so the invariant covered less of
  the book and still passed. On fixtures whose names we chose that could never
  surface; on a corpus of real books it would have happened constantly and
  silently. Documents now come from container.xml → package document →
  manifest and spine, with navigation recognised by `properties="nav"`.

### Changed
- Corpus signatures are named by the book's hash instead of its title. The
  content never leaked, but `autor - Ostatnie życzenie.json` in a public
  repository leaks the shelf, which is the same class of information the
  arrangement exists to keep local. It also survives renaming a file on disk,
  which previously orphaned its signature without a trace.
- Corpus signatures measure `preserve` as well as `strict`. `preserve` is what
  users actually get by default, and it was the one mode nothing watched.
- `--record` now prints a field-level diff before overwriting. "12 books gained
  a css warning" is something you can review; "40 hashes changed" is not.

## 0.8.0

An external audit found two defects that had gone unnoticed through 154 tests.
Both share a shape worth naming: they corrupted **data** without changing the
**shape** of the output — same files, same counts, same validator verdict. No
behaviour test was ever going to catch that, so the suite gained a category
that can: `tests/test_invariants.py`, which asserts properties of the whole
output rather than individual repairs.

### Fixed
- **The series number was lost on the second pass.** `group-position` is, by
  definition, always a refinement of the collection it numbers — there is
  nothing else for it to point at — and the reader skipped every refinement
  before reaching the branch that handles it. The branch was unreachable code.
  A book rebuilt once kept its series number; rebuilt twice, it lost it,
  because the first pass had already moved the number from
  `calibre:series_index` to the EPUB 3 spelling.
- **A book with no alt text at all came out claiming it had some.** The content
  stage supplies `alt=""` where an image has none, and recorded in the run's
  context that it had done so; the accessibility stage read that note and
  correctly withheld `alternativeText`. But the note lived only inside one run,
  and the output goes to disk and comes back. On a second pass the same empty
  alt was indistinguishable from a publisher's deliberate one, so the book was
  declared to have alternative text it does not have. Under the European
  Accessibility Act that is not cosmetic.

  The repair is not to remember harder. An empty alt asserts "this image is
  decorative" and nothing here can verify that, so it no longer counts as a
  description at all — only `role="presentation"` or `aria-hidden="true"`, which
  somebody wrote deliberately, does. That over-reports on books using an empty
  alt correctly, which is the safe direction, and the report says exactly why.
- **The output was not byte-reproducible.** `container.xml` and the package
  document were written through a code path that stamps the wall clock, while
  every other entry carried a fixed timestamp. Two runs on the same input
  produced different files. All entries are now written the same way.
- A collection of type `set` — a boxed edition — was recorded as a series.

### Added
- `tests/test_invariants.py`: K1 no readable character is lost, K2 the output
  is a function of the input, K3 a second pass changes nothing. The third would
  have caught both defects above; the weaker idempotency test it replaces
  compared file *names* and passed while the data changed underneath.
- `Policy.modified_override`, `--modified` and `SOURCE_DATE_EPOCH`, which pin
  `dcterms:modified`. With every ZIP timestamp already fixed, that was the last
  moving part: the output is now byte-identical across runs, and a test proves
  it.
- Ceilings on what an archive may expand to — per entry, in total, and by
  compression ratio. The whole book is held in memory by design and files
  arrive by drag-and-drop, so an archive must not be able to ask for unbounded
  allocation. The limits sit far above any real book and a test asserts that
  ordinary content is never refused.
- `tests/test_corpus.py`: regression against real books without putting anyone's
  book in the repository. The books stay in a gitignored directory; only a small
  metric signature per book is committed — EPUBCheck counts, whether the text
  invariant held, the report's shape and the output hash. The module skips
  itself when the directory is absent.
- `CONTRIBUTING.md` — the rules a new feature may not break, each naming the
  test that enforces it — and `docs/ROADMAP.md`, which records what comes next,
  in what order, and the four places where we deliberately departed from the
  advice we were given.
- `"schema": 1` in the JSON report. The moment anything outside this project
  reads `--report`, its shape is an interface.

### Changed
- Filenames keep their Polish letters. `unicodedata.NFKD` cannot decompose `ł`,
  so the ASCII fold dropped it without trace and `okładka.png` became
  `okadka.png`. A transliteration table is applied first: `okladka.png`,
  `Żółć.xhtml` → `Zolc.xhtml`. `đ ø æ œ ß þ ð` and friends are the same defect
  in other alphabets and cost nothing to cover.

## 0.7.0

### Added
- Optional reader-family compatibility profiles: `--compat kindle`, `kobo`,
  `apple`, `legacy`, and the matching checkboxes in the interface. All off by
  default, because the product of this tool is a standards-clean book and each
  profile is a deliberate step away from that.

  Every measure is **additive** — it adds a file, a declaration or a legacy
  element, and never removes or rewrites what the book already had. That is the
  admission price: a concession that could damage the book on correct software
  would be a regression, not a concession. With all four profiles enabled the
  output still passes EPUBCheck with zero errors and zero warnings, and a test
  pins that.

  What the measures are: the EPUB 2 `<guide>`, which is where Amazon's
  converter and RMSDK readers look for the cover and the start-reading
  position; a stylesheet declaring the HTML5 sectioning elements as blocks,
  because RMSDK renders an element it does not know as inline and collapses a
  book built from `<section>` into one running paragraph; the legacy
  `page-break-*` spelling mirrored beside each modern `break-*` declaration;
  and `META-INF/com.apple.ibooks.display-options.xml`, without which Apple
  Books substitutes its own font for every embedded face.
- `epubforge compat` prints what each profile does, why a device needs it and
  what it costs, so `--compat` is not a guess.

### Fixed
- `minimal` mode did not do what it promised. It was documented and described
  as leaving content files byte for byte, but the XHTML and CSS stages ran
  regardless, so every document came back reserialised. The two stages are now
  skipped outright in that mode — parsing a document changes its bytes even
  when nothing about it is wrong, so the only way to keep the promise is not to
  open the file.
- The About dialog's logo was a blur. `QPixmap` handed a multi-size `.ico`
  loads the *first* directory entry, which is the 16×16 one, and scaling that
  up to a 72-point badge is exactly as bad as it sounds. It now loads the
  256×256 PNG and renders at the display's pixel ratio.
- Combo boxes clipped the descenders of their own labels — which in Polish
  means every ą, ę and g.

## 0.6.0

### Changed
- Renamed to **EPUB F.O.R.G.E.** — *Fabryka Odbudowy i Renowacji Glitchujących
  EPUB-ów* / *Factory for Overhauling and Renovating Glitchy EPUBs*. The window
  title, About dialog, installer and documentation follow; executable and
  distribution folder names are deliberately unchanged so the Windows build
  keeps working.

### Added
- A rare dry remark, shown only when a book arrives with nothing at all to fix.
  The tool's personality lives in its documentation and in the fixed text of
  the interface; a wisecrack after every book stops being funny by the third
  one, and one beside a warning or an error is simply in the way.

### Fixed
- The Windows build stopped working the moment the repository itself was
  renamed to `EPUB-F.O.R.G.E.`. A trailing dot is legal in a repository name
  and illegal in a Windows directory name, so the runner's workspace —
  `D:\a\<repo>\<repo>` — became a path that cannot exist. `actions/checkout`
  aborts on it while validating `GITHUB_WORKSPACE`, which happens before it
  reads its own inputs, so its `path:` option cannot help; and every `run:`
  step would fail identically, that directory being their default working
  directory. The job now clones into a fixed dot-free path and never touches
  the workspace. Renaming the repository without the trailing dot remains the
  real fix and would let the workflow go back to a plain checkout — the
  displayed name can keep its dots regardless.

## 0.5.1

### Fixed
- The `schema:` prefix used by the accessibility metadata is only *reserved*
  from EPUB 3.3 onwards. A reader built against EPUB 3.0 or 3.1 sees an
  undeclared prefix on every accessibility property, and a strict one can
  reject the package document — which presents to the user as a book that will
  not open at all. The prefix is now declared on `<package>`, which is
  redundant under 3.3 and legal there, so it costs nothing and restores older
  devices. EPUBCheck never flagged this because it validates against 3.3.

## 0.5.0

### Added
- Publisher watermarks are consolidated instead of being left to smear through
  the book. Retailer "social DRM" stamps a per-purchase token into a
  `<div style="font-size:1px !important">` at the end of **every** document —
  34 copies in one book measured here, 27 and 23 in two others. The token text
  is never touched, but the repeated inline `!important` styling becomes a
  single rule, and the marker gains `aria-hidden` so a screen reader stops
  spelling it out at the end of every chapter.
- Visible watermark notices — the human-readable "this document is protected,
  order ##…" block — are recognised separately and left exactly as written,
  because they are meant to be read. They are reported, and if the notice
  carries an e-mail address that is called out, since it identifies the buyer.
- `--keep-watermark-markup` leaves the markup untouched.

### Fixed
- Nothing in the watermark heuristic may catch ordinary content: an unanchored
  font-size pattern read `10px` as `1` and `0.9em` as `0`, which would have
  pulled legitimate fine print into the watermark path. Sizes are now compared
  numerically, and only absolute units count — `em` and `%` are how publishers
  set small print.
- The consolidated rule hides at `font-size: 0`, not `1px`, because publishers
  hide these at `0pt` as often as at `1px` and the replacement must never be
  more visible than what it replaces.

## 0.4.0

Driven by three more real books: *Book 3*, and *Book 8* before
and after a manual repair.

### Added
- Repair for a block-level box nested directly inside an inline one — a chapter
  heading built as `<h1><a><span style="display:block">…</span></a></h1>`. The
  block splits the inline into anonymous boxes and margins and centring then
  behave unpredictably; the wrapper is promoted to `inline-block`, which is a
  legal container in the same position.

### Fixed
- Undefined entities such as `&nbsp;` survived into the output. With
  `resolve_entities=False` lxml accepts them as entity nodes and the strict
  parse *succeeds*, so the fallback that rewrites them never ran — and the
  EPUB 3 `<!DOCTYPE html>` does not declare them, making readers fail fatally.
  Entities are now normalised before the strict parse rather than after it.
- `width="10%"` on an image is valid XHTML 1.1 but invalid XHTML 5, where the
  attribute must be a bare integer. Non-integer values move to CSS; integers
  stay as attributes.
- `remote-resources` was declared for documents whose only external reference
  was an ordinary hyperlink. The property covers resources a document embeds,
  not where its links point.
- Navigation entries pointing at a fragment that no longer exists now fall back
  to the document, instead of leaving a dangling anchor for validators.
- Image paragraphs already centred by a generic rule are no longer given a
  redundant inline style.

## 0.3.0

### Added
- EPUB Accessibility 1.1 discovery metadata (`schema:accessMode`,
  `accessModeSufficient`, `accessibilityFeature`, `accessibilityHazard`,
  `accessibilitySummary`), derived only from what the book demonstrably
  contains. Relevant since the European Accessibility Act began covering
  e-books in June 2025.
- Detection of alt text that merely repeats the filename (`alt="title-1"`,
  `alt="cover"`). It satisfies a validator and tells a screen-reader user
  nothing, so it does not count as a description and `alternativeText` is
  withheld.
- The cover image is described with the book's title instead of being left with
  a placeholder or an empty alt.
- Accessibility gaps a machine cannot fill — missing descriptions, skipped
  heading levels, tables without header cells — are reported as human work.
- `--claim-conformance {wcag-a,wcag-aa,wcag-aaa}` records the publisher's own
  conformance assertion. Never set automatically: WCAG cannot be established
  mechanically, and under the EAA the claim carries legal weight.
- `--no-a11y-metadata` to skip the declarations entirely.
- Interface language is switchable between Polish and English under
  Settings → Interface language, and remembered between runs.
- An About dialog naming the authors, the licence and the bundled components
  with their licences.
- Polish README, with the English one kept as `README.en.md`.

### Changed
- The image-paragraph correction now reads the CSS cascade before acting. A rule
  aimed at a paragraph by class or id — `p.ilustracja { text-align: right }` —
  is a decision about that image and is obeyed, while a blanket
  `p { text-align: justify }` written for prose is treated as inheritance that
  happens to land on the artwork. Inline styles are likewise respected. Books
  that style their images deliberately are therefore left alone; only pages
  where nothing decided the alignment are centred.

### Fixed
- The portable build showed no icon in the taskbar or window. PyInstaller's
  `icon=` only stamps the executable's resource, which is what Explorer draws;
  Qt needs the file at runtime, and Windows needs an explicit AppUserModelID or
  it groups the process under the host interpreter.

## 0.2.0

### Added
- Self-contained Windows build: PyInstaller distribution bundling the Python
  runtime, Qt, a jlink-built Java runtime and EPUBCheck, plus an Inno Setup
  installer and a portable ZIP. Nothing needs to be installed on the target
  machine.
- Polish interface with tooltips that describe what each option does to the
  book, and per-item tooltips on the rebuild modes.
- Fluent-flavoured styling with light and dark variants selected from the
  system palette.
- Repair of publisher CSS errors: `font-style`/`font-weight: regular`, which is
  not a CSS value and caused parsers to discard the whole declaration.
- Image-only paragraphs are opted out of body-text indentation and centred, so
  cover and title artwork is no longer shifted by rules meant for running text.
- Stylesheet findings are surfaced: reader-specific properties such as
  `adobe-hyphenate`, and font stacks that end without a generic family.
- `--strict` removes reader-specific CSS properties and out-of-flow positioning.

### Changed
- The report now accounts for structural work. Upgrading the package from
  EPUB 2 to 3.3, relocating files and generating a navigation document count as
  fixes; a real rebuild can no longer report "0 fixed".
- Media types the manifest declares incorrectly are reported rather than being
  corrected silently.
- The GUI gained a "Kept" column so deliberate deviations are visible without
  opening the report.

### Fixed
- Content documents recovered by the HTML parser serialised with an `html:`
  prefix on every element instead of a default namespace.
- Fragment identifiers in the navigation document and NCX were not remapped
  when the ids they pointed at had to be renamed.
- Spine-order filename prefixes accumulated (`0000-0000-…`) when a book was
  rebuilt more than once.

### Reverted
- Out-of-flow positioning is no longer stripped from reflowable books by
  default. A rule such as `div.dol { position: absolute; bottom: 0 }` pins a
  dedication to the foot of the page — that is a layout the publisher chose,
  not a defect, so it is now reported and kept unless `--strict` is used.

## 0.1.0

Initial version: reads any EPUB 2 or 3 into a format-neutral model and
regenerates a conforming EPUB 3.3 container from it — package document,
navigation, manifest, spine, filenames and ZIP layout. Legacy presentational
markup is translated to equivalent CSS rather than dropped, obfuscated fonts
are deobfuscated, and non-core image formats are transcoded with references
rewritten. DRM is detected and refused.
