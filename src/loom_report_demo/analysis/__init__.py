"""Catalogue de mesures, moteur de calcul et profil de reconnaissance.

Ce paquet ne dépend ni de `loom_ia` ni du réseau : il ne connaît que pandas et
les CSV. Il est donc testable sans clé d'API, et c'est lui qui portera, au jalon
6, les cinq outils d'exploration remis à l'agent.
"""

from __future__ import annotations

from loom_report_demo.analysis.cadrages import Cadrage, Fenetre, fenetre
from loom_report_demo.analysis.catalogue import (
    DIMENSIONS,
    MESURES,
    Base,
    Dimension,
    Mesure,
    Nature,
    Sens,
    Unite,
    croisements_valides,
    dimension,
    dimensions_du_niveau,
    mesure,
    mesures_du_niveau,
    valider,
)
from loom_report_demo.analysis.chargement import Donnees, charger, donnees
from loom_report_demo.analysis.moteur import (
    Comparaison,
    Modalite,
    PointMensuel,
    Valeur,
    Ventilation,
    calculer,
    comparer,
    serie_mensuelle,
    ventiler,
)

__all__ = [
    "DIMENSIONS",
    "MESURES",
    "Base",
    "Cadrage",
    "Dimension",
    "Donnees",
    "Fenetre",
    "Comparaison",
    "Mesure",
    "Modalite",
    "Nature",
    "PointMensuel",
    "Sens",
    "Unite",
    "Valeur",
    "Ventilation",
    "calculer",
    "charger",
    "comparer",
    "croisements_valides",
    "dimension",
    "dimensions_du_niveau",
    "donnees",
    "fenetre",
    "mesure",
    "mesures_du_niveau",
    "serie_mensuelle",
    "valider",
    "ventiler",
]
