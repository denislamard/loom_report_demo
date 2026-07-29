# loom-report-demo

Démonstration de [`loom-ia`](https://github.com/denislamard/loom) sur un cas de
gestion : produire le tableau de bord d'une PME artisanale à partir de ses
exports comptables, **en laissant l'agent décider quels indicateurs méritent
d'être suivis**.

Le scénario est celui de Bâti-Sud, une entreprise de plomberie, chauffage et
électricité de douze techniciens répartis sur trois agences. Quatre exercices
d'historique, sept fichiers CSV, et une question posée en console : *où va mon
entreprise*, *qu'est-ce que je corrige ce mois-ci*, ou *qu'est-ce que je traite
cette semaine*. Le programme rend un classeur Excel.

> **État : jalon 4 sur 8.** Le classeur est produit, complet et vérifié, à partir
> d'une sélection d'indicateurs. L'agent qui la choisira arrive au jalon 6.
> Voir [ROADMAP.md](ROADMAP.md).

---

## Ce que la démo cherche à montrer

Le point intéressant n'est pas qu'un LLM commente des chiffres. C'est le partage
du travail entre ce qui doit être exact et ce qui demande du jugement.

**L'agent choisit la question, le code calcule la réponse.** Le modèle ne
rapporte jamais une valeur : il rend une *spécification* d'indicateur — mesure,
dimension, cadrage, comparaison. Python la revalide contre son catalogue, résout
le gabarit de formule correspondant, et écrit dans le classeur. La valeur
affichée n'a jamais transité par le modèle, même s'il l'a vue pendant son
exploration.

**Aucun chiffre dans la prose du modèle.** Il rédige un constat qualitatif et
désigne les indicateurs par leur clé. La garde est triviale à écrire et à
tester : une chaîne contenant un chiffre est rejetée, et `repair_attempts`
relance le rôle. Seule exception, le `seuil_alerte` — parce qu'un seuil est un
jugement, pas une mesure.

**Le pré-criblage est du ressort du code.** Énumérer l'espace des candidats à une
dimension est trivial pour Python et coûteux pour un modèle. Chaque candidat est
scoré sur cinq critères — effectif, dispersion, monotonie, stabilité, et surtout
**matérialité en euros** : *combien rapporterait d'amener la modalité la plus
défavorable au niveau des autres*. Ce dernier score convertit une anomalie
statistique en argent, et empêche le modèle de retenir un écart spectaculaire
mais sans enjeu. L'agent n'intervient que sur l'espace à deux dimensions et
conditionnel, qui est combinatoire — c'est là qu'il gagne sa place.

Le catalogue déclare aussi les croisements **tautologiques**, où la dimension est
dérivée de la grandeur mesurée. « Le panier moyen croît avec la tranche de
montant » est vrai par construction : les cinq scores le notent au maximum, un
humain le voit d'un coup d'œil, et un modèle le retiendrait avec assurance.

**Les hypothèses réfutées sont livrées avec les trouvailles.** L'agent note ses
hypothèses *avant* de sonder, ce qui l'empêche de rationaliser après coup. Toute
hypothèse notée finit retenue ou écartée avec son motif ; l'invariant est vérifié
par le parsing, sans clé d'API. Un dirigeant qui apprend que ce n'est *pas*
l'agence récente qui plombe la marge a gagné sa réunion.

**La liberté de l'agent est bornée par la durée de vie de sa décision.** Un
indicateur stratégique est gelé douze mois : il mérite Sonnet et un juge sévère,
avec un critère bloquant de non-manipulabilité. Un seuil opérationnel est
recalculé à chaque exécution : Haiku suffit. Le routage par coût devient un
argument d'architecture, pas seulement une économie.

---

## Les trois niveaux

Le niveau est la seule décision prise par l'humain. Tout le reste s'y adosse, et
`niveaux.py` en est la source unique.

| | Stratégique | Gestion | Opérationnel |
|---|---|---|---|
| Question | Où va mon entreprise ? | Qu'est-ce que je corrige ce mois-ci ? | Qu'est-ce que je traite cette semaine ? |
| Cadrage | 4 exercices, N vs N-1 | 12 mois glissants | 30 derniers jours |
| Socle imposé | 4 mesures | 4 mesures | 3 mesures de flux |
| Choisis par l'agent | 2 | 4 | 2 |
| Durée de vie | 12 mois, gelée | 1 mois | recalculée |
| Modèle | SONNET | HAIKU | HAIKU |
| Livrable | tableau de bord | tableau de bord | **file de travail** |

Le troisième niveau ne produit pas le même objet. Ce n'est pas un tableau
d'indicateurs à contempler, c'est une liste triée d'unités à traiter — les
créances à appeler, les devis à relancer. Elle sort aussi en JSON, pour être
poussée dans la file d'un agent de relance.

---

## Architecture

```
assets/data/*.csv
    │
    ├─► fingerprint_dataset()      SHA-256 par fichier + empreinte globale
    │
    ▼
analysis/profil.py                 volumétrie, dimensions, totaux d'ancrage
analysis/criblage.py               énumération + 5 scores, dont la matérialité
    │
    ▼
reporting.explorer(niveau)
    │
    ▼
Agent (loom-ia) ─► M3_MAIN, orchestrateur
                       │  noter_hypothese() puis 5 outils pandas
                       │  arguments en enum fermés — tools.validate_arguments
                       ▼
                   rôle exploration ─► HAIKU ou SONNET selon le niveau
                       │   output.schema ◄── validation + repair_attempts
                       │   judge (20 %)  ◄── SONNET
                       ▼
                 sélection d'indicateurs, hypothèses écartées
    │
    ▼
[console]  affichage, retrait possible d'un indicateur  ← l'humain tranche
    │
    ▼
parsing.parse_selection()          garde zéro-chiffre, validation catalogue
    │
    ▼
workbook/                          openpyxl — formules vivantes, jamais de valeurs figées
    │
    ▼
rapports/Bati-Sud_<niveau>.xlsx
```

### Les modules

`__init__.py` porte `run()` et diffère l'import de `app` : au niveau module, il
tirerait `loom_ia` dès qu'on importe le moindre sous-module, y compris ceux qui
doivent rester testables sans clé d'API.

`app.py` ne porte que le contrat de la couche d'interaction — les trois alias
qui décrivent les coutures injectables — et `entry()`. Une quarantaine de lignes,
lisibles d'un coup d'œil.

`console.py` porte le déroulé : menu, trace de l'exploration, tableau de
sélection, arbitrage humain, génération. La saisie et l'écriture y sont
injectées, ce qui rend tout le flux testable sans terminal.

`niveaux.py` porte le type de domaine qui commute tout le reste : cadrage,
socle, nombre d'indicateurs variables, modèle, durée de vie, nature du livrable.

`dataset/` génère le jeu fictif. `lignes.py` porte le contrat de données,
`parametres.py` les constantes métier et la trajectoire, `generateur.py` la
production. Bibliothèque standard uniquement.

`fingerprint.py` calcule les empreintes. `hashlib` uniquement.

`paths.py` résout les chemins indépendamment du répertoire courant. Sans aucune
dépendance.

`parsing.py` est la frontière : tout ce qui vient du modèle y passe. Décodage,
garde zéro-chiffre, validation contre le catalogue, invariant des hypothèses.
Bibliothèque standard uniquement.

`reporting.py` sera le **seul** module à importer `loom_ia`.

`analysis/` porte le catalogue de mesures, les cadrages, le moteur de calcul, le
criblage et le profil. `catalogue.py` est purement déclaratif — c'est de lui que seront tirés
les `enum` fermés des outils d'exploration. `chargement.py` est le seul module
qui fait des jointures ; le moteur ne connaît que des colonnes plates. Pandas
uniquement, pas de réseau.

`workbook/` produit le classeur. `openpyxl` uniquement. `schema.py` résout les
colonnes par nom de champ, `formules.py` traduit l'algèbre du catalogue en
`SUMIFS`, `selection.py` porte le contrat que l'agent remplira au jalon 6.

Tout sauf `reporting.py` se teste sans clé d'API et sans dépenser un centime.

---

## Installation

### Prérequis

- Python 3.14 ou plus récent
- [uv](https://docs.astral.sh/uv/)
- Une clé API Anthropic, sur <https://console.anthropic.com>
- Une clé API MiniMax, sur <https://www.minimax.io>

```bash
git clone <ce-dépôt> loom_report_demo
cd loom_report_demo
uv sync
```

`pandas` et `openpyxl` ont été ajoutés aux dépendances : `uv lock` est nécessaire
avant le premier `uv sync`. Les deux publient des roues `cp314`, `pandas` depuis
la 2.3.3.

### Les clés d'API

```bash
cp files/.env.example files/.env
$EDITOR files/.env
git check-ignore -v files/.env
```

Si la dernière commande ne renvoie rien, vos clés partiront au prochain commit.

Les noms de variables ne sont pas arbitraires : ils proviennent du champ
`api_keyname` de chaque bloc `llm` dans `files/settings.json`. Renommer l'un
oblige à renommer l'autre.

### Le jeu de données

Les sept CSV sont versionnés dans `assets/data`. Ils sont **fictifs** : aucune
donnée réelle, aucun client réel. Ils sont livrés plutôt que régénérés à chaque
exécution, faute de quoi la narration changerait d'un lancement à l'autre et le
prompt ne serait plus calibrable.

Quatre exercices, du 01/07/2022 au 30/06/2026. La trajectoire est lisible : deux
agences et sept techniciens à l'origine, deux embauches en 2023, ouverture de
Montpellier en septembre 2024, douze techniciens à la fin. Le nombre de devis
double, le chiffre d'affaires progresse de 60 %, la marge perd 7,6 points.

`uv run seed` les régénère à l'identique : le générateur est déterministe, donc
un `git status` propre après régénération prouve que les données du dépôt
correspondent au code qui les produit. C'est le contrôle le plus simple, et il
tient en une commande.

Chaque exécution affiche l'empreinte SHA-256 du jeu, qui figurera dans le
classeur : elle établit que le rapport se rapporte à ces fichiers exacts, non
modifiés depuis. Elle n'établit en revanche aucune antériorité — cela
demanderait un horodatage RFC 3161 par un tiers de confiance.

---

## Utilisation

```bash
uv run app        # le rapport
uv run seed       # régénérer le jeu de données
uv run profil     # la carte du terrain remise à l'agent
uv run candidats  # ce que le criblage trouve seul, sans IA
uv run rapport --selection tests/fixtures/gestion.json
```

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

Le menu est formulé dans la langue du client. « Stratégique, gestion,
opérationnel » est du vocabulaire de contrôleur de gestion : un artisan ne sait
pas y répondre, alors que la question se répond seule. En rendez-vous, le menu
lui-même est déjà un argument — et un test échoue si ce jargon réapparaît dans un
libellé.

---

## Observabilité

Les chemins déclarés dans `files/settings.json` sont relatifs au répertoire remis
à `Agent`, c'est-à-dire `files/`. Après une exécution :

| Chemin | Contenu |
|---|---|
| `files/log/agent.log` | échanges LLM complets, niveau `DEBUG` |
| `files/log/metrics.jsonl` | une ligne par appel : tokens, coût, latence |
| `files/log/usage/` | consommation cumulée par session |
| `files/log/memory/` | historique conversationnel, compacté au-delà de 12 000 tokens |
| `files/log/selection/` | sélection d'indicateurs persistée, un fichier par niveau |

Le garde-fou budgétaire est armé à `max_cost_run: 0.05`, `max_calls_run: 25`,
`max_cost_session: 1.0`, en mode `warn`. Passez-le à `error` pour qu'il bloque.

---

## Développement

```bash
uv run pytest              # sans clé d'API
uv run ruff check .
uv run ruff format .
uv run pyright
```

331 cas au jalon 4, tous sans clé d'API, en une dizaine de secondes. Les tests du
classeur portent sur les **chaînes de formule**, jamais sur des valeurs : c'est
ce qui permet de s'en tenir à `openpyxl`, sans LibreOffice, en intégration
continue. La saisie est
injectée plutôt que lue directement, ce qui rend le menu testable sans terminal.

Les tests du jeu de données se répartissent en deux familles. La
**reproductibilité** protège la démonstration : une empreinte de référence est
figée, et toute évolution du générateur doit être un geste explicite. Les
**invariants** protègent la crédibilité : pas de facture sans devis, pas
d'intervention avant l'embauche du technicien, une décision jamais antérieure à
son émission — et la trajectoire d'entreprise elle-même, car si un réglage la
casse, la démonstration meurt en silence.

---

## Limites connues

**Ce n'est pas un outil de comptabilité.** Le jeu de données est fictif et la
marge calculée est une marge sur coûts directs, hors frais de structure.

**Le classeur ne porte pas de valeurs en cache.** `openpyxl` écrit des formules ;
Excel et LibreOffice les calculent à l'ouverture, mais `pandas.read_excel` sur le
fichier produit renverra des cellules vides. Un `--recalc` optionnel est prévu.

**Les colonnes calculées existent deux fois**, en pandas pour l'analyse et en
formules pour le classeur. C'est une duplication assumée : le rapport doit rester
vivant, et aucune abstraction ne traduit honnêtement pandas en Excel. Les seuils
sont importés d'un seul module, un test vérifie que les deux jeux portent les
mêmes noms, et la concordance des valeurs est contrôlée par un recalcul complet
hors CI.

**La sélection de l'agent varie d'une exécution à l'autre.** `--rejouer`
rechargera la dernière sélection depuis `files/log/selection/`, ce qui est
indispensable en démonstration client.

**`M3_MAIN` porte `thinking: adaptive`.** Un rôle à `output.schema` y est
incompatible sur Anthropic : les rôles d'exploration tournent donc sur HAIKU ou
SONNET, sans thinking.

---

## Licence et contact

Denis Lamard, App-Novative. <lamard.denis@gmail.com>
