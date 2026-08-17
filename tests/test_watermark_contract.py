"""Przenoszenie i usuwanie znaku wodnego — BA-2026-003, ostatnie dwie.

Ten plik istnieje z powodu, który wyszedł dopiero przy pisaniu poprzedniego.
Korpus — sieć regresyjna tego programu, sto sześćdziesiąt prawdziwych książek —
uruchamia trzy tryby, i **wszystkie trzy** ustawiają znak wodny na
`consolidate`. Ścieżka, która wyjmuje token z treści, nie jest w nim dotykana
ani razu. Czyli dwie transformacje najdroższe w skutkach były poza siecią, która
miała ich pilnować, i „korpus zielony" nie mówiło o nich nic.

Sprawdzane są trzy rzeczy, i trzecia jest właściwym powodem, dla którego
kontrakt w ogóle powstał:

* `gather` wyjmuje token z tekstu **i parkuje go w nagłówku** — obie połowy,
  bo sama pierwsza to jest usunięcie pod ładniejszą nazwą;
* `remove` zabiera token i **nie zabiera zdania, które za nim stało**;
* gdy parkowanie się nie uda, transformacja **wraca w całości** — token zostaje
  w książce, a raport mówi, że wrócił.
"""

from __future__ import annotations

import zipfile

import pytest

from epubforge.pipeline import rebuild
from epubforge.policy import Policy
from epubforge.report import Action, Risk
from epubforge.watermark import META_NAME

from .test_dead_css_urls import book, rules_of

#: Wygląda jak token sklepu i nim jest: ciąg bez znaczenia, schowany stylem tak,
#: żeby czytelnik go nie zobaczył. Wzięty z kształtu, nie z konkretnej książki.
TOKEN = "NzgxMjI0NjMzOTUzNjQ"

#: Zdanie powieści tuż za tokenem. Jest tu po to, żeby miało co zginąć, gdyby
#: usuwanie sięgnęło o element za daleko.
NOVEL = "Był chłodny, jasny dzień kwietnia."

BODY = (
    f'<p>{NOVEL}</p>'
    f'<div style="font-size:1px;color:#FFF">{TOKEN}</div>'
)


def page(body: str) -> bytes:
    return (
        '<?xml version="1.0" encoding="utf-8"?><!DOCTYPE html>'
        '<html xmlns="http://www.w3.org/1999/xhtml" lang="pl"><head>'
        '<meta charset="utf-8"/><title>R</title></head>'
        f"<body>{body}</body></html>"
    ).encode("utf-8")


def with_watermarks(mode: str) -> Policy:
    policy = Policy.preset("preserve")
    policy.watermarks = mode
    return policy


def rebuilt(tmp_path, policy: Policy):
    source = book(
        tmp_path / "in.epub",
        "p { margin: 0 }",
        extra_files={"OEBPS/chapter.xhtml": page(BODY)},
    )
    return rebuild(source, str(tmp_path / "out.epub"), policy)


def documents_of(result) -> str:
    with zipfile.ZipFile(result.output_path) as archive:
        return " ".join(
            archive.read(name).decode("utf-8")
            for name in archive.namelist()
            if name.endswith(".xhtml")
        )


def ledger_for(result, rule: str):
    return [entry for entry in result.report.changes if entry.rule == rule]


class TestGatheringPutsItSomewhere:
    """`gather` jest domyślne i jest **przeniesieniem**. Obie połowy, albo nic."""

    def test_the_token_leaves_the_text(self, tmp_path):
        result = rebuilt(tmp_path, with_watermarks("gather"))
        assert result.status.wrote_a_file, result.report.to_text()
        assert f">{TOKEN}<" not in documents_of(result)

    def test_and_lands_in_the_head(self, tmp_path):
        """Ta połowa jest tą, o której łatwo zapomnieć, a bez niej raport mówi
        „przeniesione" o czymś, czego już nigdzie nie ma."""
        result = rebuilt(tmp_path, with_watermarks("gather"))
        documents = documents_of(result)
        assert f'name="{META_NAME}"' in documents
        assert TOKEN in documents

    def test_the_novel_is_untouched(self, tmp_path):
        result = rebuilt(tmp_path, with_watermarks("gather"))
        assert NOVEL in documents_of(result)

    def test_the_report_says_so(self, tmp_path):
        result = rebuilt(tmp_path, with_watermarks("gather"))
        assert "xhtml.watermark-relocated" in rules_of(result)

    def test_and_the_ledger_can_add_it_up(self, tmp_path):
        """BA-2026-003 prosi o bilans, który da się **zsumować**, nie o zdanie.
        Przeniesienie jest odwracalne z samego wyniku — token stoi w nagłówku —
        i bilans ma o tym mówić, bo to jest cała różnica wobec usunięcia."""
        result = rebuilt(tmp_path, with_watermarks("gather"))
        entries = ledger_for(result, "xhtml.watermark-relocated")
        assert entries, result.report.to_text()
        assert entries[0].action == Action.MOVED
        assert entries[0].risk == Risk.CONTENT
        assert entries[0].reversible is True


class TestRemovingTakesTheTokenAndNothingElse:
    def test_the_token_goes(self, tmp_path):
        result = rebuilt(tmp_path, with_watermarks("remove"))
        assert result.status.wrote_a_file, result.report.to_text()
        assert TOKEN not in documents_of(result)

    def test_the_sentence_behind_it_stays(self, tmp_path):
        """Warunek końcowy liczy **dokładnie tyle** znaków, ile niosły znaczniki.
        Zdanie stojące obok jest tym, co ten człon chroni."""
        result = rebuilt(tmp_path, with_watermarks("remove"))
        assert NOVEL in documents_of(result)

    def test_the_ledger_calls_it_irreversible(self, tmp_path):
        result = rebuilt(tmp_path, with_watermarks("remove"))
        entries = ledger_for(result, "xhtml.watermark-removed")
        assert entries, result.report.to_text()
        assert entries[0].action == Action.REMOVED
        assert entries[0].reversible is False


class TestWhenParkingFailsNothingIsLost:
    """Właściwy powód, dla którego kontrakt istnieje.

    Bez niego nieudane zaparkowanie tokenu wyglądało tak: token znika z treści,
    w nagłówku go nie ma, licznik mówi „przeniesiono", raport mówi to samo.
    Zmiana cicha i połowiczna, czyli dokładnie to, co opisuje ustalenie.
    """

    @pytest.fixture
    def parking_broken(self, monkeypatch):
        from epubforge.stages.content import ContentStage

        monkeypatch.setattr(
            ContentStage, "_gather_tokens", lambda self, root, tokens: None
        )

    def test_the_token_stays_in_the_book(self, tmp_path, parking_broken):
        result = rebuilt(tmp_path, with_watermarks("gather"))
        assert result.status.wrote_a_file, result.report.to_text()
        assert TOKEN in documents_of(result)

    def test_and_nothing_claims_it_was_moved(self, tmp_path, parking_broken):
        result = rebuilt(tmp_path, with_watermarks("gather"))
        assert "xhtml.watermark-relocated" not in rules_of(result)
        assert not ledger_for(result, "xhtml.watermark-relocated")

    def test_and_the_report_says_it_came_back(self, tmp_path, parking_broken):
        """Cicha rezygnacja wygląda w raporcie tak samo jak brak powodu do
        zmiany, i to jest ta sama wada, o której mówi ustalenie."""
        result = rebuilt(tmp_path, with_watermarks("gather"))
        assert "xhtml.watermark-reverted" in rules_of(result)

    def test_the_novel_survives_the_revert_too(self, tmp_path, parking_broken):
        result = rebuilt(tmp_path, with_watermarks("gather"))
        assert NOVEL in documents_of(result)
