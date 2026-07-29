"""Fenêtres d'observation, calculées à partir de la date de situation.

Un cadrage n'est qu'un couple de dates, mais c'est lui qui rend une valeur
comparable : « 32 % de marge » ne veut rien dire sans savoir sur quoi. Chaque
niveau a son cadrage principal et son cadrage de comparaison — c'est ce qui
permet au classeur de n'afficher aucun chiffre nu.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum

from loom_report_demo.niveaux import Niveau


class Cadrage(StrEnum):
    PERIODE_TOTALE = "periode_totale"
    EXERCICE_COURANT = "exercice_courant"
    EXERCICE_PRECEDENT = "exercice_precedent"
    DOUZE_MOIS = "12_mois_glissants"
    DOUZE_MOIS_PRECEDENTS = "12_mois_precedents"
    TRENTE_JOURS = "30_jours"
    TRENTE_JOURS_PRECEDENTS = "30_jours_precedents"


@dataclass(frozen=True, slots=True)
class Fenetre:
    cadrage: Cadrage
    debut: date
    fin: date
    libelle: str

    def contient(self, jour: date) -> bool:
        return self.debut <= jour <= self.fin

    @property
    def jours(self) -> int:
        return (self.fin - self.debut).days + 1


#: Cadrage principal et cadrage de comparaison, par niveau.
PRINCIPAL: dict[Niveau, Cadrage] = {
    Niveau.STRATEGIQUE: Cadrage.EXERCICE_COURANT,
    Niveau.GESTION: Cadrage.DOUZE_MOIS,
    Niveau.OPERATIONNEL: Cadrage.TRENTE_JOURS,
}

COMPARAISON: dict[Cadrage, Cadrage] = {
    Cadrage.EXERCICE_COURANT: Cadrage.EXERCICE_PRECEDENT,
    Cadrage.DOUZE_MOIS: Cadrage.DOUZE_MOIS_PRECEDENTS,
    Cadrage.TRENTE_JOURS: Cadrage.TRENTE_JOURS_PRECEDENTS,
}


def _debut_exercice(jour: date) -> date:
    """Les exercices sont décalés : ils courent de juillet à juin."""
    annee = jour.year if jour.month >= 7 else jour.year - 1
    return date(annee, 7, 1)


def fenetre(cadrage: Cadrage, situation: date, debut_donnees: date) -> Fenetre:
    """Borne une fenêtre d'observation, sans jamais sortir du jeu de données."""
    if cadrage is Cadrage.PERIODE_TOTALE:
        return Fenetre(cadrage, debut_donnees, situation, "période complète")

    if cadrage is Cadrage.EXERCICE_COURANT:
        debut = _debut_exercice(situation)
        return Fenetre(cadrage, debut, situation, f"exercice {debut.year}-{debut.year + 1}")

    if cadrage is Cadrage.EXERCICE_PRECEDENT:
        fin = _debut_exercice(situation) - timedelta(days=1)
        debut = _debut_exercice(fin)
        return Fenetre(cadrage, debut, fin, f"exercice {debut.year}-{debut.year + 1}")

    if cadrage is Cadrage.DOUZE_MOIS:
        return Fenetre(cadrage, situation - timedelta(days=364), situation, "12 mois glissants")

    if cadrage is Cadrage.DOUZE_MOIS_PRECEDENTS:
        fin = situation - timedelta(days=365)
        return Fenetre(cadrage, fin - timedelta(days=364), fin, "12 mois précédents")

    if cadrage is Cadrage.TRENTE_JOURS:
        return Fenetre(cadrage, situation - timedelta(days=29), situation, "30 derniers jours")

    fin = situation - timedelta(days=30)
    return Fenetre(cadrage, fin - timedelta(days=29), fin, "30 jours précédents")


def fenetres_du_niveau(
    niveau: Niveau, situation: date, debut_donnees: date
) -> tuple[Fenetre, Fenetre]:
    """Fenêtre principale et fenêtre de comparaison, dans cet ordre."""
    principal = PRINCIPAL[niveau]
    return (
        fenetre(principal, situation, debut_donnees),
        fenetre(COMPARAISON[principal], situation, debut_donnees),
    )
