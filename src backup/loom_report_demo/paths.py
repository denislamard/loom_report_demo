"""Résolution des chemins du projet, indépendante du répertoire courant.

Ce module n'a aucune dépendance : ni `loom_ia`, ni `pandas`, ni le réseau. Il est
donc importable partout et testable sans rien installer, ce qui est la raison
pour laquelle `__init__.py` diffère l'import de `app`.

Les chemins internes déclarés dans `files/settings.json` (`log/agent.log`,
`log/memory`, `log/usage`, `log/metrics.jsonl`) sont relatifs au répertoire
projet remis à `loom_ia.Agent`, c'est-à-dire `files/`. C'est ce que reflète
`loom_projet()`.
"""

from __future__ import annotations

import os
from pathlib import Path

#: Les sept exports du système de gestion, dans l'ordre de dépendance.
FICHIERS_DONNEES: tuple[str, ...] = (
    "clients.csv",
    "techniciens.csv",
    "catalogue_prestations.csv",
    "devis.csv",
    "relances.csv",
    "interventions.csv",
    "factures.csv",
)

_VARIABLE_RACINE = "LOOM_REPORT_HOME"


def _remonter_jusqu_au_projet(depart: Path) -> Path | None:
    for parent in (depart, *depart.parents):
        if (parent / "pyproject.toml").is_file():
            return parent
    return None


def racine() -> Path:
    """Racine du dépôt.

    `LOOM_REPORT_HOME` prime, puis la remontée depuis ce fichier, puis un repli
    positionnel. Le repli n'est correct que sur un layout `src/`, mais il ne sert
    que si le `pyproject.toml` a disparu — auquel cas `verifier()` signalera de
    toute façon ce qui manque.
    """
    force = os.environ.get(_VARIABLE_RACINE)
    if force:
        return Path(force).expanduser().resolve()
    trouve = _remonter_jusqu_au_projet(Path(__file__).resolve().parent)
    if trouve is not None:
        return trouve
    return Path(__file__).resolve().parents[2]


def donnees() -> Path:
    """Les CSV sources, versionnés dans le dépôt."""
    return racine() / "assets" / "data"


def loom_projet() -> Path:
    """Répertoire à remettre à `Agent(...)` : il contient settings.json et .env."""
    return racine() / "files"


def settings() -> Path:
    return loom_projet() / "settings.json"


def env() -> Path:
    return loom_projet() / ".env"


def journaux() -> Path:
    """Racine des sorties techniques, telle que déclarée dans settings.json."""
    return loom_projet() / "log"


def memoire() -> Path:
    return journaux() / "memory"


def usage() -> Path:
    return journaux() / "usage"


def metriques() -> Path:
    """Une ligne JSON par appel : tokens, coût, latence."""
    return journaux() / "metrics.jsonl"


def rapports() -> Path:
    """Destination des classeurs produits."""
    return racine() / "rapports"


def etat(nom_fichier: str) -> Path:
    """Sélection d'indicateurs persistée d'une édition à l'autre.

    Le nom vient de `DefinitionNiveau.fichier_etat` : un fichier par niveau, dont
    le volume et la volatilité suivent l'horizon — minuscule et stable pour le
    stratégique, volumineux et recalculé pour l'opérationnel.
    """
    return journaux() / "selection" / nom_fichier


def csv_source(nom: str) -> Path:
    """Chemin d'un export, validé contre la liste attendue."""
    if nom not in FICHIERS_DONNEES:
        raise KeyError(
            f"Fichier de données inconnu : {nom!r}. Attendus : {', '.join(FICHIERS_DONNEES)}"
        )
    return donnees() / nom


def manquants() -> list[Path]:
    """Fichiers indispensables absents, dans l'ordre où on les cite."""
    attendus = [settings(), *(donnees() / nom for nom in FICHIERS_DONNEES)]
    return [chemin for chemin in attendus if not chemin.is_file()]


def verifier() -> None:
    """Lève si l'installation est incomplète, en nommant précisément ce qui manque.

    Échouer au démarrage vaut mieux qu'un `KeyError` trois écrans plus loin. Le
    `.env` n'en fait pas partie : il n'est requis qu'au premier appel de modèle,
    et `loom_ia` lève déjà un message explicite nommant la variable attendue.
    """
    absents = manquants()
    if absents:
        base = racine()
        liste = "\n".join(f"  - {c.relative_to(base)}" for c in absents)
        raise FileNotFoundError(f"Installation incomplète sous {base} :\n{liste}")


def cles_absentes() -> bool:
    """Vrai si aucune clé d'API n'est disponible — avertissement, jamais blocage."""
    if env().is_file():
        return False
    return not (os.environ.get("ANTHROPIC_API_KEY") and os.environ.get("M3_API_KEY"))


def preparer_sorties() -> None:
    """Crée les répertoires d'écriture. Idempotent."""
    for chemin in (rapports(), journaux(), memoire(), usage(), etat("x").parent):
        chemin.mkdir(parents=True, exist_ok=True)
