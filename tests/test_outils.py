"""Les outils d'exploration et le flux console, sans clé d'API.

C'est ici que se joue la testabilité du jalon 6. `reporting.py` est le seul
module à connaître `loom_ia`, et il est réduit à un câblage ; toute la substance
— validation des arguments, gardes de significativité, forme des réponses,
trace, arbitrage humain — vit dans des fonctions pures qu'on éprouve exactement
comme le modèle les appellera.

Ce que ces tests ne couvrent pas : le comportement du modèle lui-même. Aucun test
ne dira si l'agent formule de bonnes hypothèses. Cela ne se vérifie qu'en
exécution réelle, et c'est l'objet de la calibration.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from functools import cache
from pathlib import Path
import pytest

from loom_report_demo import app
from loom_report_demo.analysis import catalogue as cat
from loom_report_demo.analysis.chargement import Donnees, charger
from loom_report_demo.analysis.criblage import EFFECTIF_MINIMAL, cribler
from loom_report_demo.analysis.outils import (
    MAX_CELLULES_CROISEMENT,
    MAX_MODALITES,
    ErreurOutil,
    Registre,
    SpecOutil,
    construire_outils,
)
from loom_report_demo.niveaux import NIVEAUX, Niveau
from loom_report_demo.parsing import charger as charger_selection
from loom_report_demo.reporting import Exploration, construire_invite

FIXTURE = Path(__file__).parent / "fixtures" / "gestion.json"


@cache
def jeu() -> Donnees:
    return charger()


def outils(niveau: Niveau = Niveau.GESTION) -> tuple[dict[str, SpecOutil], Registre]:
    registre = Registre()
    specs = construire_outils(jeu(), niveau, registre)
    return {s.nom: s for s in specs}, registre


# ------------------------------------------------------------- les six outils
def test_les_six_outils_sont_fournis() -> None:
    boite, _ = outils()
    assert set(boite) == {
        "noter_hypothese",
        "ventilation",
        "serie_mensuelle",
        "comparer",
        "croiser",
        "concentration",
    }


@pytest.mark.parametrize("niveau", list(Niveau))
def test_chaque_outil_decrit_ce_quil_fait(niveau: Niveau) -> None:
    """La description dicte quand le modèle appellera l'outil : elle doit être utile."""
    boite, _ = outils(niveau)
    for spec in boite.values():
        assert len(spec.description) > 80, spec.nom
        assert spec.input_schema["type"] == "object"


@pytest.mark.parametrize("niveau", list(Niveau))
def test_les_enums_sont_bornes_au_niveau(niveau: Niveau) -> None:
    """Le niveau est capturé dans la fermeture : le modèle ne peut pas s'en échapper."""
    boite, _ = outils(niveau)
    admises = {m.cle for m in cat.mesures_du_niveau(niveau)}
    enum = set(boite["ventilation"].input_schema["properties"]["mesure"]["enum"])
    assert enum == admises


@pytest.mark.parametrize("niveau", list(Niveau))
def test_aucun_schema_nexpose_le_niveau(niveau: Niveau) -> None:
    boite, _ = outils(niveau)
    for spec in boite.values():
        assert "niveau" not in spec.input_schema["properties"], spec.nom


def test_la_ventilation_ordonne_du_plus_defavorable_au_plus_favorable() -> None:
    boite, _ = outils()
    haut = boite["ventilation"].fn(mesure="taux_transformation", dimension="tranche_relance")
    valeurs = [m["valeur"] for m in haut["modalites"]]
    assert valeurs == sorted(valeurs), "mesure « plus haut mieux » : ordre croissant"

    bas = boite["ventilation"].fn(mesure="taux_derive_horaire", dimension="agence")
    valeurs = [m["valeur"] for m in bas["modalites"]]
    assert valeurs == sorted(valeurs, reverse=True), "mesure « plus bas mieux » : ordre inverse"


def test_la_ventilation_signale_ce_quelle_ecarte() -> None:
    """Le modèle doit savoir qu'une modalité a été retirée, pas la découvrir absente."""
    boite, _ = outils()
    resultat = boite["ventilation"].fn(mesure="taux_marge_brute", dimension="prestation")
    assert "ecartees_effectif_insuffisant" in resultat
    assert resultat["seuil_effectif"] == EFFECTIF_MINIMAL[Niveau.GESTION]


def test_la_ventilation_borne_le_nombre_de_modalites() -> None:
    boite, _ = outils()
    resultat = boite["ventilation"].fn(mesure="ca_facture_ht", dimension="prestation")
    assert len(resultat["modalites"]) <= MAX_MODALITES


def test_la_serie_mensuelle_qualifie_la_tendance() -> None:
    boite, _ = outils()
    resultat = boite["serie_mensuelle"].fn(mesure="taux_marge_brute")
    assert resultat["tendance"] == "decroissante"
    assert 0.0 <= resultat["monotonie"] <= 1.0


def test_comparer_dit_qui_est_avantage() -> None:
    boite, _ = outils()
    resultat = boite["comparer"].fn(
        mesure="taux_marge_brute", dimension="agence",
        modalite_a="Montpellier", modalite_b="Bordeaux",
    )
    assert resultat["favorable_a"] is True
    assert resultat["ecart"] > 0


def test_croiser_ecarte_les_cellules_trop_peu_peuplees() -> None:
    boite, _ = outils()
    resultat = boite["croiser"].fn(
        mesure="taux_derive_horaire", dimension_1="agence",
        dimension_2="anciennete_technicien",
    )
    assert resultat["cellules_sous_le_seuil"] > 0
    assert all(c["effectif"] >= resultat["seuil_effectif"] for c in resultat["cellules"])


def test_concentration_rend_un_pareto_lisible() -> None:
    boite, _ = outils()
    resultat = boite["concentration"].fn(mesure="ca_facture_ht", dimension="prestation")
    cumuls = [p["cumul"] for p in resultat["paliers"]]
    assert cumuls == sorted(cumuls)
    assert cumuls[-1] >= 0.80
    assert resultat["modalites_pour_80_pct"] == len(resultat["paliers"])


# ------------------------------------------------------------- les refus
def test_une_mesure_hors_niveau_est_refusee() -> None:
    boite, _ = outils(Niveau.GESTION)
    with pytest.raises(ErreurOutil, match="pas éligible"):
        boite["ventilation"].fn(mesure="ca_par_technicien", dimension="agence")


def test_un_croisement_tautologique_est_refuse() -> None:
    boite, _ = outils()
    with pytest.raises(ErreurOutil, match="tautologique"):
        boite["ventilation"].fn(mesure="panier_moyen_gagne", dimension="tranche_montant")


def test_une_modalite_inventee_liste_les_admises() -> None:
    """Le message doit permettre au modèle de se corriger tout seul."""
    boite, _ = outils()
    with pytest.raises(ErreurOutil, match="Bordeaux, Montpellier, Toulouse"):
        boite["comparer"].fn(
            mesure="taux_marge_brute", dimension="agence",
            modalite_a="Lyon", modalite_b="Bordeaux",
        )


def test_comparer_refuse_deux_modalites_identiques() -> None:
    boite, _ = outils()
    with pytest.raises(ErreurOutil, match="identiques"):
        boite["comparer"].fn(
            mesure="taux_marge_brute", dimension="agence",
            modalite_a="Bordeaux", modalite_b="Bordeaux",
        )


def test_un_croisement_trop_large_est_refuse_avec_une_issue() -> None:
    boite, _ = outils()
    with pytest.raises(ErreurOutil, match="ventilation"):
        boite["croiser"].fn(
            mesure="ca_facture_ht", dimension_1="prestation", dimension_2="agence"
        )


def test_le_plafond_de_croisement_reste_raisonnable() -> None:
    assert 12 <= MAX_CELLULES_CROISEMENT <= 60


def test_croiser_refuse_deux_dimensions_identiques() -> None:
    boite, _ = outils()
    with pytest.raises(ErreurOutil, match="identiques"):
        boite["croiser"].fn(
            mesure="taux_marge_brute", dimension_1="agence", dimension_2="agence"
        )


def test_une_hypothese_en_double_est_refusee() -> None:
    boite, _ = outils()
    boite["noter_hypothese"].fn(
        identifiant="H1", enonce="Une piste", mesure_visee="taux_marge_brute",
    )
    with pytest.raises(ErreurOutil, match="déjà été notée"):
        boite["noter_hypothese"].fn(
            identifiant="H1", enonce="Une autre", mesure_visee="dso",
        )


def test_une_hypothese_vise_un_croisement_calculable() -> None:
    """Noter une hypothèse invérifiable serait un engagement en trompe-l'œil."""
    boite, _ = outils()
    with pytest.raises(ErreurOutil, match="commercial"):
        boite["noter_hypothese"].fn(
            identifiant="H9", enonce="La marge dépend du commercial",
            mesure_visee="taux_marge_brute", dimension_visee="commercial",
        )


# ------------------------------------------------------------------- la trace
def test_noter_hypothese_nexecute_aucun_calcul() -> None:
    """Coût nul : c'est ce qui permet d'imposer l'engagement avant le sondage."""
    boite, registre = outils()
    boite["noter_hypothese"].fn(
        identifiant="H1", enonce="Une piste", mesure_visee="taux_marge_brute",
    )
    assert registre.sondages == 0
    assert len(registre.appels) == 1


def test_le_registre_detecte_un_sondage_avant_toute_hypothese() -> None:
    boite, registre = outils()
    boite["ventilation"].fn(mesure="taux_marge_brute", dimension="agence")
    assert registre.notees_avant_sondage() is False


def test_le_registre_confirme_lengagement_prealable() -> None:
    boite, registre = outils()
    boite["noter_hypothese"].fn(
        identifiant="H1", enonce="Une piste", mesure_visee="taux_marge_brute",
    )
    boite["ventilation"].fn(mesure="taux_marge_brute", dimension="agence")
    assert registre.notees_avant_sondage() is True


def test_chaque_appel_porte_un_resume_lisible() -> None:
    boite, registre = outils()
    boite["ventilation"].fn(mesure="taux_transformation", dimension="tranche_relance")
    boite["serie_mensuelle"].fn(mesure="taux_marge_brute")
    boite["concentration"].fn(mesure="ca_facture_ht", dimension="agence")
    for appel in registre.appels:
        assert appel.resume and not appel.resume.endswith(" ")
        assert appel.duree_ms >= 0


def test_le_resume_de_ventilation_nomme_la_plus_defavorable() -> None:
    boite, registre = outils()
    boite["ventilation"].fn(mesure="taux_transformation", dimension="tranche_relance")
    assert "Jamais relancé" in registre.appels[-1].resume


# ------------------------------------------------------------------- l'invite
def test_linvite_livre_la_carte_et_les_candidats_sans_conclure() -> None:
    from loom_report_demo.analysis.profil import profil

    invite = construire_invite(
        Niveau.GESTION, profil(Niveau.GESTION, jeu()), cribler(jeu(), Niveau.GESTION)
    )
    assert "noter_hypothese" in invite
    assert "materialite_euros_an" in invite
    for mot in ("tu dois retenir", "le problème est", "il faut absolument"):
        assert mot not in invite.lower()


def test_linvite_rappelle_le_socle_impose() -> None:
    from loom_report_demo.analysis.profil import profil

    invite = construire_invite(
        Niveau.GESTION, profil(Niveau.GESTION, jeu()), cribler(jeu(), Niveau.GESTION)
    )
    for cle in NIVEAUX[Niveau.GESTION].socle:
        assert cle in invite


def test_linvite_interdit_les_chiffres_redigee() -> None:
    from loom_report_demo.analysis.profil import profil

    invite = construire_invite(
        Niveau.GESTION, profil(Niveau.GESTION, jeu()), cribler(jeu(), Niveau.GESTION)
    )
    assert "aucun chiffre" in invite.lower()


# ------------------------------------------------------------ le flux console
def _saisies(*reponses: str) -> app.Saisie:
    flux: Iterator[str] = iter(reponses)

    def _saisir(_invite: str) -> str:
        return next(flux)

    return _saisir


def _exploration() -> Exploration:
    registre = Registre()
    boite = {s.nom: s for s in construire_outils(jeu(), Niveau.GESTION, registre)}
    boite["noter_hypothese"].fn(
        identifiant="H1", enonce="La transformation dépend du délai de relance",
        mesure_visee="taux_transformation", dimension_visee="tranche_relance",
    )
    boite["ventilation"].fn(mesure="taux_transformation", dimension="tranche_relance")
    return Exploration(
        selection=charger_selection(FIXTURE),
        registre=registre,
        criblage=cribler(jeu(), Niveau.GESTION),
        brut="{}",
    )


async def _faux_explorateur(_niveau: Niveau) -> Exploration:
    return _exploration()


def test_le_retrait_dun_indicateur_produit_une_selection_plus_courte() -> None:
    selection = charger_selection(FIXTURE)
    reduite = selection.sans(1)
    assert len(reduite.variables) == len(selection.variables) - 1
    assert selection.variables[1] not in reduite.variables
    reduite.valider(strict=False)


def test_une_selection_amputee_est_refusee_en_mode_strict() -> None:
    with pytest.raises(ValueError, match="attend"):
        charger_selection(FIXTURE).sans(0).valider()


def test_un_retrait_hors_bornes_est_refuse() -> None:
    with pytest.raises(IndexError):
        charger_selection(FIXTURE).sans(9)


def test_arbitrer_accepte_la_selection_sur_entree_vide() -> None:
    selection = charger_selection(FIXTURE)
    retenue = app.arbitrer(selection, _saisies(""), lambda *a, **k: None)
    assert retenue is not None and len(retenue.variables) == 4


def test_arbitrer_retire_puis_genere() -> None:
    selection = charger_selection(FIXTURE)
    retenue = app.arbitrer(selection, _saisies("2", ""), lambda *a, **k: None)
    assert retenue is not None and len(retenue.variables) == 3


def test_arbitrer_annule_sur_q() -> None:
    assert app.arbitrer(charger_selection(FIXTURE), _saisies("q"), lambda *a, **k: None) is None


def test_arbitrer_redemande_apres_une_saisie_invalide() -> None:
    retenue = app.arbitrer(charger_selection(FIXTURE), _saisies("z", ""), lambda *a, **k: None)
    assert retenue is not None


def test_la_trace_montre_les_hypotheses_et_les_sondages(
    capsys: pytest.CaptureFixture[str],
) -> None:
    app.trace(_exploration(), print)
    rendu = capsys.readouterr().out
    assert "La transformation dépend du délai de relance" in rendu
    assert "ventilation" in rendu


def test_le_tableau_montre_les_hypotheses_ecartees(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Elles portent la moitié de la valeur du rapport."""
    app.tableau_selection(charger_selection(FIXTURE), print)
    rendu = capsys.readouterr().out
    assert "Hypothèses écartées" in rendu
    assert "Montpellier" in rendu


def test_le_flux_complet_produit_un_classeur(capsys: pytest.CaptureFixture[str]) -> None:
    code = asyncio.run(
        app.executer(saisir=_saisies("2", ""), explorateur=_faux_explorateur)
    )
    assert code == 0
    assert "Classeur" in capsys.readouterr().out


def test_le_flux_sarrete_proprement_si_lhumain_annule(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = asyncio.run(
        app.executer(saisir=_saisies("2", "q"), explorateur=_faux_explorateur)
    )
    assert code == 0
    assert "annulée" in capsys.readouterr().out


def test_une_exploration_en_echec_ne_plante_pas(capsys: pytest.CaptureFixture[str]) -> None:
    async def _echec(_niveau: Niveau) -> Exploration:
        raise RuntimeError("budget dépassé")

    code = asyncio.run(app.executer(saisir=_saisies("2"), explorateur=_echec))
    assert code == 1
    assert "budget dépassé" in capsys.readouterr().err


def test_le_flux_refuse_dexplorer_sans_cle(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Mieux vaut renvoyer vers la fixture que d'échouer au premier appel d'API."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("M3_API_KEY", raising=False)
    code = asyncio.run(app.executer(saisir=_saisies("2")))
    assert code == 1
    assert "uv run rapport" in capsys.readouterr().out
