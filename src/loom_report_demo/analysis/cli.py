"""Point d'entrée `uv run profil` : affiche la carte du terrain d'un niveau.

Utile en développement pour calibrer le catalogue, et en démonstration pour
montrer ce que l'agent recevra avant de commencer à explorer.
"""

from __future__ import annotations

import argparse
import json
import sys

from loom_report_demo import paths
from loom_report_demo.analysis.profil import empreinte_courante, formater, profil
from loom_report_demo.niveaux import Niveau


def _analyser(argv: list[str] | None = None) -> argparse.Namespace:
    parseur = argparse.ArgumentParser(
        prog="profil",
        description="Affiche le profil de reconnaissance remis à l'agent.",
    )
    parseur.add_argument(
        "--niveau",
        choices=[n.value for n in Niveau],
        default=Niveau.GESTION.value,
        help="Registre du tableau de bord (défaut : gestion).",
    )
    parseur.add_argument(
        "--json",
        action="store_true",
        help="Sortie brute, telle qu'elle sera injectée dans le prompt.",
    )
    return parseur.parse_args(argv)


def executer(argv: list[str] | None = None) -> int:
    arguments = _analyser(argv)
    try:
        paths.verifier()
    except FileNotFoundError as erreur:
        print(f"\n{erreur}\n", file=sys.stderr)
        return 1

    carte = profil(Niveau(arguments.niveau))
    if arguments.json:
        print(json.dumps(carte, ensure_ascii=False, indent=2))
    else:
        print(formater(carte, empreinte_courante()))
    return 0


def run() -> None:
    code = executer()
    if code:
        raise SystemExit(code)
