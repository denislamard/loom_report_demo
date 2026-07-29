"""Catalogue, cadrages et moteur de calcul.

Trois familles.

La **cohérence catalogue / chargement** est la plus importante : le catalogue
déclare des noms de colonnes, `chargement.py` les construit, et rien n'oblige
mécaniquement les deux fichiers à rester d'accord. Un test les confronte, et il
échoue à l'ajout d'une mesure dont on a oublié la colonne.

Les **invariants du moteur** vérifient l'algèbre : on somme avant de diviser, un
stock ne se compare pas entre deux fenêtres, un croisement impossible est refusé
avec un message exploitable.

Le **fichier de référence** fige 57 valeurs, 8 ventilations et 3 séries. Toute
dérive du calcul le casse, ce qui est exactement le but : au jalon 4, le classeur
sera vérifié contre ces mêmes agrégats.
"""

from __future__ import annotations

import json
from datetime import date
from functools import cache
from pathlib import Path

import pytest

from loom_report_demo.analysis import catalogue as cat
from loom_report_demo.analysis.cadrages import COMPARAISON, PRINCIPAL, Cadrage, fenetre
from loom_report_demo.analysis.chargement import COLONNE_DATE, Donnees, charger
from loom_report_demo.analysis.moteur import calculer, comparer, serie_mensuelle, ventiler
from loom_report_demo.niveaux import NIVEAUX, Niveau

GOLDEN = Path(__file__).parent / "golden" / "moteur.json"
TOLERANCE = 1e-6


@cache
def jeu() -> Donnees:
    return charger()


@cache
def reference() -> dict[str, object]:
    return json.loads(GOLDEN.read_text(encoding="utf-8"))


def _proche(obtenu: float | None, attendu: float | None) -> bool:
    if obtenu is None or attendu is None:
        return obtenu is attendu
    return abs(obtenu - attendu) <= TOLERANCE * max(1.0, abs(attendu))


# ------------------------------------------ cohérence catalogue / chargement
@pytest.mark.parametrize("cle", sorted(cat.MESURES))
def test_les_colonnes_de_chaque_mesure_existent(cle: str) -> None:
    mesure = cat.MESURES[cle]
    if mesure.agregat is None:
        return
    table = jeu().table(mesure.base)
    attendues = [mesure.agregat.numerateur, mesure.agregat.denominateur, mesure.agregat.distinct]
    for colonne in filter(None, attendues):
        assert colonne in table.columns, f"{cle} : colonne {colonne!r} absente de {mesure.base}"


@pytest.mark.parametrize("cle", sorted(cat.DIMENSIONS))
def test_les_colonnes_de_chaque_dimension_existent(cle: str) -> None:
    dim = cat.DIMENSIONS[cle]
    for base in dim.bases:
        table = jeu().table(base)
        assert dim.colonne in table.columns, f"{cle} : absente de {base.value}"


@pytest.mark.parametrize("cle", sorted(cat.MESURES))
def test_aucune_colonne_de_mesure_nest_vide(cle: str) -> None:
    """Une colonne entièrement nulle signale une jointure ratée, pas un zéro métier."""
    mesure = cat.MESURES[cle]
    if mesure.agregat is None:
        return
    table = jeu().table(mesure.base)
    assert table[mesure.agregat.numerateur].notna().any()


def test_chaque_speciale_a_sa_fonction() -> None:
    from loom_report_demo.analysis.moteur import SPECIALES

    for mesure in cat.MESURES.values():
        if mesure.special is not None:
            assert mesure.special in SPECIALES, mesure.cle


def test_les_bases_declarent_toutes_leur_colonne_de_date() -> None:
    assert set(COLONNE_DATE) == set(cat.Base)
    for base, colonne in COLONNE_DATE.items():
        assert colonne in jeu().table(base).columns


# ------------------------------------------------- cohérence avec les socles
@pytest.mark.parametrize("niveau", list(Niveau))
def test_le_socle_de_chaque_niveau_existe_au_catalogue(niveau: Niveau) -> None:
    for cle in NIVEAUX[niveau].socle:
        assert cle in cat.MESURES, f"{niveau.value} : mesure de socle inconnue {cle!r}"


@pytest.mark.parametrize("niveau", list(Niveau))
def test_le_socle_est_eligible_a_son_niveau(niveau: Niveau) -> None:
    for cle in NIVEAUX[niveau].socle:
        cat.valider(cle, None, niveau)


@pytest.mark.parametrize("niveau", list(Niveau))
def test_chaque_niveau_a_de_quoi_explorer(niveau: Niveau) -> None:
    assert len(cat.mesures_du_niveau(niveau)) >= 5
    assert len(cat.dimensions_du_niveau(niveau)) >= 3
    assert len(cat.croisements_valides(niveau)) >= 20


def test_un_croisement_valide_est_calculable() -> None:
    """Le catalogue ne promet rien que le moteur ne sache tenir."""
    for cle_mesure, cle_dimension in cat.croisements_valides(Niveau.GESTION):
        ventiler(jeu(), cle_mesure, cle_dimension, Cadrage.DOUZE_MOIS, niveau=Niveau.GESTION)


# ---------------------------------------------------- validation des entrées
def test_une_mesure_inconnue_liste_les_disponibles() -> None:
    with pytest.raises(KeyError, match="ca_facture_ht"):
        cat.mesure("chiffre_affaire")


def test_une_dimension_inconnue_liste_les_disponibles() -> None:
    with pytest.raises(KeyError, match="agence"):
        cat.dimension("region")


def test_une_mesure_hors_niveau_est_refusee() -> None:
    with pytest.raises(ValueError, match="pas éligible"):
        cat.valider("ca_devise_ht", None, Niveau.STRATEGIQUE)


def test_un_croisement_impossible_est_refuse() -> None:
    """La marge se constate sur une facture ; un commercial n'en émet pas."""
    with pytest.raises(ValueError, match="commercial"):
        cat.valider("taux_marge_brute", "commercial", Niveau.GESTION)


def test_un_agregat_ne_peut_avoir_denominateur_et_distinct() -> None:
    with pytest.raises(ValueError, match="dénominateur"):
        cat.Agregat(numerateur="a", denominateur="b", distinct="c")


def test_une_mesure_a_exactement_un_mode_de_calcul() -> None:
    with pytest.raises(ValueError, match="exactement"):
        cat.Mesure(
            cle="x",
            libelle="X",
            base=cat.Base.DEVIS,
            unite=cat.Unite.EUROS,
            sens=cat.Sens.HAUT,
            niveaux=frozenset({Niveau.GESTION}),
        )


def test_un_filtre_sur_une_dimension_absente_est_refuse() -> None:
    with pytest.raises(ValueError, match="n'existe pas"):
        calculer(jeu(), "taux_marge_brute", Cadrage.DOUZE_MOIS, filtre={"commercial": "X"})


# --------------------------------------------------------------- les fenêtres
def test_lexercice_court_de_juillet_a_juin() -> None:
    f = fenetre(Cadrage.EXERCICE_COURANT, date(2026, 6, 30), date(2022, 7, 1))
    assert f.debut == date(2025, 7, 1)
    assert f.fin == date(2026, 6, 30)


def test_lexercice_precedent_ne_recouvre_pas_le_courant() -> None:
    situation, debut = date(2026, 6, 30), date(2022, 7, 1)
    courant = fenetre(Cadrage.EXERCICE_COURANT, situation, debut)
    precedent = fenetre(Cadrage.EXERCICE_PRECEDENT, situation, debut)
    assert precedent.fin < courant.debut


def test_les_douze_mois_glissants_couvrent_une_annee() -> None:
    f = fenetre(Cadrage.DOUZE_MOIS, date(2026, 6, 30), date(2022, 7, 1))
    assert f.jours == 365


def test_les_douze_mois_precedents_ne_recouvrent_pas_les_courants() -> None:
    situation, debut = date(2026, 6, 30), date(2022, 7, 1)
    courants = fenetre(Cadrage.DOUZE_MOIS, situation, debut)
    precedents = fenetre(Cadrage.DOUZE_MOIS_PRECEDENTS, situation, debut)
    assert precedents.fin < courants.debut


@pytest.mark.parametrize("niveau", list(Niveau))
def test_chaque_niveau_a_son_cadrage_et_sa_comparaison(niveau: Niveau) -> None:
    principal = PRINCIPAL[niveau]
    assert principal in COMPARAISON


# ------------------------------------------------------ invariants du moteur
def test_on_somme_avant_de_diviser() -> None:
    """La marge de trois agences n'est pas la moyenne de leurs trois taux."""
    v = ventiler(jeu(), "taux_marge_brute", "agence", Cadrage.DOUZE_MOIS)
    numerateurs = sum(m.numerateur for m in v.modalites)
    denominateurs = sum(m.denominateur or 0.0 for m in v.modalites)
    assert _proche(numerateurs, v.ensemble.numerateur)
    assert _proche(denominateurs, v.ensemble.denominateur)
    moyenne_naive = sum(m.valeur or 0.0 for m in v.modalites) / len(v.modalites)
    assert v.ensemble.valeur is not None
    assert abs(moyenne_naive - v.ensemble.valeur) > 1e-4, "les deux calculs doivent différer"


def test_les_effectifs_de_la_ventilation_couvrent_lensemble() -> None:
    v = ventiler(jeu(), "ca_facture_ht", "type_client", Cadrage.DOUZE_MOIS)
    assert sum(m.effectif for m in v.modalites) == v.ensemble.effectif


def test_les_poids_dune_ventilation_somment_a_un() -> None:
    v = ventiler(jeu(), "ca_facture_ht", "agence", Cadrage.DOUZE_MOIS)
    assert _proche(sum(m.poids for m in v.modalites), 1.0)


def test_une_dimension_ordonnee_conserve_son_ordre() -> None:
    v = ventiler(jeu(), "taux_transformation", "tranche_relance", Cadrage.DOUZE_MOIS)
    attendu = list(cat.dimension("tranche_relance").modalites)
    obtenu = [m.libelle for m in v.modalites]
    assert obtenu == [m for m in attendu if m in obtenu]


def test_les_extremes_suivent_le_sens_de_la_mesure() -> None:
    """Pour une mesure « plus bas mieux », la meilleure modalité est la plus basse."""
    v = ventiler(jeu(), "taux_derive_horaire", "anciennete_technicien", Cadrage.DOUZE_MOIS)
    extremes = v.extremes()
    assert extremes is not None
    meilleure, pire = extremes
    assert meilleure.valeur is not None and pire.valeur is not None
    assert meilleure.valeur < pire.valeur


def test_un_filtre_restreint_bien_le_calcul() -> None:
    total = calculer(jeu(), "ca_facture_ht", Cadrage.DOUZE_MOIS)
    parts = [
        calculer(jeu(), "ca_facture_ht", Cadrage.DOUZE_MOIS, filtre={"agence": a}).numerateur
        for a in ("Bordeaux", "Toulouse", "Montpellier")
    ]
    assert _proche(sum(parts), total.numerateur)


def test_une_fenetre_vide_ne_leve_pas() -> None:
    """Un cadrage sans donnée doit rendre une valeur non calculable, pas une erreur."""
    vide = charger(situation=date(2022, 7, 2))
    resultat = calculer(vide, "taux_marge_brute", Cadrage.TRENTE_JOURS)
    assert resultat.valeur is None or resultat.effectif == 0


def test_un_stock_ne_se_compare_pas_entre_deux_fenetres() -> None:
    resultat = comparer(
        jeu(), "encours_client", Cadrage.DOUZE_MOIS, Cadrage.DOUZE_MOIS_PRECEDENTS
    )
    assert resultat.ecart_relatif is None
    assert resultat.passee is None
    assert resultat.motif is not None and "stock" in resultat.motif


def test_un_flux_se_compare_normalement() -> None:
    resultat = comparer(
        jeu(), "ca_facture_ht", Cadrage.DOUZE_MOIS, Cadrage.DOUZE_MOIS_PRECEDENTS
    )
    assert resultat.ecart_relatif is not None
    assert resultat.motif is None


@pytest.mark.parametrize(
    "cle", ["encours_client", "dso", "age_moyen_file_recouvrement", "exceptions_ouvertes"]
)
def test_les_mesures_detat_sont_marquees_stock(cle: str) -> None:
    assert cat.MESURES[cle].nature is cat.Nature.STOCK


def test_la_serie_mensuelle_couvre_toute_la_periode() -> None:
    points = serie_mensuelle(jeu(), "ca_facture_ht")
    assert len(points) >= 46
    assert points[0].mois < points[-1].mois


# ------------------------------------------------------ fichier de référence
def test_le_contexte_de_reference_est_inchange() -> None:
    attendu = reference()
    assert jeu().situation.isoformat() == attendu["situation"]
    assert jeu().debut.isoformat() == attendu["debut"]
    assert jeu().volumes() == attendu["volumes"]


def test_toutes_les_valeurs_de_reference_concordent() -> None:
    attendues = reference()["valeurs"]
    assert isinstance(attendues, dict)
    ecarts: list[str] = []
    for cle_composee, attendu in attendues.items():
        cle_mesure, cadrage = cle_composee.split("|")
        obtenu = calculer(jeu(), cle_mesure, Cadrage(cadrage))
        if not _proche(obtenu.valeur, attendu["valeur"]) or obtenu.effectif != attendu["effectif"]:
            ecarts.append(f"{cle_composee} : {obtenu.valeur} au lieu de {attendu['valeur']}")
    assert not ecarts, "\n".join(ecarts)


def test_toutes_les_ventilations_de_reference_concordent() -> None:
    attendues = reference()["ventilations"]
    assert isinstance(attendues, dict)
    ecarts: list[str] = []
    for cle_composee, attendu in attendues.items():
        cle_mesure, cle_dimension = cle_composee.split("|")
        obtenue = ventiler(jeu(), cle_mesure, cle_dimension, Cadrage.DOUZE_MOIS)
        if not _proche(obtenue.ensemble.valeur, attendu["ensemble"]):
            ecarts.append(f"{cle_composee} : ensemble")
        for modalite in obtenue.modalites:
            cible = attendu["modalites"].get(modalite.libelle)
            if cible is None:
                ecarts.append(f"{cle_composee} : modalité inattendue {modalite.libelle!r}")
            elif not _proche(modalite.valeur, cible["valeur"]):
                ecarts.append(f"{cle_composee}/{modalite.libelle}")
    assert not ecarts, "\n".join(ecarts)


def test_les_series_de_reference_concordent() -> None:
    attendues = reference()["series"]
    assert isinstance(attendues, dict)
    for cle, attendu in attendues.items():
        points = serie_mensuelle(jeu(), cle)
        assert len(points) == attendu["nb_points"], cle
        assert points[0].mois == attendu["premier"][0]
        assert _proche(points[0].valeur, attendu["premier"][1])
        assert points[-1].mois == attendu["dernier"][0]
        assert _proche(points[-1].valeur, attendu["dernier"][1])
