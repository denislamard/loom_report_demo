"""Constantes métier du scénario Bâti-Sud, et trajectoire de l'entreprise.

Aucune logique ici : uniquement des données. Modifier une valeur change le jeu
produit, donc les empreintes SHA-256, donc les tests de reproductibilité — ce qui
est le comportement voulu.

La trajectoire est volontairement lisible, car c'est elle que le niveau
stratégique doit permettre de constater :

    Exercice 1 (2022-07 -> 2023-06)  2 agences, 7 techniciens, clientèle de
                                     particuliers, marge confortable, relance
                                     disciplinée.
    Exercice 2 (2023-07 -> 2024-06)  croissance du volume, deux embauches
                                     (sept. et nov. 2023) : la marge encaisse
                                     la montée en charge des nouveaux.
    Exercice 3 (2024-07 -> 2025-06)  ouverture de Montpellier (sept. 2024),
                                     deux techniciens de plus, bascule de la
                                     clientèle vers les pros et les syndics.
    Exercice 4 (2025-07 -> 2026-06)  volume au plus haut, discipline de relance
                                     dégradée, marge et DSO au plus bas.

Les trois dégradations sont des CONSÉQUENCES de la croissance, pas des variables
indépendantes :

    marge          coût matière qui dérive + montée en charge des embauches
    transformation la relance ne suit plus le volume
    DSO            le mix client bascule vers des payeurs à 45-60 jours

C'est cette causalité qui donne matière à l'agent : il peut la trouver, et il
peut se tromper de coupable.
"""

from __future__ import annotations

from datetime import date

from loom_report_demo.dataset.lignes import (
    CanalRelance,
    Categorie,
    IssueRelance,
    ProfilPaiement,
    TypeClient,
)

#: Graine du générateur. La changer produit un autre jeu de données cohérent.
GRAINE = 20260630

DATE_DEBUT = date(2022, 7, 1)
DATE_FIN = date(2026, 6, 30)
#: Date de situation : aucun mouvement n'est enregistré au-delà.
AUJOURDHUI = DATE_FIN

OUVERTURE_MONTPELLIER = date(2024, 9, 1)

AGENCES_HISTORIQUES: tuple[str, ...] = ("Bordeaux", "Toulouse")
POIDS_HISTORIQUES: tuple[float, ...] = (0.56, 0.44)

CATEGORIES: tuple[Categorie, ...] = (
    "Plomberie",
    "Chauffage",
    "Électricité",
    "Salle de bain",
    "Dépannage",
)

#: Indice de saisonnalité mensuel, index 0 = janvier.
SAISON: dict[Categorie, tuple[float, ...]] = {
    "Plomberie": (0.9, 0.9, 1.0, 1.0, 1.1, 1.2, 1.3, 1.2, 1.0, 0.9, 0.8, 0.7),
    "Chauffage": (1.4, 1.1, 0.8, 0.6, 0.5, 0.4, 0.4, 0.6, 1.3, 1.7, 1.6, 1.2),
    "Électricité": (1.0, 1.0, 1.0, 1.1, 1.1, 1.0, 0.9, 0.9, 1.1, 1.0, 1.0, 0.9),
    "Salle de bain": (0.8, 0.9, 1.1, 1.2, 1.2, 1.1, 0.9, 0.8, 1.1, 1.2, 1.0, 0.7),
    "Dépannage": (1.3, 1.1, 1.0, 0.9, 0.9, 0.9, 1.0, 1.0, 1.0, 1.1, 1.2, 1.2),
}

#: nom, agence, arrivée, biais de transformation, réactivité de relance (jours).
COMMERCIAUX: tuple[tuple[str, str, date, float, float], ...] = (
    ("Karim Belkacem", "Bordeaux", date(2019, 1, 1), 0.12, 2.5),
    ("Sophie Marchand", "Bordeaux", date(2020, 6, 1), 0.02, 0.5),
    ("Julien Fabre", "Toulouse", date(2018, 3, 1), 0.00, 0.0),
    ("Nadia Cherif", "Toulouse", date(2023, 9, 4), 0.03, 1.0),
    ("Thomas Rey", "Montpellier", date(2024, 9, 1), -0.07, -2.0),
)

#: id, nom, agence, spécialité, coût horaire, taux de facturation, embauche.
#: L'ordre est chronologique par vague de recrutement, pas alphabétique.
TECHNICIENS: tuple[tuple[str, str, str, str, float, float, date], ...] = (
    ("TEC-01", "Marc Delaunay", "Bordeaux", "Plomberie", 32.0, 68.0, date(2016, 3, 1)),
    ("TEC-02", "Ahmed Zahiri", "Bordeaux", "Chauffage", 35.0, 72.0, date(2018, 9, 1)),
    ("TEC-03", "Fabien Ortiz", "Bordeaux", "Électricité", 33.0, 70.0, date(2019, 1, 15)),
    ("TEC-05", "Sonia Mercier", "Bordeaux", "Salle de bain", 31.0, 66.0, date(2021, 4, 1)),
    ("TEC-06", "Pierre Vasseur", "Toulouse", "Chauffage", 36.0, 74.0, date(2015, 2, 1)),
    ("TEC-07", "Yannick Dubreuil", "Toulouse", "Plomberie", 30.0, 68.0, date(2020, 10, 1)),
    ("TEC-08", "Elodie Ravel", "Toulouse", "Électricité", 32.0, 70.0, date(2022, 3, 1)),
    ("TEC-04", "Lucas Bertin", "Bordeaux", "Plomberie", 27.0, 68.0, date(2023, 9, 4)),
    ("TEC-09", "Mehdi Ouali", "Toulouse", "Dépannage", 28.0, 64.0, date(2023, 11, 6)),
    ("TEC-10", "Bruno Castel", "Montpellier", "Plomberie", 31.0, 66.0, date(2024, 9, 1)),
    ("TEC-11", "Damien Roche", "Montpellier", "Chauffage", 34.0, 70.0, date(2024, 9, 1)),
    ("TEC-12", "Inès Bonnaud", "Montpellier", "Électricité", 29.0, 66.0, date(2025, 3, 3)),
)

#: Productivité de croisière : au-dessus de 1, le technicien passe plus d'heures
#: que devisé. S'y ajoute une montée en charge la première année.
PRODUCTIVITE: dict[str, float] = {
    "TEC-01": 0.94,
    "TEC-02": 0.91,
    "TEC-03": 0.98,
    "TEC-04": 1.10,
    "TEC-05": 0.96,
    "TEC-06": 0.89,
    "TEC-07": 1.02,
    "TEC-08": 0.99,
    "TEC-09": 1.04,
    "TEC-10": 1.03,
    "TEC-11": 1.00,
    "TEC-12": 1.12,
}

#: Surcoût horaire d'un technicien selon son ancienneté, en années révolues.
MONTEE_EN_CHARGE_AN_1 = 1.16
MONTEE_EN_CHARGE_AN_2 = 1.06

VILLES: dict[str, tuple[str, ...]] = {
    "Bordeaux": ("Bordeaux", "Mérignac", "Pessac", "Talence", "Bègles", "Libourne"),
    "Toulouse": ("Toulouse", "Blagnac", "Colomiers", "Balma", "Muret", "Tournefeuille"),
    "Montpellier": ("Montpellier", "Lattes", "Castelnau-le-Lez", "Sète", "Béziers", "Lunel"),
}

CODES_POSTAUX: dict[str, str] = {
    "Bordeaux": "33000",
    "Mérignac": "33700",
    "Pessac": "33600",
    "Talence": "33400",
    "Bègles": "33130",
    "Libourne": "33500",
    "Toulouse": "31000",
    "Blagnac": "31700",
    "Colomiers": "31770",
    "Balma": "31130",
    "Muret": "31600",
    "Tournefeuille": "31170",
    "Montpellier": "34000",
    "Lattes": "34970",
    "Castelnau-le-Lez": "34170",
    "Sète": "34200",
    "Béziers": "34500",
    "Lunel": "34400",
}

TYPES_CLIENT: tuple[TypeClient, ...] = (
    "Particulier",
    "Professionnel",
    "Syndic",
    "Collectivité",
)
#: Le mix bascule des particuliers vers les professionnels et les syndics.
MIX_DEBUT: tuple[float, ...] = (0.70, 0.20, 0.07, 0.03)
MIX_FIN: tuple[float, ...] = (0.51, 0.26, 0.15, 0.08)

DELAI_PAIEMENT: dict[TypeClient, int] = {
    "Particulier": 15,
    "Professionnel": 30,
    "Syndic": 60,
    "Collectivité": 45,
}
PANIER_TYPE: dict[TypeClient, float] = {
    "Particulier": 1.0,
    "Professionnel": 1.7,
    "Syndic": 2.1,
    "Collectivité": 2.4,
}

PROFILS_PAIEMENT: tuple[ProfilPaiement, ...] = (
    "Bon payeur",
    "Standard",
    "Lent",
    "Litigieux",
)
POIDS_PROFIL: dict[TypeClient, tuple[float, ...]] = {
    "Particulier": (0.46, 0.42, 0.10, 0.02),
    "Professionnel": (0.30, 0.44, 0.20, 0.06),
    "Syndic": (0.14, 0.36, 0.38, 0.12),
    "Collectivité": (0.12, 0.40, 0.38, 0.10),
}
#: Décalage moyen, en jours, par rapport à l'échéance contractuelle.
DERIVE_PROFIL: dict[ProfilPaiement, int] = {
    "Bon payeur": -6,
    "Standard": 2,
    "Lent": 34,
    "Litigieux": 115,
}
#: Part des litigieux dont la facture reste durablement bloquée.
PART_CONTENTIEUX = 0.30

CANAUX_ACQUISITION: tuple[str, ...] = (
    "Bouche-à-oreille",
    "Site web",
    "Google Ads",
    "Partenaire",
    "Annuaire pro",
    "Prospection",
)
ACQ_DEBUT: tuple[float, ...] = (0.44, 0.18, 0.08, 0.12, 0.11, 0.07)
ACQ_FIN: tuple[float, ...] = (0.26, 0.24, 0.20, 0.13, 0.06, 0.11)

CANAUX_RELANCE: tuple[CanalRelance, ...] = ("Email", "Téléphone", "SMS")
POIDS_CANAUX_RELANCE: tuple[float, ...] = (0.52, 0.36, 0.12)

ISSUES_NEUTRES: tuple[IssueRelance, ...] = (
    "Sans réponse",
    "Rappel demandé",
    "Négociation en cours",
    "Injoignable",
)
POIDS_ISSUES_NEUTRES: tuple[float, ...] = (0.44, 0.26, 0.17, 0.13)

PRENOMS: tuple[str, ...] = (
    "Alain", "Béatrice", "Cédric", "Delphine", "Émile", "Fanny", "Gérard", "Hélène",
    "Ibrahim", "Joëlle", "Kevin", "Laure", "Marc", "Nathalie", "Olivier", "Pauline",
    "Quentin", "Rachida", "Serge", "Tiphaine", "Ulysse", "Valérie", "William", "Yasmine",
    "Adrien", "Camille", "Damien", "Elsa", "Franck", "Gaëlle", "Hugo", "Inès",
)  # fmt: skip

NOMS: tuple[str, ...] = (
    "Dubois", "Moreau", "Lefèvre", "Girard", "Bonnet", "Roussel", "Perrin", "Vidal",
    "Faure", "Chevalier", "Robin", "Masson", "Lemoine", "Guerin", "Barbier", "Renard",
    "Aubert", "Colin", "Dupuis", "Marchal", "Poirier", "Léger", "Brun", "Charpentier",
    "Noel", "Berger", "Rey", "Blanc", "Gaillard", "Millet", "Da Silva", "Nguyen",
)  # fmt: skip

ENTREPRISES: tuple[str, ...] = (
    "SCI Les Tilleuls", "Cabinet Vergne Immobilier", "Boulangerie Marchetti",
    "Hôtel Le Cardinal", "Garage Autoplus", "Clinique du Parc", "SARL Toitures Sud",
    "Résidence Les Oliviers", "Brasserie du Port", "Cabinet dentaire Ansel",
    "Syndic Gestion Aquitaine", "Foncia Occitanie", "Résidence Belvédère",
    "Mairie de Lattes", "CCAS de Muret", "Lycée Saint-Exupéry",
    "Supérette Vival", "Pharmacie Centrale", "Salle de sport Ironfit",
    "Camping Les Pins", "EHPAD Les Glycines", "Cabinet vétérinaire Dorel",
    "Office HLM Aquitaine", "Groupe scolaire Jean-Jaurès", "Restaurant Le Bistrot",
    "Menuiserie Lacoste", "Auto-école Conduite Plus", "Cabinet comptable Serval",
)  # fmt: skip

#: code, libellé, catégorie, prix unitaire HT, marge cible, heures standard.
CATALOGUE: tuple[tuple[str, str, Categorie, float, float, float], ...] = (
    ("PR-001", "Remplacement chauffe-eau 200 L", "Plomberie", 1180, 0.34, 4.5),
    ("PR-002", "Recherche de fuite + réparation", "Plomberie", 420, 0.46, 2.0),
    ("PR-003", "Réfection réseau eau appartement", "Plomberie", 2950, 0.30, 14.0),
    ("PR-004", "Remplacement colonne d'évacuation", "Plomberie", 5400, 0.26, 26.0),
    ("CH-001", "Installation chaudière gaz condensation", "Chauffage", 4650, 0.28, 12.0),
    ("CH-002", "Entretien annuel chaudière", "Chauffage", 145, 0.58, 1.0),
    ("CH-003", "Installation pompe à chaleur air/eau", "Chauffage", 12800, 0.24, 28.0),
    ("CH-004", "Remplacement radiateurs (lot de 5)", "Chauffage", 2380, 0.32, 9.0),
    ("CH-005", "Désembouage circuit chauffage", "Chauffage", 680, 0.49, 3.5),
    ("EL-001", "Mise aux normes tableau électrique", "Électricité", 1650, 0.38, 7.0),
    ("EL-002", "Installation borne de recharge VE", "Électricité", 1420, 0.35, 5.0),
    ("EL-003", "Rénovation électrique complète", "Électricité", 8900, 0.27, 40.0),
    ("EL-004", "Éclairage LED locaux professionnels", "Électricité", 3200, 0.36, 15.0),
    ("SB-001", "Rénovation salle de bain complète", "Salle de bain", 9200, 0.25, 45.0),
    ("SB-002", "Remplacement baignoire par douche", "Salle de bain", 3450, 0.31, 16.0),
    ("SB-003", "Pose meuble vasque + robinetterie", "Salle de bain", 1150, 0.37, 5.5),
    ("DP-001", "Dépannage plomberie urgence", "Dépannage", 260, 0.52, 1.5),
    ("DP-002", "Débouchage canalisation", "Dépannage", 340, 0.55, 2.0),
    ("DP-003", "Dépannage électrique urgence", "Dépannage", 290, 0.51, 1.5),
    ("DP-004", "Remise en service chaudière", "Dépannage", 220, 0.56, 1.0),
)

#: Au-delà de ce prix unitaire, la prestation ne se commande pas par lots : sans
#: cette garde, un devis isolé à 38 k€ suffit à faire bouger le CA d'un exercice.
PLAFOND_LOT = 8000

#: Revalorisation tarifaire annuelle. La croissance du CA n'est donc pas que du
#: volume, ce qui donne matière à une décomposition d'écart au jalon 4.
INFLATION_ANNUELLE = 0.025

#: Le coefficient appliqué au coût matière dérive de +20 points sur la période.
COEF_MATIERE_DEBUT = 0.70
COEF_MATIERE_DERIVE = 0.20

#: Part des devis effectivement relancés : elle se dégrade quand le volume monte.
TAUX_RELANCE_DEBUT = 0.90
TAUX_RELANCE_DERIVE = 0.28

#: Délai moyen de première relance, en jours, avant réactivité du commercial.
DELAI_RELANCE_DEBUT = 5.0
DELAI_RELANCE_DERIVE = 6.0

#: Probabilité d'acceptation selon le délai de première relance. C'est le cœur
#: de la démonstration commerciale : un devis relancé sous trois jours se
#: transforme trois fois mieux qu'un devis jamais relancé.
P_ACCEPT_JAMAIS_RELANCE = 0.17
P_ACCEPT_PAR_TRANCHE: tuple[tuple[int, float], ...] = (
    (3, 0.55),
    (7, 0.45),
    (15, 0.32),
)
P_ACCEPT_AU_DELA = 0.21

MALUS_GROS_DEVIS = (-0.11, 8000)
MALUS_DEVIS_MOYEN = (-0.05, 4000)
MALUS_SYNDIC = -0.06
BONUS_DEPANNAGE = 0.12
#: Part des devis arbitrés qui sont refusés plutôt que restés sans réponse.
PART_REFUS = 0.42
