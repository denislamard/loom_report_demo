"""Les trois niveaux de tableau de bord, et ce que chacun commute.

Le niveau est la seule décision prise par l'humain. Tout le reste du programme
s'y adosse : la fenêtre d'observation, le sous-ensemble du catalogue de mesures
autorisé, le nombre d'indicateurs que l'agent choisit, le modèle qui l'assiste,
et la durée de vie de sa sélection.

Le principe qui gouverne ce tableau :

    la liberté de l'agent est inversement proportionnelle
    à la durée de vie de sa décision.

Un indicateur stratégique est gelé douze mois : il mérite un modèle cher et un
juge sévère. Un seuil opérationnel est recalculé à chaque exécution : il ne
mérite ni l'un ni l'autre.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Niveau(StrEnum):
    """Registre du tableau de bord demandé."""

    STRATEGIQUE = "strategique"
    GESTION = "gestion"
    OPERATIONNEL = "operationnel"


class Livrable(StrEnum):
    """Nature de l'objet produit, qui n'est pas la même aux trois niveaux."""

    #: Cartes d'indicateurs, graphiques, tableaux de ventilation.
    TABLEAU_DE_BORD = "tableau_de_bord"
    #: Listes triées d'unités à traiter — pas des indicateurs à contempler.
    FILE_DE_TRAVAIL = "file_de_travail"


@dataclass(frozen=True, slots=True)
class DefinitionNiveau:
    """Tout ce que le niveau détermine, en un seul objet immuable."""

    niveau: Niveau
    #: Formulé dans la langue du client, pas dans celle du contrôle de gestion.
    question: str
    cadrage: str
    horizon_jours: int
    #: Indicateurs imposés, jamais choisis par l'agent : ils assurent la
    #: comparabilité d'une édition à l'autre.
    socle: tuple[str, ...]
    #: Indicateurs que l'agent sélectionne librement dans le catalogue.
    nb_variables: int
    #: Combien de temps la sélection de l'agent reste valable.
    duree_vie: str
    #: Identifiant du bloc `llm` de settings.json qui porte l'exploration.
    modele: str
    livrable: Livrable
    #: Nom du fichier d'état où la sélection est persistée.
    fichier_etat: str

    @property
    def nb_indicateurs(self) -> int:
        return len(self.socle) + self.nb_variables


#: Socle stratégique : quatre mesures qui doivent rester comparables sur des
#: années. Aucune n'est manipulable sans créer de valeur réelle — critère
#: bloquant du juge au jalon 7.
_SOCLE_STRATEGIQUE = (
    "ca_par_technicien",
    "taux_marge_brute",
    "concentration_client",
    "dso",
)

_SOCLE_GESTION = (
    "ca_facture_ht",
    "taux_marge_brute",
    "dso",
    "encours_client",
)

#: L'opérationnel ne mesure pas un état, il suit un flux : ce qui entre, ce qui
#: sort, ce qui stagne.
_SOCLE_OPERATIONNEL = (
    "respect_delai_relance",
    "age_moyen_file_recouvrement",
    "exceptions_ouvertes",
)

NIVEAUX: dict[Niveau, DefinitionNiveau] = {
    Niveau.STRATEGIQUE: DefinitionNiveau(
        niveau=Niveau.STRATEGIQUE,
        question="Où va mon entreprise ?",
        cadrage="4 exercices, exercice N contre N-1",
        horizon_jours=1461,
        socle=_SOCLE_STRATEGIQUE,
        nb_variables=2,
        duree_vie="12 mois, sélection gelée",
        modele="SONNET",
        livrable=Livrable.TABLEAU_DE_BORD,
        fichier_etat="selection_strategique.json",
    ),
    Niveau.GESTION: DefinitionNiveau(
        niveau=Niveau.GESTION,
        question="Qu'est-ce que je corrige ce mois-ci ?",
        cadrage="12 mois glissants, contre les 12 précédents",
        horizon_jours=365,
        socle=_SOCLE_GESTION,
        nb_variables=4,
        duree_vie="1 mois",
        modele="HAIKU",
        livrable=Livrable.TABLEAU_DE_BORD,
        fichier_etat="selection_gestion.json",
    ),
    Niveau.OPERATIONNEL: DefinitionNiveau(
        niveau=Niveau.OPERATIONNEL,
        question="Qu'est-ce que je traite cette semaine ?",
        cadrage="30 derniers jours, situation du jour",
        horizon_jours=30,
        socle=_SOCLE_OPERATIONNEL,
        nb_variables=2,
        duree_vie="recalculée à chaque exécution",
        modele="HAIKU",
        livrable=Livrable.FILE_DE_TRAVAIL,
        fichier_etat="regles_operationnelles.json",
    ),
}

#: Ordre d'affichage du menu : du plus long terme au plus court.
ORDRE_MENU: tuple[Niveau, ...] = (
    Niveau.STRATEGIQUE,
    Niveau.GESTION,
    Niveau.OPERATIONNEL,
)


def definition(niveau: Niveau) -> DefinitionNiveau:
    return NIVEAUX[niveau]


def par_rang(rang: int) -> DefinitionNiveau:
    """Résout un choix de menu (1, 2, 3) en définition de niveau."""
    if not 1 <= rang <= len(ORDRE_MENU):
        raise ValueError(f"Rang de menu hors bornes : {rang}")
    return NIVEAUX[ORDRE_MENU[rang - 1]]
