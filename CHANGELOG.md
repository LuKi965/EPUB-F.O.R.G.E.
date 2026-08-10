# Changelog

Maturity is stated in words, not encoded in the number: `__stage__` sits beside
`__version__` and appears wherever the version does — `alpha` today. MINOR
moves only when the stage does, against the entry conditions in
`CONTRIBUTING.md`. PATCH moves on every release, whatever it contains, so there
is no judgement call to make and therefore no way for one to drift upwards.

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
