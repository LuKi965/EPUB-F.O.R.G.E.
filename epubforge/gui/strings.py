"""Interface text.

Polish is the default because that is what this tool is used in; English is
kept alongside so the strings stay reviewable by non-Polish speakers and the
app can be switched with EPUBFORGE_LANG=en.

Tooltips deliberately explain *consequences* rather than restating the label —
someone deciding whether to tick a box needs to know what it will do to their
book, not what the box is called.
"""

from __future__ import annotations

import os

PL: dict[str, str] = {
    # --- window and toolbar ---------------------------------------------
    "window.title": "EPUB F.O.R.G.E. {version}",
    "toolbar.add": "Dodaj książki…",
    "toolbar.add.tip": (
        "Wybierz pliki EPUB do przebudowy.\n\n"
        "Możesz też po prostu przeciągnąć je w dowolne miejsce tego okna."
    ),
    "toolbar.clear": "Wyczyść listę",
    "toolbar.clear.tip": "Usuwa wszystkie pozycje z listy. Nie kasuje żadnych plików z dysku.",
    "toolbar.output": "Folder wyjściowy:",
    "toolbar.output.placeholder": "puste — zapisz obok pliku źródłowego jako *.forged.epub",
    "toolbar.output.tip": (
        "Gdzie zapisać przebudowane książki.\n\n"
        "Gdy pole jest puste, każdy plik trafia obok oryginału z końcówką "
        "„.forged.epub”. Oryginał nigdy nie jest nadpisywany."
    ),
    "toolbar.browse": "Przeglądaj…",
    "toolbar.browse.tip": "Wskaż folder, w którym mają wylądować gotowe pliki.",

    # --- table ----------------------------------------------------------
    "table.book": "Książka",
    "table.status": "Stan",
    "table.fixed": "Naprawiono",
    "table.fixed.tip": "Liczba usterek, które narzędzie poprawiło.",
    "table.kept": "Zachowano",
    "table.kept.tip": (
        "Liczba odstępstw od standardu zostawionych świadomie, bo ich usunięcie "
        "zmieniłoby wygląd książki. Szczegóły w raporcie poniżej."
    ),
    "table.issues": "Uwagi",
    "table.issues.tip": "Ostrzeżenia i błędy, których nie dało się naprawić automatycznie.",

    "status.queued": "w kolejce",
    "status.done": "gotowe",
    "status.issues": "gotowe z uwagami",
    "status.failed": "niepowodzenie",
    "status.blocked": "odmowa",

    # --- policy panel ---------------------------------------------------
    "policy.group": "Zasady przebudowy",
    "policy.mode.label": "Gdy zgodność ze standardem kłóci się z wyglądem:",
    "policy.mode.tip": (
        "Każdy tryb buduje książkę od nowa: pakiet, nawigację, nazwy plików i "
        "strukturę ZIP. Tak działa to narzędzie — nie łata pliku, tylko wczytuje "
        "książkę i składa nowy, poprawny kontener.\n\n"
        "Ten wybór dotyczy wyłącznie tego, co zrobić z *treścią* w sytuacjach "
        "spornych — na przykład gdy książka używa hacków CSS pod konkretny czytnik "
        "albo zawiera linki do plików, których nigdy w niej nie było."
    ),
    "policy.mode.preserve": "Zachowaj wygląd, zgłoś odstępstwa",
    "policy.mode.strict": "Wymuś standard, nawet kosztem wyglądu",
    "policy.mode.minimal": "Przebuduj tylko kontener, nie ruszaj treści",
    "policy.mode.preserve.tip": (
        "Tryb domyślny i zalecany.\n\n"
        "Książka wygląda dokładnie tak jak przedtem. Jawne błędy wydawcy są "
        "naprawiane, ale rzeczy, które tylko odbiegają od standardu, a działają "
        "— zostają, z adnotacją w raporcie."
    ),
    "policy.mode.strict.tip": (
        "Pełna zgodność z EPUB 3.3, nawet jeśli coś się przez to przesunie.\n\n"
        "Martwe odnośniki tracą href (tekst zostaje), znikają bloki CSS pisane "
        "pod Kindle i właściwości specyficzne dla Adobe. Wynik przechodzi "
        "EPUBCheck bez zastrzeżeń."
    ),
    "policy.mode.minimal.tip": (
        "Regeneruje wyłącznie OPF, nawigację i strukturę ZIP.\n\n"
        "Pliki XHTML i CSS przechodzą bajt w bajt. Użyj, gdy chcesz naprawić "
        "opakowanie, ale absolutnie nie tykać zawartości."
    ),

    "policy.ncx": "Dołącz zapasowy NCX dla starszych czytników",
    "policy.ncx.tip": (
        "Dokłada stary spis treści w formacie EPUB 2 obok nowego.\n\n"
        "Kosztuje kilka kilobajtów, ale sprawia, że spis treści działa również "
        "na leciwych czytnikach. Zalecane."
    ),
    "policy.orphans": "Usuń pliki, do których nic nie prowadzi",
    "policy.orphans.tip": (
        "Domyślnie WYŁĄCZONE i lepiej tak zostawić.\n\n"
        "Kasuje zasoby, których nie widzi żaden rozdział, arkusz stylów ani spis "
        "treści. Trzy dziury, przez które to kasowało używane pliki — „srcset”, "
        "element <picture> i odsyłacze robione wewnątrz SVG — są już zamknięte. "
        "Graf jest **lepszy, ale nie kompletny**: skrypt sklejający nazwę pliku "
        "z dwóch napisów, arkusz osiągalny tylko przez zapytanie medialne, "
        "odwołanie w formacie, którego nic tutaj nie modeluje.\n\n"
        "Zysk to kilka kilobajtów. Ryzyko to dziura w miejscu obrazka."
    ),
    "policy.layout": "Uporządkuj pliki w folderach wg typu",
    "policy.layout.tip": (
        "Przenosi treść do EPUB/text, style do EPUB/styles, obrazy do "
        "EPUB/images i tak dalej, a nazwy sprowadza do bezpiecznego ASCII.\n\n"
        "Wszystkie odnośniki są przepisywane. Niektóre czytniki potrafią się "
        "wyłożyć na polskich znakach w nazwach plików."
    ),
    "policy.watermark.label": "Znak wodny księgarni:",
    "policy.watermark.tip": (
        "Polskie księgarnie znaczą każdy zakupiony plik tokenem — to ich prawo "
        "i nie o token tu chodzi, tylko o to, gdzie on siedzi.\n\n"
        "Zwykle siedzi na końcu każdego rozdziału, ustawiony na 1px albo 0px. "
        "Jest wtedy nadal składany, nadal łamie stronę i nadal bywa czytany "
        "na głos przez syntezator mowy czytnika."
    ),
    "policy.watermark.keep": "Zostaw dokładnie tak, jak jest",
    "policy.watermark.keep.tip": (
        "Znaczniki wychodzą bajt w bajt takie, jakie weszły. Raport i tak "
        "policzy, ile ich jest."
    ),
    "policy.watermark.consolidate": "Zostaw w treści, uporządkuj styl",
    "policy.watermark.consolidate.tip": (
        "Token zostaje tam, gdzie był. Powtarzany w każdym dokumencie styl "
        "liniowy z !important staje się jedną regułą, a element dostaje "
        "aria-hidden.\n\n"
        "Uwaga: aria-hidden wiąże czytniki ekranu, ale nie wiąże syntezatora "
        "mowy wbudowanego w czytnik. Ten czyta to, co jest na stronie."
    ),
    "policy.watermark.gather": "Przenieś do metadanych dokumentu",
    "policy.watermark.gather.tip": (
        "Token wychodzi z treści i ląduje w nagłówku <head> tego samego "
        "dokumentu jako <meta>.\n\n"
        "Nic go nie wyświetla, nic go nie czyta, nic nie łamie wokół niego "
        "strony — a księgarnia znajdzie go tam, gdzie go zostawiła. Z pliku nic "
        "nie ginie, ale z toku czytania token znika, więc to Twój wybór, nie "
        "domyślne zachowanie."
    ),
    "policy.watermark.remove": "Usuń token z książki",
    "policy.watermark.remove.tip": (
        "Znika. Książka przestaje nieść znak wiążący ten egzemplarz z "
        "kupującym.\n\n"
        "Jedyna opcja, która coś traci — i dlatego trzeba ją wybrać ręcznie. "
        "Nie włącza jej żaden tryb."
    ),
    # --- diagnostics panel ----------------------------------------------
    "tab.diagnostics": "Diagnostyka",
    "diagnostics.intro": (
        "Trzy pytania o pliki: co jest w środku, czy walidator to przyjmuje i czy "
        "przebudowa zachowa książkę. Nic tutaj nie zmienia ani nie nadpisuje "
        "żadnego Twojego pliku."
    ),
    "diagnostics.fidelity": "Czy przebudowa zachowa tę książkę",
    "diagnostics.fidelity.tip": (
        "Przebudowuje książkę do folderu tymczasowego i porównuje ją ze "
        "źródłem — nic nie jest zapisywane tam, gdzie to znajdziesz.\n\n"
        "Sprawdza to, o czym walidator nie ma zdania: czy każde słowo źródła "
        "jest w wyniku, czy zgadza się liczba nagłówków, obrazów i akapitów, "
        "czy każdy obrazek i font przeszedł bajt w bajt i czy dokumenty idą w "
        "tej samej kolejności.\n\n"
        "„Poprawny plik” i „ta sama książka” to dwa różne pytania. To jest to "
        "drugie."
    ),
    "diagnostics.shared": "Jeden proces walidatora na całą partię",
    "diagnostics.shared.tip": (
        "EPUBCheck kompiluje swoje schematy przy każdym starcie i to trwa około "
        "trzech i pół sekundy — niezależnie od tego, czy książka ma 2 kB czy "
        "23 MB. Osobny proces na książkę płaci ten koszt za każdym razem.\n\n"
        "Zmierzone na ośmiu prawdziwych książkach: 35,3 s przy procesie na "
        "książkę, 8,4 s przy jednym utrzymywanym. Odpowiedzi są identyczne — "
        "sterownik nie sprawdza niczego sam, tylko woła EPUBCheck tak samo jak "
        "wiersz poleceń.\n\n"
        "Odznacz, jeżeli chcesz porównać wynik z zachowaniem sprzed tej zmiany. "
        "Gdy cokolwiek pójdzie nie tak, program i tak wraca do osobnego procesu "
        "i mówi w raporcie dlaczego."
    ),
    "report.changes": "Bilans zmian: {total}, w tym nieodwracalnych: {irreversible}",
    "merge.title": "Scal dwie uszkodzone kopie",
    "merge.intro": (
        "Dwie kopie tej samej książki, każda zepsuta w innym miejscu — jedna "
        "cała z nich. Każdy plik jest brany w całości, bajt w bajt, z tej "
        "kopii, która oddaje go bez błędu. Nic nie jest rekonstruowane ani "
        "uśredniane.\n\n"
        "Pierwsza na liście jest tą naprawianą; reszta to dawcy. Nic nie zostanie "
        "zapisane, dopóki nie zobaczysz planu i nie klikniesz „Zapisz”."
    ),
    "merge.add": "Dodaj kopie…",
    "merge.remove": "Usuń z listy",
    "merge.examine": "Zbadaj i pokaż plan",
    "merge.output": "Zapisz jako:",
    "merge.write": "Zapisz scaloną",
    "merge.empty": "Dodaj co najmniej dwie kopie i kliknij „Zbadaj i pokaż plan”.",
    "merge.needs.two": "Scalenie potrzebuje co najmniej dwóch kopii.",
    "merge.refused": "Nie da się scalić: {reason}",
    "merge.plan.header": "Plan — {count} wpisów, książka naprawiana: {first}",
    "merge.plan.nothing": "(pierwsza kopia ma wszystko — nie ma czego naprawiać)",
    "merge.plan.missing": "nie ma go w żadnej kopii",
    "merge.plan.conflict": "kopie różnią się i obie są całe — nie wybieram za Ciebie",
    "merge.plan.ready": "Gotowe do zapisania. Odzyskanych z innej kopii: {count}.",
    "merge.plan.unusable": (
        "Nic nie zostanie zapisane. Scalenie ma sens tylko wtedy, gdy każdy wpis "
        "da się wziąć w całości z którejś kopii."
    ),
    "merge.plan.needs.output": "Wskaż jeszcze, gdzie zapisać wynik.",
    "merge.written": "Zapisano {path} — {count} wpisów.",
    "menu.merge": "Scal uszkodzone kopie…",
    "diagnostics.render": "Czy po przebudowie wygląda tak samo",
    "diagnostics.render.tip": (
        "Rysuje strony książki przed i po przebudowie i porównuje obrazy. To "
        "jedyna kontrola w tym programie, która patrzy na *wygląd* — wszystkie "
        "pozostałe czytają plik.\n\n"
        "Za usterkę uznawana jest tylko **strata**: strona, która wyszła pusta, "
        "albo taka, na której treści jest wyraźnie mniej niż w źródle. Zmiana, "
        "po której treści jest tyle samo albo więcej, jest wypisana i nie liczy "
        "się jako błąd — przebudowa, która dopasowuje za dużą okładkę do strony, "
        "zmienia jedną piątą pikseli i naprawia książkę.\n\n"
        "Potrzebuje przeglądarki opartej na Chromium. Nie jest instalowana razem "
        "z programem, bo przebudowa książki niczego nie rysuje; jeśli jej nie ma, "
        "ta kontrola powie, czego szuka i jak ją wskazać."
    ),
    "diagnostics.health": "Czy te pliki są całe",
    "diagnostics.health.tip": (
        "Rozpakowuje każdy plik wewnątrz książki i mówi, których archiwum nie "
        "oddaje. To jedyny sposób, żeby się tego dowiedzieć: spis zawartości "
        "ZIP-a leży na końcu pliku i przerwane pobranie potrafi zostawić go "
        "nienaruszonym, więc książka wygląda na kompletną, dopóki ktoś nie "
        "spróbuje jej rozpakować.\n\n"
        "Warto uruchomić w dniu zakupu. Uszkodzony plik naprawia się pobraniem "
        "go ponownie — a to jest łatwe dzisiaj i bywa niemożliwe za dwa lata, "
        "gdy tytuł zniknie ze sprzedaży."
    ),
    "diagnostics.files": "Plik lub folder:",
    "diagnostics.mode": "Pytanie:",
    "diagnostics.inspect": "Co jest w tym pliku",
    "diagnostics.inspect.tip": (
        "Czyta książkę i wypisuje, co w niej znalazł: wersję, metadane, liczbę "
        "zasobów, kolejność czytania, okładkę, nawigację, zaciemnione fonty i DRM.\n\n"
        "To jest widok *przed* przebudową — pokazuje, z czym narzędzie ma do "
        "czynienia, a nie co z tego zrobi."
    ),
    "diagnostics.validate": "Czy EPUBCheck to przyjmuje",
    "diagnostics.validate.tip": (
        "Puszcza walidator na plik taki, jaki jest — bez przebudowy.\n\n"
        "Przydaje się do dwóch rzeczy: sprawdzenia, czy książka była zepsuta "
        "*zanim* jej dotknęliśmy, i sprawdzenia gotowego wyniku."
    ),
    "diagnostics.empty": "Wskaż plik albo folder z książkami i naciśnij „Uruchom”.",
    "policy.fonts": "Odszyfruj zaciemnione fonty",
    "policy.fonts.tip": (
        "Część księgarń „zaciemnia\u201d osadzone fonty — miesza pierwsze bajty "
        "pliku, żeby nie dało się go po prostu wyjąć i zainstalować. Czytnik to "
        "odkręca w locie, więc na ekranie nie widać różnicy.\n\n"
        "Włączone: font wychodzi zwyczajny, a deklaracja szyfrowania znika. "
        "Wyłączone: zostaje tak, jak było. Nie ma to wpływu na wygląd książki — "
        "ma na to, czy plik fontu da się otworzyć czymkolwiek innym."
    ),
    "policy.images": "Przekoduj obrazy w formatach spoza standardu",
    "policy.images.tip": (
        "BMP i TIFF renderują się w części czytników i nie w innych, więc są "
        "zamieniane na PNG. WebP **nie** — to jest format podstawowy w EPUB 3.3 "
        "i nic mu nie trzeba robić.\n\n"
        "Obraz wieloklatkowy nie jest przekodowywany nigdy, cokolwiek tu stoi: "
        "konwersja zachowałaby pierwszą klatkę i po cichu wyrzuciła resztę."
    ),
    "policy.incomplete": "Przebuduj mimo nieodczytanego fragmentu źródła",
    "policy.incomplete.tip": (
        "Zwykle, kiedy któregoś wpisu archiwum nie da się odczytać — bo jest "
        "monstrualny albo strumień jest uszkodzony — przebudowa **zatrzymuje "
        "się i nic nie zapisuje**. Książka, której nie widać w całości, nie może "
        "dostać obietnicy, że nic z niej nie zginęło.\n\n"
        "To pole jest wyjściem awaryjnym dla człowieka, który trzyma tę książkę "
        "i wie, co robi. Zaznaczone: plik powstanie mimo wszystko, a raport "
        "powie, czego w nim nie ma. Nie sprawia, że strata staje się cicha."
    ),
    "policy.gate": "Zanim wyda plik, zapytaj EPUBCheck:",
    "policy.gate.tip": (
        "Czy wynik ma być sprawdzony walidatorem **zanim** trafi pod swoją "
        "nazwę — a nie po fakcie.\n\n"
        "Sprawdzenie dzieje się na pliku tymczasowym, tuż przed podmianą, więc "
        "odmowa nie rusza tego, co już leży pod tą nazwą. To jest cały powód, "
        "dla którego bramka stoi tutaj, a nie „sprawdź i skasuj, jak złe”: "
        "kasowanie po podmianie zniszczyłoby poprzednią, dobrą książkę.\n\n"
        "Ustawia się samo według trybu i możesz to nadpisać."
    ),
    "policy.gate.off": "nie pytaj — wydaj i opisz w raporcie",
    "policy.gate.off.tip": (
        "Tak działał ten program do tej pory. Walidacja jest dostępna osobno, "
        "w zakładce Diagnostyka i pod „sprawdź wynik”, i nic nie blokuje.\n\n"
        "Domyślne dla trybu zachowawczego i minimalnego, bo książki przychodzą "
        "z defektami i ten program ma je przenieść, a nie odmówić wydania."
    ),
    "policy.gate.no-new-errors": "wydaj, o ile ta przebudowa nie dołożyła błędu",
    "policy.gate.no-new-errors.tip": (
        "Sprawdza także źródło i porównuje. Książka, która przyszła zepsuta, "
        "wychodzi zepsuta i jest o tym napisane; książka, którą zepsuł ten "
        "program, nie wychodzi wcale.\n\n"
        "Uwaga na to, co dokładnie porównuje: źródło EPUB 2 jest sądzone "
        "regułami EPUB 2, a wynik EPUB 3 regułami EPUB 3. „Nowy” może więc "
        "znaczyć „EPUB 3 ma regułę, której EPUB 2 nie miał”. Raport podaje "
        "wersję źródła obok odmowy, żeby to było widać, a nie do wywnioskowania."
    ),
    "policy.gate.clean": "wydaj tylko plik, który EPUBCheck przyjmuje",
    "policy.gate.clean.tip": (
        "Dosłowny inwariant: zero błędów przed wydaniem, czyjekolwiek by nie "
        "były. Domyślne dla trybu ścisłego — tryb ścisły, który wydaje "
        "niepoprawny plik, nie jest ścisły.\n\n"
        "Odmówi książek, których ten program nie zepsuł: takich, które "
        "przyszły niepoprawne i nie da się ich naprawić bez zgadywania. Na "
        "korpusie publicznym to trzy książki z dwunastu.\n\n"
        "Gdy walidatora nie ma, ta bramka **odmawia**. Twierdzenie, którego "
        "nikt nie sprawdził, nie jest twierdzeniem."
    ),
    "decide.title": "Decyzja",
    "decide.value": "wpisz własną formę",
    "decide.irreversible": "Tego nie da się cofnąć z samego pliku wynikowego.",
    "decide.all": "Tak samo dla wszystkich takich przypadków w tej książce",
    "decide.all.tip": (
        "Dotyczy tylko przypadków o tym samym stopniu pewności. Opcja, w której "
        "wpisujesz własną formę, nigdy nie obejmuje grupy — to zdanie o jednym "
        "słowie, nie o wszystkich."
    ),
    "policy.render": "Sprawdzaj wygląd po przebudowie",
    "policy.render.tip": (
        "Rysuje strony książki przed i po przebudowie i porównuje obrazy. To "
        "jedyna kontrola, która patrzy na *wygląd* — wszystkie inne czytają plik.\n\n"
        "Pyta o trzy rzeczy i tylko o trzy: czy dokument zniknął z kolejności "
        "czytania, czy strona wyszła pusta, i czy ubyło jednocześnie treści i "
        "zajmowanego przez nią miejsca. Nie ma zdania o tym, czy czcionka jest "
        "inna ani czy wiersze łamią się inaczej.\n\n"
        "Przesunięcie tekstu jej nie rusza. Zmierzone: po złączeniu 46 łączników "
        "w jednej książce 7 ze 130 porównań stron w ogóle drgnęło, największe o "
        "1,64% pikseli, a treści nie ubyło nigdzie.\n\n"
        "Potrzebuje przeglądarki opartej na Chromium. Nie jest instalowana razem "
        "z programem; bez niej kontrola się nie wykona, a raport powie to wprost."
    ),
    "policy.render.gate": "Gdy strona straci treść:",
    "policy.render.unverified": "Zapisz nawet wtedy, gdy nie da się sprawdzić wyglądu",
    "policy.metadata.reconstructed": "Przyjmuj metadane odczytane z uszkodzonego pakietu",
    "policy.hyphen.review": "Słowa z łącznikiem bez dowodu w książce:",
    "policy.hyphen.review.tip": (
        "Program pyta o słowo z łącznikiem wtedy, gdy ta sama książka pisze je "
        "gdzie indziej bez łącznika — to jest dowód, że łącznik został po "
        "konwersji. Reszta dowodu nie ma.\n\n"
        "Zmierzone na 32 książkach: 67 z dowodem, 101 „prawdopodobnych” i 88 "
        "„niepewnych”, a w tych dwóch listach prawie każdy wpis to prawdziwy "
        "wyraz złożony — „marksizm-leninizm”, „savoir-vivre”, „ping-pong”."
    ),
    "policy.hyphen.review.confirmed": "pytaj tylko o te z dowodem",
    "policy.hyphen.review.confirmed.tip": (
        "Reszta jest policzona i pokazana w raporcie, i nietknięta."
    ),
    "policy.hyphen.review.grouped": "pokaż resztę jednym pytaniem na klasę",
    "policy.hyphen.review.grouped.tip": (
        "Jedno pytanie na klasę pewności, z listą słów w środku. 189 kandydatów "
        "to jedna decyzja zamiast 189."
    ),
    "policy.hyphen.review.each": "pytaj o każde osobno",
    "policy.hyphen.review.each.tip": (
        "Dla kogoś, kto chce przejść przez wszystkie po kolei. Przy dużej "
        "książce to bywa i sto kilkadziesiąt pytań."
    ),
    "policy.metadata.reconstructed.tip": (
        "Kiedy pakiet książki daje się sparsować dopiero po odzysku, tytuł, autor "
        "i język są odczytem parsera z cudzej książki, a nie tym, co napisał wydawca "
        "— potrafi z tego wyjść „ORIGINALpl”, czyli zlepek, którego nikt nigdy nie "
        "napisał.\n\n"
        "Odznaczone: program zapyta o każde takie pole i bez odpowiedzi nie zapisze "
        "nic. Zaznaczone: zapisze to, co odczytał, i napisze w raporcie, skąd to "
        "pochodzi."
    ),
    "policy.render.unverified.tip": (
        "To osobne pytanie niż powyższe. Powyższe mówi, co zrobić, gdy kontrola "
        "wyglądu SIĘ WYKONA i znajdzie stronę ze stratą. To mówi, co zrobić, gdy "
        "kontrola NIE MA JAK się wykonać — bo na tej maszynie nie ma przeglądarki.\n\n"
        "Odznaczone: program zapyta, zanim cokolwiek zapisze, i bez odpowiedzi nie "
        "zapisze nic. Zaznaczone: zapisze i napisze w raporcie, że wygląd nie został "
        "sprawdzony — zgoda wydana z góry, na przykład dla partii, przy której nikt "
        "nie siedzi."
    ),
    "policy.render.gate.off": "nie sprawdzaj wyglądu w ogóle",
    "policy.render.gate.off.tip": (
        "Kontrola nie działa przy przebudowie. Zostaje osobne pytanie w "
        "Diagnostyce i polecenie „render-check”, uruchamiane ręcznie."
    ),
    "policy.render.gate.report": "zapisz plik i napisz o tym w raporcie",
    "policy.render.gate.report.tip": (
        "Strata trafia do raportu, obrazy przed/po lądują obok książki, a plik "
        "powstaje. Decyzję, co z tym zrobić, podejmujesz po fakcie."
    ),
    "policy.render.gate.stop": "nie zapisuj pliku",
    "policy.render.gate.stop.tip": (
        "Przy wykrytej stracie nic nie zostaje zapisane, a plik, który był pod tą "
        "nazwą, zostaje nietknięty. Obrazy przed/po są zapisywane obok, żeby dało "
        "się zobaczyć, o co chodzi.\n\n"
        "Zmierzone przed ustawieniem tego jako domyślne: 0 odmów na 32 książkach."
    ),
    "policy.text.invariant": "Sprawdź, czy nie ubyło tekstu (K1)",
    "policy.text.invariant.tip":
        "Przed nadaniem plikowi nazwy porównuje tekst źródła z tekstem wyniku: "
        "każdy znak kolejności czytania ma być w wyniku, w tej samej kolejności. "
        "Odstępy, cudzysłowy i myślniki są składane, bo przebudowa świadomie je "
        "zmienia. Usunięcie znaku wodnego i złączenie przeciętego słowa są "
        "wyjątkami — dzieją się na Twoją prośbę i są nazwane w raporcie.",
    "policy.render.all": "Rysuj wszystkie strony, nie próbkę",
    "policy.render.all.tip": (
        "Domyślnie rysowanych jest 12 stron: pierwsze trzy zawsze, bo okładka i "
        "strony tytułowe to miejsce, gdzie obrazki się tną i gniotą, a reszta "
        "rozłożona po książce. To około 36 sekund na książkę.\n\n"
        "Zaznaczone — rysowane są wszystkie strony. Dla książki o 65 rozdziałach "
        "to kilka minut, ale wtedy nic nie jest zgadywane z próbki."
    ),
    "policy.repair.encoding": "Przywróć znaki przestankowe zgubione przez konwersję",
    "policy.repair.encoding.tip": (
        "Windows trzyma cudzysłowy, myślniki i wielokropki na pozycjach, które "
        "Unikod rezerwuje dla kodów sterujących. Konwerter, który odczyta taki "
        "tekst złym kodowaniem, zamienia każdy z tych znaków w kod bez "
        "kształtu — żadna czcionka go nie rysuje, więc w czytniku zostaje "
        "puste miejsce.\n\n"
        "Wyłączone — program **pyta** przy każdej książce, w której to znajdzie, "
        "i pokazuje, ilu znaków i jakich to dotyczy.\n\n"
        "Włączone — odpowiada „napraw” za Ciebie, dla całej kolejki. Przydatne "
        "przy wielu książkach naraz; odwzorowanie jest jednoznaczne i nic w nim "
        "nie jest zgadywane.\n\n"
        "**To jest zmiana tekstu** i nie da się jej cofnąć z samego wyniku — "
        "dlatego domyślnie program pyta, zamiast robić."
    ),
    "policy.shop.notices": "Usuń widoczne ślady księgarni",
    "policy.shop.notices.tip": (
        "Niektóre księgarnie wstawiają w treść zdanie o zamówieniu: numer "
        "zamówienia, imię i nazwisko kupującego, adres e-mail, „zakupione "
        "dla…”. W jednej z Twoich książek siedzi to **w biegnącym tekście, "
        "tuż przed pierwszym zdaniem powieści**.\n\n"
        "Włączone — takie zdania są usuwane, a raport wypisuje **każde z nich "
        "co do słowa**, nie liczbę. To jedyne ustawienie w tym programie, które "
        "kasuje tekst widoczny dla czytelnika, więc masz sprawdzić, że zabrało "
        "zdanie księgarni, a nie zdanie z Twojej książki.\n\n"
        "Zabierane są wyłącznie zdania nazywające **sprzedaż** — zamówienie, "
        "zakup, licencję, kupującego. **Stopka redakcyjna wydawcy** (adres, "
        "telefon, ISBN) nazywa wydawcę, a nie transakcję, i nie jest ruszana. "
        "**Żadna strona nie jest usuwana** — element, który zostanie pusty, "
        "zostaje, a bilans to zgłasza.\n\n"
        "To ustawienie jest osobne od „znaków wodnych” powyżej: tamto pyta, jak "
        "widoczny może być ukryty znacznik, to pyta, czy wolno skasować zdanie."
    ),
    "policy.relative.units": "Uwolnij rozmiary czcionek spod pikseli",
    "policy.relative.units.tip": (
        "Książka, która pisze `font-size: 12px`, odebrała sterowanie wielkością "
        "pisma osobie, która ją czyta: na czytniku ustawionym na większy tekst "
        "ten fragment i tak zostanie dwunastopikselowy. To najczęstsza "
        "pozostałość po składzie do druku na twojej półce.\n\n"
        "Włączone — rozmiary podane w px i pt zostają przepisane na **rem**, "
        "czyli miarę liczoną od ustawienia czytnika. Przy ustawieniu domyślnym "
        "strona wygląda **identycznie** co do piksela; przy zmienionym cała "
        "książka skaluje się razem z nim, zachowując proporcje między "
        "rozmiarami, które dobrał wydawca.\n\n"
        "Domyślnie **wyłączone**, i nie z ostrożności o arytmetykę: to jest "
        "przepisanie arkusza, który ktoś napisał. Poza ustawieniem domyślnym "
        "książka celowo przestaje wyglądać tak samo — o to w tym chodzi — więc "
        "jest to decyzja, a nie naprawa.\n\n"
        "Raport wypisuje liczbę takich rozmiarów w każdym pliku niezależnie od "
        "tego, czy ten przełącznik jest włączony."
    ),
    "policy.hyphens": "Szukaj łączników zostawionych w środku słów",
    "policy.hyphens.tip": (
        "Zła konwersja PDF-a zostawia w tekście łącznik z podziału wiersza: "
        "„obo-jętna”, „ko-rytarz”, „Ce-laena”. Czytelnik to widzi i jest to błąd, "
        "którego żadna reguła w tym programie wcześniej nie umiała zobaczyć.\n\n"
        "Ten przełącznik włącza samo **wykrywanie**. Nic nie jest łączone bez "
        "twojej odpowiedzi — nie ma ustawienia, które kazałoby temu działać "
        "samodzielnie, i dlatego wykrywanie może być domyślnie włączone.\n\n"
        "Pytania dostajesz tylko o te przypadki, gdzie dowód jest w samej "
        "książce: ta sama książka pisze to słowo bez łącznika. Zmierzone na "
        "32 książkach: 67 takich, wobec 189 podejrzeń bez dowodu, z których "
        "prawie wszystkie to prawdziwe słowa — „marksizm-leninizm”, "
        "„savoir-vivre”, „ping-pong”. O tamte nie pyta."
    ),
    "policy.remember": "Pamiętaj moje odpowiedzi o tej książce",
    "policy.remember.tip": (
        "Odpowiedzi zapisują się obok książki, w pliku „<nazwa>.decyzje.json”, "
        "i przy kolejnej przebudowie program pyta tylko o to, czego jeszcze nie "
        "wie.\n\n"
        "Jeżeli plik książki się zmienił, zapis jest odrzucany w całości i "
        "raport to mówi. Odtworzenie czyjejś decyzji na stronie, której ta osoba "
        "nie widziała, jest gorsze niż zapytanie drugi raz."
    ),
    "policy.memory": "Odmawiaj książek, na które ta maszyna nie ma pamięci",
    "policy.memory.limit.placeholder": "budżet pamięci, np. 4G — puste znaczy „zapytaj system”",
    "policy.memory.limit.tip": (
        "Stały budżet zamiast pytania, ile pamięci jest akurat wolnej. Przydaje "
        "się, gdy pracujesz w czasie, gdy leci wsad: wolna pamięć zmienia się "
        "wtedy z każdym otwartym oknem, a próg, który się rusza, odmawia raz tej "
        "książki, raz innej.\n\n"
        "Zapisuje się tak, jak się mówi: 4G, 512M, 1500000. Puste pole znaczy "
        "„pytaj system i zostaw jedną piątą zapasu”."
    ),
    "policy.memory.tip": (
        "Przed otwarciem książki szacowany jest jej koszt pamięciowy, a gdy "
        "przekracza to, co system podaje jako wolne, przebudowa jest odmawiana z "
        "raportem zamiast być zabita w połowie.\n\n"
        "Skąd to się wzięło: czytnik od dawna ma sufit 2 GiB treści. Pomiar na "
        "sześciu książkach pokazał, że tekst po sparsowaniu kosztuje dwanaście "
        "razy swój rozmiar — dokument XHTML nie zostaje ciągiem znaków, staje "
        "się drzewem elementów. Sufit 2 GiB treści jest więc obietnicą, że "
        "proces może sięgnąć dwudziestu czterech gigabajtów. Maszyna z 2 GiB "
        "wolnymi umiera przy jakichś 160 MB tekstu — i umiera przez zabicie: bez "
        "raportu, bez rozpoznania, bez pliku i bez komunikatu, z którym da się "
        "cokolwiek zrobić.\n\n"
        "Szacunek jest modelem z sześciu książek i celowo 15% pesymistycznym. "
        "Odznacz, jeżeli wiesz coś, czego model nie wie — że nic innego nie "
        "działa, że jest swap, że ta książka jest inna niż tamtych sześć."
    ),
    "policy.reproducible": "Buduj reprodukowalnie (te same bajty za każdym razem)",
    "policy.reproducible.tip": (
        "Dwie przebudowy tej samej książki dają plik bajt w bajt identyczny. "
        "Przydaje się, gdy chcesz porównać dwa buildy albo sprawdzić, że to, co "
        "masz, faktycznie powstaje z tego źródła.\n\n"
        "Zmienia dwie rzeczy. `dcterms:modified` bierze się ze źródła, a nie z "
        "zegara — a jeżeli źródło nie ma żadnej daty, wpisywana jest epoka "
        "(1970), bo wymyślenie wiarygodnie wyglądającej daty byłoby zmyśleniem "
        "faktu o cudzej książce. Książka bez własnego identyfikatora dostaje "
        "identyfikator **wyliczony z jej zawartości**, a nie losowy — ten sam "
        "plik zawsze ten sam, dwie różne książki nigdy taki sam.\n\n"
        "Domyślnie wyłączone, bo uczciwą datą modyfikacji pliku zrobionego "
        "przed chwilą jest „przed chwilą”."
    ),
    "policy.junk": "Usuwaj pozostałości po pakowaniu",
    "policy.junk.tip": (
        "`.DS_Store`, `Thumbs.db`, `__MACOSX/`, cienie `._`, "
        "`iTunesMetadata.plist`, `calibre_bookmarks.txt`, `.bak` — rzeczy, "
        "które archiwum zebrało po drodze z czyjegoś komputera i których w "
        "publikacji nie ma po co trzymać.\n\n"
        "Usuwane **tylko wtedy, gdy książka się do nich nie odwołuje**. Nazwa "
        "nie jest dowodem o treści: `rozdzial.bak` to nazwa, jaką wydawca może "
        "dać plikowi, który jest w manifeście i do którego prowadzi spis "
        "treści. Plik, do którego coś prowadzi, zostaje i raport to mówi.\n\n"
        "Odznaczone: nie usuwa nic, cokolwiek by się nazywało."
    ),
    "policy.ask": "Pytaj mnie o odnośniki, których nie da się rozwiązać",
    "policy.ask.tip": (
        "Odnośnik potrafi wskazywać kotwicę, której w dokumencie docelowym nie "
        "ma — najczęściej po konwersji z PDF-a, gdzie tylko część przypisów "
        "dostała identyfikator. Program **nie zgadnie**, dokąd taki odnośnik "
        "miał prowadzić: usunięcie fragmentu uciszyłoby walidator i wysłało "
        "czytelnika z przypisu siedemnastego do pierwszego.\n\n"
        "Zaznaczone: przy każdym takim odnośniku dostajesz okno z jego treścią "
        "i listą kotwic, które w dokumencie docelowym naprawdę są — i decydujesz "
        "sam. Można odpowiedzieć raz na całą książkę.\n\n"
        "Odznaczone: odwołanie zostaje dokładnie takie, jakie napisał wydawca, a "
        "raport je wymienia. W trybie ścisłym książka z takimi odnośnikami nie "
        "zostanie w ogóle zapisana."
    ),
    "ask.title": "Dokąd prowadzi ten odnośnik?",
    "ask.explanation": (
        "Ten odnośnik wskazuje kotwicę, której w dokumencie docelowym nie ma. "
        "Program nie wie, dokąd miał prowadzić, i nie zgadnie za Ciebie."
    ),
    "ask.facts": (
        "Dokument: {document}\n"
        "Odnośnik: {reference}\n"
        "Treść odnośnika: {text}"
    ),
    "ask.no-text": "(bez tekstu)",
    "ask.keep": "Zostaw tak, jak napisał wydawca",
    "ask.keep.tip": (
        "Odwołanie zostaje nietknięte. Czytelnik zobaczy, że odnośnik jest "
        "zepsuty — co jest uczciwsze niż odnośnik, który po cichu prowadzi w "
        "niewłaściwe miejsce. Raport wymieni je wszystkie."
    ),
    "ask.repoint": "Wskaż kotwicę, o którą chodzi:",
    "ask.repoint.tip": (
        "Lista identyfikatorów, które w dokumencie docelowym naprawdę są. "
        "Wybrana kotwica trafia do odnośnika, a raport zapisuje, że wskazał ją "
        "człowiek, a nie program."
    ),
    "ask.document": "Kieruj na początek dokumentu docelowego",
    "ask.document.tip": (
        "Fragment znika, odnośnik prowadzi na początek pliku. Program sam tego "
        "nigdy nie zrobi — przy przypisie oznacza to trafienie w przypis "
        "pierwszy zamiast siedemnastego. Wybierz to, jeżeli wiesz, że w tej "
        "książce tak jest dobrze."
    ),
    "ask.all": "Zastosuj tę odpowiedź do wszystkich pozostałych w tej książce",
    "ask.all.tip": (
        "Konwersja potrafi zostawić dwieście takich odnośników. Dotyczy tylko "
        "odpowiedzi, które znaczą to samo wszędzie — wskazania konkretnej "
        "kotwicy nie da się zastosować do całej książki, bo każdy odnośnik "
        "wskazywałby wtedy to samo miejsce."
    ),
    "policy.typography": "Popraw typografię tekstu",
    "policy.typography.tip": (
        "Jedyne miejsce, w którym narzędzie zmienia sam tekst, a nie znaczniki "
        "wokół niego. Dlatego jest wyłączone i nie włącza go żaden tryb.\n\n"
        "Trzy kropki stają się wielokropkiem, a w książkach polskich "
        "jednoliterowe spójniki (a i o u w z) dostają twardą spację, żeby nie "
        "zostawały na końcu wiersza.\n\n"
        "Po każdym dokumencie sprawdza samo siebie: jeżeli nie potrafi wykazać, "
        "że zachowało tekst co do słowa, przywraca dokument bez zmian i pisze "
        "o tym w raporcie."
    ),
    "policy.scripts": "Usuń skrypty JavaScript",
    "policy.dead": "Usuwaj to, co nic nie robi",
    "policy.dead.tip": (
        "Reguły CSS dla znaczników, których książka nie zawiera, i znaczniki "
        "<span>, których reguły nie zmieniają niczego.\n\n"
        "Nic z tego nie zmienia ani jednego piksela — ale usuwanie to usuwanie, "
        "więc masz to pod ręką. Włączone samo w trybie „Wymuś standard”; "
        "odznaczenie działa również tam.\n\n"
        "Wyłączone: raport i tak wypisze, ile tego jest i gdzie."
    ),
    "policy.scripts.tip": (
        "Wycina elementy <script> i atrybuty zdarzeń.\n\n"
        "Domyślnie wyłączone: część książek o stałym układzie używa skryptów do "
        "poprawnego wyświetlania i bez nich się rozjedzie."
    ),
    "policy.validate": "Sprawdź wynik programem EPUBCheck",
    "policy.validate.tip": (
        "Uruchamia oficjalny walidator W3C na gotowym pliku i dopisuje jego "
        "werdykt do raportu.\n\n"
        "Wydłuża przetwarzanie o kilka sekund na książkę."
    ),
    "policy.validate.missing": (
        "EPUBCheck nie został znaleziony.\n\n"
        "W wersji instalowanej jest dołączony. Przy uruchamianiu ze źródeł "
        "wskaż plik epubcheck.jar zmienną EPUBCHECK_JAR."
    ),

    # --- tabs and shared ------------------------------------------------
    "tab.rebuild": "Przebudowa",
    "tab.library": "Biblioteka",
    "tab.corpus": "Korpus",
    "common.folder": "Folder:",
    "common.browse": "Przeglądaj…",
    "common.run": "Uruchom",
    "common.stop": "Przerwij",
    "common.save": "Zapisz wynik…",
    "common.saved": "Zapisano: {path}",
    "common.pickfolder": "Wybierz folder",
    "common.nofolder": "Najpierw wskaż folder z książkami.",
    "common.working": "Pracuję: {name}",
    "common.done": "Gotowe — {count} {count:książka|książki|książek}",

    # --- library tab ----------------------------------------------------
    "library.intro": (
        "Dwa różne pytania o całą bibliotekę naraz. Nic nie jest zapisywane obok "
        "Twoich książek i nic ich nie zmienia."
    ),
    "library.mode": "Co policzyć:",
    "library.survey": "Przegląd — co narzędzie naprawia i jak często",
    "library.survey.tip": (
        "Przepuszcza każdą książkę przez pełne przetwarzanie i zlicza znaleziska.\n\n"
        "Odpowiada na pytanie „co się psuje najczęściej”, a nie „co jest w tej jednej "
        "książce”. Reguła napisana z jednego pliku jest zgadywaniem; ta sama usterka "
        "w czterdziestu plikach jest faktem.\n\n"
        "Wynik nie jest nigdzie zapisywany poza plikiem, który sam wskażesz."
    ),
    "library.inventory": "Inwentarz — czym te książki są",
    "library.inventory.tip": (
        "Mierzy pochodzenie (ślady Calibre, InDesigna, Worda, konwersji z PDF-u), "
        "uszkodzenia (eksplozja klas, zupa spanów, martwy CSS) i typografię "
        "(cudzysłowy, pauzy, wielokropki, mojibake).\n\n"
        "Przegląd potrafi wymienić tylko te usterki, które narzędzie już umie nazwać — "
        "więc sam siebie nie zaskoczy. Inwentarz mówi, czego jeszcze nie widzi."
    ),
    "library.withnames": "Dołącz nazwy plików do wyniku",
    "library.withnames.tip": (
        "Domyślnie wyłączone. Wynik ma się dać komuś pokazać, a lista tytułów mówi "
        "więcej o Twojej półce niż o narzędziu.\n\n"
        "Włącz, jeśli chcesz móc odnaleźć konkretną książkę stojącą za liczbą."
    ),
    "library.empty": "Wskaż folder z ebookami i naciśnij „Uruchom”.",
    # The survey renderer used to write these into the output itself, so a
    # window switched to English printed an English report with Polish headings.
    "survey.books": "{count} {count:książka|książki|książek}",
    "survey.versions": "wersje źródła: {versions}",
    "survey.unreadable": "nieodczytanych",
    "survey.crashed": "awarii etapu",
    "survey.drm": "z DRM (odrzucone): {count}",
    "survey.head.books": "ksiąg",
    "survey.head.total": "razem",
    "survey.head.level": "poziom",
    "survey.head.stage": "etap",
    "survey.head.finding": "znalezisko",

    # --- corpus tab -----------------------------------------------------
    "corpus.intro": (
        "Sieć bezpieczeństwa dla tego programu, nie dla Twoich plików.\n\n"
        "Dla każdej książki zapisuje, co przebudowa z niej zrobiła — same liczby "
        "i skrót wyniku. Gdy jutro zmienię w narzędziu regułę, a ta zmiana zepsuje "
        "którąkolwiek z Twoich książek, ten test to zauważy — mimo że tych książek "
        "nigdy nie widziałem i nie zobaczę. „Inny wynik” znaczy więc: przebudowana "
        "inaczej niż ostatnim razem. Twój plik na dysku pozostaje nietknięty."
    ),
    "corpus.books": "Książki:",
    "corpus.signatures": "Podpisy:",
    "corpus.signatures.placeholder": "puste — folder „expected” obok książek",
    "corpus.check": "Sprawdź",
    "corpus.check.tip": (
        "Porównuje każdą książkę z zapisanym podpisem i wypisuje, co się różni.\n\n"
        "Nic nie nadpisuje."
    ),
    "corpus.record": "Nagraj podpisy",
    "corpus.record.tip": (
        "Zapisuje podpisy z tego przebiegu jako nowy punkt odniesienia — i najpierw "
        "pokazuje, co się zmieniło.\n\n"
        "Rób to wtedy, gdy zmiana w narzędziu była zamierzona."
    ),
    "corpus.what": (
        "Podpis zawiera: liczbę znalezisk, czy tekst przeżył przebudowę, liczbę bloków, "
        "wynik EPUBCheck i skrót pliku wyjściowego. Ani tytułu, ani autora, ani jednego "
        "zdania treści."
    ),
    "corpus.empty": "Wskaż folder z książkami i naciśnij „Sprawdź”.",
    "corpus.status.unchanged": "bez zmian",
    "corpus.status.changed": "inny wynik",
    "corpus.status.new": "nowa",
    "corpus.status.failed": "błąd",
    "corpus.status.duplicate": "ta sama",
    "corpus.edges": "Dołóż brzegi",
    "corpus.edges.tip": (
        "Dopisuje do folderu z książkami cztery pliki, których nie da się kupić: "
        "bez okładki, jedna grafika 9 MB, 400 pozycji spine, cała książka w jednym "
        "pliku.\n\n"
        "Roadmapa nazywa je rodziną „patologie” — awarie pamięciowe i wydajnościowe "
        "wychodzą tylko na nich. Uruchomione dwa razy zostawiają cztery pliki, nie osiem."
    ),
    "corpus.edges.done": "Dopisano {count} {count:plik brzegowy|pliki brzegowe|plików brzegowych}:",
    "corpus.edges.working": "buduję brzegi…",
    "corpus.fixtures": "Książki testowe",
    "corpus.fixtures.tip": (
        "Trzy ustalenia audytu da się zamknąć tylko na dwóch konkretnych, kupionych "
        "książkach — żaden plik syntetyczny ich nie zastąpi. Audyt nazwał je "
        "„obowiązkowymi”, po czym zapisał wszystkie trzy jako zablokowane z powodu "
        "braku plików, nie mówiąc nigdzie, o które pliki chodzi.\n\n"
        "Ten przycisk mówi, o które. Sprawdza wybrany folder i wypisuje, czego "
        "brakuje, wraz z tym, co ta książka ma zawierać. Nic nie jest kopiowane; do "
        "repozytorium trafia odcisk i kilka liczb, nigdy tytuł ani znak tekstu."
    ),
    "corpus.fixtures.assign": "Przypisz książkę testową…",
    "corpus.fixtures.assign.tip": (
        "Wskaż plik, który ma wypełnić rolę. Potrzebne, gdy masz inne wydanie niż "
        "zapisane: rola jest dopasowywana po odcisku i po niczym innym, bo "
        "dopasowanie „po podobieństwie” podało kiedyś do roli zupełnie inną powieść."
    ),
    "corpus.fixtures.role": "Do której roli?",
    "corpus.fixtures.done": "Przypisano {role} ← {name}",
    "corpus.fixtures.present": "jest",
    "corpus.fixtures.missing": "brak",
    "corpus.fixtures.needed": "potrzebna do: {findings}",
    "corpus.fixtures.similar": "podobna na półce: {name}",
    "corpus.fixtures.working": "szukam książek testowych…",
    "corpus.streak": "Passa zielonych wydań: {count} ({releases}).",
    "corpus.streak.none": "Passa zielonych wydań: brak — ostatni przebieg nie był czysty.",
    "corpus.streak.widened": "Pominięte jako poszerzenie pomiaru: {releases}.",

    # --- reader compatibility -------------------------------------------
    "compat.group": "Zgodność z czytnikami (opcjonalne)",
    "compat.hint": "Ustępstwa na rzecz konkretnych urządzeń:",
    "compat.hint.tip": (
        "Domyślnie żadne z nich nie jest włączone, bo wynikiem tego narzędzia jest "
        "książka zgodna ze standardem, a każde z tych ustępstw jest krokiem w bok.\n\n"
        "Wszystkie są wyłącznie dokładające: dopisują plik, deklarację albo stary "
        "element. Żadne nic nie usuwa ani nie przepisuje tego, co już w książce było, "
        "i żadne nie zmienia wyglądu na czytniku trzymającym się standardu."
    ),
    "compat.kindle": "Kindle (Amazon)",
    "compat.kindle.tip": (
        "Dokłada element <guide>, po którym konwerter Amazona odnajduje okładkę i "
        "miejsce rozpoczęcia lektury, arkusz deklarujący elementy HTML5 jako blokowe "
        "oraz starą pisownię właściwości łamania stron obok nowej.\n\n"
        "Jeśli okładka jest zawinięta w SVG, dostaniesz uwagę w raporcie: Kindle radzi "
        "sobie z tym słabo, ale rozwinięcie tego zmieniłoby układ na każdym innym "
        "czytniku, więc narzędzie tego nie rusza."
    ),
    "compat.kobo": "Kobo",
    "compat.kobo.tip": (
        "Pilnuje obecności NCX, dokłada <guide> i arkusz z blokowymi elementami HTML5.\n\n"
        "Dotyczy sytuacji, w której Kobo czyta EPUB-a wprost, a nie przekonwertowanego "
        "do KEPUB-a. To nie jest lekarstwo na czytnik, który w ogóle odmawia otwarcia "
        "pliku — taka usterka leży gdzie indziej."
    ),
    "compat.apple": "Apple Books",
    "compat.apple.tip": (
        "Dokłada plik META-INF/com.apple.ibooks.display-options.xml.\n\n"
        "Bez niego Apple Books ignoruje wszystkie osadzone kroje pisma i podstawia "
        "własny. Plik powstaje tylko wtedy, gdy książka faktycznie zawiera czcionki — "
        "w przeciwnym razie deklarowałby coś, czego nie ma."
    ),
    "compat.legacy": "Starsze czytniki (Adobe RMSDK)",
    "compat.legacy.tip": (
        "PocketBook, Nook, Sony, starsze Kobo i Onyx. Wszystkie powyższe ustępstwa "
        "naraz: NCX, <guide>, blokowe elementy HTML5 i stara pisownia łamania stron.\n\n"
        "Te czytniki renderują nieznany element jako liniowy, przez co książka "
        "zbudowana z <section> zlewa się w jeden ciągły akapit."
    ),
    "compat.note": (
        "Element <guide> nie należy już do EPUB 3.3 — EPUBCheck wciąż go akceptuje, "
        "więc plik pozostaje poprawny, ale niesie coś, co standard porzucił."
    ),

    # --- metadata overrides ---------------------------------------------
    "meta.group": "Nadpisanie metadanych (opcjonalne)",
    "meta.placeholder": "zostaw puste — użyj tego, co jest w książce",
    "meta.title": "Tytuł",
    "meta.title.tip": "Zastępuje dc:title we wszystkich przetwarzanych książkach.",
    "meta.author": "Autor",
    "meta.author.tip": (
        "Zastępuje głównego autora. Nazwisko do sortowania („Kowalski, Jan”) "
        "zostanie wyliczone automatycznie."
    ),
    "meta.language": "Język (BCP 47)",
    "meta.language.tip": (
        "Kod języka, np. „pl” albo „pl-PL”.\n\n"
        "Używany też wtedy, gdy książka w ogóle nie deklaruje języka lub "
        "deklaruje go błędnie."
    ),

    # --- actions --------------------------------------------------------
    "action.run": "Przebuduj",
    "action.run.tip": "Uruchamia przebudowę wszystkich książek z listy.",
    "action.save": "Zapisz raport…",
    "action.save.tip": "Zapisuje raport zaznaczonej książki jako plik JSON.",
    "action.save.batch": "Zapisz raport zbiorczy…",
    "action.save.batch.tip": "Jeden plik JSON z raportami wszystkich książek z kolejki, najgorsze na górze.",
    "dialog.savereport.batch": "Zapisz raport zbiorczy",
    "status.batch.saved": "Zapisano raport zbiorczy z {count} książek.",
    "menu.file": "&Plik",
    "menu.quit": "Zakończ",

    # --- report ---------------------------------------------------------
    "report.placeholder": "Zaznacz książkę na liście, aby zobaczyć, co zostało w niej zmienione.",
    "report.source": "źródło",
    "report.output": "wynik",
    "report.notwritten": "NIE ZAPISANO",

    "level.fix": "naprawiono",
    "level.preserved": "zachowano",
    "level.warn": "ostrzeżenie",
    "level.error": "błąd",
    "level.info": "informacja",

    # --- status bar and dialogs -----------------------------------------
    "status.hint": "Przeciągnij pliki EPUB w dowolne miejsce tego okna.",
    "status.hint.nocheck": "EPUBCheck niedostępny — weryfikacja wyłączona.",
    "status.queued.count": "W kolejce: {count}",
    "status.working": "Przebudowuję {name}…",
    "status.validating": "Sprawdzam {name} programem EPUBCheck…",
    "status.finished": "Zakończono {count} książek — wszystkie zapisane.",
    "status.finished.failures": "Zakończono {count} książek — {failures} nie udało się zapisać.",
    "dialog.nothing.title": "Nie ma czego przebudowywać",
    "dialog.nothing.body": "Najpierw dodaj przynajmniej jeden plik EPUB.",
    "dialog.overwrite.title": "Wynik nadpisałby oryginał",
    "dialog.overwrite.body": (
        "Wybierz inny folder wyjściowy — plik {name} zostałby nadpisany w miejscu."
    ),
    "dialog.noreport.title": "Brak raportu",
    "dialog.noreport.body": "Najpierw przebuduj książkę, a potem zaznacz ją na liście.",
    "dialog.filter": "Pliki EPUB (*.epub)",
    "dialog.selectfiles": "Wybierz pliki EPUB",
    "dialog.selectfolder": "Wybierz folder wyjściowy",
    "dialog.savereport": "Zapisz raport",

    # --- settings and about ---------------------------------------------
    "menu.settings": "&Ustawienia",
    "menu.language": "Język interfejsu",
    "menu.help": "&Pomoc",
    "menu.about": "O programie",
    "language.pl": "Polski",
    "language.en": "English",
    "about.title": "O programie EPUB F.O.R.G.E.",
    "about.subtitle": "Fabryka Odbudowy i Renowacji Glitchujących EPUB-ów",
    "about.tagline": "Przekuwa wadliwe ebooki w czysty EPUB 3.3 — bez psucia tego, jak wyglądają.",
    "about.version": "Wersja {version}",
    "about.authors": "Autorzy",
    "about.author.human": "Łukasz „LuKi” Kniotek — pomysł, kierunek i wymagania",
    "about.author.ai": "Claude (Anthropic) — projekt i implementacja",
    "about.license": "Licencja",
    "about.license.body": (
        "GNU GPL v3 lub późniejsza. Wolno używać, badać i zmieniać; to, co z tego "
        "powstanie, też musi być na GPL i z otwartym źródłem. Bez żadnej gwarancji.\n\n"
        "Program korzysta z bibliotek na LGPL (Qt/PySide6, cssutils) i z EPUBCheck-a "
        "na licencji BSD. Kod źródłowy dostępny na GitHubie."
    ),
    "about.components": "Dołączone komponenty",
    "about.components.body": (
        "EPUBCheck (W3C) — licencja BSD 3-Clause\n"
        "Środowisko OpenJDK zbudowane jlinkiem — GPLv2 z wyjątkiem Classpath\n"
        "Qt przez PySide6 — LGPLv3, biblioteki dołączone jako wymienialne pliki"
    ),
    "about.close": "Zamknij",
}

EN: dict[str, str] = {
    "window.title": "EPUB F.O.R.G.E. {version}",
    "toolbar.add": "Add books…",
    "toolbar.add.tip": "Pick EPUB files to rebuild.\n\nYou can also drop them anywhere in this window.",
    "toolbar.clear": "Clear list",
    "toolbar.clear.tip": "Empties the list. No files are deleted from disk.",
    "toolbar.output": "Output folder:",
    "toolbar.output.placeholder": "empty — write next to the source as *.forged.epub",
    "toolbar.output.tip": (
        "Where rebuilt books are written.\n\nLeft empty, each file is written beside its "
        "original with a .forged.epub suffix. The source is never overwritten."
    ),
    "toolbar.browse": "Browse…",
    "toolbar.browse.tip": "Choose the folder for the finished files.",
    "table.book": "Book",
    "table.status": "Status",
    "table.fixed": "Fixed",
    "table.fixed.tip": "Defects the tool corrected.",
    "table.kept": "Kept",
    "table.kept.tip": (
        "Deviations left in place on purpose, because removing them would change how the "
        "book looks. See the report below."
    ),
    "table.issues": "Issues",
    "table.issues.tip": "Warnings and errors that could not be fixed automatically.",
    "status.queued": "queued",
    "status.done": "done",
    "status.issues": "done with issues",
    "status.failed": "failed",
    "status.blocked": "refused",
    "policy.group": "Rebuild policy",
    "policy.mode.label": "When conformance and appearance conflict:",
    "policy.mode.tip": (
        "Every mode builds the book anew: package, navigation, filenames, ZIP "
        "layout. That is how this tool works — it does not patch a file, it reads "
        "the book and assembles a correct container.\n\n"
        "This choice is only about what to do with the *content* in disputed "
        "cases — reader-specific CSS hacks, or links to files the book never "
        "contained."
    ),
    "policy.mode.preserve": "Preserve appearance, report deviations",
    "policy.mode.strict": "Enforce the standard, even if rendering changes",
    "policy.mode.minimal": "Rebuild the container only, leave content alone",
    "policy.mode.preserve.tip": (
        "The default. The book looks exactly as before. Clear publisher errors are repaired, "
        "but things that merely deviate from the spec while working are kept and reported."
    ),
    "policy.mode.strict.tip": (
        "Full EPUB 3.3 conformance even if something shifts. Dead links lose their href, "
        "Kindle-only CSS and Adobe properties are removed. Passes EPUBCheck cleanly."
    ),
    "policy.mode.minimal.tip": (
        "Regenerates only the OPF, navigation and ZIP structure. XHTML and CSS pass through "
        "byte for byte."
    ),
    "policy.ncx": "Include a legacy NCX for older readers",
    "policy.ncx.tip": (
        "Adds the EPUB 2 table of contents alongside the new one. Costs a few kilobytes and "
        "makes the toc work on old devices. Recommended."
    ),
    "policy.orphans": "Remove files nothing references",
    "policy.orphans.tip": (
        "OFF by default, and best left that way.\n\n"
        "Deletes resources no chapter, stylesheet or table of contents points "
        "at. The three holes that made it delete files in use — srcset, "
        "<picture>, and links made from inside an SVG — are closed. The graph is "
        "**better and not complete**: a script that builds a filename from two "
        "strings, a stylesheet reached only through a media query nothing here "
        "evaluates, a reference in a format nothing here models.\n\n"
        "The saving is a few kilobytes. The risk is a hole where a picture was."
    ),
    "policy.layout": "Reorganise files into typed folders",
    "policy.layout.tip": (
        "Moves content to EPUB/text, styles to EPUB/styles and so on, folding names to safe "
        "ASCII. Every reference is rewritten. Some readers choke on non-ASCII filenames."
    ),
    "policy.watermark.label": "Bookshop watermark:",
    "policy.watermark.tip": (
        "Shops stamp each purchased file with a token. That is their right and "
        "the token is not the problem — where it sits is.\n\n"
        "It usually sits at the end of every chapter at 1px or 0px, where it is "
        "still laid out, still paginates, and is still read aloud by a reader's "
        "own text-to-speech."
    ),
    "policy.watermark.keep": "Leave it exactly as found",
    "policy.watermark.keep.tip": (
        "The markup comes out byte for byte as it went in. The report still "
        "counts what is there."
    ),
    "policy.watermark.consolidate": "Keep it in the text, tidy the styling",
    "policy.watermark.consolidate.tip": (
        "The token stays where it is. The !important inline style repeated in "
        "every document becomes one rule and the element gets aria-hidden.\n\n"
        "Note: aria-hidden binds screen readers. It does not bind the "
        "text-to-speech engine inside an e-reader, which reads what is on the "
        "page."
    ),
    "policy.watermark.gather": "Move it into document metadata",
    "policy.watermark.gather.tip": (
        "The token leaves the text and lands in the <head> of the same document "
        "as a <meta>.\n\n"
        "Nothing renders it, nothing speaks it, nothing paginates around it — "
        "and the shop finds it where it left it. Nothing leaves the file, but "
        "it does leave the reading order, so it is your choice rather than the "
        "default."
    ),
    "policy.watermark.remove": "Delete the token",
    "policy.watermark.remove.tip": (
        "Gone. The book stops carrying the mark that ties this copy to its "
        "buyer.\n\n"
        "The only option that loses anything, which is why you have to pick it "
        "yourself. No mode turns it on."
    ),
    # --- diagnostics panel ----------------------------------------------
    "tab.diagnostics": "Diagnostics",
    "diagnostics.intro": (
        "Two questions about files that need nothing rebuilt to answer: what is "
        "inside, and whether a validator accepts it. Nothing here changes a file."
    ),
    "diagnostics.fidelity": "Would a rebuild keep this book",
    "diagnostics.fidelity.tip": (
        "Rebuilds the book into a temporary folder and compares it with the "
        "source — nothing is written anywhere you will find it.\n\n"
        "It checks what a validator has no opinion about: whether every word of "
        "the source is in the result, whether the count of headings, pictures "
        "and paragraphs still matches, whether every image and font came "
        "through byte for byte, and whether the documents are in the same "
        "order.\n\n"
        "\"A valid file\" and \"the same book\" are two different questions. "
        "This is the second one."
    ),
    "diagnostics.shared": "One validator process for the whole batch",
    "diagnostics.shared.tip": (
        "EPUBCheck compiles its schemas every time it starts, and that takes "
        "about three and a half seconds whether the book is 2 kB or 23 MB. A "
        "process per book pays that cost again for every book.\n\n"
        "Measured on eight real books: 35.3 s with a process per book, 8.4 s "
        "through one held open. The answers are identical — the driver checks "
        "nothing itself, it calls EPUBCheck exactly as the command line does.\n\n"
        "Uncheck it to compare against the behaviour from before this change. "
        "If anything goes wrong the program falls back to a separate process "
        "anyway, and says in the report why."
    ),
    "report.changes": "Balance of changes: {total}, of which irreversible: {irreversible}",
    "merge.title": "Merge two damaged copies",
    "merge.intro": (
        "Two copies of one book, each broken somewhere the other is not, and "
        "one whole book out of them. Every file is taken entire, byte for byte, "
        "from a copy that gives it up cleanly. Nothing is reconstructed and "
        "nothing is averaged.\n\n"
        "The first in the list is the one being repaired; the rest are donors. "
        "Nothing is written until you have seen the plan and pressed Write."
    ),
    "merge.add": "Add copies…",
    "merge.remove": "Remove from list",
    "merge.examine": "Examine and show the plan",
    "merge.output": "Write to:",
    "merge.write": "Write the merged book",
    "merge.empty": "Add at least two copies and press \"Examine and show the plan\".",
    "merge.needs.two": "A merge needs at least two copies.",
    "merge.refused": "Cannot merge: {reason}",
    "merge.plan.header": "Plan — {count} entries, repairing: {first}",
    "merge.plan.nothing": "(the first copy has everything — nothing to repair)",
    "merge.plan.missing": "no copy has it",
    "merge.plan.conflict": "the copies differ and both are intact — not choosing for you",
    "merge.plan.ready": "Ready to write. Recovered from another copy: {count}.",
    "merge.plan.unusable": (
        "Nothing will be written. A merge only makes sense when every entry can "
        "be taken whole from one of the copies."
    ),
    "merge.plan.needs.output": "Say where to write the result.",
    "merge.written": "Wrote {path} — {count} entries.",
    "menu.merge": "Merge damaged copies…",
    "diagnostics.render": "Does it still look the same after rebuilding",
    "diagnostics.render.tip": (
        "Draws the book's pages before and after the rebuild and compares the "
        "images. It is the only check in this program that looks at how a page "
        "*looks* — every other one reads the file.\n\n"
        "Only **loss** counts as a defect: a page that came out blank, or one "
        "with materially less on it than the source had. A change that leaves as "
        "much or more is listed and held against nobody — a rebuild that fits an "
        "oversized cover to the page changes a fifth of the pixels and repairs "
        "the book.\n\n"
        "Needs a Chromium-based browser. It is not installed with the program, "
        "because rebuilding a book draws nothing; if there is none, this check "
        "says what it looked for and how to point it at one."
    ),
    "diagnostics.health": "Are these files whole",
    "diagnostics.health.tip": (
        "Unpacks every file inside the book and says which ones the archive "
        "will not give up. It is the only way to find out: a ZIP's table of "
        "contents sits at the end of the file, and an interrupted download can "
        "leave it perfectly intact — so the book looks complete until somebody "
        "tries to unpack it.\n\n"
        "Worth running on the day the books arrive. A damaged file is repaired "
        "by downloading it again, which is easy today and sometimes impossible "
        "in two years, when the title has left the shop."
    ),
    "diagnostics.files": "File or folder:",
    "diagnostics.mode": "Question:",
    "diagnostics.inspect": "What is in this file",
    "diagnostics.inspect.tip": (
        "Reads the book and prints what it found: version, metadata, resource "
        "count, reading order, cover, navigation, obfuscated fonts and DRM.\n\n"
        "This is the view *before* a rebuild — what the tool is dealing with, "
        "not what it would make of it."
    ),
    "diagnostics.validate": "Does EPUBCheck accept it",
    "diagnostics.validate.tip": (
        "Runs the validator against the file as it is, with no rebuild.\n\n"
        "Useful for two things: finding out whether a book was broken *before* "
        "anything touched it, and checking a finished result."
    ),
    "diagnostics.empty": "Pick a file or a folder of books and press Run.",
    "policy.fonts": "Undo font obfuscation",
    "policy.fonts.tip": (
        "Some shops \u201cobfuscate\u201d embedded fonts — they scramble the "
        "first bytes of the file so it cannot simply be lifted out and "
        "installed. A reading system undoes it on the fly, so nothing on screen "
        "changes either way.\n\n"
        "On: the font comes out ordinary and the encryption declaration goes. "
        "Off: it stays as it was. This does not affect how the book looks — it "
        "affects whether the font file opens in anything else."
    ),
    "policy.images": "Transcode images in formats outside the standard",
    "policy.images.tip": (
        "BMP and TIFF render on some reading systems and not others, so they "
        "become PNG. WebP does **not** — it is a core media type in EPUB 3.3 "
        "and needs nothing doing to it.\n\n"
        "A multi-frame image is never transcoded whatever this says: converting "
        "it would keep the first frame and silently drop the rest."
    ),
    "policy.incomplete": "Rebuild even when part of the source could not be read",
    "policy.incomplete.tip": (
        "Normally, when an archive entry cannot be read — because it is "
        "monstrous, or its stream is damaged — the rebuild **stops and writes "
        "nothing**. A book this program cannot see all of cannot be given the "
        "promise that none of it was lost.\n\n"
        "This box is the way through for a person holding that book who knows "
        "what they are doing. Ticked: the file is written anyway and the report "
        "says what is not in it. It does not make the loss quiet."
    ),
    "policy.gate": "Before publishing, ask EPUBCheck:",
    "policy.gate.tip": (
        "Whether the result is checked by the validator **before** it takes its "
        "name, rather than after.\n\n"
        "The check runs on the staging file, immediately before the swap, so a "
        "refusal never touches whatever is already at that name. That is the "
        "whole reason the gate lives here and not in a \"validate it and delete "
        "it if bad\" step: deleting after the swap would destroy the previous, "
        "good book.\n\n"
        "It follows the mode by default, and you can override it."
    ),
    "policy.gate.off": "do not ask — publish and report",
    "policy.gate.off.tip": (
        "How this program has always worked. Validation is still available on "
        "its own, in the Diagnostics tab and under \"check the result\", and "
        "nothing blocks.\n\n"
        "The default for preserve and minimal, because books arrive with "
        "defects and this program is here to carry them, not to refuse them."
    ),
    "policy.gate.no-new-errors": "publish unless this rebuild added an error",
    "policy.gate.no-new-errors.tip": (
        "Validates the source as well, and compares. A book that arrived broken "
        "comes out broken with the report saying so; a book this program broke "
        "does not come out at all.\n\n"
        "Mind what it compares: a 2.0 source is judged by EPUB 2 rules and a 3.3 "
        "rebuild by EPUB 3 rules, so \"new\" can also mean \"EPUB 3 has a rule "
        "EPUB 2 did not\". The report names the source's version beside the "
        "refusal so that difference is visible rather than inferred."
    ),
    "policy.gate.clean": "publish only a file EPUBCheck accepts",
    "policy.gate.clean.tip": (
        "The literal invariant: no errors before publication, whoever made "
        "them. The default in strict — a strict mode that publishes an invalid "
        "file is not strict.\n\n"
        "It will refuse books this program did nothing wrong to: ones that "
        "arrived invalid and cannot be repaired without guessing. On the public "
        "corpus that is three books out of twelve.\n\n"
        "With no validator present this gate **refuses**. A claim nobody "
        "checked is not a claim."
    ),
    "decide.title": "Decision",
    "decide.value": "type your own form",
    "decide.irreversible": "This cannot be undone from the output file alone.",
    "decide.all": "The same for every case like this in this book",
    "decide.all.tip": (
        "Only cases carrying the same strength of evidence. The option where you "
        "type your own form never covers a group — that is a statement about one "
        "word, not about all of them."
    ),
    "policy.render": "Check the appearance after rebuilding",
    "policy.render.tip": (
        "Draws the book's pages before and after the rebuild and compares the "
        "images. It is the only check that looks at how a page *looks* — every "
        "other one reads the file.\n\n"
        "It asks three things and only three: did a document vanish from the "
        "reading order, did a page come out blank, and did both the content and "
        "the area it occupies shrink. It has no opinion about a different font "
        "or about lines wrapping differently.\n\n"
        "Reflow does not move it. Measured: after joining 46 hyphens in one "
        "book, 7 of 130 page comparisons moved at all, the largest by 1.64% of "
        "pixels, and nothing lost content.\n\n"
        "Needs a Chromium-based browser. It is not installed with the program; "
        "without one the check does not run and the report says so plainly."
    ),
    "policy.render.gate": "When a page loses content:",
    "policy.render.gate.off": "do not check the appearance at all",
    "policy.render.gate.off.tip": (
        "The check does not run during a rebuild. The separate question in "
        "Diagnostics and the `render-check` command remain, run by hand."
    ),
    "policy.render.gate.report": "write the file and say so in the report",
    "policy.render.gate.report.tip": (
        "The loss goes into the report, the before/after pictures land beside "
        "the book, and the file is written. You decide afterwards."
    ),
    "policy.render.gate.stop": "do not write the file",
    "policy.render.gate.stop.tip": (
        "On a detected loss nothing is written, and whatever was at that name is "
        "left untouched. The before/after pictures are saved beside it so you "
        "can see what it means.\n\n"
        "Measured before this became the default: 0 refusals across 32 books."
    ),
    "policy.text.invariant": "Check that no text went missing (K1)",
    "policy.text.invariant.tip":
        "Before the file takes its name, compares the source's text with the "
        "output's: every character of the reading order has to be there, in the "
        "same order. Spacing, quotes and dashes are folded, because the rebuild "
        "changes those on purpose. Removing a watermark and joining a word a "
        "conversion cut in half are the exceptions — both happen at your request "
        "and both are named in the report.",
    "policy.render.all": "Draw every page, not a sample",
    "policy.render.unverified": "Write the book even when the appearance check cannot run",
    "policy.metadata.reconstructed": "Accept metadata read out of a damaged package",
    "policy.hyphen.review": "Hyphenated words the book does not settle:",
    "policy.hyphen.review.tip": (
        "The program asks about a hyphenated word when the same book writes it "
        "without a hyphen somewhere else — that is evidence the hyphen is left "
        "over from a conversion. For the rest there is no evidence.\n\n"
        "Measured over 32 books: 67 with evidence, 101 'likely' and 88 "
        "'uncertain', and in those two lists nearly every entry is a real "
        "compound — `marksizm-leninizm`, `savoir-vivre`, `ping-pong`."
    ),
    "policy.hyphen.review.confirmed": "ask only about the evidenced ones",
    "policy.hyphen.review.confirmed.tip": (
        "The rest are counted, shown in the report, and left alone."
    ),
    "policy.hyphen.review.grouped": "show the rest as one question per class",
    "policy.hyphen.review.grouped.tip": (
        "One question per confidence class, carrying the words. 189 candidates "
        "become one decision instead of 189."
    ),
    "policy.hyphen.review.each": "ask about every one separately",
    "policy.hyphen.review.each.tip": (
        "For going through them properly. On a large book that can be a "
        "hundred and something questions."
    ),
    "policy.metadata.reconstructed.tip": (
        "When a book's package only parses after recovery, the title, author and "
        "language are the parser's reading of somebody else's book rather than what "
        "the publisher wrote — it can produce `ORIGINALpl`, a string nobody ever "
        "typed.\n\n"
        "Unticked: the rebuild asks about each such field and writes nothing without "
        "an answer. Ticked: it writes what it read and the report says where it came "
        "from."
    ),
    "policy.render.unverified.tip": (
        "A different question from the one above. That one says what to do when the "
        "appearance check RUNS and finds a page that lost content. This says what to "
        "do when the check CANNOT RUN at all — because this machine has no browser.\n\n"
        "Unticked: the rebuild asks before writing anything, and without an answer it "
        "writes nothing. Ticked: it writes, and the report says the appearance was not "
        "checked — consent given in advance, for a batch nobody is sitting in front of."
    ),
    "policy.render.all.tip": (
        "By default 12 pages are drawn: the first three always, because the "
        "cover and title pages are where images crop and stretch, and the rest "
        "spread across the book. About 36 seconds per book.\n\n"
        "Ticked, every page is drawn. For a 65-chapter book that is several "
        "minutes, but then nothing is inferred from a sample."
    ),
    "policy.repair.encoding": "Restore punctuation a conversion lost",
    "policy.repair.encoding.tip": (
        "Windows keeps quotation marks, dashes and ellipses on the positions "
        "Unicode reserves for control codes. A converter reading such text "
        "with the wrong encoding turns every one of them into a code with no "
        "shape — no font draws it, so a reading system shows a blank.\n\n"
        "Off, the program **asks** for every book it finds this in, and shows "
        "how many characters and which ones.\n\n"
        "On, it answers “repair” on your behalf, for the whole queue. Useful "
        "across many books at once; the mapping is one-to-one and nothing "
        "about it is guessed.\n\n"
        "**This changes the text** and cannot be undone from the output alone, "
        "which is why asking is the default."
    ),
    "policy.shop.notices": "Remove the shop's visible traces",
    "policy.shop.notices.tip": (
        "Some shops stamp a sentence about the purchase into the text: an "
        "order number, the buyer's name, an e-mail address, “purchased "
        "for…”. In one of your books it sits **in the running text, directly "
        "in front of the novel's first sentence**.\n\n"
        "On, those sentences are removed, and the report prints **every one of "
        "them word for word** rather than a count. This is the only setting in "
        "the program that deletes text a reader can see, so you are meant to "
        "check that it took the shop's sentence and not your book's.\n\n"
        "Only sentences naming **the sale** are taken — an order, a purchase, a "
        "licence, a buyer. **A publisher's colophon** (address, telephone, "
        "ISBN) names the publisher rather than the transaction and is never "
        "touched. **No page is ever removed** — an element left empty stays, "
        "and the balance reports it.\n\n"
        "Separate from “watermarks” above: that one asks how visible a hidden "
        "marker may be, this one asks whether a sentence may be deleted."
    ),
    "policy.relative.units": "Free font sizes from pixels",
    "policy.relative.units.tip": (
        "A book that writes `font-size: 12px` has taken the size control away "
        "from the person reading it: on a device set to larger text, that "
        "passage stays twelve pixels. It is the most common piece of "
        "print-era formatting on your shelf.\n\n"
        "On, sizes given in px and pt are rewritten in **rem** — a measure "
        "taken from the reading device's own setting. At the default setting "
        "the page is **identical** to the pixel; away from it the whole book "
        "scales together, keeping the proportions between the sizes the "
        "publisher chose.\n\n"
        "**Off** by default, and not out of caution about the arithmetic: this "
        "rewrites a stylesheet somebody wrote. Away from the default setting "
        "the book deliberately stops looking the same — that is the point — so "
        "it is a decision rather than a repair.\n\n"
        "The report gives the number of such sizes in every file whether or "
        "not this is switched on."
    ),
    "policy.hyphens": "Look for hyphens left inside words",
    "policy.hyphens.tip": (
        "A bad PDF conversion leaves the line-break hyphen in the text: "
        "„obo-jętna”, „ko-rytarz”, „Ce-laena”. The reader sees them, they are "
        "wrong, and no rule in this program could previously see them at all.\n\n"
        "This switch turns on **detection**. Nothing is joined without your "
        "answer — there is no setting that makes this act on its own, which is "
        "why detection can be on by default.\n\n"
        "You are asked only where the evidence is in the book itself: the same "
        "book spells that word without a hyphen. Measured across 32 books: 67 "
        "of those against 189 suspicions with no evidence, nearly all of which "
        "are real words — „marksizm-leninizm”, „savoir-vivre”, „ping-pong”. It "
        "does not ask about those."
    ),
    "policy.remember": "Remember my answers about this book",
    "policy.remember.tip": (
        "Answers are saved beside the book, in „<name>.decyzje.json”, and the "
        "next rebuild asks only what it does not already know.\n\n"
        "If the book file has changed, the store is refused outright and the "
        "report says so. Replaying somebody's decision onto a page they have not "
        "seen is worse than asking a second time."
    ),
    "policy.memory": "Refuse books this machine has no memory for",
    "policy.memory.limit.placeholder": "memory budget, e.g. 4G — empty means \"ask the system\"",
    "policy.memory.limit.tip": (
        "A fixed budget instead of asking how much memory happens to be free. "
        "Useful when you are working while a batch runs: free memory then moves "
        "with every window you open, and a threshold that moves refuses one book "
        "and not the next for no reason you can see.\n\n"
        "Written the way you would say it: 4G, 512M, 1500000. Empty means \"ask "
        "the system and leave a fifth spare\"."
    ),
    "policy.memory.tip": (
        "Before a book is opened its memory cost is estimated, and when it "
        "exceeds what the system reports as free the rebuild is refused with a "
        "report instead of being killed halfway.\n\n"
        "Where this came from: the reader has held a 2 GiB content ceiling for a "
        "long time. Measured across six books, text costs twelve times its own "
        "size once parsed — an XHTML document does not stay a string, it becomes "
        "an element tree. So a 2 GiB content ceiling is a promise the process may "
        "reach twenty-four gigabytes. A machine with 2 GiB free dies at around "
        "160 MB of text, and dies by being killed: no report, no diagnosis, no "
        "file and nothing a person can act on.\n\n"
        "The estimate is a model built from six books and is deliberately 15% "
        "pessimistic. Untick it if you know something it does not — that nothing "
        "else is running, that there is swap, that this book is unlike those six."
    ),
    "policy.reproducible": "Reproducible build (the same bytes every time)",
    "policy.reproducible.tip": (
        "Two rebuilds of one book produce a byte-for-byte identical file. "
        "Useful for comparing two builds, or for checking that what you have "
        "is what this source actually produces.\n\n"
        "It changes two things. `dcterms:modified` comes from the source rather "
        "than the clock — and where the source carries no date at all, the "
        "epoch (1970) is stamped, because inventing a plausible-looking date "
        "would be making up a fact about somebody's book. A book with no "
        "identifier of its own gets one **derived from its content** instead of "
        "a random one: the same file always the same, two different books never "
        "the same.\n\n"
        "Off by default, because the honest modification date of a file made a "
        "moment ago is a moment ago."
    ),
    "policy.junk": "Remove packaging leftovers",
    "policy.junk.tip": (
        "`.DS_Store`, `Thumbs.db`, `__MACOSX/`, `._` shadows, "
        "`iTunesMetadata.plist`, `calibre_bookmarks.txt`, `.bak` — what the "
        "archive picked up on its way out of somebody's machine, and what has "
        "no business in a publication.\n\n"
        "Removed **only where the book does not refer to them**. A name is not "
        "evidence about content: `chapter.bak` is a name a publisher can give a "
        "file that is in the manifest with the navigation pointing at it. "
        "Anything the book reaches is kept, and the report says so.\n\n"
        "Unticked: nothing is removed, whatever it is called."
    ),
    "policy.ask": "Ask me about references that cannot be resolved",
    "policy.ask.tip": (
        "A link can name an anchor the target document does not have — usually "
        "after a PDF conversion, where only some of the notes were given an "
        "identifier. This program **will not guess** where such a link was "
        "meant to lead: removing the fragment would silence the validator and "
        "send the reader from footnote seventeen to footnote one.\n\n"
        "Ticked: each one comes to you in a window with the link's own text and "
        "the anchors the target document really has, and you decide. One answer "
        "can cover the whole book.\n\n"
        "Unticked: the reference is left exactly as the publisher wrote it and "
        "the report lists them. In strict mode a book carrying them is not "
        "written at all."
    ),
    "ask.title": "Where does this link lead?",
    "ask.explanation": (
        "This link names an anchor the target document does not have. The "
        "program does not know where it was meant to lead, and will not guess "
        "on your behalf."
    ),
    "ask.facts": (
        "Document: {document}\n"
        "Reference: {reference}\n"
        "Link text: {text}"
    ),
    "ask.no-text": "(no text)",
    "ask.keep": "Leave it as the publisher wrote it",
    "ask.keep.tip": (
        "The reference is untouched. A reader will see that the link is broken "
        "— which is honester than a link that quietly arrives somewhere wrong. "
        "The report lists every one of them."
    ),
    "ask.repoint": "Point it at this anchor:",
    "ask.repoint.tip": (
        "The identifiers the target document really has. The chosen anchor goes "
        "into the link, and the report records that a person chose it rather "
        "than the program."
    ),
    "ask.document": "Send it to the top of the target document",
    "ask.document.tip": (
        "The fragment goes and the link lands at the start of the file. The "
        "program will never do this by itself — for a footnote it means "
        "arriving at footnote one instead of seventeen. Choose it when you know "
        "that is right for this book."
    ),
    "ask.all": "Apply this answer to every remaining one in this book",
    "ask.all.tip": (
        "A conversion can leave two hundred of these. It applies only to "
        "answers that mean the same thing everywhere — pointing at one "
        "particular anchor cannot be applied to a whole book, because every "
        "link would then lead to the same place."
    ),
    "policy.typography": "Repair the text's typography",
    "policy.typography.tip": (
        "The only place this tool changes the text itself rather than the markup "
        "around it. That is why it is off, and why no mode turns it on.\n\n"
        "Three dots become an ellipsis, and in Polish books single-letter "
        "conjunctions (a i o u w z) get a hard space so they do not end a line."
        "\n\nAfter each document it checks its own work: if it cannot show it "
        "kept the text word for word, the document goes back unchanged and the "
        "report says so."
    ),
    "policy.scripts": "Remove JavaScript",
    "policy.dead": "Remove what does nothing",
    "policy.dead.tip": (
        "CSS rules for markup the book does not contain, and <span> elements "
        "whose rules change nothing.\n\n"
        "None of it moves a pixel — but removal is removal, so it is under your "
        "hand. Ticked by \"Force the standard\"; unticking works there too.\n\n"
        "Off: the report still says how much there is and where."
    ),
    "policy.scripts.tip": (
        "Strips <script> elements and event attributes. Off by default: some fixed-layout "
        "books need scripting to render correctly."
    ),
    "policy.validate": "Verify the result with EPUBCheck",
    "policy.validate.tip": (
        "Runs the official W3C validator on the finished file and adds its verdict to the "
        "report. Adds a few seconds per book."
    ),
    "policy.validate.missing": (
        "EPUBCheck was not found.\n\nThe installed build bundles it. Running from source, "
        "point EPUBCHECK_JAR at epubcheck.jar."
    ),
    "tab.rebuild": "Rebuild",
    "tab.library": "Library",
    "tab.corpus": "Corpus",
    "common.folder": "Folder:",
    "common.browse": "Browse…",
    "common.run": "Run",
    "common.stop": "Stop",
    "common.save": "Save result…",
    "common.saved": "Saved: {path}",
    "common.pickfolder": "Choose a folder",
    "common.nofolder": "Point at a folder of books first.",
    "common.working": "Working: {name}",
    "common.done": "Done — {count} book(s)",

    "library.intro": (
        "Two different questions about a whole library. Nothing is written beside your "
        "books and nothing changes them."
    ),
    "library.mode": "What to measure:",
    "library.survey": "Survey — what the tool repairs, and how often",
    "library.survey.tip": (
        "Runs every book through the full pipeline and counts the findings.\n\n"
        "It answers \"what breaks most often\", not \"what is in this one book\". A rule "
        "written from a single file is a guess; the same defect in forty files is a "
        "fact.\n\nNothing is written anywhere except the file you choose."
    ),
    "library.inventory": "Inventory — what the books are made of",
    "library.inventory.tip": (
        "Measures provenance (traces of Calibre, InDesign, Word, a PDF conversion), "
        "damage (class explosion, span soup, dead CSS) and typography (quotes, dashes, "
        "ellipses, mojibake).\n\n"
        "A survey can only name defects the tool already knows about, so it never "
        "surprises anybody. An inventory says what it cannot yet see."
    ),
    "library.withnames": "Include filenames in the result",
    "library.withnames.tip": (
        "Off by default. The result is meant to be shareable, and a list of titles says "
        "more about your shelf than about the tool.\n\n"
        "Turn on if you need to find the book behind a number."
    ),
    "library.empty": "Point at a folder of e-books and press Run.",
    "survey.books": "{count} book(s)",
    "survey.versions": "source versions: {versions}",
    "survey.unreadable": "unreadable",
    "survey.crashed": "stage failures",
    "survey.drm": "with DRM (refused): {count}",
    "survey.head.books": "books",
    "survey.head.total": "total",
    "survey.head.level": "level",
    "survey.head.stage": "stage",
    "survey.head.finding": "finding",

    "corpus.intro": (
        "A safety net for this program, not for your files.\n\n"
        "For each book it records what the rebuild did to it — counts only, plus a "
        "hash of the result. When a rule changes tomorrow and that change breaks one "
        "of your books, this notices — even though nobody ever handed the books over. "
        "\"Different\" therefore means: rebuilt differently than last time. Your file "
        "on disk is untouched."
    ),
    "corpus.books": "Books:",
    "corpus.signatures": "Signatures:",
    "corpus.signatures.placeholder": "empty — an \"expected\" folder beside the books",
    "corpus.check": "Check",
    "corpus.check.tip": "Compares each book with its signature and lists what differs. Overwrites nothing.",
    "corpus.record": "Record signatures",
    "corpus.record.tip": (
        "Writes this run's signatures as the new baseline — showing first what moved.\n\n"
        "Do this when the change in the tool was intended."
    ),
    "corpus.what": (
        "A signature holds: how many findings, whether the text survived, the block "
        "count, the EPUBCheck verdict and a hash of the output. No title, no author, "
        "not a word of the text."
    ),
    "corpus.empty": "Point at a folder of books and press Check.",
    "corpus.status.unchanged": "unchanged",
    "corpus.status.changed": "different result",
    "corpus.status.new": "new",
    "corpus.status.failed": "failed",
    "corpus.status.duplicate": "same file",
    "corpus.edges": "Add the edge cases",
    "corpus.edges.tip": (
        "Writes four books into the folder that nobody can buy: no cover, one 9 MB "
        "image, 400 spine items, the whole book in one document.\n\n"
        "The roadmap calls them the pathological family — memory and performance "
        "failures surface there and nowhere else. Run twice, it leaves four files, "
        "not eight."
    ),
    "corpus.edges.done": "Wrote {count} edge case(s):",
    "corpus.edges.working": "building the edge cases…",
    "corpus.fixtures": "Fixture books",
    "corpus.fixtures.tip": (
        "Three audit findings can only be closed against two particular purchased "
        "books; no synthetic file stands in for them. The audit called them "
        "mandatory, then recorded all three as blocked for want of the files — "
        "without saying anywhere which files it meant.\n\n"
        "This says which. It checks the chosen folder and lists what is missing "
        "along with what that book has to contain. Nothing is copied; the "
        "repository gets a digest and a few counts, never a title or a word of text."
    ),
    "corpus.fixtures.assign": "Assign a fixture book…",
    "corpus.fixtures.assign.tip": (
        "Point at the file that fills a role. Needed when your edition differs from "
        "the recorded one: a role is matched by digest and by nothing else, because "
        "matching on resemblance once handed a completely different novel to a role."
    ),
    "corpus.fixtures.role": "Which role?",
    "corpus.fixtures.done": "Assigned {role} ← {name}",
    "corpus.fixtures.present": "present",
    "corpus.fixtures.missing": "missing",
    "corpus.fixtures.needed": "needed for: {findings}",
    "corpus.fixtures.similar": "similar on the shelf: {name}",
    "corpus.fixtures.working": "looking for the fixture books…",
    "corpus.streak": "Green releases in a row: {count} ({releases}).",
    "corpus.streak.none": "Green releases in a row: none — the last run was not clean.",
    "corpus.streak.widened": "Passed over as a widening of the measurement: {releases}.",

    "compat.group": "Reader compatibility (optional)",
    "compat.hint": "Concessions to particular devices:",
    "compat.hint.tip": (
        "All off by default, because the product of this tool is a standards-clean "
        "book and each of these steps away from it.\n\n"
        "Every one is additive: it adds a file, a declaration or a legacy element. "
        "None removes or rewrites what the book already had, and none changes how a "
        "reader that follows the specification renders it."
    ),
    "compat.kindle": "Kindle (Amazon)",
    "compat.kindle.tip": (
        "Adds the <guide> element Amazon's converter uses to find the cover and the "
        "start-reading position, a stylesheet declaring the HTML5 sectioning elements "
        "as blocks, and the legacy spelling of the page-break properties beside the "
        "modern one.\n\n"
        "If the cover is wrapped in SVG you get a note in the report: Kindle handles "
        "that poorly, but unwrapping it would change the layout on every other reader, "
        "so the tool leaves it alone."
    ),
    "compat.kobo": "Kobo",
    "compat.kobo.tip": (
        "Insists on the NCX, adds <guide> and the HTML5 block stylesheet.\n\n"
        "For Kobo reading the EPUB directly rather than a converted KEPUB. It is not a "
        "cure for a device that refuses to open a file at all — that fault lies "
        "elsewhere."
    ),
    "compat.apple": "Apple Books",
    "compat.apple.tip": (
        "Adds META-INF/com.apple.ibooks.display-options.xml.\n\n"
        "Without it Apple Books ignores every embedded face and substitutes its own. "
        "Written only when the book actually embeds fonts — otherwise it would declare "
        "something that is not there."
    ),
    "compat.legacy": "Older readers (Adobe RMSDK)",
    "compat.legacy.tip": (
        "PocketBook, Nook, Sony, older Kobo and Onyx. Everything above at once: NCX, "
        "<guide>, HTML5 block declarations and the legacy page-break spelling.\n\n"
        "These renderers treat an element they do not know as inline, which collapses "
        "a book built from <section> into one running paragraph."
    ),
    "compat.note": (
        "<guide> is no longer part of EPUB 3.3. EPUBCheck still accepts it, so the file "
        "stays valid, but it carries something the specification dropped."
    ),

    "meta.group": "Metadata overrides (optional)",
    "meta.placeholder": "leave empty — keep what the book has",
    "meta.title": "Title",
    "meta.title.tip": "Replaces dc:title in every book processed.",
    "meta.author": "Author",
    "meta.author.tip": "Replaces the main author. The sort name is derived automatically.",
    "meta.language": "Language (BCP 47)",
    "meta.language.tip": (
        "A tag such as \"pl\" or \"pl-PL\". Also used when the book declares no language, "
        "or an invalid one."
    ),
    "action.run": "Rebuild",
    "action.run.tip": "Rebuilds every book in the list.",
    "action.save": "Save report…",
    "action.save.tip": "Writes the selected book's report as JSON.",
    "action.save.batch": "Save batch report…",
    "action.save.batch.tip": "One JSON file with every book in the queue, worst first.",
    "dialog.savereport.batch": "Save batch report",
    "status.batch.saved": "Batch report for {count} book(s) saved.",
    "menu.file": "&File",
    "menu.quit": "Quit",
    "report.placeholder": "Select a book to see what the rebuild changed.",
    "report.source": "source",
    "report.output": "output",
    "report.notwritten": "NOT WRITTEN",
    "level.fix": "fixed",
    "level.preserved": "kept",
    "level.warn": "warning",
    "level.error": "error",
    "level.info": "info",
    "status.hint": "Drop EPUB files anywhere in this window.",
    "status.hint.nocheck": "EPUBCheck unavailable — validation disabled.",
    "status.queued.count": "Queued: {count}",
    "status.working": "Rebuilding {name}…",
    "status.validating": "Checking {name} with EPUBCheck…",
    "status.finished": "Finished {count} book(s) — all written.",
    "status.finished.failures": "Finished {count} book(s) — {failures} could not be written.",
    "dialog.nothing.title": "Nothing to do",
    "dialog.nothing.body": "Add at least one EPUB file first.",
    "dialog.overwrite.title": "Output would overwrite the source",
    "dialog.overwrite.body": "Choose a different output folder — {name} would be overwritten in place.",
    "dialog.noreport.title": "No report",
    "dialog.noreport.body": "Rebuild a book first, then select it.",
    "dialog.filter": "EPUB files (*.epub)",
    "dialog.selectfiles": "Select EPUB files",
    "dialog.selectfolder": "Select output folder",
    "dialog.savereport": "Save report",

    "menu.settings": "&Settings",
    "menu.language": "Interface language",
    "menu.help": "&Help",
    "menu.about": "About",
    "language.pl": "Polski",
    "language.en": "English",
    "about.title": "About EPUB F.O.R.G.E.",
    "about.subtitle": "Factory for Overhauling and Renovating Glitchy EPUBs",
    "about.tagline": "Forges broken e-books into clean EPUB 3.3 — without spoiling how they look.",
    "about.version": "Version {version}",
    "about.authors": "Authors",
    "about.author.human": "Łukasz \u201cLuKi\u201d Kniotek — concept, direction and requirements",
    "about.author.ai": "Claude (Anthropic) — design and implementation",
    "about.license": "License",
    "about.license.body": (
        "GNU GPL v3 or later. You may use, study and change it; whatever you make "
        "of it must be GPL too, with its source open. Without any warranty.\n\n"
        "It links LGPL libraries (Qt/PySide6, cssutils) and BSD-licensed EPUBCheck. "
        "Source available on GitHub."
    ),
    "about.components": "Bundled components",
    "about.components.body": (
        "EPUBCheck (W3C) — BSD 3-Clause\n"
        "OpenJDK runtime built with jlink — GPLv2 with the Classpath Exception\n"
        "Qt via PySide6 — LGPLv3, shipped as replaceable shared libraries"
    ),
    "about.close": "Close",
}

LANGUAGES = {"pl": PL, "en": EN}


DEFAULT_LANGUAGE = "pl"


def _detect() -> str:
    """Environment override first, then Polish.

    The system locale is deliberately *not* consulted: a machine reporting an
    English locale (a container, an English Windows install) should not decide
    the interface language. The GUI overrides this from stored settings.
    """
    override = os.environ.get("EPUBFORGE_LANG", "").strip().lower()[:2]
    return override if override in LANGUAGES else DEFAULT_LANGUAGE


def language() -> str:
    return _ACTIVE


_ACTIVE = _detect()


def set_language(code: str) -> None:
    """Switch the window's language, and the questions' along with it.

    The second half is the point (EF-032). Questions are raised deep in the
    rebuild, by modules that must not import anything from the window, so they
    carry their own catalogue; keeping the two settings in step here means there
    is one call to make and no way to change one without the other. Before this,
    an English user got the interface in English and then a paragraph of Polish
    at the moment of deciding something irreversible about their book.
    """
    global _ACTIVE
    if code in LANGUAGES:
        _ACTIVE = code
        from .. import question_texts

        question_texts.set_language(code)


def tr(key: str, **kwargs) -> str:
    """Look up *key*, falling back to English and then to the key itself.

    Filled with the same formatter the message catalogue uses, so a window
    string may say `{count:plik|pliki|plików}` and get the form the number
    actually takes. English gets away with "(s)"; Polish has three forms and
    "1 plików" is a mistake rather than a clumsy phrasing.
    """
    from ..rules import fill

    text = LANGUAGES[_ACTIVE].get(key) or EN.get(key) or key
    return fill(text, kwargs) if kwargs else text
