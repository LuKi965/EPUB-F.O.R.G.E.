"""Every finding this program can report, by a name that does not change.

The identity of a finding used to be its English sentence. Three things follow
from that, and all three had already happened:

* tests assert fragments of sentences, so rewording a message breaks a test
  that was never about the wording — it did, during 0.8.0;
* `survey.py` has to strip numbers and quoted fragments with regular
  expressions before it can count anything, which is a symptom rather than a
  solution;
* the report cannot be translated. A sentence that *is* the identity cannot be
  replaced by its Polish equivalent without changing what it identifies, which
  is why the interface is bilingual and the report is not.

So a finding carries a `rule` — `nav.repointed`, `xhtml.doctype-modernised` —
and the sentence becomes what it should have been all along: the human-readable
rendering of something else.

The catalogue below is the list of what exists. It is not documentation that
happens to sit near the code: `test_rules.py` fails if a finding is reported
under an id that is not here, and fails if an id here is reported by nothing.
Both directions, because a catalogue that drifts is worse than none — it is
consulted and believed.

Identifiers are `<area>.<what>`, lower case, hyphen-separated. The area is the
part of the program the reader would blame, not necessarily the module that
raised it.
"""

from __future__ import annotations

import re
import string

#: id → one line saying what the finding means. English for now; this mapping is
#: the thing a translation replaces, and the reason it exists.
CATALOGUE: dict[str, str] = {
    # -- reader: what the source turned out to be ---------------------------
    "reader.remote-resource": "the manifest declares a resource hosted elsewhere",
    "reader.dangling-reference": "{attribute} names an id the manifest does not define",
    "reader.name-rewritten": "an archive entry name was not a container path and was rewritten",
    "reader.name-dropped": "an archive entry name could not be made into a container path: {reason}",
    "reader.duplicate-entry": "the archive holds the same entry name twice",
    "reader.colliding-names": "{count} entry names differ only by {kind}",
    "reader.entry-too-large": "an archive entry is implausibly large and was refused: {reason}",
    "reader.meta-inf-carried": "a reserved container file was carried through untouched: it says something about the publication that this rebuild does not change",
    "reader.meta-inf-invalidated": "a digital signature or container inventory was removed, because the rebuild makes it untrue: a signature is computed over exact bytes and cannot survive them changing, and one left in place would read as evidence of tampering rather than of a repair",
    "reader.meta-inf-unknown-carried": "a file this program does not recognise was found beside the container document and carried through unchanged rather than judged",
    "reader.manifest-id-duplicated": "two manifest items share the id {id} ({first} and {second}); the spine entries that name it could mean either, and this rebuild will not pick one for you",
    "reader.entry-unreadable": "an archive entry could not be read at all: {error}",
    "reader.rootfile-missing": "container.xml points at a package document that is not in the archive",
    "reader.container-missing": "META-INF/container.xml is missing, so the package was located by scanning",
    "reader.package-scanned": "the package document was recovered by scanning the archive",
    "reader.metadata-missing": "the package has no <metadata> element",
    "reader.manifest-missing": "the package has no <manifest>, so the archive contents were used instead",
    "reader.manifest-file-missing": "the manifest lists a file that is not in the archive",
    "reader.manifest-case-matched": "a manifest entry matched a file only when case was ignored",
    "reader.manifest-type-corrected": "the manifest declared {declared}, which is not what the file is; corrected to {actual}",
    "reader.spine-missing": "the package has no <spine>",
    "reader.spine-id-unknown": "the reading order referenced a manifest id that does not exist",
    "reader.ncx-unparseable": "the legacy NCX could not be parsed",
    "reader.nav-unparseable": "the navigation document could not be parsed",
    "reader.encryption-unparseable": "META-INF/encryption.xml could not be parsed",
    "reader.drm": "the archive declares real encryption, not just font obfuscation",
    "reader.mimetype-invalid": "the mimetype entry is missing or wrong and will be regenerated",
    "reader.page-direction-carried": "the page progression direction is {direction} and was carried through",
    "reader.toc-from-ncx": "the table of contents was recovered from the legacy NCX",
    "reader.ncx-unreferenced-used": "an NCX nothing referenced was found and used for the table of contents",
    "reader.unmanifested-file": "a file is in the archive but absent from the manifest",
    "reader.spine-rebuilt": "the reading order was empty and was rebuilt from {count} content documents",
    # -- structure: where files ended up ------------------------------------
    "structure.relaid-out": "{count} file(s) were regrouped into a typed {directory}/ layout with portable names",
    "structure.junk-removed": "packaging leftovers were removed",
    "structure.orphan-removed": "a file nothing in the book references was removed",
    "structure.carried-xml-repointed": "{count} reference(s) inside a file carried as-is were repointed",
    # -- navigation ---------------------------------------------------------
    "nav.regenerated": "the navigation document was regenerated, with {count} entries",
    "nav.generated": "the book had no navigation document and one was generated, with {count} entries",
    "nav.contents-page-kept": "the publisher's contents page was kept and the navigation put beside it",
    "nav.repointed": "{count} reference(s) to the replaced navigation document were repointed",
    "nav.kept-in-spine": "the navigation document stayed in the reading order, where the source had it",
    "nav.entry-dropped": "{count} table-of-contents entry/entries pointed at something that is not there",
    "nav.fragment-cleared": "{count} navigation anchor(s) do not exist, so the entries now point at the document",
    "nav.toc-synthesised": "the book had no usable table of contents and one was built from {count} spine documents",
    "nav.cover-page-generated": "a cover page was generated so the artwork is the first spine item",
    "nav.ncx-written": "a legacy NCX was written alongside the navigation document",
    "nav.ncx-dropped": "the legacy NCX was not carried over",
    "nav.cover-image-missing": "the declared cover image is not in the archive",
    # -- content documents --------------------------------------------------
    "xhtml.untouched": "content documents were left as they were; only the container was rebuilt",
    "xhtml.untouched-except-doctype": "content documents were left as they were apart from the DOCTYPE; only the container was rebuilt",
    "xhtml.doctype-modernised": "a legacy DOCTYPE was replaced with the EPUB 3 one in {count} document(s)",
    "xhtml.orphaned-styling-restored": "{count} class(es) the document uses but no stylesheet it links defines were given the publisher's own rule: {classes}",
    "xhtml.empty-span-found": "{count} <span>(s) whose every rule says nothing — a conversion artefact; they are kept",
    "xhtml.empty-span-unwrapped": "{count} <span>(s) unwrapped whose every rule said nothing; the text inside is untouched",
    "xhtml.epub2-only-markup": "markup legal in EPUB 2 and not in EPUB 3 stays untouched in this mode: {what}",
    "xhtml.title-filled": "{count} empty <title> element(s) were given the document's own heading",
    "xhtml.doctype-kept": "{count} document(s) keep a legacy DOCTYPE because an entity cannot be resolved: {documents}",
    "xhtml.entities-rewritten": "undefined named entities were rewritten as numeric references",
    "xhtml.property-withdrawn": "manifest properties the document does not bear out were withdrawn: {properties}",
    "typography.ellipsis-normalised": "{count} run(s) of three dots became a single ellipsis character",
    "typography.conjunctions-bound": "{count} single-letter conjunction(s) were bound to the word after them",
    "typography.quotes-retyped": "{count} straight quote(s) were retyped into the book's own convention ({convention})",
    "typography.quotes-unsettled": "the book has not settled on a quoting convention, so its quotes were left alone",
    "typography.reverted": "{count} document(s) were put back unchanged: the typography pass could not show it kept the text",
    # -- profile -------------------------------------------------------------
    "profile.made-by": "the book carries traces of {count} tool(s): {tools}",
    "profile.body-text-found": "the body text is {shape}: {percent}% of {blocks} paragraph(s)",
    "profile.body-text-inconsistent": "no shape covers the body text; the commonest reaches {percent}% of {blocks} paragraph(s)",
    "profile.paragraphs-mixed": "paragraphs are separated both ways: {indented} by indent, {spaced} by space",
    "profile.paragraphs-consistent": "every paragraph is separated the same way: {paradigm}",
    "profile.dead-classes-found": "{count} class(es) are declared in CSS and used by nothing",
    "profile.duplicate-classes-found": "{names} class(es) in {groups} group(s) declare exactly the same thing",
    "profile.scene-separators-found": "{count} scene separator(s) were found",
    "profile.break-runs-found": "{count} run(s) of <br/> stand in for a paragraph break",
    "profile.heading-candidates-found": "{count} paragraph(s) look like headings without being marked as one",
    # -- stylesheets --------------------------------------------------------
    "css.url-unresolved": "{count} url() reference(s) could not be resolved and were left unchanged",
    "css.remote-import-removed": "{count} @import rule(s) fetching a stylesheet over the network were removed",
    "xhtml.remote-import-removed": "{count} @import rule(s) fetching a stylesheet over the network were removed from a style element",
    "css.vendor-at-rule-kept": "{count} vendor-specific at-rule(s) targeting particular readers were kept",
    "css.kindle-media-removed": "Kindle-specific @media blocks were removed",
    "css.invalid-value-corrected": "{count} declaration(s) using the invalid value 'regular' were corrected",
    "css.unreachable-rules-found": "{count} of {total} rule(s) — {share}% of this stylesheet — name a class or id that appears nowhere in the book",
    "css.unreachable-rules-removed": "{count} of {total} rule(s) removed — {share}% of this stylesheet — naming a class or id that appears nowhere in the book",
    "css.unreachable-rules-scripted": "{count} rule(s) match nothing today, and are kept because the book carries a script",
    "css.unreachable-rules-unverified": "{count} rule(s) look unreachable but the sheet did not survive the check, so it was left as it was",
    "css.position-kept": "{count} absolute or fixed position rule(s) were kept",
    "css.position-kept-reflowable": "{count} absolute or fixed position rule(s) were kept in a reflowable book",
    "css.position-contained": "{count} out-of-flow position rule(s) are held inside a positioned ancestor in {documents} document(s) and were kept",
    "xhtml.position-pinned-in-flow": "content pinned to the foot of the page was translated into an in-flow equivalent",
    "css.position-superseded": "out-of-flow positioning is superseded in {count} document(s) by the equivalent written into them",
    "css.position-removed": "{count} absolute or fixed position rule(s) were removed from a reflowable book",
    "css.reader-property-kept": "{count} reader-specific CSS propert(ies) inherited from the source were kept",
    "css.reader-property-removed": "{count} reader-specific CSS propert(ies) were removed",
    "css.font-stack-generic-added": "{count} font stack(s) gained the generic family the embedded font declares about itself",
    "css.font-stack-generic-missing": "{count} font stack(s) end without a generic family",
    "css.unparseable": "a stylesheet could not be parsed for validation: {error}",
    "css.no-usable-rules": "a stylesheet contains no usable rules",
    "xhtml.unparseable": "a content document could not be parsed at all: {error}",
    "xhtml.recovered-with-html-parser": "a document was not well-formed XML and was recovered with an HTML parser",
    "xhtml.dtd-entities-resolved": "{count} entity/entities declared in the document's own DTD were resolved",
    "xhtml.dtd-entities-refused": "{count} entity/entities were left as references rather than resolved",
    "xhtml.watermark-consolidated": "{count} watermark marker(s) across {documents} document(s) became one rule",
    "xhtml.watermark-relocated": "{count} watermark marker(s) across {documents} document(s) moved out of the text into document metadata",
    "xhtml.watermark-removed": "{count} watermark marker(s) across {documents} document(s) were deleted at your request",
    "xhtml.watermark-kept": "{count} visible watermark notice(s) were left exactly as the publisher wrote them",
    "xhtml.watermark-kept-personal-data": "{count} visible watermark notice(s) carrying personal data were left exactly as the publisher wrote them",
    "xhtml.ids-renamed": "{count} id attribute(s) were not valid XML names and were renamed",
    "xhtml.document-language-kept": "the document says it is written in {document} and the publication says {publication}; the document was believed, because a book with two languages in it is a book and not a mistake",
    "package.budget-exceeded": "this book asks for more than one book is allowed: {limit} came to {found} where {allowed} is the ceiling, so nothing was written",
    "package.not-written": "the rebuilt book could not be written where it was asked to go: {error}. The source is untouched and every other book in this run is unaffected",
    "package.invariant-failed": "{count} thing(s) about the rebuilt book are not true, so nothing was written: {detail}",
    "structure.reference-bearing-kept": "a {media_type} file links to {count} other file(s) in this book ({names}) and nothing here can rewrite those links, so it was left exactly where the publisher put it rather than moved to a file that no longer exists",
    "xhtml.encoding-mended": "this document said it was in one encoding and its bytes were in another ({encoding}); it was read as what it is rather than parsed with the difference substituted away, which is how a character of a book disappears without anybody being told",
    "xhtml.document-language-corrected": "the document said it was written in {was} and its own text is plainly Polish, so it now says {now}; a reading system speaks this attribute to its voice and hyphenates by it",
    "xhtml.duplicate-ids-renamed": "{count} id attribute(s) appeared more than once in the same document ({names}); the first of each keeps its name and the later ones were renamed, so every existing link still lands where it did",
    "nav.unspined-target-added": "the table of contents led to {count} document(s) the reading order did not hold ({names}); each was added to it as linear=\"no\", which is reachable from the contents without page-turning ever arriving there",
    "css.direction-default-removed": "{count} declaration(s) set the text direction a style sheet already has; EPUB 3 does not allow the property there and this one said nothing, so it was removed",
    "css.direction-kept": "{count} declaration(s) set a text direction the page depends on ({declarations}); EPUB 3 says the markup should carry it instead, and they were kept rather than have the page come out mirrored",
    "xhtml.head-added": "a missing <head> element was added",
    "xhtml.body-added": "a missing <body> element was added",
    "xhtml.dead-reference-kept": "{count} reference(s) point at files not in the book and were left unchanged",
    "xhtml.dead-reference-neutralised": "{count} reference(s) to files absent from the book were neutralised",
    "xhtml.dead-fragment-dropped": "{count} link(s) pointed at an anchor no document defines; the fragment was dropped",
    "xhtml.presentational-markup-converted": "legacy presentational markup was converted to CSS",
    "xhtml.image-paragraph-centred": "{count} image-only paragraph(s) were centred and their text indent removed",
    "xhtml.image-paragraph-unindented": "a running-text indent was removed from {count} image paragraph(s)",
    "xhtml.image-paragraph-kept": "{count} image paragraph(s) were left as the publisher styled them",
    "xhtml.cover-fitted": "the cover image was given page-fitting limits, because nothing in the book set any",
    "xhtml.inline-promoted": "{count} inline element(s) containing block-level content were promoted",
    "xhtml.cover-described": "the cover image was described with the book title",
    "xhtml.empty-alt-added": "an empty alt attribute was added to {count} image(s)",
    "xhtml.scripts-kept": "{count} script element(s) were kept and the document was declared scripted",
    "xhtml.scripts-removed": "{count} script element(s) and {handlers} inline handler(s) were removed",
    # -- metadata -----------------------------------------------------------
    "metadata.override-applied": "the caller overrode the metadata field {field}",
    "metadata.title-missing": "the source has no dc:title and a placeholder was inserted",
    "metadata.titles-collapsed": "{count} dc:title elements were collapsed to one main title",
    "metadata.language-invalid": "the language tag {was} is not valid BCP 47 and was replaced with {now}",
    "metadata.language-corrected": "the declared language {was} is contradicted by the text; corrected to {now}",
    "metadata.language-missing": "the source has no dc:language, so {now} was used",
    "metadata.identifier-minted": "the source has no dc:identifier and a UUID was minted",
    "metadata.identifier-promoted": "no unique-identifier was declared and the first one was promoted",
    "metadata.date-normalised": "dc:date was normalised to ISO 8601: {was} became {now}",
    "metadata.date-unparseable": "dc:date {was} could not be parsed and was dropped",
    "metadata.creator-missing": "the source names no dc:creator",

    # -- images -------------------------------------------------------------
    "image.pillow-unavailable": "Pillow is not installed, so images passed through unchecked",
    "image.unreadable": "an image could not be decoded and was kept as it was: {error}",
    "image.type-corrected": "a file is really {actual} though it was declared {declared}",
    "image.type-kept": "{media_type} is not a core EPUB 3 type but was kept by policy",
    "image.renamed": "a file was renamed to .{suffix}, the format it really is",
    "image.transcode-failed": "transcoding failed and the original was kept: {error}",
    "image.transcoded": "an image was transcoded from {media_type} to PNG for universal reader support",
    "image.animation-kept": "a {media_type} image holding {frames} frames was left exactly as it was: converting it would have kept the first frame and silently dropped the rest",

    # -- fonts --------------------------------------------------------------
    "font.type-corrected": "a font's media type was corrected to {actual}, from the declared {declared}",
    "font.unrecognised": "a font has no recognisable signature",
    "font.drm": "the content is DRM-encrypted and the rebuild cannot proceed safely",
    "font.obfuscation-kept": "font obfuscation was left in place by policy",
    "font.obfuscation-unkeyed": "fonts are obfuscated but the package has no identifier to key on",
    "font.deobfuscation-failed": "deobfuscation did not yield a valid font, so the file was left alone",
    "font.deobfuscated": "{count} embedded font(s) were deobfuscated and the encryption file dropped",

    # -- compatibility profiles ---------------------------------------------
    "compat.unknown-profile": "the compatibility profile {profile} does not exist and was ignored",
    "compat.applied": "compatibility profiles were applied: {profiles}",
    "compat.legacy-font-types": "{count} embedded font(s) are declared by the media type Adobe RMSDK knows, not the one EPUB 3.3 registers",
    "compat.ncx-required": "a selected profile needs the legacy NCX, which was switched off",
    "compat.stylesheet-added": "{stylesheet} was linked into {count} document(s)",
    "compat.page-break-mirrored": "{count} fragmentation declaration(s) were mirrored into page-break-*",
    "compat.specified-fonts-skipped": "the book embeds no fonts, so the Apple declaration was skipped",
    "compat.specified-fonts-added": "specified-fonts was declared for Apple Books",
    "compat.guide-skipped": "nothing in the book maps onto a legacy <guide>",
    "compat.guide-added": "the EPUB 2 <guide> element was added for readers that look for it",
    "compat.svg-cover": "the cover page wraps its image in SVG, which some converters mishandle",

    # -- accessibility ------------------------------------------------------
    "a11y.conformance-declared": "conformance with {profile} was declared because the caller asserted it",
    "a11y.metadata-added": "EPUB Accessibility 1.1 discovery metadata was added",
    "a11y.missing-alt": "{count} image(s) have no usable alt text",
    "a11y.placeholder-alt": "{count} image(s) have alt text that only repeats the file name",
    "a11y.heading-jump": "heading levels skip a rank in {count} place(s)",
    "a11y.table-without-headers": "{count} table(s) have no header cells",

    # -- package ------------------------------------------------------------
    "package.upgraded": "the package was rebuilt from EPUB {version} to 3.3",
    "package.regenerated": "the source was already EPUB {version} and the package was regenerated anyway",
    "package.layout-kept": "the package document stayed at {path}, because the files around it did not move",
    "package.version-unusable": "the package declared no usable version and was treated as EPUB 2",
    "package.unreadable-source": "the source file could not be read: {error}",
    "package.stage-failed": "the {stage} stage raised, so nothing was written: {error}",
    "package.input-incomplete": "{count} entry(ies) of the source could not be read ({names}), so nothing was written; a rebuild that cannot see part of the book cannot promise to keep it",
    "package.input-incomplete-allowed": "{count} entry(ies) of the source could not be read ({names}) and the rebuild went ahead anyway, because it was told to: what those entries held is not in the output",
    "package.layout-unusable": "the source keeps its package document at {path}, which is not a path this may write ({reason}), so the standard layout was used instead",
    "package.source-protected": "writing over the source file was refused",
    "package.spine-item-vanished": "a spine item was gone by the time the package was written",
    # -- validation ---------------------------------------------------------
    "epubcheck.reported": "EPUBCheck reported {fatal} fatal and {errors} error(s)",
    "epubcheck.clean": "EPUBCheck accepted the output, with {warnings} warning(s)",
    "epubcheck.unavailable": "EPUBCheck is not installed, so the output was not validated",
    "epubcheck.failed": "EPUBCheck could not be run at all: {error}",
    # -- the window ---------------------------------------------------------
    "gui.unexpected-failure": "the rebuild failed in a way nothing anticipated: {error}",
}


#: The same catalogue in Polish. Separate mapping rather than a tuple per entry
#: so that adding a language is adding a file-sized block and not editing
#: seventy-seven lines — and `test_rules.py` holds the two to the same key set,
#: because a half-translated catalogue silently falls back to English and looks
#: like a translation that is finished.
CATALOGUE_PL: dict[str, str] = {
    'reader.remote-resource': 'manifest deklaruje zasób trzymany gdzie indziej',
    'reader.dangling-reference': '{attribute} wskazuje na identyfikator, którego manifest nie definiuje',
    'reader.name-rewritten': 'nazwa wpisu w archiwum nie była ścieżką kontenera i została przepisana',
    'reader.name-dropped': 'nazwy wpisu w archiwum nie dało się zamienić na ścieżkę kontenera: {reason}',
    'reader.duplicate-entry': 'archiwum zawiera tę samą nazwę wpisu dwa razy',
    'reader.colliding-names': '{count} {count:nazwa wpisu różni się|nazwy wpisów różnią się|nazw wpisów różni się} tylko przez {kind}',
    'reader.entry-too-large': 'wpis w archiwum jest niewiarygodnie duży i został odrzucony: {reason}',
    'reader.meta-inf-carried': 'zarezerwowany plik kontenera przeniesiono bez zmian: mówi o publikacji coś, czego ta przebudowa nie zmienia',
    'reader.meta-inf-invalidated': 'usunięto podpis cyfrowy albo spis zawartości kontenera, bo przebudowa czyni go nieprawdziwym: podpis liczy się z dokładnych bajtów i nie przetrwa ich zmiany, a zostawiony wyglądałby na dowód manipulacji zamiast na ślad naprawy',
    'reader.meta-inf-unknown-carried': 'obok dokumentu kontenera znaleziono plik, którego ten program nie rozpoznaje — przeniesiono go bez zmian, zamiast go oceniać',
    'reader.manifest-id-duplicated': 'dwie pozycje manifestu mają ten sam identyfikator {id} ({first} i {second}); wpisy spine\u2019a, które go wskazują, mogą znaczyć jedno albo drugie, a ta przebudowa nie wybierze za ciebie',
    'reader.entry-unreadable': 'wpisu w archiwum w ogóle nie dało się odczytać: {error}',
    'reader.rootfile-missing': 'container.xml wskazuje na dokument pakietu, którego nie ma w archiwum',
    'reader.container-missing': 'brakuje META-INF/container.xml, więc pakiet znaleziono przez przeszukanie archiwum',
    'reader.package-scanned': 'dokument pakietu odzyskano, przeszukując archiwum',
    'reader.metadata-missing': 'pakiet nie ma elementu <metadata>',
    'reader.manifest-missing': 'pakiet nie ma elementu <manifest>, więc użyto zawartości archiwum',
    'reader.manifest-file-missing': 'manifest wymienia plik, którego nie ma w archiwum',
    'reader.manifest-case-matched': 'wpis manifestu pasował do pliku dopiero po pominięciu wielkości liter',
    'reader.manifest-type-corrected': 'manifest deklarował {declared}, czym plik nie jest; poprawiono na {actual}',
    'reader.spine-missing': 'pakiet nie ma elementu <spine>',
    'reader.spine-id-unknown': 'kolejność czytania wskazywała na nieistniejący identyfikator w manifeście',
    'reader.ncx-unparseable': 'starego NCX nie dało się sparsować',
    'reader.nav-unparseable': 'dokumentu nawigacyjnego nie dało się sparsować',
    'reader.encryption-unparseable': 'pliku META-INF/encryption.xml nie dało się sparsować',
    'reader.drm': 'archiwum deklaruje prawdziwe szyfrowanie, a nie samo zaciemnienie czcionek',
    'reader.mimetype-invalid': 'wpis mimetype jest nieobecny albo błędny i zostanie zapisany od nowa',
    'reader.page-direction-carried': 'kierunek czytania to {direction} i został przeniesiony bez zmian',
    'reader.toc-from-ncx': 'spis treści odzyskano ze starego NCX',
    'reader.ncx-unreferenced-used': 'znaleziono NCX, do którego nic się nie odwoływało, i użyto go jako spisu treści',
    'reader.unmanifested-file': 'plik jest w archiwum, ale nie ma go w manifeście',
    'reader.spine-rebuilt': 'kolejność czytania była pusta i odtworzono ją z {count} {count:dokumentu treści|dokumentów treści|dokumentów treści}',
    'structure.relaid-out': '{count} {count:plik przegrupowano|pliki przegrupowano|plików przegrupowano} w układ według typów w {directory}/, z przenośnymi nazwami',
    'structure.junk-removed': 'usunięto pozostałości po pakowaniu',
    'structure.orphan-removed': 'usunięto plik, do którego nic w książce się nie odwołuje',
    'structure.carried-xml-repointed': 'przepięto {count} {count:odwołanie|odwołania|odwołań} wewnątrz pliku przenoszonego bez zmian',
    'nav.regenerated': 'dokument nawigacyjny wygenerowano od nowa, z {count} {count:pozycją|pozycjami|pozycjami}',
    'nav.generated': 'książka nie miała dokumentu nawigacyjnego i został utworzony, z {count} {count:pozycją|pozycjami|pozycjami}',
    'nav.contents-page-kept': 'zachowano stronę spisu treści wydawcy, a wygenerowaną nawigację umieszczono obok',
    'nav.repointed': 'przepięto {count} {count:odwołanie|odwołania|odwołań} do zastąpionego dokumentu nawigacyjnego',
    'nav.kept-in-spine': 'dokument nawigacyjny został w kolejności czytania, tam gdzie miało go źródło',
    'nav.entry-dropped': '{count} {count:pozycja spisu treści wskazywała|pozycje spisu treści wskazywały|pozycji spisu treści wskazywało} na coś, czego nie ma',
    'nav.fragment-cleared': '{count} {count:kotwica nawigacyjna nie istnieje|kotwice nawigacyjne nie istnieją|kotwic nawigacyjnych nie istnieje}, więc pozycje wskazują teraz na sam dokument',
    'nav.toc-synthesised': 'książka nie miała używalnego spisu treści; zbudowano go z {count} {count:dokumentu|dokumentów|dokumentów} kolejności czytania',
    'nav.cover-page-generated': 'wygenerowano stronę okładki, żeby grafika była pierwsza w kolejności czytania',
    'nav.ncx-written': 'zapisano stary plik NCX obok dokumentu nawigacyjnego, dla starszych czytników',
    'nav.ncx-dropped': 'stary plik NCX nie został przeniesiony; EPUB 3 nawiguje dokumentem nawigacyjnym',
    'nav.cover-image-missing': 'zadeklarowany obraz okładki nie znajduje się w archiwum',
    'xhtml.untouched': 'dokumenty treści zostały bez zmian; przebudowano wyłącznie kontener',
    'xhtml.untouched-except-doctype': 'dokumenty treści zostały bez zmian poza DOCTYPE; przebudowano wyłącznie kontener',
    'xhtml.doctype-modernised': 'stary DOCTYPE zastąpiono tym z EPUB 3 w {count} {count:dokumencie|dokumentach|dokumentach}',
    'xhtml.orphaned-styling-restored': '{count} {count:klasie|klasom|klasom}, których dokument używa, a nie definiuje ich żaden podpięty do niego arkusz, przywrócono własną regułę wydawcy: {classes}',
    'xhtml.empty-span-found': '{count} {count:element <span>, którego reguły nic nie mówią|elementy <span>, których reguły nic nie mówią|elementów <span>, których reguły nic nie mówią} — ślad konwersji; zostają',
    'xhtml.empty-span-unwrapped': 'rozwinięto {count} {count:element <span>|elementy <span>|elementów <span>}, których reguły nic nie mówiły; tekst w środku nietknięty',
    'xhtml.epub2-only-markup': 'znaczniki dozwolone w EPUB 2, a niedozwolone w EPUB 3, zostają w tym trybie nietknięte: {what}',
    'xhtml.title-filled': '{count} {count:pustemu elementowi|pustym elementom|pustym elementom} <title> nadano nagłówek samego dokumentu',
    'xhtml.doctype-kept': '{count} {count:dokument zachowuje|dokumenty zachowują|dokumentów zachowuje} stary DOCTYPE, bo encji nie da się rozwiązać: {documents}',
    'xhtml.entities-rewritten': 'niezadeklarowane encje nazwane przepisano na referencje numeryczne',
    'xhtml.property-withdrawn': 'wycofano właściwości manifestu, których dokument nie potwierdza: {properties}',
    # -- profile -------------------------------------------------------------
    'typography.ellipsis-normalised': '{count} {count:ciąg trzech kropek stał się|ciągi trzech kropek stały się|ciągów trzech kropek stało się} pojedynczym wielokropkiem',
    'typography.conjunctions-bound': '{count} {count:jednoliterowy spójnik związano|jednoliterowe spójniki związano|jednoliterowych spójników związano} z następującym po nim słowem',
    'typography.quotes-retyped': '{count} {count:prosty cudzysłów przepisano|proste cudzysłowy przepisano|prostych cudzysłowów przepisano} na własną konwencję książki ({convention})',
    'typography.quotes-unsettled': 'książka nie ustaliła jednej konwencji cudzysłowu, więc zostawiono je bez zmian',
    'typography.reverted': '{count} {count:dokument przywrócono|dokumenty przywrócono|dokumentów przywrócono} bez zmian: przebieg typograficzny nie potrafił wykazać, że zachował tekst',
    'profile.made-by': 'książka nosi ślady {count} {count:narzędzia|narzędzi|narzędzi}: {tools}',
    'profile.body-text-found': 'tekst główny to {shape}: {percent}% z {blocks} {blocks:akapitu|akapitów|akapitów}',
    'profile.body-text-inconsistent': 'żaden kształt nie obejmuje tekstu głównego; najczęstszy sięga {percent}% z {blocks} {blocks:akapitu|akapitów|akapitów}',
    'profile.paragraphs-mixed': 'akapity oddzielane są na oba sposoby: {indented} wcięciem, {spaced} odstępem',
    'profile.paragraphs-consistent': 'akapity oddzielane są konsekwentnie ({paradigm})',
    'profile.dead-classes-found': '{count} {count:klasa jest zadeklarowana|klasy są zadeklarowane|klas jest zadeklarowanych} w CSS i {count:nie używa jej nic|nie używa ich nic|nie używa ich nic}',
    'profile.duplicate-classes-found': '{names} {names:klasa w|klasy w|klas w} {groups} {groups:grupie deklaruje|grupach deklaruje|grupach deklaruje} dokładnie to samo',
    'profile.scene-separators-found': 'znaleziono {count} {count:separator scen|separatory scen|separatorów scen}',
    'profile.break-runs-found': '{count} {count:ciąg <br/> zastępuje|ciągi <br/> zastępują|ciągów <br/> zastępuje} przerwę akapitową',
    'profile.heading-candidates-found': '{count} {count:akapit wygląda jak nagłówek|akapity wyglądają jak nagłówki|akapitów wygląda jak nagłówki}, nie będąc nim oznaczone',
    # -- stylesheets --------------------------------------------------------
    'css.url-unresolved': '{count} {count:odwołania url() nie dało się rozwiązać|odwołań url() nie dało się rozwiązać|odwołań url() nie dało się rozwiązać} i zostały bez zmian',
    'css.remote-import-removed': 'usunięto {count} {count:regułę @import pobierającą arkusz stylów z sieci|reguły @import pobierające arkusz stylów z sieci|reguł @import pobierających arkusz stylów z sieci}',
    'xhtml.remote-import-removed': 'usunięto z elementu <style> {count} {count:regułę @import pobierającą arkusz stylów z sieci|reguły @import pobierające arkusz stylów z sieci|reguł @import pobierających arkusz stylów z sieci}',
    'css.vendor-at-rule-kept': 'zachowano {count} {count:regułę @|reguły @|reguł @} charakterystyczną dla konkretnych czytników',
    'css.kindle-media-removed': 'usunięto bloki @media przeznaczone dla Kindle',
    'css.invalid-value-corrected': 'poprawiono {count} {count:deklarację|deklaracje|deklaracji} z niepoprawną wartością „regular”',
    'css.unreachable-rules-found': '{count} z {total} {count:reguła nazywa|reguły nazywają|reguł nazywa} klasę lub id, których nie ma nigdzie w książce — {share}% tego arkusza',
    'css.unreachable-rules-removed': 'usunięto {count} z {total} {count:regułę|reguły|reguł} nazywającą klasę lub id, których nie ma nigdzie w książce — {share}% tego arkusza',
    'css.unreachable-rules-scripted': '{count} {count:reguła nie pasuje|reguły nie pasują|reguł nie pasuje} dziś do niczego i zostaje, bo książka niesie skrypt',
    'css.unreachable-rules-unverified': '{count} {count:reguła wygląda|reguły wyglądają|reguł wygląda} na nieosiągalne, ale arkusz nie przeszedł kontroli, więc został bez zmian',
    'css.position-kept': 'zachowano {count} {count:regułę pozycjonowania|reguły pozycjonowania|reguł pozycjonowania} absolutnego lub stałego',
    'css.position-kept-reflowable': 'zachowano {count} {count:regułę pozycjonowania|reguły pozycjonowania|reguł pozycjonowania} absolutnego lub stałego w książce przepływalnej',
    'css.position-contained': '{count} {count:reguła pozycjonowania poza przepływem jest trzymana|reguły pozycjonowania poza przepływem są trzymane|reguł pozycjonowania poza przepływem jest trzymanych} wewnątrz pozycjonowanego przodka w {documents} {documents:dokumencie|dokumentach|dokumentach} i zostały zachowane',
    'xhtml.position-pinned-in-flow': 'treść przypiętą do stopki strony przetłumaczono na odpowiednik działający w przepływie',
    'css.position-superseded': 'pozycjonowanie poza przepływem jest zastąpione w {count} {count:dokumencie|dokumentach|dokumentach} odpowiednikiem wpisanym do nich',
    'css.position-removed': 'usunięto {count} {count:regułę pozycjonowania|reguły pozycjonowania|reguł pozycjonowania} absolutnego lub stałego z książki przepływalnej',
    'css.reader-property-kept': 'zachowano {count} {count:właściwość CSS|właściwości CSS|właściwości CSS} charakterystyczną dla czytników, odziedziczoną ze źródła',
    'css.reader-property-removed': 'usunięto {count} {count:właściwość CSS|właściwości CSS|właściwości CSS} charakterystyczną dla czytników',
    'css.font-stack-generic-added': '{count} {count:stos czcionek dostał|stosy czcionek dostały|stosów czcionek dostało} generyczną rodzinę, którą osadzona czcionka deklaruje o sobie sama',
    'css.font-stack-generic-missing': '{count} {count:lista krojów kończy się|listy krojów kończą się|list krojów kończy się} bez rodziny generycznej',
    'css.unparseable': 'arkusza stylów nie dało się sparsować do sprawdzenia: {error}',
    'css.no-usable-rules': 'arkusz stylów nie zawiera żadnych używalnych reguł',
    'xhtml.unparseable': 'dokumentu treści w ogóle nie dało się sparsować: {error}',
    'xhtml.recovered-with-html-parser': 'dokument nie był poprawnym XML-em i został odzyskany parserem HTML',
    'xhtml.dtd-entities-resolved': 'rozwiązano {count} {count:encję|encje|encji} zadeklarowaną w DTD samego dokumentu',
    'xhtml.dtd-entities-refused': '{count} {count:encję pozostawiono|encje pozostawiono|encji pozostawiono} jako odwołania zamiast je rozwiązać',
    'xhtml.watermark-consolidated': '{count} {count:znacznik znaku wodnego|znaczniki znaku wodnego|znaczników znaku wodnego} w {documents} {documents:dokumencie|dokumentach|dokumentach} sprowadzono do jednej reguły',
    'xhtml.watermark-relocated': '{count} {count:znacznik znaku wodnego|znaczniki znaku wodnego|znaczników znaku wodnego} w {documents} {documents:dokumencie|dokumentach|dokumentach} przeniesiono z treści do metadanych dokumentu',
    'xhtml.watermark-removed': '{count} {count:znacznik znaku wodnego|znaczniki znaku wodnego|znaczników znaku wodnego} w {documents} {documents:dokumencie|dokumentach|dokumentach} usunięto na Twoje życzenie',
    'xhtml.watermark-kept': '{count} {count:widoczną adnotację|widoczne adnotacje|widocznych adnotacji} znaku wodnego zostawiono dokładnie tak, jak napisał je wydawca',
    'xhtml.watermark-kept-personal-data': '{count} {count:widoczną adnotację|widoczne adnotacje|widocznych adnotacji} znaku wodnego z danymi osobowymi zostawiono dokładnie tak, jak napisał je wydawca',
    'xhtml.ids-renamed': '{count} {count:atrybut id nie był poprawną nazwą XML|atrybuty id nie były poprawnymi nazwami XML|atrybutów id nie było poprawnymi nazwami XML} i zostały przemianowane',
    'xhtml.document-language-kept': 'dokument mówi, że jest napisany w {document}, a publikacja mówi {publication}; uwierzono dokumentowi, bo książka z dwoma językami jest książką, a nie pomyłką',
    'package.budget-exceeded': 'ta książka prosi o więcej, niż wolno jednej książce: {limit} wyszło {found}, a sufit to {allowed} — nic nie zapisano',
    'package.not-written': 'przebudowanej książki nie dało się zapisać tam, gdzie miała trafić: {error}. Źródło jest nietknięte, a pozostałe książki w tym przebiegu to nie dotyczy',
    'package.invariant-failed': '{count} {count:rzecz w przebudowanej książce nie jest prawdą|rzeczy w przebudowanej książce nie są prawdą|rzeczy w przebudowanej książce nie jest prawdą}, więc nic nie zapisano: {detail}',
    'structure.reference-bearing-kept': 'plik {media_type} odwołuje się do {count} {count:innego pliku|innych plików|innych plików} tej książki ({names}), a nic tutaj nie umie przepisać tych odwołań — został więc dokładnie tam, gdzie umieścił go wydawca, zamiast wskazywać plik, którego już nie ma',
    'xhtml.encoding-mended': 'ten dokument twierdził, że jest w jednym kodowaniu, a jego bajty były w innym ({encoding}); odczytano go jako to, czym jest, zamiast sparsować z podmianą różnicy — bo tak właśnie znika znak książki i nikt się o tym nie dowiaduje',
    'xhtml.document-language-corrected': 'dokument twierdził, że jest w {was}, a jego własny tekst jest ewidentnie polski, więc mówi teraz {now}; czytnik podaje ten atrybut syntezatorowi mowy i dzieli po nim wyrazy',
    'xhtml.duplicate-ids-renamed': '{count} {count:atrybut id powtarzał się|atrybuty id powtarzały się|atrybutów id powtarzało się} w tym samym dokumencie ({names}); pierwszy z każdej pary zachowuje nazwę, późniejsze przemianowano — każdy istniejący odnośnik trafia tam, gdzie trafiał',
    'nav.unspined-target-added': 'spis treści prowadził do {count} {count:dokumentu, którego|dokumentów, których|dokumentów, których} nie było w kolejności czytania ({names}); dodano je do niej jako linear="no", czyli osiągalne ze spisu, ale przewracanie stron nigdy tam nie trafi',
    'css.direction-default-removed': '{count} {count:deklaracja ustawiała|deklaracje ustawiały|deklaracji ustawiało} kierunek tekstu, który arkusz i tak ma; EPUB 3 nie pozwala na tę własność w arkuszu, a ta nic nie wnosiła — usunięto',
    'css.direction-kept': '{count} {count:deklaracja ustawia|deklaracje ustawiają|deklaracji ustawia} kierunek tekstu, od którego zależy wygląd strony ({declarations}); EPUB 3 chce tego w znacznikach, ale zostawiono — inaczej strona wyszłaby odbita',
    'xhtml.head-added': 'dodano brakujący element <head>',
    'xhtml.body-added': 'dodano brakujący element <body>',
    'xhtml.dead-reference-kept': '{count} {count:odwołanie wskazuje|odwołania wskazują|odwołań wskazuje} na pliki, których w książce nie ma; zostawiono je bez zmian',
    'xhtml.dead-reference-neutralised': 'unieszkodliwiono {count} {count:odwołanie|odwołania|odwołań} do plików nieobecnych w książce',
    'xhtml.dead-fragment-dropped': '{count} {count:odnośnik wskazywał|odnośniki wskazywały|odnośników wskazywało} na kotwicę, której żaden dokument nie definiuje; usunięto fragment',
    'xhtml.presentational-markup-converted': 'stare znaczniki prezentacyjne zamieniono na CSS',
    'xhtml.image-paragraph-centred': 'wyśrodkowano {count} {count:akapit zawierający sam obraz|akapity zawierające sam obraz|akapitów zawierających sam obraz} i usunięto z nich wcięcie',
    'xhtml.image-paragraph-unindented': 'usunięto wcięcie tekstu bieżącego z {count} {count:akapitu z obrazem|akapitów z obrazem|akapitów z obrazem}',
    'xhtml.image-paragraph-kept': '{count} {count:akapit z obrazem zostawiono|akapity z obrazem zostawiono|akapitów z obrazem zostawiono} tak, jak {count:ostylował go|ostylował je|ostylował je} wydawca',
    'xhtml.cover-fitted': 'obrazowi okładki nadano ograniczenia dopasowujące go do strony, bo nic w książce ich nie ustawiało',
    'xhtml.inline-promoted': '{count} {count:element liniowy zawierający treść blokową|elementy liniowe zawierające treść blokową|elementów liniowych zawierających treść blokową} zamieniono na blokowe',
    'xhtml.cover-described': 'obraz okładki opisano tytułem książki',
    'xhtml.empty-alt-added': 'dodano pusty atrybut alt do {count} {count:obrazu|obrazów|obrazów}',
    'xhtml.scripts-kept': '{count} {count:element skryptu zachowano|elementy skryptu zachowano|elementów skryptu zachowano}, a dokument zadeklarowano jako skryptowany',
    'xhtml.scripts-removed': 'usunięto {count} {count:element skryptu|elementy skryptu|elementów skryptu} i {handlers} {handlers:liniową obsługę zdarzeń|liniowe obsługi zdarzeń|liniowych obsług zdarzeń}',
    'metadata.override-applied': 'wywołujący nadpisał pole metadanych {field}',
    'metadata.title-missing': 'źródło nie ma dc:title; wstawiono zastępczy',
    'metadata.titles-collapsed': '{count} {count:element dc:title sprowadzono|elementy dc:title sprowadzono|elementów dc:title sprowadzono} do jednego tytułu głównego',
    'metadata.language-invalid': 'znacznik języka {was} nie jest poprawnym BCP 47 i został zastąpiony przez {now}',
    'metadata.language-corrected': 'zadeklarowany język {was} jest sprzeczny z tekstem; poprawiono na {now}',
    'metadata.language-missing': 'źródło nie ma dc:language, więc użyto {now}',
    'metadata.identifier-minted': 'źródło nie ma dc:identifier; wygenerowano UUID',
    'metadata.identifier-promoted': 'nie zadeklarowano unique-identifier; awansowano pierwszy',
    'metadata.date-normalised': 'dc:date sprowadzono do ISO 8601: {was} stało się {now}',
    'metadata.date-unparseable': 'dc:date {was} nie dało się odczytać i zostało pominięte',
    'metadata.creator-missing': 'źródło nie podaje dc:creator',
    'image.pillow-unavailable': 'Pillow nie jest zainstalowany, więc obrazy przeszły niesprawdzone',
    'image.unreadable': 'obrazu nie dało się odczytać i został bez zmian: {error}',
    'image.type-corrected': 'plik jest w rzeczywistości {actual}, choć zadeklarowano {declared}',
    'image.type-kept': '{media_type} nie jest typem rdzenia EPUB 3, ale zachowano go zgodnie z polityką',
    'image.renamed': 'plik przemianowano na .{suffix} — taki format naprawdę ma',
    'image.transcode-failed': 'transkodowanie się nie powiodło; zachowano oryginał: {error}',
    'image.transcoded': 'obraz przekodowano z {media_type} na PNG dla zgodności z czytnikami',
    'image.animation-kept': 'obraz {media_type} z {frames} {frames:klatką|klatkami|klatkami} zostawiono dokładnie takim, jaki był: konwersja zachowałaby pierwszą klatkę i po cichu wyrzuciła resztę',
    'font.type-corrected': 'typ MIME czcionki poprawiono na {actual}; zadeklarowany był {declared}',
    'font.unrecognised': 'czcionka nie ma rozpoznawalnej sygnatury',
    'font.drm': 'treść jest zabezpieczona DRM; przebudowa nie może przebiec bezpiecznie',
    'font.obfuscation-kept': 'zaciemnienie czcionek zostawione zgodnie z polityką',
    'font.obfuscation-unkeyed': 'czcionki są zaciemnione, ale pakiet nie ma identyfikatora, na którym można je oprzeć',
    'font.deobfuscation-failed': 'odciemnianie nie dało poprawnej czcionki; plik został bez zmian',
    'font.deobfuscated': 'odciemniono {count} {count:osadzoną czcionkę|osadzone czcionki|osadzonych czcionek} i usunięto plik szyfrowania',
    'compat.unknown-profile': 'profil zgodności {profile} nie istnieje i został pominięty',
    'compat.applied': 'zastosowano profile zgodności: {profiles}',
    'compat.legacy-font-types': '{count} {count:osadzona czcionka jest zadeklarowana|osadzone czcionki są zadeklarowane|osadzonych czcionek jest zadeklarowanych} typem, który zna Adobe RMSDK, a nie tym, który rejestruje EPUB 3.3',
    'compat.ncx-required': 'wybrany profil wymaga starego NCX, który był wyłączony',
    'compat.stylesheet-added': '{stylesheet} podlinkowano do {count} {count:dokumentu|dokumentów|dokumentów}',
    'compat.page-break-mirrored': '{count} {count:deklarację łamania odwzorowano|deklaracje łamania odwzorowano|deklaracji łamania odwzorowano} na page-break-*',
    'compat.specified-fonts-skipped': 'książka nie osadza czcionek, więc pominięto deklarację dla Apple',
    'compat.specified-fonts-added': 'zadeklarowano specified-fonts dla Apple Books',
    'compat.guide-skipped': 'nic w książce nie odwzorowuje się na stary <guide>',
    'compat.guide-added': 'dodano element <guide> z EPUB 2 dla czytników, które go szukają',
    'compat.svg-cover': 'strona okładki opakowuje grafikę w SVG, co część konwerterów obsługuje źle',
    'a11y.conformance-declared': 'zadeklarowano zgodność z {profile}, bo wywołujący to stwierdził',
    'a11y.metadata-added': 'dodano metadane dostępności EPUB Accessibility 1.1',
    'a11y.missing-alt': '{count} {count:obraz nie ma|obrazy nie mają|obrazów nie ma} używalnego tekstu alternatywnego',
    'a11y.placeholder-alt': '{count} {count:obraz ma|obrazy mają|obrazów ma} tekst alternatywny powtarzający tylko nazwę pliku',
    'a11y.heading-jump': 'poziomy nagłówków przeskakują stopień w {count} {count:miejscu|miejscach|miejscach}',
    'a11y.table-without-headers': '{count} {count:tabela nie ma|tabele nie mają|tabel nie ma} komórek nagłówkowych',
    'package.upgraded': 'pakiet przebudowano z EPUB {version} na 3.3',
    'package.regenerated': 'źródło było już EPUB {version}, a pakiet i tak wygenerowano od nowa',
    'package.layout-kept': 'dokument pakietu został w {path}, bo pliki wokół niego się nie przesunęły',
    'package.version-unusable': 'pakiet nie deklarował używalnej wersji; potraktowano go jak EPUB 2',
    'package.unreadable-source': 'pliku źródłowego nie dało się odczytać: {error}',
    'package.stage-failed': 'etap {stage} zgłosił wyjątek, więc nic nie zostało zapisane: {error}',
    'package.input-incomplete': 'nie udało się odczytać {count} {count:wpisu|wpisów|wpisów} źródła ({names}), więc nic nie zapisano; przebudowa, która nie widzi części książki, nie może obiecać, że ją zachowa',
    'package.input-incomplete-allowed': 'nie udało się odczytać {count} {count:wpisu|wpisów|wpisów} źródła ({names}), a przebudowa i tak poszła dalej, bo tak jej kazano: tego, co w nich było, nie ma w wyniku',
    'package.layout-unusable': 'źródło trzyma dokument pakietu w {path}, a to nie jest ścieżka, którą wolno tu zapisać ({reason}), więc użyto układu standardowego',
    'package.source-protected': 'odmówiono nadpisania pliku źródłowego',
    'package.spine-item-vanished': 'pozycja kolejności czytania zniknęła, zanim pakiet został zapisany',
    'epubcheck.reported': 'EPUBCheck zgłosił {fatal} błędów krytycznych i {errors} błędów',
    'epubcheck.clean': 'EPUBCheck przyjął wynik, z {warnings} ostrzeżeniem/ami',
    'epubcheck.unavailable': 'EPUBCheck nie jest zainstalowany, więc wynik nie został zweryfikowany',
    'epubcheck.failed': 'EPUBCheck w ogóle nie dał się uruchomić: {error}',
    # -- the window ---------------------------------------------------------
    'gui.unexpected-failure': 'przebudowa zawiodła w sposób, którego nic nie przewidziało: {error}',
}

#: The paragraph beneath a finding, in English, keyed by the same identifier.
#:
#: It used to be written at the call site, where it lived beside the sentence it
#: explains and nowhere near the Polish version of itself. Two homes for one
#: fact is one home too many: they drifted, and nothing could see them drift.
#:
#: A rule missing from here has a paragraph that is data rather than prose — a
#: list of names, a generated identifier, EPUBCheck's own output — and passes it
#: at the call site instead. `test_rules.py` names those and their reason.
DETAILS: dict[str, str] = {
    "a11y.conformance-declared":
        "EPUB-Forge did not verify this; it is the publisher's assertion.",
    "a11y.missing-alt":
        "Either the attribute is absent or it is empty. An empty alt asserts the image is decorative, and that cannot be checked mechanically — only role=\"presentation\" or aria-hidden=\"true\" says it outright. So alternativeText is not claimed. If any of these images carry meaning, only a human can write the description.",
    "a11y.placeholder-alt":
        "{examples} — this passes validation but tells a screen-reader user nothing, so alternativeText is not claimed.",
    "a11y.table-without-headers":
        "Screen readers cannot announce what a cell relates to without <th>.",
    "compat.guide-added":
        "EPUB 3.3 no longer defines this element, though EPUBCheck still accepts it: the output stays valid, but it carries something the current specification dropped. Amazon's converter and RMSDK readers find the cover and the start-reading position here and nowhere else.",
    "compat.ncx-required":
        "Readers predating EPUB 3 build their chapter list from the NCX and ignore the navigation document. Drop --no-ncx to restore it.",
    "compat.page-break-mirrored":
        "The modern break-* properties are left exactly as they are; the legacy spelling is added beside them for renderers that only know that one.",
    "compat.specified-fonts-added":
        "Without this file Apple Books ignores every embedded face and substitutes its own.",
    "compat.specified-fonts-skipped":
        "Declaring it anyway would state something the book does not do.",
    "compat.stylesheet-added":
        "Declares the HTML5 sectioning elements as blocks. It is linked ahead of the book's own stylesheets, so every rule the publisher wrote still overrides it.",
    "compat.svg-cover":
        "The wrapper is what scales the artwork to the page, so removing it would change the layout on every other reader. Left as it is; replace it with a plain <img> by hand if the Kindle cover comes out wrong.",
    "compat.unknown-profile":
        "Known profiles: {known}.",
    "css.font-stack-generic-missing":
        "e.g. {examples} — inherited from the source and left as-is, since guessing serif vs sans-serif could change how the book looks.",
    "css.invalid-value-corrected":
        "font-style/font-weight have no 'regular' keyword, so parsers dropped these rules entirely. Replaced with 'normal', which is what was meant.",
    "css.unreachable-rules-found":
        "Shops ship one house stylesheet into every title they sell, and most of it is for markup the particular book has not got — `td.proc4` in a novel with no tables. It changes no pixel either way. Use --strict to remove it; this mode reports and keeps, because a selector matching nothing in the documents we parsed is not the same claim as a selector matching nothing.",
    "css.unreachable-rules-removed":
        "Only rules whose every branch names a class or id absent from the whole book. A bare tag selector, an attribute selector, a pseudo-class and anything inside @media are never touched. The cut is then checked by re-parsing the sheet and comparing the survivors; a sheet that does not match is put back untouched.",
    "css.unreachable-rules-scripted":
        "A script can add a class while the book is being read, so 'this matches nothing' would be a statement about the file rather than about the reading.",
    "css.unreachable-rules-unverified":
        "The rules stay. A removal that cannot be shown to have taken exactly what it meant to is not one this tool makes.",
    "css.position-kept":
        "This is a fixed-layout book, where out-of-flow positioning is how it works.",
    "xhtml.position-pinned-in-flow":
        "`margin-top: auto` inside a flex column puts a block at the foot of the page exactly as `bottom: 0` was meant to, and keeps it in the flow, so pagination cannot lose it. Written into the one document that needs it, never into the shared stylesheet — flexing every body in a book would stop adjacent margins collapsing on every page of it. Only where the page is that one block: with siblings there is no faithful translation, so the rule is left alone and reported instead.",
    "css.position-contained":
        "An absolutely positioned element resolves against its nearest positioned ancestor, not against the page — a caption over a picture, a badge on a cover. It travels with the box that holds it, so pagination cannot lose it and the argument for removing out-of-flow positioning does not reach it. Kept even under --strict, which used to delete it and drop the caption below the image on every reader.",
    "css.position-superseded":
        "The declaration is still in the stylesheet and no longer decides anything: the document carries an equivalent that outranks it. Left in place because deleting from a shared sheet would reach documents nobody examined.",
    "css.position-removed":
        "The affected blocks now flow with the page instead of being pinned to it. Kept out of fixed-layout books, where out-of-flow positioning is how the format works. On a real reader a dedication pinned this way came out as a blank page — the block left the flow and pagination went round it.",
    "css.reader-property-kept":
        "{names} — validators flag these as unknown. Use --strict to remove them.",
    "css.vendor-at-rule-kept":
        "Use --strict to remove them.",
    "epubcheck.unavailable":
        "Install it and set {variable}, or put epubcheck on PATH.",
    "font.deobfuscated":
        "Fonts render identically and the container no longer depends on the identifier.",
    "font.deobfuscation-failed":
        "The source identifier likely differs from the one used to obfuscate it.",
    "font.drm":
        "Remove DRM with a tool you are licensed to use before running EPUB-Forge.",
    "image.transcoded":
        "was {was}",
    "metadata.title-missing":
        "Pass --title to set the real one.",
    "nav.contents-page-kept":
        "The page is in the reading order, so it is something the reader turns to. Replacing it with generated markup would lose whatever the publisher wrote there.",
    "nav.fragment-cleared":
        "The entry now points at the document, which is where the reader would land anyway.",
    "nav.generated":
        "The source had none; its table of contents came from the NCX.",
    "nav.kept-in-spine":
        "A nav document in the spine is a page the reader can turn to. Regenerating it used to remove that page.",
    "nav.repointed":
        "{in_tables} in the navigation tables, {in_documents} inside content documents. The source's own contents page is replaced, and a reference left pointing at it makes the book invalid, not merely inconsistent.",
    "package.layout-kept":
        "This rebuild does not move content files, so moving the package document away from them would leave every manifest href pointing back out of its own directory with `../`.",
    "package.source-protected":
        "Nothing was written. Choose a different destination.",
    "package.stage-failed":
        "Nothing was written. The model was left half-modified by the failure, so anything built from it would be a book only in shape.",
    "package.upgraded":
        "Package document, navigation and container structure were regenerated.",
    "reader.colliding-names":
        "They are separate files inside the archive and one file on a filesystem that folds case or Unicode normalisation — which is most of them outside Linux. Anyone unpacking this book loses one.",
    "reader.dangling-reference":
        "{reference} — the reference is dropped rather than guessed at",
    "reader.drm":
        "EPUB-Forge will not attempt to decrypt DRM-protected content.",
    "reader.entry-too-large":
        "No real book contains this; the archive is broken or hostile.",
    "reader.name-dropped":
        "Nothing in a conforming EPUB is named this way. It is not carried into the output, where it would be somebody else's problem to unpack safely.",
    "reader.remote-resource":
        "Nothing here fetches it. It is not stored in the container either.",
    "structure.carried-xml-repointed":
        "The pipeline does not model this file type, but it does move the files it points at. Leaving the references alone would have produced an invalid book rather than a poorer one.",
    "structure.orphan-removed":
        "{bytes} bytes reclaimed",
    "structure.relaid-out":
        "{renamed} file(s) needed a new name; every reference was rewritten to match",
    "xhtml.cover-fitted":
        "No stylesheet rule and no attribute sized this image, so a reader would show it at its own pixel dimensions.",
    "profile.paragraphs-mixed":
        "A book from one source does not mix the two. When it does, somebody glued two files together or ran one through two tools — which is worth knowing before any rule tries to normalise the paragraphs.",
    "profile.body-text-inconsistent":
        "Rules that ask whether a construction is this book's norm have no norm to compare against here. The percentage is kept rather than rounded away, because how far off a book was is what a rule declining to fire will want to say.",
    "xhtml.dead-reference-kept":
        "These are source defects and remain conformance errors. Use --strict to neutralise them.",
    "xhtml.dead-fragment-dropped":
        "The file each link names is present; the anchor inside it is not. Keeping the fragment leaves an error nobody can act on, so the link now lands at the top of the right document instead of nowhere.",
    "css.remote-import-removed":
        "EPUB 3 allows one kind of remote resource — a font declared on its manifest item — and a stylesheet is not one. The font-family declarations are untouched, so the book falls back exactly as it would have.",
    "xhtml.remote-import-removed":
        "EPUB 3 allows one kind of remote resource — a font declared on its manifest item — and a stylesheet is not one. The font-family declarations are untouched, so the book falls back exactly as it would have.",
    "xhtml.dead-reference-neutralised":
        "{unlinked} link(s) unlinked, {removed} element(s) removed",
    "xhtml.doctype-kept":
        "The output stays an invalid EPUB 3 in those documents, and that is the lesser harm: replacing the declaration would strand the reference and the book would no longer open at all. Rebuild this book in a mode that rewrites content.",
    "xhtml.orphaned-styling-restored":
        "The rule exists in this book, in a stylesheet this document does not link, and exactly one stylesheet has it — so there is nothing to choose between. Copied into the document verbatim rather than linking the whole sheet, which would import every other decision in it into a page it was not written for. Not applied when two sheets disagree, nor to rules that fetch something with url().",
    "xhtml.empty-span-found":
        "Measured over 12 475 spans in thirty-two books: 97% do something, and the ones that do not are all PDF conversion — `.reset { margin: 0; padding: 0 }` on an inline box where those are the defaults, and `.black { color: #010000 }`, black moved by one part in 255. A span nothing styles at all is left alone: the largest such class in the corpus was 219 drop caps whose stylesheet had come unlinked.",
    "xhtml.empty-span-unwrapped":
        "Unwrapped, not deleted — the text inside stays exactly where it was. Only spans with no id, lang, epub:type, role, dir, title or style, and only where a rule reaches them and every declaration in it is the default for an inline box.",
    "xhtml.epub2-only-markup":
        "Container-only mode edits the head and nothing else, so this stays and the output is an invalid EPUB 3 through no fault of the content. Rebuild in \"preserve\" for a conformant file — that mode moves these into CSS and renders the same. Named as found rather than claimed complete: anything not listed still shows up in a validator.",
    "xhtml.title-filled":
        "EPUB 2 allowed an empty <title>; EPUB 3 does not, and this rebuild produces EPUB 3. The text is not rendered in the body, so nothing on the page moves. In container-only mode this is the second and last edit made inside a document.",
    "xhtml.doctype-modernised":
        "The only change this mode makes inside a document. A DOCTYPE says nothing about rendering, and a legacy one makes the book invalid. A DOCTYPE that declares its own entities is left alone, because the document uses them.",
    "xhtml.dtd-entities-refused":
        "{names}. Either they point outside the file, which this tool will not fetch, or expanding them would have grown the document past any plausible size.",
    "xhtml.dtd-entities-resolved":
        "{names}. The declarations lived in the DOCTYPE, which EPUB 3 replaces with one that declares nothing — so without this the references would have appeared on the page as literal text.",
    "xhtml.empty-alt-added":
        "Required for valid markup. It is not treated as a description: the accessibility stage still counts these images as undescribed, so nothing is claimed on their behalf.",
    "xhtml.image-paragraph-centred":
        "Running-text rules were shifting the artwork; no rule targeted these paragraphs specifically, so the layout was inherited rather than chosen.",
    "xhtml.image-paragraph-kept":
        "A rule aimed at these paragraphs, or at an element containing them, sets their alignment or indent.",
    "xhtml.image-paragraph-unindented":
        "A rule aimed at these paragraphs or their container decides where the image sits; the indent reached them from a rule about body text.",
    "xhtml.inline-promoted":
        "A block box inside an inline box splits the line and makes margins and centring behave unpredictably; inline-block is a legal container that keeps the element where it was.",
    "xhtml.property-withdrawn":
        "Declaring one of these without the markup to match is a conformance error in its own right, and EPUBCheck reports it against the source.",
    "xhtml.untouched":
        "Every XHTML file comes out byte for byte as it went in.",
    "xhtml.untouched-except-doctype":
        "Every XHTML file comes out byte for byte as it went in, apart from the DOCTYPE where it had to be modernised.",
    "xhtml.watermark-consolidated":
        "{tokens} distinct token(s), text unchanged. The repeated inline !important style became one rule, and the markers are hidden from screen readers instead of being spelled out each chapter.",
    "xhtml.watermark-relocated":
        "{tokens} distinct token(s), text unchanged, now carried as <meta name=\"{name}\"> in the head of the document each one came from. Still in the file and still traceable, but no longer laid out, paginated or read aloud — which a token at font-size zero still was.",
    "xhtml.watermark-removed":
        "{tokens} distinct token(s), gone. The book no longer carries the mark that ties this copy to its buyer.",
    "metadata.language-corrected":
        "{rate} Polish-only letters per 1000 characters of the book's own text. A reading system speaks dc:language to its text-to-speech engine and hyphenates by it, so a wrong declaration is read aloud in the wrong voice and broken across lines by the wrong rules — neither of which any validator mentions. --language overrides this.",
    "css.font-stack-generic-added":
        "Read from the font's OS/2 table — PANOSE, ten bytes the designer filled in — not inferred from its name. A stack with no generic family falls back to whatever the reader likes when the embedded font fails to load, which on an e-reader it often does.",
    "xhtml.watermark-kept":
        "Meant to be read, so left exactly as the publisher wrote it.",
    "xhtml.watermark-kept-personal-data":
        "Carries personal data ({data}). Meant to be read, so left exactly as the publisher wrote it.",
}

#: The paragraph beneath a finding, in Polish, keyed by the same identifier.
#:
#: Kept apart from `CATALOGUE_PL` because it is a different kind of text and
#: has a different completion state: the headline is one sentence and every one
#: of them is translated, while a detail is prose and some of them are not text
#: at all — a list of names, a byte count, an example the reader is meant to
#: read verbatim. Those have nothing to translate and are marked by their
#: absence here rather than by a copied English line, which is what a stalled
#: translation looks like.
#:
#: The English detail stays exactly where it was written, at the call site.
#: Nothing here replaces it: this is what a Polish reader gets instead.
DETAILS_PL: dict[str, str] = {
    "reader.dangling-reference":
        "{reference} — odwołanie jest pomijane, a nie zgadywane.",
    "a11y.placeholder-alt":
        "{examples} — to przechodzi walidację, ale użytkownikowi czytnika ekranu nie mówi nic, więc alternativeText nie jest deklarowane.",
    "compat.unknown-profile":
        "Znane profile: {known}.",
    "xhtml.dead-reference-neutralised":
        "{unlinked} {unlinked:odnośnik odlinkowano|odnośniki odlinkowano|odnośników odlinkowano}, {removed} {removed:element usunięto|elementy usunięto|elementów usunięto}.",
    "css.font-stack-generic-missing":
        "np. {examples} — odziedziczone ze źródła i zostawione bez zmian, bo zgadywanie między szeryfową a bezszeryfową mogłoby zmienić wygląd książki.",
    "xhtml.untouched":
        "Każdy plik XHTML wychodzi bajt w bajt taki, jaki wszedł.",
    "xhtml.untouched-except-doctype":
        "Każdy plik XHTML wychodzi bajt w bajt taki, jaki wszedł, poza DOCTYPE, który trzeba było unowocześnić.",
    "xhtml.dtd-entities-resolved":
        "{names}. Deklaracje mieszkały w DOCTYPE, który EPUB 3 zastępuje takim, co nie deklaruje niczego — więc bez tego odwołania pojawiłyby się na stronie jako dosłowny tekst.",
    "xhtml.dtd-entities-refused":
        "{names}. Albo wskazują poza plik, czego to narzędzie nie pobiera, albo ich rozwinięcie rozdęłoby dokument ponad bezpieczną granicę.",
    "xhtml.watermark-consolidated":
        "{tokens} {tokens:odrębny token|odrębne tokeny|odrębnych tokenów}, tekst bez zmian. Powtarzany styl liniowy z !important stał się jedną regułą, a znaczniki są ukryte przed czytnikami ekranu, zamiast być wypowiadane w każdym rozdziale.",
    "xhtml.watermark-relocated":
        "{tokens} {tokens:odrębny token|odrębne tokeny|odrębnych tokenów}, tekst bez zmian, teraz jako <meta name=\"{name}\"> w nagłówku tego dokumentu, z którego pochodzi. Wciąż w pliku i wciąż do odczytania, ale już nie na stronie: nic go nie składa, nie łamie i nie czyta na głos — a token o zerowym stopniu pisma wciąż tam był.",
    "xhtml.watermark-removed":
        "{tokens} {tokens:odrębny token|odrębne tokeny|odrębnych tokenów} — nie ma. Książka nie niesie już znaku, który wiąże ten egzemplarz z kupującym.",
    "metadata.language-corrected":
        "{rate} liter wyłącznie polskich na 1000 znaków własnego tekstu książki. Czytnik podaje dc:language syntezatorowi mowy i po nim dzieli wyrazy, więc zła deklaracja to czytanie niewłaściwym głosem i łamanie niewłaściwymi regułami — o żadnym z tych dwóch nie powie ci walidator. --language to nadpisuje.",
    "css.font-stack-generic-added":
        "Odczytane z tablicy OS/2 samej czcionki — PANOSE, dziesięć bajtów wpisanych przez projektanta — a nie wywnioskowane z nazwy. Stos bez rodziny generycznej spada na cokolwiek, co czytnik uzna za stosowne, gdy osadzona czcionka się nie wczyta, a na czytniku zdarza się to często.",
    "xhtml.watermark-kept":
        "Ma być czytane, więc zostawione dokładnie tak, jak napisał to wydawca.",
    "xhtml.watermark-kept-personal-data":
        "Zawiera dane osobowe ({data}). Ma być czytane, więc zostawione dokładnie tak, jak napisał to wydawca.",
    "css.reader-property-kept":
        "{names} — walidatory zgłaszają je jako nieznane. Użyj --strict, żeby je usunąć.",
    "image.transcoded":
        "było {was}",
    "nav.repointed":
        "{in_tables} w tablicach nawigacyjnych, {in_documents} wewnątrz dokumentów treści. Własna strona spisu treści źródła zostaje zastąpiona, a odwołanie zostawione na nią czyni książkę niepoprawną, nie tylko niespójną.",
    "structure.orphan-removed":
        "odzyskano {bytes} {bytes:bajt|bajty|bajtów}",
    "structure.relaid-out":
        "{renamed} {renamed:plik potrzebował|pliki potrzebowały|plików potrzebowało} nowej nazwy; każde odwołanie zostało przepisane, żeby się zgadzało",
    "epubcheck.unavailable":
        "Zainstaluj go i ustaw {variable}, albo umieść epubcheck w PATH.",
    "package.layout-kept":
        "Ta przebudowa nie przesuwa plików treści, więc odsunięcie od nich dokumentu pakietu zostawiłoby każdy odnośnik manifestu wskazujący z powrotem poza własny katalog, przez „../”.",
    "package.upgraded":
        "Dokument pakietu, nawigacja i struktura kontenera zostały wygenerowane od nowa.",
    "package.source-protected":
        "Nic nie zostało zapisane. Wybierz inne miejsce docelowe.",
    "package.stage-failed":
        "Nic nie zostało zapisane. Awaria zostawiła model w połowie zmieniony, więc cokolwiek by z niego zbudowano, byłoby książką tylko z kształtu.",
    "reader.entry-too-large":
        "Żadna prawdziwa książka tego nie zawiera; archiwum jest uszkodzone albo wrogie.",
    "reader.colliding-names":
        "W archiwum to osobne pliki, a na systemie plików zwijającym wielkość liter albo Unicode — jeden. Który z nich przetrwa, zależy od kolejności rozpakowania.",
    "reader.drm":
        "EPUB F.O.R.G.E. nie próbuje odszyfrowywać treści chronionej DRM.",
    "reader.remote-resource":
        "Nic tutaj tego nie pobiera. Nie jest to też przechowywane w kontenerze.",
    "reader.name-dropped":
        "Nic w poprawnym EPUB-ie nie nazywa się w ten sposób. Wpis nie trafia do wyniku, gdzie i tak byłby nieosiągalny.",
    "a11y.conformance-declared":
        "EPUB F.O.R.G.E. tego nie zweryfikował; to oświadczenie wydawcy.",
    "a11y.missing-alt":
        "Albo atrybutu nie ma, albo jest pusty. Pusty alt oświadcza, że obraz jest dekoracyjny, a tego nie da się sprawdzić maszynowo — mówi to wprost dopiero role=\"presentation\" albo aria-hidden=\"true\". Dlatego alternativeText nie jest deklarowane. Jeśli któryś z tych obrazów niesie treść, opis może napisać tylko człowiek.",
    "a11y.table-without-headers":
        "Bez <th> czytnik ekranu nie ma jak ogłosić, do czego odnosi się komórka.",
    "compat.ncx-required":
        "Czytniki starsze niż EPUB 3 budują listę rozdziałów z NCX i ignorują dokument nawigacyjny.",
    "compat.stylesheet-added":
        "Deklaruje elementy sekcjonujące HTML5 jako blokowe. Jest podlinkowany przed arkuszem samej książki, więc jej własne reguły nadal wygrywają.",
    "compat.page-break-mirrored":
        "Nowoczesne właściwości break-* zostają dokładnie takie, jakie były; stary zapis dochodzi obok nich, a nie zamiast nich.",
    "compat.specified-fonts-added":
        "Bez tego pliku Apple Books ignoruje każdy osadzony krój i podstawia własny.",
    "compat.guide-added":
        "EPUB 3.3 już nie definiuje tego elementu, choć EPUBCheck wciąż go przyjmuje: wynik pozostaje poprawny.",
    "compat.svg-cover":
        "To opakowanie skaluje grafikę do strony, więc jego usunięcie zmieniłoby układ na każdym czytniku, który radzi sobie z SVG.",
    "compat.specified-fonts-skipped":
        "Zadeklarowanie tego mimo wszystko stwierdzałoby coś, czego książka nie robi.",
    "css.position-removed":
        "Objęte bloki płyną teraz razem ze stroną, zamiast być do niej przypięte.",
    "profile.paragraphs-mixed":
        "Książka z jednego źródła nie miesza obu sposobów. Kiedy miesza, ktoś skleił dwa pliki albo przepuścił jeden przez dwa narzędzia — a to warto wiedzieć, zanim jakakolwiek reguła spróbuje ujednolicić akapity.",
    "profile.body-text-inconsistent":
        "Reguły pytające, czy dana konstrukcja jest w tej książce normą, nie mają się tu do czego odnieść. Procent zostaje zamiast zostać zaokrąglonym do „brak”, bo to, jak bardzo książce brakowało, jest tym, co powie reguła, która odmówi zadziałania.",
    "xhtml.dead-reference-kept":
        "To są defekty źródła i pozostają błędami zgodności. Użyj --strict, żeby je unieszkodliwić.",
    "xhtml.dead-fragment-dropped":
        "Plik, który wskazuje każdy z tych odnośników, jest na miejscu; kotwicy w nim nie ma. Zostawienie fragmentu to błąd, z którym nikt nic nie zrobi, więc odnośnik prowadzi teraz na początek właściwego dokumentu, a nie donikąd.",
    "css.remote-import-removed":
        "EPUB 3 dopuszcza jeden rodzaj zasobu zdalnego — font zadeklarowany przy pozycji manifestu — a arkusz stylów nim nie jest. Deklaracje font-family zostają nietknięte, więc książka podstawia kroje dokładnie tak, jak podstawiłaby wcześniej.",
    "xhtml.remote-import-removed":
        "EPUB 3 dopuszcza jeden rodzaj zasobu zdalnego — font zadeklarowany przy pozycji manifestu — a arkusz stylów nim nie jest. Deklaracje font-family zostają nietknięte, więc książka podstawia kroje dokładnie tak, jak podstawiłaby wcześniej.",
    "xhtml.image-paragraph-centred":
        "Reguły tekstu bieżącego przesuwały grafikę; żadna reguła nie celowała w te akapity z osobna, więc nic, co wybrał wydawca, nie zostało nadpisane.",
    "xhtml.image-paragraph-unindented":
        "O położeniu obrazu decyduje reguła celująca w te akapity albo w ich kontener; wcięcie dotyczy tekstu bieżącego, którego tu nie ma.",
    "xhtml.image-paragraph-kept":
        "Reguła celująca w te akapity — albo w element, który je zawiera — ustawia ich wyrównanie lub wcięcie.",
    "xhtml.cover-fitted":
        "Żadna reguła arkusza ani żaden atrybut nie nadał temu obrazowi rozmiaru, więc czytnik pokazałby go w jego własnych pikselach.",
    "xhtml.inline-promoted":
        "Pudełko blokowe wewnątrz liniowego łamie wiersz i sprawia, że marginesy oraz środkowanie zachowują się nieprzewidywalnie — różnie na różnych czytnikach.",
    "xhtml.empty-alt-added":
        "Wymagany przez poprawną składnię. Nie jest traktowany jako opis: etap dostępności nadal liczy te obrazy jako pozbawione tekstu alternatywnego.",
    "xhtml.property-withdrawn":
        "Zadeklarowanie którejś z nich bez odpowiadających jej znaczników jest samo w sobie błędem zgodności i EPUBCheck zgłasza to wobec źródła.",
    "css.vendor-at-rule-kept":
        "Użyj --strict, żeby je usunąć.",
    "css.invalid-value-corrected":
        "font-style ani font-weight nie mają słowa kluczowego „regular”, więc parsery odrzucały te reguły w całości. Zastąpione przez „normal”.",
    "css.unreachable-rules-found":
        "Księgarnie wgrywają jeden firmowy arkusz do każdego sprzedawanego tytułu i większość z niego dotyczy znaczników, których dana książka nie ma — `td.proc4` w powieści bez tabel. Tak czy inaczej nie zmienia to ani piksela. Użyj --strict, żeby to usunąć; ten tryb raportuje i zostawia, bo selektor niepasujący do niczego w sparsowanych przez nas dokumentach to nie to samo, co selektor niepasujący do niczego.",
    "css.unreachable-rules-removed":
        "Tylko reguły, których każda gałąź nazywa klasę lub id nieobecne w całej książce. Goły selektor znacznika, selektor atrybutu, pseudoklasa i wszystko wewnątrz @media pozostają nietknięte. Cięcie jest następnie sprawdzane przez ponowne sparsowanie arkusza i porównanie tego, co zostało; arkusz, który się nie zgadza, wraca bez zmian.",
    "css.unreachable-rules-scripted":
        "Skrypt może dodać klasę w trakcie czytania, więc „nie pasuje do niczego” byłoby zdaniem o pliku, a nie o lekturze.",
    "css.unreachable-rules-unverified":
        "Reguły zostają. Usunięcia, o którym nie da się wykazać, że zabrało dokładnie to, co miało, to narzędzie nie robi.",
    "css.position-kept":
        "To książka o stałym układzie, w której pozycjonowanie poza przepływem jest sposobem działania.",
    "xhtml.position-pinned-in-flow":
        "`margin-top: auto` w kolumnie flex ustawia blok przy stopce strony dokładnie tak, jak miało to robić `bottom: 0`, i zostawia go w przepływie, więc paginacja nie ma jak go zgubić. Wpisane do tego jednego dokumentu, który tego potrzebuje, nigdy do wspólnego arkusza — zrobienie z każdego `body` w książce kolumny flex zatrzymałoby scalanie sąsiadujących marginesów na każdej jej stronie. Tylko wtedy, gdy strona jest tym jednym blokiem: przy rodzeństwie nie ma wiernego tłumaczenia, więc reguła zostaje i jest raportowana.",
    "css.position-contained":
        "Element pozycjonowany absolutnie liczy się względem najbliższego pozycjonowanego przodka, a nie względem strony — podpis na obrazku, plakietka na okładce. Jedzie razem z pudełkiem, które go trzyma, więc paginacja nie ma jak go zgubić, a argument za usuwaniem pozycjonowania poza przepływem w ogóle go nie dotyczy. Zachowane również pod --strict, który wcześniej to kasował i zrzucał podpis pod obrazek na każdym czytniku.",
    "css.position-superseded":
        "Deklaracja nadal jest w arkuszu i już o niczym nie decyduje: dokument niesie odpowiednik, który ją przebija. Zostawiona, bo usuwanie ze wspólnego arkusza sięgnęłoby dokumentów, których nikt nie oglądał.",
    "css.position-kept-reflowable":
        "Nie każdy czytnik paginuje treść wyjętą z przepływu, ale to układ wybrany przez wydawcę i nie ma dla niego wiernego odpowiednika. Użyj --strict, żeby go usunąć.",
    "css.position-removed":
        "Te bloki płyną teraz razem ze stroną, zamiast być do niej przypięte. Nie dotyczy książek o stałym układzie, gdzie pozycjonowanie poza przepływem jest sposobem działania formatu. Na prawdziwym czytniku dedykacja przypięta w ten sposób wyszła jako pusta strona — blok wypadł z przepływu, a paginacja go ominęła.",
    "xhtml.orphaned-styling-restored":
        "Reguła jest w tej książce, w arkuszu, którego ten dokument nie podpina, i ma ją dokładnie jeden arkusz — więc nie ma między czym wybierać. Skopiowana do dokumentu dosłownie, zamiast podpinania całego arkusza, co wniosłoby na tę stronę wszystkie pozostałe decyzje z niego. Nie stosowane, gdy dwa arkusze się różnią, ani do reguł pobierających coś przez url().",
    "xhtml.empty-span-found":
        "Zmierzone na 12 475 spanach w 32 książkach: 97% coś robi, a te, które nie robią nic, to w całości konwersja z PDF-u — `.reset { margin: 0; padding: 0 }` na elemencie liniowym, gdzie to są wartości domyślne, i `.black { color: #010000 }`, czyli czerń przesunięta o jedną część na 255. Span, którego nie styluje nic, zostaje nietknięty: największą taką klasą w korpusie było 219 inicjałów z odpiętym arkuszem.",
    "xhtml.empty-span-unwrapped":
        "Rozwinięte, nie skasowane — tekst w środku zostaje dokładnie tam, gdzie był. Tylko spany bez id, lang, epub:type, role, dir, title i style, i tylko tam, gdzie reguła ich dosięga, a każda jej deklaracja jest wartością domyślną dla elementu liniowego.",
    "xhtml.epub2-only-markup":
        "Tryb kontenerowy zmienia tylko głowę dokumentu, więc to zostaje, a wynik jest niepoprawnym EPUB-em 3 nie z winy treści. Przebuduj w trybie „Zachowaj wygląd” — tam trafia to do CSS-u i renderuje się tak samo. Wypisane jest to, co znaleziono, a nie cała klasa: czego tu nie ma, i tak pokaże walidator.",
    "xhtml.title-filled":
        "EPUB 2 dopuszczał pusty <title>, EPUB 3 już nie, a ta przebudowa daje EPUB-a 3. Tekst nie jest wyświetlany w treści, więc nic na stronie się nie przesuwa. W trybie kontenerowym to druga i ostatnia zmiana wewnątrz dokumentu.",
    "xhtml.doctype-modernised":
        "Jedyna zmiana, jaką ten tryb wprowadza wewnątrz dokumentu. DOCTYPE nie mówi nic o sposobie wyświetlania, a stary czyni książkę niepoprawną. DOCTYPE deklarujący własne encje zostaje nietknięty, bo dokument z nich korzysta.",
    "xhtml.doctype-kept":
        "W tych dokumentach wynik pozostaje niepoprawnym EPUB-em 3 i jest to mniejsza szkoda: zastąpienie DOCTYPE osierociłoby encję, a książka z osieroconą encją w ogóle się nie otwiera.",
    "font.drm":
        "Usuń DRM narzędziem, do którego masz licencję, zanim uruchomisz EPUB F.O.R.G.E.",
    "font.deobfuscated":
        "Czcionki wyglądają identycznie, a kontener nie zależy już od identyfikatora.",
    "font.deobfuscation-failed":
        "Identyfikator źródła prawdopodobnie różni się od tego, którym je zaciemniono.",
    "metadata.title-missing":
        "Podaj --title, żeby ustawić prawdziwy.",
    "nav.fragment-cleared":
        "Pozycja wskazuje teraz na sam dokument, czyli tam, gdzie czytelnik i tak by trafił.",
    "nav.kept-in-spine":
        "Dokument nawigacyjny w kolejności czytania to strona, na którą czytelnik może przejść. Generowanie go od nowa usuwało tę stronę — czyli usuwało z książki coś, co czytelnik widział.",
    "nav.generated":
        "Źródło nie miało żadnego; jego spis treści pochodził z NCX.",
    "nav.contents-page-kept":
        "Ta strona jest w kolejności czytania, więc czytelnik na nią przechodzi. Zastąpienie jej wygenerowaną nawigacją usuwałoby stronę, którą złożył wydawca.",
    "structure.carried-xml-repointed":
        "Ten typ pliku nie jest modelowany przez potok, ale pliki, na które wskazuje, potok przesuwa. Zostawienie odwołań w spokoju dałoby książkę niepoprawną, a nie tylko uboższą.",
}

#: The fixed phrases this program passes *into* a finding as data.
#:
#: `reader.name-dropped` says "…could not be made into a container path: {reason}",
#: and the reason is one of a handful of sentences written in `ocf.py`. Left
#: alone it produced a Polish sentence with an English clause inside it — a
#: translation that looks finished and reads like neither language.
#:
#: This is a vocabulary, not prose: every entry is one of a closed set the
#: program itself chose. A value that is not in it — a file name, a number, a
#: media type — passes through untouched, which is why the mapping can be
#: applied to every value without asking which ones are words.
VOCABULARY_PL: dict[str, str] = {
    # ocf.py — why an archive entry name was rejected
    "the name climbs out of the container with '..'":
        "nazwa wychodzi poza kontener przez „..”",
    "the name is empty once normalised": "nazwa jest pusta po normalizacji",
    # ocf.py — what had to be changed in a name
    "null byte": "bajt zerowy",
    "backslash separators": "separatory w postaci lewych ukośników",
    "leading slash": "ukośnik na początku",
    "drive letter": "litera dysku",
    "percent-encoding": "kodowanie procentowe",
    "empty or current-directory segments": "puste segmenty albo segmenty bieżącego katalogu",
    "parent-directory segments": "segmenty katalogu nadrzędnego",
    # profile.py — the paragraph paradigm, which goes into a sentence
    "indented": "wcięciem",
    "spaced": "odstępem",
    "both": "wcięciem i odstępem naraz",
    # ocf.py — how two entry names collide
    "identical": "identyczność",
    "case": "wielkość liter",
    "normalisation": "normalizację Unicode",
}

VOCABULARIES: dict[str, dict[str, str]] = {"pl": VOCABULARY_PL}


def translate_values(values: dict | None, language: str) -> dict:
    """Replace values that are this program's own fixed phrases.

    Everything else — names, counts, media types — is data and passes through.
    """
    vocabulary = VOCABULARIES.get(language)
    if not values or not vocabulary:
        return values or {}
    return {
        key: vocabulary.get(value, value) if isinstance(value, str) else value
        for key, value in values.items()
    }


#: Language code → catalogue. `describe` falls back to English for a language
#: nobody has written, which is the right failure: a report in the wrong
#: language is still a report, and one that refuses to print is not.
CATALOGUES: dict[str, dict[str, str]] = {"en": CATALOGUE, "pl": CATALOGUE_PL}


def known(rule: str) -> bool:
    return rule in CATALOGUE


#: Placeholders in a catalogue entry: `{name}`, optionally with a plural spec.
_PLACEHOLDER = re.compile(r"\{([a-z_][a-z0-9_]*)(?::[^}]*)?\}")


class _Plural(string.Formatter):
    """`{count:plik|pliki|plików}` — the noun agreeing with the number.

    English gets away with "(s)" and Polish does not: it has three forms, and
    which one a number takes is not a matter of taste. "1 plików" is not a
    clumsy phrasing, it is a mistake, and a translation full of them is the
    kind that gets switched off.

    The rule is the standard one: one for exactly 1, the *few* form for numbers
    ending 2–4 except the teens, the *many* form for everything else.
    """

    def format_field(self, value, format_spec: str) -> str:
        if "|" not in format_spec:
            return super().format_field(value, format_spec)
        forms = format_spec.split("|")
        if len(forms) != 3:
            return super().format_field(value, "")
        one, few, many = forms
        try:
            number = abs(int(value))
        except (TypeError, ValueError):
            return many
        if number == 1:
            return one
        if number % 10 in (2, 3, 4) and number % 100 not in (12, 13, 14):
            return few
        return many


_FORMATTER = _Plural()


def fill(text: str, values: dict | None = None) -> str:
    """Fill one template, plural forms and all, without raising over a gap.

    Exposed because the window needs the same agreement the report has. The
    string tables held a second, plainer formatter, so a count in the interface
    could only say "4 plik" or hedge with a parenthesis — in the one place a
    Polish reader is looking at Polish.
    """
    if not values:
        return text
    try:
        return _FORMATTER.vformat(text, (), values)
    except (KeyError, IndexError, ValueError, AttributeError):
        return text


def placeholders(rule: str, language: str = "en") -> set[str]:
    """The names a catalogue entry expects to be given."""
    catalogue = CATALOGUES.get(language, CATALOGUE)
    return set(_PLACEHOLDER.findall(catalogue.get(rule) or CATALOGUE.get(rule, "")))


def describe(rule: str, language: str = "en", values: dict | None = None) -> str:
    """What the id means, in the language asked for.

    Falls back to English, then to the id itself. Returning the id rather than
    raising is deliberate: a report missing an explanation is still a report,
    and one that refuses to print because of a missing dictionary entry helps
    nobody.

    An entry with placeholders is a template, and *values* fills it. A template
    given nothing to fill it with comes back with its braces intact rather than
    raising — the caller can see that for itself, through `renders_fully`, and
    the alternative is a report that dies over a missing number.
    """
    catalogue = CATALOGUES.get(language, CATALOGUE)
    text = catalogue.get(rule) or CATALOGUE.get(rule, rule)
    if not values:
        return text
    try:
        return _FORMATTER.vformat(text, (), translate_values(values, language))
    except (KeyError, IndexError, ValueError, AttributeError):
        return text


def detail_placeholders(rule: str, language: str = "en") -> set[str]:
    """The names the paragraph beneath a finding expects to be given."""
    catalogue = DETAILS_PL if language == "pl" else DETAILS
    return set(_PLACEHOLDER.findall(catalogue.get(rule, "")))


def describe_detail_en(rule: str, values: dict | None = None) -> str | None:
    """The English paragraph for a rule, or `None` where there is none to give."""
    if rule not in DETAILS:
        return None
    return describe_from(DETAILS, rule, values)


def describe_detail(rule: str, language: str = "en", values: dict | None = None) -> str | None:
    """The paragraph beneath a finding, in the language asked for.

    Returns `None` when there is nothing to put there — English asks for the
    original, and a detail nobody has translated yet has to fall back to it
    rather than be dropped. Losing the paragraph would be a worse translation
    than an untranslated one: it is where the file names and the reasons live.
    """
    if language == "en" or rule not in DETAILS_PL:
        return None
    return describe_from(DETAILS_PL, rule, values, language)


def describe_from(
    catalogue: dict[str, str], rule: str, values: dict | None, language: str = "en"
) -> str:
    """Fill one catalogue entry, leaving its braces alone rather than raising."""
    text = catalogue.get(rule, rule)
    if not values:
        return text
    try:
        return _FORMATTER.vformat(text, (), translate_values(values, language))
    except (KeyError, IndexError, ValueError, AttributeError):
        return text


def renders_fully(rule: str, language: str, values: dict | None) -> bool:
    """Whether the description says everything the message says.

    This is what decides if the original English sentence still has to appear
    underneath a translated one. A finding's specifics — how many entries,
    which file, which media type — are exactly what it carries in `values`, so
    the description is complete when it states all of them. A finding carrying
    none has no specifics to lose, and its description stands alone.

    The other direction is not a failure: a template may name a value the
    finding did not supply, and then the placeholder would print at the reader.
    That is what makes it incomplete.
    """
    supplied = set(values or {})
    # A finding's specifics may be stated by either line. `a11y.placeholder-alt`
    # counts the images in its headline and lists them in its paragraph, and
    # judging the headline alone declared the finding incomplete and put the
    # English sentence back underneath a perfectly complete Polish one.
    expected = placeholders(rule, language)
    consumed = expected | detail_placeholders(rule, language)
    return supplied <= consumed and expected <= supplied


__all__ = [
    "CATALOGUE",
    "CATALOGUES",
    "CATALOGUE_PL",
    "DETAILS",
    "DETAILS_PL",
    "describe_detail_en",
    "VOCABULARY_PL",
    "translate_values",
    "describe",
    "describe_detail",
    "describe_from",
    "known",
    "placeholders",
    "detail_placeholders",
    "renders_fully",
]
