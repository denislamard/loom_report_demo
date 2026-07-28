"""Empreinte SHA-256 du jeu de données.

Le rapport porte une empreinte pour établir qu'il se rapporte à ces fichiers
exacts, non modifiés depuis. C'est le pendant, pour des données comptables, de
l'empreinte de photographie d'un état des lieux — et l'argument y est plus fort :
un tableau de bord se discute, et savoir de quelle version des données il sort
évite la discussion.

Ce qu'elle établit et ce qu'elle n'établit pas : elle prouve que les données
n'ont pas bougé, pas qu'elles existaient à une date donnée. Une antériorité
demanderait un horodatage RFC 3161 par un tiers de confiance.

Aucune dépendance : `hashlib` et `pathlib`. Testable sans rien installer.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

#: Lecture par blocs : un CSV de plusieurs mégaoctets n'a pas à tenir en mémoire.
_TAILLE_BLOC = 65536


@dataclass(frozen=True, slots=True)
class EmpreinteFichier:
    nom: str
    sha256: str
    taille_octets: int
    lignes: int

    @property
    def enregistrements(self) -> int:
        """Lignes hors en-tête."""
        return max(0, self.lignes - 1)


@dataclass(frozen=True, slots=True)
class EmpreinteJeu:
    """Empreintes individuelles et empreinte d'ensemble.

    L'empreinte globale est calculée sur la liste triée des couples
    `nom:sha256`, jamais sur la concaténation des contenus : elle est donc
    indépendante de l'ordre de parcours du répertoire, et reste stable d'une
    machine à l'autre.
    """

    fichiers: tuple[EmpreinteFichier, ...]
    globale: str

    @property
    def taille_totale(self) -> int:
        return sum(f.taille_octets for f in self.fichiers)

    @property
    def enregistrements(self) -> int:
        return sum(f.enregistrements for f in self.fichiers)

    def par_nom(self, nom: str) -> EmpreinteFichier:
        for fichier in self.fichiers:
            if fichier.nom == nom:
                return fichier
        raise KeyError(f"Aucune empreinte pour {nom!r}")


def empreinte_fichier(chemin: Path) -> EmpreinteFichier:
    """SHA-256, taille et nombre de lignes d'un fichier."""
    condensat = hashlib.sha256()
    taille = 0
    lignes = 0
    with chemin.open("rb") as flux:
        while bloc := flux.read(_TAILLE_BLOC):
            condensat.update(bloc)
            taille += len(bloc)
            lignes += bloc.count(b"\n")
    return EmpreinteFichier(
        nom=chemin.name,
        sha256=condensat.hexdigest(),
        taille_octets=taille,
        lignes=lignes,
    )


def empreinte_jeu(fichiers: list[Path]) -> EmpreinteJeu:
    """Empreinte d'un ensemble de fichiers, invariante par ordre de parcours."""
    manquants = [c for c in fichiers if not c.is_file()]
    if manquants:
        liste = ", ".join(c.name for c in manquants)
        raise FileNotFoundError(f"Fichiers absents, empreinte impossible : {liste}")

    individuelles = tuple(sorted((empreinte_fichier(c) for c in fichiers), key=lambda e: e.nom))
    condensat = hashlib.sha256()
    for fichier in individuelles:
        condensat.update(f"{fichier.nom}:{fichier.sha256}\n".encode())
    return EmpreinteJeu(fichiers=individuelles, globale=condensat.hexdigest())


def grouper(condensat: str, taille: int = 4) -> str:
    """Découpe une empreinte en groupes lisibles, pour la relire à l'œil."""
    if taille <= 0:
        raise ValueError("La taille de groupe doit être strictement positive")
    return " ".join(condensat[i : i + taille] for i in range(0, len(condensat), taille))


def formater(empreinte: EmpreinteJeu, largeur_nom: int = 28) -> str:
    """Rendu texte, pour la console et pour la feuille de paramètres du classeur."""
    lignes = [
        f"  {f.nom:<{largeur_nom}} {f.enregistrements:>6} lignes  "
        f"{f.taille_octets / 1024:>7.1f} Kio  {f.sha256[:16]}…"
        for f in empreinte.fichiers
    ]
    lignes.append("")
    lignes.append(f"  Empreinte du jeu   {grouper(empreinte.globale)}")
    lignes.append(
        f"  Total              {empreinte.enregistrements} enregistrements, "
        f"{empreinte.taille_totale / 1024:.1f} Kio"
    )
    return "\n".join(lignes)
