"""Démo d'utilisation du package loom-ia."""

import asyncio

__all__ = ["main", "run"]


async def main() -> None:
    # Import différé : au niveau module, il tirerait `loom_ia` dès qu'on
    # importe le moindre sous-module du paquet — y compris `parsing`, qui
    # n'en dépend pas et doit rester testable sans clé d'API.
    from loom_report_demo.app import entry

    await entry()


def run() -> None:
    asyncio.run(main())
