# Veille juridique sociale — AIPALS

Site de veille mis à jour automatiquement chaque matin pour le service social :
les nouveautés juridiques et pratiques (droit social, protection sociale,
handicap, aides sociales) issues des sources officielles françaises, triées par
thème et par importance, avec un résumé rédigé par IA (Google Gemini, offre
gratuite).

L'assistante sociale n'a rien à installer : elle met l'adresse du site en
favori. Tout tourne sur GitHub, gratuitement.

```
Chaque matin (GitHub Actions)
  1. collecte   : flux RSS / pages des sources officielles      (veille/sources.py)
  2. pré-filtre : mots-clés par thème                            (veille/filtre.py + config.yaml)
  3. fiches IA  : pertinence, importance, résumé, « à retenir »  (veille/ia.py, Gemini)
  4. historique : data/items.json, enregistré dans le dépôt      (veille/run.py)
  5. site       : page web + flux RSS, publiés sur GitHub Pages  (veille/rendu.py + templates/)
```

## Sources surveillées (22)

| Famille | Sources |
|---|---|
| Généralistes | Service-Public.fr (particuliers, professionnels), **Journal officiel** (open data DILA), Vie-publique.fr (lois, actualités) |
| Ministères | Travail, Solidarités, Handicap.gouv.fr, DREETS Occitanie |
| Protection sociale | ameli.fr (assurés, médecins), L'Assurance retraite, Agirc-Arrco, Complémentaire santé solidaire |
| Handicap / santé au travail | Agefiph, CNSA, Présanse |
| Jurisprudence | Cour de cassation (chambre sociale + 2e chambre civile, open data DILA), Conseil d'État, Défenseur des droits |
| Presse spécialisée | ASH, Éditions Tissot santé-sécurité (titres et chapôs ; articles parfois payants) |

Écartées volontairement : **caf.fr**, **sante.gouv.fr** et le site **Légifrance**
bloquent les robots (le JO et la jurisprudence sont donc lus via l'open data
officiel de la DILA, sans compte) ; **Mon Parcours Handicap** l'interdit dans
son robots.txt. L'actualité CAF arrive tout de même via Service-Public et le
ministère des Solidarités.

## Ce que voit l'assistante sociale

- Les éléments regroupés par jour, avec un niveau **Essentiel / Utile / Contexte**,
  le type de texte (décret, loi, jurisprudence…), un résumé, un encadré
  **« À retenir »** pour l'accompagnement et la date d'entrée en vigueur.
- Des filtres : thème, importance, période, source, recherche libre.
- Un badge **Nouveau** sur ce qui est arrivé depuis sa dernière visite.
- Des **favoris** (☆ Suivre) pour garder un texte sous le coude.
- **Copier le récap affiché** : du texte prêt à coller dans un mail (équipe, médecins du travail).
- **Imprimer / PDF** de la sélection.
- Un flux RSS (`flux.xml`) pour recevoir les nouveautés dans Outlook.

Favoris et « dernière visite » sont mémorisés dans son navigateur (pas de compte).

## Mise en ligne (une seule fois, ~15 minutes)

1. **Clé Gemini gratuite** : sur <https://aistudio.google.com/apikey>, se
   connecter avec un compte Google (idéalement un compte dédié au service),
   « Create API key ». Aucune carte bancaire n'est nécessaire.
2. **Dépôt GitHub** : créer un dépôt **public** (GitHub Pages est gratuit pour
   les dépôts publics ; il ne contient que des actualités publiques, et la page
   est marquée pour ne pas être indexée par les moteurs de recherche), puis y
   pousser ce dossier :
   ```powershell
   cd "$HOME\Documents\veille-sociale-aipals"
   git init -b main
   git add .
   git commit -m "Veille juridique sociale"
   git remote add origin https://github.com/clemszz/veille-sociale.git
   git push -u origin main
   ```
3. **Secret** : dans le dépôt, *Settings > Secrets and variables > Actions >
   New repository secret* : nom `GEMINI_API_KEY`, valeur = la clé.
4. **Pages** : *Settings > Pages > Build and deployment > Source* : **GitHub Actions**.
5. **Premier passage** : onglet *Actions > Veille quotidienne > Run workflow*.
   Au bout de quelques minutes l'adresse du site s'affiche dans le résumé du
   passage (`https://clemszz.github.io/veille-sociale/`). La recopier
   dans `config.yaml` (`site.url`) pour le flux RSS.

Ensuite tout est automatique (tous les jours vers 6 h 30, avec un passage de secours vers 12 h 30).

> Le premier passage remonte 45 jours en arrière : beaucoup d'éléments à
> résumer d'un coup. Si le quota gratuit de Gemini est atteint, le reste est
> rédigé aux passages suivants (les éléments s'affichent en attendant avec
> l'extrait officiel).

## Personnaliser

Tout se règle dans **`config.yaml`**, modifiable directement sur GitHub (icône
crayon) ; chaque enregistrement relance la veille.

- **Mots-clés** : ajouter/retirer des lignes dans chaque thème. Accents et
  majuscules sont ignorés ; `mot*` = préfixe ; un sigle en MAJUSCULES respecte
  la casse (`AME` ne capte pas « âme »).
- **Sources** : ajouter un flux RSS (`type: rss`) ou désactiver une source
  (`actif: false`). L'état de chaque source (✓ / ⚠) est affiché en bas du site.
- **Modèle Gemini** : variable de dépôt `GEMINI_MODEL` (*Settings > Secrets and
  variables > Actions > Variables*) si le modèle par défaut disparaît. Le code
  utilise par défaut `gemini-3.5-flash-lite` (rapide, quota gratuit le plus
  large) et bascule tout seul sur `gemini-3.8-flash` puis `gemini-flash-latest`
  si besoin (Flash n'autorise que 20 requêtes/jour en gratuit).

## Lancer en local (pour tester une modification)

```powershell
cd "$HOME\Documents\veille-sociale-aipals"
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy .env.example .env      # puis y coller la clé Gemini
.venv\Scripts\python -m veille               # passage complet
.venv\Scripts\python -m veille --sans-ia     # collecte seule, sans Gemini
.venv\Scripts\python -m veille --rendu-seul  # régénère la page depuis data/
start site\index.html
```

## Bon à savoir

- **Résumés IA** : ils peuvent se tromper. Le site le rappelle et chaque titre
  renvoie au texte officiel. Seules des actualités publiques sont envoyées à
  Google, jamais de données sur les salariés accompagnés.
- **Sans clé Gemini**, la veille fonctionne quand même : extraits officiels
  bruts et thèmes par mots-clés.
- **Inactivité** : GitHub peut suspendre les tâches planifiées d'un dépôt
  public sans activité pendant 60 jours. Si la veille s'arrête (mail de
  GitHub), il suffit de cliquer sur *Enable workflow* dans l'onglet Actions.
- **Éléments sans date** (certaines pages d'actualités) : au premier passage
  d'une source ils servent de référence et ne sont pas affichés ; ensuite tout
  nouvel élément apparaît, daté du jour où il a été repéré (`data/vus.json`).
- **Une source en ⚠** : le site a probablement changé d'adresse ou de mise en
  page ; la veille continue avec les autres sources.
