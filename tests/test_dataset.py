"""Reproductibilité du générateur et invariants métier du jeu de données.

Deux familles de tests, aux rôles distincts.

Les tests de **reproductibilité** protègent la démonstration : les CSV sont
versionnés, les prompts sont calibrés dessus, et le classeur du jalon 4 est
vérifié contre leurs agrégats. Une modification involontaire du générateur doit
se voir immédiatement, pas trois jalons plus tard.

Les tests d'**invariants** protègent la crédibilité : un jeu fictif qui contient
une facture sans devis, ou une intervention antérieure à l'embauche du
technicien, ne survit pas à un client qui regarde de près. Ils vérifient aussi
la trajectoire d'entreprise, car c'est elle que l'agent devra constater.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date
from functools import cache
from pathlib import Path

import pytest

from loom_report_demo import paths
from loom_report_demo.dataset import generer
from loom_report_demo.dataset import parametres as P
from loom_report_demo.dataset.generateur import (
    JeuDeDonnees,
    ecrire,
    exercice,
    mois_key,
)
from loom_report_demo.fingerprint import empreinte_jeu

#: Empreinte du jeu de données versionné dans `assets/data`. Toute évolution
#: volontaire du générateur ou de ses paramètres demande de la mettre à jour —
#: et c'est précisément le geste que l'on veut rendre explicite.
EMPREINTE_REFERENCE = (
    "266077f091a13a48"
    "850145d4c652c30d"
    "fe4fa49d6b81c7d4"
    "5e8eee21611d44f4"
)

VOLUMES_REFERENCE = {
    "clients": 1019,
    "techniciens": 12,
    "catalogue": 20,
    "devis": 3052,
    "relances": 3167,
    "interventions": 1105,
    "factures": 1084,
}

EXERCICES = ("2022-2023", "2023-2024", "2024-2025", "2025-2026")


@cache
def jeu() -> JeuDeDonnees:
    """Une seule génération pour tout le module : environ 0,25 s."""
    return generer()


# ------------------------------------------------------------ reproductibilité
def test_la_graine_fixe_entierement_la_sortie() -> None:
    assert generer(P.GRAINE) == generer(P.GRAINE)


def test_une_autre_graine_produit_un_autre_jeu() -> None:
    assert generer(P.GRAINE + 1) != generer(P.GRAINE)


def test_les_volumes_sont_ceux_de_reference() -> None:
    assert jeu().volumes() == VOLUMES_REFERENCE


def test_le_jeu_versionne_correspond_au_generateur(tmp_path: Path) -> None:
    """Le contrôle central du jalon : `uv run seed` ne doit rien changer."""
    produits = ecrire(jeu(), tmp_path)
    versionnes = [paths.csv_source(nom) for nom in paths.FICHIERS_DONNEES]
    assert empreinte_jeu(produits).globale == empreinte_jeu(versionnes).globale


def test_lempreinte_de_reference_est_a_jour(tmp_path: Path) -> None:
    assert empreinte_jeu(ecrire(jeu(), tmp_path)).globale == EMPREINTE_REFERENCE


# -------------------------------------------------------- intégrité des liens
def test_tout_devis_reference_un_client_existant() -> None:
    connus = {c["client_id"] for c in jeu().clients}
    orphelins = {d["devis_id"] for d in jeu().devis if d["client_id"] not in connus}
    assert not orphelins


def test_toute_relance_reference_un_devis_existant() -> None:
    connus = {d["devis_id"] for d in jeu().devis}
    assert all(r["devis_id"] in connus for r in jeu().relances)


def test_toute_intervention_porte_sur_un_devis_accepte() -> None:
    acceptes = {d["devis_id"] for d in jeu().devis if d["statut"] == "Accepté"}
    assert all(i["devis_id"] in acceptes for i in jeu().interventions)


def test_toute_facture_porte_sur_un_devis_accepte() -> None:
    acceptes = {d["devis_id"] for d in jeu().devis if d["statut"] == "Accepté"}
    assert all(f["devis_id"] in acceptes for f in jeu().factures)


def test_toute_facture_a_son_intervention() -> None:
    """Une facture sans intervention serait une prestation facturée non réalisée."""
    realises = {i["devis_id"] for i in jeu().interventions}
    assert all(f["devis_id"] in realises for f in jeu().factures)


def test_un_devis_ne_donne_quune_intervention_et_une_facture() -> None:
    for table in (jeu().interventions, jeu().factures):
        doublons = [d for d, n in Counter(x["devis_id"] for x in table).items() if n > 1]
        assert not doublons


@pytest.mark.parametrize(
    ("table", "cle"),
    [
        ("clients", "client_id"),
        ("techniciens", "technicien_id"),
        ("catalogue", "code_prestation"),
        ("devis", "devis_id"),
        ("relances", "relance_id"),
        ("interventions", "intervention_id"),
        ("factures", "facture_id"),
    ],
)
def test_les_identifiants_sont_uniques(table: str, cle: str) -> None:
    lignes = jeu().table(table)
    assert len({x[cle] for x in lignes}) == len(lignes)


# ------------------------------------------------------- cohérence temporelle
@pytest.mark.parametrize(
    ("table", "champ"),
    [
        ("devis", "date_emission"),
        ("relances", "date_relance"),
        ("interventions", "date_intervention"),
        ("factures", "date_facture"),
    ],
)
def test_aucun_mouvement_hors_periode(table: str, champ: str) -> None:
    dates = [x[champ] for x in jeu().table(table)]
    assert min(dates) >= P.DATE_DEBUT
    assert max(dates) <= P.DATE_FIN


def test_aucun_paiement_apres_la_date_de_situation() -> None:
    regles = [f["date_paiement"] for f in jeu().factures if f["date_paiement"] is not None]
    assert max(regles) <= P.AUJOURDHUI


def test_aucune_intervention_avant_lembauche_du_technicien() -> None:
    embauches = {t[0]: t[6] for t in P.TECHNICIENS}
    fautives = [
        i["intervention_id"]
        for i in jeu().interventions
        if i["date_intervention"] < embauches[i["technicien_id"]]
    ]
    assert not fautives


def test_aucun_devis_montpellier_avant_louverture() -> None:
    premiers = [d["date_emission"] for d in jeu().devis if d["agence"] == "Montpellier"]
    assert min(premiers) >= P.OUVERTURE_MONTPELLIER


def test_aucun_commercial_avant_son_arrivee() -> None:
    arrivees = {c[0]: c[2] for c in P.COMMERCIAUX}
    fautifs = [
        d["devis_id"] for d in jeu().devis if d["date_emission"] < arrivees[d["commercial"]]
    ]
    assert not fautifs


def test_la_decision_ne_precede_jamais_lemission() -> None:
    for d in jeu().devis:
        if d["date_decision"] is not None:
            assert d["date_decision"] >= d["date_emission"], d["devis_id"]


def test_la_relance_ne_precede_jamais_lemission() -> None:
    emissions = {d["devis_id"]: d["date_emission"] for d in jeu().devis}
    assert all(r["date_relance"] >= emissions[r["devis_id"]] for r in jeu().relances)


def test_lintervention_suit_la_decision() -> None:
    decisions = {d["devis_id"]: d["date_decision"] for d in jeu().devis}
    for i in jeu().interventions:
        attendue = decisions[i["devis_id"]]
        assert attendue is not None
        assert i["date_intervention"] >= attendue, i["intervention_id"]


def test_la_facture_suit_lintervention() -> None:
    realisations = {i["devis_id"]: i["date_intervention"] for i in jeu().interventions}
    assert all(f["date_facture"] >= realisations[f["devis_id"]] for f in jeu().factures)


def test_le_paiement_ne_precede_jamais_la_facture() -> None:
    for f in jeu().factures:
        if f["date_paiement"] is not None:
            assert f["date_paiement"] >= f["date_facture"], f["facture_id"]


def test_aucune_intervention_le_week_end() -> None:
    assert all(i["date_intervention"].weekday() < 5 for i in jeu().interventions)


@pytest.mark.parametrize(
    ("table", "champ"),
    [
        ("devis", "date_emission"),
        ("relances", "date_relance"),
        ("interventions", "date_intervention"),
        ("factures", "date_facture"),
    ],
)
def test_les_colonnes_mois_et_exercice_suivent_la_date(table: str, champ: str) -> None:
    for ligne in jeu().table(table):
        reference: date = ligne[champ]
        assert ligne["mois"] == mois_key(reference)
        assert ligne["exercice"] == exercice(reference)


# ------------------------------------------------------- cohérence des valeurs
def test_le_ttc_decoule_du_ht_et_du_taux() -> None:
    for f in jeu().factures:
        attendu = round(f["montant_ht"] * (1 + f["taux_tva"]), 2)
        assert abs(f["montant_ttc"] - attendu) < 0.005, f["facture_id"]


def test_lecheance_decoule_du_delai_contractuel() -> None:
    from datetime import timedelta

    for f in jeu().factures:
        assert f["date_echeance"] == f["date_facture"] + timedelta(days=f["delai_contractuel_j"])


def test_le_delai_contractuel_suit_le_type_de_client() -> None:
    assert all(
        f["delai_contractuel_j"] == P.DELAI_PAIEMENT[f["type_client"]] for f in jeu().factures
    )


def test_le_statut_de_facture_est_coherent_avec_le_paiement() -> None:
    for f in jeu().factures:
        if f["date_paiement"] is not None:
            assert f["statut_facture"] == "Payée", f["facture_id"]
        else:
            attendu = "En retard" if f["date_echeance"] < P.AUJOURDHUI else "En attente"
            assert f["statut_facture"] == attendu, f["facture_id"]


def test_un_devis_en_cours_na_pas_de_decision() -> None:
    for d in jeu().devis:
        if d["statut"] == "En cours":
            assert d["date_decision"] is None
        else:
            assert d["date_decision"] is not None


def test_le_cout_de_main_doeuvre_decoule_des_heures() -> None:
    for i in jeu().interventions:
        attendu = round(i["heures_reelles"] * i["cout_horaire"], 2)
        assert abs(i["cout_main_oeuvre"] - attendu) < 0.005, i["intervention_id"]


def test_le_technicien_appartient_a_lagence_du_devis() -> None:
    agences = {d["devis_id"]: d["agence"] for d in jeu().devis}
    assert all(i["agence"] == agences[i["devis_id"]] for i in jeu().interventions)


def test_le_code_prestation_existe_au_catalogue() -> None:
    connus = {p["code_prestation"] for p in jeu().catalogue}
    assert all(d["code_prestation"] in connus for d in jeu().devis)


def test_la_categorie_du_devis_suit_celle_de_la_prestation() -> None:
    categories = {p["code_prestation"]: p["categorie"] for p in jeu().catalogue}
    assert all(d["categorie"] == categories[d["code_prestation"]] for d in jeu().devis)


def test_les_prestations_lourdes_ne_se_commandent_pas_par_lots() -> None:
    """Sans cette garde, un devis isolé ferait bouger le CA d'un exercice."""
    prix = {p["code_prestation"]: p["prix_unitaire_ht"] for p in jeu().catalogue}
    assert all(
        d["quantite"] == 1 for d in jeu().devis if prix[d["code_prestation"]] > P.PLAFOND_LOT
    )


# --------------------------------------------------------------- les relances
def test_les_rangs_de_relance_sont_consecutifs_a_partir_de_un() -> None:
    par_devis: defaultdict[str, list[int]] = defaultdict(list)
    for r in jeu().relances:
        par_devis[r["devis_id"]].append(r["rang"])
    for devis_id, rangs in par_devis.items():
        assert sorted(rangs) == list(range(1, len(rangs) + 1)), devis_id


def test_le_compteur_du_devis_egale_le_nombre_de_relances() -> None:
    comptes = Counter(r["devis_id"] for r in jeu().relances)
    for d in jeu().devis:
        assert d["nb_relances"] == comptes.get(d["devis_id"], 0), d["devis_id"]


def test_un_devis_sans_delai_de_relance_na_aucune_relance() -> None:
    relances = {r["devis_id"] for r in jeu().relances}
    jamais = [d["devis_id"] for d in jeu().devis if d["delai_1ere_relance_j"] is None]
    assert not (set(jamais) & relances)


def test_laccord_ou_le_refus_ne_clot_que_les_devis_correspondants() -> None:
    statuts = {d["devis_id"]: d["statut"] for d in jeu().devis}
    for r in jeu().relances:
        if r["issue"] == "Accord obtenu":
            assert statuts[r["devis_id"]] == "Accepté"
        elif r["issue"] == "Refus signifié":
            assert statuts[r["devis_id"]] == "Refusé"


# ------------------------------------------------ la trajectoire d'entreprise
def _par_exercice(lignes: tuple[object, ...], champ: str) -> dict[str, float]:
    total: defaultdict[str, float] = defaultdict(float)
    for ligne in lignes:
        assert isinstance(ligne, dict)
        total[ligne["exercice"]] += ligne[champ]
    return dict(total)


def test_le_chiffre_daffaires_progresse_puis_plafonne() -> None:
    ca = _par_exercice(jeu().factures, "montant_ht")
    valeurs = [ca[e] for e in EXERCICES]
    assert valeurs == sorted(valeurs), "le CA doit progresser sur les quatre exercices"
    croissance_finale = valeurs[3] / valeurs[2] - 1
    assert croissance_finale < 0.10, "le dernier exercice doit plafonner"


def test_le_taux_de_marge_se_degrade_a_chaque_exercice() -> None:
    """La marge est le premier symptôme de la croissance mal absorbée."""
    couts = {i["devis_id"]: i["cout_main_oeuvre"] + i["cout_materiel"] for i in jeu().interventions}
    ca: defaultdict[str, float] = defaultdict(float)
    marge: defaultdict[str, float] = defaultdict(float)
    for f in jeu().factures:
        ca[f["exercice"]] += f["montant_ht"]
        marge[f["exercice"]] += f["montant_ht"] - couts.get(f["devis_id"], 0.0)
    taux = [marge[e] / ca[e] for e in EXERCICES]
    assert taux == sorted(taux, reverse=True), f"taux non décroissants : {taux}"
    assert taux[0] - taux[3] > 0.05, "la dégradation doit être visible"


def test_la_discipline_de_relance_se_degrade() -> None:
    total: defaultdict[str, int] = defaultdict(int)
    jamais: defaultdict[str, int] = defaultdict(int)
    for d in jeu().devis:
        if d["statut"] == "En cours":
            continue
        total[d["exercice"]] += 1
        if d["delai_1ere_relance_j"] is None:
            jamais[d["exercice"]] += 1
    parts = [jamais[e] / total[e] for e in EXERCICES]
    assert parts == sorted(parts), f"parts non croissantes : {parts}"


def test_la_transformation_recule() -> None:
    arbitres: defaultdict[str, float] = defaultdict(float)
    gagnes: defaultdict[str, float] = defaultdict(float)
    for d in jeu().devis:
        if d["statut"] == "En cours":
            continue
        arbitres[d["exercice"]] += d["montant_ht"]
        if d["statut"] == "Accepté":
            gagnes[d["exercice"]] += d["montant_ht"]
    taux = [gagnes[e] / arbitres[e] for e in EXERCICES]
    assert taux[3] < taux[0] - 0.05, f"la transformation doit reculer : {taux}"


def test_leffectif_croit_par_vagues() -> None:
    actifs = {e: set() for e in EXERCICES}
    for i in jeu().interventions:
        actifs[i["exercice"]].add(i["technicien_id"])
    effectifs = [len(actifs[e]) for e in EXERCICES]
    assert effectifs == sorted(effectifs)
    assert effectifs[0] < effectifs[-1], "l'entreprise doit avoir embauché"


def test_montpellier_ne_cannibalise_pas_toulouse() -> None:
    """Une agence nouvelle conquiert un territoire, elle ne prend pas les clients
    de la voisine : le volume de Toulouse ne doit pas reculer à l'ouverture."""
    volumes: defaultdict[tuple[str, str], int] = defaultdict(int)
    for d in jeu().devis:
        volumes[d["agence"], d["exercice"]] += 1
    avant = volumes["Toulouse", "2023-2024"]
    apres = volumes["Toulouse", "2024-2025"]
    assert apres >= avant * 0.95, f"Toulouse recule : {avant} puis {apres}"
    assert volumes["Montpellier", "2025-2026"] > volumes["Montpellier", "2024-2025"]


def test_les_creances_anciennes_existent() -> None:
    """Sans queue de créances, la balance âgée du classeur n'a rien à montrer."""
    ouvertes = [f for f in jeu().factures if f["date_paiement"] is None]
    assert len(ouvertes) >= 20
    tres_anciennes = [f for f in ouvertes if (P.AUJOURDHUI - f["date_echeance"]).days > 90]
    assert tres_anciennes, "aucune créance de plus de 90 jours"
