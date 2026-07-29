"""La sélection d'indicateurs : le contrat entre l'agent et le classeur.

Au jalon 4, elle venait d'une fixture écrite à la main ; au jalon 6, elle viendra
du modèle. La forme ne change pas, et c'est délibéré : le constructeur du
classeur n'a jamais besoin de savoir d'où elle sort.

Ce module ne décode rien. Le passage du texte brut à cet objet est le travail de
`parsing.py`, qui porte les gardes — c'est la seule frontière par où passe ce
que le modèle a produit.

Un indicateur ne porte aucune valeur. Il porte une *spécification* — mesure,
dimension, comparaison — que Python revalide contre le catalogue avant de
résoudre le gabarit de formule correspondant. Le seul nombre qu'un agent aura le
droit d'y écrire est un seuil d'alerte, parce qu'un seuil est un jugement et non
une mesure.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import ClassVar

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
    ecartees: tuple[HypothesePerdue, ...] = ()
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

    #: Correspondance entre une mesure et la file qu'elle pilote.
    #:
    #: Seules les mesures dont l'unité est celle du seuil de la file y figurent.
    #: `respect_delai_relance` mesure une PART de devis relancés à temps : son
    #: seuil est un pourcentage, pas un nombre de jours, et il ne peut donc pas
    #: piloter une file qui trie par ancienneté. La garde du parsing l'a signalé
    #: avant que l'erreur n'atteigne le classeur.
    FILES_PAR_MESURE: ClassVar[Mapping[str, str]] = {
        "age_moyen_file_recouvrement": "creances",
        "delai_1ere_relance": "devis",
        "taux_derive_horaire": "derive",
    }

    def seuils(self) -> dict[str, float]:
        """Seuils de tri retenus par l'agent, par file de travail.

        C'est tout ce qu'il choisit au niveau opérationnel : les files sont
        dictées par les processus, pas par lui. Un seuil est un jugement — à
        partir de quand une créance passe en recouvrement — et c'est exactement
        le genre de décision qu'on lui délègue.
        """
        retenus: dict[str, float] = {}
        for indicateur in self.variables:
            file = self.FILES_PAR_MESURE.get(indicateur.mesure)
            if file is not None and indicateur.seuil_alerte is not None:
                retenus[file] = indicateur.seuil_alerte
        return retenus

    def sans(self, indice: int) -> Selection:
        """Sélection privée d'un indicateur, après arbitrage humain.

        L'humain a le dernier mot : c'est la seule barrière entre une bêtise du
        modèle et le livrable, et c'est ce qui transforme la démonstration d'un
        tour de magie en un outil dont on garde la main.
        """
        if not 0 <= indice < len(self.variables):
            raise IndexError(f"Indicateur inexistant : {indice + 1}")
        restants = tuple(x for k, x in enumerate(self.variables) if k != indice)
        return Selection(
            niveau=self.niveau,
            variables=restants,
            ecartees=self.ecartees,
            message_direction=self.message_direction,
        )

    def valider(self, strict: bool = True) -> None:
        """Refuse une sélection que le catalogue ne sait pas tenir.

        `strict` vaut faux après un retrait manuel : on accepte alors moins
        d'indicateurs que prévu, jamais plus.
        """
        definition = NIVEAUX[self.niveau]
        attendus = definition.nb_variables
        if not strict and len(self.variables) <= attendus:
            pass
        elif len(self.variables) != attendus:
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
