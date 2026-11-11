---
title: Phase 5 — Diagnostic peau réel (vision Claude)
group: Montée en compétence
order: 13
---

← [Retour au sommaire](README.md)

# 13. Phase 5 — Diagnostic peau réel (vision Claude)

## Ce qui change par rapport à la Phase 3

Depuis la Phase 3, `/diagnostic-peau` affichait une analyse **en dur**
(`hardcodedAnalysis()`, un texte fixe par type de peau) — seul le flux
event-driven était réel. Cette étape branche la vraie IA : côté
`kbeauty-ai-core-service` (Spring Boot), un nouvel endpoint `POST
/diagnostics/analyze` envoie une photo à l'API vision de Claude (Anthropic)
et retourne une vraie analyse + des scores anonymisés (voir le détail côté
Java : `kbeauty-ai-core-service/docs/05-diagnostic-vision-claude.md`, repo
séparé). Cette page documente le câblage côté Laravel.

## Le flux

1. Le visiteur choisit un type de peau **et** upload une photo (les deux
   sont maintenant requis — avant, seul le type de peau suffisait).
2. `POST /diagnostic-peau` envoie la photo en `multipart/form-data` à
   `AiCoreDiagnosticClient::analyzeSkin()`, qui la relaie telle quelle
   (jamais écrite sur le disque Laravel) vers `kbeauty-ai-core-service`.
3. **Si l'IA échoue** (service injoignable, timeout, ou refus — ex. compte
   Anthropic sans crédit) : retour au formulaire avec une erreur
   (`back()->withErrors(['photo' => ...])`), **pas** un faux résultat
   présenté comme réel. Contrairement à `createDiagnosticRequest()` en
   Phase 3 (qui ignorait silencieusement un échec, l'analyse étant de
   toute façon bidon), ici le contenu affiché *est* le produit — le
   masquer derrière un texte inventé serait trompeur.
4. **Si l'IA réussit** : la page affiche le texte d'analyse réel **et**
   les scores (barres de progression) retournés par Claude, en plus des
   produits recommandés — depuis le 2026-09-02, un vrai matching
   vectoriel plutôt qu'une sélection aléatoire filtrée par `skin_types`
   (voir la section dédiée plus bas).

## Fichiers créés/modifiés

### app/Services/AiCoreDiagnosticClient.php

`createDiagnosticRequest()` (Phase 3, appel bidon sans contenu) est
supprimée — remplacée par `analyzeSkin(UploadedFile $image, string
$skinType)`. Timeout à 20s (contre 2s avant) : un appel à une API vision
externe est structurellement plus lent qu'un simple insert. La photo est
lue en mémoire (`UploadedFile::get()`) et transmise via
`Http::attach()`, jamais écrite sur disque côté Laravel.

### app/Http/Controllers/Storefront/DiagnosticController.php

`hardcodedAnalysis()` supprimée. `analyze()` valide maintenant `photo`
(`required|image|max:8192`, même limite que le `spring.servlet.multipart.
max-file-size=8MB` côté Spring Boot), appelle `analyzeSkin()`, et gère
explicitement le cas d'échec (voir point 3 ci-dessus).

### resources/js/pages/storefront/diagnostic.tsx

Le clic direct sur un type de peau (qui lançait l'analyse immédiatement)
devient une sélection dans un vrai petit formulaire : type de peau +
`<input type="file">` + bouton "Lancer le diagnostic" (désactivé tant que
les deux ne sont pas remplis). `router.post` avec `forceFormData: true`
(obligatoire pour envoyer un `File` via Inertia). Nouvelle section scores
sous l'analyse texte quand `result.scores` est présent.

### tests/Feature/Storefront/DiagnosticAnalyzeTest.php

3 tests Pest d'origine (photo requise, résultat réel affiché quand
`AiCoreDiagnosticClient` mocké réussit, formulaire redisplayé avec erreur
quand il échoue), + 2 tests ajoutés le 2026-09-02 pour le matching
vectoriel (ordre de similarité respecté, repli sur la sélection aléatoire
quand `recommendedProductIds` est vide). Pas d'appel réseau réel dans les
tests — `$this->mock()` intercepte le service au niveau de son interface,
comme pour `CloudinaryService` ailleurs dans le projet.

## Matching vectoriel des produits recommandés (2026-09-02)

Jusque-là, `recommendedProducts` était une sélection **aléatoire** de
produits publiés partageant le même tag `skin_types` que le diagnostic —
aucun rapport avec le contenu réel de l'analyse. Détail complet côté
concept dans [11-embeddings-rag-pgvector.md](11-embeddings-rag-pgvector.md)
("Ce qu'il reste pour un vrai RAG") ; résumé du câblage ici.

**Indexation (Laravel)** — `php artisan products:embed-ingredients`
(`App\Application\Catalog\UseCases\EmbedProductIngredients`, commande
`App\Console\Commands\EmbedProductIngredientsCommand`) vectorise
`ingredients_inci` de chaque produit publié via `VoyageEmbeddingClient`
(`input_type="document"`), et upsert le résultat dans
`shop_ingredient_embeddings` (migration
`2026_09_02_100000_create_shop_ingredient_embeddings_table`, `vector(1024)`
+ index HNSW — colonne ajoutée en SQL brut, `Schema::create` ne connaît pas
le type pgvector). Idempotent (exclut les produits déjà vectorisés) et par
lots de 5 espacés de 25s, même contrainte de rate limit Voyage AI gratuit
que côté `kbeauty-ingredients-scraper`. À relancer manuellement après
ajout/modification de produits publiés — pas de planification automatique.

**Recherche (kbeauty-ai-core-service)** — `ProductMatchingService`
transforme l'analyse + les scores du diagnostic en texte de requête
("Diagnostic peau. *analyse...* Scores : rougeurs : 30/100, ..."), le
vectorise via `VoyageEmbeddingClient.embedQuery`
(`input_type="query"`, cette fois côté Java), puis `ProductMatchRepository`
(`JdbcTemplate`, pas Hibernate — pgvector n'a pas de mapping JPA) exécute
`ORDER BY embedding <=> ?::vector LIMIT 4` sur `shop_ingredient_embeddings`
filtré aux produits `published`. `POST /diagnostics/analyze` renvoie
désormais `recommendedProductIds` en plus de `analysis`/`scores`.

**Résolution (Laravel)** — `DiagnosticController::recommendedProducts()`
charge les vrais `Product` par ces ids (`with(['variants', 'primaryImage',
'brand'])`, comme avant) et préserve l'ordre de similarité renvoyé
(`sortBy` sur la position dans `recommendedProductIds`, pas l'ordre SQL).
Si la liste est vide (Voyage AI en panne, ou commande d'embedding jamais
lancée — `ProductMatchingService` est "best effort" côté Java, ne fait
jamais échouer le diagnostic lui-même), repli automatique sur l'ancienne
sélection aléatoire filtrée par `skin_types`. Aucun changement côté
`resources/js/pages/storefront/diagnostic.tsx` : la forme de
`recommendedProducts` reste identique, seule son origine change.

## Deux bugs trouvés en testant en conditions réelles (pas en test unitaire)

Comme pour le contrat RabbitMQ (voir
[12-contrat-rabbitmq-laravel.md](12-contrat-rabbitmq-laravel.md)), les tests
unitaires des deux côtés passaient alors que la vraie boucle échouait
encore :

1. **Compte Anthropic sans crédit** au premier essai — pas un bug de code,
   juste un compte à recharger. A produit un `502` propre côté Laravel
   (`{"error": "Analyse IA indisponible"}` affiché comme erreur de
   formulaire), confirmant que la gestion d'échec fonctionnait avant même
   d'avoir un vrai succès à montrer.
2. **Après recharge, un vrai bug côté Spring Boot** : `claude-sonnet-5`
   renvoie un bloc "extended thinking" avant le bloc texte dans sa réponse
   (activé par défaut, sans même le demander) — le code y lisait le
   mauvais bloc et n'y trouvait jamais de JSON. Invisible en test unitaire
   (qui teste le parsing JSON isolément, jamais l'extraction depuis une
   vraie réponse Anthropic). Détail complet et fix côté Java :
   `kbeauty-ai-core-service/docs/05-diagnostic-vision-claude.md`.

Après ces deux corrections, le chemin de succès a été vérifié depuis le
vrai navigateur (upload réel sur `/diagnostic-peau`, pas un `curl` direct
sur le microservice) : analyse + scores affichés, ligne insérée dans
`diagnostic_request` (Neon), événement `diagnostic.created` consommé côté
RabbitMQ avec `status=completed`.

## Comment tester toi-même

1. `composer run dev` (Laravel) + `mvn spring-boot:run` sous WSL
   (`kbeauty-ai-core-service`, RabbitMQ démarré) + une vraie clé Anthropic
   avec du crédit dans `application.properties` (jamais committée).
2. `http://localhost:8000/diagnostic-peau` : choisis un type de peau,
   upload une photo, lance le diagnostic.
3. Si le microservice est éteint ou en erreur : le formulaire affiche un
   message d'erreur sous le champ photo, rien ne casse.
4. Si tout fonctionne : analyse réelle + scores affichés, produits
   recommandés en dessous (inchangé depuis la Phase 3).

## Prochaine étape

Retour à l'Axe 2 (Résilience applicative — Resilience4j) : cette Phase 5
lui donne enfin une cible réelle (l'appel à l'API Anthropic), ce qui
manquait quand l'axe avait été évalué comme prématuré (voir
[07-axes-hors-programme.md](07-axes-hors-programme.md)).
