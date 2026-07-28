"""Le moteur de calcul : une mesure, un cadrage, éventuellement une dimension.

Le moteur ne décide de rien. Il applique l'algèbre déclarée par le catalogue, et
refuse tout ce qui n'y figure pas. C'est ce qui permettra, au jalon 6, d'exposer
les outils d'exploration à l'agent avec des arguments en `enum` fermés : aucune
expression libre n'atteint jamais pandas.

Une propriété tient tout l'édifice : **on somme avant de diviser**. La marge
moyenne de trois agences n'est pas la moyenne de leurs trois taux de marge, et
c'est l'erreur la plus fréquente dans les tableaux de bord. Chaque agrégat porte
donc son numérateur et son dénominateur en colonnes distinctes, agrégées
séparément, divisées en dernier.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

import pandas as pd

from loom_report_demo.analysis import catalogue as cat
from loom_report_demo.analysis.cadrages import Cadrage, Fenetre, fenetre
from loom_report_demo.analysis.chargement import COLONNE_DATE, Donnees
from loom_report_demo.niveaux import Niveau

Filtre = Mapping[str, str]


@dataclass(frozen=True, slots=True)
class Valeur:
    """Résultat scalaire, avec de quoi juger de sa solidité."""

    mesure: str
    valeur: float | None
    effectif: int
    numerateur: float
    denominateur: float | None

    @property
    def calculable(self) -> bool:
        return self.valeur is not None


@dataclass(frozen=True, slots=True)
class Modalite:
    libelle: str
    valeur: float | None
    effectif: int
    numerateur: float
    denominateur: float | None
    #: Part de la modalité dans le numérateur total : sert à distinguer un écart
    #: spectaculaire mais marginal d'un écart qui pèse.
    poids: float


@dataclass(frozen=True, slots=True)
class Ventilation:
    mesure: str
    dimension: str
    fenetre: Fenetre
    ensemble: Valeur
    modalites: tuple[Modalite, ...] = field(default_factory=tuple)

    @property
    def retenues(self) -> tuple[Modalite, ...]:
        return tuple(m for m in self.modalites if m.valeur is not None)

    def extremes(self) -> tuple[Modalite, Modalite] | None:
        """Modalité la plus favorable et la moins favorable, au sens de la mesure."""
        retenues = self.retenues
        if len(retenues) < 2:
            return None
        ordre = sorted(retenues, key=lambda m: m.valeur or 0.0)
        if cat.mesure(self.mesure).sens is cat.Sens.BAS:
            return ordre[0], ordre[-1]
        return ordre[-1], ordre[0]


@dataclass(frozen=True, slots=True)
class PointMensuel:
    mois: str
    valeur: float | None
    effectif: int


def _appliquer_filtre(table: pd.DataFrame, base: cat.Base, filtre: Filtre | None) -> pd.DataFrame:
    if not filtre:
        return table
    resultat = table
    for cle, valeur in filtre.items():
        dimension = cat.dimension(cle)
        if not dimension.disponible_sur(base):
            raise ValueError(
                f"Filtre impossible : {cle!r} n'existe pas sur la table {base.value}."
            )
        resultat = resultat[resultat[dimension.colonne] == valeur]
    return resultat


def _fenetrer(table: pd.DataFrame, base: cat.Base, borne: Fenetre) -> pd.DataFrame:
    colonne = table[COLONNE_DATE[base]]
    return table[(colonne >= pd.Timestamp(borne.debut)) & (colonne <= pd.Timestamp(borne.fin))]


def _agreger(mesure: cat.Mesure, table: pd.DataFrame) -> Valeur:
    """Applique `facteur × num / den + décalage` sur un sous-ensemble déjà filtré."""
    agregat = mesure.agregat
    assert agregat is not None
    effectif = len(table)
    numerateur = float(table[agregat.numerateur].sum()) if effectif else 0.0

    if not agregat.est_ratio:
        return Valeur(mesure.cle, agregat.facteur * numerateur + agregat.decalage,
                      effectif, numerateur, None)

    if agregat.distinct is not None:
        denominateur = float(table[agregat.distinct].nunique()) if effectif else 0.0
    else:
        assert agregat.denominateur is not None
        denominateur = float(table[agregat.denominateur].sum()) if effectif else 0.0

    if denominateur == 0:
        return Valeur(mesure.cle, None, effectif, numerateur, denominateur)
    valeur = agregat.facteur * (numerateur / denominateur) + agregat.decalage
    return Valeur(mesure.cle, valeur, effectif, numerateur, denominateur)


def _concentration_client(_mesure: cat.Mesure, table: pd.DataFrame) -> Valeur:
    """Part du chiffre d'affaires portée par les 10 % de clients les plus gros.

    Mesure un risque de dépendance : au-delà de 50 %, perdre trois clients suffit
    à mettre une PME en difficulté.
    """
    effectif = len(table)
    if effectif == 0:
        return Valeur("concentration_client", None, 0, 0.0, None)
    par_client = table.groupby("client_id")["montant_ht"].sum().sort_values(ascending=False)
    total = float(par_client.sum())
    if total == 0:
        return Valeur("concentration_client", None, effectif, 0.0, 0.0)
    tete = max(1, round(len(par_client) * 0.10))
    part = float(par_client.iloc[:tete].sum())
    return Valeur("concentration_client", part / total, effectif, part, total)


#: Les rares mesures que l'algèbre des agrégats ne couvre pas. Registre fermé :
#: aucune fonction n'y entre sans passer par le catalogue.
SPECIALES = {"concentration_client": _concentration_client}


def _calculer_sur(mesure: cat.Mesure, table: pd.DataFrame) -> Valeur:
    if mesure.special is not None:
        return SPECIALES[mesure.special](mesure, table)
    return _agreger(mesure, table)


def calculer(
    donnees: Donnees,
    cle_mesure: str,
    cadrage: Cadrage,
    filtre: Filtre | None = None,
    niveau: Niveau | None = None,
) -> Valeur:
    """Valeur scalaire d'une mesure sur une fenêtre, éventuellement filtrée."""
    if niveau is not None:
        cat.valider(cle_mesure, None, niveau)
    mesure = cat.mesure(cle_mesure)
    borne = fenetre(cadrage, donnees.situation, donnees.debut)
    table = _fenetrer(donnees.table(mesure.base), mesure.base, borne)
    return _calculer_sur(mesure, _appliquer_filtre(table, mesure.base, filtre))


def ventiler(
    donnees: Donnees,
    cle_mesure: str,
    cle_dimension: str,
    cadrage: Cadrage,
    filtre: Filtre | None = None,
    niveau: Niveau | None = None,
) -> Ventilation:
    """Répartition d'une mesure selon une dimension, sur une fenêtre donnée."""
    if niveau is not None:
        cat.valider(cle_mesure, cle_dimension, niveau)
    mesure = cat.mesure(cle_mesure)
    dimension = cat.dimension(cle_dimension)
    if not dimension.disponible_sur(mesure.base):
        raise ValueError(
            f"{cle_mesure!r} se calcule sur {mesure.base.value}, "
            f"où la dimension {cle_dimension!r} n'existe pas."
        )

    return ventiler_fenetre(
        donnees, mesure, dimension, fenetre(cadrage, donnees.situation, donnees.debut), filtre
    )


def ventiler_fenetre(
    donnees: Donnees,
    mesure: cat.Mesure,
    dimension: cat.Dimension,
    borne: Fenetre,
    filtre: Filtre | None = None,
) -> Ventilation:
    """Ventilation sur une fenêtre déjà résolue.

    Sert au criblage, qui découpe la période en moitiés pour éprouver la
    stabilité d'un écart : ces fenêtres-là ne correspondent à aucun cadrage.
    """
    table = _appliquer_filtre(
        _fenetrer(donnees.table(mesure.base), mesure.base, borne), mesure.base, filtre
    )
    ensemble = _calculer_sur(mesure, table)

    libelles = list(dict.fromkeys(table[dimension.colonne].dropna()))
    if dimension.ordonnee and dimension.modalites:
        connues = [m for m in dimension.modalites if m in libelles]
        libelles = connues + [m for m in libelles if m not in dimension.modalites]
    else:
        libelles = sorted(libelles)

    total_numerateur = ensemble.numerateur
    modalites: list[Modalite] = []
    for libelle in libelles:
        sous_table = table[table[dimension.colonne] == libelle]
        valeur = _calculer_sur(mesure, sous_table)
        poids = valeur.numerateur / total_numerateur if total_numerateur else 0.0
        modalites.append(
            Modalite(
                libelle=str(libelle),
                valeur=valeur.valeur,
                effectif=valeur.effectif,
                numerateur=valeur.numerateur,
                denominateur=valeur.denominateur,
                poids=poids,
            )
        )

    return Ventilation(
        mesure=mesure.cle,
        dimension=dimension.cle,
        fenetre=borne,
        ensemble=ensemble,
        modalites=tuple(modalites),
    )


def serie_mensuelle(
    donnees: Donnees,
    cle_mesure: str,
    cadrage: Cadrage = Cadrage.PERIODE_TOTALE,
    filtre: Filtre | None = None,
) -> tuple[PointMensuel, ...]:
    """Évolution mois par mois. Les mois sans donnée ne sont pas inventés."""
    mesure = cat.mesure(cle_mesure)
    borne = fenetre(cadrage, donnees.situation, donnees.debut)
    table = _appliquer_filtre(
        _fenetrer(donnees.table(mesure.base), mesure.base, borne), mesure.base, filtre
    )
    points: list[PointMensuel] = []
    for mois in sorted(table["mois"].unique()):
        valeur = _calculer_sur(mesure, table[table["mois"] == mois])
        points.append(PointMensuel(str(mois), valeur.valeur, valeur.effectif))
    return tuple(points)


@dataclass(frozen=True, slots=True)
class Comparaison:
    actuelle: Valeur
    passee: Valeur | None
    ecart_relatif: float | None
    #: Renseigné quand l'écart est refusé, pour que l'appelant sache pourquoi.
    motif: str | None = None


def comparer(
    donnees: Donnees,
    cle_mesure: str,
    reference: Cadrage,
    comparaison: Cadrage,
    filtre: Filtre | None = None,
) -> Comparaison:
    """Deux valeurs et leur écart, quand l'écart a un sens.

    Sur une mesure de stock, ni la valeur passée ni l'écart ne sont produits :
    les donner reviendrait à laisser calculer un écart faux.
    """
    mesure = cat.mesure(cle_mesure)
    actuelle = calculer(donnees, cle_mesure, reference, filtre)
    if not mesure.comparable_entre_periodes:
        return Comparaison(
            actuelle,
            None,
            None,
            "mesure de stock : un état à la date de situation n'a pas de version "
            "« période précédente » sans recalcul à une date antérieure",
        )
    passee = calculer(donnees, cle_mesure, comparaison, filtre)
    if actuelle.valeur is None or passee.valeur is None or passee.valeur == 0:
        return Comparaison(actuelle, passee, None, "valeur de référence nulle ou non calculable")
    return Comparaison(actuelle, passee, actuelle.valeur / passee.valeur - 1)
