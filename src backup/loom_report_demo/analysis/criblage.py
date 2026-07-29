"""Criblage : ce que le code trouve seul, avant que l'agent n'intervienne.

Énumérer l'espace des candidats à une dimension est trivial pour du code et
coûteux pour un modèle. On le fait donc ici, exhaustivement, et on score chaque
candidat sur cinq critères. L'agent recevra les mieux placés, et n'aura à
raisonner que sur l'espace à deux dimensions et conditionnel — celui qui est
réellement combinatoire, et où il gagne sa place.

Ce module pose aussi la référence contre laquelle l'apport de l'agent se mesure :
`uv run candidats` montre ce qu'on obtient sans une ligne d'IA.

**La matérialité est le score qui décide.** Les quatre autres disent qu'un écart
est réel ; celui-ci dit ce qu'il coûte. Sans lui, un modèle retient l'écart le
plus spectaculaire — le taux d'accord des SMS, inférieur de six points à celui
des courriels, vrai et significatif, mais portant sur cent soixante relances et
donc sans enjeu. Convertir en euros et annualiser rend les candidats comparables
entre eux, quelle que soit leur unité d'origine.

Les pondérations du score global sont un choix, pas une vérité. Elles sont
rassemblées dans `PONDERATIONS` pour être discutées d'un seul endroit, et les
cinq composantes restent exposées séparément afin qu'un lecteur puisse ne pas
être d'accord.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from loom_report_demo.analysis import catalogue as cat
from loom_report_demo.analysis.cadrages import PRINCIPAL, Cadrage, Fenetre, fenetre
from loom_report_demo.analysis.chargement import COLONNE_DATE, Donnees
from loom_report_demo.analysis.moteur import (
    Modalite,
    Ventilation,
    ventiler,
    ventiler_fenetre,
)
from loom_report_demo.niveaux import Niveau

#: Effectif minimal d'une modalité pour qu'elle compte. En dessous, une
#: ventilation ne mesure plus rien : elle tire au sort.
EFFECTIF_MINIMAL: dict[Niveau, int] = {
    Niveau.STRATEGIQUE: 30,
    Niveau.GESTION: 20,
    Niveau.OPERATIONNEL: 8,
}

#: Part du numérateur que les modalités retenues doivent couvrir. En dessous, la
#: ventilation est trop fragmentée pour qu'on en tire une décision.
COUVERTURE_MINIMALE = 0.70

#: Écart relatif en deçà duquel un candidat n'a rien à dire.
DISPERSION_PLANCHER = 0.05

#: Poids des cinq composantes. Un choix assumé, pas une vérité : la matérialité
#: domine parce qu'un constat chiffrable vaut mieux qu'un constat vrai.
PONDERATIONS = {
    "materialite": 0.45,
    "dispersion": 0.20,
    "stabilite": 0.20,
    "monotonie": 0.15,
}


@dataclass(frozen=True, slots=True)
class Scores:
    """Les cinq composantes, exposées séparément pour rester discutables."""

    effectif_min: int
    dispersion: float
    monotonie: float
    stabilite: float
    materialite_euros: float | None


@dataclass(frozen=True, slots=True)
class Candidat:
    mesure: str
    dimension: str
    cadrage: Cadrage
    libelle: str
    unite: str
    valeur_ensemble: float | None
    modalite_defavorable: str | None
    valeur_defavorable: float | None
    #: Valeur de l'ensemble *hors* la modalité défavorable : « si elle faisait
    #: comme le reste ». Plus honnête que la moyenne, qui l'inclut.
    cible: float | None
    effectif_defavorable: int
    nb_modalites: int
    scores: Scores
    score_global: float
    recevable: bool
    motif_rejet: str | None = None

    @property
    def cle(self) -> str:
        return f"{self.mesure}|{self.dimension}"


@dataclass(frozen=True, slots=True)
class Criblage:
    niveau: Niveau
    fenetre: Fenetre
    #: Les mieux placés, remis à l'agent.
    retenus: tuple[Candidat, ...]
    #: Tous les candidats recevables, classés — `retenus` en est le début.
    evalues: tuple[Candidat, ...]
    rejetes: tuple[Candidat, ...]
    #: Facteur de conversion d'un gain de la fenêtre vers douze mois.
    annualisation: float

    @property
    def explores(self) -> int:
        return len(self.evalues) + len(self.rejetes)


# --------------------------------------------------------------- statistiques
def _rangs(valeurs: list[float]) -> list[float]:
    """Rangs moyens, pour que les ex æquo ne biaisent pas la corrélation."""
    ordre = sorted(range(len(valeurs)), key=lambda i: valeurs[i])
    rangs = [0.0] * len(valeurs)
    i = 0
    while i < len(ordre):
        j = i
        while j + 1 < len(ordre) and valeurs[ordre[j + 1]] == valeurs[ordre[i]]:
            j += 1
        moyen = (i + j) / 2 + 1
        for k in range(i, j + 1):
            rangs[ordre[k]] = moyen
        i = j + 1
    return rangs


def spearman(x: list[float], y: list[float]) -> float:
    """Corrélation de rang. Rend 0.0 quand elle n'est pas définie."""
    if len(x) != len(y) or len(x) < 3:
        return 0.0
    rx, ry = _rangs(x), _rangs(y)
    n = len(rx)
    moyenne = (n + 1) / 2
    numerateur = sum((a - moyenne) * (b - moyenne) for a, b in zip(rx, ry, strict=True))
    variance_x = sum((a - moyenne) ** 2 for a in rx)
    variance_y = sum((b - moyenne) ** 2 for b in ry)
    if variance_x == 0 or variance_y == 0:
        return 0.0
    return numerateur / (variance_x * variance_y) ** 0.5


# ---------------------------------------------------------------- matérialité
def _taux_marge_global(donnees: Donnees, borne: Fenetre) -> float:
    import pandas as pd

    table = donnees.factures
    colonne = table[COLONNE_DATE[cat.Base.FACTURES]]
    fenetree = table[
        (colonne >= pd.Timestamp(borne.debut)) & (colonne <= pd.Timestamp(borne.fin))
    ]
    ca = float(fenetree["montant_ht"].sum())
    return float(fenetree["marge"].sum()) / ca if ca else 0.0


def _cout_horaire_moyen(donnees: Donnees) -> float:
    return float(donnees.techniciens["cout_horaire"].mean())


def _materialite(
    mesure: cat.Mesure,
    pire: Modalite,
    cible: float | None,
    taux_marge: float,
    cout_horaire: float,
    annualisation: float,
) -> float | None:
    """Combien rapporterait d'amener la modalité défavorable au niveau des autres.

    Le résultat est en euros de marge brute sur douze mois, quelle que soit
    l'unité d'origine : c'est ce qui rend deux candidats comparables.
    """
    if mesure.conversion is cat.Conversion.AUCUNE:
        return None
    if cible is None or pire.valeur is None or pire.denominateur is None:
        return None

    ecart = cible - pire.valeur
    if mesure.sens is cat.Sens.BAS:
        ecart = -ecart
    if ecart <= 0:
        return 0.0

    volume = ecart * pire.denominateur
    if mesure.conversion is cat.Conversion.MARGE:
        euros = volume
    elif mesure.conversion is cat.Conversion.CHIFFRE_AFFAIRES:
        euros = volume * taux_marge
    else:  # heures économisées
        euros = volume * cout_horaire
    return max(0.0, euros * annualisation)


# ------------------------------------------------------------------- scoring
def _dispersion(pire: Modalite | None, cible: float | None) -> float:
    """Écart relatif entre la modalité défavorable et l'objectif atteignable.

    Rapporté à la plus grande des deux valeurs, donc borné à 1 et sans échelle :
    une mesure dont la moyenne frôle zéro — la dérive horaire tourne autour de
    2 % — produisait sinon des dispersions de 900 %, qui écrasaient tous les
    autres candidats au moment de normaliser.
    """
    if pire is None or pire.valeur is None or cible is None:
        return 0.0
    echelle = max(abs(cible), abs(pire.valeur), 1e-9)
    return min(1.0, abs(pire.valeur - cible) / echelle)


def _monotonie(dimension: cat.Dimension, retenues: list[Modalite]) -> float:
    """Gradient le long d'une dimension ordonnée.

    Une dimension sans ordre naturel n'a pas de gradient : on rend 0.0 plutôt
    qu'un nombre inventé sur un classement alphabétique.
    """
    if not dimension.ordonnee or len(retenues) < 3:
        return 0.0
    ordre = list(dimension.modalites)
    couples = [
        (float(ordre.index(m.libelle)), m.valeur)
        for m in retenues
        if m.libelle in ordre and m.valeur is not None
    ]
    if len(couples) < 3:
        return 0.0
    return abs(spearman([a for a, _ in couples], [b for _, b in couples]))


def _stabilite(
    donnees: Donnees,
    mesure: cat.Mesure,
    dimension: cat.Dimension,
    borne: Fenetre,
    pire_libelle: str,
    sens_defavorable: bool,
) -> float:
    """L'écart tient-il sur les deux moitiés de la fenêtre ?

    Un écart qui n'apparaît que sur une moitié est un accident, pas un constat.
    """
    milieu = borne.debut + timedelta(days=borne.jours // 2)
    moities = (
        Fenetre(borne.cadrage, borne.debut, milieu - timedelta(days=1), "première moitié"),
        Fenetre(borne.cadrage, milieu, borne.fin, "seconde moitié"),
    )
    complet = ventiler_fenetre(donnees, mesure, dimension, borne)
    ecart_complet = _ecart_signe(complet, pire_libelle, sens_defavorable)
    if ecart_complet is None or ecart_complet <= 0:
        return 0.0

    parts: list[float] = []
    for moitie in moities:
        partielle = ventiler_fenetre(donnees, mesure, dimension, moitie)
        ecart = _ecart_signe(partielle, pire_libelle, sens_defavorable)
        parts.append(0.0 if ecart is None else max(0.0, min(1.0, ecart / ecart_complet)))
    return sum(parts) / len(parts)


def _ecart_signe(
    ventilation: Ventilation, libelle: str, sens_defavorable: bool
) -> float | None:
    """Écart d'une modalité à l'ensemble, positif quand il est défavorable."""
    ensemble = ventilation.ensemble.valeur
    if ensemble is None:
        return None
    cible = next(
        (m for m in ventilation.modalites if m.libelle == libelle and m.valeur is not None), None
    )
    if cible is None or cible.valeur is None:
        return None
    return cible.valeur - ensemble if sens_defavorable else ensemble - cible.valeur


def _normaliser(valeur: float, maximum: float) -> float:
    return 0.0 if maximum <= 0 else min(1.0, valeur / maximum)


# ------------------------------------------------------------------ criblage
def cribler(
    donnees: Donnees,
    niveau: Niveau,
    cadrage: Cadrage | None = None,
    limite: int = 12,
) -> Criblage:
    """Énumère tous les couples valides, les score, et rend les mieux placés."""
    borne = fenetre(cadrage or PRINCIPAL[niveau], donnees.situation, donnees.debut)
    annualisation = 365.0 / borne.jours
    seuil = EFFECTIF_MINIMAL[niveau]
    taux_marge = _taux_marge_global(donnees, borne)
    cout_horaire = _cout_horaire_moyen(donnees)

    bruts: list[tuple[Candidat, cat.Mesure, cat.Dimension, str | None, bool]] = []

    for cle_mesure, cle_dimension in cat.croisements_valides(niveau):
        mesure = cat.mesure(cle_mesure)
        dimension = cat.dimension(cle_dimension)
        ventilation = ventiler(donnees, cle_mesure, cle_dimension, borne.cadrage)

        retenues = [
            m for m in ventilation.modalites if m.valeur is not None and m.effectif >= seuil
        ]
        motif: str | None = None
        if len(retenues) < 2:
            motif = f"moins de deux modalités atteignent {seuil} observations"
        else:
            couverture = sum(m.poids for m in retenues)
            if couverture < COUVERTURE_MINIMALE:
                motif = f"les modalités retenues ne couvrent que {couverture:.0%} du total"

        sens_defavorable = mesure.sens is cat.Sens.BAS
        pire: Modalite | None = None
        cible: float | None = None
        if retenues:
            pire = max(
                retenues,
                key=lambda m: (m.valeur or 0.0) if sens_defavorable else -(m.valeur or 0.0),
            )
            cible = _cible_hors(ventilation, pire, retenues)

        dispersion = _dispersion(pire, cible)
        if motif is None and dispersion < DISPERSION_PLANCHER:
            motif = f"écart de {dispersion:.1%}, sous le plancher de {DISPERSION_PLANCHER:.0%}"

        materialite = (
            _materialite(mesure, pire, cible, taux_marge, cout_horaire, annualisation)
            if pire is not None
            else None
        )
        monotonie = _monotonie(dimension, retenues)

        candidat = Candidat(
            mesure=cle_mesure,
            dimension=cle_dimension,
            cadrage=borne.cadrage,
            libelle=f"{mesure.libelle} par {dimension.libelle.lower()}",
            unite=mesure.unite.value,
            valeur_ensemble=ventilation.ensemble.valeur,
            modalite_defavorable=pire.libelle if pire else None,
            valeur_defavorable=pire.valeur if pire else None,
            cible=cible,
            effectif_defavorable=pire.effectif if pire else 0,
            nb_modalites=len(retenues),
            scores=Scores(
                effectif_min=min((m.effectif for m in retenues), default=0),
                dispersion=dispersion,
                monotonie=monotonie,
                stabilite=0.0,
                materialite_euros=materialite,
            ),
            score_global=0.0,
            recevable=motif is None,
            motif_rejet=motif,
        )
        bruts.append(
            (candidat, mesure, dimension, pire.libelle if pire else None, sens_defavorable)
        )

    # La stabilité coûte deux ventilations de plus : on ne la calcule que sur les
    # candidats qui ont franchi les gardes.
    recevables: list[Candidat] = []
    rejetes: list[Candidat] = []
    for candidat, mesure, dimension, pire_libelle, sens_defavorable in bruts:
        if not candidat.recevable or pire_libelle is None:
            rejetes.append(candidat)
            continue
        stabilite = _stabilite(donnees, mesure, dimension, borne, pire_libelle, sens_defavorable)
        recevables.append(
            _remplacer_scores(candidat, stabilite=stabilite)
        )

    plafond = max(
        (c.scores.materialite_euros or 0.0 for c in recevables), default=0.0
    )
    plafond_dispersion = max((c.scores.dispersion for c in recevables), default=0.0)
    notes: list[Candidat] = []
    for candidat in recevables:
        score = (
            PONDERATIONS["materialite"]
            * _normaliser(candidat.scores.materialite_euros or 0.0, plafond)
            + PONDERATIONS["dispersion"]
            * _normaliser(candidat.scores.dispersion, plafond_dispersion)
            + PONDERATIONS["stabilite"] * candidat.scores.stabilite
            + PONDERATIONS["monotonie"] * candidat.scores.monotonie
        )
        notes.append(_remplacer_scores(candidat, score_global=round(score, 6)))

    notes.sort(key=lambda c: (-c.score_global, c.cle))
    return Criblage(
        niveau=niveau,
        fenetre=borne,
        retenus=tuple(notes[:limite]),
        evalues=tuple(notes),
        rejetes=tuple(rejetes),
        annualisation=annualisation,
    )


def _cible_hors(
    ventilation: Ventilation, pire: Modalite, retenues: list[Modalite]
) -> float | None:
    """Valeur de l'ensemble si l'on retire la modalité défavorable.

    « Si Bordeaux faisait comme le reste du groupe » est un objectif atteignable ;
    « si Bordeaux atteignait la moyenne » ne l'est pas tout à fait, puisque la
    moyenne inclut Bordeaux et se déplace avec lui.
    """
    autres = [m for m in retenues if m.libelle != pire.libelle and m.valeur is not None]
    if not autres:
        return None
    mesure = cat.mesure(ventilation.mesure)
    # Une mesure spéciale n'a pas d'agrégat à recomposer : on retombe sur la
    # moyenne simple des autres modalités, faute de mieux.
    if mesure.agregat is None or any(m.denominateur is None for m in autres):
        return sum(m.valeur or 0.0 for m in autres) / len(autres)
    denominateur = sum(m.denominateur or 0.0 for m in autres)
    if denominateur == 0:
        return None
    numerateur = sum(m.numerateur for m in autres)
    return mesure.agregat.facteur * (numerateur / denominateur) + mesure.agregat.decalage


def _remplacer_scores(
    candidat: Candidat, stabilite: float | None = None, score_global: float | None = None
) -> Candidat:
    scores = candidat.scores
    if stabilite is not None:
        scores = Scores(
            effectif_min=scores.effectif_min,
            dispersion=scores.dispersion,
            monotonie=scores.monotonie,
            stabilite=stabilite,
            materialite_euros=scores.materialite_euros,
        )
    return Candidat(
        mesure=candidat.mesure,
        dimension=candidat.dimension,
        cadrage=candidat.cadrage,
        libelle=candidat.libelle,
        unite=candidat.unite,
        valeur_ensemble=candidat.valeur_ensemble,
        modalite_defavorable=candidat.modalite_defavorable,
        valeur_defavorable=candidat.valeur_defavorable,
        cible=candidat.cible,
        effectif_defavorable=candidat.effectif_defavorable,
        nb_modalites=candidat.nb_modalites,
        scores=scores,
        score_global=candidat.score_global if score_global is None else score_global,
        recevable=candidat.recevable,
        motif_rejet=candidat.motif_rejet,
    )
