"""Les outils d'exploration remis à l'agent.

Ce module ne connaît ni `loom_ia` ni le réseau : il expose des fonctions pures et
leurs schémas d'entrée. `reporting.py` les enveloppe ensuite dans des
`FunctionTool`. Cette séparation n'est pas cosmétique — elle permet de tester
exhaustivement le comportement des outils sans clé d'API, alors que la partie
proprement agentique ne se vérifie qu'en exécution réelle.

**Le niveau est capturé dans la fermeture, jamais exposé dans le schéma.** Un
modèle ne peut donc pas s'échapper du registre qu'on lui a assigné : les `enum`
de mesures et de dimensions sont construits pour son niveau et pour lui seul.

**Les arguments sont des `enum` fermés.** Aucune expression libre n'atteint
pandas : pas d'`eval`, pas de filtre arbitraire, pas de surface d'attaque. Le
bloc B de `loom-ia` valide les arguments contre ce schéma *avant* exécution ; la
validation refaite ici couvre le cas où la garde amont serait désactivée, et
surtout produit un message que le modèle peut exploiter pour se corriger.

**`noter_hypothese` n'exécute rien.** Il enregistre, à coût nul. Sa raison d'être
est de forcer l'engagement *avant* de voir le résultat : sans lui, un modèle
rationalise après coup et toute trouvaille paraît prévue.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from loom_report_demo.analysis import catalogue as cat
from loom_report_demo.analysis.cadrages import COMPARAISON, PRINCIPAL, Cadrage
from loom_report_demo.analysis.chargement import Donnees
from loom_report_demo.analysis.criblage import EFFECTIF_MINIMAL, spearman
from loom_report_demo.analysis.moteur import calculer, serie_mensuelle, ventiler
from loom_report_demo.niveaux import Niveau

#: Au-delà, une ventilation coûte des jetons sans rien apprendre.
MAX_MODALITES = 12
#: Un croisement à deux dimensions explose vite : on refuse plutôt que de tronquer.
MAX_CELLULES_CROISEMENT = 30
#: Nombre de points rendus par une série mensuelle.
MAX_POINTS_SERIE = 24


class ErreurOutil(ValueError):
    """Argument hors catalogue. Le message liste les valeurs admises.

    Levée telle quelle, elle est convertie par `loom-ia` en `tool_result` marqué
    en erreur : le modèle la lit et se corrige, la boucle ne casse pas.
    """


@dataclass(frozen=True, slots=True)
class Hypothese:
    identifiant: str
    enonce: str
    mesure_visee: str
    dimension_visee: str | None


@dataclass(frozen=True, slots=True)
class Appel:
    """Une ligne de trace, affichée en direct pendant l'exploration."""

    outil: str
    arguments: dict[str, Any]
    resume: str
    duree_ms: int


@dataclass
class Registre:
    """État d'une exploration : hypothèses notées et appels effectués.

    Mutable et propre à une exécution. Il sert à trois choses : afficher la trace
    en direct, vérifier que le modèle a bien noté avant de sonder, et alimenter
    la feuille « Ce qui a été regardé ».
    """

    hypotheses: dict[str, Hypothese] = field(default_factory=dict[str, Hypothese])
    appels: list[Appel] = field(default_factory=list[Appel])

    @property
    def sondages(self) -> int:
        return sum(1 for a in self.appels if a.outil != "noter_hypothese")

    def notees_avant_sondage(self) -> bool:
        """Vrai si au moins une hypothèse précède le premier sondage."""
        for appel in self.appels:
            if appel.outil == "noter_hypothese":
                return True
            return False
        return False


@dataclass(frozen=True, slots=True)
class SpecOutil:
    """Description neutre d'un outil, indépendante de `loom_ia`."""

    nom: str
    description: str
    input_schema: dict[str, Any]
    fn: Callable[..., dict[str, Any]]


def _arrondir(valeur: float | None, unite: cat.Unite) -> float | None:
    if valeur is None:
        return None
    if unite is cat.Unite.EUROS:
        return round(valeur)
    if unite in (cat.Unite.JOURS, cat.Unite.NOMBRE):
        return round(valeur, 1)
    return round(valeur, 4)


def _verifier(cle_mesure: str, cle_dimension: str | None, niveau: Niveau) -> cat.Mesure:
    try:
        cat.valider(cle_mesure, cle_dimension, niveau)
    except (KeyError, ValueError) as erreur:
        raise ErreurOutil(str(erreur)) from None
    return cat.mesure(cle_mesure)


def _modalites_admises(
    dimension: cat.Dimension, donnees: Donnees, base: cat.Base
) -> list[str]:
    colonne = donnees.table(base)[dimension.colonne]
    return sorted(str(x) for x in colonne.dropna().unique())


# ------------------------------------------------------------------- les outils
def _ventilation(
    donnees: Donnees, niveau: Niveau, registre: Registre, mesure: str, dimension: str
) -> dict[str, Any]:
    objet = _verifier(mesure, dimension, niveau)
    resultat = ventiler(donnees, mesure, dimension, PRINCIPAL[niveau])
    seuil = EFFECTIF_MINIMAL[niveau]

    retenues = [m for m in resultat.modalites if m.valeur is not None and m.effectif >= seuil]
    ecartees = [m.libelle for m in resultat.modalites if m not in retenues]
    # Toujours de la plus défavorable à la plus favorable, quel que soit le sens
    # de la mesure : le modèle n'a pas à raisonner sur l'ordre du tri.
    retenues.sort(key=lambda m: m.valeur or 0.0, reverse=objet.sens is cat.Sens.BAS)

    return {
        "mesure": mesure,
        "dimension": dimension,
        "unite": objet.unite.value,
        "sens_favorable": objet.sens.value,
        "ordre": "de la plus défavorable à la plus favorable",
        "ensemble": _arrondir(resultat.ensemble.valeur, objet.unite),
        "modalites": [
            {
                "libelle": m.libelle,
                "valeur": _arrondir(m.valeur, objet.unite),
                "effectif": m.effectif,
                "poids": round(m.poids, 3),
            }
            for m in retenues[:MAX_MODALITES]
        ],
        "ecartees_effectif_insuffisant": ecartees,
        "seuil_effectif": seuil,
    }


def _serie_mensuelle(
    donnees: Donnees, niveau: Niveau, registre: Registre, mesure: str
) -> dict[str, Any]:
    objet = _verifier(mesure, None, niveau)
    points = serie_mensuelle(donnees, mesure, Cadrage.PERIODE_TOTALE)
    valeurs = [(p.mois, p.valeur) for p in points if p.valeur is not None]
    if len(valeurs) < 3:
        raise ErreurOutil(f"Série trop courte pour {mesure!r} : {len(valeurs)} points.")

    rangs = [float(i) for i in range(len(valeurs))]
    correlation = spearman(rangs, [v for _, v in valeurs])
    if correlation > 0.5:
        tendance = "croissante"
    elif correlation < -0.5:
        tendance = "decroissante"
    else:
        tendance = "instable"

    derniers = valeurs[-MAX_POINTS_SERIE:]
    return {
        "mesure": mesure,
        "unite": objet.unite.value,
        "nb_points": len(valeurs),
        "tendance": tendance,
        "monotonie": round(abs(correlation), 3),
        "premier": [valeurs[0][0], _arrondir(valeurs[0][1], objet.unite)],
        "dernier": [valeurs[-1][0], _arrondir(valeurs[-1][1], objet.unite)],
        "serie": [[m, _arrondir(v, objet.unite)] for m, v in derniers],
    }


def _comparer(
    donnees: Donnees,
    niveau: Niveau,
    registre: Registre,
    mesure: str,
    dimension: str,
    modalite_a: str,
    modalite_b: str,
) -> dict[str, Any]:
    objet = _verifier(mesure, dimension, niveau)
    objet_dimension = cat.dimension(dimension)
    admises = _modalites_admises(objet_dimension, donnees, objet.base)
    for modalite in (modalite_a, modalite_b):
        if modalite not in admises:
            raise ErreurOutil(
                f"Modalité inconnue pour {dimension!r} : {modalite!r}. "
                f"Admises : {', '.join(admises)}"
            )
    if modalite_a == modalite_b:
        raise ErreurOutil("Les deux modalités à comparer sont identiques.")

    resultats = {
        modalite: calculer(donnees, mesure, PRINCIPAL[niveau], filtre={dimension: modalite})
        for modalite in (modalite_a, modalite_b)
    }
    a, b = resultats[modalite_a], resultats[modalite_b]
    ecart = None if a.valeur is None or b.valeur is None else a.valeur - b.valeur
    return {
        "mesure": mesure,
        "dimension": dimension,
        "unite": objet.unite.value,
        modalite_a: {"valeur": _arrondir(a.valeur, objet.unite), "effectif": a.effectif},
        modalite_b: {"valeur": _arrondir(b.valeur, objet.unite), "effectif": b.effectif},
        "ecart": _arrondir(ecart, objet.unite),
        "favorable_a": None
        if ecart is None
        else (ecart > 0) == (objet.sens is cat.Sens.HAUT),
    }


def _croiser(
    donnees: Donnees,
    niveau: Niveau,
    registre: Registre,
    mesure: str,
    dimension_1: str,
    dimension_2: str,
) -> dict[str, Any]:
    objet = _verifier(mesure, dimension_1, niveau)
    _verifier(mesure, dimension_2, niveau)
    if dimension_1 == dimension_2:
        raise ErreurOutil("Les deux dimensions du croisement sont identiques.")

    d1, d2 = cat.dimension(dimension_1), cat.dimension(dimension_2)
    m1 = _modalites_admises(d1, donnees, objet.base)
    m2 = _modalites_admises(d2, donnees, objet.base)
    if len(m1) * len(m2) > MAX_CELLULES_CROISEMENT:
        raise ErreurOutil(
            f"Croisement trop large : {len(m1)} x {len(m2)} cellules, maximum "
            f"{MAX_CELLULES_CROISEMENT}. Choisissez des dimensions moins fines, ou "
            f"filtrez d'abord avec `ventilation`."
        )

    seuil = EFFECTIF_MINIMAL[niveau]
    cellules: list[dict[str, Any]] = []
    for a in m1:
        for b in m2:
            valeur = calculer(
                donnees, mesure, PRINCIPAL[niveau], filtre={dimension_1: a, dimension_2: b}
            )
            if valeur.valeur is None or valeur.effectif < seuil:
                continue
            cellules.append(
                {
                    dimension_1: a,
                    dimension_2: b,
                    "valeur": _arrondir(valeur.valeur, objet.unite),
                    "effectif": valeur.effectif,
                }
            )
    return {
        "mesure": mesure,
        "unite": objet.unite.value,
        "ensemble": _arrondir(calculer(donnees, mesure, PRINCIPAL[niveau]).valeur, objet.unite),
        "cellules": cellules,
        "cellules_sous_le_seuil": len(m1) * len(m2) - len(cellules),
        "seuil_effectif": seuil,
    }


def _concentration(
    donnees: Donnees, niveau: Niveau, registre: Registre, mesure: str, dimension: str
) -> dict[str, Any]:
    # Appel pour son seul effet : refuser un couple hors catalogue. La
    # concentration ne travaille que sur des poids, elle n'a pas besoin de
    # l'unité de la mesure.
    _verifier(mesure, dimension, niveau)
    resultat = ventiler(donnees, mesure, dimension, PRINCIPAL[niveau])
    poids = sorted(
        ((m.libelle, m.poids) for m in resultat.modalites if m.poids > 0),
        key=lambda x: x[1],
        reverse=True,
    )
    if not poids:
        raise ErreurOutil(f"Aucune modalité contributrice pour {mesure!r} par {dimension!r}.")

    cumul = 0.0
    paliers: list[dict[str, Any]] = []
    for rang, (libelle, part) in enumerate(poids, start=1):
        cumul += part
        paliers.append({"rang": rang, "libelle": libelle, "part": round(part, 3),
                        "cumul": round(cumul, 3)})
        if cumul >= 0.80:
            break
    return {
        "mesure": mesure,
        "dimension": dimension,
        "nb_modalites": len(poids),
        "paliers": paliers,
        "modalites_pour_80_pct": len(paliers),
        "lecture": (
            f"{len(paliers)} modalité(s) sur {len(poids)} portent quatre cinquièmes du total."
        ),
    }


def _noter_hypothese(
    donnees: Donnees,
    niveau: Niveau,
    registre: Registre,
    identifiant: str,
    enonce: str,
    mesure_visee: str,
    dimension_visee: str | None = None,
) -> dict[str, Any]:
    """N'exécute rien : enregistre une intention avant de la mettre à l'épreuve."""
    if identifiant in registre.hypotheses:
        raise ErreurOutil(f"L'hypothèse {identifiant!r} a déjà été notée.")
    _verifier(mesure_visee, dimension_visee, niveau)
    registre.hypotheses[identifiant] = Hypothese(
        identifiant=identifiant,
        enonce=enonce,
        mesure_visee=mesure_visee,
        dimension_visee=dimension_visee,
    )
    return {
        "enregistree": identifiant,
        "total_notees": len(registre.hypotheses),
        "rappel": (
            "Sonde maintenant cette hypothèse. Elle devra figurer dans la sortie "
            "finale, retenue ou écartée avec son motif."
        ),
    }


# ------------------------------------------------------------------ les schémas
def _enum_mesures(niveau: Niveau) -> list[str]:
    return sorted(m.cle for m in cat.mesures_du_niveau(niveau))


def _enum_dimensions(niveau: Niveau) -> list[str]:
    return sorted(d.cle for d in cat.dimensions_du_niveau(niveau))


def construire_outils(donnees: Donnees, niveau: Niveau, registre: Registre) -> list[SpecOutil]:
    """Fabrique les six outils, liés à un niveau et à un registre.

    Le niveau et les données sont capturés ici, hors de portée du modèle.
    """
    mesures = _enum_mesures(niveau)
    dimensions = _enum_dimensions(niveau)
    fenetre = PRINCIPAL[niveau].value
    comparaison = COMPARAISON[PRINCIPAL[niveau]].value

    def lier(fonction: Callable[..., dict[str, Any]]) -> Callable[..., dict[str, Any]]:
        def enveloppe(**arguments: Any) -> dict[str, Any]:
            depart = time.perf_counter()
            resultat = fonction(donnees, niveau, registre, **arguments)
            registre.appels.append(
                Appel(
                    outil=fonction.__name__.lstrip("_"),
                    arguments=arguments,
                    resume=_resumer(fonction.__name__.lstrip("_"), arguments, resultat),
                    duree_ms=int((time.perf_counter() - depart) * 1000),
                )
            )
            return resultat

        return enveloppe

    def objet(**proprietes: Any) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": proprietes,
            "required": [c for c, p in proprietes.items() if "default" not in p],
        }

    champ_mesure = {"enum": mesures, "description": "Clé de mesure du catalogue."}
    champ_dimension = {"enum": dimensions, "description": "Clé de dimension du catalogue."}

    return [
        SpecOutil(
            nom="noter_hypothese",
            description=(
                "Enregistre une hypothèse AVANT de la sonder. N'exécute aucun calcul et ne "
                "coûte rien. À appeler systématiquement en premier : une hypothèse formulée "
                "après coup n'est plus une hypothèse. Chaque hypothèse notée devra figurer "
                "dans la sortie finale, retenue ou écartée avec son motif."
            ),
            input_schema=objet(
                identifiant={"type": "string", "description": "Court et unique, par exemple H1."},
                enonce={
                    "type": "string",
                    "description": "Ce que tu penses trouver, formulé sans aucun chiffre.",
                },
                mesure_visee=champ_mesure,
                dimension_visee={**champ_dimension, "default": None},
            ),
            fn=lier(_noter_hypothese),
        ),
        SpecOutil(
            nom="ventilation",
            description=(
                f"Répartit une mesure selon une dimension, sur la fenêtre {fenetre}. Rend la "
                "valeur d'ensemble, celle de chaque modalité, son effectif et son poids. Les "
                "modalités trop peu peuplées sont écartées et signalées : elles ne mesurent "
                "rien. C'est l'outil de premier recours."
            ),
            input_schema=objet(mesure=champ_mesure, dimension=champ_dimension),
            fn=lier(_ventilation),
        ),
        SpecOutil(
            nom="serie_mensuelle",
            description=(
                "Évolution d'une mesure mois par mois sur toute la période. Sert à distinguer "
                "une tendance installée d'un accident ponctuel : rend la monotonie et le sens "
                "de la tendance en plus des points."
            ),
            input_schema=objet(mesure=champ_mesure),
            fn=lier(_serie_mensuelle),
        ),
        SpecOutil(
            nom="comparer",
            description=(
                "Confronte deux modalités d'une même dimension sur une mesure. À utiliser "
                "pour trancher une hypothèse qui désigne un coupable précis, plutôt que de "
                "ventiler puis de lire soi-même."
            ),
            input_schema=objet(
                mesure=champ_mesure,
                dimension=champ_dimension,
                modalite_a={"type": "string"},
                modalite_b={"type": "string"},
            ),
            fn=lier(_comparer),
        ),
        SpecOutil(
            nom="croiser",
            description=(
                "Mesure ventilée selon deux dimensions à la fois. Sert à isoler un effet "
                "combiné — par exemple une dérive qui ne toucherait qu'un métier dans une "
                "seule agence. Refusé au-delà de "
                f"{MAX_CELLULES_CROISEMENT} cellules."
            ),
            input_schema=objet(
                mesure=champ_mesure,
                dimension_1=champ_dimension,
                dimension_2=champ_dimension,
            ),
            fn=lier(_croiser),
        ),
        SpecOutil(
            nom="concentration",
            description=(
                "Quelle part du total repose sur quelle minorité de modalités. Sert à "
                "constater une dépendance — à un client, un métier, un technicien — que la "
                f"ventilation ne montre pas. Comparaison disponible : {comparaison}."
            ),
            input_schema=objet(mesure=champ_mesure, dimension=champ_dimension),
            fn=lier(_concentration),
        ),
    ]


def _resumer(outil: str, arguments: dict[str, Any], resultat: dict[str, Any]) -> str:
    """Une ligne pour la trace affichée pendant que l'agent travaille.

    Le prospect regarde l'agent réfléchir et se tromper. Le classeur, il le
    regarde dix secondes ; ça, il s'en souvient.
    """
    if outil == "noter_hypothese":
        return f"hypothèse {arguments['identifiant']} : {arguments['enonce']}"
    if outil == "ventilation":
        modalites = resultat.get("modalites", [])
        if not modalites:
            return (
            f"{arguments['mesure']} par {arguments['dimension']} — "
            "aucune modalité retenue"
        )
        pire = modalites[0]
        return (
            f"{arguments['mesure']} par {arguments['dimension']} — "
            f"{len(modalites)} modalités, la plus défavorable : {pire['libelle']}"
        )
    if outil == "serie_mensuelle":
        return f"{arguments['mesure']} dans le temps — tendance {resultat['tendance']}"
    if outil == "comparer":
        favorable = resultat.get("favorable_a")
        sens = "à l'avantage de" if favorable else "au désavantage de"
        return (
            f"{arguments['modalite_a']} contre {arguments['modalite_b']} "
            f"sur {arguments['mesure']} — {sens} {arguments['modalite_a']}"
        )
    if outil == "croiser":
        return (
            f"{arguments['mesure']} par {arguments['dimension_1']} x "
            f"{arguments['dimension_2']} — {len(resultat['cellules'])} cellules exploitables"
        )
    return (
        f"concentration de {arguments['mesure']} par {arguments['dimension']} — "
        f"{resultat['modalites_pour_80_pct']} modalités portent quatre cinquièmes du total"
    )
