"""Les gardes appliquées à la sortie du modèle.

Aucun jeton, aucun réseau, quelques millisecondes : ces cas tournent en
intégration continue à chaque commit. C'est le filet qui rend défendable la
promesse commerciale — *l'IA ne peut pas se tromper sur un chiffre, elle n'en
écrit aucun* — et une promesse non testée n'est qu'une intention.

Le jeu de départ est la fixture livrée avec le dépôt : chaque cas la dégrade sur
un point précis, ce qui garantit qu'un test échoue pour la raison annoncée et
non pour une autre.
"""

from __future__ import annotations

import copy
import json
from functools import cache
from pathlib import Path
from typing import Any

import pytest

from loom_report_demo.analysis import catalogue as cat
from loom_report_demo.niveaux import NIVEAUX, Niveau
from loom_report_demo.parsing import (
    CHAMPS_REDIGES,
    LONGUEUR_MAX_TEXTE,
    ErreurSortie,
    analyser,
    charger,
    extraire_json,
    garde_zero_chiffre,
    parse_selection,
)

FIXTURE = Path(__file__).parent / "fixtures" / "gestion.json"


@cache
def _reference() -> dict[str, Any]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def valide() -> dict[str, Any]:
    return copy.deepcopy(_reference())


# ---------------------------------------------------------------- la fixture
def test_la_fixture_livree_est_acceptee() -> None:
    selection = charger(FIXTURE)
    assert selection.niveau is Niveau.GESTION
    assert len(selection.variables) == NIVEAUX[Niveau.GESTION].nb_variables
    assert len(selection.ecartees) == 2


def test_la_fixture_ne_contient_aucun_chiffre_redige() -> None:
    """Elle sert de modèle au prompt : elle doit respecter la règle qu'elle illustre."""
    charge = _reference()
    textes = [charge["message_direction"]]
    textes += [h.get("enonce", "") for h in charge["hypotheses"]]
    textes += [h.get("motif", "") for h in charge["hypotheses"]]
    textes += [v["pourquoi"] for v in charge["variables"]]
    textes += [v["decision_attendue"] for v in charge["variables"]]
    for texte in textes:
        garde_zero_chiffre(texte, "fixture", "fixture")


def test_chaque_indicateur_retenu_est_calculable() -> None:
    for indicateur in charger(FIXTURE).variables:
        cat.valider(indicateur.mesure, indicateur.dimension, Niveau.GESTION)


# ------------------------------------------------------------- le décodage
def test_le_json_est_extrait_malgre_une_ligne_de_trace() -> None:
    """Le modèle préfixe volontiers sa réponse d'une trace."""
    brut = "Analyse terminée en quatre sondages.\n" + json.dumps(_reference())
    assert parse_selection(brut).niveau is Niveau.GESTION


def test_le_json_est_extrait_malgre_une_cloture_markdown() -> None:
    brut = "```json\n" + json.dumps(_reference()) + "\n```"
    assert parse_selection(brut).niveau is Niveau.GESTION


def test_une_accolade_dans_une_chaine_ne_trompe_pas_lextracteur() -> None:
    charge = valide()
    charge["message_direction"] = "Le levier tient au délai } de relance, sans réserve."
    brut = "trace\n" + json.dumps(charge) + "\nfin"
    assert parse_selection(brut).message_direction.endswith("sans réserve.")


def test_une_sortie_sans_json_est_refusee() -> None:
    with pytest.raises(ErreurSortie, match="Aucun objet JSON"):
        parse_selection("Je n'ai pas trouvé d'écart notable.")


def test_un_json_tronque_est_refuse() -> None:
    with pytest.raises(ErreurSortie, match="non refermé"):
        parse_selection('{"niveau": "gestion", "variables": [')


def test_un_json_malforme_est_refuse() -> None:
    with pytest.raises(ErreurSortie, match="JSON invalide"):
        parse_selection('{"niveau": "gestion",,}')


def test_une_liste_racine_est_refusee() -> None:
    with pytest.raises(ErreurSortie, match="objet"):
        extraire_json("[1, 2, 3]")


# ------------------------------------------------------ la garde zéro-chiffre
@pytest.mark.parametrize("champ", list(CHAMPS_REDIGES))
def test_la_garde_refuse_un_chiffre_dans_chaque_champ_redige(champ: str) -> None:
    with pytest.raises(ErreurSortie, match="ne portent aucune valeur"):
        garde_zero_chiffre("La marge recule de 8 points.", champ, "test")


def test_la_garde_accepte_une_quantite_en_toutes_lettres() -> None:
    garde_zero_chiffre("La marge recule de huit points sur la période.", "pourquoi", "test")


def test_la_garde_nomme_le_champ_et_montre_lextrait() -> None:
    with pytest.raises(ErreurSortie) as erreur:
        garde_zero_chiffre("Transformation à 22 pour cent.", "pourquoi", "indicateur #1")
    message = str(erreur.value)
    assert "pourquoi" in message
    assert "indicateur #1" in message
    assert "22" in message or "2" in message


def test_un_chiffre_dans_le_message_de_direction_est_refuse() -> None:
    charge = valide()
    charge["message_direction"] = "La transformation tombe à 22 pour cent sur la période."
    with pytest.raises(ErreurSortie, match="message_direction"):
        analyser(charge)


def test_un_chiffre_dans_un_pourquoi_est_refuse() -> None:
    charge = valide()
    charge["variables"][0]["pourquoi"] = "Le délai dépasse 3 jours dans la majorité des cas."
    with pytest.raises(ErreurSortie, match="pourquoi"):
        analyser(charge)


def test_un_chiffre_dans_une_decision_est_refuse() -> None:
    charge = valide()
    charge["variables"][1]["decision_attendue"] = "Ramener la marge au-dessus de 32 pour cent."
    with pytest.raises(ErreurSortie, match="decision_attendue"):
        analyser(charge)


def test_un_chiffre_dans_un_motif_decartement_est_refuse() -> None:
    charge = valide()
    charge["hypotheses"][-1]["motif"] = "Réfutée : l'écart ne dépasse pas 2 points."
    with pytest.raises(ErreurSortie, match="motif"):
        analyser(charge)


def test_le_seuil_dalerte_reste_autorise() -> None:
    """C'est le seul nombre admis : un seuil est un jugement, pas une mesure."""
    selection = charger(FIXTURE)
    seuils = [i.seuil_alerte for i in selection.variables]
    assert any(s is not None for s in seuils)


# --------------------------------------------------------- le seuil d'alerte
def test_un_taux_exprime_en_points_est_refuse() -> None:
    """`25` au lieu de `0.25` casserait silencieusement la mise en forme conditionnelle."""
    charge = valide()
    charge["variables"][0]["seuil_alerte"] = 25
    with pytest.raises(ErreurSortie, match="fraction"):
        analyser(charge)


def test_un_seuil_negatif_sur_une_duree_est_refuse() -> None:
    charge = valide()
    charge["variables"][3]["mesure"] = "encours_client"
    charge["variables"][3]["seuil_alerte"] = -100.0
    with pytest.raises(ErreurSortie, match="négatif"):
        analyser(charge)


def test_un_seuil_textuel_est_refuse() -> None:
    charge = valide()
    charge["variables"][0]["seuil_alerte"] = "vingt-cinq pour cent"
    with pytest.raises(ErreurSortie, match="nombre"):
        analyser(charge)


def test_un_seuil_absent_est_accepte() -> None:
    charge = valide()
    del charge["variables"][0]["seuil_alerte"]
    assert analyser(charge).variables[0].seuil_alerte is None


# ------------------------------------------------- la validation catalogue
def test_une_mesure_inventee_est_refusee() -> None:
    charge = valide()
    charge["variables"][0]["mesure"] = "taux_de_satisfaction"
    with pytest.raises(ErreurSortie, match="Mesure inconnue"):
        analyser(charge)


def test_une_dimension_inventee_est_refusee() -> None:
    charge = valide()
    charge["variables"][0]["dimension"] = "region"
    with pytest.raises(ErreurSortie, match="Dimension inconnue"):
        analyser(charge)


def test_une_mesure_hors_niveau_est_refusee() -> None:
    charge = valide()
    charge["variables"][0]["mesure"] = "ca_par_technicien"
    charge["variables"][0]["dimension"] = "agence"
    with pytest.raises(ErreurSortie, match="pas éligible"):
        analyser(charge)


def test_un_croisement_impossible_est_refuse() -> None:
    """La marge se constate sur une facture ; un commercial n'en émet pas."""
    charge = valide()
    charge["variables"][1]["mesure"] = "taux_marge_brute"
    charge["variables"][1]["dimension"] = "commercial"
    with pytest.raises(ErreurSortie, match="commercial"):
        analyser(charge)


def test_un_croisement_tautologique_est_refuse() -> None:
    charge = valide()
    charge["variables"][1]["mesure"] = "panier_moyen_gagne"
    charge["variables"][1]["dimension"] = "tranche_montant"
    with pytest.raises(ErreurSortie, match="tautologique"):
        analyser(charge)


def test_un_niveau_inconnu_est_refuse() -> None:
    charge = valide()
    charge["niveau"] = "tactique"
    with pytest.raises(ErreurSortie, match="Niveau inconnu"):
        analyser(charge)


# -------------------------------------------------------------- la forme
def test_une_cle_inventee_est_refusee() -> None:
    """Pendant du `extra: forbid` : une clé inconnue échoue bruyamment."""
    charge = valide()
    charge["confiance"] = 0.9
    with pytest.raises(ErreurSortie, match="clés inconnues"):
        analyser(charge)


def test_une_cle_inventee_dans_un_indicateur_est_refusee() -> None:
    charge = valide()
    charge["variables"][0]["priorite"] = 1
    with pytest.raises(ErreurSortie, match="clés inconnues"):
        analyser(charge)


def test_une_cle_manquante_est_refusee() -> None:
    charge = valide()
    del charge["variables"][0]["decision_attendue"]
    with pytest.raises(ErreurSortie, match="clés manquantes"):
        analyser(charge)


def test_un_texte_vide_est_refuse() -> None:
    charge = valide()
    charge["variables"][0]["pourquoi"] = "   "
    with pytest.raises(ErreurSortie, match="texte non vide"):
        analyser(charge)


def test_un_texte_trop_long_est_refuse() -> None:
    charge = valide()
    charge["variables"][0]["pourquoi"] = "Le délai pèse. " * 60
    with pytest.raises(ErreurSortie, match="dépasse"):
        analyser(charge)


def test_la_longueur_maximale_reste_raisonnable() -> None:
    assert 200 <= LONGUEUR_MAX_TEXTE <= 800


def test_un_nombre_dindicateurs_incorrect_est_refuse() -> None:
    charge = valide()
    charge["variables"] = charge["variables"][:2]
    with pytest.raises(ErreurSortie, match="attend 4 indicateurs"):
        analyser(charge)


def test_un_indicateur_en_double_est_refuse() -> None:
    charge = valide()
    charge["variables"][1] = copy.deepcopy(charge["variables"][0])
    charge["variables"][1]["hypothese_source"] = "H2"
    with pytest.raises(ErreurSortie, match="double"):
        analyser(charge)


# --------------------------------------------------- l'invariant des hypothèses
def test_une_hypothese_retenue_sans_indicateur_est_refusee() -> None:
    """Elle signale un raisonnement réécrit après coup."""
    charge = valide()
    charge["hypotheses"].append(
        {"identifiant": "H7", "enonce": "Le canal d'acquisition pèse sur la marge",
         "statut": "retenue"}
    )
    with pytest.raises(ErreurSortie, match="sans indicateur"):
        analyser(charge)


def test_un_indicateur_sans_hypothese_notee_est_refuse() -> None:
    charge = valide()
    charge["variables"][0]["hypothese_source"] = "H9"
    with pytest.raises(ErreurSortie, match="jamais notées"):
        analyser(charge)


def test_un_indicateur_adosse_a_une_hypothese_ecartee_est_refuse() -> None:
    """On ne retient pas un indicateur issu d'une piste qu'on a déclarée réfutée."""
    charge = valide()
    charge["variables"][0]["hypothese_source"] = "H5"
    with pytest.raises(ErreurSortie, match="écartées"):
        analyser(charge)


def test_une_hypothese_ecartee_sans_motif_est_refusee() -> None:
    charge = valide()
    del charge["hypotheses"][-1]["motif"]
    with pytest.raises(ErreurSortie, match="motif"):
        analyser(charge)


def test_un_statut_inconnu_est_refuse() -> None:
    charge = valide()
    charge["hypotheses"][0]["statut"] = "probable"
    with pytest.raises(ErreurSortie, match="statut"):
        analyser(charge)


def test_deux_hypotheses_de_meme_identifiant_sont_refusees() -> None:
    charge = valide()
    charge["hypotheses"][1]["identifiant"] = "H1"
    with pytest.raises(ErreurSortie, match="identifiant"):
        analyser(charge)


def test_une_liste_dhypotheses_vide_est_refusee() -> None:
    charge = valide()
    charge["hypotheses"] = []
    with pytest.raises(ErreurSortie, match="non vide"):
        analyser(charge)


def test_les_hypotheses_ecartees_sont_transmises_au_classeur() -> None:
    """Elles portent la moitié de la valeur du rapport."""
    selection = charger(FIXTURE)
    identifiants = {h.identifiant for h in selection.ecartees}
    assert identifiants == {"H5", "H6"}
    assert all(h.motif for h in selection.ecartees)


# ------------------------------------------------ cohérence avec settings.json
def _configuration() -> dict[str, Any]:
    from loom_report_demo import paths

    return json.loads(paths.settings().read_text(encoding="utf-8"))


def _role_selection() -> dict[str, Any]:
    """Le rôle qui porte le contrat de sortie.

    Depuis la calibration, c'est l'orchestrateur lui-même : celui qui juge est
    celui qui rédige, et le contrat est vérifié là où le jugement se forme.
    """
    roles = {r["name"]: r for r in _configuration()["roles"]}
    assert "main" in roles, "le rôle 'main' doit exister"
    return roles["main"]


def test_le_role_selection_declare_un_schema_de_sortie() -> None:
    sortie = _role_selection()["output"]
    assert sortie["schema"]["additionalProperties"] is False
    assert sortie["repair_attempts"] >= 1
    assert sortie["must_not_match"] == "```"


def test_le_schema_de_sortie_enumere_les_mesures_du_catalogue() -> None:
    """Un `enum` fermé : le modèle ne peut pas inventer une clé."""
    schema = _role_selection()["output"]["schema"]
    mesures = schema["properties"]["variables"]["items"]["properties"]["mesure"]["enum"]
    assert set(mesures) == set(cat.MESURES)


def test_le_schema_de_sortie_enumere_les_dimensions_du_catalogue() -> None:
    schema = _role_selection()["output"]["schema"]
    dimensions = schema["properties"]["variables"]["items"]["properties"]["dimension"]["enum"]
    assert set(dimensions) == set(cat.DIMENSIONS) | {None}


def test_le_role_selection_na_pas_de_thinking() -> None:
    """Un rôle à `output.schema` est incompatible avec le raisonnement étendu.

    C'est le prix de la fusion orchestrateur / rédacteur, et il est assumé.
    """
    modeles = {m["id"]: m for m in _configuration()["llm"]}
    porteur = modeles[_role_selection()["llm"]]
    assert "thinking" not in porteur.get("params", {})


def test_le_role_selection_a_de_quoi_ecrire_le_json() -> None:
    modeles = {m["id"]: m for m in _configuration()["llm"]}
    assert modeles[_role_selection()["llm"]]["max_tokens"] >= 4096


def test_le_juge_porte_deux_criteres_bloquants() -> None:
    criteres = {c["name"]: c["min_score"] for c in _role_selection()["judge"]["criteria"]}
    assert criteres["actionnabilite"] >= 0.7
    assert criteres["non_redondance"] >= 0.7
    assert criteres["qualite_motifs"] < 0.5


def test_la_consigne_systeme_enonce_la_regle_zero_chiffre() -> None:
    consigne = _role_selection()["system"].lower()
    assert "aucun chiffre" in consigne
    assert "seuil_alerte" in consigne


def test_la_longueur_maximale_du_schema_suit_celle_du_parsing() -> None:
    schema = _role_selection()["output"]["schema"]
    borne = schema["properties"]["variables"]["items"]["properties"]["pourquoi"]["maxLength"]
    assert borne == LONGUEUR_MAX_TEXTE


# ------------------------------------------- renvois entre hypothèses
# Cas rapporté par la première exécution réelle : le modèle écrit « …confirmant
# H3 », un renvoi à une hypothèse et non une valeur. La garde le refusait, ce qui
# revenait à lui interdire de raisonner d'une piste à l'autre.
def test_un_renvoi_a_une_hypothese_declaree_est_admis() -> None:
    charge = valide()
    charge["hypotheses"][-1]["motif"] = "Réfutée : l'écart va dans l'autre sens, confirmant H1."
    assert analyser(charge).ecartees[-1].motif.endswith("confirmant H1.")


def test_un_renvoi_dans_le_message_de_direction_est_admis() -> None:
    charge = valide()
    charge["message_direction"] = "Le premier levier est celui de l'hypothèse H1."
    assert analyser(charge).message_direction.endswith("H1.")


def test_un_renvoi_dans_un_pourquoi_est_admis() -> None:
    charge = valide()
    charge["variables"][0]["pourquoi"] = "La piste H1 se confirme sur toute la période."
    assert analyser(charge).variables[0].pourquoi.startswith("La piste H1")


def test_un_renvoi_a_une_hypothese_inexistante_reste_refuse() -> None:
    """Sinon la garde deviendrait un trou : « H9 » ferait passer n'importe quoi."""
    charge = valide()
    charge["hypotheses"][-1]["motif"] = "Réfutée, confirmant H9."
    with pytest.raises(ErreurSortie, match="chiffre"):
        analyser(charge)


def test_une_quantite_reste_refusee_malgre_les_renvois() -> None:
    with pytest.raises(ErreurSortie, match="chiffre"):
        garde_zero_chiffre("La marge recule de 8 points.", "motif", "test", {"H1", "H8"})


def test_les_identifiants_les_plus_longs_sont_retires_en_premier() -> None:
    """Sans tri par longueur, retirer « H1 » de « H12 » y laisserait un « 2 »."""
    garde_zero_chiffre("Confirmé par H12.", "motif", "test", {"H1", "H12"})


# ------------------------------------ l'enveloppe attendue par le rôle
# Le modèle avait écrit 'indicateurs' au lieu de 'variables', et omis deux clés.
# En relisant la consigne, elle décrivait les règles sans jamais montrer la forme.
def test_la_consigne_montre_lenveloppe_complete() -> None:
    consigne = _role_selection()["system"]
    for cle in ("niveau", "message_direction", "hypotheses", "variables"):
        assert f'"{cle}"' in consigne, f"la consigne ne nomme pas {cle!r}"


def test_la_consigne_ecarte_les_noms_voisins() -> None:
    """« indicateurs », « kpis » : les noms qu'un modèle invente naturellement."""
    consigne = _role_selection()["system"].lower()
    assert "pas 'indicateurs'" in consigne


def test_la_consigne_autorise_les_renvois_entre_hypotheses() -> None:
    assert "confirmant H3" in _role_selection()["system"]


def test_le_role_repare_plus_dune_fois() -> None:
    """Une seule tentative suffit rarement sur une erreur de forme."""
    assert _role_selection()["output"]["repair_attempts"] >= 2
