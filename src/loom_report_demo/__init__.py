"""Démo d'utilisation du package loom-ia."""

import asyncio

__all__ = ["main", "profil", "run", "seed"]


async def main() -> None:
    # Import différé : au niveau module, il tirerait `loom_ia` dès qu'on
    # importe le moindre sous-module du paquet — y compris `parsing`, qui
    # n'en dépend pas et doit rester testable sans clé d'API.
    from loom_report_demo.app import entry

    await entry()


def run() -> None:
    asyncio.run(main())


def seed() -> None:
    """Régénère le jeu de données dans `assets/data`.

    Import différé pour la même raison que `main` : le paquet `dataset` n'a
    besoin ni de `loom_ia` ni d'une clé d'API, et doit le rester.
    """
    from loom_report_demo.dataset.seed import regenerer

    regenerer()


def profil() -> None:
    """Affiche le profil de reconnaissance d'un niveau. Sans clé d'API."""
    from loom_report_demo.analysis.cli import run as executer_profil

    executer_profil()
