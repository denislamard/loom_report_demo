"""Le profil de reconnaissance : ce que l'agent reçoit avant d'explorer.

Le profil ne contient aucune réponse. Il décrit le terrain — quelles mesures
existent à ce niveau, quelles dimensions sont praticables, combien de modalités
chacune porte, et quelques totaux d'ancrage pour donner les ordres de grandeur.

C'est délibéré. Un modèle à qui l'on sert des conclusions les reformule ; un
modèle à qui l'on sert une carte formule des hypothèses. Le criblage du jalon 3
viendra scorer les candidats, mais le choix de ce qui mérite d'être regardé reste
au modèle.

La structure produite est un dictionnaire sérialisable en JSON, sans objet
pandas : c'est ce qui sera injecté dans le prompt au jalon 6, et ce qui rend le
profil comparable d'une édition à l'autre.
"""

from __future__ import annotations

from typing import Any

from loom_report_demo import paths
from loom_report_demo.analysis import catalogue as cat
from loom_report_demo.analysis.cadrages import fenetres_du_niveau
from loom_report_demo.analysis.chargement import Donnees, donnees
from loom_report_demo.analysis.moteur import comparer
from loom_report_demo.fingerprint import empreinte_jeu
from loom_report_demo.niveaux import Niveau, definition


def _modalites(source: Donnees, dimension: cat.Dimension) -> dict[str, Any]:
    """Cardinalité et effectif minimal, sur la première base où la dimension existe.

    L'effectif minimal est l'information décisive : une dimension à trente
    modalités dont la moitié comptent trois lignes ne se ventile pas, elle
    s'agrège. Le criblage s'en servira, mais l'agent doit déjà le voir.
    """
    base = next(b for b in cat.Base if b in dimension.bases)
    table = source.table(base)
    comptes = table[dimension.colonne].value_counts()
    return {
        "cle": dimension.cle,
        "libelle": dimension.libelle,
        "ordonnee": dimension.ordonnee,
        "bases": sorted(b.value for b in dimension.bases),
        "nb_modalites": int(len(comptes)),
        "effectif_min": int(comptes.min()) if len(comptes) else 0,
        "effectif_median": int(comptes.median()) if len(comptes) else 0,
        "description": dimension.description,
    }


def _ancrage(source: Donnees, cle: str, principale: Any, comparaison: Any) -> dict[str, Any]:
    resultat = comparer(source, cle, principale.cadrage, comparaison.cadrage)
    mesure = cat.mesure(cle)
    return {
        "cle": cle,
        "libelle": mesure.libelle,
        "unite": mesure.unite.value,
        "nature": mesure.nature.value,
        "valeur": resultat.actuelle.valeur,
        "effectif": resultat.actuelle.effectif,
        "valeur_comparaison": None if resultat.passee is None else resultat.passee.valeur,
        "ecart_relatif": resultat.ecart_relatif,
        "motif_sans_ecart": resultat.motif,
    }


def profil(niveau: Niveau, source: Donnees | None = None) -> dict[str, Any]:
    """Carte du terrain pour un niveau donné, sérialisable en JSON."""
    jeu = source if source is not None else donnees()
    d = definition(niveau)
    principale, comparaison = fenetres_du_niveau(niveau, jeu.situation, jeu.debut)

    mesures = [
        {
            "cle": m.cle,
            "libelle": m.libelle,
            "base": m.base.value,
            "unite": m.unite.value,
            "sens": m.sens.value,
            "materialisable": m.materialisable,
            "description": m.description,
        }
        for m in cat.mesures_du_niveau(niveau)
    ]
    dimensions = [_modalites(jeu, x) for x in cat.dimensions_du_niveau(niveau)]

    return {
        "niveau": niveau.value,
        "question": d.question,
        "situation": jeu.situation.isoformat(),
        "periode_donnees": {"debut": jeu.debut.isoformat(), "fin": jeu.situation.isoformat()},
        "fenetre_principale": {
            "cadrage": principale.cadrage.value,
            "libelle": principale.libelle,
            "debut": principale.debut.isoformat(),
            "fin": principale.fin.isoformat(),
        },
        "fenetre_comparaison": {
            "cadrage": comparaison.cadrage.value,
            "libelle": comparaison.libelle,
            "debut": comparaison.debut.isoformat(),
            "fin": comparaison.fin.isoformat(),
        },
        "volumes": jeu.volumes(),
        "socle_impose": list(d.socle),
        "indicateurs_a_choisir": d.nb_variables,
        "mesures": mesures,
        "dimensions": dimensions,
        "croisements_valides": len(cat.croisements_valides(niveau)),
        "ancrages": [_ancrage(jeu, cle, principale, comparaison) for cle in d.socle],
    }


def _formater_valeur(valeur: float | None, unite: str) -> str:
    if valeur is None:
        return "non calculable"
    if unite == "%":
        return f"{valeur:.1%}"
    if unite == "€":
        return f"{valeur:,.0f} €".replace(",", " ")
    if unite == "j":
        return f"{valeur:.0f} j"
    if unite == "h":
        return f"{valeur:.1f} h"
    return f"{valeur:,.0f}".replace(",", " ")


def formater(carte: dict[str, Any], empreinte: str | None = None) -> str:
    """Rendu console du profil."""
    lignes: list[str] = [
        "",
        f"  Niveau           {carte['niveau']} — {carte['question']}",
        f"  Situation        {carte['situation']}",
        f"  Fenêtre          {carte['fenetre_principale']['libelle']} "
        f"({carte['fenetre_principale']['debut']} → {carte['fenetre_principale']['fin']})",
        f"  Comparaison      {carte['fenetre_comparaison']['libelle']}",
        "",
        f"  Mesures éligibles      {len(carte['mesures'])}",
        f"  Dimensions praticables {len(carte['dimensions'])}",
        f"  Croisements valides    {carte['croisements_valides']}",
        f"  Indicateurs à choisir  {carte['indicateurs_a_choisir']} "
        f"(en plus des {len(carte['socle_impose'])} du socle)",
        "",
        "  Socle imposé",
    ]
    for ancrage in carte["ancrages"]:
        valeur = _formater_valeur(ancrage["valeur"], ancrage["unite"])
        ecart = ancrage["ecart_relatif"]
        if ecart is not None:
            variation = f"{ecart:+.1%}"
        else:
            variation = "stock" if ancrage["nature"] == "stock" else "—"
        lignes.append(f"    {ancrage['libelle']:<38} {valeur:>14}   {variation:>8}")

    lignes.extend(("", "  Dimensions praticables"))
    for dimension in carte["dimensions"]:
        lignes.append(
            f"    {dimension['libelle']:<30} {dimension['nb_modalites']:>3} modalités, "
            f"effectif min {dimension['effectif_min']}"
        )

    if empreinte:
        lignes.extend(("", f"  Empreinte du jeu  {empreinte[:32]}…"))
    lignes.append("")
    return "\n".join(lignes)


def empreinte_courante() -> str:
    chemins = [paths.csv_source(nom) for nom in paths.FICHIERS_DONNEES]
    return empreinte_jeu(chemins).globale
