"""Le flux console, testé sans terminal grâce à la saisie injectée."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from loom_report_demo import app, console
from loom_report_demo.niveaux import Niveau


def saisies(*reponses: str) -> console.Saisie:
    flux: Iterator[str] = iter(reponses)

    def _saisir(_invite: str) -> str:
        return next(flux)

    return _saisir


def test_le_menu_affiche_les_trois_questions() -> None:
    rendu = console.menu()
    for niveau in Niveau:
        assert console.NIVEAUX[niveau].question in rendu


def test_lire_choix_accepte_un_rang_valide() -> None:
    choix = console.lire_choix(saisies("2"))
    assert choix is not None and choix.niveau is Niveau.GESTION


def test_lire_choix_tolere_les_espaces_et_la_casse() -> None:
    choix = console.lire_choix(saisies("  3  "))
    assert choix is not None and choix.niveau is Niveau.OPERATIONNEL


def test_lire_choix_rend_none_sur_q() -> None:
    assert console.lire_choix(saisies("q")) is None


def test_lire_choix_rend_none_sur_entree_vide() -> None:
    assert console.lire_choix(saisies("")) is None


def test_lire_choix_redemande_apres_une_saisie_invalide() -> None:
    choix = console.lire_choix(saisies("7", "abc", "1"))
    assert choix is not None and choix.niveau is Niveau.STRATEGIQUE


def test_lire_choix_rend_none_sur_fin_de_flux() -> None:
    def _epuise(_invite: str) -> str:
        raise EOFError

    assert console.lire_choix(_epuise) is None


def test_lire_choix_rend_none_sur_interruption_clavier() -> None:
    def _interrompt(_invite: str) -> str:
        raise KeyboardInterrupt

    assert console.lire_choix(_interrompt) is None


def test_le_resume_annonce_le_socle_impose() -> None:
    rendu = console.resume(console.NIVEAUX[Niveau.STRATEGIQUE])
    assert "ca_par_technicien" in rendu
    assert "concentration_client" in rendu


async def test_executer_sort_proprement_quand_on_quitte(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert await console.executer(saisir=saisies("q")) == 0
    assert "Interrompu" in capsys.readouterr().out


async def test_executer_annonce_le_niveau_avant_toute_depense(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sans clé, le flux s'arrête après le résumé et renvoie vers la fixture.

    L'ordre compte : le résumé du niveau — socle, modèle, durée de vie — s'affiche
    AVANT que le moindre jeton ne soit engagé.
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("M3_API_KEY", raising=False)
    assert await console.executer(saisir=saisies("2")) == 1
    sortie = capsys.readouterr().out
    assert "gestion" in sortie
    assert "Socle imposé" in sortie
    assert "uv run rapport" in sortie


async def test_executer_echoue_proprement_si_installation_incomplete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("LOOM_REPORT_HOME", str(tmp_path))
    assert await console.executer(saisir=saisies("1")) == 1
    assert "Installation incomplète" in capsys.readouterr().err


async def test_entry_leve_systemexit_si_installation_incomplete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`run()` ne rend rien : le code de sortie passe par SystemExit."""
    monkeypatch.setenv("LOOM_REPORT_HOME", str(tmp_path))
    monkeypatch.setattr("builtins.input", lambda _prompt="": "1")
    with pytest.raises(SystemExit) as excinfo:
        await app.entry()
    assert excinfo.value.code == 1
    capsys.readouterr()


async def test_entry_ne_leve_pas_quand_tout_va_bien(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("builtins.input", lambda _prompt="": "q")
    await app.entry()
    capsys.readouterr()
