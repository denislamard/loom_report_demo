"""Le contrat de données, une `TypedDict` par table.

Ces types décrivent exactement les colonnes des sept CSV, dans leur ordre
d'écriture. Ils servent à trois choses : Pyright vérifie que le générateur ne
produit ni clé en trop ni clé manquante, `csv.DictWriter` en tire l'en-tête, et
un lecteur comprend le schéma sans ouvrir un fichier de données.

Les valeurs sont typées telles qu'elles existent en mémoire. La conversion en
texte est faite une seule fois, à l'écriture.
"""

from __future__ import annotations

from datetime import date
from typing import Literal, TypedDict

TypeClient = Literal["Particulier", "Professionnel", "Syndic", "Collectivité"]
ProfilPaiement = Literal["Bon payeur", "Standard", "Lent", "Litigieux"]
Categorie = Literal["Plomberie", "Chauffage", "Électricité", "Salle de bain", "Dépannage"]
StatutDevis = Literal["Accepté", "Refusé", "Sans réponse", "En cours"]
StatutFacture = Literal["Payée", "En attente", "En retard"]
CanalRelance = Literal["Email", "Téléphone", "SMS"]
IssueRelance = Literal[
    "Accord obtenu",
    "Refus signifié",
    "Sans réponse",
    "Rappel demandé",
    "Négociation en cours",
    "Injoignable",
]


class LigneClient(TypedDict):
    client_id: str
    nom_client: str
    type_client: TypeClient
    ville: str
    code_postal: str
    agence_rattachement: str
    canal_acquisition: str
    date_creation: date
    profil_paiement: ProfilPaiement


class LigneTechnicien(TypedDict):
    technicien_id: str
    nom_technicien: str
    agence: str
    specialite: str
    cout_horaire: float
    taux_facturation_horaire: float
    date_embauche: date


class LignePrestation(TypedDict):
    code_prestation: str
    libelle: str
    categorie: Categorie
    prix_unitaire_ht: float
    marge_cible_pct: float
    heures_standard: float


class LigneDevis(TypedDict):
    devis_id: str
    date_emission: date
    mois: str
    exercice: str
    client_id: str
    type_client: TypeClient
    agence: str
    commercial: str
    categorie: Categorie
    code_prestation: str
    libelle_prestation: str
    quantite: int
    montant_ht: float
    statut: StatutDevis
    date_decision: date | None
    delai_1ere_relance_j: int | None
    nb_relances: int


class LigneRelance(TypedDict):
    relance_id: str
    devis_id: str
    date_relance: date
    mois: str
    exercice: str
    rang: int
    canal: CanalRelance
    agence: str
    commercial: str
    issue: IssueRelance
    duree_min: float


class LigneIntervention(TypedDict):
    intervention_id: str
    devis_id: str
    date_intervention: date
    mois: str
    exercice: str
    technicien_id: str
    technicien: str
    agence: str
    categorie: Categorie
    heures_devisees: float
    heures_reelles: float
    cout_horaire: float
    cout_main_oeuvre: float
    cout_materiel: float
    statut_intervention: Literal["Terminée", "En cours"]


class LigneFacture(TypedDict):
    facture_id: str
    devis_id: str
    client_id: str
    type_client: TypeClient
    agence: str
    date_facture: date
    mois: str
    exercice: str
    date_echeance: date
    delai_contractuel_j: int
    montant_ht: float
    taux_tva: float
    montant_ttc: float
    profil_paiement: ProfilPaiement
    date_paiement: date | None
    statut_facture: StatutFacture


#: Nom de fichier associé à chaque table, dans l'ordre de dépendance : un
#: lecteur qui les charge dans cet ordre n'a jamais de référence pendante.
FICHIERS: tuple[tuple[str, str], ...] = (
    ("clients", "clients.csv"),
    ("techniciens", "techniciens.csv"),
    ("catalogue", "catalogue_prestations.csv"),
    ("devis", "devis.csv"),
    ("relances", "relances.csv"),
    ("interventions", "interventions.csv"),
    ("factures", "factures.csv"),
)
