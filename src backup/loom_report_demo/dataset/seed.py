"""Point d'entrée `uv run seed` : régénère les CSV et affiche leur empreinte.

La régénération écrase les fichiers versionnés. Comme le générateur est
déterministe, un `git status` propre après un `uv run seed` prouve que les
données du dépôt correspondent bien au code qui les produit — c'est le contrôle
le plus simple, et il tient en une commande.
"""

from __future__ import annotations

from pathlib import Path

from loom_report_demo import paths
from loom_report_demo.dataset.generateur import ecrire, generer
from loom_report_demo.dataset.parametres import DATE_DEBUT, DATE_FIN, GRAINE
from loom_report_demo.fingerprint import empreinte_jeu, formater


def regenerer(destination: Path | None = None, graine: int = GRAINE) -> None:
    cible = destination if destination is not None else paths.donnees()
    print(f"  Génération  graine {graine}, du {DATE_DEBUT:%d/%m/%Y} au {DATE_FIN:%d/%m/%Y}")
    jeu = generer(graine)
    chemins = ecrire(jeu, cible)
    print(f"  Destination {cible}\n")
    print(formater(empreinte_jeu(chemins)))
    print(
        "\n  Le générateur est déterministe : à graine égale, les fichiers sont\n"
        "  identiques à l'octet près. Un `git status` propre le confirme.\n"
    )
