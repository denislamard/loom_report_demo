"""Flux console : question du niveau, puis production du rapport.

`entry()` est le point d'entrée attendu par `loom_report_demo.main()`. Il est
asynchrone parce qu'au jalon 6 il attendra l'exploration menée par l'agent ; la
signature est posée maintenant pour ne plus bouger.

La saisie et l'écriture sont injectées plutôt qu'appelées en dur : c'est ce qui
rend le menu testable sans terminal, donc en intégration continue.

Au jalon 0, ce module ne tire pas encore `loom_ia` — mais il le fera dès qu'il
importera `reporting`. C'est la raison de l'import différé dans `__init__.py`.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from typing import Any

from loom_report_demo import paths
from loom_report_demo.niveaux import (
    NIVEAUX,
    ORDRE_MENU,
    DefinitionNiveau,
    Livrable,
    par_rang,
)

Saisie = Callable[[str], str]
Ecriture = Callable[..., Any]

_LARGEUR = 74
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


def resume(d: DefinitionNiveau) -> str:
    """Ce que le niveau choisi implique, affiché avant toute dépense de jetons."""
    nature = "tableau de bord" if d.livrable is Livrable.TABLEAU_DE_BORD else "file de travail"
    return "\n".join(
        (
            "",
            _regle(),
            f"  Niveau retenu      {d.niveau.value}",
            f"  Question           {d.question}",
            f"  Cadrage            {d.cadrage}",
            f"  Livrable           {nature}",
            f"  Indicateurs        {len(d.socle)} de socle + {d.nb_variables} choisis "
            f"par l'agent = {d.nb_indicateurs}",
            f"  Socle imposé       {', '.join(d.socle)}",
            f"  Modèle d'analyse   {d.modele}",
            f"  Durée de vie       {d.duree_vie}",
            _regle(),
        )
    )


def lire_choix(saisir: Saisie) -> DefinitionNiveau | None:
    """Boucle de saisie. Rend `None` si l'utilisateur quitte.

    Une saisie invalide n'interrompt pas : elle réaffiche la consigne. Une
    interruption clavier ou une fin de flux valent « quitter ».
    """
    while True:
        try:
            brut = saisir("  Votre choix [1-3, q] : ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return None
        if brut in _QUITTER:
            return None
        if brut.isdigit() and 1 <= int(brut) <= len(ORDRE_MENU):
            return par_rang(int(brut))
        print(f"  Choix non reconnu : {brut!r}. Attendu 1, 2, 3 ou q.")


async def executer(saisir: Saisie | None = None, sortie: Ecriture | None = None) -> int:
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
    ecrire(
        "\n  [jalon 0] L'exploration par l'agent et la génération du classeur\n"
        "            arrivent au jalon 6. L'installation est valide.\n"
    )
    return 0


async def entry() -> None:
    """Point d'entrée appelé par `loom_report_demo.main()`."""
    code = await executer()
    if code:
        raise SystemExit(code)
