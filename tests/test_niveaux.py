"""Le type de domaine qui commute tout le reste du programme."""

from __future__ import annotations

import pytest

from loom_report_demo.niveaux import (
    NIVEAUX,
    ORDRE_MENU,
    Livrable,
    Niveau,
    definition,
    par_rang,
)


def test_les_trois_niveaux_sont_definis() -> None:
    assert set(NIVEAUX) == set(Niveau)


def test_le_menu_couvre_tous_les_niveaux_sans_doublon() -> None:
    assert len(ORDRE_MENU) == len(set(ORDRE_MENU)) == len(Niveau)


def test_le_menu_va_du_plus_long_terme_au_plus_court() -> None:
    horizons = [NIVEAUX[n].horizon_jours for n in ORDRE_MENU]
    assert horizons == sorted(horizons, reverse=True)


@pytest.mark.parametrize("niveau", list(Niveau))
def test_chaque_socle_est_non_vide_et_sans_doublon(niveau: Niveau) -> None:
    socle = definition(niveau).socle
    assert socle, "un socle vide laisserait l'agent seul maître du contenu"
    assert len(socle) == len(set(socle))


@pytest.mark.parametrize("niveau", list(Niveau))
def test_la_question_est_posee_dans_la_langue_du_client(niveau: Niveau) -> None:
    question = definition(niveau).question
    assert question.endswith("?")
    for jargon in ("stratégique", "gestion", "opérationnel", "KPI", "indicateur"):
        assert jargon.lower() not in question.lower()


def test_le_stratégique_est_le_seul_gele_sur_douze_mois() -> None:
    geles = [n for n in Niveau if "12 mois" in definition(n).duree_vie]
    assert geles == [Niveau.STRATEGIQUE]


def test_le_modele_le_plus_cher_sert_la_decision_la_plus_durable() -> None:
    """La liberté de l'agent est bornée par la durée de vie de sa décision."""
    assert definition(Niveau.STRATEGIQUE).modele == "SONNET"
    assert definition(Niveau.GESTION).modele == "HAIKU"
    assert definition(Niveau.OPERATIONNEL).modele == "HAIKU"


def test_l_operationnel_produit_une_file_pas_un_tableau_de_bord() -> None:
    assert definition(Niveau.OPERATIONNEL).livrable is Livrable.FILE_DE_TRAVAIL
    assert definition(Niveau.GESTION).livrable is Livrable.TABLEAU_DE_BORD
    assert definition(Niveau.STRATEGIQUE).livrable is Livrable.TABLEAU_DE_BORD


def test_les_fichiers_detat_sont_distincts() -> None:
    fichiers = [definition(n).fichier_etat for n in Niveau]
    assert len(set(fichiers)) == len(fichiers)


def test_nb_indicateurs_somme_socle_et_variables() -> None:
    d = definition(Niveau.GESTION)
    assert d.nb_indicateurs == len(d.socle) + d.nb_variables


@pytest.mark.parametrize(("rang", "attendu"), [(1, Niveau.STRATEGIQUE), (3, Niveau.OPERATIONNEL)])
def test_par_rang_resout_le_choix_de_menu(rang: int, attendu: Niveau) -> None:
    assert par_rang(rang).niveau is attendu


@pytest.mark.parametrize("rang", [0, 4, -1])
def test_par_rang_refuse_un_rang_hors_bornes(rang: int) -> None:
    with pytest.raises(ValueError, match="hors bornes"):
        par_rang(rang)


def test_la_definition_est_immuable() -> None:
    d = definition(Niveau.GESTION)
    with pytest.raises(AttributeError):
        d.nb_variables = 9  # type: ignore[misc]
