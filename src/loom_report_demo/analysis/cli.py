"""Points d'entrée `uv run profil` et `uv run candidats`.

Le premier montre la carte du terrain remise à l'agent, le second ce que le
criblage trouve seul. Ensemble, ils posent la référence contre laquelle l'apport
de l'agent se mesurera au jalon 6 : s'il ne fait pas mieux que `candidats`, il ne
sert à rien.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict

from loom_report_demo import paths
from loom_report_demo.analysis.chargement import donnees
from loom_report_demo.analysis.criblage import Criblage, cribler
from loom_report_demo.analysis.profil import empreinte_courante, formater, profil
from loom_report_demo.niveaux import Niveau


def _analyser(argv: list[str] | None = None) -> argparse.Namespace:
    parseur = argparse.ArgumentParser(
        prog="profil",
        description="Affiche le profil de reconnaissance remis à l'agent.",
    )
    parseur.add_argument(
        "--niveau",
        choices=[n.value for n in Niveau],
        default=Niveau.GESTION.value,
        help="Registre du tableau de bord (défaut : gestion).",
    )
    parseur.add_argument(
        "--json",
        action="store_true",
        help="Sortie brute, telle qu'elle sera injectée dans le prompt.",
    )
    return parseur.parse_args(argv)


def executer(argv: list[str] | None = None) -> int:
    arguments = _analyser(argv)
    try:
        paths.verifier()
    except FileNotFoundError as erreur:
        print(f"\n{erreur}\n", file=sys.stderr)
        return 1

    carte = profil(Niveau(arguments.niveau))
    if arguments.json:
        print(json.dumps(carte, ensure_ascii=False, indent=2))
    else:
        print(formater(carte, empreinte_courante()))
    return 0


def run() -> None:
    code = executer()
    if code:
        raise SystemExit(code)


def _formater_candidats(criblage: Criblage, montrer_rejets: bool) -> str:
    lignes = [
        "",
        f"  Niveau      {criblage.niveau.value}",
        f"  Fenêtre     {criblage.fenetre.libelle} "
        f"({criblage.fenetre.debut} → {criblage.fenetre.fin})",
        f"  Explorés    {criblage.explores} couples · "
        f"{len(criblage.evalues)} recevables · {len(criblage.rejetes)} écartés",
        "",
        "  Ce que le code trouve seul, sans une ligne d'IA :",
        "",
    ]
    for rang, candidat in enumerate(criblage.retenus, start=1):
        euros = candidat.scores.materialite_euros
        montant = f"{euros:>11,.0f} €".replace(",", " ") if euros else "            —"
        lignes.append(f"  {rang:2d}. {candidat.libelle}")
        lignes.append(
            f"      {montant}   dispersion {candidat.scores.dispersion:>5.1%}   "
            f"stabilité {candidat.scores.stabilite:.2f}   "
            f"monotonie {candidat.scores.monotonie:.2f}   "
            f"score {candidat.score_global:.3f}"
        )
        if candidat.modalite_defavorable is not None:
            lignes.append(
                f"      la plus défavorable : {candidat.modalite_defavorable} "
                f"({_valeur(candidat.valeur_defavorable, candidat.unite)} "
                f"contre {_valeur(candidat.cible, candidat.unite)} pour les autres, "
                f"sur {candidat.effectif_defavorable} observations)"
            )
        lignes.append("")

    if montrer_rejets and criblage.rejetes:
        lignes.append("  Écartés avant scoring :")
        for candidat in criblage.rejetes:
            lignes.append(f"    {candidat.libelle:<52} {candidat.motif_rejet}")
        lignes.append("")
    return "\n".join(lignes)


def _valeur(valeur: float | None, unite: str) -> str:
    if valeur is None:
        return "—"
    if unite == "%":
        return f"{valeur:.1%}"
    if unite == "€":
        return f"{valeur:,.0f} €".replace(",", " ")
    if unite == "j":
        return f"{valeur:.0f} j"
    return f"{valeur:,.1f}".replace(",", " ")


def executer_candidats(argv: list[str] | None = None) -> int:
    parseur = argparse.ArgumentParser(
        prog="candidats",
        description="Criblage : les couples (mesure, dimension) les mieux scorés.",
    )
    parseur.add_argument(
        "--niveau", choices=[n.value for n in Niveau], default=Niveau.GESTION.value
    )
    parseur.add_argument("--limite", type=int, default=12)
    parseur.add_argument("--rejetes", action="store_true", help="Montrer les couples écartés.")
    parseur.add_argument("--json", action="store_true")
    arguments = parseur.parse_args(argv)

    try:
        paths.verifier()
    except FileNotFoundError as erreur:
        print(f"\n{erreur}\n", file=sys.stderr)
        return 1

    resultat = cribler(donnees(), Niveau(arguments.niveau), limite=arguments.limite)
    if arguments.json:
        print(json.dumps([asdict(c) for c in resultat.retenus], ensure_ascii=False, indent=2))
    else:
        print(_formater_candidats(resultat, arguments.rejetes))
    return 0


def run_candidats() -> None:
    code = executer_candidats()
    if code:
        raise SystemExit(code)
