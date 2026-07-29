"""Production du jeu de données Bâti-Sud.

Le générateur est **déterministe** : à graine égale, il produit des fichiers
identiques à l'octet près. C'est ce qui permet de livrer les CSV dans le dépôt
plutôt que de les recalculer à chaque exécution, et donc de calibrer les prompts
sur une narration stable.

Cette propriété est fragile : elle tient à l'ordre exact des appels au générateur
aléatoire. Déplacer une ligne, remplacer un `and` court-circuité par un `if`
imbriqué, ou évaluer un argument plus tôt suffit à décaler toute la suite. Les
tests de reproductibilité comparent les empreintes SHA-256 aux valeurs de
référence : ils échouent au premier écart.
"""

from __future__ import annotations

import csv
import random
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any, TypeVar

from loom_report_demo.dataset import parametres as P
from loom_report_demo.dataset.lignes import (
    FICHIERS,
    CanalRelance,
    Categorie,
    IssueRelance,
    LigneClient,
    LigneDevis,
    LigneFacture,
    LigneIntervention,
    LignePrestation,
    LigneRelance,
    LigneTechnicien,
    StatutDevis,
    StatutFacture,
)

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class JeuDeDonnees:
    """Les sept tables, en mémoire, avant écriture."""

    clients: tuple[LigneClient, ...]
    techniciens: tuple[LigneTechnicien, ...]
    catalogue: tuple[LignePrestation, ...]
    devis: tuple[LigneDevis, ...]
    relances: tuple[LigneRelance, ...]
    interventions: tuple[LigneIntervention, ...]
    factures: tuple[LigneFacture, ...]

    def table(self, nom: str) -> tuple[Any, ...]:
        return getattr(self, nom)

    def volumes(self) -> dict[str, int]:
        return {nom: len(self.table(nom)) for nom, _ in FICHIERS}


# --------------------------------------------------------------------- dates
def mois_key(d: date) -> str:
    return f"{d.year}-{d.month:02d}"


def exercice(d: date) -> str:
    """Exercice décalé juillet-juin, comme la période couverte."""
    debut = d.year if d.month >= 7 else d.year - 1
    return f"{debut}-{debut + 1}"


def avancement(d: date) -> float:
    """0.0 au premier jour de la période, 1.0 au dernier."""
    total = (P.DATE_FIN - P.DATE_DEBUT).days
    return max(0.0, min(1.0, (d - P.DATE_DEBUT).days / total))


def jour_ouvre_suivant(d: date, n: int) -> date:
    """Ajoute n jours calendaires puis décale hors week-end."""
    resultat = d + timedelta(days=n)
    while resultat.weekday() >= 5:
        resultat += timedelta(days=1)
    return resultat


def indice_prix(d: date) -> float:
    return 1.0 + P.INFLATION_ANNUELLE * ((d - P.DATE_DEBUT).days / 365.25)


def interpoler(debut: Sequence[float], fin: Sequence[float], t: float) -> list[float]:
    return [a + (b - a) * t for a, b in zip(debut, fin, strict=True)]


def agences_ouvertes(d: date) -> tuple[tuple[str, ...], tuple[float, ...]]:
    """Répartition utilisée pour l'acquisition de clients."""
    if d < P.OUVERTURE_MONTPELLIER:
        return P.AGENCES_HISTORIQUES, P.POIDS_HISTORIQUES
    return ("Bordeaux", "Toulouse", "Montpellier"), (0.42, 0.33, 0.25)


def probabilite_acceptation(delai_relance: int | None) -> float:
    """Probabilité de base, avant biais commercial et effets de panier."""
    if delai_relance is None:
        return P.P_ACCEPT_JAMAIS_RELANCE
    for seuil, proba in P.P_ACCEPT_PAR_TRANCHE:
        if delai_relance <= seuil:
            return proba
    return P.P_ACCEPT_AU_DELA


# ----------------------------------------------------------------- génération
def generer(graine: int = P.GRAINE) -> JeuDeDonnees:
    """Produit les sept tables. Aucune écriture disque, aucun effet de bord."""
    rng = random.Random(graine)

    def choisir(items: Sequence[T], poids: Sequence[float]) -> T:
        return rng.choices(items, weights=poids, k=1)[0]

    # -------------------------------------------------------------- clients
    clients: list[LigneClient] = []

    def creer_client(agence: str, creation: date) -> LigneClient:
        t = avancement(creation) if creation > P.DATE_DEBUT else 0.0
        typ = choisir(P.TYPES_CLIENT, interpoler(P.MIX_DEBUT, P.MIX_FIN, t))
        ville = rng.choice(P.VILLES[agence])
        nom = (
            f"{rng.choice(P.PRENOMS)} {rng.choice(P.NOMS)}"
            if typ == "Particulier"
            else f"{rng.choice(P.ENTREPRISES)} {rng.randint(1, 99)}"
        )
        return {
            "client_id": f"CLI-{len(clients) + 1:04d}",
            "nom_client": nom,
            "type_client": typ,
            "ville": ville,
            "code_postal": P.CODES_POSTAUX[ville],
            "agence_rattachement": agence,
            "canal_acquisition": choisir(
                P.CANAUX_ACQUISITION, interpoler(P.ACQ_DEBUT, P.ACQ_FIN, t)
            ),
            "date_creation": creation,
            "profil_paiement": choisir(P.PROFILS_PAIEMENT, P.POIDS_PROFIL[typ]),
        }

    # Portefeuille antérieur à la période, sur les deux agences historiques.
    for _ in range(190):
        agence = choisir(P.AGENCES_HISTORIQUES, P.POIDS_HISTORIQUES)
        clients.append(creer_client(agence, P.DATE_DEBUT - timedelta(days=rng.randint(1, 1600))))

    # Acquisition pendant la période, au rythme croissant de l'activité.
    jour_acq = P.DATE_DEBUT
    while jour_acq <= P.DATE_FIN:
        if rng.random() < (0.34 + 0.42 * avancement(jour_acq)):
            noms, poids = agences_ouvertes(jour_acq)
            clients.append(creer_client(choisir(noms, poids), jour_acq))
        jour_acq += timedelta(days=1)

    # Reprise de fichier local à l'ouverture de Montpellier.
    for _ in range(45):
        clients.append(
            creer_client(
                "Montpellier", P.OUVERTURE_MONTPELLIER - timedelta(days=rng.randint(0, 20))
            )
        )

    clients.sort(key=lambda c: c["date_creation"])
    par_agence: dict[str, list[LigneClient]] = {a: [] for a in P.VILLES}
    for client in clients:
        par_agence[client["agence_rattachement"]].append(client)
    curseur = dict.fromkeys(P.VILLES, 0)

    def volume_du_jour(d: date, t: float) -> list[str]:
        """Répartit le volume du jour par agence.

        Les agences historiques suivent une croissance qui SATURE : au-delà des
        deux tiers de la période, l'effectif ne suit plus. Montpellier s'ajoute
        à ce socle au lieu de le partager — une agence nouvelle conquiert un
        territoire, elle ne prend pas les clients de Toulouse.
        """
        multiplicateur = 1 + 0.80 * min(1.0, t / 0.70)
        nb = max(0, int(rng.gauss(2.10 * multiplicateur, 1.05)))
        sortie = [choisir(P.AGENCES_HISTORIQUES, P.POIDS_HISTORIQUES) for _ in range(nb)]
        if d >= P.OUVERTURE_MONTPELLIER:
            mois_ouv = (d.year - P.OUVERTURE_MONTPELLIER.year) * 12 + (
                d.month - P.OUVERTURE_MONTPELLIER.month
            )
            nb_mtp = max(0, int(rng.gauss(min(1.20, 0.20 + 0.075 * mois_ouv), 0.65)))
            sortie += ["Montpellier"] * nb_mtp
        return sortie

    # ----------------------------------------------------------- production
    devis: list[LigneDevis] = []
    relances: list[LigneRelance] = []
    interventions: list[LigneIntervention] = []
    factures: list[LigneFacture] = []

    jour = P.DATE_DEBUT
    while jour <= P.DATE_FIN:
        for agence in P.VILLES:
            liste = par_agence[agence]
            while curseur[agence] < len(liste) and liste[curseur[agence]]["date_creation"] <= jour:
                curseur[agence] += 1

        if jour.weekday() >= 5:
            jour += timedelta(days=1)
            continue

        t = avancement(jour)

        for agence in volume_du_jour(jour, t):
            disponibles = par_agence[agence][: curseur[agence]]
            if not disponibles:
                continue
            client = rng.choice(disponibles)
            typ = client["type_client"]

            commerciaux = [c for c in P.COMMERCIAUX if c[1] == agence and c[2] <= jour]
            if not commerciaux:
                continue
            nom_commercial, _, _, biais, reactivite = rng.choice(commerciaux)

            categorie: Categorie = choisir(
                P.CATEGORIES, [P.SAISON[c][jour.month - 1] for c in P.CATEGORIES]
            )
            references = [c for c in P.CATALOGUE if c[2] == categorie]
            code, libelle, _, prix, marge_cible, heures_std = rng.choice(references)

            quantite = (
                1
                if prix > P.PLAFOND_LOT
                else rng.choices([1, 1, 1, 2, 3], weights=[0.62, 0.14, 0.08, 0.11, 0.05])[0]
            )
            facteur = P.PANIER_TYPE[typ] if typ != "Particulier" else 1.0
            montant = round(
                prix * quantite * facteur * indice_prix(jour) * rng.uniform(0.88, 1.18), 2
            )

            # La discipline de relance se dégrade à mesure que le volume monte.
            relance_faite = rng.random() < (P.TAUX_RELANCE_DEBUT - P.TAUX_RELANCE_DERIVE * t)
            delai_1 = (
                max(
                    1,
                    int(
                        rng.gauss(
                            P.DELAI_RELANCE_DEBUT + P.DELAI_RELANCE_DERIVE * t - reactivite, 4.0
                        )
                    ),
                )
                if relance_faite
                else None
            )

            p_acc = probabilite_acceptation(delai_1) + biais
            if montant > P.MALUS_GROS_DEVIS[1]:
                p_acc += P.MALUS_GROS_DEVIS[0]
            elif montant > P.MALUS_DEVIS_MOYEN[1]:
                p_acc += P.MALUS_DEVIS_MOYEN[0]
            if typ == "Syndic":
                p_acc += P.MALUS_SYNDIC
            if categorie == "Dépannage":
                p_acc += P.BONUS_DEPANNAGE
            p_acc = min(0.93, max(0.05, p_acc))

            statut: StatutDevis
            date_decision: date | None
            if (P.AUJOURDHUI - jour).days < 25 and rng.random() < 0.55:
                statut, date_decision = "En cours", None
            else:
                tirage = rng.random()
                if tirage < p_acc:
                    statut = "Accepté"
                elif tirage < p_acc + (1 - p_acc) * P.PART_REFUS:
                    statut = "Refusé"
                else:
                    statut = "Sans réponse"
                # Le plafonnement à la date de situation ne doit jamais ramener
                # la décision avant l'émission : un devis émis le dernier jour de
                # la période serait daté de la veille.
                date_decision = max(
                    jour,
                    min(
                        jour + timedelta(days=int(abs(rng.gauss(18, 12))) + 3),
                        P.AUJOURDHUI - timedelta(days=1),
                    ),
                )

            devis_id = f"DEV-{len(devis) + 1:05d}"
            devis.append(
                {
                    "devis_id": devis_id,
                    "date_emission": jour,
                    "mois": mois_key(jour),
                    "exercice": exercice(jour),
                    "client_id": client["client_id"],
                    "type_client": typ,
                    "agence": agence,
                    "commercial": nom_commercial,
                    "categorie": categorie,
                    "code_prestation": code,
                    "libelle_prestation": libelle,
                    "quantite": quantite,
                    "montant_ht": montant,
                    "statut": statut,
                    "date_decision": date_decision,
                    "delai_1ere_relance_j": delai_1,
                    "nb_relances": 0,
                }
            )

            if relance_faite and delai_1 is not None:
                nb_relances = rng.choices([1, 2, 3, 4], weights=[0.36, 0.34, 0.21, 0.09])[0]
                decalage = delai_1
                for rang in range(1, nb_relances + 1):
                    date_relance = jour + timedelta(days=decalage)
                    if date_relance > P.AUJOURDHUI:
                        break
                    if date_decision is not None and date_relance > date_decision:
                        break
                    canal: CanalRelance = choisir(P.CANAUX_RELANCE, P.POIDS_CANAUX_RELANCE)
                    issue: IssueRelance
                    if rang == nb_relances and statut == "Accepté":
                        issue = "Accord obtenu"
                    elif rang == nb_relances and statut == "Refusé":
                        issue = "Refus signifié"
                    else:
                        issue = choisir(P.ISSUES_NEUTRES, P.POIDS_ISSUES_NEUTRES)
                    relances.append(
                        {
                            "relance_id": f"REL-{len(relances) + 1:05d}",
                            "devis_id": devis_id,
                            "date_relance": date_relance,
                            "mois": mois_key(date_relance),
                            "exercice": exercice(date_relance),
                            "rang": rang,
                            "canal": canal,
                            "agence": agence,
                            "commercial": nom_commercial,
                            "issue": issue,
                            "duree_min": round(
                                rng.uniform(2, 14) if canal == "Téléphone" else rng.uniform(1, 5),
                                1,
                            ),
                        }
                    )
                    devis[-1]["nb_relances"] = rang
                    decalage += rng.randint(5, 14)

            if statut != "Accepté" or date_decision is None:
                continue

            date_intervention = min(
                jour_ouvre_suivant(date_decision, rng.randint(4, 30)),
                P.AUJOURDHUI - timedelta(days=1),
            )
            equipe = [x for x in P.TECHNICIENS if x[2] == agence and x[6] <= date_intervention]
            if not equipe:
                continue
            specialistes = [x for x in equipe if x[3] == categorie]
            tech_id, tech_nom, tech_agence, _, cout_horaire, _, embauche = rng.choice(
                specialistes or equipe
            )

            # Un technicien coûte plus cher pendant sa montée en charge.
            anciennete = (date_intervention - embauche).days
            if anciennete < 365:
                montee = P.MONTEE_EN_CHARGE_AN_1
            elif anciennete < 730:
                montee = P.MONTEE_EN_CHARGE_AN_2
            else:
                montee = 1.0

            heures_devisees = round(heures_std * quantite * rng.uniform(0.9, 1.15), 1)
            heures_reelles = round(
                heures_devisees * P.PRODUCTIVITE[tech_id] * montee * rng.uniform(0.92, 1.14), 1
            )
            coef_matiere = P.COEF_MATIERE_DEBUT + P.COEF_MATIERE_DERIVE * t
            cout_materiel = round(
                montant * (1 - marge_cible) * coef_matiere * rng.uniform(0.85, 1.14), 2
            )

            interventions.append(
                {
                    "intervention_id": f"INT-{len(interventions) + 1:05d}",
                    "devis_id": devis_id,
                    "date_intervention": date_intervention,
                    "mois": mois_key(date_intervention),
                    "exercice": exercice(date_intervention),
                    "technicien_id": tech_id,
                    "technicien": tech_nom,
                    "agence": tech_agence,
                    "categorie": categorie,
                    "heures_devisees": heures_devisees,
                    "heures_reelles": heures_reelles,
                    "cout_horaire": cout_horaire,
                    "cout_main_oeuvre": round(heures_reelles * cout_horaire, 2),
                    "cout_materiel": cout_materiel,
                    "statut_intervention": (
                        "Terminée"
                        if date_intervention < P.AUJOURDHUI - timedelta(days=3)
                        else "En cours"
                    ),
                }
            )

            date_facture = jour_ouvre_suivant(date_intervention, rng.randint(1, 8))
            if date_facture > P.AUJOURDHUI:
                continue

            delai = P.DELAI_PAIEMENT[typ]
            date_echeance = date_facture + timedelta(days=delai)
            tva = (
                0.10
                if categorie in ("Plomberie", "Chauffage", "Salle de bain") and typ == "Particulier"
                else 0.20
            )
            profil = client["profil_paiement"]
            derive = P.DERIVE_PROFIL[profil]
            jours_reels = max(1, int(delai + rng.gauss(derive, 16 if derive < 20 else 55)))
            # Court-circuit volontaire : le tirage n'a lieu que pour un litigieux.
            bloque = profil == "Litigieux" and rng.random() < P.PART_CONTENTIEUX
            date_paiement_prevue = date_facture + timedelta(days=jours_reels)
            # Les deux variables sont annotées avant l'embranchement : sans cela,
            # Pyright élargit une alternative de deux littéraux en `str`, qui
            # n'est plus assignable au champ `StatutFacture` de la ligne.
            date_paiement: date | None
            statut_facture: StatutFacture
            if not bloque and date_paiement_prevue <= P.AUJOURDHUI:
                date_paiement = date_paiement_prevue
                statut_facture = "Payée"
            else:
                date_paiement = None
                statut_facture = "En retard" if date_echeance < P.AUJOURDHUI else "En attente"

            factures.append(
                {
                    "facture_id": f"FAC-{len(factures) + 1:05d}",
                    "devis_id": devis_id,
                    "client_id": client["client_id"],
                    "type_client": typ,
                    "agence": agence,
                    "date_facture": date_facture,
                    "mois": mois_key(date_facture),
                    "exercice": exercice(date_facture),
                    "date_echeance": date_echeance,
                    "delai_contractuel_j": delai,
                    "montant_ht": montant,
                    "taux_tva": tva,
                    "montant_ttc": round(montant * (1 + tva), 2),
                    "profil_paiement": profil,
                    "date_paiement": date_paiement,
                    "statut_facture": statut_facture,
                }
            )

        jour += timedelta(days=1)

    techniciens: list[LigneTechnicien] = [
        {
            "technicien_id": tid,
            "nom_technicien": nom,
            "agence": agence,
            "specialite": specialite,
            "cout_horaire": cout,
            "taux_facturation_horaire": facturation,
            "date_embauche": embauche,
        }
        for tid, nom, agence, specialite, cout, facturation, embauche in sorted(
            P.TECHNICIENS, key=lambda x: x[0]
        )
    ]
    catalogue: list[LignePrestation] = [
        {
            "code_prestation": code,
            "libelle": libelle,
            "categorie": categorie,
            "prix_unitaire_ht": prix,
            "marge_cible_pct": marge,
            "heures_standard": heures,
        }
        for code, libelle, categorie, prix, marge, heures in P.CATALOGUE
    ]

    return JeuDeDonnees(
        clients=tuple(clients),
        techniciens=tuple(techniciens),
        catalogue=tuple(catalogue),
        devis=tuple(devis),
        relances=tuple(relances),
        interventions=tuple(interventions),
        factures=tuple(factures),
    )


# ------------------------------------------------------------------ écriture
def _valeur_csv(valeur: object) -> str:
    """Une seule conversion en texte, au moment de l'écriture.

    `None` devient une chaîne vide : c'est ainsi qu'une date de paiement absente
    se distingue d'une date réelle, et que `pandas` la lira en `NaT`.
    """
    if valeur is None:
        return ""
    if isinstance(valeur, date):
        return valeur.isoformat()
    return str(valeur)


def ecrire(jeu: JeuDeDonnees, destination: Path) -> list[Path]:
    """Écrit les sept CSV et rend leurs chemins, dans l'ordre de dépendance."""
    destination.mkdir(parents=True, exist_ok=True)
    ecrits: list[Path] = []
    for nom_table, nom_fichier in FICHIERS:
        lignes = jeu.table(nom_table)
        if not lignes:
            raise ValueError(f"Table vide : {nom_table}")
        chemin = destination / nom_fichier
        with chemin.open("w", newline="", encoding="utf-8") as flux:
            writer = csv.DictWriter(flux, fieldnames=list(lignes[0]), delimiter=";")
            writer.writeheader()
            for ligne in lignes:
                writer.writerow({cle: _valeur_csv(val) for cle, val in ligne.items()})
        ecrits.append(chemin)
    return ecrits
