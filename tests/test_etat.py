"""Persistance de la sélection : gel du millésime, rejeu, refus d'un état périmé.

Le rejeu n'est pas un confort de développement. Un agent qui choisit d'autres
indicateurs à chaque lancement est un risque en rendez-vous client : on veut
pouvoir montrer deux fois la même chose. Et le gel n'est pas une rigidité : un
référentiel stratégique qui change en cours d'année cesse d'être comparable, ce
qui était sa seule raison d'être.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from loom_report_demo import etat, paths
from loom_report_demo.niveaux import NIVEAUX, Niveau
from loom_report_demo.parsing import ErreurSortie

FIXTURES = Path(__file__).parent / "fixtures"


def _brut(niveau: Niveau) -> str:
    nom = "strategique.json" if niveau is Niveau.STRATEGIQUE else "gestion.json"
    return (FIXTURES / nom).read_text(encoding="utf-8")


def _isoler(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Redirige l'état sans toucher aux données, qui restent celles du dépôt."""
    monkeypatch.setattr(etat, "chemin", lambda niveau: tmp_path / f"{niveau.value}.json")


# ----------------------------------------------------------------- millésime
def test_le_strategique_est_versionne_a_lannee() -> None:
    assert etat.millesime(Niveau.STRATEGIQUE, date(2026, 6, 30)) == "2026"
    assert etat.millesime(Niveau.STRATEGIQUE, date(2026, 1, 2)) == "2026"


def test_les_autres_niveaux_sont_versionnes_au_mois() -> None:
    assert etat.millesime(Niveau.GESTION, date(2026, 6, 30)) == "2026-06"
    assert etat.millesime(Niveau.OPERATIONNEL, date(2026, 7, 1)) == "2026-07"


def test_le_grain_de_versionnement_suit_la_duree_de_vie() -> None:
    """Le seul niveau versionné à l'année est le seul dont la sélection est gelée."""
    for niveau in Niveau:
        annuel = etat.millesime(niveau, date(2026, 6, 30)) == "2026"
        assert annuel == ("gelée" in NIVEAUX[niveau].duree_vie)


def test_chaque_niveau_a_son_propre_fichier() -> None:
    fichiers = {etat.chemin(n).name for n in Niveau}
    assert len(fichiers) == len(Niveau)


def test_letat_est_range_sous_les_sorties_techniques() -> None:
    assert paths.journaux() in etat.chemin(Niveau.GESTION).parents


# --------------------------------------------------------- écriture, relecture
def test_une_selection_enregistree_se_relit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isoler(tmp_path, monkeypatch)
    etat.enregistrer(Niveau.GESTION, _brut(Niveau.GESTION), date(2026, 6, 30))
    enregistrement = etat.derniere(Niveau.GESTION)
    assert enregistrement is not None
    assert enregistrement.millesime == "2026-06"
    assert len(enregistrement.selection().variables) == 4


def test_la_relecture_repasse_par_toutes_les_gardes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Un état écrit sous un ancien catalogue doit être refusé, pas accepté."""
    _isoler(tmp_path, monkeypatch)
    charge = json.loads(_brut(Niveau.GESTION))
    charge["variables"][0]["mesure"] = "mesure_disparue"
    etat.enregistrer(Niveau.GESTION, json.dumps(charge), date(2026, 6, 30))
    with pytest.raises(ErreurSortie, match="Mesure inconnue"):
        etat.rejouer(Niveau.GESTION)


def test_labsence_detat_est_signalee_clairement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isoler(tmp_path, monkeypatch)
    assert etat.derniere(Niveau.GESTION) is None
    with pytest.raises(FileNotFoundError, match="uv run app"):
        etat.rejouer(Niveau.GESTION)


def test_le_rejeu_rend_la_meme_selection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isoler(tmp_path, monkeypatch)
    etat.enregistrer(Niveau.GESTION, _brut(Niveau.GESTION), date(2026, 6, 30))
    premiere, seconde = etat.rejouer(Niveau.GESTION), etat.rejouer(Niveau.GESTION)
    assert premiere == seconde


def test_un_nouvel_enregistrement_ecrase_le_precedent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isoler(tmp_path, monkeypatch)
    etat.enregistrer(Niveau.STRATEGIQUE, _brut(Niveau.STRATEGIQUE), date(2026, 6, 30))
    etat.enregistrer(Niveau.STRATEGIQUE, _brut(Niveau.STRATEGIQUE), date(2026, 6, 30))
    assert len(list(tmp_path.glob("*.json"))) == 1


# ------------------------------------------------------------------- le gel
def test_une_selection_du_millesime_courant_est_gelee(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isoler(tmp_path, monkeypatch)
    etat.enregistrer(Niveau.STRATEGIQUE, _brut(Niveau.STRATEGIQUE), date(2026, 6, 30))
    assert etat.gelee(Niveau.STRATEGIQUE, date(2026, 11, 5)) is not None


def test_le_gel_tombe_au_changement_de_millesime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isoler(tmp_path, monkeypatch)
    etat.enregistrer(Niveau.STRATEGIQUE, _brut(Niveau.STRATEGIQUE), date(2026, 6, 30))
    assert etat.gelee(Niveau.STRATEGIQUE, date(2027, 1, 4)) is None


def test_le_gel_de_gestion_tombe_au_mois_suivant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isoler(tmp_path, monkeypatch)
    etat.enregistrer(Niveau.GESTION, _brut(Niveau.GESTION), date(2026, 6, 30))
    assert etat.gelee(Niveau.GESTION, date(2026, 6, 2)) is not None
    assert etat.gelee(Niveau.GESTION, date(2026, 7, 2)) is None


def test_aucun_gel_sans_etat(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _isoler(tmp_path, monkeypatch)
    assert etat.gelee(Niveau.STRATEGIQUE, date(2026, 6, 30)) is None
