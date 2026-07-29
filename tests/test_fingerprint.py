"""Empreintes SHA-256. Aucune dépendance, quelques millisecondes."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from loom_report_demo import paths
from loom_report_demo.fingerprint import (
    empreinte_fichier,
    empreinte_jeu,
    formater,
    grouper,
)


def _ecrire(dossier: Path, nom: str, contenu: bytes) -> Path:
    chemin = dossier / nom
    chemin.write_bytes(contenu)
    return chemin


def test_empreinte_fichier_correspond_a_hashlib(tmp_path: Path) -> None:
    chemin = _ecrire(tmp_path, "a.csv", b"col\n1\n2\n")
    assert empreinte_fichier(chemin).sha256 == hashlib.sha256(b"col\n1\n2\n").hexdigest()


def test_empreinte_fichier_compte_taille_et_lignes(tmp_path: Path) -> None:
    empreinte = empreinte_fichier(_ecrire(tmp_path, "a.csv", b"col\n1\n2\n"))
    assert empreinte.taille_octets == 8
    assert empreinte.lignes == 3
    assert empreinte.enregistrements == 2


def test_empreinte_fichier_lit_par_blocs(tmp_path: Path) -> None:
    """Un fichier plus gros qu'un bloc doit donner le même condensat."""
    contenu = b"x" * 200_000
    empreinte = empreinte_fichier(_ecrire(tmp_path, "gros.csv", contenu))
    assert empreinte.sha256 == hashlib.sha256(contenu).hexdigest()


def test_empreinte_jeu_est_independante_de_lordre(tmp_path: Path) -> None:
    a = _ecrire(tmp_path, "a.csv", b"aaa")
    b = _ecrire(tmp_path, "b.csv", b"bbb")
    assert empreinte_jeu([a, b]).globale == empreinte_jeu([b, a]).globale


def test_empreinte_jeu_change_si_un_octet_change(tmp_path: Path) -> None:
    a = _ecrire(tmp_path, "a.csv", b"aaa")
    avant = empreinte_jeu([a]).globale
    _ecrire(tmp_path, "a.csv", b"aab")
    assert empreinte_jeu([a]).globale != avant


def test_empreinte_jeu_change_si_un_fichier_est_renomme(tmp_path: Path) -> None:
    """Le nom entre dans l'empreinte : renommer un export n'est pas neutre."""
    a = _ecrire(tmp_path, "a.csv", b"aaa")
    avant = empreinte_jeu([a]).globale
    b = _ecrire(tmp_path, "b.csv", b"aaa")
    assert empreinte_jeu([b]).globale != avant


def test_empreinte_jeu_nomme_les_fichiers_absents(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="fantome.csv"):
        empreinte_jeu([tmp_path / "fantome.csv"])


def test_par_nom_retrouve_une_empreinte(tmp_path: Path) -> None:
    a = _ecrire(tmp_path, "a.csv", b"aaa")
    assert empreinte_jeu([a]).par_nom("a.csv").taille_octets == 3


def test_par_nom_refuse_un_inconnu(tmp_path: Path) -> None:
    a = _ecrire(tmp_path, "a.csv", b"aaa")
    with pytest.raises(KeyError):
        empreinte_jeu([a]).par_nom("z.csv")


def test_grouper_decoupe_par_quatre() -> None:
    assert grouper("0123456789ab") == "0123 4567 89ab"


def test_grouper_refuse_une_taille_nulle() -> None:
    with pytest.raises(ValueError, match="positive"):
        grouper("abcd", taille=0)


def test_formater_affiche_lempreinte_globale() -> None:
    chemins = [paths.csv_source(nom) for nom in paths.FICHIERS_DONNEES]
    empreinte = empreinte_jeu(chemins)
    rendu = formater(empreinte)
    assert "Empreinte du jeu" in rendu
    assert grouper(empreinte.globale) in rendu
    for nom in paths.FICHIERS_DONNEES:
        assert nom in rendu
