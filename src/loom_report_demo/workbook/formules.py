"""Génération des formules Excel : colonnes calculées et gabarits de mesure.

Deux responsabilités.

**Les colonnes calculées** reproduisent en formules ce que `chargement.py`
construit en pandas. Les seuils de tranches sont importés de ce module : une
seule source de vérité, sinon les deux définitions divergent au premier
ajustement.

**Les gabarits de mesure** traduisent l'algèbre du catalogue en `SUMIFS`. Le
principe qui tient tout l'édifice y survit : numérateur et dénominateur sont
agrégés séparément, la division vient en dernier. Une formule qui moyennerait
des taux serait fausse, et le classeur est précisément l'endroit où l'erreur
serait invisible.

Aucune valeur n'est figée. Les bornes de fenêtre sont des formules dérivées de la
date de situation, elle-même saisissable : modifier cette cellule recalcule le
rapport entier.
"""

from __future__ import annotations

from loom_report_demo.analysis import catalogue as cat
from loom_report_demo.analysis.chargement import (
    ANCIENNETE_HAUTE,
    JAMAIS_RELANCE,
    REGLEE,
    TRANCHE_AGE_HAUTE,
    TRANCHE_MONTANT_HAUTE,
    TRANCHE_RELANCE_HAUTE,
    TRANCHES_AGE,
    TRANCHES_ANCIENNETE,
    TRANCHES_MONTANT,
    TRANCHES_RELANCE,
)
from loom_report_demo.workbook.schema import ColonneCalculee, Schema
from loom_report_demo.workbook.theme import EUR, NB, NB1, PCT

#: Cellules de la feuille Paramètres, référencées par toutes les formules.
#: Les cinq premières lignes portent le bandeau : les paramètres commencent en 8.
LIGNE_SITUATION = 8
SITUATION = "Paramètres!$C$8"
DEBUT = "Paramètres!$C$9"
FIN = "Paramètres!$C$10"
DEBUT_COMPARAISON = "Paramètres!$C$11"
FIN_COMPARAISON = "Paramètres!$C$12"
SEUIL_EXCEPTION = "Paramètres!$C$13"
SEUIL_RELANCE = "Paramètres!$C$14"


def _tranches_imbriquees(
    champ: str, seuils: tuple[tuple[float, str], ...], haute: str
) -> str:
    """`IF` imbriqués plutôt que `IFS` : compatible avec toutes les versions."""
    sortie = f'"{haute}"'
    for borne, libelle in reversed(seuils):
        sortie = f'IF({champ}<={borne},"{libelle}",{sortie})'
    return sortie


COLONNES_CALCULEES: dict[str, tuple[ColonneCalculee, ...]] = {
    "Devis": (
        ColonneCalculee("metier", "Métier", "={categorie}{r}", None, 14),
        ColonneCalculee("prestation", "Prestation", "={libelle_prestation}{r}", None, 30),
        ColonneCalculee(
            "canal_acquisition",
            "Canal d'acquisition",
            '=IFERROR(INDEX({cl_canal},MATCH({client_id}{r},{cl_id},0)),"")',
            None,
            18,
        ),
        ColonneCalculee(
            "profil_paiement",
            "Profil de paiement",
            '=IFERROR(INDEX({cl_profil},MATCH({client_id}{r},{cl_id},0)),"")',
            None,
            16,
        ),
        ColonneCalculee("ligne", "Ligne", "=1", NB, 8),
        ColonneCalculee("est_gagne", "Gagné", '=IF({statut}{r}="Accepté",1,0)', NB, 9),
        ColonneCalculee(
            "ca_gagne", "CA gagné HT", "={montant_ht}{r}*{est_gagne}{r}", EUR, 14
        ),
        ColonneCalculee(
            "montant_arbitre",
            "Montant arbitré HT",
            '=IF({statut}{r}="En cours",0,{montant_ht}{r})',
            EUR,
            16,
        ),
        ColonneCalculee(
            "est_relance", "Relancé", '=IF({delai_1ere_relance_j}{r}="",0,1)', NB, 9
        ),
        ColonneCalculee(
            "delai_relance_pondere",
            "Délai relance pondéré",
            '=IF({delai_1ere_relance_j}{r}="",0,{delai_1ere_relance_j}{r})',
            NB1,
            15,
        ),
        ColonneCalculee(
            "relance_rapide",
            "Relance sous seuil",
            '=IF(AND({delai_1ere_relance_j}{r}<>"",'
            "{delai_1ere_relance_j}{r}<=" + SEUIL_RELANCE + "),1,0)",
            NB,
            13,
        ),
        ColonneCalculee(
            "tranche_relance",
            "Tranche de relance",
            '=IF({delai_1ere_relance_j}{r}="","' + JAMAIS_RELANCE + '",'
            + _tranches_imbriquees(
                "{delai_1ere_relance_j}{r}", TRANCHES_RELANCE, TRANCHE_RELANCE_HAUTE
            )
            + ")",
            None,
            17,
        ),
        ColonneCalculee(
            "tranche_montant",
            "Tranche de montant",
            "="
            + _tranches_imbriquees("{montant_ht}{r}", TRANCHES_MONTANT, TRANCHE_MONTANT_HAUTE),
            None,
            16,
        ),
    ),
    "Factures": (
        ColonneCalculee(
            "metier",
            "Métier",
            '=IFERROR(INDEX({dv_categorie},MATCH({devis_id}{r},{dv_id},0)),"")',
            None,
            14,
        ),
        ColonneCalculee(
            "prestation",
            "Prestation",
            '=IFERROR(INDEX({dv_libelle},MATCH({devis_id}{r},{dv_id},0)),"")',
            None,
            30,
        ),
        ColonneCalculee(
            "canal_acquisition",
            "Canal d'acquisition",
            '=IFERROR(INDEX({cl_canal},MATCH({client_id}{r},{cl_id},0)),"")',
            None,
            18,
        ),
        ColonneCalculee("ligne", "Ligne", "=1", NB, 8),
        ColonneCalculee(
            "cout_revient",
            "Coût de revient",
            "=IFERROR(INDEX({in_cout},MATCH({devis_id}{r},{in_devis},0)),0)",
            EUR,
            15,
        ),
        ColonneCalculee(
            "marge", "Marge brute", "={montant_ht}{r}-{cout_revient}{r}", EUR, 14
        ),
        ColonneCalculee("est_payee", "Réglée", '=IF({date_paiement}{r}="",0,1)', NB, 9),
        ColonneCalculee(
            "encours",
            "Encours TTC",
            '=IF({date_paiement}{r}="",{montant_ttc}{r},0)',
            EUR,
            14,
        ),
        ColonneCalculee(
            "retard",
            "Retard (j)",
            '=IF({date_paiement}{r}="",MAX(0,'
            + SITUATION
            + "-{date_echeance}{r}),MAX(0,{date_paiement}{r}-{date_echeance}{r}))",
            NB,
            11,
        ),
        ColonneCalculee(
            "retard_pondere", "Retard pondéré", "={retard}{r}*{encours}{r}", NB, 14
        ),
        ColonneCalculee(
            "delai_reel_pondere",
            "Délai réel (j)",
            '=IF({date_paiement}{r}="",0,{date_paiement}{r}-{date_facture}{r})',
            NB,
            13,
        ),
        ColonneCalculee(
            "en_retard",
            "En retard",
            '=IF(AND({date_paiement}{r}="",{date_echeance}{r}<' + SITUATION + "),1,0)",
            NB,
            10,
        ),
        ColonneCalculee(
            "exception",
            "Exception",
            '=IF(AND({date_paiement}{r}="",{retard}{r}>' + SEUIL_EXCEPTION + "),1,0)",
            NB,
            10,
        ),
        ColonneCalculee(
            "mois_encaissement",
            "Mois d'encaissement",
            '=IF({date_paiement}{r}="","",YEAR({date_paiement}{r})&"-"'
            '&TEXT(MONTH({date_paiement}{r}),"00"))',
            None,
            16,
        ),
        ColonneCalculee(
            "tranche_age_creance",
            "Ancienneté de créance",
            '=IF({est_payee}{r}=1,"' + REGLEE + '",'
            + _tranches_imbriquees("{retard}{r}", TRANCHES_AGE, TRANCHE_AGE_HAUTE)
            + ")",
            None,
            18,
        ),
        ColonneCalculee(
            "tranche_montant",
            "Tranche de montant",
            "="
            + _tranches_imbriquees("{montant_ht}{r}", TRANCHES_MONTANT, TRANCHE_MONTANT_HAUTE),
            None,
            16,
        ),
    ),
    "Interventions": (
        ColonneCalculee("metier", "Métier", "={categorie}{r}", None, 14),
        ColonneCalculee("ligne", "Ligne", "=1", NB, 8),
        ColonneCalculee(
            "ca_lie",
            "CA HT lié",
            "=IFERROR(INDEX({dv_montant},MATCH({devis_id}{r},{dv_id},0)),0)",
            EUR,
            14,
        ),
        ColonneCalculee(
            "cout_total", "Coût total", "={cout_main_oeuvre}{r}+{cout_materiel}{r}", EUR, 14
        ),
        ColonneCalculee("marge", "Marge brute", "={ca_lie}{r}-{cout_total}{r}", EUR, 14),
        ColonneCalculee(
            "anciennete_technicien",
            "Ancienneté du technicien",
            "=IFERROR("
            + _tranches_imbriquees(
                "({date_intervention}{r}-INDEX({te_embauche},"
                "MATCH({technicien_id}{r},{te_id},0)))",
                TRANCHES_ANCIENNETE,
                ANCIENNETE_HAUTE,
            )
            + ',"")',
            None,
            20,
        ),
    ),
    "Relances": (),
    "Clients": (),
    "Techniciens": (),
    "Catalogue": (),
}


def substitutions_globales(schemas: dict[str, Schema]) -> dict[str, str]:
    """Plages inter-feuilles utilisées par les colonnes calculées."""
    devis, factures, clients, interventions, techniciens = (
        schemas["Devis"],
        schemas["Factures"],
        schemas["Clients"],
        schemas["Interventions"],
        schemas["Techniciens"],
    )
    return {
        "cl_id": clients.plage("client_id"),
        "cl_canal": clients.plage("canal_acquisition"),
        "cl_profil": clients.plage("profil_paiement"),
        "dv_id": devis.plage("devis_id"),
        "dv_montant": devis.plage("montant_ht"),
        "dv_categorie": devis.plage("categorie"),
        "dv_libelle": devis.plage("libelle_prestation"),
        "in_devis": interventions.plage("devis_id"),
        "in_cout": interventions.plage("cout_total"),
        "te_id": techniciens.plage("technicien_id"),
        "te_embauche": techniciens.plage("date_embauche"),
        "fa_montant": factures.plage("montant_ht"),
    }


# ------------------------------------------------------------ mesures
def _sumifs(plage: str, criteres: list[tuple[str, str]]) -> str:
    morceaux = [plage] + [f"{p},{c}" for p, c in criteres]
    return f"SUMIFS({','.join(morceaux)})"


def _criteres(
    schema: Schema,
    colonne_date: str,
    debut: str,
    fin: str,
    dimension: tuple[str, str] | None = None,
) -> list[tuple[str, str]]:
    plage_date = schema.plage(colonne_date)
    criteres = [(plage_date, f'">="&{debut}'), (plage_date, f'"<="&{fin}')]
    if dimension is not None:
        champ, valeur = dimension
        criteres.append((schema.plage(champ), valeur))
    return criteres


def formule_mesure(
    mesure: cat.Mesure,
    schema: Schema,
    colonne_date: str,
    debut: str = DEBUT,
    fin: str = FIN,
    dimension: tuple[str, str] | None = None,
) -> str:
    """Formule d'une mesure sur une fenêtre, éventuellement pour une modalité.

    Les mesures à dénominateur distinct et les mesures spéciales n'ont pas de
    traduction directe en `SUMIFS` ; elles arrivent avec les niveaux stratégique
    et opérationnel, au jalon 7.
    """
    if mesure.special is not None:
        raise NotImplementedError(
            f"{mesure.cle} : mesure spéciale, sans gabarit Excel (jalon 7)."
        )
    agregat = mesure.agregat
    assert agregat is not None
    if agregat.distinct is not None:
        raise NotImplementedError(
            f"{mesure.cle} : dénominateur en valeurs distinctes, sans gabarit Excel (jalon 7)."
        )

    criteres = _criteres(schema, colonne_date, debut, fin, dimension)
    numerateur = _sumifs(schema.plage(agregat.numerateur), criteres)

    if agregat.denominateur is None:
        corps = numerateur
        if agregat.facteur != 1.0:
            corps = f"{agregat.facteur}*{corps}"
        if agregat.decalage:
            corps = f"{corps}{agregat.decalage:+}"
        return f"={corps}"

    denominateur = _sumifs(schema.plage(agregat.denominateur), criteres)
    corps = f"{numerateur}/{denominateur}"
    if agregat.facteur != 1.0:
        corps = f"{agregat.facteur}*({corps})"
    if agregat.decalage:
        corps = f"{corps}{agregat.decalage:+}"
    return f'=IFERROR({corps},"")'


def formule_effectif(
    schema: Schema,
    colonne_date: str,
    debut: str = DEBUT,
    fin: str = FIN,
    dimension: tuple[str, str] | None = None,
) -> str:
    """Nombre de lignes couvertes, pour juger de la solidité d'une valeur."""
    criteres = _criteres(schema, colonne_date, debut, fin, dimension)
    morceaux = [f"{p},{c}" for p, c in criteres]
    return f"=COUNTIFS({','.join(morceaux)})"


def formule_variation(cellule_actuelle: str, cellule_passee: str) -> str:
    return f'=IFERROR({cellule_actuelle}/{cellule_passee}-1,"")'


def formule_ecart_points(cellule_actuelle: str, cellule_passee: str) -> str:
    """Écart en points, pour deux valeurs déjà exprimées en pourcentage."""
    return f'=IFERROR(({cellule_actuelle}-{cellule_passee})*100,"")'


def format_unite(mesure: cat.Mesure) -> str:
    return {"€": EUR, "%": PCT, "j": "#,##0 \" j\";-#,##0 \" j\";\"–\"", "h": NB1}.get(
        mesure.unite.value, NB
    )
