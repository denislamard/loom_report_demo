# Feuille de route

Chaque jalon porte un critère de sortie mécaniquement vérifiable : on lance la
commande, c'est vert ou ce n'est pas fini. Les jalons 0 à 5 ne consomment aucun
jeton.

| # | Jalon | Critère de sortie | Charge | LLM | État |
|---|---|---|---|---|---|
| 0 | Squelette | `uv run app` affiche le menu, `pyright` propre | S | — | **fait** |
| 1 | Jeu de données | `uv run seed` reproductible au hash près | S | — | **fait** |
| 2 | Catalogue | `uv run profil --niveau gestion` sort le profil | M | — | **fait** |
| 3 | Criblage | `uv run candidats` liste les 12 meilleurs, scorés | M | — | **fait** |
| 4 | Classeur gestion | `uv run rapport --selection fixtures/gestion.json` | L | — | **fait** |
| 5 | Contrat et gardes | ~25 tests de parsing, zéro jeton | M | — | **fait** |
| 6 | L'agent | `uv run app` de bout en bout | M | oui | **écrit, non éprouvé** |
| 7 | Niveau stratégique | menu 1 opérationnel, sélection gelée | M | oui | **fait** |
| 8 | Niveau opérationnel | menu 3 + export JSON `agent-pro` | M | oui | **fait** |

---

## Jalon 0 — Squelette *(fait)*

Greffé sur le squelette existant : `run()` et l'import différé de `app` sont
conservés tels quels, `entry()` reste asynchrone. Ajout de `paths.py` sans
dépendance, `niveaux.py` qui porte le type de domaine, le menu et la saisie
injectée dans `app.py`, un `.gitignore` et un `.env.example`.

`files/settings.json` conserve tous les blocs d'infrastructure d'origine — `llm`
avec leur `pricing` et `context_window`, `memory` avec sa compaction, `usage`,
`budget`, `tools`, `metrics`. Seuls les rôles changent : `etat_des_lieux`
appartenait à la démonstration précédente.

**Vérification bloquante levée** : `pandas` publie des wheels `cp314` depuis la
2.3.3, et la 3.0.5 les fournit sur toutes les plateformes. `openpyxl` est pur
Python. Le repli DuckDB envisagé n'est pas nécessaire.

52 tests, sans clé d'API.

## Jalon 1 — Jeu de données *(fait)*

Générateur porté en trois modules : `lignes.py` porte le contrat de données
(une `TypedDict` par table), `parametres.py` les constantes métier et la
trajectoire, `generateur.py` la production. `fingerprint.py` calcule un SHA-256
par fichier plus une empreinte d'ensemble, invariante par ordre de parcours.

Le portage est **fidèle à l'octet près** : les CSV produits par le nouveau code
étaient identiques à ceux livrés au jalon précédent. Cette propriété tient à
l'ordre exact des appels au générateur aléatoire, y compris les court-circuits
(`profil == "Litigieux" and rng.random() < …`), et c'est ce que verrouille
l'empreinte de référence figée dans les tests.

**Un défaut trouvé par les tests** : trois devis émis le dernier jour de la
période portaient une date de décision antérieure à leur émission, le
plafonnement à la date de situation les ramenant à la veille. Corrigé, sans
effet sur les interventions ni les factures.

69 tests : reproductibilité, intégrité référentielle, cohérence temporelle,
cohérence des valeurs calculées, et la trajectoire d'entreprise elle-même —
marge décroissante, discipline de relance qui se dégrade, Montpellier qui ne
cannibalise pas Toulouse.

## Jalon 2 — Catalogue et moteur *(fait)*

Dix-neuf mesures et douze dimensions, chacune portant son attribut `niveau`, et
le moteur qui calcule n'importe quel `(mesure, dimension, cadrage, filtre)`.
Plus le profil de reconnaissance remis à l'agent, et `uv run profil`.

L'algèbre des agrégats est volontairement pauvre — `facteur × num / den +
décalage` — mais elle couvre dix-huit mesures sur dix-neuf, la concentration
client étant la seule à passer par un registre fermé de fonctions spéciales.
Numérateurs et dénominateurs sont sommés séparément puis divisés en dernier : la
moyenne de trois taux de marge n'est pas le taux de marge de trois agences.

**Deux garde-fous nés de l'exécution.** Le catalogue distingue les mesures de
*flux* des mesures de *stock* : comparer un encours entre deux fenêtres
produisait un écart de +2 340 %, puisque les factures de l'an dernier ont été
réglées depuis. Le moteur refuse désormais de produire cet écart plutôt que d'en
produire un faux. Et un couple `(mesure, dimension)` n'est valide que si la
dimension existe sur la base de la mesure : la marge se constate sur une facture,
un commercial n'en émet pas.

Le fichier de référence fige 57 valeurs, 8 ventilations et 3 séries mensuelles.
Toute dérive du calcul le casse — et c'est contre ces mêmes agrégats que le
classeur du jalon 4 sera vérifié.

121 tests, dont celui qui confronte les colonnes déclarées par le catalogue à
celles construites par le chargement : rien n'oblige mécaniquement les deux
fichiers à rester d'accord.

## Jalon 3 — Criblage *(fait)*

Énumération exhaustive des couples valides — 89 au niveau gestion — puis cinq
scores : effectif, dispersion, monotonie de Spearman, stabilité sur deux
moitiés de fenêtre, et matérialité en euros de marge annuelle. La matérialité
est recalculée à la main sur deux candidats dans les tests, parce que c'est le
score qui décide du classement.

**Le défaut que les scores ne voient pas.** « Le panier moyen croît avec la
tranche de montant » obtenait dispersion, stabilité et monotonie au maximum,
et arrivait en tête. C'est vrai par construction : la dimension est dérivée de
la grandeur mesurée. Aucun score ne détecte une tautologie ; seule une
déclaration explicite dans le catalogue les écarte. Quinze couples sont
désormais interdits, avec leur justification.

Deux autres corrections nées de l'exécution : la dispersion est bornée et
rapportée à l'objectif atteignable — une mesure dont la moyenne frôle zéro
produisait des écarts de 900 % qui écrasaient tous les autres candidats — et la
stabilité compare l'amplitude de l'écart sur chaque moitié plutôt que son signe,
qui ne discriminait rien.

`uv run candidats --niveau gestion` place en tête le taux de transformation par
délai de première relance, à **107 k€** de marge annuelle. C'est ce que le code
trouve seul, et la référence contre laquelle l'apport de l'agent se mesurera.

67 tests.

## Jalon 4 — Classeur, niveau gestion *(fait)*

`workbook/` complet, piloté par une sélection en fixture. Cinq feuilles de
pilotage — Synthèse, Indicateurs, Détail mensuel, Ce qui a été regardé,
Paramètres — plus les sept feuilles de données avec leurs colonnes calculées.
**64 249 formules, aucune erreur au recalcul.**

Les gabarits traduisent l'algèbre du catalogue en `SUMIFS`, en conservant la
propriété qui tient tout l'édifice : numérateur et dénominateur agrégés
séparément, division en dernier. Les colonnes calculées du classeur portent
exactement les noms utilisés par `analysis/catalogue.py`, ce qui évite toute
table de correspondance — et un contrôle croisé confirme que le classeur et
pandas rendent les mêmes chiffres au centime.

**Les deux ponts de décomposition d'écart** sont exacts par construction. Le pont
de chiffre d'affaires sépare volume, mix et prix ; le pont commercial sépare
volume devisé et transformation, et c'est lui qui porte le constat : +334 k€
d'effet volume contre −387 k€ d'effet transformation. L'entreprise a émis
beaucoup plus de devis et en a gagné moins.

**Un défaut trouvé à l'inspection.** Les quatre graphiques de la feuille
Indicateurs se recouvraient : chaque bloc démarrait sous le tableau précédent,
alors qu'un graphique de cinq barres occupe deux fois plus de lignes. Le bloc
suivant part désormais sous le graphique, calcul fait.

**Livrable client autonome, sans une ligne d'IA.** Si la démonstration agentique
déraille en rendez-vous, il reste ça.

36 tests, qui assertent sur les chaînes de formule produites plutôt que sur des
valeurs : c'est ce qui permet de tester sans LibreOffice.

## Jalon 5 — Contrat et gardes *(fait)*

`parsing.py` est la frontière : tout ce qui vient du modèle y passe, et rien n'en
ressort qui n'ait été confronté au catalogue. Aucune dépendance à `loom_ia`, ni à
pandas, ni au réseau.

**La forme.** Extraction du premier objet JSON équilibré — le modèle préfixe
volontiers sa réponse d'une ligne de trace, et l'entoure parfois d'une clôture
Markdown malgré la consigne. Puis vérification stricte des clés, pendant du
`extra: forbid` : une clé inventée échoue bruyamment plutôt que d'être ignorée.

**Le fond.** Chaque indicateur est revalidé contre le catalogue — mesure connue,
éligible au niveau, dimension praticable sur la base de la mesure, croisement non
tautologique. Le seuil d'alerte, seul nombre autorisé, est contrôlé : `25` au lieu
de `0.25` sur un taux casserait silencieusement la mise en forme conditionnelle.

**La prose.** Aucun chiffre dans les textes rédigés. Règle dure, et volontairement :
une liste blanche serait plus permissive mais impossible à expliquer en rendez-vous.
La promesse tient en une phrase — *le modèle n'écrit aucun chiffre, donc il ne peut
pas se tromper sur un chiffre*.

**L'invariant des hypothèses.** Toute hypothèse notée finit retenue ou écartée avec
un motif ; tout indicateur référence une hypothèse retenue. C'est ce qui empêche le
modèle de rationaliser après coup : une piste qui disparaît sans verdict signale un
raisonnement réécrit une fois le résultat connu.

Côté `settings.json`, le rôle `selection` porte son bloc `output` — schéma à
`additionalProperties: false`, `max_chars`, `must_not_match`, `repair_attempts`,
`on_failure` — et son juge à trois critères, deux bloquants. Les `enum` de mesures
et de dimensions sont **engendrés depuis le catalogue** : le modèle ne peut pas
inventer une clé, et un test vérifie que les deux listes ne divergent jamais.

55 tests, quelques millisecondes, zéro jeton.

## Jalon 6 — L'agent *(écrit, non éprouvé)*

Les six outils vivent dans `analysis/outils.py`, sans aucune dépendance à
`loom_ia` : fonctions pures et schémas d'entrée. `reporting.py` les enveloppe en
`FunctionTool` et se réduit à un câblage d'une page. Cette séparation est ce qui
permet d'éprouver exhaustivement le comportement des outils — validation,
gardes, forme des réponses, trace — sans clé d'API.

**Le niveau est capturé dans la fermeture, jamais exposé dans le schéma.** Les
`enum` de mesures et de dimensions sont construits pour un niveau et pour lui
seul : le modèle ne peut pas s'échapper du registre qu'on lui a assigné.

**`noter_hypothese` n'exécute rien.** Coût nul, mais il force l'engagement avant
que le résultat ne soit connu. Le registre garde la trace de l'ordre des appels,
et sait dire si une hypothèse a bien précédé le premier sondage.

**L'humain tranche avant génération.** La sélection est affichée avec ses
hypothèses écartées, et un indicateur peut être retiré. C'est la seule barrière
entre une bêtise du modèle et le livrable — et le moment où le client comprend
qu'il garde la main. Une sélection amputée reste valide et produit un classeur
qui recalcule sans erreur.

**Ce qui n'est pas vérifié.** Ni `loom_ia`, ni clé d'API, ni réseau n'étaient
disponibles à l'écriture. Le comportement du modèle lui-même — qualité des
hypothèses, respect de la méthode imposée, coût réel — n'a donc jamais été
observé. Le premier point à trancher en exécution est le partage des rôles :
l'orchestrateur raisonne et sonde, le rôle terminal `selection` met en forme
sous contrainte de schéma, et le jugement transite donc par une transcription.
Si l'information s'y perd, l'alternative est de retirer `thinking` de
l'orchestrateur et de lui donner directement le bloc `output`.

47 tests sur les outils et le flux, sans jeton.

## Jalon 7 — Niveau stratégique *(fait)*

Les deux gabarits que le jalon 4 avait laissés de côté sont implémentés, et
concordent avec pandas au centime : le chiffre d'affaires par technicien passe
par une colonne d'appui à plage expansive qui marque la première intervention de
chaque technicien dans la fenêtre — le décompte de valeurs distinctes redevient
une somme —, la concentration client par un `LARGE` sur un chiffre d'affaires par
client précalculé. Ces colonnes coûtent cher et ne sont écrites qu'à ce niveau.

**Une propriété découverte en cherchant à ventiler.** Un rapport per capita dont
le dénominateur est un décompte de valeurs distinctes ne se décompose pas
additivement : un technicien intervient sur plusieurs métiers et serait compté
dans chacun. Ce n'est pas une limite d'Excel, c'est une propriété de la mesure.
L'attribut `ventilable` l'écarte du catalogue des croisements — ce qui a fait
disparaître le candidat stratégique en tête du criblage, celui-là même que le
jalon 3 signalait comme douteux.

Persistance de la sélection, gel du millésime, forçage et rejeu : les quatre
comportements sont éprouvés. Seul le stratégique est gelé — régénérer un rapport
de gestion dans le mois après avoir corrigé une donnée est légitime.

Le juge gagne le critère **non-manipulabilité** en tête, bloquant à 0,75.

## Jalon 8 — Niveau opérationnel *(fait)*

Le livrable change de nature : trois files de travail — créances à appeler, devis
à relancer, interventions en dérive — triées par priorité, plafonnées à
vingt-cinq lignes. Au-delà ce n'est plus une liste de travail, c'est un export.

**L'agent ne choisit pas les files**, dictées par les processus, mais les
**seuils** : à partir de quel retard une créance passe en recouvrement, à partir
de quelle dérive une intervention mérite un examen. Un seuil est un jugement.

Ces feuilles portent des valeurs figées, contrairement au reste du classeur. Une
file constate un état à un instant : la recalculer trois semaines plus tard
changerait les priorités sous les yeux de qui la traite, et ferait rappeler des
clients déjà réglés.

L'export JSON transmet les files avec l'empreinte du jeu de données — un agent de
relance doit pouvoir dire de quelle version sort sa file. La garde de faisabilité
avertit, sans jamais bloquer, quand les données ne portent pas le niveau demandé.

**Une erreur de conception attrapée par une garde du jalon 5.** J'avais fait
piloter la file des devis par `respect_delai_relance`, qui mesure une *part* de
devis relancés à temps : son seuil est un pourcentage, pas un nombre de jours.
Le contrôle d'unité l'a refusé avant que l'erreur n'atteigne le classeur.

