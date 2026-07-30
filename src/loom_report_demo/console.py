"""Couche d'interaction : ce que l'utilisateur voit, et ce qu'il décide.

Séparée du point d'entrée pour une raison simple : `app.py` doit rester lisible
d'un coup d'œil, alors que le déroulé d'une exécution — annoncer le niveau,
afficher la trace de l'agent, soumettre la sélection à l'arbitrage, générer —
tient en plusieurs écrans.

La saisie et l'écriture restent injectées : c'est ce qui rend tout ce module
testable sans terminal, donc en intégration continue.
"""

from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path
from typing import TYPE_CHECKING

from loom_report_demo import paths
from loom_report_demo.analysis import catalogue as cat
from loom_report_demo.app import Ecriture, Explorateur, Saisie
from loom_report_demo.niveaux import (
    NIVEAUX,
    ORDRE_MENU,
    DefinitionNiveau,
    Livrable,
    Niveau,
    par_rang,
)
from loom_report_demo.workbook.selection import Selection

if TYPE_CHECKING:
    from loom_report_demo.etat import Enregistrement
    from loom_report_demo.reporting import Exploration

#: Largeur des règles et des bandeaux, en caractères.
_LARGEUR = 74
#: Largeur réservée au montant, à droite de chaque indicateur.
_COLONNE_EUROS = 14
_TITRE = "Bâti-Sud — rapport de pilotage"
_SOUS_TITRE = "Démonstration loom-ia · jeu de données fictif, 4 exercices"

_QUITTER = frozenset({"q", "quitter", "quit", "exit", ""})


def _regle(caractere: str = "─") -> str:
    return caractere * _LARGEUR


def banniere() -> str:
    return "\n".join((_regle("━"), f"  {_TITRE}", f"  {_SOUS_TITRE}", _regle("━")))


def menu() -> str:
    """Le menu, formulé dans la langue du client.

    « Stratégique, gestion, opérationnel » est du vocabulaire de contrôleur de
    gestion : un artisan ne sait pas y répondre, alors que la question se répond
    seule. En rendez-vous, le menu lui-même est déjà un argument.
    """
    lignes = ["", "  Quel rapport voulez-vous ?", ""]
    for rang, niveau in enumerate(ORDRE_MENU, start=1):
        d = NIVEAUX[niveau]
        lignes.append(f"   {rang}   {d.question:<40}{d.cadrage}")
    lignes.extend(("", "   q   quitter", ""))
    return "\n".join(lignes)


def _orchestrateur() -> str:
    """Modèle réellement aux commandes, lu dans la configuration.

    L'écran annonçait le modèle déclaré par le niveau, alors que l'orchestrateur
    en utilisait un autre : c'est le genre d'écart qui fait perdre une heure à
    quiconque relit un journal d'exécution.
    """
    try:
        config = json.loads(paths.settings().read_text(encoding="utf-8"))
        principal = next(r for r in config["roles"] if r["name"] == "main")
        return str(principal["llm"])
    except OSError, KeyError, StopIteration, json.JSONDecodeError:
        return "non déterminé"


def resume(d: DefinitionNiveau) -> str:
    """Ce que le niveau implique, en cinq lignes plutôt qu'en dix.

    L'écran précédent alignait dix couples clé-valeur. Personne ne les lit : ce
    qui compte est ce qu'on va obtenir et combien l'agent en décide.
    """
    nature = "tableau de bord" if d.livrable is Livrable.TABLEAU_DE_BORD else "files de travail"
    lignes = [
        "",
        _regle(),
        f"  {d.question}",
        f"  {d.cadrage}",
        f"  Livrable   {nature} · sélection {d.duree_vie}",
    ]
    # Le socle opérationnel dépasse la largeur d'une ligne : on le replie plutôt
    # que de le tronquer, car chaque clé y est utile.
    socle = textwrap.wrap(", ".join(d.socle), _LARGEUR - 13)
    for rang, morceau in enumerate(socle):
        etiquette = "  Socle      " if rang == 0 else " " * 13
        lignes.append(f"{etiquette}{morceau}")
    lignes.append(
        f"  L'agent choisit {d.nb_variables} indicateurs de plus · modèle {_orchestrateur()}"
    )
    lignes.append(_regle())
    return "\n".join(lignes)


def lire_choix(saisir: Saisie) -> DefinitionNiveau | None:
    """Boucle de saisie du menu. Rend `None` si l'utilisateur quitte.

    Une saisie invalide n'interrompt pas : elle réaffiche la consigne. Une
    interruption clavier ou une fin de flux valent « quitter ».
    """
    while True:
        try:
            brut = saisir("  Votre choix [1-3, q] : ").strip().lower()
        except EOFError, KeyboardInterrupt:
            return None
        if brut in _QUITTER:
            return None
        if brut.isdigit() and 1 <= int(brut) <= len(ORDRE_MENU):
            return par_rang(int(brut))
        print(f"  Choix non reconnu : {brut!r}. Attendu 1, 2, 3 ou q.")


def _compter_outils(exploration: Exploration) -> str:
    """« ventilation ×7 · croiser ×3 » plutôt que quatorze lignes de détail."""
    comptes: dict[str, int] = {}
    for appel in exploration.registre.appels:
        if appel.outil != "noter_hypothese":
            comptes[appel.outil] = comptes.get(appel.outil, 0) + 1
    ordonnes = sorted(comptes.items(), key=lambda x: -x[1])
    return " · ".join(f"{nom} ×{n}" for nom, n in ordonnes)


def trace(exploration: Exploration, ecrire: Ecriture) -> None:
    """Ce que l'agent a fait, en deux lignes.

    La version précédente déroulait chaque appel, hypothèses et sondages mêlés
    dans l'ordre d'arrivée. On y lisait mal, et surtout on n'y lisait rien : le
    verdict de chaque hypothèse figure plus bas, et le détail complet part dans
    la feuille « Ce qui a été regardé ». Ici, seule compte l'ampleur du travail.
    """
    registre = exploration.registre
    duree = sum(a.duree_ms for a in registre.appels) / 1000
    ecrire("")
    ecrire(
        f"  Exploration   {len(registre.hypotheses)} hypothèses · "
        f"{registre.sondages} sondages · {duree:.1f} s"
    )
    ecrire(f"                {_compter_outils(exploration)}")


def _materialite(exploration: Exploration | None, mesure: str, dimension: str | None) -> str:
    """Ce que vaut l'écart, en euros. C'est le chiffre qui emporte la décision."""
    if exploration is None:
        return ""
    cle = f"{mesure}|{dimension}"
    for candidat in exploration.criblage.evalues:
        if candidat.cle == cle and candidat.scores.materialite_euros:
            montant = f"{candidat.scores.materialite_euros:,.0f}".replace(",", " ")
            return f"{montant} €/an"
    return ""


def _abreger(texte: str, largeur: int) -> str:
    if len(texte) <= largeur:
        return texte
    return texte[: largeur - 1].rstrip() + "…"


def tableau_selection(
    selection: Selection, ecrire: Ecriture, exploration: Exploration | None = None
) -> None:
    """La sélection soumise à l'arbitrage.

    Les retenues occupent la place, les écartées tiennent sur une ligne chacune :
    l'une se décide, l'autre se survole. Le motif complet reste dans le classeur.
    """
    ecrire("")
    ecrire(_regle("━"))
    for ligne_ in textwrap.wrap(selection.message_direction, _LARGEUR - 4):
        ecrire(f"  {ligne_}")
    ecrire(_regle("━"))
    ecrire("")

    for rang, indicateur in enumerate(selection.variables, start=1):
        mesure = cat.mesure(indicateur.mesure)
        coupe = (
            f"par {cat.dimension(indicateur.dimension).libelle.lower()}"
            if indicateur.dimension
            else "ensemble"
        )
        euros = _materialite(exploration, indicateur.mesure, indicateur.dimension)
        # La colonne des euros est ancrée à droite : le libellé est raccourci
        # pour qu'elle ne se décale jamais, quelle que soit la mesure.
        entete = _abreger(f"{mesure.libelle} · {coupe}", _LARGEUR - _COLONNE_EUROS - 6)
        ecrire(f"  {rang}  {entete:<{_LARGEUR - _COLONNE_EUROS - 6}}{euros:>{_COLONNE_EUROS}}")
        ecrire(f"     → {_abreger(indicateur.decision_attendue, _LARGEUR - 8)}")
        ecrire("")

    if selection.ecartees:
        ecrire(f"  Écartées ({len(selection.ecartees)})")
        for hypothese in selection.ecartees:
            ecrire(f"   {hypothese.identifiant:<4}{_abreger(hypothese.motif, _LARGEUR - 8)}")
        ecrire("")


def arbitrer(
    selection: Selection,
    saisir: Saisie,
    ecrire: Ecriture,
    exploration: Exploration | None = None,
) -> Selection | None:
    """Laisse l'humain retirer un indicateur avant génération.

    Trois raisons d'être. C'est la seule barrière avant qu'une bêtise n'atteigne
    le livrable. C'est ce qui transforme la démonstration en un outil dont on
    garde la main. Et c'est le moment où le client comprend qu'il décide encore.

    Deux pièges corrigés après une exécution réelle. L'action par défaut était
    la touche Entrée, invisible juste après un menu numéroté : l'utilisateur
    tape naturellement un chiffre, et déclenchait un retrait au lieu de générer.
    Et retirer le dernier indicateur annulait tout en silence, alors que rien
    n'annonçait que le geste était destructeur. Générer a désormais sa propre
    touche, et la sélection ne peut plus se vider par inadvertance.
    """
    while True:
        borne = len(selection.variables)
        ecrire("")
        options = "[g] générer" + (f" · [1-{borne}] retirer" if borne > 1 else "")
        ecrire(f"  {options} · [q] annuler")
        try:
            reponse = saisir(f"  Votre choix [g, 1-{borne}, q] : ").strip().lower()
        except EOFError, KeyboardInterrupt:
            return None

        if reponse in ("q", "quitter", "annuler"):
            return None
        if reponse in ("g", "generer", "générer", ""):
            return selection
        if reponse.isdigit() and 1 <= int(reponse) <= borne:
            if borne == 1:
                ecrire("  Il doit rester au moins un indicateur. Choisissez [q] pour tout annuler.")
                continue
            retire = selection.variables[int(reponse) - 1]
            selection = selection.sans(int(reponse) - 1)
            ecrire(f"\n  Retiré : {retire.mesure} par {retire.dimension or '—'}")
            tableau_selection(selection, ecrire, exploration)
            continue
        ecrire(f"  Choix non reconnu : {reponse!r}.")


async def executer(
    saisir: Saisie | None = None,
    sortie: Ecriture | None = None,
    explorateur: Explorateur | None = None,
    rejouer: bool = False,
    forcer: bool = False,
) -> int:
    """Déroule le flux et rend le code de sortie du processus.

    Asynchrone dès maintenant : au jalon 6, la sélection des indicateurs sera
    obtenue par `await reporting.explorer(niveau)`.

    Les valeurs par défaut sont résolues À L'APPEL, pas à la définition : sinon
    `input` serait figé à l'import et un `monkeypatch.setattr("builtins.input")`
    resterait sans effet — le test se mettrait à attendre une vraie saisie.
    """
    lire = saisir if saisir is not None else input
    ecrire = sortie if sortie is not None else print
    try:
        paths.verifier()
    except FileNotFoundError as erreur:
        ecrire(f"\n{erreur}\n", file=sys.stderr)
        return 1
    paths.preparer_sorties()

    ecrire(banniere())
    if paths.cles_absentes():
        ecrire(
            "\n  Aucune clé d'API détectée : copiez files/.env.example vers files/.env.\n"
            "  Le menu reste utilisable ; l'exploration par l'agent, non."
        )
    ecrire(menu())

    choix = lire_choix(lire)
    if choix is None:
        ecrire("\n  Interrompu.\n")
        return 0

    ecrire(resume(choix))

    if rejouer:
        from loom_report_demo import etat

        try:
            retenue = etat.rejouer(choix.niveau)
        except (FileNotFoundError, ValueError) as erreur:
            ecrire(f"\n  {erreur}\n", file=sys.stderr)
            return 1
        ecrire("\n  Sélection rejouée depuis la dernière exécution.\n")
        tableau_selection(retenue, ecrire)
        chemin = _construire(retenue)
        ecrire(f"\n  Classeur     {chemin}\n")
        return 0

    gel = None if forcer else _selection_gelee(choix.niveau)
    if gel is not None:
        ecrire(
            f"\n  Une sélection est déjà gelée pour ce millésime "
            f"({gel.millesime}, enregistrée le {gel.enregistre_le[:10]}).\n"
            f"  Un référentiel qui change en cours d'année cesse d'être comparable.\n"
            f"  Relancez avec --rejouer pour la reprendre, ou --forcer pour la refaire.\n"
        )
        return 1

    if explorateur is None:
        if paths.cles_absentes():
            ecrire(
                "\n  Aucune clé d'API : l'exploration est impossible.\n"
                "  Copiez files/.env.example vers files/.env, ou produisez un rapport\n"
                "  à partir d'une sélection existante :\n"
                "      uv run rapport --selection tests/fixtures/gestion.json\n"
            )
            return 1
        explorateur = _explorateur_reel()

    ecrire("\n  L'agent explore. Une minute environ, quelques centimes.\n")
    try:
        exploration = await explorateur(choix.niveau)
    except Exception as erreur:  # noqa: BLE001 - la cause exacte importe peu ici
        ecrire(f"\n  L'exploration a échoué : {erreur}\n", file=sys.stderr)
        return 1

    trace(exploration, ecrire)
    tableau_selection(exploration.selection, ecrire, exploration)

    retenue = arbitrer(exploration.selection, lire, ecrire, exploration)
    if retenue is None:
        ecrire("\n  Génération annulée.\n")
        return 0

    _enregistrer(choix.niveau, exploration)

    chemin = _construire(retenue)
    ecrire(f"\n  Classeur     {chemin}\n")
    return 0


def _selection_gelee(niveau: Niveau) -> Enregistrement | None:
    """Sélection encore valable pour le millésime courant, s'il y en a une."""
    from loom_report_demo import etat
    from loom_report_demo.analysis.chargement import donnees

    # Seul le stratégique est gelé. Régénérer un rapport de gestion dans le mois
    # est légitime — on corrige une donnée, on relance. Bloquer là serait une
    # rigidité gratuite, et cela empêcherait de rejouer une démonstration.
    if "gelée" not in NIVEAUX[niveau].duree_vie:
        return None
    return etat.gelee(niveau, donnees().situation)


def _enregistrer(niveau: Niveau, exploration: Exploration) -> None:
    from loom_report_demo import etat
    from loom_report_demo.analysis.chargement import donnees

    etat.enregistrer(niveau, exploration.brut, donnees().situation)


def _explorateur_reel() -> Explorateur:
    """Import différé : `reporting` tire `loom_ia`, que le reste n'utilise pas."""
    from loom_report_demo.reporting import explorer

    async def _explorer(niveau: Niveau) -> Exploration:
        return await explorer(niveau)

    return _explorer


def _construire(selection: Selection) -> Path:
    from loom_report_demo.workbook import construire

    destination = paths.rapports() / f"Bati-Sud_{selection.niveau.value}.xlsx"
    return construire(selection, destination, strict=False)
