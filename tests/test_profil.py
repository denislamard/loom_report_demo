"""Le profil de reconnaissance remis à l'agent."""

from __future__ import annotations

import json
from functools import cache
from typing import Any

import pytest

from loom_report_demo.analysis import catalogue as cat
from loom_report_demo.analysis.cli import executer
from loom_report_demo.analysis.profil import formater, profil
from loom_report_demo.niveaux import NIVEAUX, Niveau


@cache
def carte(niveau: Niveau) -> dict[str, Any]:
    return profil(niveau)


@pytest.mark.parametrize("niveau", list(Niveau))
def test_le_profil_est_serialisable_en_json(niveau: Niveau) -> None:
    """Il sera injecté tel quel dans le prompt : aucun objet pandas ne doit rester."""
    json.dumps(carte(niveau), ensure_ascii=False)


@pytest.mark.parametrize("niveau", list(Niveau))
def test_le_profil_ne_livre_que_les_mesures_du_niveau(niveau: Niveau) -> None:
    proposees = {m["cle"] for m in carte(niveau)["mesures"]}
    assert proposees == {m.cle for m in cat.mesures_du_niveau(niveau)}


@pytest.mark.parametrize("niveau", list(Niveau))
def test_le_profil_annonce_le_socle_et_le_nombre_a_choisir(niveau: Niveau) -> None:
    definition = NIVEAUX[niveau]
    assert carte(niveau)["socle_impose"] == list(definition.socle)
    assert carte(niveau)["indicateurs_a_choisir"] == definition.nb_variables


@pytest.mark.parametrize("niveau", list(Niveau))
def test_chaque_mesure_du_socle_a_son_ancrage(niveau: Niveau) -> None:
    ancres = {a["cle"] for a in carte(niveau)["ancrages"]}
    assert ancres == set(NIVEAUX[niveau].socle)


def test_le_profil_ne_livre_aucun_ecart_sur_une_mesure_de_stock() -> None:
    """Sans cette garde, l'agent lirait un DSO en hausse de 2 000 pour cent."""
    ancrages = {a["cle"]: a for a in carte(Niveau.STRATEGIQUE)["ancrages"]}
    dso = ancrages["dso"]
    assert dso["nature"] == "stock"
    assert dso["ecart_relatif"] is None
    assert dso["valeur_comparaison"] is None
    assert dso["motif_sans_ecart"]


def test_le_profil_livre_un_ecart_sur_une_mesure_de_flux() -> None:
    ancrages = {a["cle"]: a for a in carte(Niveau.GESTION)["ancrages"]}
    assert ancrages["taux_marge_brute"]["ecart_relatif"] is not None


def test_le_profil_ne_livre_aucune_conclusion() -> None:
    """Il décrit le terrain. Les mots de jugement n'y ont pas leur place."""
    brut = json.dumps(carte(Niveau.GESTION), ensure_ascii=False).lower()
    for interdit in ("recommand", "il faut", "problème", "alerte", "priorit"):
        assert interdit not in brut, f"le profil ne doit pas conclure : {interdit!r}"


@pytest.mark.parametrize("niveau", list(Niveau))
def test_chaque_dimension_annonce_son_effectif_minimal(niveau: Niveau) -> None:
    """C'est l'information qui distingue une ventilation d'un tirage au sort."""
    for dimension in carte(niveau)["dimensions"]:
        assert dimension["nb_modalites"] >= 1
        assert dimension["effectif_min"] >= 0


@pytest.mark.parametrize("niveau", list(Niveau))
def test_les_fenetres_sont_disjointes_et_ordonnees(niveau: Niveau) -> None:
    principale = carte(niveau)["fenetre_principale"]
    comparaison = carte(niveau)["fenetre_comparaison"]
    assert comparaison["fin"] < principale["debut"]


def test_le_rendu_console_annonce_le_socle() -> None:
    rendu = formater(carte(Niveau.STRATEGIQUE))
    assert "Socle imposé" in rendu
    assert "Concentration" in rendu


def test_le_rendu_console_marque_les_stocks_plutot_quun_faux_ecart() -> None:
    assert "stock" in formater(carte(Niveau.STRATEGIQUE))


@pytest.mark.parametrize("niveau", [n.value for n in Niveau])
def test_la_commande_profil_reussit(niveau: str, capsys: pytest.CaptureFixture[str]) -> None:
    assert executer(["--niveau", niveau]) == 0
    assert "Socle imposé" in capsys.readouterr().out


def test_la_commande_profil_sort_du_json_valide(capsys: pytest.CaptureFixture[str]) -> None:
    assert executer(["--niveau", "gestion", "--json"]) == 0
    charge = json.loads(capsys.readouterr().out)
    assert charge["niveau"] == "gestion"
