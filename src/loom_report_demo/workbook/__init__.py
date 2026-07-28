"""Construction du classeur Excel.

`openpyxl` uniquement : ce paquet ne connaît ni `loom_ia`, ni le réseau. Il
reçoit une sélection d'indicateurs et produit un fichier — que la sélection
vienne d'une fixture écrite à la main ou du modèle ne change rien pour lui.
"""

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook

from loom_report_demo import paths
from loom_report_demo.analysis import catalogue as cat
from loom_report_demo.analysis.cadrages import fenetre
from loom_report_demo.analysis.chargement import (
    SEUIL_EXCEPTION_JOURS,
    SEUIL_RELANCE_RAPIDE_JOURS,
    Donnees,
    donnees as charger_donnees,
)
from loom_report_demo.analysis.criblage import cribler
from loom_report_demo.fingerprint import empreinte_jeu
from loom_report_demo.workbook import tableaux
from loom_report_demo.workbook.feuilles_donnees import ecrire_feuilles
from loom_report_demo.workbook.formules import COLONNES_CALCULEES
from loom_report_demo.workbook.schema import construire_schemas
from loom_report_demo.workbook.selection import Selection

#: Ordre d'apparition des onglets : restitution d'abord, sources ensuite.
ORDRE = (
    "Synthèse",
    "Indicateurs",
    "Détail mensuel",
    "Ce qui a été regardé",
    "Paramètres",
    "Devis",
    "Relances",
    "Factures",
    "Interventions",
    "Clients",
    "Techniciens",
    "Catalogue",
)

COULEURS_ONGLET = {
    "Synthèse": "1B2733",
    "Indicateurs": "1F6FB2",
    "Détail mensuel": "1E8A6E",
    "Ce qui a été regardé": "D9762B",
    "Paramètres": "6B7A88",
}


def _modalites(source: Donnees, selection: Selection) -> dict[str, tuple[str, ...]]:
    """Libellés des modalités, dans l'ordre du catalogue quand il est imposé.

    Seuls les libellés sont extraits des données : les valeurs, elles, seront
    calculées par le classeur.
    """
    resultat: dict[str, tuple[str, ...]] = {}
    for indicateur in selection.variables:
        if indicateur.dimension is None:
            continue
        dimension = cat.dimension(indicateur.dimension)
        mesure = cat.mesure(indicateur.mesure)
        colonne = source.table(mesure.base)[dimension.colonne]
        presentes = list(dict.fromkeys(str(x) for x in colonne.dropna()))
        if dimension.ordonnee and dimension.modalites:
            ordonnees = [m for m in dimension.modalites if m in presentes]
            presentes = ordonnees + [m for m in presentes if m not in dimension.modalites]
        else:
            presentes.sort()
        resultat[indicateur.dimension] = tuple(presentes)
    return resultat


def construire(
    selection: Selection,
    destination: Path,
    source: Donnees | None = None,
    dossier_donnees: Path | None = None,
) -> Path:
    """Produit le classeur et rend son chemin."""
    selection.valider()
    jeu = source if source is not None else charger_donnees(dossier_donnees)
    schemas = construire_schemas(COLONNES_CALCULEES, dossier_donnees)
    borne = fenetre(selection.cadrage, jeu.situation, jeu.debut)
    mois = tuple(sorted({*jeu.factures["mois"].unique(), *jeu.devis["mois"].unique()}))
    metiers = tuple(sorted(str(x) for x in jeu.factures["metier"].dropna().unique()))
    empreinte = empreinte_jeu([paths.csv_source(n) for n in paths.FICHIERS_DONNEES])

    classeur = Workbook()
    classeur.remove(classeur.active)

    ecrire_feuilles(classeur, schemas, dossier_donnees)
    tableaux.parametres(
        classeur, jeu.situation, empreinte, SEUIL_EXCEPTION_JOURS, SEUIL_RELANCE_RAPIDE_JOURS, borne
    )
    tableaux.detail_mensuel(classeur, schemas, mois)
    tableaux.synthese(classeur, schemas, selection, borne, metiers, len(mois))
    tableaux.indicateurs(classeur, schemas, selection, _modalites(jeu, selection))
    tableaux.criblage(classeur, cribler(jeu, selection.niveau), selection)

    classeur._sheets = [classeur[nom] for nom in ORDRE]  # noqa: SLF001
    for nom in ORDRE:
        classeur[nom].sheet_properties.tabColor = COULEURS_ONGLET.get(nom, "B8C4CE")
    classeur["Synthèse"].sheet_view.tabSelected = True
    classeur.active = 0

    destination.parent.mkdir(parents=True, exist_ok=True)
    classeur.save(destination)
    return destination
