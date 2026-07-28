"""Point d'entrée `uv run rapport` : produit le classeur à partir d'une sélection.

Au jalon 4, la sélection vient d'une fixture. Au jalon 6, elle viendra de
l'agent — et cette commande restera utile pour rejouer un rapport à l'identique
sans dépenser un jeton.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from loom_report_demo import paths
from loom_report_demo.workbook import construire
from loom_report_demo.workbook.selection import charger


def executer(argv: list[str] | None = None) -> int:
    parseur = argparse.ArgumentParser(
        prog="rapport",
        description="Produit le classeur Excel à partir d'une sélection d'indicateurs.",
    )
    parseur.add_argument(
        "--selection",
        type=Path,
        required=True,
        help="Fichier JSON décrivant le niveau et les indicateurs retenus.",
    )
    parseur.add_argument(
        "--sortie", type=Path, default=None, help="Chemin du classeur produit."
    )
    arguments = parseur.parse_args(argv)

    try:
        paths.verifier()
    except FileNotFoundError as erreur:
        print(f"\n{erreur}\n", file=sys.stderr)
        return 1
    if not arguments.selection.is_file():
        print(f"\nSélection introuvable : {arguments.selection}\n", file=sys.stderr)
        return 1

    selection = charger(arguments.selection)
    destination = arguments.sortie or paths.rapports() / f"Bati-Sud_{selection.niveau.value}.xlsx"
    produit = construire(selection, destination)

    print(f"\n  Niveau       {selection.niveau.value}")
    print(f"  Indicateurs  {len(selection.socle)} de socle + {len(selection.variables)} choisis")
    print(f"  Écartées     {len(selection.ecartees)} hypothèses documentées")
    print(f"  Classeur     {produit}  ({produit.stat().st_size // 1024} Kio)\n")
    return 0


def run() -> None:
    code = executer()
    if code:
        raise SystemExit(code)
