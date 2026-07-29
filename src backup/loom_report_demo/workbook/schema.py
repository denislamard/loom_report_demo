"""Résolution des colonnes Excel par NOM DE CHAMP, jamais par lettre.

Coder `Devis!$M$2` en dur revient à refaire ce travail à chaque évolution du
schéma, et surtout à le rater silencieusement : une `SUMIFS` qui pointe la
colonne voisine ne lève aucune erreur, elle rend un mauvais chiffre. Les lettres
sont donc dérivées des en-têtes des CSV, augmentées des colonnes calculées.

Les colonnes calculées reproduisent en formules Excel ce que `chargement.py`
construit en pandas. C'est une duplication assumée : le classeur doit rester
vivant — modifier une donnée source met tout le rapport à jour — et aucune
abstraction ne traduit honnêtement pandas en Excel. Un test vérifie que les deux
jeux de colonnes portent les mêmes noms ; la concordance des valeurs est
contrôlée par un recalcul LibreOffice, hors intégration continue.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from openpyxl.utils import get_column_letter

from loom_report_demo import paths
from loom_report_demo.analysis.catalogue import Base

FEUILLES: dict[str, str] = {
    "Devis": "devis.csv",
    "Relances": "relances.csv",
    "Factures": "factures.csv",
    "Interventions": "interventions.csv",
    "Clients": "clients.csv",
    "Techniciens": "techniciens.csv",
    "Catalogue": "catalogue_prestations.csv",
}

FEUILLE_DE_BASE: dict[Base, str] = {
    Base.DEVIS: "Devis",
    Base.FACTURES: "Factures",
    Base.INTERVENTIONS: "Interventions",
}


@dataclass(frozen=True, slots=True)
class ColonneCalculee:
    """Une colonne ajoutée à droite des données sources.

    `gabarit` reçoit `{r}` (numéro de ligne) et les lettres ancrées de sa propre
    feuille, plus les plages nommées passées à la construction.
    """

    cle: str
    entete: str
    gabarit: str
    format: str | None = None
    largeur: int = 14


@dataclass(frozen=True, slots=True)
class Schema:
    """Lettres de colonne et bornes de lignes, pour une feuille de données."""

    feuille: str
    champs: tuple[str, ...]
    nb_lignes: int

    @property
    def derniere_ligne(self) -> int:
        return self.nb_lignes + 1

    def lettre(self, champ: str) -> str:
        try:
            return get_column_letter(self.champs.index(champ) + 1)
        except ValueError:
            raise KeyError(
                f"Champ inconnu dans {self.feuille} : {champ!r}. "
                f"Disponibles : {', '.join(sorted(self.champs))}"
            ) from None

    def ancre(self, champ: str) -> str:
        return "$" + self.lettre(champ)

    def plage(self, champ: str) -> str:
        colonne = self.lettre(champ)
        return f"{self.feuille}!${colonne}$2:${colonne}${self.derniere_ligne}"

    def plage_locale(self, champ: str) -> str:
        colonne = self.lettre(champ)
        return f"${colonne}$2:${colonne}${self.derniere_ligne}"


def entetes_csv(fichier: str, dossier: Path | None = None) -> list[str]:
    source = (dossier or paths.donnees()) / fichier
    with source.open(encoding="utf-8") as flux:
        return next(csv.reader(flux, delimiter=";"))


def nb_lignes_csv(fichier: str, dossier: Path | None = None) -> int:
    source = (dossier or paths.donnees()) / fichier
    with source.open(encoding="utf-8") as flux:
        return sum(1 for _ in flux) - 1


def construire_schemas(
    calculees: dict[str, tuple[ColonneCalculee, ...]], dossier: Path | None = None
) -> dict[str, Schema]:
    """Un schéma par feuille, en-têtes CSV augmentés des colonnes calculées."""
    schemas: dict[str, Schema] = {}
    for feuille, fichier in FEUILLES.items():
        champs = tuple(entetes_csv(fichier, dossier)) + tuple(
            c.cle for c in calculees.get(feuille, ())
        )
        schemas[feuille] = Schema(feuille, champs, nb_lignes_csv(fichier, dossier))
    return schemas
