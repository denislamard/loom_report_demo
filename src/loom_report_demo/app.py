"""Point d'entrée console.

Ce module ne porte que le contrat de la couche d'interaction et le point
d'entrée lui-même. Le déroulé d'une exécution vit dans `console.py`.

Les trois alias sont ici parce qu'ils décrivent les coutures injectables du
programme : d'où vient la saisie, où va l'écriture, et qui explore. Les tests
les remplacent par des doubles, ce qui permet d'éprouver tout le flux sans
terminal, sans clé d'API et sans dépenser un jeton.

L'import de `console` est différé dans `entry` : `console` importe ce module
pour ses alias, et un import au niveau du module créerait un cycle.
"""

from __future__ import annotations

import sys
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from loom_report_demo.niveaux import Niveau

if TYPE_CHECKING:
    from loom_report_demo.reporting import Exploration

#: D'où vient la saisie de l'utilisateur.
Saisie = Callable[[str], str]
#: Où part l'affichage. Volontairement permissif : `print` accepte `file=`.
Ecriture = Callable[..., Any]
#: Qui mène l'exploration. Injectable, car la vraie demande une clé d'API.
Explorateur = Callable[[Niveau], "Awaitable[Exploration]"]


async def entry(argv: list[str] | None = None) -> None:
    """Point d'entrée appelé par `loom_report_demo.main()`.

    Deux drapeaux seulement, tous deux au service de la démonstration :
    `--rejouer` reprend la dernière sélection sans rappeler le modèle, ce qui
    rend un rendez-vous reproductible ; `--forcer` passe outre le gel du
    millésime stratégique.
    """
    # Import différé : `console` importe ce module pour ses alias.
    from loom_report_demo.console import executer

    arguments = sys.argv[1:] if argv is None else argv
    code = await executer(
        rejouer="--rejouer" in arguments,
        forcer="--forcer" in arguments,
    )
    if code:
        raise SystemExit(code)
