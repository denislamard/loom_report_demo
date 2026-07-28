"""Le vocabulaire fermé de l'analyse : mesures, dimensions, cadrages.

Ce module ne contient que des déclarations. Aucun calcul, aucune dépendance à
pandas. C'est lui qui définit ce que l'agent a le droit de demander, et c'est de
lui que seront tirés les `enum` des outils d'exploration : un argument hors
catalogue est rejeté avant exécution, sans qu'aucune expression libre n'atteigne
jamais le moteur.

Trois notions structurent le catalogue.

**La base** est la table de faits sur laquelle une mesure se calcule. Un couple
`(mesure, dimension)` n'est valide que si la dimension existe sur la base de la
mesure : demander la marge par commercial n'a pas de sens, la marge se constate
sur une facture et un commercial ne facture pas.

**L'agrégat** est une algèbre volontairement pauvre — `facteur × num / den +
décalage` — mais suffisante pour dix-sept mesures sur dix-neuf. On somme les
numérateurs et les dénominateurs *avant* de diviser, jamais l'inverse : la
moyenne d'un taux n'est pas le taux moyen, et c'est la faute la plus répandue
dans les tableaux de bord d'entreprise.

**Le niveau** restreint le catalogue. Toutes les mesures ne sont pas éligibles
partout : le retard en jours d'une facture est opérationnel et n'a rien à faire
dans un rapport stratégique ; la concentration client est l'inverse. Sans cet
attribut, l'agent produirait un stratégique qui ne serait qu'un rapport de
gestion agrégé.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from loom_report_demo.niveaux import Niveau


class Base(StrEnum):
    """Table de faits portant la mesure."""

    DEVIS = "devis"
    FACTURES = "factures"
    INTERVENTIONS = "interventions"


class Unite(StrEnum):
    EUROS = "€"
    POURCENT = "%"
    JOURS = "j"
    HEURES = "h"
    NOMBRE = ""


class Nature(StrEnum):
    """Ce qu'une mesure mesure, et donc ce qu'on a le droit d'en comparer.

    Un FLUX se constate sur les mouvements d'une période : le comparer à la
    période précédente a un sens. Un STOCK est un état à la date de situation :
    l'encours d'aujourd'hui n'a pas d'équivalent « des douze mois précédents »,
    puisque les factures de l'an dernier ont été réglées depuis. Comparer un
    stock entre deux fenêtres produit des écarts de plusieurs milliers de pour
    cent qui ne veulent rien dire — et c'est précisément le genre de faux constat
    qu'un agent bâtirait avec assurance.

    Une comparaison honnête d'un stock demanderait de le recalculer à une date de
    situation antérieure. Ce n'est pas au périmètre : le moteur refuse donc de
    produire l'écart plutôt que d'en produire un faux.
    """

    FLUX = "flux"
    STOCK = "stock"


class Sens(StrEnum):
    """Direction souhaitable. Détermine quelle modalité est « la pire »."""

    HAUT = "plus_haut_mieux"
    BAS = "plus_bas_mieux"
    NEUTRE = "neutre"


@dataclass(frozen=True, slots=True)
class Agregat:
    """`facteur × (numerateur / dénominateur) + décalage`.

    Sans dénominateur, la mesure est une simple somme. `distinct` remplace la
    somme du dénominateur par un décompte de valeurs distinctes — le seul cas est
    le chiffre d'affaires par technicien.
    """

    numerateur: str
    denominateur: str | None = None
    distinct: str | None = None
    facteur: float = 1.0
    decalage: float = 0.0

    def __post_init__(self) -> None:
        if self.denominateur is not None and self.distinct is not None:
            raise ValueError("Un agrégat ne peut avoir à la fois un dénominateur et un distinct")

    @property
    def est_ratio(self) -> bool:
        return self.denominateur is not None or self.distinct is not None


@dataclass(frozen=True, slots=True)
class Mesure:
    cle: str
    libelle: str
    base: Base
    unite: Unite
    sens: Sens
    niveaux: frozenset[Niveau]
    nature: Nature = Nature.FLUX
    agregat: Agregat | None = None
    #: Nom d'une fonction du registre `moteur.SPECIALES`, pour les rares mesures
    #: que l'algèbre des agrégats ne couvre pas.
    special: str | None = None
    #: Une mesure matérialisable peut être convertie en euros : c'est elle qui
    #: alimentera le score de matérialité du criblage, au jalon 3.
    materialisable: bool = True
    description: str = ""

    def __post_init__(self) -> None:
        if (self.agregat is None) == (self.special is None):
            raise ValueError(f"{self.cle} : exactement un agrégat ou une spéciale")

    def concerne(self, niveau: Niveau) -> bool:
        return niveau in self.niveaux

    @property
    def comparable_entre_periodes(self) -> bool:
        return self.nature is Nature.FLUX


@dataclass(frozen=True, slots=True)
class Dimension:
    cle: str
    libelle: str
    colonne: str
    bases: frozenset[Base]
    niveaux: frozenset[Niveau]
    #: Vrai si les modalités ont un ordre naturel — une tranche d'ancienneté se
    #: lit dans l'ordre, une agence non.
    ordonnee: bool = False
    #: Ordre imposé des modalités, pour les dimensions ordonnées.
    modalites: tuple[str, ...] = field(default_factory=tuple)
    description: str = ""

    def concerne(self, niveau: Niveau) -> bool:
        return niveau in self.niveaux

    def disponible_sur(self, base: Base) -> bool:
        return base in self.bases


_TOUS = frozenset(Niveau)
_STRAT = frozenset({Niveau.STRATEGIQUE})
_GESTION = frozenset({Niveau.GESTION})
_OPE = frozenset({Niveau.OPERATIONNEL})
_STRAT_GESTION = frozenset({Niveau.STRATEGIQUE, Niveau.GESTION})
_GESTION_OPE = frozenset({Niveau.GESTION, Niveau.OPERATIONNEL})

_MESURES: tuple[Mesure, ...] = (
    # ----------------------------------------------------------- facturation
    Mesure(
        cle="ca_facture_ht",
        libelle="Chiffre d'affaires facturé HT",
        base=Base.FACTURES,
        unite=Unite.EUROS,
        sens=Sens.HAUT,
        niveaux=_TOUS,
        agregat=Agregat(numerateur="montant_ht"),
        description="Somme des montants hors taxes facturés sur la période.",
    ),
    Mesure(
        cle="marge_brute",
        libelle="Marge brute",
        base=Base.FACTURES,
        unite=Unite.EUROS,
        sens=Sens.HAUT,
        niveaux=_STRAT_GESTION,
        agregat=Agregat(numerateur="marge"),
        description="Chiffre d'affaires diminué des coûts directs de l'intervention liée.",
    ),
    Mesure(
        cle="taux_marge_brute",
        libelle="Taux de marge brute",
        base=Base.FACTURES,
        unite=Unite.POURCENT,
        sens=Sens.HAUT,
        niveaux=_TOUS,
        agregat=Agregat(numerateur="marge", denominateur="montant_ht"),
        description="Marge sur coûts directs rapportée au chiffre d'affaires, hors structure.",
    ),
    Mesure(
        cle="encours_client",
        libelle="Encours client TTC",
        base=Base.FACTURES,
        unite=Unite.EUROS,
        sens=Sens.BAS,
        niveaux=_GESTION_OPE,
        nature=Nature.STOCK,
        agregat=Agregat(numerateur="encours"),
        description="Montant TTC restant dû à la date de situation.",
    ),
    Mesure(
        cle="dso",
        libelle="DSO — délai moyen d'encaissement",
        base=Base.FACTURES,
        unite=Unite.JOURS,
        sens=Sens.BAS,
        niveaux=_STRAT_GESTION,
        nature=Nature.STOCK,
        agregat=Agregat(numerateur="encours", denominateur="montant_ttc", facteur=365.0),
        materialisable=False,
        description="Encours rapporté au chiffre d'affaires TTC de la période, ramené en jours.",
    ),
    Mesure(
        cle="delai_reglement",
        libelle="Délai réel de règlement",
        base=Base.FACTURES,
        unite=Unite.JOURS,
        sens=Sens.BAS,
        niveaux=_GESTION_OPE,
        agregat=Agregat(numerateur="delai_reel_pondere", denominateur="est_payee"),
        materialisable=False,
        description=(
            "Moyenne des délais constatés sur les factures réglées. Attention au biais de "
            "survie : les mauvais payeurs récents n'ont pas encore payé et sortent du calcul. "
            "Le DSO n'a pas ce défaut."
        ),
    ),
    Mesure(
        cle="taux_retard_paiement",
        libelle="Part des factures en retard",
        base=Base.FACTURES,
        unite=Unite.POURCENT,
        sens=Sens.BAS,
        niveaux=_GESTION_OPE,
        nature=Nature.STOCK,
        agregat=Agregat(numerateur="en_retard", denominateur="ligne"),
        materialisable=False,
        description="Factures échues et non réglées, rapportées au nombre total de factures.",
    ),
    Mesure(
        cle="age_moyen_file_recouvrement",
        libelle="Âge moyen de la file de recouvrement",
        base=Base.FACTURES,
        unite=Unite.JOURS,
        sens=Sens.BAS,
        niveaux=_OPE,
        nature=Nature.STOCK,
        agregat=Agregat(numerateur="retard_pondere", denominateur="encours"),
        materialisable=False,
        description=(
            "Retard moyen pondéré par le montant : un gros impayé pèse plus qu'un petit."
        ),
    ),
    Mesure(
        cle="exceptions_ouvertes",
        libelle="Exceptions ouvertes",
        base=Base.FACTURES,
        unite=Unite.NOMBRE,
        sens=Sens.BAS,
        niveaux=_OPE,
        nature=Nature.STOCK,
        agregat=Agregat(numerateur="exception"),
        materialisable=False,
        description="Créances dépassant le seuil de recouvrement, à traiter individuellement.",
    ),
    Mesure(
        cle="concentration_client",
        libelle="Concentration du chiffre d'affaires",
        base=Base.FACTURES,
        unite=Unite.POURCENT,
        sens=Sens.BAS,
        niveaux=_STRAT,
        special="concentration_client",
        materialisable=False,
        description=(
            "Part du chiffre d'affaires réalisée par les dix pour cent de clients les plus "
            "contributeurs. Mesure un risque de dépendance, pas une performance."
        ),
    ),
    # -------------------------------------------------------------- commerce
    Mesure(
        cle="taux_transformation",
        libelle="Taux de transformation des devis",
        base=Base.DEVIS,
        unite=Unite.POURCENT,
        sens=Sens.HAUT,
        niveaux=_TOUS,
        agregat=Agregat(numerateur="ca_gagne", denominateur="montant_arbitre"),
        description=(
            "Euros gagnés rapportés aux euros arbitrés. En valeur et non en nombre : un taux "
            "en nombre se manipule en cessant de chiffrer les gros dossiers."
        ),
    ),
    Mesure(
        cle="ca_devise_ht",
        libelle="Volume devisé HT",
        base=Base.DEVIS,
        unite=Unite.EUROS,
        sens=Sens.HAUT,
        niveaux=_GESTION,
        agregat=Agregat(numerateur="montant_ht"),
        description="Somme des devis émis, tous statuts confondus.",
    ),
    Mesure(
        cle="panier_moyen_gagne",
        libelle="Panier moyen d'un devis gagné",
        base=Base.DEVIS,
        unite=Unite.EUROS,
        sens=Sens.HAUT,
        niveaux=_STRAT_GESTION,
        agregat=Agregat(numerateur="ca_gagne", denominateur="est_gagne"),
        description="Montant moyen des devis acceptés.",
    ),
    Mesure(
        cle="delai_1ere_relance",
        libelle="Délai de première relance",
        base=Base.DEVIS,
        unite=Unite.JOURS,
        sens=Sens.BAS,
        niveaux=_GESTION_OPE,
        agregat=Agregat(numerateur="delai_relance_pondere", denominateur="est_relance"),
        materialisable=False,
        description="Nombre de jours entre l'émission du devis et le premier rappel.",
    ),
    Mesure(
        cle="taux_devis_relances",
        libelle="Part des devis relancés",
        base=Base.DEVIS,
        unite=Unite.POURCENT,
        sens=Sens.HAUT,
        niveaux=_GESTION_OPE,
        agregat=Agregat(numerateur="est_relance", denominateur="ligne"),
        materialisable=False,
        description="Devis ayant fait l'objet d'au moins un rappel.",
    ),
    Mesure(
        cle="respect_delai_relance",
        libelle="Relances émises dans le délai",
        base=Base.DEVIS,
        unite=Unite.POURCENT,
        sens=Sens.HAUT,
        niveaux=_OPE,
        agregat=Agregat(numerateur="relance_rapide", denominateur="ligne"),
        materialisable=False,
        description=(
            "Devis relancés sous trois jours, seuil au-delà duquel la transformation chute."
        ),
    ),
    # ------------------------------------------------------------ production
    Mesure(
        cle="taux_derive_horaire",
        libelle="Dérive des heures passées",
        base=Base.INTERVENTIONS,
        unite=Unite.POURCENT,
        sens=Sens.BAS,
        niveaux=_GESTION_OPE,
        agregat=Agregat(
            numerateur="heures_reelles", denominateur="heures_devisees", decalage=-1.0
        ),
        description="Écart entre heures réellement passées et heures devisées.",
    ),
    Mesure(
        cle="marge_production",
        libelle="Marge de production",
        base=Base.INTERVENTIONS,
        unite=Unite.EUROS,
        sens=Sens.HAUT,
        niveaux=_GESTION,
        agregat=Agregat(numerateur="marge"),
        description="Marge constatée au niveau de l'intervention, avant facturation.",
    ),
    Mesure(
        cle="ca_par_technicien",
        libelle="Chiffre d'affaires par technicien",
        base=Base.INTERVENTIONS,
        unite=Unite.EUROS,
        sens=Sens.HAUT,
        niveaux=_STRAT,
        agregat=Agregat(numerateur="ca_lie", distinct="technicien_id"),
        materialisable=False,
        description="Production rapportée à l'effectif réellement actif sur la période.",
    ),
)

_DIMENSIONS: tuple[Dimension, ...] = (
    Dimension(
        cle="agence",
        libelle="Agence",
        colonne="agence",
        bases=frozenset(Base),
        niveaux=_TOUS,
        description="Bordeaux, Toulouse, Montpellier.",
    ),
    Dimension(
        cle="metier",
        libelle="Métier",
        colonne="metier",
        bases=frozenset(Base),
        niveaux=_TOUS,
        description="Plomberie, chauffage, électricité, salle de bain, dépannage.",
    ),
    Dimension(
        cle="commercial",
        libelle="Commercial",
        colonne="commercial",
        bases=frozenset({Base.DEVIS}),
        niveaux=_GESTION_OPE,
    ),
    Dimension(
        cle="type_client",
        libelle="Type de client",
        colonne="type_client",
        bases=frozenset({Base.DEVIS, Base.FACTURES}),
        niveaux=_TOUS,
        description="Particulier, professionnel, syndic, collectivité.",
    ),
    Dimension(
        cle="canal_acquisition",
        libelle="Canal d'acquisition",
        colonne="canal_acquisition",
        bases=frozenset({Base.DEVIS, Base.FACTURES}),
        niveaux=_STRAT_GESTION,
    ),
    Dimension(
        cle="profil_paiement",
        libelle="Profil de paiement",
        colonne="profil_paiement",
        bases=frozenset({Base.FACTURES}),
        niveaux=_GESTION_OPE,
        ordonnee=True,
        modalites=("Bon payeur", "Standard", "Lent", "Litigieux"),
    ),
    Dimension(
        cle="technicien",
        libelle="Technicien",
        colonne="technicien",
        bases=frozenset({Base.INTERVENTIONS}),
        niveaux=_GESTION_OPE,
    ),
    Dimension(
        cle="anciennete_technicien",
        libelle="Ancienneté du technicien",
        colonne="anciennete_technicien",
        bases=frozenset({Base.INTERVENTIONS}),
        niveaux=_TOUS,
        ordonnee=True,
        modalites=("Moins d'un an", "1 à 2 ans", "Plus de 2 ans"),
        description="Tranche d'ancienneté à la date de l'intervention.",
    ),
    Dimension(
        cle="tranche_relance",
        libelle="Délai de première relance",
        colonne="tranche_relance",
        bases=frozenset({Base.DEVIS}),
        niveaux=_GESTION_OPE,
        ordonnee=True,
        modalites=("0-3 j", "4-7 j", "8-15 j", "Plus de 15 j", "Jamais relancé"),
    ),
    Dimension(
        cle="tranche_age_creance",
        libelle="Ancienneté de la créance",
        colonne="tranche_age_creance",
        bases=frozenset({Base.FACTURES}),
        niveaux=_GESTION_OPE,
        ordonnee=True,
        modalites=("Réglée", "Non échu", "1-30 j", "31-60 j", "61-90 j", "Plus de 90 j"),
    ),
    Dimension(
        cle="prestation",
        libelle="Prestation",
        colonne="prestation",
        bases=frozenset({Base.DEVIS, Base.FACTURES}),
        niveaux=_GESTION,
        description="Libellé du catalogue, vingt modalités.",
    ),
    Dimension(
        cle="tranche_montant",
        libelle="Tranche de montant",
        colonne="tranche_montant",
        bases=frozenset({Base.DEVIS, Base.FACTURES}),
        niveaux=_GESTION_OPE,
        ordonnee=True,
        modalites=("Moins de 1 k€", "1 à 5 k€", "5 à 15 k€", "Plus de 15 k€"),
    ),
)

MESURES: dict[str, Mesure] = {m.cle: m for m in _MESURES}
DIMENSIONS: dict[str, Dimension] = {d.cle: d for d in _DIMENSIONS}


def mesure(cle: str) -> Mesure:
    try:
        return MESURES[cle]
    except KeyError:
        raise KeyError(
            f"Mesure inconnue : {cle!r}. Disponibles : {', '.join(sorted(MESURES))}"
        ) from None


def dimension(cle: str) -> Dimension:
    try:
        return DIMENSIONS[cle]
    except KeyError:
        raise KeyError(
            f"Dimension inconnue : {cle!r}. Disponibles : {', '.join(sorted(DIMENSIONS))}"
        ) from None


def mesures_du_niveau(niveau: Niveau) -> tuple[Mesure, ...]:
    return tuple(m for m in _MESURES if m.concerne(niveau))


def dimensions_du_niveau(niveau: Niveau) -> tuple[Dimension, ...]:
    return tuple(d for d in _DIMENSIONS if d.concerne(niveau))


def croisements_valides(niveau: Niveau) -> tuple[tuple[str, str], ...]:
    """Couples `(mesure, dimension)` calculables à ce niveau.

    Une dimension absente de la base d'une mesure produit un couple invalide : la
    marge se constate sur une facture, un commercial n'en émet pas.
    """
    return tuple(
        (m.cle, d.cle)
        for m in mesures_du_niveau(niveau)
        for d in dimensions_du_niveau(niveau)
        if d.disponible_sur(m.base)
    )


def valider(cle_mesure: str, cle_dimension: str | None, niveau: Niveau) -> None:
    """Lève un message exploitable si le couple demandé n'a pas de sens."""
    m = mesure(cle_mesure)
    if not m.concerne(niveau):
        raise ValueError(
            f"La mesure {cle_mesure!r} n'est pas éligible au niveau {niveau.value}. "
            f"Éligibles : {', '.join(x.cle for x in mesures_du_niveau(niveau))}"
        )
    if cle_dimension is None:
        return
    d = dimension(cle_dimension)
    if not d.concerne(niveau):
        raise ValueError(
            f"La dimension {cle_dimension!r} n'est pas éligible au niveau {niveau.value}."
        )
    if not d.disponible_sur(m.base):
        raise ValueError(
            f"{cle_mesure!r} se calcule sur la table {m.base.value}, "
            f"où la dimension {cle_dimension!r} n'existe pas."
        )
