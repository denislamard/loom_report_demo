"""Persistance de la sélection d'indicateurs, d'une édition à l'autre.

Le volume et la volatilité de l'état suivent l'horizon du niveau — c'est le
principe des quatre étages : ce qu'on persiste rétrécit et se stabilise à mesure
que l'échelle augmente. Une sélection stratégique est minuscule et gelée douze
mois ; des règles opérationnelles sont recalculées à chaque exécution.

Ce qui est stocké est la **sortie brute du modèle**, pas l'objet de domaine. Deux
raisons. La relecture repasse par `parsing`, donc par toutes les gardes : une
sélection enregistrée sous un ancien catalogue est refusée plutôt que
silencieusement acceptée. Et le format est celui que l'agent produit, donc
comparable d'un mois sur l'autre sans conversion.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from loom_report_demo import paths
from loom_report_demo.niveaux import NIVEAUX, Niveau
from loom_report_demo.parsing import ErreurSortie, parse_selection
from loom_report_demo.workbook.selection import Selection


@dataclass(frozen=True, slots=True)
class Enregistrement:
    niveau: Niveau
    millesime: str
    enregistre_le: str
    brut: str

    def selection(self) -> Selection:
        """Relit en repassant par toutes les gardes."""
        return parse_selection(self.brut)


def millesime(niveau: Niveau, situation: date) -> str:
    """Grain de versionnement : l'année au stratégique, le mois ailleurs.

    C'est ce qui rend une sélection stratégique *gelée* : tant que le millésime
    n'a pas changé, la relancer rend la même chose.
    """
    if niveau is Niveau.STRATEGIQUE:
        return f"{situation.year}"
    return f"{situation:%Y-%m}"


def chemin(niveau: Niveau) -> Path:
    return paths.etat(NIVEAUX[niveau].fichier_etat)


def enregistrer(niveau: Niveau, brut: str, situation: date) -> Path:
    """Écrit la sélection courante, en écrasant celle du même millésime."""
    destination = chemin(niveau)
    destination.parent.mkdir(parents=True, exist_ok=True)
    charge: dict[str, Any] = {
        "niveau": niveau.value,
        "millesime": millesime(niveau, situation),
        "enregistre_le": datetime.now().astimezone().isoformat(timespec="seconds"),
        "brut": brut,
    }
    destination.write_text(
        json.dumps(charge, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return destination


def derniere(niveau: Niveau) -> Enregistrement | None:
    """Dernière sélection enregistrée, ou `None` s'il n'y en a pas."""
    source = chemin(niveau)
    if not source.is_file():
        return None
    charge = json.loads(source.read_text(encoding="utf-8"))
    return Enregistrement(
        niveau=Niveau(charge["niveau"]),
        millesime=charge["millesime"],
        enregistre_le=charge["enregistre_le"],
        brut=charge["brut"],
    )


def gelee(niveau: Niveau, situation: date) -> Enregistrement | None:
    """Sélection encore valable pour le millésime courant, s'il y en a une.

    Au stratégique, elle interdit de rebattre les cartes en cours d'année : un
    référentiel qui change tous les trimestres n'est plus un référentiel, et
    l'indicateur cesse d'être comparable — ce qui était sa seule raison d'être.
    """
    enregistrement = derniere(niveau)
    if enregistrement is None:
        return None
    if enregistrement.millesime != millesime(niveau, situation):
        return None
    return enregistrement


def rejouer(niveau: Niveau) -> Selection:
    """Recharge la dernière sélection. Indispensable en démonstration client.

    Un agent qui choisit d'autres indicateurs à chaque lancement est un risque en
    rendez-vous : on veut pouvoir montrer deux fois la même chose.
    """
    enregistrement = derniere(niveau)
    if enregistrement is None:
        raise FileNotFoundError(
            f"Aucune sélection enregistrée pour le niveau {niveau.value}. "
            f"Lancez `uv run app` une première fois."
        )
    try:
        return enregistrement.selection()
    except ErreurSortie as erreur:
        raise ErreurSortie(
            f"La sélection enregistrée le {enregistrement.enregistre_le} n'est plus "
            f"valide : {erreur}"
        ) from None
