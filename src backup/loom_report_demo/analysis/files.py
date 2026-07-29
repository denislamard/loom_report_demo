"""Files de travail : l'objet que produit le niveau opérationnel.

Ce n'est pas un tableau de bord. Un tableau de bord se contemple ; une file de
travail se traite. La différence n'est pas cosmétique — elle change la nature du
livrable, et c'est pour cela que `DefinitionNiveau` porte un attribut `livrable`
plutôt qu'un simple libellé.

Trois files, chacune adossée à un processus réel de l'entreprise : les créances à
appeler, les devis à relancer, les interventions dont les heures dérivent. Le
tri n'est pas cosmétique non plus : il détermine dans quel ordre un artisan qui a
deux heures devant lui va travailler. Chaque file porte donc une **priorité**
explicite, et le motif de cette priorité.

L'agent ne choisit pas les files — elles sont dictées par les processus. Il
choisit les **seuils** : à partir de quel retard une créance passe en
recouvrement, à partir de quelle dérive une intervention mérite un examen. C'est
un jugement, pas une mesure, et c'est exactement ce qu'on lui demande.

Ce module ne connaît ni `openpyxl` ni `loom_ia` : il rend des structures que le
classeur affiche et que l'export JSON transmet à un agent de relance.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

import pandas as pd

from loom_report_demo.analysis.chargement import Donnees

#: Nombre maximal de lignes par file. Au-delà, ce n'est plus une liste de
#: travail : c'est un export, et personne ne la traite.
MAX_LIGNES = 25

#: Seuils par défaut, appliqués quand l'agent n'en propose pas.
SEUIL_RECOUVREMENT_JOURS = 90
SEUIL_RELANCE_JOURS = 7
SEUIL_DERIVE = 0.15


@dataclass(frozen=True, slots=True)
class Tache:
    """Une unité à traiter, avec de quoi décider sans ouvrir un autre écran."""

    reference: str
    libelle: str
    montant: float
    anciennete_jours: int
    priorite: float
    motif: str
    detail: dict[str, Any]

    def en_dict(self) -> dict[str, Any]:
        return {
            "reference": self.reference,
            "libelle": self.libelle,
            "montant": round(self.montant, 2),
            "anciennete_jours": self.anciennete_jours,
            "priorite": round(self.priorite, 2),
            "motif": self.motif,
            **self.detail,
        }


@dataclass(frozen=True, slots=True)
class File:
    cle: str
    titre: str
    unite_montant: str
    #: Ce que l'agent, ou le programme à défaut, a retenu comme seuil.
    seuil: float
    seuil_libelle: str
    taches: tuple[Tache, ...]
    total_candidats: int

    @property
    def montant_total(self) -> float:
        return sum(t.montant for t in self.taches)

    def en_dict(self) -> dict[str, Any]:
        return {
            "file": self.cle,
            "titre": self.titre,
            "seuil": self.seuil,
            "seuil_libelle": self.seuil_libelle,
            "total_candidats": self.total_candidats,
            "affichees": len(self.taches),
            "montant_total": round(self.montant_total, 2),
            "taches": [t.en_dict() for t in self.taches],
        }


def _nom_client(donnees: Donnees, client_id: str) -> str:
    ligne = donnees.clients.loc[donnees.clients["client_id"] == client_id, "nom_client"]
    return str(ligne.iloc[0]) if len(ligne) else client_id


def creances_a_appeler(
    donnees: Donnees, seuil_jours: float = SEUIL_RECOUVREMENT_JOURS
) -> File:
    """Factures ouvertes et échues, les plus lourdes et les plus vieilles d'abord.

    La priorité est le produit du montant par l'ancienneté : un petit impayé très
    ancien et un gros impayé récent méritent tous deux un appel, mais un gros
    impayé très ancien passe avant les deux.
    """
    ouvertes = donnees.factures[
        (donnees.factures["est_payee"] == 0) & (donnees.factures["retard"] > 0)
    ].copy()
    total = len(ouvertes)
    ouvertes["priorite"] = ouvertes["encours"] * ouvertes["retard"]
    ouvertes = ouvertes.sort_values("priorite", ascending=False).head(MAX_LIGNES)

    taches = tuple(
        Tache(
            reference=str(ligne["facture_id"]),
            libelle=_nom_client(donnees, str(ligne["client_id"])),
            montant=float(ligne["encours"]),
            anciennete_jours=int(ligne["retard"]),
            priorite=float(ligne["priorite"]),
            motif=(
                "recouvrement"
                if ligne["retard"] > seuil_jours
                else "relance amiable"
            ),
            detail={
                "type_client": str(ligne["type_client"]),
                "agence": str(ligne["agence"]),
                "profil_paiement": str(ligne["profil_paiement"]),
                "echeance": ligne["date_echeance"].date().isoformat(),
            },
        )
        for _, ligne in ouvertes.iterrows()
    )
    return File(
        cle="creances",
        titre="Créances à appeler",
        unite_montant="€ TTC",
        seuil=seuil_jours,
        seuil_libelle=f"passage en recouvrement au-delà de {seuil_jours:.0f} jours de retard",
        taches=taches,
        total_candidats=total,
    )


def devis_a_relancer(
    donnees: Donnees, situation: date, seuil_jours: float = SEUIL_RELANCE_JOURS
) -> File:
    """Devis encore ouverts, jamais relancés ou relancés trop tard.

    Le tri par montant est volontaire : à délai comparable, c'est le montant qui
    décide de l'ordre des appels. Un devis relancé sous trois jours se transforme
    trois fois mieux qu'un devis jamais relancé — l'ordre a donc une valeur.
    """
    devis = donnees.devis
    ouverts = devis[devis["statut"] == "En cours"].copy()
    ouverts["age"] = (pd.Timestamp(situation) - ouverts["date_emission"]).dt.days
    en_retard = ouverts[
        ouverts["delai_1ere_relance_j"].isna() & (ouverts["age"] > seuil_jours)
    ].copy()
    total = len(en_retard)
    en_retard = en_retard.sort_values("montant_ht", ascending=False).head(MAX_LIGNES)

    taches = tuple(
        Tache(
            reference=str(ligne["devis_id"]),
            libelle=str(ligne["libelle_prestation"]),
            montant=float(ligne["montant_ht"]),
            anciennete_jours=int(ligne["age"]),
            priorite=float(ligne["montant_ht"]),
            motif="jamais relancé",
            detail={
                "commercial": str(ligne["commercial"]),
                "agence": str(ligne["agence"]),
                "type_client": str(ligne["type_client"]),
                "metier": str(ligne["metier"]),
            },
        )
        for _, ligne in en_retard.iterrows()
    )
    return File(
        cle="devis",
        titre="Devis à relancer",
        unite_montant="€ HT",
        seuil=seuil_jours,
        seuil_libelle=f"relance attendue sous {seuil_jours:.0f} jours après émission",
        taches=taches,
        total_candidats=total,
    )


def interventions_en_derive(donnees: Donnees, seuil: float = SEUIL_DERIVE) -> File:
    """Interventions dont les heures passées dépassent nettement les heures devisées.

    Le montant est le surcoût de main-d'œuvre, pas le chiffre d'affaires : c'est
    lui qui dit ce que la dérive a coûté, et donc s'il faut revoir le chiffrage.
    """
    interventions = donnees.interventions.copy()
    interventions = interventions[interventions["heures_devisees"] > 0]
    interventions["derive"] = (
        interventions["heures_reelles"] / interventions["heures_devisees"] - 1
    )
    depassements = interventions[interventions["derive"] > seuil].copy()
    total = len(depassements)
    depassements["surcout"] = (
        depassements["heures_reelles"] - depassements["heures_devisees"]
    ) * depassements["cout_horaire"]
    depassements = depassements.sort_values("surcout", ascending=False).head(MAX_LIGNES)

    taches = tuple(
        Tache(
            reference=str(ligne["intervention_id"]),
            libelle=f"{ligne['technicien']} — {ligne['metier']}",
            montant=float(ligne["surcout"]),
            anciennete_jours=int(ligne["anciennete_jours"]),
            priorite=float(ligne["surcout"]),
            motif=f"dérive de {ligne['derive']:.0%}",
            detail={
                "agence": str(ligne["agence"]),
                "heures_devisees": float(ligne["heures_devisees"]),
                "heures_reelles": float(ligne["heures_reelles"]),
                "anciennete_technicien": str(ligne["anciennete_technicien"]),
            },
        )
        for _, ligne in depassements.iterrows()
    )
    return File(
        cle="derive",
        titre="Interventions en dérive",
        unite_montant="€ de surcoût",
        seuil=seuil,
        seuil_libelle=f"examen au-delà de {seuil:.0%} d'écart entre heures passées et devisées",
        taches=taches,
        total_candidats=total,
    )


def construire_files(
    donnees: Donnees, seuils: dict[str, float] | None = None
) -> tuple[File, ...]:
    """Les trois files, avec les seuils retenus par l'agent quand il en propose."""
    choisis = seuils or {}
    return (
        creances_a_appeler(
            donnees, choisis.get("creances", SEUIL_RECOUVREMENT_JOURS)
        ),
        devis_a_relancer(
            donnees, donnees.situation, choisis.get("devis", SEUIL_RELANCE_JOURS)
        ),
        interventions_en_derive(donnees, choisis.get("derive", SEUIL_DERIVE)),
    )
