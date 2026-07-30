# loom-report-demo

Démonstration de [`loom-ia`](https://github.com/denislamard/loom) sur un cas de
gestion : produire le tableau de bord d'une PME artisanale à partir de ses
exports comptables, **en laissant un agent décider quels indicateurs méritent
d'être suivis**.

**Application console.** On répond à une question, l'agent explore les données,
propose une sélection d'indicateurs, et le programme produit un classeur Excel.

---

## 1. L'objectif

Le scénario est celui de Bâti-Sud, une entreprise fictive de plomberie,
chauffage et électricité : douze techniciens, trois agences, quatre exercices
d'historique, sept fichiers CSV. Aucune donnée réelle, aucun client réel.

L'intérêt n'est pas qu'un modèle de langage commente des chiffres. C'est le
partage du travail entre ce qui doit être **exact** et ce qui demande du
**jugement**.

### L'agent choisit la question, le code calcule la réponse

Le modèle ne rapporte jamais une valeur. Il rend une *spécification*
d'indicateur : une mesure, une dimension, un cadrage. Python la revalide contre
son catalogue, résout le gabarit de formule correspondant, et l'écrit dans le
classeur. **La valeur affichée n'a jamais transité par le modèle**, même s'il l'a
vue pendant son exploration.

### Aucun chiffre dans la prose du modèle

Il rédige un constat qualitatif et désigne les indicateurs par leur clé. La
garde tient en une expression régulière, se teste sans clé d'API, et la promesse
s'explique en une phrase : *le modèle n'écrit aucun chiffre, donc il ne peut pas
se tromper sur un chiffre*. Seule exception : le `seuil_alerte`, parce qu'un
seuil est un jugement et non une mesure.

### Le criblage relève du code, pas du modèle

Énumérer l'espace des candidats à une dimension est trivial pour Python et
coûteux pour un modèle. Le programme score donc en amont tous les croisements
valides, quatre-vingt-dix au niveau gestion, sur cinq critères : effectif,
dispersion, monotonie, stabilité, et surtout **matérialité en euros**. Ce dernier
critère mesure ce que rapporterait d'amener la modalité la plus défavorable au
niveau des autres. Il convertit une anomalie statistique en argent, et écarte les
écarts spectaculaires mais sans enjeu.

L'agent n'intervient que sur l'espace à deux dimensions et conditionnel, celui
qui est réellement combinatoire.

### Les hypothèses réfutées sont livrées avec les trouvailles

L'agent note ses hypothèses **avant** de sonder, ce qui l'empêche de rationaliser
après coup. Toute hypothèse notée finit retenue ou écartée avec son motif ;
l'invariant est vérifié par le parsing. Un dirigeant qui apprend que ce n'est
*pas* l'agence récente qui plombe la marge a gagné sa réunion.

### Trois niveaux, trois libertés

Le niveau est la seule décision prise par l'humain. Tout le reste s'y adosse,
selon un principe simple : **la liberté de l'agent est inversement
proportionnelle à la durée de vie de sa décision.**

| | Stratégique | Gestion | Opérationnel |
|---|---|---|---|
| Question | Où va mon entreprise ? | Qu'est-ce que je corrige ce mois-ci ? | Qu'est-ce que je traite cette semaine ? |
| Cadrage | exercice N contre N-1 | 12 mois glissants | 30 derniers jours |
| Socle imposé | 4 mesures | 4 mesures | 3 mesures de flux |
| Choisis par l'agent | 2 | 4 | 2 |
| Durée de vie | gelée 12 mois | revue chaque mois | recalculée |
| Livrable | tableau de bord | tableau de bord | **files de travail** |

Le troisième niveau ne produit pas le même objet : ce n'est pas un tableau
d'indicateurs à contempler, c'est une liste triée d'unités à traiter : créances à
appeler, devis à relancer, interventions en dérive. Elle sort aussi en JSON, pour
être poussée dans la file d'un agent de relance.

### Voir le résultat sans rien installer

Les trois rapports sont livrés dans le dossier `rapports/` :

| Fichier | Niveau |
|---|---|
| `Bati-Sud_strategique.xlsx` | Où va mon entreprise ? |
| `Bati-Sud_gestion.xlsx` | Qu'est-ce que je corrige ce mois-ci ? |
| `Bati-Sud_operationnel.xlsx` | Qu'est-ce que je traite cette semaine ? |

Deux feuilles méritent le détour. **Synthèse** porte le socle imposé, les
indicateurs choisis et les ponts de décomposition d'écart. **Ce qui a été
regardé** liste les hypothèses réfutées avec leur motif, ainsi que les
croisements que le criblage a écartés et pourquoi.

Tout y est en formules vivantes : changer la date de situation dans la feuille
**Paramètres** recalcule l'ensemble du classeur.

Une nouvelle exécution écrase ces fichiers. Pour en produire d'autres sans les
perdre, passez un chemin explicite à `uv run rapport --sortie`.

---

## 2. Faire fonctionner la démonstration

### Prérequis

- Python 3.14 ou plus récent
- [uv](https://docs.astral.sh/uv/)
- une clé API Anthropic, sur <https://console.anthropic.com/settings/keys>
- une clé API MiniMax, sur <https://www.minimax.io> (section *API Keys*)

### Installation

```bash
git clone <ce-dépôt> loom_report_demo
cd loom_report_demo
uv sync
```

### Renseigner le fichier `.env`

Sans lui, l'application affiche le menu mais refuse d'explorer.

```bash
cp files/.env.example files/.env
$EDITOR files/.env
```

Le fichier doit contenir vos deux clés :

```dotenv
# files/.env
ANTHROPIC_API_KEY=sk-ant-votre-cle-ici
M3_API_KEY=votre-cle-ici
```

**Les noms de variables ne sont pas arbitraires.** Ils proviennent du champ
`api_keyname` de chaque bloc `llm` dans `files/settings.json` : renommer l'un
oblige à renommer l'autre.

Vérifiez que le fichier est bien exclu du dépôt avant tout commit :

```bash
git check-ignore -v files/.env
```

Si cette commande ne renvoie rien, **vos clés partiront au prochain commit**.

### Lancer l'application

```bash
uv run app
```

L'application pose une question, annonce ce qu'elle va produire, puis explore.
L'exploration prend une minute environ et coûte quelques centimes.

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Bâti-Sud — rapport de pilotage
  Démonstration loom-ia · jeu de données fictif, 4 exercices
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Quel rapport voulez-vous ?

   1   Où va mon entreprise ?                  4 exercices, exercice N contre N-1
   2   Qu'est-ce que je corrige ce mois-ci ?   12 mois glissants, contre les 12 précédents
   3   Qu'est-ce que je traite cette semaine ? 30 derniers jours, situation du jour

   q   quitter
```

Le menu est formulé dans la langue du client : « stratégique, gestion,
opérationnel » est du vocabulaire de contrôleur de gestion, auquel un artisan ne
sait pas répondre.

La sélection proposée est ensuite soumise à votre arbitrage, matérialité en euros
à l'appui. Vous pouvez en retirer un indicateur avant génération : c'est la seule
barrière entre une erreur du modèle et le livrable.

```
  1  Taux de transformation des devis · par délai de premi…  106 770 €/an
     → Fixer un délai de relance maximal et l'outiller, plutôt que de le…

  [g] générer · [1-4] retirer · [q] annuler
```

Le classeur atterrit dans `rapports/`.

### Les autres commandes

| Commande | Ce qu'elle fait | Clé requise |
|---|---|---|
| `uv run app` | le flux complet | oui |
| `uv run app --rejouer` | reprend la dernière sélection sans rappeler le modèle | non |
| `uv run app --forcer` | passe outre le gel d'une sélection stratégique | oui |
| `uv run seed` | régénère le jeu de données | non |
| `uv run profil --niveau gestion` | la carte du terrain remise à l'agent | non |
| `uv run candidats --niveau gestion` | ce que le criblage trouve seul, sans IA | non |
| `uv run rapport --selection tests/fixtures/gestion.json` | produit un classeur depuis une sélection écrite à la main | non |

`--rejouer` sert en rendez-vous client : un agent qui choisit d'autres
indicateurs à chaque lancement empêche de montrer deux fois la même chose.

### Le jeu de données

Les sept CSV sont versionnés dans `assets/data`. Ils sont livrés plutôt que
régénérés à chaque exécution, faute de quoi la narration changerait d'un
lancement à l'autre et les prompts ne seraient plus calibrables.

`uv run seed` les régénère à l'identique. Le générateur étant déterministe, un
`git status` propre après régénération prouve que les données du dépôt
correspondent bien au code qui les produit.

### Observabilité

Les chemins déclarés dans `files/settings.json` sont relatifs à `files/`.

| Chemin | Contenu |
|---|---|
| `files/log/agent.log` | échanges LLM complets |
| `files/log/metrics.jsonl` | une ligne par appel : jetons, coût, latence |
| `files/log/derniere_sortie.txt` | dernière réponse brute du modèle, écrite avant validation |
| `files/log/usage/` | consommation cumulée par session |
| `files/log/selection/` | sélection persistée, un fichier par niveau |

En cas d'échec de l'exploration, `derniere_sortie.txt` dit immédiatement s'il
s'agit d'un problème de forme ou de contenu.

Le garde-fou budgétaire est armé dans `settings.json` : `max_cost_run`,
`max_calls_run` et `max_cost_session`, en mode `warn`.

---

## 3. Architecture logicielle

### Le flux

```
assets/data/*.csv                    sept exports, versionnés
    │
    ├─► fingerprint.py               SHA-256 par fichier + empreinte globale
    │
    ▼
analysis/chargement.py               jointures, colonnes dérivées
analysis/profil.py                   la carte du terrain
analysis/criblage.py                 tous les croisements valides, 5 scores
    │
    ▼
reporting.py ──► Agent (loom-ia)     SEUL module à importer loom_ia
                     │
                     │  noter_hypothese, puis cinq outils pandas
                     │  arguments en enum fermés, niveau capturé
                     ▼
                 rôle `main`         explore, juge ET rédige la sortie
                     │               output.schema + juge SONNET (20 %)
                     ▼
                 JSON de sélection
    │
    ▼
parsing.py                           garde zéro-chiffre, validation catalogue,
    │                                invariant des hypothèses
    ▼
console.py                           affichage, arbitrage humain
    │
    ▼
workbook/                            openpyxl, formules vivantes
    │
    ▼
rapports/Bati-Sud_<niveau>.xlsx
```

### Les modules

**`app.py`** ne porte que deux choses : le contrat de la couche d'interaction,
soit trois alias décrivant les coutures injectables, et `entry()`. Une
cinquantaine de lignes.

**`console.py`** déroule l'exécution : menu, trace, tableau de sélection,
arbitrage, génération. Saisie et écriture y sont injectées, ce qui rend tout le
flux testable sans terminal.

**`niveaux.py`** définit le type de domaine qui commute tout le reste : cadrage,
socle, nombre d'indicateurs variables, durée de vie, nature du livrable.

**`analysis/`** est le cœur analytique : pandas uniquement, aucun réseau.
`catalogue.py` y est purement déclaratif : dix-neuf mesures et douze dimensions,
avec leurs unités, leur sens, leur nature (flux ou stock) et les croisements
**tautologiques** interdits. C'est de lui que sont tirés les `enum` fermés des
outils d'exploration. `chargement.py` est le seul module qui fait des jointures ;
le moteur ne connaît que des colonnes plates. `outils.py` expose les six outils remis à
l'agent sous forme de fonctions pures, ce qui permet de les éprouver
exhaustivement sans clé d'API.

**`parsing.py`** est la frontière. Tout ce qui vient du modèle y passe, et rien
n'en ressort qui n'ait été confronté au catalogue. Bibliothèque standard
uniquement.

**`workbook/`** produit le classeur. `formules.py` traduit l'algèbre du catalogue
en `SUMIFS`. `schema.py` résout les colonnes par **nom de champ**, jamais par
lettre. Ces noms sont exactement ceux du catalogue, ce qui garantit que le
classeur et pandas calculent la même chose.

**`dataset/`** génère le jeu fictif de façon déterministe. **`etat.py`** persiste
la sélection d'une édition à l'autre. **`reporting.py`** est le seul module à
importer `loom_ia`, et se réduit à un câblage d'une page.

### Trois décisions qui structurent le reste

**Un seul modèle, un seul contrat.** L'orchestrateur explore, juge et rédige la
sortie structurée. Une première version séparait le raisonnement de la mise en
forme ; le transcripteur recevait les constats en texte libre et devait
reconstruire une enveloppe qu'il n'avait jamais vue. Il inventait des clés. Le
prix de la fusion est le raisonnement étendu : `thinking` étant incompatible avec
un schéma de sortie, il a été retiré de l'orchestrateur.

**On somme avant de diviser.** La marge moyenne de trois agences n'est pas la
moyenne de leurs trois taux. Chaque mesure porte son numérateur et son
dénominateur en colonnes distinctes, agrégés séparément, divisés en dernier.

**Les mesures de stock ne se comparent pas entre périodes.** Un encours est un
état à la date de situation ; le comparer aux douze mois précédents produisait
des écarts de plusieurs milliers de pour cent. Le moteur refuse de produire cet
écart plutôt que d'en produire un faux.

### Ce qui se teste sans dépenser un jeton

```bash
uv run pytest        # ~480 cas, quelques secondes
uv run ruff check .
uv run pyright
```

Tout sauf `reporting.py` se teste sans clé d'API : les outils d'exploration
s'éprouvent exactement comme le modèle les appellera, et les gardes du parsing
tournent sur des fixtures JSON. Le classeur, lui, s'assertit sur les chaînes de
formule produites plutôt que sur des valeurs : le recalcul complet par
LibreOffice prend près d'une minute sur soixante-quatre mille formules.

Ce qui échappe aux tests est le comportement du modèle lui-même : qualité des
hypothèses, respect de la méthode, coût réel. Cela ne se vérifie qu'en exécution.

---

## Limites connues

**Ce n'est pas un outil de comptabilité.** Le jeu est fictif et la marge calculée
est une marge sur coûts directs, hors frais de structure.

**Le classeur ne porte pas de valeurs en cache.** `openpyxl` écrit des formules ;
Excel et LibreOffice les calculent à l'ouverture, mais `pandas.read_excel` sur le
fichier produit renverra des cellules vides.

**La sélection de l'agent varie d'une exécution à l'autre.** `--rejouer` existe
pour cette raison.

---

Denis Lamard, App-Novative. <lamard.denis@gmail.com>