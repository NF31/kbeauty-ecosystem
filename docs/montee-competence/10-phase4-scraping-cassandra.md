---
title: Phase 4 — Scraping Scrapy & pipeline Cassandra
group: Montée en compétence
order: 10
---

← [Retour au sommaire](README.md)

# 10. Phase 4 — Scraping Scrapy & pipeline Cassandra

## Objectif

Construire un pipeline de data engineering simple et réel : un spider qui va chercher des données publiques sur le web, et un pipeline qui les pousse dans une base NoSQL (Cassandra) — la persistance polyglotte évoquée en Phase 1/2, appliquée à un cas concret plutôt qu'en théorie.

## Choisir une cible qu'on a le droit de scraper

Le premier réflexe a été de viser un vrai catalogue d'ingrédients cosmétiques (CosDNA, INCI Beauty), pour rester proche du thème "diagnostic peau" des phases précédentes. Avant d'écrire la moindre ligne de spider, vérification de leur `robots.txt` :

- **CosDNA** : `User-agent: CLAUDEBOT` → `Disallow: /`, et `User-agent: GenAI` → `Disallow: /`.
- **INCI Beauty** : `User-agent: ClaudeBot`, `Claude-User`, `Claude-SearchBot` → `Disallow: /`.
- **Open Beauty Facts** (même son sous-domaine d'export officiel `static.openbeautyfacts.org`, pourtant fait pour le téléchargement en masse) : `User-agent: Scrapy` → `Disallow: /`, et `User-agent: ClaudeBot` / `anthropic-ai` → `Disallow: /`.

Les trois bloquent explicitement soit Scrapy, soit les agents IA/Claude. Utiliser un user-agent générique pour contourner ça aurait été aller contre l'intention claire de l'éditeur — donc aucun des trois n'a été retenu, même si le but est pédagogique.

**Cible retenue : `uniikon.com`** (boutique Shopify de cosmétique capillaire). Son `robots.txt` autorise explicitement le crawl public (`User-agent: * / Allow: /` sur `/products`), sans restriction visant Scrapy ou les IA — au contraire, il documente même un point d'entrée agentique (`agents.md`, `UCP/MCP`) pour les achats automatisés. Chaque fiche produit contient un tableau comparatif de "gammes" (public cible, actions principales, actifs clés) : pas un vrai catalogue INCI, mais une structure de données assez proche dans l'esprit pour l'exercice.

## Ce qui a été construit

### Infra

- `docker compose up -d cassandra` dans `kbeauty-ecosystem` (le service existait déjà dans le `docker-compose.yml`, juste pas démarré).
- Keyspace + tables créés via `cqlsh` :
  ```sql
  CREATE KEYSPACE kbeauty_ingredients WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1};

  CREATE TABLE kbeauty_ingredients.gammes (
    name text PRIMARY KEY,
    source_url text,
    ideal_pour text,
    actions_principales text,
    actifs_cles text,
    scraped_at timestamp
  );

  CREATE TABLE kbeauty_ingredients.products (
    sku text PRIMARY KEY,
    source_url text,
    name text,
    price decimal,
    currency text,
    availability text,
    rating decimal,
    ratings_count int,
    benefits text,
    description text,
    ingredients_raw text,
    scraped_at timestamp
  );
  ```
  Deux tables distinctes mais reliées par `source_url` (une page produit alimente les deux) : `gammes` pour le tableau comparatif (répété à l'identique sur toutes les pages, cf. section "Résultats du crawl complet"), `products` pour la fiche produit elle-même — un concept différent, donc pas mélangé dans la même table.

### Le projet Scrapy

`~/projects/kbeauty-ingredients-scraper` (nouveau, séparé du monolithe Laravel — un venv Python, pas de dépendance croisée) :

- `ingredients_scraper/items.py` — deux items :
  - `GammeItem` (name, source_url, ideal_pour, actions_principales, actifs_cles) : une ligne du tableau comparatif de gammes.
  - `ProductItem` (sku, source_url, name, price, currency, availability, rating, ratings_count, benefits, description, ingredients_raw) : la fiche produit elle-même.
- `ingredients_scraper/spiders/uniikon_gammes.py` — un `SitemapSpider` qui suit `sitemap.xml`, ne garde que les URLs `/products/...` (pas les traductions `/es/...`), et pour chaque page extrait deux choses en parallèle :
  - **`parse_product()`** — les blocs `.card-comparaison .card-info` (tableau de gammes). Le HTML de chaque bloc est irrégulier (parfois label + valeur dans le même `<p>`, parfois la valeur étalée sur plusieurs `<p>` suivants) — `_extract_labelled_values()` gère les deux cas en accumulant le texte jusqu'au label suivant.
  - **`_extract_product()`** — un `ProductItem` construit à partir du bloc **JSON-LD `schema.org/Product`** que Shopify injecte sur chaque page (`<script type="application/ld+json">`) : `sku`, `price`, `priceCurrency`, `availability`, et la note Loox (`aggregateRating.ratingValue`/`ratingCount`). Bien plus fiable à parser que du HTML classique — structuré, pas de sélecteurs CSS fragiles. Complété avec deux onglets HTML de la page (`benefits` depuis `.tab-content-0 .check-item`, `ingredients_raw` — la vraie liste **INCI** — depuis `.tab-content-2`). Le site duplique ces deux blocs (versions desktop/mobile identiques) : seule la première occurrence est gardée pour éviter les doublons.
  - `USER_AGENT` explicite et honnête (`kbeauty-montee-competence-bot/1.0`, avec contact) plutôt que de se faire passer pour un navigateur — bonne pratique de scraping, même quand le `robots.txt` autorise.
  - `DOWNLOAD_DELAY = 1.5` et `CONCURRENT_REQUESTS_PER_DOMAIN = 2` pour rester poli.
- `ingredients_scraper/pipelines.py` — `CassandraPipeline` : ouvre une connexion Cassandra une fois par run (`open_spider`/`close_spider`), et route chaque item vers la bonne table (`gammes` ou `products`) selon son type (`isinstance`). Conversions `Decimal`/`int` explicites pour les colonnes typées (`price`, `rating`, `ratings_count`) — le driver Cassandra n'accepte pas une string brute pour une colonne `decimal`/`int`.
- `settings.py` — pipeline activé (`ITEM_PIPELINES`).

### Validation

Le parsing a d'abord été testé hors-ligne sur une fixture HTML réelle (`fixtures/sample_product.html`), via `scripts/test_parse_fixture.py` (construit une fausse `HtmlResponse` Scrapy à partir du fichier local, sans requête réseau — utile pour itérer sur le parsing sans se faire rate-limiter). Puis validé en conditions réelles par le crawl complet (voir section suivante).

### Persistance polyglotte "local + prod" (comme Neon)

Contrairement à Neon (une seule DB_URL qui pointe local ou prod selon l'environnement), Cassandra n'a pas d'équivalent : chaque cluster se configure séparément (contact point + datacenter en local, Secure Connect Bundle + token en cloud). Mis en place ici avec le même principe que Neon :

- **Local** : le conteneur Docker `kbeauty_cassandra` (`127.0.0.1:9042`), sans authentification. Bac à sable de dev — libre de `TRUNCATE`/re-tester sans conséquence.
- **"Prod"** : [DataStax Astra DB](https://astra.datastax.com), un Cassandra managé avec un vrai tier gratuit serverless (région `us-east-2`, seule dispo sur le free tier). Keyspace `default_keyspace` (le seul autorisé côté free tier), table `gammes` identique au schéma local. Authentification par token (`user=token`, `password=AstraCS:...`) + un fichier **Secure Connect Bundle** (`.zip`, contient les certificats TLS et le routage du cluster) à télécharger par base.
- Provisionné via l'[Astra CLI](https://docs.datastax.com/en/astra-cli/install.html) (`astra setup`, `astra db list`, `astra db download-scb`) plutôt qu'à la main dans l'UI web — plus simple à documenter et à refaire.

Le pipeline Scrapy (`CassandraPipeline`) écrit uniquement dans le local pour l'instant — un choix volontaire de garder l'itération spider/parsing gratuite et illimitée avant de pousser une vraie donnée validée vers Astra.

### Inspection visuelle : DBeaver

Besoin d'un visuel sur les deux bases (comme un client SQL sur Neon), sans re-router tout le projet vers un Firebase/Supabase juste pour ça (ce qui aurait perdu l'intérêt pédagogique de la persistance polyglotte). Solution : DBeaver, avec une contrainte à contourner —le support natif Cassandra est réservé aux éditions payantes de DBeaver, la Community edition (gratuite) ne l'inclut pas.

Contournement : un driver JDBC tiers open-source, [`ing-bank/cassandra-jdbc-wrapper`](https://github.com/ing-bank/cassandra-jdbc-wrapper), enregistré manuellement dans DBeaver (Gestionnaire des pilotes → nouveau pilote → JAR du wrapper). Deux connexions distinctes, avec deux drivers différents (l'URL Astra n'est pas compatible avec le template `jdbc:cassandra://{host}` du driver "standard") :

- **Local** — driver `Cassandra JDBC`, URL `jdbc:cassandra://localhost:9042/kbeauty_ingredients?localdatacenter=datacenter1` (le paramètre `localdatacenter` est une exigence du driver Cassandra dès qu'un contact point explicite est fourni), sans authentification.
- **Astra** — driver `Cassandra JDBC Astra` (copie du précédent, URL Template changé en `jdbc:cassandra:astra:///{database}` — le schéma `astra:` n'est disponible qu'à partir de la version du wrapper utilisée ici, `5.0.2`), URL `jdbc:cassandra:astra:///default_keyspace?secureconnectbundle=<chemin vers le .zip>`, authentification `token` / `AstraCS:...`.

Les deux bases sont maintenant navigables et interrogeables visuellement, en local comme en "prod", sans compte tiers supplémentaire (Astra sert aussi de dashboard web basique en secours).

### Installation des outils (WSL Ubuntu + Windows)

```bash
# Python venv (le paquet manquait par defaut sur cette install Ubuntu)
sudo apt install -y python3.12-venv
python3 -m venv .venv
source .venv/bin/activate
pip install scrapy cassandra-driver

# Astra CLI (necessite unzip)
sudo apt-get install -y unzip
curl -fsSL ibm.biz/get-astra-cli -o /tmp/get-astra-cli.sh && bash /tmp/get-astra-cli.sh
echo 'eval "$(~/.astra/cli/astra shellenv)"' >> ~/.bashrc

astra setup                    # colle le token Astra (AstraCS:...)
astra db list                  # verifie que la base apparait
astra db download-scb kbeauty-ingredients -f ~/projects/kbeauty-ingredients-scraper/.astra-secrets/secure-connect-kbeauty-ingredients.zip
```

Côté Windows (GUI, installé via `winget`) :

```powershell
winget install --id dbeaver.dbeaver -e --accept-package-agreements --accept-source-agreements
```

Puis dans DBeaver : Gestionnaire des pilotes → nouveau pilote → JAR téléchargé depuis les [releases GitHub du wrapper](https://github.com/ing-bank/cassandra-jdbc-wrapper/releases) (`cassandra-jdbc-wrapper-5.0.2-bundle.jar`) → classe `com.ing.data.cassandra.jdbc.CassandraDriver`.

## Résultats du crawl complet

Le rate-limit Shopify rencontré pendant le debugging manuel (`curl` répétés déclenchant un `429 local_rate_limited`) a fini par se lever de lui-même après quelques minutes sans requête — rien à voir avec le spider, c'est bien un effet de bord du debugging, pas du crawl. Premier crawl complet (`scrapy crawl uniikon_gammes`) :

- **78 pages produits** crawlées (sitemap complet, hors traductions `/es/...`), toutes en `200 OK`.
- **268 items "gamme"** extraits, mais seulement **5 lignes uniques** en base (`kbeauty_ingredients.gammes`) : le même tableau comparatif des gammes de la marque est répété à l'identique sur les 78 fiches produit, et la clé primaire (`name`) écrase les doublons à l'insertion — comportement voulu, pas un bug. En creusant, deux des cinq lignes (`❤️ Gamme The One` / `🩷 Gamme The One`) sont en fait la même gamme avec un simple variant d'emoji côté site : 4 gammes distinctes en réalité.
- Un run a également déclenché 5 `429` en cours de crawl (le site reste sensible même en respectant `DOWNLOAD_DELAY`), tous absorbés automatiquement par le `RetryMiddleware` de Scrapy sans intervention.

Ce constat (beaucoup de volume scrapé, peu de matière réellement nouvelle) a motivé l'ajout de `ProductItem` : en plus du tableau de gammes, chaque page produit alimente maintenant aussi `kbeauty_ingredients.products` avec des données propres à *chaque* produit (prix, note, avis, description, liste INCI) — potentiellement jusqu'à 78 lignes uniques (une par SKU), au lieu de 4-5.

Vérification après un run :

```bash
docker exec kbeauty_cassandra cqlsh -e "SELECT COUNT(*) FROM kbeauty_ingredients.gammes;"
docker exec kbeauty_cassandra cqlsh -e "SELECT COUNT(*) FROM kbeauty_ingredients.products;"
docker exec kbeauty_cassandra cqlsh -e "SELECT sku, name, price, rating FROM kbeauty_ingredients.products;"
```

## Prochaine étape

Une fois le crawl `products` validé sur l'ensemble du catalogue et les données réelles poussées vers Astra (à la place des fixtures de test) : Scrapy-Playwright + social listening (prévu Phase 4 avancée), ou enchaîner sur la Phase 0 (BPMN/UML, toujours en attente) / Phase 5 (IA réelle).
