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


#: Colonnes d'appui du niveau stratégique. Elles n'existent que pour deux mesures
#: — le chiffre d'affaires par technicien et la concentration client — dont le
#: dénominateur n'est pas une somme. Les plages sont *expansives* (`$F$2:$F{r}`) :
#: chaque ligne ne regarde que celles qui la précèdent, ce qui marque la première
#: occurrence d'un technicien dans la fenêtre sans coûter un balayage complet.
def _premiere_occurrence(debut: str, fin: str) -> str:
    """Marque la première intervention de chaque technicien dans une fenêtre.

    Les plages sont *expansives* — `{technicien_id}$2:{technicien_id}{r}` — donc
    chaque ligne ne regarde que celles qui la précèdent. La somme de la colonne
    vaut alors le nombre de techniciens distincts ayant travaillé sur la période,
    et le décompte de valeurs distinctes redevient une simple `SUMIFS`.
    """
    tech = "{technicien_id}"
    date = "{date_intervention}"
    return (
        f"=IF(AND({date}{{r}}>={debut},{date}{{r}}<={fin},"
        f"COUNTIFS({tech}$2:{tech}{{r}},{tech}{{r}},"
        f'{date}$2:{date}{{r}},">="&{debut},'
        f'{date}$2:{date}{{r}},"<="&{fin})=1),1,0)'
    )


def _ca_client(debut: str, fin: str) -> str:
    """Chiffre d'affaires d'un client sur une fenêtre, pour la concentration."""
    return (
        "=SUMIFS({fa_montant},{fa_client},{client_id}{r},"
        f'{{fa_date}},">="&{debut},{{fa_date}},"<="&{fin})'
    )


COLONNES_STRATEGIQUES: dict[str, tuple[ColonneCalculee, ...]] = {
    "Interventions": (
        ColonneCalculee(
            "technicien_nouveau",
            "Technicien actif (fenêtre)",
            _premiere_occurrence(DEBUT, FIN),
            NB,
            18,
        ),
        ColonneCalculee(
            "technicien_nouveau_comparaison",
            "Technicien actif (comparaison)",
            _premiere_occurrence(DEBUT_COMPARAISON, FIN_COMPARAISON),
            NB,
            20,
        ),
    ),
    "Clients": (
        ColonneCalculee("ca_fenetre", "CA de la fenêtre", _ca_client(DEBUT, FIN), EUR, 16),
        ColonneCalculee(
            "ca_fenetre_comparaison",
            "CA de la comparaison",
            _ca_client(DEBUT_COMPARAISON, FIN_COMPARAISON),
            EUR,
            18,
        ),
    ),
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
        "fa_client": factures.plage("client_id"),
        "fa_date": factures.plage("date_facture"),
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
    schemas: dict[str, Schema] | None = None,
) -> str:
    """Formule d'une mesure sur une fenêtre, éventuellement pour une modalité.

    `schemas` n'est requis que pour la concentration client, dont la colonne
    d'appui vit sur une autre feuille que la table de faits.

    Les mesures à dénominateur distinct et les mesures spéciales n'ont pas de
    traduction directe en `SUMIFS` ; elles arrivent avec les niveaux stratégique
    et opérationnel, au jalon 7.
    """
    if dimension is not None and not mesure.ventilable:
        raise ValueError(f"{mesure.cle} ne se ventile pas : son dénominateur n'est pas additif.")
    if mesure.special is not None:
        if schemas is None:
            raise ValueError(
                f"{mesure.cle} : cette mesure a besoin de l'ensemble des schémas."
            )
        return _formule_speciale(mesure, schemas["Clients"], debut)
    agregat = mesure.agregat
    assert agregat is not None
    if agregat.distinct is not None:
        return _formule_par_effectif(mesure, agregat, schema, colonne_date, debut, fin)

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


def _formule_par_effectif(
    mesure: cat.Mesure,
    agregat: cat.Agregat,
    schema: Schema,
    colonne_date: str,
    debut: str,
    fin: str,
) -> str:
    """Rapport dont le dénominateur est un décompte de valeurs distinctes.

    Excel ne sait pas compter des valeurs distinctes sous critère. On somme donc
    une colonne d'appui qui vaut 1 sur la première occurrence de chaque
    technicien dans la fenêtre, et 0 partout ailleurs : le décompte redevient une
    somme, et le classeur reste vivant.
    """
    colonne = (
        "technicien_nouveau" if debut == DEBUT else "technicien_nouveau_comparaison"
    )
    criteres = _criteres(schema, colonne_date, debut, fin)
    numerateur = _sumifs(schema.plage(agregat.numerateur), criteres)
    denominateur = _sumifs(schema.plage(colonne), criteres)
    corps = f"{numerateur}/{denominateur}"
    if agregat.facteur != 1.0:
        corps = f"{agregat.facteur}*({corps})"
    return f'=IFERROR({corps},"")'


def _formule_speciale(mesure: cat.Mesure, schema: Schema, debut: str) -> str:
    """Concentration : part du total portée par le décile supérieur.

    `LARGE` donne le seuil du décile, `SUMIF` ce qui est au-dessus. Une égalité
    exacte au seuil ferait basculer un client de plus dans le décile ; sur des
    montants en euros, le cas ne se présente pas.
    """
    if mesure.special != "concentration_client":
        raise NotImplementedError(f"{mesure.cle} : mesure spéciale sans gabarit Excel.")
    colonne = "ca_fenetre" if debut == DEBUT else "ca_fenetre_comparaison"
    plage = schema.plage(colonne)
    rang = f'MAX(1,ROUND(COUNTIF({plage},">0")*0.1,0))'
    seuil = f"LARGE({plage},{rang})"
    return f'=IFERROR(SUMIF({plage},">="&{seuil})/SUM({plage}),"")'


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
    return {"€": EUR, "%": PCT, "j": "#,##0 \" j\";-#,##0 \" j\";\"-\"", "h": NB1}.get(
        mesure.unite.value, NB
    )
