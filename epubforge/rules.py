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
    "xhtml.doctype-kept": "{count} document(s) keep a legacy DOCTYPE because an entity cannot be resolved: {documents}",
    "xhtml.entities-rewritten": "undefined named entities were rewritten as numeric references",
    "xhtml.property-withdrawn": "manifest properties the document does not bear out were withdrawn: {properties}",
    # -- stylesheets --------------------------------------------------------
    "css.url-unresolved": "{count} url() reference(s) could not be resolved and were left unchanged",
    "css.vendor-at-rule-kept": "{count} vendor-specific at-rule(s) targeting particular readers were kept",
    "css.kindle-media-removed": "Kindle-specific @media blocks were removed",
    "css.invalid-value-corrected": "{count} declaration(s) using the invalid value 'regular' were corrected",
    "css.position-kept": "{count} absolute or fixed position rule(s) were kept",
    "css.position-kept-reflowable": "{count} absolute or fixed position rule(s) were kept in a reflowable book",
    "css.position-removed": "{count} absolute or fixed position rule(s) were removed from a reflowable book",
    "css.reader-property-kept": "{count} reader-specific CSS propert(ies) inherited from the source were kept",
    "css.reader-property-removed": "{count} reader-specific CSS propert(ies) were removed",
    "css.font-stack-generic-missing": "{count} font stack(s) end without a generic family",
    "css.unparseable": "a stylesheet could not be parsed for validation: {error}",
    "css.no-usable-rules": "a stylesheet contains no usable rules",
    "xhtml.unparseable": "a content document could not be parsed at all: {error}",
    "xhtml.recovered-with-html-parser": "a document was not well-formed XML and was recovered with an HTML parser",
    "xhtml.dtd-entities-resolved": "{count} entity/entities declared in the document's own DTD were resolved",
    "xhtml.dtd-entities-refused": "{count} entity/entities were left as references rather than resolved",
    "xhtml.watermark-consolidated": "{count} watermark marker(s) across {documents} document(s) became one rule",
    "xhtml.watermark-kept": "{count} visible watermark notice(s) were left exactly as the publisher wrote them",
    "xhtml.watermark-kept-personal-data": "{count} visible watermark notice(s) carrying personal data were left exactly as the publisher wrote them",
    "xhtml.ids-renamed": "{count} id attribute(s) were not valid XML names and were renamed",
    "xhtml.head-added": "a missing <head> element was added",
    "xhtml.body-added": "a missing <body> element was added",
    "xhtml.dead-reference-kept": "{count} reference(s) point at files not in the book and were left unchanged",
    "xhtml.dead-reference-neutralised": "{count} reference(s) to files absent from the book were neutralised",
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
    "compat.applied": "compatibility profiles were applied",
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
    'xhtml.doctype-kept': '{count} {count:dokument zachowuje|dokumenty zachowują|dokumentów zachowuje} stary DOCTYPE, bo encji nie da się rozwiązać: {documents}',
    'xhtml.entities-rewritten': 'niezadeklarowane encje nazwane przepisano na referencje numeryczne',
    'xhtml.property-withdrawn': 'wycofano właściwości manifestu, których dokument nie potwierdza: {properties}',
    # -- stylesheets --------------------------------------------------------
    'css.url-unresolved': '{count} {count:odwołania url() nie dało się rozwiązać|odwołań url() nie dało się rozwiązać|odwołań url() nie dało się rozwiązać} i zostały bez zmian',
    'css.vendor-at-rule-kept': 'zachowano {count} {count:regułę @|reguły @|reguł @} charakterystyczną dla konkretnych czytników',
    'css.kindle-media-removed': 'usunięto bloki @media przeznaczone dla Kindle',
    'css.invalid-value-corrected': 'poprawiono {count} {count:deklarację|deklaracje|deklaracji} z niepoprawną wartością „regular”',
    'css.position-kept': 'zachowano {count} {count:regułę pozycjonowania|reguły pozycjonowania|reguł pozycjonowania} absolutnego lub stałego',
    'css.position-kept-reflowable': 'zachowano {count} {count:regułę pozycjonowania|reguły pozycjonowania|reguł pozycjonowania} absolutnego lub stałego w książce przepływalnej',
    'css.position-removed': 'usunięto {count} {count:regułę pozycjonowania|reguły pozycjonowania|reguł pozycjonowania} absolutnego lub stałego z książki przepływalnej',
    'css.reader-property-kept': 'zachowano {count} {count:właściwość CSS|właściwości CSS|właściwości CSS} charakterystyczną dla czytników, odziedziczoną ze źródła',
    'css.reader-property-removed': 'usunięto {count} {count:właściwość CSS|właściwości CSS|właściwości CSS} charakterystyczną dla czytników',
    'css.font-stack-generic-missing': '{count} {count:lista krojów kończy się|listy krojów kończą się|list krojów kończy się} bez rodziny generycznej',
    'css.unparseable': 'arkusza stylów nie dało się sparsować do sprawdzenia: {error}',
    'css.no-usable-rules': 'arkusz stylów nie zawiera żadnych używalnych reguł',
    'xhtml.unparseable': 'dokumentu treści w ogóle nie dało się sparsować: {error}',
    'xhtml.recovered-with-html-parser': 'dokument nie był poprawnym XML-em i został odzyskany parserem HTML',
    'xhtml.dtd-entities-resolved': 'rozwiązano {count} {count:encję|encje|encji} zadeklarowaną w DTD samego dokumentu',
    'xhtml.dtd-entities-refused': '{count} {count:encję pozostawiono|encje pozostawiono|encji pozostawiono} jako odwołania zamiast je rozwiązać',
    'xhtml.watermark-consolidated': '{count} {count:znacznik znaku wodnego|znaczniki znaku wodnego|znaczników znaku wodnego} w {documents} {documents:dokumencie|dokumentach|dokumentach} sprowadzono do jednej reguły',
    'xhtml.watermark-kept': '{count} {count:widoczną adnotację|widoczne adnotacje|widocznych adnotacji} znaku wodnego zostawiono dokładnie tak, jak napisał je wydawca',
    'xhtml.watermark-kept-personal-data': '{count} {count:widoczną adnotację|widoczne adnotacje|widocznych adnotacji} znaku wodnego z danymi osobowymi zostawiono dokładnie tak, jak napisał je wydawca',
    'xhtml.ids-renamed': '{count} {count:atrybut id nie był poprawną nazwą XML|atrybuty id nie były poprawnymi nazwami XML|atrybutów id nie było poprawnymi nazwami XML} i zostały przemianowane',
    'xhtml.head-added': 'dodano brakujący element <head>',
    'xhtml.body-added': 'dodano brakujący element <body>',
    'xhtml.dead-reference-kept': '{count} {count:odwołanie wskazuje|odwołania wskazują|odwołań wskazuje} na pliki, których w książce nie ma; zostawiono je bez zmian',
    'xhtml.dead-reference-neutralised': 'unieszkodliwiono {count} {count:odwołanie|odwołania|odwołań} do plików nieobecnych w książce',
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
    'font.type-corrected': 'typ MIME czcionki poprawiono na {actual}; zadeklarowany był {declared}',
    'font.unrecognised': 'czcionka nie ma rozpoznawalnej sygnatury',
    'font.drm': 'treść jest zabezpieczona DRM; przebudowa nie może przebiec bezpiecznie',
    'font.obfuscation-kept': 'zaciemnienie czcionek zostawione zgodnie z polityką',
    'font.obfuscation-unkeyed': 'czcionki są zaciemnione, ale pakiet nie ma identyfikatora, na którym można je oprzeć',
    'font.deobfuscation-failed': 'odciemnianie nie dało poprawnej czcionki; plik został bez zmian',
    'font.deobfuscated': 'odciemniono {count} {count:osadzoną czcionkę|osadzone czcionki|osadzonych czcionek} i usunięto plik szyfrowania',
    'compat.unknown-profile': 'profil zgodności {profile} nie istnieje i został pominięty',
    'compat.applied': 'zastosowano profile zgodności',
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
    'package.source-protected': 'odmówiono nadpisania pliku źródłowego',
    'package.spine-item-vanished': 'pozycja kolejności czytania zniknęła, zanim pakiet został zapisany',
    'epubcheck.reported': 'EPUBCheck zgłosił {fatal} błędów krytycznych i {errors} błędów',
    'epubcheck.clean': 'EPUBCheck przyjął wynik, z {warnings} ostrzeżeniem/ami',
    'epubcheck.unavailable': 'EPUBCheck nie jest zainstalowany, więc wynik nie został zweryfikowany',
    'epubcheck.failed': 'EPUBCheck w ogóle nie dał się uruchomić: {error}',
    # -- the window ---------------------------------------------------------
    'gui.unexpected-failure': 'przebudowa zawiodła w sposób, którego nic nie przewidziało: {error}',
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
    "xhtml.dead-reference-kept":
        "To są defekty źródła i pozostają błędami zgodności. Użyj --strict, żeby je unieszkodliwić.",
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
    "css.position-kept":
        "To książka o stałym układzie, w której pozycjonowanie poza przepływem jest sposobem działania.",
    "css.position-kept-reflowable":
        "Treść poza przepływem nie paginuje się na każdym czytniku, ale to układ wybrany przez wydawcę. Użyj --strict, żeby go usunąć.",
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
    expected = placeholders(rule, language)
    return supplied <= expected and expected <= supplied


__all__ = [
    "CATALOGUE",
    "CATALOGUES",
    "CATALOGUE_PL",
    "DETAILS_PL",
    "VOCABULARY_PL",
    "translate_values",
    "describe",
    "describe_detail",
    "describe_from",
    "known",
    "placeholders",
    "renders_fully",
]
