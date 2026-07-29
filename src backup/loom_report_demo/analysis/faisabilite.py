"""Faisabilité d'un niveau, et transmission des files à un agent de relance.

**La garde de faisabilité** répond à une question qu'on ne se pose qu'après avoir
payé : est-ce que les données portent le niveau demandé ? Un rapport
opérationnel sur vingt factures ouvertes n'a rien à dire, un stratégique sur un
exercice et demi non plus. Mieux vaut le constater en une seconde et sans jeton
que dans la sortie du modèle, une minute et deux centimes plus tard.

Elle avertit sans bloquer. Le dirigeant reste juge : il peut vouloir voir un
rapport maigre, et un avertissement qui empêche d'agir est vite contourné.

**L'export** transmet les files de travail au format JSON. C'est la passerelle
commerciale : le classeur diagnostique, `agent-pro` agit. Le moment où le client
comprend le problème est aussi celui où on lui montre ce qui le traite.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from loom_report_demo.analysis.cadrages import PRINCIPAL, fenetre
from loom_report_demo.analysis.chargement import Donnees
from loom_report_demo.analysis.files import File
from loom_report_demo.fingerprint import EmpreinteJeu
from loom_report_demo.niveaux import Livrable, Niveau, definition

#: Volumétrie minimale de la fenêtre principale, par niveau.
MINIMA: dict[Niveau, tuple[int, str]] = {
    Niveau.STRATEGIQUE: (400, "factures sur l'exercice"),
    Niveau.GESTION: (120, "factures sur douze mois"),
    Niveau.OPERATIONNEL: (15, "mouvements sur trente jours"),
}

#: Sous ce nombre d'exercices complets, une comparaison N contre N-1 ne dit rien.
EXERCICES_MINIMAUX = 2


@dataclass(frozen=True, slots=True)
class Verdict:
    niveau: Niveau
    praticable: bool
    observations: tuple[str, ...]

    @property
    def resume(self) -> str:
        if self.praticable:
            return "Les données portent ce niveau."
        return " ".join(self.observations)


def _mouvements(donnees: Donnees, niveau: Niveau) -> int:
    """Nombre de mouvements dans la fenêtre principale du niveau.

    Les bornes sont converties en `Timestamp` plutôt que comparées sous forme de
    chaînes : pandas accepte la comparaison textuelle, mais elle repose sur un
    format implicite et dépend de la locale. `chargement.py` a déjà analysé ces
    colonnes en dates — il n'y a rien à reconvertir.
    """
    borne = fenetre(PRINCIPAL[niveau], donnees.situation, donnees.debut)
    debut, fin = pd.Timestamp(borne.debut), pd.Timestamp(borne.fin)
    total = 0
    for table, colonne in (
        (donnees.factures, "date_facture"),
        (donnees.devis, "date_emission"),
    ):
        dates = table[colonne]
        total += int(((dates >= debut) & (dates <= fin)).sum())
    return total


def evaluer(donnees: Donnees, niveau: Niveau) -> Verdict:
    """Dit si les données portent le niveau, sans jamais interdire."""
    observations: list[str] = []
    seuil, libelle = MINIMA[niveau]
    observes = _mouvements(donnees, niveau)
    if observes < seuil:
        observations.append(
            f"Seulement {observes} {libelle} : le seuil de lisibilité est de {seuil}. "
            f"Les ventilations seront trop peu peuplées pour trancher."
        )

    if niveau is Niveau.STRATEGIQUE:
        exercices = donnees.factures["exercice"].nunique()
        if exercices < EXERCICES_MINIMAUX:
            observations.append(
                f"{exercices} exercice(s) dans les données : une comparaison d'un "
                f"exercice à l'autre en demande au moins {EXERCICES_MINIMAUX}."
            )

    if niveau is Niveau.OPERATIONNEL:
        ouvertes = int((donnees.factures["est_payee"] == 0).sum())
        if ouvertes < 10:
            observations.append(
                f"{ouvertes} factures ouvertes : la file de recouvrement sera vide "
                f"ou anecdotique."
            )

    return Verdict(niveau, not observations, tuple(observations))


def exporter_files(
    files: tuple[File, ...],
    donnees: Donnees,
    niveau: Niveau,
    destination: Path,
    empreinte: EmpreinteJeu | None = None,
) -> Path:
    """Écrit les files au format attendu par un agent de relance.

    L'empreinte du jeu de données accompagne l'export : un agent qui traite une
    file doit pouvoir dire de quelle version des données elle sort, faute de quoi
    on ne saura jamais pourquoi il a appelé un client déjà réglé.
    """
    charge: dict[str, Any] = {
        "source": "loom-report-demo",
        "niveau": niveau.value,
        "livrable": definition(niveau).livrable.value,
        "situation": donnees.situation.isoformat(),
        "genere_le": datetime.now().astimezone().isoformat(timespec="seconds"),
        "empreinte_donnees": None if empreinte is None else empreinte.globale,
        "files": [f.en_dict() for f in files],
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(charge, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return destination


def produit_des_files(niveau: Niveau) -> bool:
    return definition(niveau).livrable is Livrable.FILE_DE_TRAVAIL
