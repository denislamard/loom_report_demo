"""Files de travail, garde de faisabilité et export vers un agent de relance."""

from __future__ import annotations

import json
from datetime import date
from functools import cache
from pathlib import Path

import pytest

from loom_report_demo.analysis.chargement import Donnees, charger
from loom_report_demo.analysis.faisabilite import (
    MINIMA,
    evaluer,
    exporter_files,
    produit_des_files,
)
from loom_report_demo.analysis.files import MAX_LIGNES, construire_files
from loom_report_demo.niveaux import Livrable, Niveau, definition
from loom_report_demo.parsing import charger as charger_selection

FIXTURE = Path(__file__).parent / "fixtures" / "operationnel.json"


@cache
def jeu() -> Donnees:
    return charger()


@cache
def files() -> tuple:
    return construire_files(jeu())


def test_les_trois_files_sont_produites() -> None:
    assert {f.cle for f in files()} == {"creances", "devis", "derive"}


@pytest.mark.parametrize("rang", range(3))
def test_chaque_file_est_triee_par_priorite_decroissante(rang: int) -> None:
    """Le tri décide de l'ordre dans lequel un artisan va travailler."""
    priorites = [t.priorite for t in files()[rang].taches]
    assert priorites == sorted(priorites, reverse=True)


@pytest.mark.parametrize("rang", range(3))
def test_aucune_file_ne_depasse_la_taille_traitable(rang: int) -> None:
    """Au-delà, ce n'est plus une liste de travail : c'est un export."""
    assert len(files()[rang].taches) <= MAX_LIGNES


@pytest.mark.parametrize("rang", range(3))
def test_chaque_file_annonce_ce_quelle_ne_montre_pas(rang: int) -> None:
    file = files()[rang]
    assert file.total_candidats >= len(file.taches)
    assert file.seuil_libelle


@pytest.mark.parametrize("rang", range(3))
def test_chaque_tache_porte_son_motif(rang: int) -> None:
    for tache in files()[rang].taches:
        assert tache.motif
        assert tache.montant > 0


def test_les_creances_ouvertes_seulement() -> None:
    references = {t.reference for t in files()[0].taches}
    ouvertes = set(
        jeu().factures.loc[jeu().factures["est_payee"] == 0, "facture_id"].astype(str)
    )
    assert references <= ouvertes


def test_les_devis_a_relancer_nont_jamais_ete_relances() -> None:
    references = {t.reference for t in files()[1].taches}
    jamais = set(
        jeu()
        .devis.loc[jeu().devis["delai_1ere_relance_j"].isna(), "devis_id"]
        .astype(str)
    )
    assert references <= jamais


def test_la_derive_est_un_surcout_pas_un_chiffre_daffaires() -> None:
    """Ce qui décide de revoir un chiffrage, c'est ce que la dérive a coûté."""
    for tache in files()[2].taches:
        assert tache.detail["heures_reelles"] > tache.detail["heures_devisees"]


def test_un_seuil_plus_severe_reduit_la_file() -> None:
    large = construire_files(jeu(), {"derive": 0.05})[2]
    stricte = construire_files(jeu(), {"derive": 0.40})[2]
    assert stricte.total_candidats < large.total_candidats


# ------------------------------------------------------------- faisabilité
@pytest.mark.parametrize("niveau", list(Niveau))
def test_le_jeu_livre_porte_les_trois_niveaux(niveau: Niveau) -> None:
    assert evaluer(jeu(), niveau).praticable, evaluer(jeu(), niveau).resume


def test_un_jeu_trop_maigre_est_signale() -> None:
    """Mieux vaut le constater sans jeton que dans la sortie du modèle."""
    maigre = charger(situation=date(2022, 8, 15))
    verdict = evaluer(maigre, Niveau.STRATEGIQUE)
    assert not verdict.praticable
    assert "exercice" in verdict.resume.lower()


def test_la_garde_avertit_sans_bloquer() -> None:
    """Un avertissement qui empêche d'agir est vite contourné.

    La garde ne lève jamais : elle rend un verdict que l'appelant affiche. Le
    dirigeant peut vouloir voir un rapport maigre, et c'est son droit.
    """
    verdict = evaluer(charger(situation=date(2022, 8, 15)), Niveau.STRATEGIQUE)
    assert not verdict.praticable
    assert verdict.observations
    assert verdict.resume and not verdict.resume.startswith("Les données portent")


def test_un_verdict_favorable_reste_lisible() -> None:
    verdict = evaluer(jeu(), Niveau.GESTION)
    assert verdict.praticable
    assert verdict.observations == ()
    assert verdict.resume.startswith("Les données portent")


def test_les_seuils_de_lisibilite_suivent_lhorizon() -> None:
    assert MINIMA[Niveau.STRATEGIQUE][0] > MINIMA[Niveau.GESTION][0]
    assert MINIMA[Niveau.GESTION][0] > MINIMA[Niveau.OPERATIONNEL][0]


def test_seul_loperationnel_produit_des_files() -> None:
    assert produit_des_files(Niveau.OPERATIONNEL)
    assert not produit_des_files(Niveau.GESTION)
    assert definition(Niveau.OPERATIONNEL).livrable is Livrable.FILE_DE_TRAVAIL


# ------------------------------------------------------------------ export
def test_lexport_est_un_json_exploitable(tmp_path: Path) -> None:
    chemin = exporter_files(files(), jeu(), Niveau.OPERATIONNEL, tmp_path / "f.json")
    charge = json.loads(chemin.read_text(encoding="utf-8"))
    assert charge["niveau"] == "operationnel"
    assert charge["livrable"] == "file_de_travail"
    assert len(charge["files"]) == 3
    assert charge["files"][0]["taches"][0]["reference"].startswith("FAC-")


def test_lexport_transmet_lempreinte_des_donnees(tmp_path: Path) -> None:
    """Un agent qui traite une file doit savoir de quelle version elle sort."""
    from loom_report_demo import paths
    from loom_report_demo.fingerprint import empreinte_jeu

    empreinte = empreinte_jeu([paths.csv_source(n) for n in paths.FICHIERS_DONNEES])
    chemin = exporter_files(
        files(), jeu(), Niveau.OPERATIONNEL, tmp_path / "f.json", empreinte
    )
    charge = json.loads(chemin.read_text(encoding="utf-8"))
    assert charge["empreinte_donnees"] == empreinte.globale


# --------------------------------------------------------------- sélection
def test_lagent_ne_choisit_que_les_seuils() -> None:
    seuils = charger_selection(FIXTURE).seuils()
    assert seuils == {"devis": 5.0, "derive": 0.15}


def test_un_seuil_dunite_incompatible_ne_pilote_aucune_file() -> None:
    """Une part de devis relancés à temps ne trie pas une file par ancienneté."""
    from loom_report_demo.workbook.selection import Selection

    assert "respect_delai_relance" not in Selection.FILES_PAR_MESURE
