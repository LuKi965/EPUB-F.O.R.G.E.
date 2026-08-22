"""What the program says when it asks somebody a question, in both languages.

EF-032. Every question this program puts to a person was written in Polish, as a
literal, in the module that happened to raise it — `hyphens.py` and `pipeline.py`
between them. The report has had a catalogue with both languages since 0.2.4 and
renders from `rule` + `values` at display time; the questions, which are the one
place the program actually *talks* to somebody, had neither. An English user got
the interface in English and then, at the moment of being asked to decide
something irreversible about their book, a paragraph of Polish.

The mechanism is deliberately the smaller of the two available. The report keeps
`rule` and `values` and renders per call, which is right for a report: it is
written once and read in whatever language somebody asks for. A question is
asked, answered and gone, so it is rendered once here, at the moment of asking,
in the language the interface is running in. `set_language` is how that language
gets in — the window calls it at start-up, and the default matches the window's
own default so that nothing changes for the owner.

Keys are dotted and name the situation, not the wording, so that rephrasing a
question is editing this file and touching nothing else.
"""

from __future__ import annotations

import os

LANGUAGES = ("pl", "en")

#: Where the command line already says which language the interface speaks —
#: `cli.py` reads it for the closing remark. Read here too so that a batch run
#: with nobody at the window still asks in the language that run was configured
#: for, rather than needing a second setting nobody would think to change.
ENV_LANGUAGE = "EPUBFORGE_LANG"


def _initial() -> str:
    """Polish unless the environment says otherwise — the window's default, so
    a build that never calls `set_language` behaves exactly as it did before
    this module existed."""
    named = os.environ.get(ENV_LANGUAGE, "")[:2].lower()
    return named if named in LANGUAGES else "pl"


#: Language of the next question asked.
_ACTIVE = _initial()


def set_language(code: str) -> None:
    """Ask the next question in *code*. Unknown codes leave the setting alone."""
    global _ACTIVE
    if code in LANGUAGES:
        _ACTIVE = code


def language() -> str:
    return _ACTIVE


TEXTS_PL: dict[str, str] = {
    # --- hyphens: a word cut in two by markup somebody chose ----------------
    "hyphen.cut-by-markup.summary": "„{word}” — słowo przecięte znacznikiem <{carrier}>",
    "hyphen.cut-by-markup.detail": (
        "Nie proponuję złączenia: obie połowy siedzą w różnych elementach, "
        "a <{carrier}> niesie własne formatowanie albo znaczenie. Złączenie "
        "przeniosłoby tekst poza element, który ktoś wybrał — to zmiana "
        "struktury, a nie pisowni."
    ),
    "hyphen.cut-by-markup.keep": "Zostaw jak jest",
    "hyphen.cut-by-markup.keep.why": (
        "Słowo zostaje przecięte dokładnie tak, jak w pliku źródłowym"
    ),
    # --- hyphens: one word --------------------------------------------------
    "hyphen.one.summary": "„{word}” — łącznik w środku słowa",
    "hyphen.one.keep": "Zostaw jak jest",
    "hyphen.one.keep.why": (
        "Słowo zostaje z łącznikiem, dokładnie tak jak w pliku źródłowym"
    ),
    "hyphen.one.join": "Złącz w „{joined}”",
    "hyphen.one.join.why": "W tekście będzie „{joined}”",
    "hyphen.one.write": "Wpisz poprawną formę",
    "hyphen.one.write.why": "W tekście będzie to, co wpiszesz",
    # --- hyphens: a whole confidence class at once --------------------------
    "hyphen.group.summary": (
        "{count} słów z łącznikiem — {label}, bez dowodu w tej książce"
    ),
    "hyphen.group.detail": (
        "Ta książka nigdzie nie pisze tych słów bez łącznika, więc nie ma dowodu, "
        "że łącznik jest usterką konwersji, a nie pisownią autora. Wiele z nich "
        "to prawdziwe wyrazy złożone.\n\n{shown}{more}"
    ),
    "hyphen.group.more": " … i jeszcze {count}",
    "hyphen.group.label.likely": "prawdopodobne",
    "hyphen.group.label.uncertain": "niepewne",
    "hyphen.group.keep": "Zostaw wszystkie",
    "hyphen.group.keep.why": "Żadne z tych słów nie zostanie zmienione — tak jak dotąd",
    "hyphen.group.join": "Złącz wszystkie {count}",
    "hyphen.group.join.why": (
        "Każde z tych słów straci łącznik; to zmiana treści i nie da się jej "
        "cofnąć z samego wyniku"
    ),
    # --- the appearance check could not run at all --------------------------
    "render.unverified.summary": (
        "Sprawdzenie wyglądu jest obowiązkowe i nie dało się go wykonać"
    ),
    "render.unverified.detail": (
        "Program rysuje strony przed i po przebudowie i porównuje je, żeby wykryć "
        "stronę, która straciła treść. Na tej maszynie nie ma przeglądarki, którą "
        "mógłby do tego użyć, więc wynik nie został sprawdzony.\n\n"
        "Zainstaluj Chromium albo Chrome'a, albo wskaż własną przeglądarkę zmienną "
        "{variable}, a sprawdzenie wykona się samo. Możesz też świadomie z niego "
        "zrezygnować — teraz, tą odpowiedzią, albo z góry dla całej partii "
        "ustawieniem „przyjmij niesprawdzone”."
    ),
    "render.unverified.keep": "Nie zapisuj",
    "render.unverified.keep.why": (
        "Plik nie powstanie, a ten, który leży pod tą nazwą, zostanie nietknięty. "
        "Nic nie tracisz i możesz wrócić po zainstalowaniu przeglądarki."
    ),
    "render.unverified.publish": "Zapisz mimo to",
    "render.unverified.publish.why": (
        "Plik powstanie, a w raporcie stanie, że wygląd nie został sprawdzony. "
        "Świadoma rezygnacja z weryfikacji."
    ),
    # --- a metadata field that came out of a damaged package ----------------
    "metadata.reconstructed.summary": "„{current}” — {label} odczytany z uszkodzonego pakietu",
    "metadata.reconstructed.detail": (
        "Pakiet tej książki dał się sparsować dopiero po odzysku, więc to pole "
        "jest odczytem parsera, a nie tym, co napisał wydawca. Wyszło: „{current}”."
    ),
    "metadata.reconstructed.keep": "Zostaw „{current}”",
    "metadata.reconstructed.keep.why": "W książce zostanie to, co odczytał parser",
    "metadata.reconstructed.write": "Wpisz poprawną wartość",
    "metadata.reconstructed.write.why": "W książce będzie to, co wpiszesz",
    # --- punctuation a conversion turned into unprintable codes -------------
    # --- bare footnote markers whose notes exist ----------------------------
    "footnote.summary": "{count} znaczników przypisów [N] bez odnośnika, a sekcja przypisów istnieje",
    "footnote.detail": (
        "W treści stoją gołe znaczniki w rodzaju [1], a w sekcji przypisów "
        "czekają noty o tych numerach — konwerter porzucił linkowanie w pół "
        "drogi. Pierwsze pary:\n\n{shown}\n\nPołączenie nie zmienia ani "
        "jednego znaku tekstu: znacznik zostaje, dochodzi tylko odnośnik."
    ),
    "footnote.keep": "Zostaw jak jest",
    "footnote.keep.why": "Nic się nie zmienia; znaczniki dalej nie prowadzą nigdzie",
    "footnote.link": "Połącz znaczniki z przypisami",
    "footnote.link.why": (
        "{count} znaczników stanie się odnośnikami do swoich not; tekst "
        "pozostaje co do znaku ten sam"
    ),
    # --- contents entries all pointing at one untangled id ------------------
    "toc.duplicate.summary": (
        "{count} pozycji spisu treści prowadzi w to samo miejsce, a rozplątane "
        "cele czekają"
    ),
    "toc.duplicate.detail": (
        "W źródle jeden identyfikator powtarzał się wielokrotnie i każda z tych "
        "pozycji spisu skakała do pierwszego wystąpienia. Przebudowa rozplątała "
        "identyfikatory i liczby się zgadzają: pozycji jest tyle, ile wystąpień. "
        "Przypisanie po kolejności w dokumencie ({where}):\n\n{shown}\n\n"
        "To przypisanie jest prawdopodobne, nie pewne — dlatego jest pytaniem."
    ),
    "toc.duplicate.keep": "Zostaw jak jest",
    "toc.duplicate.keep.why": (
        "Wszystkie pozycje dalej skaczą do pierwszego wystąpienia — tak, jak "
        "działało źródło"
    ),
    "toc.duplicate.repoint": "Przepnij pozycje po kolejności",
    "toc.duplicate.repoint.why": (
        "{count} pozycji spisu poprowadzi kolejno do swoich rozplątanych celów; "
        "jeśli kolejność w źródle znaczyła co innego, czytelnik trafi w złe "
        "miejsce"
    ),
    # --- a declaration written `property="value"` in a hand-touched rule ----
    "style.dupsel.summary": (
        "Dwie reguły `{selector}` nie dają się scalić bez zmiany zwycięzcy"
    ),
    "style.dupsel.detail": (
        "W {where} selektor `{selector}` występuje dwukrotnie, a między "
        "kopiami stoi `{blocker}`, walcząca o to samo ({contest}). "
        "Scalenie przeniesie deklaracje wcześniejszej kopii za `{blocker}` "
        "— tam, gdzie obie reguły trafiają ten sam element, wygrywać "
        "zacznie wartość przeniesiona."
    ),
    "style.dupsel.keep": "Zostaw jak jest",
    "style.dupsel.keep.why": (
        "Nic się nie zmienia; kaskada wydawcy zostaje kaskadą wydawcy"
    ),
    "style.dupsel.merge": "Scal mimo sporu",
    "style.dupsel.merge.why": (
        "Kopie stają się jedną regułą; na wspólnych elementach przeniesiona "
        "wartość zaczyna wygrywać z `{blocker}`"
    ),
    "style.tie.summary": (
        "Reguła `{selector}` stoi za bardziej specyficzną, a remis na "
        "drodze nie pozwala jej przestawić"
    ),
    "style.tie.detail": (
        "W {where} lint chce, by `{selector}` stała przed `{target}`, ale "
        "po drodze remisuje z `{blocker}` o to samo ({contest}) na "
        "elementach, które ta książka naprawdę ma. Przestawienie sprawi, "
        "że na wspólnych elementach `{blocker}` zacznie wygrywać."
    ),
    "style.tie.keep": "Zostaw jak jest",
    "style.tie.keep.why": (
        "Nic się nie zmienia; kolejność wydawcy dalej rozstrzyga remis"
    ),
    "style.tie.move": "Przestaw mimo remisu",
    "style.tie.move.why": (
        "Reguła idzie na miejsce wskazane przez lint, a `{blocker}` "
        "zaczyna wygrywać na wspólnych elementach; ruch wejdzie tylko, "
        "jeśli nie pogorszy sumy lintu"
    ),
    "style.important.summary": (
        "Właściwość `{prop}` powtórzona w jednym bloku z mieszanym "
        "`!important` i różnymi wartościami — czytniki liczą ją różnie"
    ),
    "style.important.detail": (
        "W {where} jeden blok deklaruje `{prop}` kilkukrotnie: {values}. "
        "Współczesny czytnik bierze wartość z `!important` ({winner}); "
        "czytnik nieznający ważności — ostatnią zwykłą. Którą wersję "
        "książka ma znaczyć, wie tylko człowiek."
    ),
    "style.important.keep": "Zostaw jak jest",
    "style.important.keep.why": (
        "Nic się nie zmienia; rozbieżność między czytnikami zostaje taka, "
        "jaka była"
    ),
    "style.important.resolve": "Zostaw zwycięzcę współczesnej kaskady",
    "style.important.resolve.why": (
        "Zostaje tylko `{winner}`; każdy czytnik, stary i nowy, policzy "
        "odtąd to samo"
    ),
    "style.generic.summary": (
        "{count} deklaracji fontów wskazuje kroje, których książka nie "
        "dołącza, bez rodziny zapasowej ({generic}?)"
    ),
    "style.generic.detail": (
        "W {where} deklaracje font-family kończą się na nazwanych krojach "
        "({examples}), których nie ma w paczce książki. Czytnik bez takiego "
        "kroju użyje swojego domyślnego — jakiegokolwiek. Dopisanie rodziny "
        "zapasowej `{generic}` mówi mu: „jak nie masz tego kroju, weź swój "
        "{generic}”. Zmiana widoczna wyłącznie na czytnikach, którym kroju "
        "brakuje — i tam przybliża wygląd do zamysłu wydawcy."
    ),
    "style.generic.keep": "Zostaw jak jest",
    "style.generic.keep.why": (
        "Nic się nie zmienia; czytnik bez nazwanego kroju dalej bierze swój "
        "domyślny"
    ),
    "style.generic.append": "Dopisz `{generic}` jako zapasowy",
    "style.generic.append.why": (
        "Do każdej z tych deklaracji dołącza `, {generic}` na końcu; kroje "
        "nazwane zostają na swoich miejscach i dalej mają pierwszeństwo"
    ),
    "style.equals.summary": (
        "{count} deklaracji CSS zapisanych jak atrybut HTML (`=` zamiast `:`) — "
        "żaden czytnik ich nie stosuje"
    ),
    "style.equals.detail": (
        "W arkuszu {where} stoją deklaracje w rodzaju:\n\n{shown}\n\n"
        "Składnia CSS wymaga dwukropka, więc parser każdego czytnika odrzuca "
        "taką linię w całości — to formatowanie nigdy nie działało. Reguła "
        "nie nosi podpisu żadnego konwertera, więc mógł to być zamysł "
        "wydawcy z literówką. Włączenie sprawi, że formatowanie, którego "
        "nikt dotąd nie widział, zacznie obowiązywać."
    ),
    "style.equals.keep": "Zostaw jak jest",
    "style.equals.keep.why": (
        "Nic się nie zmienia; linia dalej jest ignorowana przez czytniki, "
        "a książka wygląda tak, jak wyglądała"
    ),
    "style.equals.drop": "Usuń martwą linię",
    "style.equals.drop.why": (
        "Linia znika z arkusza; wygląd książki się nie zmienia, bo nikt jej "
        "nigdy nie stosował"
    ),
    "style.equals.enable": "Popraw `=` na `:` i włącz",
    "style.equals.enable.why": (
        "{count} deklaracji zacznie działać — książka może zmienić wygląd w "
        "miejscach, których nikt wcześniej nie widział z tym formatowaniem"
    ),
    "encoding.mojibake.summary": (
        "{count} znaków przestankowych zamienionych przez konwersję w kody bez kształtu"
    ),
    "encoding.mojibake.detail": (
        "Konwerter, którym zrobiono ten plik, odczytał tekst z Windowsa złym "
        "kodowaniem. Cudzysłowy i myślniki wylądowały na pozycjach, które w "
        "Unikodzie są kodami sterującymi — żadna czcionka ich nie rysuje, więc w "
        "czytniku są dziś pustymi miejscami.\n\n{shown}\n\n"
        "Odwzorowanie jest jednoznaczne i idzie w jedną stronę: każda z tych "
        "pozycji ma dokładnie jeden odpowiednik, nie ma tu zgadywania."
    ),
    "encoding.mojibake.line": "{count} × {character}",
    "encoding.mojibake.keep": "Zostaw jak jest",
    "encoding.mojibake.keep.why": (
        "Znaki zostaną w książce takie, jakie są — niewidoczne. Tekst nie zmieni "
        "się o żaden znak"
    ),
    "encoding.mojibake.repair": "Przywróć znaki przestankowe",
    "encoding.mojibake.repair.why": (
        "{count} kodów bez kształtu zamieni się w cudzysłowy, myślniki i "
        "wielokropki. To zmiana treści; z samego wyniku nie da się jej cofnąć"
    ),
}

TEXTS_EN: dict[str, str] = {
    "hyphen.cut-by-markup.summary": "“{word}” — a word cut in two by a <{carrier}>",
    "hyphen.cut-by-markup.detail": (
        "No join is offered: the two halves sit in different elements, and "
        "<{carrier}> carries formatting or meaning of its own. Joining them would "
        "move text out of an element somebody chose — a change to the structure "
        "rather than to the spelling."
    ),
    "hyphen.cut-by-markup.keep": "Leave it as it is",
    "hyphen.cut-by-markup.keep.why": (
        "The word stays cut exactly as it is in the source file"
    ),
    "hyphen.one.summary": "“{word}” — a hyphen inside a word",
    "hyphen.one.keep": "Leave it as it is",
    "hyphen.one.keep.why": (
        "The word keeps its hyphen, exactly as it is in the source file"
    ),
    "hyphen.one.join": "Join into “{joined}”",
    "hyphen.one.join.why": "The text will read “{joined}”",
    "hyphen.one.write": "Type the correct form",
    "hyphen.one.write.why": "The text will read whatever you type",
    "hyphen.group.summary": (
        "{count} hyphenated words — {label}, with no evidence in this book"
    ),
    "hyphen.group.detail": (
        "This book never spells these words without a hyphen, so there is no "
        "evidence that the hyphen is a conversion fault rather than the author's "
        "spelling. Many of them are real compounds.\n\n{shown}{more}"
    ),
    "hyphen.group.more": " … and {count} more",
    "hyphen.group.label.likely": "likely",
    "hyphen.group.label.uncertain": "uncertain",
    "hyphen.group.keep": "Leave all of them",
    "hyphen.group.keep.why": "None of these words will be changed — as until now",
    "hyphen.group.join": "Join all {count}",
    "hyphen.group.join.why": (
        "Every one of these words loses its hyphen; this changes the text and "
        "cannot be undone from the output alone"
    ),
    "render.unverified.summary": (
        "The appearance check is mandatory and could not be carried out"
    ),
    "render.unverified.detail": (
        "The program draws the pages before and after the rebuild and compares "
        "them, to catch a page that has lost content. This machine has no browser "
        "it can use for that, so the result has not been checked.\n\n"
        "Install Chromium or Chrome, or point at a browser of your own with "
        "{variable}, and the check runs by itself. You may also decline it "
        "knowingly — now, with this answer, or in advance for a whole batch with "
        "the “accept unverified” setting."
    ),
    "render.unverified.keep": "Do not write it",
    "render.unverified.keep.why": (
        "No file is produced, and whatever already sits under that name is left "
        "untouched. You lose nothing and can come back once a browser is installed."
    ),
    "render.unverified.publish": "Write it anyway",
    "render.unverified.publish.why": (
        "The file is produced, and the report will say the appearance was not "
        "checked. A knowing decision to go without the verification."
    ),
    "metadata.reconstructed.summary": "“{current}” — {label} read out of a damaged package",
    "metadata.reconstructed.detail": (
        "This book's package only parsed after recovery, so this field is the "
        "parser's reading rather than what the publisher wrote. It came out as: "
        "“{current}”."
    ),
    "metadata.reconstructed.keep": "Keep “{current}”",
    "metadata.reconstructed.keep.why": "The book keeps what the parser read",
    "metadata.reconstructed.write": "Type the correct value",
    "metadata.reconstructed.write.why": "The book will carry whatever you type",
    # --- bare footnote markers whose notes exist ----------------------------
    "footnote.summary": "{count} footnote marker(s) [N] with no link, and a notes section exists",
    "footnote.detail": (
        "The text carries bare markers like [1], and notes with those numbers "
        "wait in the notes section — a converter abandoned the linking "
        "halfway. First pairs:\n\n{shown}\n\nJoining them changes not a "
        "single character of the text: the marker stays, only a link is added."
    ),
    "footnote.keep": "Leave it as it is",
    "footnote.keep.why": "Nothing changes; the markers keep leading nowhere",
    "footnote.link": "Join the markers to their notes",
    "footnote.link.why": (
        "{count} marker(s) become links to their notes; the text stays the "
        "same to the character"
    ),
    # --- contents entries all pointing at one untangled id ------------------
    "toc.duplicate.summary": (
        "{count} contents entries lead to the same place, and untangled "
        "targets are waiting"
    ),
    "toc.duplicate.detail": (
        "In the source one identifier repeated many times, and every one of "
        "these contents entries jumped to its first occurrence. The rebuild "
        "untangled the identifiers and the counts agree: as many entries as "
        "occurrences. Assigned by document order ({where}):\n\n{shown}\n\n"
        "That assignment is probable, not certain — which is why it is a "
        "question."
    ),
    "toc.duplicate.keep": "Leave it as it is",
    "toc.duplicate.keep.why": (
        "Every entry keeps jumping to the first occurrence — the way the "
        "source behaved"
    ),
    "toc.duplicate.repoint": "Repoint the entries in order",
    "toc.duplicate.repoint.why": (
        "{count} contents entries lead one-by-one to their untangled targets; "
        "if the source's ordering meant something else, a reader lands in the "
        "wrong place"
    ),
    # --- a declaration written `property="value"` in a hand-touched rule ----
    "style.dupsel.summary": (
        "Two `{selector}` rules cannot be merged without changing a winner"
    ),
    "style.dupsel.detail": (
        "In {where} the selector `{selector}` appears twice, and between "
        "the copies stands `{blocker}`, fighting over the same thing "
        "({contest}). Merging moves the earlier copy's declarations past "
        "`{blocker}` — where both rules hit the same element, the moved "
        "value starts winning."
    ),
    "style.dupsel.keep": "Leave as is",
    "style.dupsel.keep.why": (
        "Nothing changes; the publisher's cascade stays the publisher's"
    ),
    "style.dupsel.merge": "Merge despite the contest",
    "style.dupsel.merge.why": (
        "The copies become one rule; on shared elements the moved value "
        "starts beating `{blocker}`"
    ),
    "style.tie.summary": (
        "Rule `{selector}` stands below a more specific one, and a tie on "
        "the road will not let it move"
    ),
    "style.tie.detail": (
        "In {where} the lint wants `{selector}` before `{target}`, but on "
        "the way it ties with `{blocker}` over the same thing ({contest}) "
        "on elements this book really has. Moving it makes `{blocker}` "
        "start winning on the shared elements."
    ),
    "style.tie.keep": "Leave as is",
    "style.tie.keep.why": (
        "Nothing changes; the publisher's order keeps deciding the tie"
    ),
    "style.tie.move": "Move despite the tie",
    "style.tie.move.why": (
        "The rule goes where the lint wants it, and `{blocker}` starts "
        "winning on the shared elements; the move lands only if it does "
        "not worsen the lint total"
    ),
    "style.important.summary": (
        "Property `{prop}` repeated in one block with mixed `!important` "
        "and different values — readers compute it differently"
    ),
    "style.important.detail": (
        "In {where} one block declares `{prop}` several times: {values}. "
        "A modern reader takes the `!important` value ({winner}); a reader "
        "that never learned importance takes the last plain one. Which of "
        "the two the book means, only a person knows."
    ),
    "style.important.keep": "Leave as is",
    "style.important.keep.why": (
        "Nothing changes; the divergence between readers stays as it was"
    ),
    "style.important.resolve": "Keep the modern cascade's winner",
    "style.important.resolve.why": (
        "Only `{winner}` remains; every reader, old and new, computes the "
        "same thing from now on"
    ),
    "style.generic.summary": (
        "{count} font declaration(s) name faces the book does not embed, "
        "with no generic fallback ({generic}?)"
    ),
    "style.generic.detail": (
        "In {where}, font-family declarations end on named faces "
        "({examples}) that are not in the book's package. A reader without "
        "such a face falls back to its default — whatever that is. Appending "
        "the generic family `{generic}` tells it: \"if you lack this face, "
        "use your {generic}\". Visible only on readers missing the face — "
        "and there it moves the look toward the publisher's intent."
    ),
    "style.generic.keep": "Leave as is",
    "style.generic.keep.why": (
        "Nothing changes; a reader without the named face keeps using its "
        "default"
    ),
    "style.generic.append": "Append `{generic}` as the fallback",
    "style.generic.append.why": (
        "Each of these declarations gains `, {generic}` at the end; the "
        "named faces stay first and keep priority"
    ),
    "style.equals.summary": (
        "{count} CSS declaration(s) written like an HTML attribute (`=` "
        "instead of `:`) — no reading system applies them"
    ),
    "style.equals.detail": (
        "The sheet {where} carries declarations like:\n\n{shown}\n\n"
        "CSS syntax requires a colon, so every reading system's parser "
        "rejects the whole line — this formatting has never worked. The rule "
        "bears no converter's signature, so it could be a publisher's intent "
        "with a typo in it. Enabling it means formatting nobody has ever "
        "seen starts applying."
    ),
    "style.equals.keep": "Leave it as it is",
    "style.equals.keep.why": (
        "Nothing changes; reading systems keep ignoring the line and the "
        "book looks the way it looked"
    ),
    "style.equals.drop": "Remove the dead line",
    "style.equals.drop.why": (
        "The line leaves the sheet; the book's appearance does not change, "
        "because nothing ever applied it"
    ),
    "style.equals.enable": "Correct the `=` to a `:` and enable it",
    "style.equals.enable.why": (
        "{count} declaration(s) start working — the book may change its "
        "appearance in places nobody has seen with this formatting"
    ),
    "encoding.mojibake.summary": (
        "{count} punctuation marks a conversion turned into codes with no shape"
    ),
    "encoding.mojibake.detail": (
        "The converter that produced this file read Windows text with the wrong "
        "encoding. Quotation marks and dashes landed on positions that Unicode "
        "uses for control codes — no font draws them, so today they are blank "
        "spaces in a reading system.\n\n{shown}\n\n"
        "The mapping is unambiguous and one-way: each of these positions has "
        "exactly one counterpart, and nothing here is guessed."
    ),
    "encoding.mojibake.line": "{count} × {character}",
    "encoding.mojibake.keep": "Leave them as they are",
    "encoding.mojibake.keep.why": (
        "The characters stay in the book exactly as they are — invisible. Not one "
        "character of the text changes"
    ),
    "encoding.mojibake.repair": "Restore the punctuation",
    "encoding.mojibake.repair.why": (
        "{count} shapeless codes become quotation marks, dashes and ellipses. "
        "This changes the text and cannot be undone from the output alone"
    ),
}

CATALOGUES: dict[str, dict[str, str]] = {"pl": TEXTS_PL, "en": TEXTS_EN}


def say(key: str, **values) -> str:
    """The text for *key* in the active language, filled with *values*.

    Falls back to Polish and then to the key itself rather than raising, for the
    same reason `rules.describe` does: a question in the wrong language is still
    a question somebody can answer, and one that refuses to render leaves a
    person staring at a traceback instead of at their book.
    """
    catalogue = CATALOGUES.get(_ACTIVE, TEXTS_PL)
    text = catalogue.get(key) or TEXTS_PL.get(key, key)
    if not values:
        return text
    try:
        return text.format(**values)
    except (KeyError, IndexError, ValueError):
        return text


__all__ = [
    "CATALOGUES",
    "ENV_LANGUAGE",
    "LANGUAGES",
    "language",
    "say",
    "set_language",
]
