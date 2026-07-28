"""Orchestration de l'exploration par l'agent. **Seul module à importer `loom_ia`.**

Tout ce qui a de la substance est ailleurs : les outils dans `analysis/outils.py`,
les gardes dans `parsing.py`, le rendu dans `workbook/`. Ce module se contente de
les câbler. C'est délibéré — il est le seul à ne pas pouvoir être testé sans clé
d'API, et il faut donc qu'il tienne dans une page qu'on relit d'un coup d'œil.

Le partage des rôles mérite d'être explicité, car il n'est pas évident.
L'orchestrateur `main` raisonne et sonde : c'est lui qui note ses hypothèses,
appelle les outils et forme un jugement. Le rôle terminal `selection` ne fait que
mettre en forme, sous contrainte de schéma. Cette répartition est imposée par
`loom-ia` : un rôle porté par un `LLMTool` est une feuille, il ne peut pas
appeler d'outils lui-même, et un rôle à `output.schema` est incompatible avec le
raisonnement étendu que porte `main`.

Elle a un coût : le jugement transite par une transcription. Si la calibration
montre que l'information se perd au passage, l'alternative est de retirer
`thinking` de l'orchestrateur et de lui donner directement le bloc `output`.
C'est le premier point à trancher en exécution réelle.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import Any

from loom_report_demo import paths
from loom_report_demo.analysis.chargement import Donnees, donnees as charger_donnees
from loom_report_demo.analysis.criblage import Criblage, cribler
from loom_report_demo.analysis.outils import Registre, SpecOutil, construire_outils
from loom_report_demo.analysis.profil import profil
from loom_report_demo.niveaux import NIVEAUX, Niveau
from loom_report_demo.parsing import parse_selection
from loom_report_demo.workbook.selection import Selection

#: Nombre de candidats du criblage soumis à l'agent. Au-delà, on paie des jetons
#: pour des pistes qu'il n'aura pas le temps d'éprouver.
CANDIDATS_SOUMIS = 12


@dataclass(frozen=True, slots=True)
class Exploration:
    """Ce que rend une exécution : la sélection, la trace, et le criblage amont."""

    selection: Selection
    registre: Registre
    criblage: Criblage
    brut: str


def _candidat_lisible(candidat: Any) -> dict[str, Any]:
    return {
        "mesure": candidat.mesure,
        "dimension": candidat.dimension,
        "modalite_defavorable": candidat.modalite_defavorable,
        "materialite_euros_an": (
            None
            if candidat.scores.materialite_euros is None
            else round(candidat.scores.materialite_euros)
        ),
        "dispersion": round(candidat.scores.dispersion, 3),
        "stabilite": round(candidat.scores.stabilite, 2),
        "monotonie": round(candidat.scores.monotonie, 2),
    }


def construire_invite(niveau: Niveau, carte: dict[str, Any], resultat: Criblage) -> str:
    """La consigne remise à l'orchestrateur.

    Elle donne la carte du terrain et les candidats les mieux scorés, jamais de
    conclusion. Un modèle à qui l'on sert des conclusions les reformule ; un
    modèle à qui l'on sert une carte formule des hypothèses.
    """
    definition = NIVEAUX[niveau]
    candidats = [_candidat_lisible(c) for c in resultat.retenus[:CANDIDATS_SOUMIS]]
    return "\n".join(
        (
            f"Tu prépares le tableau de bord « {definition.question} » d'une PME artisanale.",
            "",
            "PROFIL DU JEU DE DONNÉES",
            json.dumps(carte, ensure_ascii=False, separators=(",", ":")),
            "",
            "CANDIDATS LES MIEUX SCORÉS PAR LE CRIBLAGE AUTOMATIQUE",
            "La matérialité est exprimée en euros de marge sur douze mois : c'est ce que",
            "rapporterait d'amener la modalité la plus défavorable au niveau des autres.",
            json.dumps(candidats, ensure_ascii=False, separators=(",", ":")),
            "",
            "TA MISSION",
            f"Choisir les {definition.nb_variables} indicateurs qui déclenchent une décision.",
            f"Le socle ({', '.join(definition.socle)}) est imposé : ne le reprends pas.",
            "",
            "MÉTHODE IMPOSÉE",
            "1. Note chaque hypothèse avec `noter_hypothese` AVANT de la sonder. Une",
            "   hypothèse formulée après le résultat n'est pas une hypothèse.",
            "2. Éprouve-la avec les outils. Une hypothèse réfutée vaut autant qu'une",
            "   confirmée : le dirigeant qui apprend que ce n'est pas ce qu'il croyait a",
            "   gagné sa réunion.",
            "3. Ne te contente pas des candidats proposés. Le criblage n'explore qu'une",
            "   dimension à la fois ; les effets combinés se cherchent avec `croiser`.",
            "4. Écarte ce qui n'est pas actionnable. Un écart réel sur un levier que le",
            "   dirigeant ne contrôle pas n'a rien à faire dans un tableau de bord.",
            "",
            "Quand tu as tranché, appelle l'outil `selection` en lui transmettant tes",
            "hypothèses, tes sondages et tes verdicts. N'écris aucun chiffre dans les",
            "textes rédigés : le programme recalcule toutes les valeurs.",
        )
    )


def _identifiant_session(niveau: Niveau, situation: date) -> str:
    """Une session par niveau et par mois : l'agent voit sa sélection précédente."""
    return f"{niveau.value}-{situation:%Y-%m}"


async def explorer(
    niveau: Niveau,
    source: Donnees | None = None,
    session_id: str | None = None,
) -> Exploration:
    """Fait explorer l'agent et rend une sélection validée.

    Toutes les erreurs de forme remontent en `ErreurSortie` depuis `parsing`, y
    compris après la boucle de réparation locale de `loom-ia`.
    """
    from loom_ia.agent import Agent
    from loom_ia.tools.function_tool import FunctionTool

    jeu = source if source is not None else charger_donnees()
    registre = Registre()
    specs: list[SpecOutil] = construire_outils(jeu, niveau, registre)
    outils = [
        FunctionTool(
            name=spec.nom,
            description=spec.description,
            input_schema=spec.input_schema,
            fn=spec.fn,
        )
        for spec in specs
    ]

    resultat = cribler(jeu, niveau)
    invite = construire_invite(niveau, profil(niveau, jeu), resultat)

    async with Agent(str(paths.loom_projet()), tools=outils) as agent:
        brut = await agent.run(
            invite,
            session_id=session_id or _identifiant_session(niveau, jeu.situation),
        )

    return Exploration(
        selection=parse_selection(brut),
        registre=registre,
        criblage=resultat,
        brut=brut,
    )
