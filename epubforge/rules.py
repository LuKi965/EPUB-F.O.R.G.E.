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

#: id → one line saying what the finding means. English for now; this mapping is
#: the thing a translation replaces, and the reason it exists.
CATALOGUE: dict[str, str] = {
    # -- reader: what the source turned out to be ---------------------------
    "reader.remote-resource": "the manifest declares a resource hosted elsewhere",
    "reader.dangling-reference": "a fallback or media-overlay names an id the manifest does not define",
    "reader.name-rewritten": "an archive entry name was not a container path and was rewritten",
    "reader.name-dropped": "an archive entry name could not be made into a container path",
    "reader.duplicate-entry": "the archive holds the same entry name twice",
    "reader.colliding-names": "two entry names differ only by case or by Unicode normalisation",
    # -- structure: where files ended up ------------------------------------
    "structure.relaid-out": "files were regrouped into a typed layout with portable names",
    "structure.junk-removed": "packaging leftovers were removed",
    "structure.orphan-removed": "a file nothing in the book references was removed",
    "structure.carried-xml-repointed": "references inside a file carried as-is were repointed",
    # -- navigation ---------------------------------------------------------
    "nav.regenerated": "the navigation document was regenerated",
    "nav.generated": "the book had none and one was generated",
    "nav.contents-page-kept": "the publisher's contents page was kept and the navigation put beside it",
    "nav.repointed": "references to the replaced navigation document were repointed",
    "nav.kept-in-spine": "the navigation document stayed in the reading order, where the source had it",
    "nav.entry-dropped": "a table-of-contents entry pointed at something that is not there",
    "nav.fragment-cleared": "a navigation anchor does not exist and the entry now points at the document",
    "nav.toc-synthesised": "the book had no usable table of contents and one was built from the spine",
    "nav.cover-page-generated": "a cover page was generated so the artwork is the first spine item",
    "nav.ncx-written": "a legacy NCX was written alongside the navigation document",
    "nav.ncx-dropped": "the legacy NCX was not carried over",
    # -- content documents --------------------------------------------------
    "xhtml.untouched": "content documents were left as they were; only the container was rebuilt",
    "xhtml.doctype-modernised": "a legacy DOCTYPE was replaced with the EPUB 3 one",
    "xhtml.doctype-kept": "a legacy DOCTYPE stayed because an entity in the document cannot be resolved",
    "xhtml.entities-rewritten": "undefined named entities were rewritten as numeric references",
    "xhtml.property-withdrawn": "a manifest property the document does not bear out was withdrawn",
    # -- metadata -----------------------------------------------------------
    "metadata.override-applied": "the caller overrode a metadata field",
    "metadata.title-missing": "the source has no dc:title and a placeholder was inserted",
    "metadata.titles-collapsed": "several dc:title elements were collapsed to one main title",
    "metadata.language-invalid": "the language tag is not valid BCP 47 and was replaced",
    "metadata.language-missing": "the source has no dc:language and the default was used",
    "metadata.identifier-minted": "the source has no dc:identifier and a UUID was minted",
    "metadata.identifier-promoted": "no unique-identifier was declared and the first one was promoted",
    "metadata.date-normalised": "dc:date was normalised to ISO 8601",
    "metadata.date-unparseable": "dc:date could not be parsed and was dropped",
    "metadata.creator-missing": "the source names no dc:creator",

    # -- images -------------------------------------------------------------
    "image.pillow-unavailable": "Pillow is not installed, so images passed through unchecked",
    "image.unreadable": "an image could not be decoded and was kept as it was",
    "image.type-corrected": "a file is not the format its media type declared",
    "image.type-kept": "a non-core image type was kept because policy said so",
    "image.renamed": "a file was renamed to match the format it really is",
    "image.transcode-failed": "transcoding failed and the original was kept",
    "image.transcoded": "an image was transcoded to PNG for universal reader support",

    # -- fonts --------------------------------------------------------------
    "font.type-corrected": "a font's media type was corrected to what the file really is",
    "font.unrecognised": "a font has no recognisable signature",
    "font.drm": "the content is DRM-encrypted and the rebuild cannot proceed safely",
    "font.obfuscation-kept": "font obfuscation was left in place by policy",
    "font.obfuscation-unkeyed": "fonts are obfuscated but the package has no identifier to key on",
    "font.deobfuscation-failed": "deobfuscation did not yield a valid font, so the file was left alone",
    "font.deobfuscated": "embedded fonts were deobfuscated and the encryption file dropped",

    # -- compatibility profiles ---------------------------------------------
    "compat.unknown-profile": "a compatibility profile was named that does not exist",
    "compat.applied": "compatibility profiles were applied",
    "compat.ncx-required": "a selected profile needs the legacy NCX, which was switched off",
    "compat.stylesheet-added": "the HTML5 block stylesheet was linked into documents",
    "compat.page-break-mirrored": "fragmentation declarations were mirrored into page-break-*",
    "compat.specified-fonts-skipped": "the book embeds no fonts, so the Apple declaration was skipped",
    "compat.specified-fonts-added": "specified-fonts was declared for Apple Books",
    "compat.guide-skipped": "nothing in the book maps onto a legacy <guide>",
    "compat.guide-added": "the EPUB 2 <guide> element was added for readers that look for it",
    "compat.svg-cover": "the cover page wraps its image in SVG, which some converters mishandle",

    # -- accessibility ------------------------------------------------------
    "a11y.conformance-declared": "conformance was declared because the caller asserted it",
    "a11y.metadata-added": "EPUB Accessibility 1.1 discovery metadata was added",
    "a11y.missing-alt": "images have no usable alt text",
    "a11y.placeholder-alt": "alt text only repeats the file name",
    "a11y.heading-jump": "heading levels skip a rank",
    "a11y.table-without-headers": "a table has no header cells",

    # -- package ------------------------------------------------------------
    "package.upgraded": "the package was rebuilt from an older EPUB version to 3.3",
    "package.regenerated": "the source was already EPUB 3 and the package was regenerated anyway",
    "package.layout-kept": "the package document stayed where the source had it, because the files around it did not move",
    "package.version-unusable": "the package declared no usable version and was treated as EPUB 2",
    "package.unreadable-source": "the source file could not be read",
    "package.stage-failed": "a stage raised, so nothing was written",
    "package.source-protected": "writing over the source file was refused",
    "package.spine-item-vanished": "a spine item was gone by the time the package was written",
    # -- validation ---------------------------------------------------------
    "epubcheck.reported": "EPUBCheck reported problems with the output",
    "epubcheck.clean": "EPUBCheck accepted the output",
    "epubcheck.unavailable": "EPUBCheck is not installed, so the output was not validated",
    "epubcheck.failed": "EPUBCheck could not be run at all",
}


#: The same catalogue in Polish. Separate mapping rather than a tuple per entry
#: so that adding a language is adding a file-sized block and not editing
#: seventy-seven lines — and `test_rules.py` holds the two to the same key set,
#: because a half-translated catalogue silently falls back to English and looks
#: like a translation that is finished.
CATALOGUE_PL: dict[str, str] = {
    'reader.remote-resource': 'manifest deklaruje zasób trzymany gdzie indziej',
    'reader.dangling-reference': 'fallback albo media-overlay wskazuje na identyfikator, którego manifest nie definiuje',
    'reader.name-rewritten': 'nazwa wpisu w archiwum nie była ścieżką kontenera i została przepisana',
    'reader.name-dropped': 'nazwy wpisu w archiwum nie dało się zamienić na ścieżkę kontenera',
    'reader.duplicate-entry': 'archiwum zawiera tę samą nazwę wpisu dwa razy',
    'reader.colliding-names': 'dwie nazwy różnią się tylko wielkością liter albo normalizacją Unicode',
    'structure.relaid-out': 'pliki zostały przegrupowane w układ według typów, z przenośnymi nazwami',
    'structure.junk-removed': 'usunięto pozostałości po pakowaniu',
    'structure.orphan-removed': 'usunięto plik, do którego nic w książce się nie odwołuje',
    'structure.carried-xml-repointed': 'przepięto odwołania wewnątrz pliku przenoszonego bez zmian',
    'nav.regenerated': 'dokument nawigacyjny został wygenerowany od nowa',
    'nav.generated': 'książka nie miała dokumentu nawigacyjnego i został utworzony',
    'nav.contents-page-kept': 'zachowano stronę spisu treści wydawcy, a wygenerowaną nawigację umieszczono obok',
    'nav.repointed': 'odwołania do zastąpionego dokumentu nawigacyjnego zostały przepięte',
    'nav.kept-in-spine': 'dokument nawigacyjny został w kolejności czytania, tam gdzie miało go źródło',
    'nav.entry-dropped': 'pozycja spisu treści wskazywała na coś, czego nie ma',
    'nav.fragment-cleared': 'kotwica nawigacyjna nie istnieje, więc pozycja wskazuje teraz na sam dokument',
    'nav.toc-synthesised': 'książka nie miała używalnego spisu treści; zbudowano go z kolejności czytania',
    'nav.cover-page-generated': 'wygenerowano stronę okładki, żeby grafika była pierwsza w kolejności czytania',
    'nav.ncx-written': 'zapisano stary plik NCX obok dokumentu nawigacyjnego, dla starszych czytników',
    'nav.ncx-dropped': 'stary plik NCX nie został przeniesiony; EPUB 3 nawiguje dokumentem nawigacyjnym',
    'xhtml.untouched': 'dokumenty treści zostały bez zmian; przebudowano wyłącznie kontener',
    'xhtml.doctype-modernised': 'stary DOCTYPE zastąpiono tym z EPUB 3',
    'xhtml.doctype-kept': 'stary DOCTYPE został, bo encji w dokumencie nie da się rozwiązać',
    'xhtml.entities-rewritten': 'niezadeklarowane encje nazwane przepisano na referencje numeryczne',
    'xhtml.property-withdrawn': 'wycofano właściwość manifestu, której dokument nie potwierdza',
    'metadata.override-applied': 'wywołujący nadpisał pole metadanych',
    'metadata.title-missing': 'źródło nie ma dc:title; wstawiono zastępczy',
    'metadata.titles-collapsed': 'kilka elementów dc:title sprowadzono do jednego tytułu głównego',
    'metadata.language-invalid': 'znacznik języka nie jest poprawnym BCP 47 i został zastąpiony',
    'metadata.language-missing': 'źródło nie ma dc:language; użyto domyślnego',
    'metadata.identifier-minted': 'źródło nie ma dc:identifier; wygenerowano UUID',
    'metadata.identifier-promoted': 'nie zadeklarowano unique-identifier; awansowano pierwszy',
    'metadata.date-normalised': 'dc:date sprowadzono do ISO 8601',
    'metadata.date-unparseable': 'dc:date nie dało się odczytać i zostało pominięte',
    'metadata.creator-missing': 'źródło nie podaje dc:creator',
    'image.pillow-unavailable': 'Pillow nie jest zainstalowany, więc obrazy przeszły niesprawdzone',
    'image.unreadable': 'obrazu nie dało się odczytać i został bez zmian',
    'image.type-corrected': 'plik nie jest tym formatem, który deklarował jego typ MIME',
    'image.type-kept': 'typ obrazu spoza rdzenia EPUB 3 zachowany zgodnie z polityką',
    'image.renamed': 'plik przemianowano zgodnie z formatem, którym naprawdę jest',
    'image.transcode-failed': 'transkodowanie się nie powiodło; zachowano oryginał',
    'image.transcoded': 'obraz przekodowano na PNG dla zgodności z czytnikami',
    'font.type-corrected': 'typ MIME czcionki poprawiono na ten, którym plik naprawdę jest',
    'font.unrecognised': 'czcionka nie ma rozpoznawalnej sygnatury',
    'font.drm': 'treść jest zabezpieczona DRM; przebudowa nie może przebiec bezpiecznie',
    'font.obfuscation-kept': 'zaciemnienie czcionek zostawione zgodnie z polityką',
    'font.obfuscation-unkeyed': 'czcionki są zaciemnione, ale pakiet nie ma identyfikatora, na którym można je oprzeć',
    'font.deobfuscation-failed': 'odciemnianie nie dało poprawnej czcionki; plik został bez zmian',
    'font.deobfuscated': 'odciemniono osadzone czcionki i usunięto plik szyfrowania',
    'compat.unknown-profile': 'podano profil zgodności, który nie istnieje',
    'compat.applied': 'zastosowano profile zgodności',
    'compat.ncx-required': 'wybrany profil wymaga starego NCX, który był wyłączony',
    'compat.stylesheet-added': 'podlinkowano arkusz z blokowymi elementami HTML5',
    'compat.page-break-mirrored': 'deklaracje łamania odwzorowano na page-break-*',
    'compat.specified-fonts-skipped': 'książka nie osadza czcionek, więc pominięto deklarację dla Apple',
    'compat.specified-fonts-added': 'zadeklarowano specified-fonts dla Apple Books',
    'compat.guide-skipped': 'nic w książce nie odwzorowuje się na stary <guide>',
    'compat.guide-added': 'dodano element <guide> z EPUB 2 dla czytników, które go szukają',
    'compat.svg-cover': 'strona okładki opakowuje grafikę w SVG, co część konwerterów obsługuje źle',
    'a11y.conformance-declared': 'zadeklarowano zgodność, bo wywołujący to stwierdził',
    'a11y.metadata-added': 'dodano metadane dostępności EPUB Accessibility 1.1',
    'a11y.missing-alt': 'obrazy nie mają używalnego tekstu alternatywnego',
    'a11y.placeholder-alt': 'tekst alternatywny powtarza tylko nazwę pliku',
    'a11y.heading-jump': 'poziomy nagłówków przeskakują stopień',
    'a11y.table-without-headers': 'tabela nie ma komórek nagłówkowych',
    'package.upgraded': 'pakiet przebudowano ze starszej wersji EPUB na 3.3',
    'package.regenerated': 'źródło było już EPUB 3, a pakiet i tak wygenerowano od nowa',
    'package.layout-kept': 'dokument pakietu został tam, gdzie był w źródle, bo pliki wokół niego się nie przesunęły',
    'package.version-unusable': 'pakiet nie deklarował używalnej wersji; potraktowano go jak EPUB 2',
    'package.unreadable-source': 'pliku źródłowego nie dało się odczytać',
    'package.stage-failed': 'etap zgłosił wyjątek, więc nic nie zostało zapisane',
    'package.source-protected': 'odmówiono nadpisania pliku źródłowego',
    'package.spine-item-vanished': 'pozycja kolejności czytania zniknęła, zanim pakiet został zapisany',
    'epubcheck.reported': 'EPUBCheck zgłosił problemy z wynikiem',
    'epubcheck.clean': 'EPUBCheck przyjął wynik',
    'epubcheck.unavailable': 'EPUBCheck nie jest zainstalowany, więc wynik nie został zweryfikowany',
    'epubcheck.failed': 'EPUBCheck w ogóle nie dał się uruchomić',
}

#: Language code → catalogue. `describe` falls back to English for a language
#: nobody has written, which is the right failure: a report in the wrong
#: language is still a report, and one that refuses to print is not.
CATALOGUES: dict[str, dict[str, str]] = {"en": CATALOGUE, "pl": CATALOGUE_PL}


def known(rule: str) -> bool:
    return rule in CATALOGUE


def describe(rule: str, language: str = "en") -> str:
    """What the id means, in the language asked for.

    Falls back to English, then to the id itself. Returning the id rather than
    raising is deliberate: a report missing an explanation is still a report,
    and one that refuses to print because of a missing dictionary entry helps
    nobody.
    """
    catalogue = CATALOGUES.get(language, CATALOGUE)
    return catalogue.get(rule) or CATALOGUE.get(rule, rule)


__all__ = ["CATALOGUE", "CATALOGUES", "CATALOGUE_PL", "describe", "known"]
