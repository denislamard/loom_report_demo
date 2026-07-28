"""Génération du jeu de données fictif Bâti-Sud.

Ce paquet ne dépend ni de `loom_ia`, ni du réseau, ni d'`openpyxl` : il n'utilise
que la bibliothèque standard. Il est donc testable partout et à coût nul.
"""

from __future__ import annotations

from loom_report_demo.dataset.generateur import JeuDeDonnees, ecrire, generer
from loom_report_demo.dataset.parametres import DATE_DEBUT, DATE_FIN, GRAINE

__all__ = ["DATE_DEBUT", "DATE_FIN", "GRAINE", "JeuDeDonnees", "ecrire", "generer"]
