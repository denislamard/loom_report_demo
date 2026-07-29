"""Résolution des chemins et complétude de l'installation.

Aucune clé d'API, aucun réseau, aucun import de `loom_ia`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from loom_report_demo import paths


def test_racine_contient_le_pyproject() -> None:
    assert (paths.racine() / "pyproject.toml").is_file()


def test_racine_forcee_par_variable_denvironnement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOOM_REPORT_HOME", str(tmp_path))
    assert paths.racine() == tmp_path.resolve()


def test_les_sept_exports_sont_presents() -> None:
    absents = [nom for nom in paths.FICHIERS_DONNEES if not (paths.donnees() / nom).is_file()]
    assert absents == [], f"exports manquants : {absents}"


def test_csv_source_refuse_un_nom_inconnu() -> None:
    with pytest.raises(KeyError, match="inconnu"):
        paths.csv_source("ventes.csv")


def test_csv_source_rend_un_chemin_existant() -> None:
    assert paths.csv_source("devis.csv").is_file()


def test_le_projet_loom_est_le_dossier_files() -> None:
    """Les chemins `log/...` de settings.json sont relatifs à ce répertoire."""
    assert paths.loom_projet().name == "files"
    assert paths.settings().parent == paths.loom_projet()
    assert paths.journaux().parent == paths.loom_projet()


def test_les_chemins_techniques_suivent_settings_json() -> None:
    config = json.loads(paths.settings().read_text(encoding="utf-8"))
    base = paths.loom_projet()
    assert paths.journaux() / "agent.log" == base / config["logging"]["file"]
    assert paths.memoire() == base / config["memory"]["path"]
    assert paths.usage() == base / config["usage"]["path"]
    assert paths.metriques() == base / config["metrics"]["file"]


def test_verifier_passe_sur_une_installation_complete() -> None:
    paths.verifier()


def test_verifier_nomme_les_fichiers_manquants(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOOM_REPORT_HOME", str(tmp_path))
    with pytest.raises(FileNotFoundError) as excinfo:
        paths.verifier()
    message = str(excinfo.value)
    assert "settings.json" in message
    assert "devis.csv" in message


def test_verifier_nexige_pas_le_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Le .env n'est requis qu'au premier appel de modèle, pas au démarrage."""
    monkeypatch.setenv("LOOM_REPORT_HOME", str(tmp_path))
    with pytest.raises(FileNotFoundError) as excinfo:
        paths.verifier()
    assert ".env" not in str(excinfo.value)


def test_cles_absentes_detecte_labsence_de_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOOM_REPORT_HOME", str(tmp_path))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("M3_API_KEY", raising=False)
    assert paths.cles_absentes() is True


def test_cles_absentes_accepte_les_variables_denvironnement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOOM_REPORT_HOME", str(tmp_path))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("M3_API_KEY", "test")
    assert paths.cles_absentes() is False


def test_preparer_sorties_est_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOOM_REPORT_HOME", str(tmp_path))
    paths.preparer_sorties()
    paths.preparer_sorties()
    assert (tmp_path / "rapports").is_dir()
    assert (tmp_path / "files" / "log" / "memory").is_dir()
    assert (tmp_path / "files" / "log" / "selection").is_dir()


def test_settings_declare_les_trois_modeles() -> None:
    config = json.loads(paths.settings().read_text(encoding="utf-8"))
    identifiants = {bloc["id"] for bloc in config["llm"]}
    assert {"M3_MAIN", "HAIKU", "SONNET"} <= identifiants


def test_chaque_modele_declare_le_nom_de_sa_variable_denvironnement() -> None:
    config = json.loads(paths.settings().read_text(encoding="utf-8"))
    for bloc in config["llm"]:
        assert bloc["api_keyname"], f"api_keyname manquant pour {bloc['id']}"


def test_aucune_cle_dapi_en_clair_dans_settings() -> None:
    """Garde-fou : une clé collée dans settings.json partirait au prochain commit."""
    assert "sk-ant-" not in paths.settings().read_text(encoding="utf-8")


def test_le_env_est_bien_ignore_par_git() -> None:
    """Régression : le .env avait fuité dans une archive faute de .gitignore."""
    regles = (paths.racine() / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "files/.env" in regles


def test_les_modeles_du_catalogue_de_niveaux_existent_dans_settings() -> None:
    """`DefinitionNiveau.modele` doit désigner un bloc `llm` réel."""
    from loom_report_demo.niveaux import NIVEAUX

    config = json.loads(paths.settings().read_text(encoding="utf-8"))
    identifiants = {bloc["id"] for bloc in config["llm"]}
    for definition in NIVEAUX.values():
        assert definition.modele in identifiants, (
            f"le niveau {definition.niveau} référence un modèle absent : {definition.modele}"
        )
