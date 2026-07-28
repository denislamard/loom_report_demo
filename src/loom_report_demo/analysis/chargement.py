"""Lecture des exports et construction des trois tables de faits.

Un seul module touche aux jointures. Le moteur, lui, ne connaît que des colonnes
plates : c'est ce qui permet à l'algèbre des agrégats de rester pauvre, et au
catalogue de rester déclaratif.

Toutes les colonnes calculées ici sont référencées par `catalogue.py`. Un test
vérifie la réciproque : aucune colonne attendue par une mesure ou une dimension
ne doit manquer. Cette paire — déclaration d'un côté, construction de l'autre —
est le seul endroit où les deux fichiers doivent rester d'accord.

Toutes les mesures d'un même agrégat sont sommées AVANT division. Les colonnes
en `_pondere` et les indicatrices en 0/1 existent pour cette raison : elles
transforment une moyenne conditionnelle en un simple rapport de deux sommes,
donc en quelque chose qui s'agrège correctement sur n'importe quelle dimension.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path

import pandas as pd

from loom_report_demo import paths
from loom_report_demo.analysis.catalogue import Base

#: Ancienneté à partir de laquelle une créance sort du suivi courant.
SEUIL_EXCEPTION_JOURS = 90

#: Seuil de réactivité au-delà duquel la transformation chute nettement.
SEUIL_RELANCE_RAPIDE_JOURS = 3

_TRANCHES_MONTANT = ((1_000, "Moins de 1 k€"), (5_000, "1 à 5 k€"), (15_000, "5 à 15 k€"))
_TRANCHE_MONTANT_HAUTE = "Plus de 15 k€"

_TRANCHES_RELANCE = ((3, "0-3 j"), (7, "4-7 j"), (15, "8-15 j"))
_TRANCHE_RELANCE_HAUTE = "Plus de 15 j"
_JAMAIS_RELANCE = "Jamais relancé"

_TRANCHES_AGE = ((0, "Non échu"), (30, "1-30 j"), (60, "31-60 j"), (90, "61-90 j"))
_TRANCHE_AGE_HAUTE = "Plus de 90 j"
_REGLEE = "Réglée"

_TRANCHES_ANCIENNETE = ((365, "Moins d'un an"), (730, "1 à 2 ans"))
_ANCIENNETE_HAUTE = "Plus de 2 ans"

#: Colonne portant la date qui sert au découpage temporel, par table de faits.
COLONNE_DATE: dict[Base, str] = {
    Base.DEVIS: "date_emission",
    Base.FACTURES: "date_facture",
    Base.INTERVENTIONS: "date_intervention",
}


@dataclass(frozen=True, slots=True)
class Donnees:
    """Les trois tables de faits enrichies, plus les référentiels."""

    devis: pd.DataFrame
    factures: pd.DataFrame
    interventions: pd.DataFrame
    clients: pd.DataFrame
    techniciens: pd.DataFrame
    catalogue: pd.DataFrame
    relances: pd.DataFrame
    situation: date
    debut: date

    def table(self, base: Base) -> pd.DataFrame:
        return {
            Base.DEVIS: self.devis,
            Base.FACTURES: self.factures,
            Base.INTERVENTIONS: self.interventions,
        }[base]

    def volumes(self) -> dict[str, int]:
        return {
            "clients": len(self.clients),
            "techniciens": len(self.techniciens),
            "catalogue": len(self.catalogue),
            "devis": len(self.devis),
            "relances": len(self.relances),
            "interventions": len(self.interventions),
            "factures": len(self.factures),
        }


def _tranche(valeur: float, seuils: tuple[tuple[float, str], ...], haute: str) -> str:
    for borne, libelle in seuils:
        if valeur <= borne:
            return libelle
    return haute


def _lire(dossier: Path, nom: str, dates: list[str]) -> pd.DataFrame:
    return pd.read_csv(dossier / nom, sep=";", parse_dates=dates)


def charger(dossier: Path | None = None, situation: date | None = None) -> Donnees:
    """Lit les sept exports et construit les tables de faits enrichies."""
    source = dossier if dossier is not None else paths.donnees()

    clients = _lire(source, "clients.csv", ["date_creation"])
    techniciens = _lire(source, "techniciens.csv", ["date_embauche"])
    catalogue = _lire(source, "catalogue_prestations.csv", [])
    devis = _lire(source, "devis.csv", ["date_emission", "date_decision"])
    relances = _lire(source, "relances.csv", ["date_relance"])
    interventions = _lire(source, "interventions.csv", ["date_intervention"])
    factures = _lire(
        source, "factures.csv", ["date_facture", "date_echeance", "date_paiement"]
    )

    # La date de situation par défaut est le dernier mouvement observé : le jeu
    # ne contient rien au-delà, et la déduire évite de la maintenir en double.
    jour = situation if situation is not None else max(
        devis["date_emission"].max(), factures["date_facture"].max()
    ).date()
    debut = devis["date_emission"].min().date()
    horodatage = pd.Timestamp(jour)

    # ------------------------------------------------------------- devis
    devis = devis.merge(
        clients[["client_id", "canal_acquisition", "profil_paiement"]],
        on="client_id",
        how="left",
    )
    devis["metier"] = devis["categorie"]
    devis["prestation"] = devis["libelle_prestation"]
    devis["ligne"] = 1
    devis["arbitre"] = (devis["statut"] != "En cours").astype(int)
    devis["est_gagne"] = (devis["statut"] == "Accepté").astype(int)
    devis["ca_gagne"] = devis["montant_ht"] * devis["est_gagne"]
    devis["montant_arbitre"] = devis["montant_ht"] * devis["arbitre"]
    devis["est_relance"] = devis["delai_1ere_relance_j"].notna().astype(int)
    devis["delai_relance_pondere"] = devis["delai_1ere_relance_j"].fillna(0.0)
    devis["relance_rapide"] = (
        devis["delai_1ere_relance_j"].fillna(9_999) <= SEUIL_RELANCE_RAPIDE_JOURS
    ).astype(int)
    devis["tranche_relance"] = [
        _JAMAIS_RELANCE if pd.isna(d) else _tranche(d, _TRANCHES_RELANCE, _TRANCHE_RELANCE_HAUTE)
        for d in devis["delai_1ere_relance_j"]
    ]
    devis["tranche_montant"] = [
        _tranche(m, _TRANCHES_MONTANT, _TRANCHE_MONTANT_HAUTE) for m in devis["montant_ht"]
    ]

    # ------------------------------------------------------ interventions
    cout = interventions["cout_main_oeuvre"] + interventions["cout_materiel"]
    interventions = interventions.merge(
        devis[["devis_id", "montant_ht"]].rename(columns={"montant_ht": "ca_lie"}),
        on="devis_id",
        how="left",
    ).merge(
        techniciens[["technicien_id", "date_embauche"]], on="technicien_id", how="left"
    )
    interventions["cout_total"] = cout.to_numpy()
    interventions["marge"] = interventions["ca_lie"] - interventions["cout_total"]
    interventions["metier"] = interventions["categorie"]
    interventions["ligne"] = 1
    anciennete = (
        interventions["date_intervention"] - interventions["date_embauche"]
    ).dt.days
    interventions["anciennete_jours"] = anciennete
    interventions["anciennete_technicien"] = [
        _tranche(a, _TRANCHES_ANCIENNETE, _ANCIENNETE_HAUTE) for a in anciennete
    ]

    # ---------------------------------------------------------- factures
    factures = (
        factures.merge(
            interventions[["devis_id", "cout_total"]].rename(
                columns={"cout_total": "cout_revient"}
            ),
            on="devis_id",
            how="left",
        )
        .merge(
            devis[["devis_id", "categorie", "libelle_prestation", "code_prestation"]],
            on="devis_id",
            how="left",
        )
        .merge(clients[["client_id", "canal_acquisition"]], on="client_id", how="left")
    )
    factures["cout_revient"] = factures["cout_revient"].fillna(0.0)
    factures["marge"] = factures["montant_ht"] - factures["cout_revient"]
    factures["metier"] = factures["categorie"]
    factures["prestation"] = factures["libelle_prestation"]
    factures["ligne"] = 1
    factures["est_payee"] = factures["date_paiement"].notna().astype(int)
    factures["encours"] = factures["montant_ttc"] * (1 - factures["est_payee"])

    # Le retard d'une facture réglée est celui constaté au paiement ; celui d'une
    # facture ouverte court jusqu'à la date de situation.
    retard_regle = (factures["date_paiement"] - factures["date_echeance"]).dt.days
    retard_ouvert = (horodatage - factures["date_echeance"]).dt.days
    factures["retard"] = (
        retard_regle.where(factures["est_payee"] == 1, retard_ouvert).clip(lower=0).fillna(0)
    )
    factures["retard_pondere"] = factures["retard"] * factures["encours"]
    delai_reel = (factures["date_paiement"] - factures["date_facture"]).dt.days
    factures["delai_reel"] = delai_reel
    factures["delai_reel_pondere"] = delai_reel.fillna(0.0)
    factures["en_retard"] = (
        (factures["est_payee"] == 0) & (factures["date_echeance"] < horodatage)
    ).astype(int)
    factures["exception"] = (
        (factures["est_payee"] == 0) & (factures["retard"] > SEUIL_EXCEPTION_JOURS)
    ).astype(int)
    factures["tranche_age_creance"] = [
        _REGLEE if payee else _tranche(r, _TRANCHES_AGE, _TRANCHE_AGE_HAUTE)
        for payee, r in zip(factures["est_payee"] == 1, factures["retard"], strict=True)
    ]
    factures["tranche_montant"] = [
        _tranche(m, _TRANCHES_MONTANT, _TRANCHE_MONTANT_HAUTE) for m in factures["montant_ht"]
    ]

    return Donnees(
        devis=devis,
        factures=factures,
        interventions=interventions,
        clients=clients,
        techniciens=techniciens,
        catalogue=catalogue,
        relances=relances,
        situation=jour,
        debut=debut,
    )


@lru_cache(maxsize=4)
def _charger_cache(dossier: str, situation: date | None) -> Donnees:
    return charger(Path(dossier), situation)


def donnees(dossier: Path | None = None, situation: date | None = None) -> Donnees:
    """Chargement mémoïsé : lire quatre mégaoctets une fois par processus suffit."""
    source = dossier if dossier is not None else paths.donnees()
    return _charger_cache(str(source), situation)
