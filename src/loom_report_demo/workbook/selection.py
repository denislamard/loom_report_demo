"""La sélection d'indicateurs : le contrat entre l'agent et le classeur.

Au jalon 4, elle vient d'une fixture écrite à la main. Au jalon 6, elle viendra
du modèle. La forme ne change pas, et c'est délibéré : le constructeur du
classeur n'a jamais besoin de savoir d'où elle sort.

Un indicateur ne porte aucune valeur. Il porte une *spécification* — mesure,
dimension, comparaison — que Python revalide contre le catalogue avant de
résoudre le gabarit de formule correspondant. Le seul nombre qu'un agent aura le
droit d'y écrire est un seuil d'alerte, parce qu'un seuil est un jugement et non
une mesure.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from loom_report_demo.analysis import catalogue as cat
from loom_report_demo.analysis.cadrages import COMPARAISON, PRINCIPAL, Cadrage
from loom_report_demo.niveaux import NIVEAUX, Niveau


@dataclass(frozen=True, slots=True)
class Indicateur:
    """Un indicateur choisi, décrit par ce qu'il faut calculer et pourquoi."""

    mesure: str
    dimension: str | None = None
    seuil_alerte: float | None = None
    pourquoi: str = ""
    decision_attendue: str = ""
    hypothese_source: str | None = None

    @property
    def cle(self) -> str:
        return self.mesure if self.dimension is None else f"{self.mesure}|{self.dimension}"


@dataclass(frozen=True, slots=True)
class HypothesePerdue:
    """Une piste explorée puis abandonnée, livrée avec son motif.

    Cette liste vaut autant que les trouvailles : un dirigeant qui apprend que ce
    n'est *pas* l'agence récente qui plombe la marge a gagné sa réunion.
    """

    identifiant: str
    enonce: str
    motif: str


@dataclass(frozen=True, slots=True)
class Selection:
    niveau: Niveau
    variables: tuple[Indicateur, ...]
    ecartees: tuple[HypothesePerdue, ...] = field(default_factory=tuple)
    message_direction: str = ""

    @property
    def socle(self) -> tuple[str, ...]:
        """Imposé par le niveau, jamais choisi par l'agent."""
        return NIVEAUX[self.niveau].socle

    @property
    def cadrage(self) -> Cadrage:
        return PRINCIPAL[self.niveau]

    @property
    def cadrage_comparaison(self) -> Cadrage:
        return COMPARAISON[self.cadrage]

    def valider(self) -> None:
        """Refuse une sélection que le catalogue ne sait pas tenir."""
        definition = NIVEAUX[self.niveau]
        attendus = definition.nb_variables
        if len(self.variables) != attendus:
            raise ValueError(
                f"Le niveau {self.niveau.value} attend {attendus} indicateurs choisis, "
                f"{len(self.variables)} fournis."
            )
        for cle in self.socle:
            cat.valider(cle, None, self.niveau)
        vues: set[str] = set()
        for indicateur in self.variables:
            cat.valider(indicateur.mesure, indicateur.dimension, self.niveau)
            if indicateur.cle in vues:
                raise ValueError(f"Indicateur en double : {indicateur.cle}")
            vues.add(indicateur.cle)
        hypotheses = [h.identifiant for h in self.ecartees]
        if len(set(hypotheses)) != len(hypotheses):
            raise ValueError("Deux hypothèses écartées portent le même identifiant.")


def depuis_dict(donnees: dict[str, Any]) -> Selection:
    selection = Selection(
        niveau=Niveau(donnees["niveau"]),
        variables=tuple(Indicateur(**x) for x in donnees.get("variables", ())),
        ecartees=tuple(HypothesePerdue(**x) for x in donnees.get("ecartees", ())),
        message_direction=donnees.get("message_direction", ""),
    )
    selection.valider()
    return selection


def charger(chemin: Path) -> Selection:
    return depuis_dict(json.loads(chemin.read_text(encoding="utf-8")))
