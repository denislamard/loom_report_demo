"""Le criblage : gardes, scores, et la matérialité vérifiée à la main.

La matérialité est le score qui décide du classement. Elle est donc recalculée
ici à partir des données brutes, sans passer par le moteur, sur deux candidats
dont on connaît la mécanique. Si les deux chemins divergent, l'un des deux a
tort, et le test le dit avant qu'un client ne le découvre.

Les couples tautologiques ont leur propre famille de tests. Ils ne sont détectés
par aucun des cinq scores : « le panier moyen croît avec la tranche de montant »
est vrai par construction, mais dispersion, stabilité et monotonie le notent au
maximum. Seule une déclaration explicite dans le catalogue les écarte.
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path

import pandas as pd
import pytest

from loom_report_demo.analysis import catalogue as cat
from loom_report_demo.analysis.cadrages import PRINCIPAL, fenetre
from loom_report_demo.analysis.chargement import COLONNE_DATE, Donnees, charger
from loom_report_demo.analysis.criblage import (
    COUVERTURE_MINIMALE,
    DISPERSION_PLANCHER,
    EFFECTIF_MINIMAL,
    PONDERATIONS,
    Criblage,
    cribler,
    spearman,
)
from loom_report_demo.niveaux import Niveau

GOLDEN = Path(__file__).parent / "golden" / "criblage.json"
TOLERANCE = 1e-6


@cache
def jeu() -> Donnees:
    return charger()


@cache
def criblage(niveau: Niveau) -> Criblage:
    return cribler(jeu(), niveau)


def _fenetre_gestion() -> tuple[pd.Timestamp, pd.Timestamp]:
    borne = fenetre(PRINCIPAL[Niveau.GESTION], jeu().situation, jeu().debut)
    return pd.Timestamp(borne.debut), pd.Timestamp(borne.fin)


def _table_fenetree(base: cat.Base) -> pd.DataFrame:
    debut, fin = _fenetre_gestion()
    table = jeu().table(base)
    colonne = table[COLONNE_DATE[base]]
    return table[(colonne >= debut) & (colonne <= fin)]


def _candidat(niveau: Niveau, cle: str):
    trouve = next((c for c in criblage(niveau).evalues if c.cle == cle), None)
    assert trouve is not None, f"candidat absent du criblage : {cle}"
    return trouve


# --------------------------------------------------- corrélation de rang
def test_spearman_detecte_une_relation_croissante() -> None:
    assert spearman([1.0, 2.0, 3.0, 4.0], [10.0, 20.0, 30.0, 40.0]) == pytest.approx(1.0)


def test_spearman_detecte_une_relation_decroissante() -> None:
    assert spearman([1.0, 2.0, 3.0, 4.0], [40.0, 30.0, 20.0, 10.0]) == pytest.approx(-1.0)


def test_spearman_ignore_lechelle_et_la_forme() -> None:
    """C'est une corrélation de RANG : seul l'ordre compte."""
    assert spearman([1.0, 2.0, 3.0, 4.0], [1.0, 4.0, 900.0, 1e6]) == pytest.approx(1.0)


def test_spearman_gere_les_ex_aequo() -> None:
    valeur = spearman([1.0, 2.0, 3.0, 4.0], [5.0, 5.0, 5.0, 9.0])
    assert -1.0 <= valeur <= 1.0


def test_spearman_rend_zero_sur_un_echantillon_trop_court() -> None:
    assert spearman([1.0, 2.0], [1.0, 2.0]) == 0.0


def test_spearman_rend_zero_quand_tout_est_constant() -> None:
    assert spearman([1.0, 2.0, 3.0], [7.0, 7.0, 7.0]) == 0.0


# ------------------------------------------- matérialité vérifiée à la main
def test_materialite_du_taux_de_marge_par_agence() -> None:
    """Recalcul indépendant : « si l'agence la moins rentable faisait comme les autres ».

    Conversion directe, puisque le numérateur de la mesure est déjà de la marge.
    """
    factures = _table_fenetree(cat.Base.FACTURES)
    par_agence = factures.groupby("agence")[["marge", "montant_ht"]].sum()
    taux = par_agence["marge"] / par_agence["montant_ht"]

    pire = str(taux.idxmin())
    autres = par_agence.drop(index=pire)
    cible = float(autres["marge"].sum() / autres["montant_ht"].sum())
    attendu = (cible - float(taux[pire])) * float(par_agence.loc[pire, "montant_ht"])

    obtenu = _candidat(Niveau.GESTION, "taux_marge_brute|agence")
    assert obtenu.modalite_defavorable == pire
    assert obtenu.cible == pytest.approx(cible, rel=TOLERANCE)
    assert obtenu.scores.materialite_euros == pytest.approx(attendu, rel=1e-4)

    # Vraisemblance : un gain de rattrapage sur une seule agence se compte en
    # points de marge, pas en fractions de chiffre d'affaires.
    ca_total = float(factures["montant_ht"].sum())
    assert 0 < attendu < 0.10 * ca_total


def test_materialite_de_la_transformation_par_delai_de_relance() -> None:
    """Le candidat vedette de la démonstration, recalculé de bout en bout.

    Le numérateur est du chiffre d'affaires : la conversion passe par le taux de
    marge de la période, pour que le gain s'exprime en marge comme les autres.
    """
    devis = _table_fenetree(cat.Base.DEVIS)
    par_tranche = devis.groupby("tranche_relance")[["ca_gagne", "montant_arbitre"]].sum()
    taux = par_tranche["ca_gagne"] / par_tranche["montant_arbitre"]

    pire = str(taux.idxmin())
    autres = par_tranche.drop(index=pire)
    cible = float(autres["ca_gagne"].sum() / autres["montant_arbitre"].sum())
    gain_ca = (cible - float(taux[pire])) * float(par_tranche.loc[pire, "montant_arbitre"])

    factures = _table_fenetree(cat.Base.FACTURES)
    taux_marge = float(factures["marge"].sum() / factures["montant_ht"].sum())
    attendu = gain_ca * taux_marge

    obtenu = _candidat(Niveau.GESTION, "taux_transformation|tranche_relance")
    assert obtenu.modalite_defavorable == "Jamais relancé"
    assert obtenu.cible == pytest.approx(cible, rel=TOLERANCE)
    assert obtenu.scores.materialite_euros == pytest.approx(attendu, rel=1e-4)

    # C'est le premier levier du groupe : il doit peser plus que le rattrapage
    # d'une agence, sans pour autant dépasser le chiffre d'affaires de la période.
    ca_total = float(factures["montant_ht"].sum())
    assert 0.03 * ca_total < attendu < 0.25 * ca_total


def test_la_materialite_est_annualisee() -> None:
    """Trente jours de gain valent douze fois moins que douze mois."""
    gestion = criblage(Niveau.GESTION)
    operationnel = criblage(Niveau.OPERATIONNEL)
    assert gestion.annualisation == pytest.approx(1.0, rel=0.01)
    assert operationnel.annualisation == pytest.approx(365 / 30, rel=0.01)


def test_une_mesure_non_convertible_na_pas_de_materialite() -> None:
    candidat = _candidat(Niveau.GESTION, "delai_1ere_relance|agence")
    assert not cat.mesure("delai_1ere_relance").materialisable
    assert candidat.scores.materialite_euros is None


def test_une_mesure_convertible_a_une_materialite() -> None:
    for cle in ("taux_marge_brute", "taux_transformation", "taux_derive_horaire"):
        assert cat.mesure(cle).materialisable
    assert _candidat(Niveau.GESTION, "taux_derive_horaire|agence").scores.materialite_euros


# ----------------------------------------------------- couples tautologiques
@pytest.mark.parametrize(
    ("cle_mesure", "cle_dimension"),
    [
        ("panier_moyen_gagne", "tranche_montant"),
        ("delai_1ere_relance", "tranche_relance"),
        ("ca_facture_ht", "tranche_montant"),
        ("age_moyen_file_recouvrement", "tranche_age_creance"),
        ("dso", "profil_paiement"),
        ("panier_moyen_gagne", "metier"),
    ],
)
def test_un_couple_tautologique_nest_jamais_propose(
    cle_mesure: str, cle_dimension: str
) -> None:
    for niveau in Niveau:
        assert (cle_mesure, cle_dimension) not in cat.croisements_valides(niveau)


def test_un_couple_tautologique_est_refuse_avec_un_motif_clair() -> None:
    with pytest.raises(ValueError, match="tautologique"):
        cat.valider("panier_moyen_gagne", "tranche_montant", Niveau.GESTION)


def test_les_tautologies_declarees_designent_des_mesures_reelles() -> None:
    for dimension in cat.DIMENSIONS.values():
        for cle in dimension.tautologiques:
            assert cle in cat.MESURES, f"{dimension.cle} déclare une mesure inconnue : {cle}"


def test_la_transformation_par_delai_de_relance_reste_permise() -> None:
    """Le délai de relance ne détermine pas la transformation : c'est un constat."""
    assert ("taux_transformation", "tranche_relance") in cat.croisements_valides(Niveau.GESTION)


# ---------------------------------------------------- gardes et recevabilité
@pytest.mark.parametrize("niveau", list(Niveau))
def test_le_criblage_couvre_tout_lespace_des_croisements(niveau: Niveau) -> None:
    assert criblage(niveau).explores == len(cat.croisements_valides(niveau))


@pytest.mark.parametrize("niveau", list(Niveau))
def test_chaque_rejet_porte_un_motif(niveau: Niveau) -> None:
    for candidat in criblage(niveau).rejetes:
        assert candidat.motif_rejet, candidat.cle
        assert not candidat.recevable


@pytest.mark.parametrize("niveau", list(Niveau))
def test_aucun_recevable_ne_descend_sous_le_seuil_deffectif(niveau: Niveau) -> None:
    seuil = EFFECTIF_MINIMAL[niveau]
    for candidat in criblage(niveau).evalues:
        assert candidat.scores.effectif_min >= seuil, candidat.cle


@pytest.mark.parametrize("niveau", list(Niveau))
def test_aucun_recevable_ne_descend_sous_le_plancher_de_dispersion(niveau: Niveau) -> None:
    for candidat in criblage(niveau).evalues:
        assert candidat.scores.dispersion >= DISPERSION_PLANCHER, candidat.cle


@pytest.mark.parametrize("niveau", list(Niveau))
def test_tout_recevable_a_au_moins_deux_modalites(niveau: Niveau) -> None:
    for candidat in criblage(niveau).evalues:
        assert candidat.nb_modalites >= 2, candidat.cle


def test_le_seuil_operationnel_est_plus_permissif_que_le_strategique() -> None:
    """Trente jours de données ne portent pas les mêmes exigences que quatre ans."""
    assert EFFECTIF_MINIMAL[Niveau.OPERATIONNEL] < EFFECTIF_MINIMAL[Niveau.STRATEGIQUE]


def test_la_couverture_minimale_reste_exigeante() -> None:
    assert 0.5 <= COUVERTURE_MINIMALE <= 0.9


# ---------------------------------------------------------- bornes des scores
@pytest.mark.parametrize("niveau", list(Niveau))
def test_les_scores_restent_dans_leurs_bornes(niveau: Niveau) -> None:
    for candidat in criblage(niveau).evalues:
        assert 0.0 <= candidat.scores.dispersion <= 1.0, candidat.cle
        assert 0.0 <= candidat.scores.monotonie <= 1.0, candidat.cle
        assert 0.0 <= candidat.scores.stabilite <= 1.0, candidat.cle
        assert 0.0 <= candidat.score_global <= 1.0, candidat.cle
        if candidat.scores.materialite_euros is not None:
            assert candidat.scores.materialite_euros >= 0.0, candidat.cle


def test_la_dispersion_reste_bornee_meme_quand_la_moyenne_frole_zero() -> None:
    """La dérive horaire tourne autour de 2 % : un écart relatif y explosait."""
    candidat = _candidat(Niveau.GESTION, "taux_derive_horaire|technicien")
    assert candidat.scores.dispersion <= 1.0


def test_la_stabilite_discrimine_reellement() -> None:
    """Une stabilité constante à 1.0 ne mesurerait rien."""
    valeurs = {c.scores.stabilite for c in criblage(Niveau.GESTION).evalues}
    assert len(valeurs) > 3, f"stabilité trop peu discriminante : {sorted(valeurs)}"


def test_la_monotonie_est_nulle_sur_une_dimension_sans_ordre() -> None:
    """Un gradient calculé sur un classement alphabétique serait une invention."""
    assert _candidat(Niveau.GESTION, "taux_marge_brute|agence").scores.monotonie == 0.0


def test_la_monotonie_est_forte_sur_un_vrai_gradient() -> None:
    candidat = _candidat(Niveau.GESTION, "taux_transformation|tranche_relance")
    assert candidat.scores.monotonie > 0.9


def test_les_ponderations_somment_a_un() -> None:
    assert sum(PONDERATIONS.values()) == pytest.approx(1.0)


@pytest.mark.parametrize("niveau", list(Niveau))
def test_le_classement_est_decroissant(niveau: Niveau) -> None:
    scores = [c.score_global for c in criblage(niveau).retenus]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.parametrize("niveau", list(Niveau))
def test_les_retenus_sont_le_debut_des_evalues(niveau: Niveau) -> None:
    resultat = criblage(niveau)
    assert list(resultat.retenus) == list(resultat.evalues[: len(resultat.retenus)])


def test_la_materialite_domine_le_classement() -> None:
    """À dispersion comparable, le candidat qui pèse en euros doit passer devant."""
    tete = criblage(Niveau.GESTION).retenus[0]
    assert tete.scores.materialite_euros is not None
    assert tete.scores.materialite_euros > 50_000


# ------------------------------------------------------------ fichier témoin
def test_le_criblage_est_conforme_au_temoin() -> None:
    attendu = json.loads(GOLDEN.read_text(encoding="utf-8"))
    for niveau in Niveau:
        resultat = criblage(niveau)
        reference = attendu[niveau.value]
        assert [c.cle for c in resultat.retenus[:5]] == reference["tete"], niveau.value
        assert resultat.explores == reference["explores"], niveau.value
        assert len(resultat.evalues) == reference["recevables"], niveau.value
        for cle, montant in reference["materialite"].items():
            candidat = _candidat(niveau, cle)
            assert candidat.scores.materialite_euros == pytest.approx(montant, rel=1e-4)
