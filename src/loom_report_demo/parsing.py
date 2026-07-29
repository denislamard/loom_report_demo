"""Décodage et validation de la sortie de l'agent.

Ce module est la frontière. Tout ce qui vient du modèle passe par ici, et rien
n'en ressort qui n'ait été confronté au catalogue. Il ne dépend ni de `loom_ia`,
ni de pandas, ni du réseau : il se teste sur des fixtures JSON en quelques
millisecondes, sans dépenser un jeton.

Trois familles de gardes, dans cet ordre.

**La forme.** Le modèle rend du JSON précédé d'une ligne de trace, parfois
entouré d'une clôture Markdown. On extrait le premier objet équilibré, puis on
vérifie que les clés sont exactement celles attendues — ni en trop, ni en moins.
C'est le pendant du `extra: forbid` de la configuration : une clé inventée doit
échouer bruyamment, pas être ignorée.

**Le fond.** Chaque indicateur est revalidé contre le catalogue : mesure connue,
éligible au niveau demandé, dimension praticable sur la base de la mesure, et
croisement non tautologique. Le modèle propose, le catalogue dispose.

**La prose.** Aucun chiffre n'est admis dans les textes rédigés. Le modèle décrit
les écarts qualitativement et désigne les indicateurs par leur clé ; Python
substitue les valeurs depuis la source de vérité. La seule valeur numérique qu'il
a le droit d'écrire est un seuil d'alerte — parce qu'un seuil est un jugement,
pas une mesure. La garde tient en une expression régulière, et c'est précisément
ce qui la rend défendable devant un client : l'IA ne peut pas se tromper sur un
chiffre, elle n'en écrit aucun.
"""

from __future__ import annotations

import json
import re
from collections.abc import Collection
from pathlib import Path
from typing import Literal, NotRequired, TypedDict, cast

from loom_report_demo.analysis import catalogue as cat
from loom_report_demo.niveaux import NIVEAUX, Niveau
from loom_report_demo.workbook.selection import HypothesePerdue, Indicateur, Selection

#: Longueur maximale d'un texte rédigé. Doit rester cohérent avec le
#: `max_chars` du bloc `output` de settings.json.
LONGUEUR_MAX_TEXTE = 400
LONGUEUR_MAX_MESSAGE = 600

#: Champs soumis à la garde zéro-chiffre.
CHAMPS_REDIGES = ("pourquoi", "decision_attendue", "enonce", "motif")

_CHIFFRE = re.compile(r"\d")
_CLOTURE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.MULTILINE)


class ErreurSortie(ValueError):
    """Sortie d'agent inexploitable. Le message nomme le champ fautif."""


class HypotheseBrute(TypedDict):
    identifiant: str
    enonce: str
    statut: Literal["retenue", "ecartee"]
    motif: NotRequired[str]


class IndicateurBrut(TypedDict):
    mesure: str
    dimension: NotRequired[str | None]
    seuil_alerte: NotRequired[float | None]
    pourquoi: str
    decision_attendue: str
    hypothese_source: str


class SortieBrute(TypedDict):
    niveau: str
    message_direction: str
    hypotheses: list[HypotheseBrute]
    variables: list[IndicateurBrut]


_CLES_SORTIE = {"niveau", "message_direction", "hypotheses", "variables"}
_CLES_HYPOTHESE = {"identifiant", "enonce", "statut"}
_CLES_HYPOTHESE_OPT = {"motif"}
_CLES_INDICATEUR = {"mesure", "pourquoi", "decision_attendue", "hypothese_source"}
_CLES_INDICATEUR_OPT = {"dimension", "seuil_alerte"}


# ------------------------------------------------------------------- la forme
def extraire_json(brut: str) -> dict[str, object]:
    """Isole le premier objet JSON équilibré d'une sortie bavarde.

    Le modèle préfixe volontiers sa réponse d'une ligne de trace, et l'entoure
    parfois d'une clôture Markdown malgré la consigne. Chercher le premier `{`
    puis compter les accolades est plus robuste qu'une expression régulière, et
    ne se laisse pas piéger par une accolade dans une chaîne.
    """
    texte = _CLOTURE.sub("", brut).strip()
    debut = texte.find("{")
    if debut == -1:
        raise ErreurSortie("Aucun objet JSON dans la sortie de l'agent.")

    profondeur = 0
    dans_chaine = False
    echappe = False
    for position in range(debut, len(texte)):
        caractere = texte[position]
        if dans_chaine:
            if echappe:
                echappe = False
            elif caractere == "\\":
                echappe = True
            elif caractere == '"':
                dans_chaine = False
            continue
        if caractere == '"':
            dans_chaine = True
        elif caractere == "{":
            profondeur += 1
        elif caractere == "}":
            profondeur -= 1
            if profondeur == 0:
                fragment = texte[debut : position + 1]
                try:
                    charge = json.loads(fragment)
                except json.JSONDecodeError as erreur:
                    raise ErreurSortie(f"JSON invalide : {erreur}") from None
                if not isinstance(charge, dict):
                    raise ErreurSortie("La sortie doit être un objet, pas une liste.")
                return cast(dict[str, object], charge)
    raise ErreurSortie("Objet JSON non refermé dans la sortie de l'agent.")


def _objet(valeur: object, contexte: str) -> dict[str, object]:
    """Garde de forme : rend un dictionnaire dont les valeurs sont typées `object`.

    `json.loads` rend du `Any`, qui se propage silencieusement dans tout le
    module et prive les gardes en aval de la moindre vérification statique. On
    referme donc la porte ici : après cet appel, plus rien n'est `Any`.
    """
    if not isinstance(valeur, dict):
        raise ErreurSortie(f"{contexte} : objet attendu.")
    return cast(dict[str, object], valeur)


def _liste(valeur: object, contexte: str) -> list[object]:
    if not isinstance(valeur, list):
        raise ErreurSortie(f"{contexte} : liste attendue.")
    return cast(list[object], valeur)


def _verifier_cles(
    objet: dict[str, object], requises: set[str], optionnelles: set[str], contexte: str
) -> None:
    presentes = set(objet)
    manquantes = requises - presentes
    if manquantes:
        raise ErreurSortie(f"{contexte} : clés manquantes {sorted(manquantes)}")
    surnumeraires = presentes - requises - optionnelles
    if surnumeraires:
        raise ErreurSortie(
            f"{contexte} : clés inconnues {sorted(surnumeraires)}. "
            f"Attendues : {sorted(requises | optionnelles)}"
        )


def _texte(objet: dict[str, object], champ: str, contexte: str, maximum: int) -> str:
    valeur = objet.get(champ, "")
    if not isinstance(valeur, str) or not valeur.strip():
        raise ErreurSortie(f"{contexte} : le champ {champ!r} doit être un texte non vide.")
    if len(valeur) > maximum:
        raise ErreurSortie(
            f"{contexte} : le champ {champ!r} dépasse {maximum} caractères ({len(valeur)})."
        )
    return valeur.strip()


# ------------------------------------------------------------------ la prose
def garde_zero_chiffre(
    texte: str, champ: str, contexte: str, identifiants: Collection[str] = ()
) -> None:
    """Refuse tout chiffre dans un texte rédigé, hors renvoi à une hypothèse.

    Règle dure, et volontairement. Une liste blanche des valeurs présentes dans
    les données serait plus permissive, mais elle rendrait la garde impossible à
    expliquer en rendez-vous et difficile à tester. La promesse tient en une
    phrase : le modèle n'écrit aucun chiffre, donc il ne peut pas se tromper sur
    un chiffre.

    Une seule exception, découverte à la première exécution réelle : le modèle
    renvoie d'une hypothèse à l'autre — « l'écart va dans l'autre sens,
    confirmant H3 ». C'est précisément ce qui donne leur valeur aux réfutations,
    et le refuser revenait à interdire de raisonner. Les identifiants réellement
    déclarés dans CETTE sortie sont donc retirés du texte avant l'examen : « H3 »
    passe si et seulement si H3 existe, tandis que « trois points » reste refusé.
    """
    nettoye = texte
    for identifiant in sorted(identifiants, key=len, reverse=True):
        nettoye = nettoye.replace(identifiant, " ")
    trouve = _CHIFFRE.search(nettoye)
    if trouve is None:
        return
    extrait = nettoye[max(0, trouve.start() - 30) : trouve.start() + 30]
    raise ErreurSortie(
        f"{contexte} : le champ {champ!r} contient le chiffre {trouve.group()!r}. "
        f"Les textes rédigés ne portent aucune valeur — écrivez-la en toutes lettres, "
        f"ou désignez l'indicateur par sa clé. Extrait : « …{extrait.strip()}… »"
    )


def _texte_optionnel(objet: dict[str, object], champ: str, contexte: str) -> str | None:
    """Champ facultatif : absent ou nul vaut `None`, mais s'il est là c'est du texte."""
    valeur = objet.get(champ)
    if valeur is None or valeur == "":
        return None
    if not isinstance(valeur, str):
        raise ErreurSortie(f"{contexte} : le champ {champ!r} doit être un texte ou nul.")
    return valeur


def _seuil(objet: dict[str, object], mesure: cat.Mesure, contexte: str) -> float | None:
    """Le seul nombre que l'agent a le droit d'écrire, et il reste contrôlé."""
    valeur = objet.get("seuil_alerte")
    if valeur is None:
        return None
    if isinstance(valeur, bool) or not isinstance(valeur, int | float):
        raise ErreurSortie(f"{contexte} : 'seuil_alerte' doit être un nombre ou nul.")
    seuil = float(valeur)
    if mesure.unite is cat.Unite.POURCENT and not -1.0 <= seuil <= 1.0:
        raise ErreurSortie(
            f"{contexte} : seuil de {seuil} sur une mesure en pourcentage. "
            f"Un taux s'exprime en fraction — 0.25 et non 25."
        )
    if mesure.unite in (cat.Unite.JOURS, cat.Unite.HEURES, cat.Unite.EUROS) and seuil < 0:
        raise ErreurSortie(f"{contexte} : seuil négatif ({seuil}) sur une mesure {mesure.unite}.")
    return seuil


# -------------------------------------------------------------- les invariants
def _valider_hypotheses(brutes: object) -> dict[str, HypotheseBrute]:
    """Valide en deux passes.

    La première recense les identifiants : sans eux, la garde zéro-chiffre
    refuserait un renvoi entre hypothèses. La seconde examine les textes, une
    fois l'ensemble des renvois légitimes connu.
    """
    liste = _liste(brutes, "'hypotheses'")
    if not liste:
        raise ErreurSortie("'hypotheses' doit être une liste non vide.")

    connues: dict[str, HypotheseBrute] = {}
    for rang, valeur in enumerate(liste, start=1):
        contexte = f"hypothèse #{rang}"
        brute = _objet(valeur, contexte)
        _verifier_cles(brute, _CLES_HYPOTHESE, _CLES_HYPOTHESE_OPT, contexte)
        identifiant = _texte(brute, "identifiant", contexte, 16)
        if identifiant in connues:
            raise ErreurSortie(f"Deux hypothèses portent l'identifiant {identifiant!r}.")
        statut = brute.get("statut")
        if statut not in ("retenue", "ecartee"):
            raise ErreurSortie(
                f"{contexte} : statut {statut!r} inconnu. Attendu 'retenue' ou 'ecartee'."
            )
        connues[identifiant] = cast(HypotheseBrute, brute)

    renvois = set(connues)
    for rang, (identifiant, brute) in enumerate(connues.items(), start=1):
        contexte = f"hypothèse #{rang} ({identifiant})"
        objet = cast(dict[str, object], brute)
        enonce = _texte(objet, "enonce", contexte, LONGUEUR_MAX_TEXTE)
        garde_zero_chiffre(enonce, "enonce", contexte, renvois)
        if brute["statut"] == "ecartee":
            motif = _texte(objet, "motif", contexte, LONGUEUR_MAX_TEXTE)
            garde_zero_chiffre(motif, "motif", contexte, renvois)
    return connues


def _valider_boucle(hypotheses: dict[str, HypotheseBrute], indicateurs: list[Indicateur]) -> None:
    """Toute hypothèse notée finit quelque part, tout indicateur vient d'une hypothèse.

    C'est l'invariant qui empêche le modèle de rationaliser après coup. Il note
    ses pistes avant de sonder ; une piste qui disparaît sans verdict signale
    qu'il a réécrit son raisonnement une fois le résultat connu.
    """
    referencees = {i.hypothese_source for i in indicateurs if i.hypothese_source}
    retenues = {cle for cle, h in hypotheses.items() if h["statut"] == "retenue"}

    inconnues = referencees - set(hypotheses)
    if inconnues:
        raise ErreurSortie(
            f"Indicateurs adossés à des hypothèses jamais notées : {sorted(inconnues)}."
        )
    # Une contradiction prime sur une incomplétude : retenir un indicateur issu
    # d'une piste qu'on a soi-même déclarée réfutée est plus grave qu'oublier de
    # conclure sur une piste.
    ecartees_referencees = referencees & {
        cle for cle, h in hypotheses.items() if h["statut"] == "ecartee"
    }
    if ecartees_referencees:
        raise ErreurSortie(
            f"Indicateurs adossés à des hypothèses écartées : {sorted(ecartees_referencees)}."
        )
    orphelines = retenues - referencees
    if orphelines:
        raise ErreurSortie(
            f"Hypothèses retenues sans indicateur correspondant : {sorted(orphelines)}. "
            f"Une hypothèse retenue doit produire un indicateur, ou être écartée avec un motif."
        )


# ------------------------------------------------------------------- l'entrée
def analyser(charge: dict[str, object]) -> Selection:
    """Valide un objet déjà décodé et rend une sélection utilisable."""
    _verifier_cles(charge, _CLES_SORTIE, set(), "sortie")

    nom_niveau = _texte(charge, "niveau", "sortie", 32)
    try:
        niveau = Niveau(nom_niveau)
    except ValueError:
        raise ErreurSortie(
            f"Niveau inconnu : {nom_niveau!r}. Attendu {', '.join(n.value for n in Niveau)}."
        ) from None

    # Les hypothèses sont lues d'abord : leurs identifiants sont les seuls
    # renvois chiffrés admis dans les textes qui suivent.
    hypotheses = _valider_hypotheses(charge["hypotheses"])
    renvois = set(hypotheses)

    message = _texte(charge, "message_direction", "sortie", LONGUEUR_MAX_MESSAGE)
    garde_zero_chiffre(message, "message_direction", "sortie", renvois)

    brutes = _liste(charge["variables"], "'variables'")
    attendus = NIVEAUX[niveau].nb_variables
    if len(brutes) != attendus:
        raise ErreurSortie(
            f"Le niveau {niveau.value} attend {attendus} indicateurs choisis, "
            f"{len(brutes)} fournis."
        )

    indicateurs: list[Indicateur] = []
    for rang, valeur in enumerate(brutes, start=1):
        contexte = f"indicateur #{rang}"
        brute = _objet(valeur, contexte)
        _verifier_cles(brute, _CLES_INDICATEUR, _CLES_INDICATEUR_OPT, contexte)

        cle_mesure = _texte(brute, "mesure", contexte, 64)
        cle_dimension = _texte_optionnel(brute, "dimension", contexte)
        try:
            cat.valider(cle_mesure, cle_dimension, niveau)
        except (KeyError, ValueError) as erreur:
            raise ErreurSortie(f"{contexte} : {erreur}") from None

        pourquoi = _texte(brute, "pourquoi", contexte, LONGUEUR_MAX_TEXTE)
        decision = _texte(brute, "decision_attendue", contexte, LONGUEUR_MAX_TEXTE)
        garde_zero_chiffre(pourquoi, "pourquoi", contexte, renvois)
        garde_zero_chiffre(decision, "decision_attendue", contexte, renvois)

        indicateurs.append(
            Indicateur(
                mesure=cle_mesure,
                dimension=cle_dimension,
                seuil_alerte=_seuil(brute, cat.mesure(cle_mesure), contexte),
                pourquoi=pourquoi,
                decision_attendue=decision,
                hypothese_source=_texte(brute, "hypothese_source", contexte, 16),
            )
        )

    _valider_boucle(hypotheses, indicateurs)

    selection = Selection(
        niveau=niveau,
        variables=tuple(indicateurs),
        ecartees=tuple(
            HypothesePerdue(
                identifiant=h["identifiant"], enonce=h["enonce"], motif=h.get("motif", "")
            )
            for h in hypotheses.values()
            if h["statut"] == "ecartee"
        ),
        message_direction=message,
    )
    try:
        selection.valider()
    except ValueError as erreur:
        raise ErreurSortie(str(erreur)) from None
    return selection


def parse_selection(brut: str) -> Selection:
    """Point d'entrée : de la sortie brute du modèle à une sélection validée."""
    return analyser(extraire_json(brut))


def charger(chemin: Path) -> Selection:
    """Charge une sélection depuis un fichier, avec les mêmes gardes."""
    return analyser(json.loads(chemin.read_text(encoding="utf-8")))
