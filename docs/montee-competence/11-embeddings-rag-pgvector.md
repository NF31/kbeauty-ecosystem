---
title: Embeddings, RAG & pgvector — comprendre la brique avant de la coder
group: Montée en compétence
order: 11
---

← [Retour au sommaire](README.md)

# 11. Embeddings, RAG & pgvector — comprendre la brique avant de la coder

## Objectif

`scripts/embed_ingredients.py` (côté `kbeauty-ingredients-scraper`) a vectorisé 59 listes INCI et les a poussées dans une table `pgvector` sur Neon. Ce document explique *ce que ça veut dire* — le concept avant l'implémentation — parce que "RAG" et "embeddings" sont des mots qu'on croise partout sans forcément savoir ce qu'ils recouvrent concrètement. Sert de référence avant d'attaquer le vrai moteur de matching en Phase 5 (`kbeauty-ai-core-service`).

## Le problème de départ : comparer du texte

Le catalogue kbeauty-shop et le catalogue uniikon.com scrapé ont chacun une liste d'ingrédients INCI par produit, sous forme de texte brut :

```
Aqua, Niacinamide, Glycerin, Panthenol, Centella Asiatica Extract, ...
```

Le besoin final (Phase 5) : étant donné un produit, trouver les produits "similaires" en composition — pas identiques mot pour mot, mais proches dans l'esprit (mêmes familles d'actifs, même logique de formulation). Or comparer du texte brut ne marche pas pour ça :

- **Une comparaison exacte** (`WHERE ingredients = '...'`) ne trouve que des doublons parfaits — quasi inexistants entre deux marques différentes.
- **Une recherche par mot-clé** (`LIKE '%niacinamide%'`) capture la présence d'un ingrédient précis, mais ne dit rien de la similarité *globale* de la formule, et ne comprend pas que "Aqua" et "Water" ou "Centella Asiatica" et "Cica" désignent la même chose.

Il faut un moyen de transformer un texte en quelque chose de **comparable mathématiquement**, tout en préservant le sens. C'est exactement ce que fait un embedding.

## Qu'est-ce qu'un embedding

Un embedding est la traduction d'un texte en un vecteur — une liste de nombres à virgule flottante, de longueur fixe (ici 1024 valeurs, imposé par le modèle Voyage AI `voyage-3.5`) :

```
"Aqua, Niacinamide, Glycerin, ..."  →  [0.0123, -0.0456, 0.0789, ..., -0.0234]   (1024 nombres)
```

Ce vecteur n'est pas une compression ou un hash — il n'y a aucun moyen de le "décompresser" pour retrouver le texte d'origine. C'est une **position dans un espace à 1024 dimensions**, produite par un modèle de langage entraîné pour que cette position reflète le *sens* du texte plutôt que sa forme exacte. Concrètement, l'entraînement du modèle fait en sorte que :

- Deux textes au sens proche → deux vecteurs proches dans cet espace (peu importe que les mots soient différents).
- Deux textes au sens éloigné → deux vecteurs éloignés.

Impossible à vérifier à l'œil sur 1024 dimensions, mais l'intuition à garder est celle d'une carte géographique : deux villes voisines sur la carte (deux textes au sens proche) ont des coordonnées (latitude, longitude) numériquement proches — sauf qu'ici on a 1024 "coordonnées" au lieu de 2, et les "coordonnées" du modèle de langage capturent du sens plutôt que de la géographie.

**Pourquoi 1024 dimensions et pas 2 ou 3 ?** Parce que le "sens" d'un texte est riche — il faut assez de dimensions pour encoder simultanément le type de produit, les familles d'actifs, l'intention (hydratant, anti-âge, apaisant...), etc. C'est un choix du fournisseur du modèle (Voyage AI), pas un paramètre qu'on ajuste soi-même — la colonne `vector(1024)` de `uniikon_ingredient_embeddings` doit correspondre exactement à la dimension produite par `voyage-3.5`.

**Pourquoi Voyage AI et pas Claude directement ?** Anthropic (l'éditeur de Claude) n'a pas d'API d'embeddings native — Claude génère du texte, pas des vecteurs. Voyage AI est l'entreprise qu'Anthropic a rachetée et recommande officiellement comme partenaire embeddings à côté de Claude. D'où le choix de `voyage-3.5` plutôt qu'une alternative (OpenAI `text-embedding-3-small` était l'option initialement envisagée).

## Comparer deux vecteurs : la similarité cosinus

Une fois deux textes transformés en vecteurs, "sont-ils proches en sens ?" devient une question purement géométrique : **quel est l'angle entre ces deux vecteurs ?**

- Angle proche de 0° (vecteurs presque alignés) → textes au sens très proche.
- Angle proche de 90° (vecteurs perpendiculaires) → textes sans rapport.

La **similarité cosinus** mesure exactement ça (le cosinus de l'angle), et se ramène à une formule simple :

```
similarité(A, B) = (A · B) / (‖A‖ × ‖B‖)
```

Elle vaut 1 pour deux vecteurs identiques, 0 pour deux vecteurs perpendiculaires (sans rapport), -1 pour deux vecteurs opposés. C'est le calcul que fait `pgvector` en interne quand on lui demande de trier par proximité (`vector_cosine_ops`, cf. plus bas) — pas besoin de l'implémenter à la main, mais comprendre ce qu'il y a sous le capot évite que `<=>` reste une formule magique.

## Pourquoi une base de données spécialisée (pgvector) plutôt qu'une colonne classique

Rien n'empêche techniquement de stocker un vecteur dans une colonne `text` ou `json` — le problème est la **recherche**. Le besoin réel n'est jamais "donne-moi le produit avec exactement ce vecteur", mais toujours "donne-moi les *N produits les plus proches* de ce vecteur" (top-K nearest neighbors). Sans index adapté, ça veut dire calculer la similarité cosinus entre le vecteur cherché et **chaque ligne de la table**, une par une, à chaque requête — un balayage complet (`O(n)`) qui devient inutilisable dès que le catalogue grossit.

`pgvector` est une extension PostgreSQL qui ajoute :

1. **Un type `vector(N)`** — stocke le tableau de floats nativement, avec la dimension imposée en garde-fou (`vector(1024)` refuse d'insérer un vecteur d'une autre taille).
2. **Des opérateurs de distance** — `<=>` (distance cosinus), `<->` (distance euclidienne), `<#>` (produit scalaire négatif) — utilisables directement dans un `ORDER BY`.
3. **Un index approximatif (HNSW)** — la vraie raison d'être de l'extension. `HNSW` (*Hierarchical Navigable Small World*) construit un graphe de proximité entre les vecteurs à l'insertion, pour ne visiter qu'une petite fraction des lignes lors d'une recherche, au lieu de toutes les balayer. En échange d'une garantie d'exactitude à 100 % (d'où "approximatif" — il peut rater le tout premier voisin dans de rares cas), la requête passe de linéaire à quasi-instantanée même sur de gros volumes.

C'est ce qui a été mis en place sur Neon :

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE uniikon_ingredient_embeddings (
    sku               text PRIMARY KEY,
    product_name      text,
    ingredients_raw   text,
    embedding         vector(1024),
    embedding_model   text,
    created_at        timestamptz DEFAULT now()
);

CREATE INDEX ON uniikon_ingredient_embeddings
    USING hnsw (embedding vector_cosine_ops);
```

Et la requête "trouve-moi les 5 produits les plus proches de tel vecteur" devient :

```sql
SELECT sku, product_name, embedding <=> '[0.0123, -0.0456, ...]' AS distance
FROM uniikon_ingredient_embeddings
ORDER BY embedding <=> '[0.0123, -0.0456, ...]'
LIMIT 5;
```

`<=>` renvoie une **distance** (1 − similarité cosinus) : plus la valeur est petite, plus les deux produits sont proches en sens — d'où le tri croissant.

**Pourquoi sur Neon plutôt que Cassandra ?** Cassandra (utilisé pour le scraping, cf. [Phase 4 — Scraping](10-phase4-scraping-cassandra.md)) n'a pas d'équivalent pgvector — c'est une base clé-valeur/colonnes distribuée, pensée pour l'écriture massive, pas pour la recherche par similarité. Neon (PostgreSQL) est la source de vérité transactionnelle du projet et supporte pgvector nativement : cohérent avec la doc [02 — Bases de données](02-bases-donnees.md), qui identifiait déjà Neon comme le futur support du RAG avant même que cette brique soit codée.

## Qu'est-ce que le RAG (Retrieval-Augmented Generation)

RAG = *Retrieval-Augmented Generation*, "génération augmentée par recherche". C'est un pattern en deux étapes qui répond à une limite structurelle des LLM (comme Claude) : un modèle de langage ne connaît que ce qui était dans ses données d'entraînement — il n'a aucune idée du catalogue kbeauty-shop, qui change tous les jours.

Le RAG contourne ce problème sans réentraîner le modèle :

1. **Retrieval (recherche)** — avant de poser la question au LLM, on va chercher dans une base de connaissance externe (ici : `uniikon_ingredient_embeddings`) les documents les plus pertinents par rapport à la question, via la recherche vectorielle décrite ci-dessus.
2. **Augmented Generation (génération augmentée)** — on colle ces documents trouvés directement dans le prompt envoyé au LLM ("Voici 5 produits similaires : [...]. Sachant ça, réponds à : ..."), et le LLM génère sa réponse *en s'appuyant sur ce contexte frais* plutôt que sur sa seule mémoire d'entraînement.

Appliqué au projet : le futur moteur de matching (Phase 5, `kbeauty-ai-core-service` en Spring Boot) prendra un produit du catalogue kbeauty-shop, ira chercher par embedding les formules les plus proches dans les données scrapées (ou dans le catalogue lui-même), et pourra ensuite s'en servir soit directement (affichage "produits similaires"), soit comme contexte pour une génération plus riche (ex : "pourquoi ces produits sont-ils recommandés ensemble ?").

`scripts/embed_ingredients.py` ne construit que la **première moitié** du "R" de RAG — la base vectorielle interrogeable. Il n'y a ni recherche top-K en place, ni appel à un LLM avec contexte injecté : c'est le chantier Phase 5 explicitement noté comme "le plus incertain, prévoir buffer" dans la [ROADMAP](ROADMAP.md). Volontairement isolé de `kbeauty-ai-core-service` (Java) : ce script Python ne fait que produire la donnée vectorisée, il ne branche aucun matching.

## Le pipeline mis en place, étape par étape

1. **Source** : `ingredients_raw` (liste INCI brute) pour chaque produit uniikon.com, dans Cassandra (`kbeauty_ingredients.products`) — donnée déjà scrapée en Phase 4.
2. **Idempotence** : avant d'appeler l'API, requête sur `uniikon_ingredient_embeddings` pour récupérer les `sku` déjà vectorisés, et les exclure du lot à traiter. Permet de relancer le script sans risque après un échec partiel (rate limit, coupure réseau) sans repayer des appels API déjà faits.
3. **Vectorisation par lots** : les listes INCI restantes sont envoyées à l'API Voyage AI (`client.embed(texts, model="voyage-3.5", input_type="document")`) par petits paquets de 5, espacés de 25 secondes — contrainte du tier gratuit Voyage AI (3 requêtes/minute sans moyen de paiement enregistré).
4. **Écriture** : chaque lot est inséré (`INSERT ... ON CONFLICT (sku) DO UPDATE`) immédiatement après réception, avec `conn.autocommit = True` — chaque lot est validé indépendamment, pour qu'un échec sur un lot ultérieur ne fasse pas perdre le travail déjà fait sur les précédents (bug rencontré et corrigé pendant le développement : une première version enveloppait toute la boucle dans une seule transaction, et un rate limit sur le lot 2 annulait silencieusement les inserts du lot 1 déjà réussi).

Résultat : 59 listes INCI vectorisées et interrogeables par similarité dans `uniikon_ingredient_embeddings`.

## `input_type="document"` — un détail qui compte

Voyage AI (comme la plupart des modèles d'embeddings modernes) distingue deux modes d'encodage selon le rôle du texte :

- `input_type="document"` — pour le texte qu'on stocke et qu'on rendra cherchable (ici, les listes INCI). Utilisé dans `embed_ingredients.py`.
- `input_type="query"` — pour le texte de la *recherche* elle-même, au moment d'interroger la base.

Le modèle applique un traitement légèrement différent dans les deux cas, optimisé pour que la similarité entre une "query" et un "document" pertinent soit maximisée — même si intuitivement on pourrait s'attendre à ce que le même texte donne le même vecteur quel que soit le mode. C'est un point à ne pas oublier en Phase 5 : la requête de recherche devra être vectorisée avec `input_type="query"`, pas `"document"`, sous peine de biaiser les scores de similarité.

## Ce qu'il reste pour un vrai RAG (Phase 5)

Ce qui existe aujourd'hui est la fondation, pas le produit fini :

- [x] Base vectorielle peuplée et interrogeable (`uniikon_ingredient_embeddings`, index HNSW).
- [x] Vectoriser aussi le catalogue kbeauty-shop lui-même (2026-09-02) : table `shop_ingredient_embeddings` (même schéma, même modèle `voyage-3.5`), peuplée par `php artisan products:embed-ingredients` (`App\Application\Catalog\UseCases\EmbedProductIngredients`) — voir aussi [13-diagnostic-vision-laravel.md](13-diagnostic-vision-laravel.md) pour le détail du branchement.
- [x] Requête top-K réelle (2026-09-02) : `ProductMatchRepository` (`kbeauty-ai-core-service`, `JdbcTemplate`, pas Hibernate — pgvector n'a pas de mapping JPA natif) exécute `ORDER BY embedding <=> ?::vector LIMIT 4` sur `shop_ingredient_embeddings`, exposée via `POST /diagnostics/analyze` (`recommendedProductIds` dans la réponse).
- [ ] Décider si le résultat sert tel quel (liste de produits similaires, choix retenu pour l'instant) ou est réinjecté dans un prompt LLM pour une génération de texte (le "G" du RAG, pas encore abordé).

**Requête utilisée pour la recherche (Phase 5)** : le texte de requête n'est pas une liste INCI mais l'analyse Claude + les scores du diagnostic ("Diagnostic peau. *Peau plutôt équilibrée...* Scores : rougeurs : 30/100, ..."), vectorisé avec `input_type="query"` (voir `VoyageEmbeddingClient.embedQuery`, côté Java) — contrairement à `embed_ingredients.py` qui vectorise des listes INCI en `input_type="document"`. C'est le même modèle mais un texte de nature différente ; ça reste cohérent car Voyage encode le *sens* du texte, pas sa structure littérale.

**Repli si le matching échoue** : `ProductMatchingService` (Java) est "best effort" — une panne Voyage AI, ou `shop_ingredient_embeddings` pas encore peuplée, renvoie une liste vide plutôt qu'une erreur. Côté Laravel, `DiagnosticController::recommendedProducts()` retombe alors sur l'ancienne sélection aléatoire filtrée par `skin_types` — le diagnostic reste toujours utilisable, avec une recommandation moins pertinente en attendant que l'embedding tourne.
