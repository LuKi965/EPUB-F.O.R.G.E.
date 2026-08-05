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
    # -- content documents --------------------------------------------------
    "xhtml.untouched": "content documents were left as they were; only the container was rebuilt",
    "xhtml.doctype-modernised": "a legacy DOCTYPE was replaced with the EPUB 3 one in {count} document(s)",
    "xhtml.doctype-kept": "{count} document(s) keep a legacy DOCTYPE because an entity cannot be resolved: {documents}",
    "xhtml.entities-rewritten": "undefined named entities were rewritten as numeric references",
    "xhtml.property-withdrawn": "manifest properties the document does not bear out were withdrawn: {properties}",
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
    'xhtml.untouched': 'dokumenty treści zostały bez zmian; przebudowano wyłącznie kontener',
    'xhtml.doctype-modernised': 'stary DOCTYPE zastąpiono tym z EPUB 3 w {count} {count:dokumencie|dokumentach|dokumentach}',
    'xhtml.doctype-kept': '{count} {count:dokument zachowuje|dokumenty zachowują|dokumentów zachowuje} stary DOCTYPE, bo encji nie da się rozwiązać: {documents}',
    'xhtml.entities-rewritten': 'niezadeklarowane encje nazwane przepisano na referencje numeryczne',
    'xhtml.property-withdrawn': 'wycofano właściwości manifestu, których dokument nie potwierdza: {properties}',
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
        return _FORMATTER.vformat(text, (), values)
    except (KeyError, IndexError, ValueError, AttributeError):
        return text


def renders_fully(rule: str, language: str, values: dict | None) -> bool:
    """Whether the description says everything the message says.

    This is what decides if the original English sentence still has to appear
    underneath a translated one. It is true only when the entry is a template
    and every placeholder in it has a value: an entry with no placeholders is
    generic by construction, and the specifics — how many entries, which file —
    live in the message and would be lost.
    """
    expected = placeholders(rule, language)
    return bool(expected) and expected <= set(values or {})


__all__ = [
    "CATALOGUE",
    "CATALOGUES",
    "CATALOGUE_PL",
    "describe",
    "known",
    "placeholders",
    "renders_fully",
]
