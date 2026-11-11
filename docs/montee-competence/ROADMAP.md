---
title: Roadmap — Montée en compétence
group: Montée en compétence
order: 8.5
---

← [Retour au sommaire](README.md)

# Roadmap — Montée en compétence (prép. Master MIAGE)

> Séquencement réaliste du dossier technique. Objectif : livrer un jalon fonctionnel de bout en bout avant d'ouvrir le suivant, plutôt que de démarrer les 6 en parallèle et n'en finir aucun. Le projet Kbeauty en production (Laravel/Inertia) n'est pas touché — ces services se connectent en périphérie, à titre expérimental.

## Principe d'ordonnancement

1. **Fondations SI avant code** (modélisation, infra) — c'est ce que MIAGE évalue le plus, et ça structure tout le reste.
2. **Un seul microservice qui tourne réellement** avant d'en ajouter un deuxième.
3. **L'IA (diagnostic peau) en dernier** — c'est la brique la plus coûteuse/floue (budget API, prompt engineering), elle ne doit pas bloquer le reste.

---

## Phase 0 — Cadrage & modélisation SI (J1) — [x] Fait (2026-09-04)

Dossier complet : [14-phase0-modelisation.md](14-phase0-modelisation.md) + [00-portfolio.md](00-portfolio.md).
Fait **après** le code, pas avant — assumé : les diagrammes décrivent l'existant (Phases 1-5), le
backlog est rétro-documenté pour les 3 premiers sprints et prospectif pour le 4ᵉ.

- [x] BPMN 2.0 : `tunnel d'achat Stripe` + `circuit asynchrone du diagnostic de peau`. Fichiers
  `.bpmn` éditables (`diagrams/*.bpmn`, extension VS Code `bpmn-io`) + rendu Mermaid de secours
  dans le `.md`.
- [x] UML : diagramme de séquence de l'analyse d'un diagnostic (appel inter-service authentifié
  `X-Internal-Api-Key` + branche asynchrone RabbitMQ — le pont Next.js/jeton initialement prévu
  ici a été abandonné dès la Phase 3 au profit d'Inertia), diagramme de classes JPA
  (`kbeauty-ai-core-service`) + diagramme de classes de la frontière côté `kbeauty-shop`.
- [x] Modèle C4 (ajout au périmètre initial) : contexte, conteneurs, composants du microservice.
- [x] Backlog : 6 épics, 16 user stories estimées en points, découpées en 4 sprints de 2 semaines
  (S1-S3 livrés = Phases 1-5, S4 = US14/15/16 = Phase 2 dernier item + Phase 6).
- [x] README portefeuille (`00-portfolio.md` + `~/projects/README.md`) : les 4 dépôts, leurs rôles,
  comment ils se parlent.

**Livrable** : dossier de conception + backlog priorisé, tracés au code (section 6 de
[14-phase0-modelisation.md](14-phase0-modelisation.md)).

## Phase 1 — Infra commune (J2) — ~2-3 jours — [x] Fait (2026-08-10)

- [x] `docker-compose.yml` (Valkey, RabbitMQ, Cassandra, SonarQube) sous WSL Ubuntu — existait déjà dans `kbeauty-ecosystem/docker-compose.yml` (créé en amont pour les Phases 2/4/5), jamais coché ici
- [x] Vérifier chaque conteneur individuellement (2026-08-10) : RabbitMQ (dashboard `:15672` → 200 OK), SonarQube (`:9000` → `status: UP`), Cassandra (`cqlsh -e "describe cluster"` → répond), Valkey (`valkey-cli PING` → `PONG`). Cassandra/SonarQube/Valkey sont gourmands en RAM (2-4 Go chacun, VM WSL limitée à ~5.7 Go) : arrêtés juste après vérification, seul RabbitMQ tourne en continu (utilisé par les Phases 2-5)
- [x] Premier scan SonarQube sur `kbeauty-shop` (2026-08-10) — baseline : 31 248 lignes de code, 2 bugs (fiabilité C), 3 vulnérabilités (sécurité C), 227 code smells, 5.4% de duplication, maintenabilité A. Config dans `sonar-project.properties` (nouveau, à la racine)

**Livrable** : infra locale qui tourne, scan Sonar du projet existant fait.

**Trouvé en vérifiant (2026-08-10)** : Laravel utilise en réalité un `redis-server` natif (paquet apt, service systemd, port 6379), pas le conteneur `valkey` du docker-compose — `.env` pointe `REDIS_HOST=127.0.0.1` avec `CACHE_STORE=redis` et `QUEUE_CONNECTION=redis`, mais rien ne force ce trafic vers le conteneur Docker. Le conteneur `valkey` existe et répond, mais n'est jamais réellement sollicité par l'application. Pas corrigé ici (bascule vers le conteneur = choix d'archi à trancher, pas une correction de doc) — juste documenté pour ne pas le découvrir plus tard par surprise.

## Phase 2 — Premier microservice end-to-end (J4 réduit) — ~1-2 semaines

Objectif : un Spring Boot minimal qui **lit/écrit réellement** dans Neon et **publie un message RabbitMQ** — sans IA, sans Next.js. C'est le noyau qui prouve que l'event-driven fonctionne.

- [x] `kbeauty-ai-core-service` : squelette Spring Boot (pom.xml corrigé), connexion Neon via `application.properties`
- [x] Une entité JPA simple (ex: `DiagnosticRequest`) + un endpoint REST `POST /diagnostics` qui l'enregistre
- [x] `@RabbitListener` qui consomme un message de test et log le résultat — branché en vrai au producteur (`DiagnosticEventPublisher`/`DiagnosticEventListener`), pas juste un test isolé
- [ ] Contrat OpenAPI via Springdoc, testé dans Swagger UI

**Livrable** : `curl POST /diagnostics` → ligne en base Neon → message publié dans RabbitMQ → consommé et loggé. Bout en bout, sans façade.

**Point de contrôle** : si cette phase prend plus de 3 semaines, il vaut mieux réduire le périmètre (ex. sauter JPA et écrire du SQL natif) que de laisser traîner.

## Phase 3 — Page diagnostic en Inertia (J5) — ~3-5 jours

> Décision (2026-08-02) : pas de pont Next.js pour cette fonctionnalité. Inertia fait déjà tourner du React moderne dans le monolithe Laravel (composants, hooks, SSR optionnel) — un pont Sanctum + Next.js séparé n'aurait ajouté que de la complexité sans bénéfice produit. Next.js est repoussé à un morceau où une vraie séparation frontend a du sens (ex. Phase 6, dashboard analytics découplé), ou à un projet dédié si l'objectif est de pratiquer Next.js pour lui-même.

- [x] Route Laravel dédiée (`web.php`, middleware `auth` classique) qui rend une page Inertia `Diagnostic/Show` — `GET/POST diagnostic-peau` dans `routes/storefront.php`
- [x] Contrôleur qui appelle `kbeauty-ai-core-service` (Phase 2) pour créer le `DiagnosticRequest` et passe les données en props Inertia — `Storefront\DiagnosticController` + `AiCoreDiagnosticClient`
- [x] Rate limiting via le middleware Laravel standard (`throttle:3,60`) sur la route — le garde-fou doit exister dès le début, même avec un diagnostic bidon
- [x] Bouton "Ajouter au panier" sur la page qui appelle directement `CartService` (même contrôleur, pas de redirection inter-app)

**Livrable** : clic depuis la boutique → page diagnostic Inertia → panier peuplé. Le contenu du diagnostic peut être bidon (hardcodé) à ce stade — l'objectif est le flux, pas l'IA.

## Phase 4 — Data engineering (J3) — ~1-2 semaines, en parallèle possible de la phase 3

- [x] Scrapy spider simple sur un catalogue d'ingrédients (pas encore Reddit/Playwright — commencer par du HTML statique) — [uniikon.com](https://uniikon.com), voir [détail complet](10-phase4-scraping-cassandra.md)
- [x] Pipeline `cassandra-driver` pour pousser les résultats dans Cassandra — deux tables (`gammes`, `products`), local **et** Astra DB ("prod" managée)
- [x] ~~Scrapy-Playwright + social listening~~ — abandonné (2026-08-09) : les avis clients (widget Loox sur uniikon.com) sont le seul contenu JS pertinent trouvé, mais `loox.io` interdit `/widget` dans son `robots.txt`, et Trustpilot (piste de repli) bloque tout via un `Disallow: /` générique. Le projet respecte toujours `robots.txt` (c'est déjà pour ça qu'uniikon.com avait été retenu au départ) — pas de contournement. Redirigé vers une exploitation réelle des données déjà scrapées plutôt que d'insister pour cocher la case Playwright.
- [x] Exploitation des données scrapées (2026-08-09) : `scripts/analyze_scraped_data.py` (ingrédients INCI les plus fréquents, recouvrement avec le catalogue kbeauty-shop, positionnement prix) et première brique du pipeline RAG (`scripts/embed_ingredients.py`) — 59 listes INCI vectorisées (Voyage AI `voyage-3.5`) dans une table `pgvector` dédiée sur Neon (`uniikon_ingredient_embeddings`), en vue du futur moteur de matching Phase 5.
- [x] Matching réel (2026-09-02) : le diagnostic peau recommande désormais de vrais produits kbeauty-shop par similarité vectorielle (`shop_ingredient_embeddings` + `ProductMatchRepository`/`ProductMatchingService` côté `kbeauty-ai-core-service`), plutôt qu'une sélection aléatoire filtrée par `skin_types` — détail complet dans [11-embeddings-rag-pgvector.md](11-embeddings-rag-pgvector.md) et [13-diagnostic-vision-laravel.md](13-diagnostic-vision-laravel.md).

**Livrable** : spider validé par un crawl complet (78 pages, données visibles dans Cassandra via `cqlsh`). Cron en place (2026-08-07) : `scripts/run_crawl.sh` dans `kbeauty-ingredients-scraper`, installé en crontab utilisateur quotidien à 3h — s'assure que Cassandra tourne avant de lancer le spider, log horodaté dans `logs/`. Phase 4 close : voir ci-dessus pour l'issue de Scrapy-Playwright et l'exploitation des données.

## Phase 5 — Brancher l'IA réelle — ~2-3 semaines (le plus incertain, prévoir buffer) — [x] Fait (2026-08-10)

- [x] Choisir l'API vision/LLM : Claude (Anthropic), `claude-sonnet-5` — coût réel non encore suivi dans la durée (juste vérifié négligeable par appel de test), pas de budget/quota formalisé
- [x] Endpoint Spring Boot qui appelle l'API IA, traite l'image en mémoire uniquement (RGPD — jamais persistée)
- [x] Persistance des scores anonymisés uniquement (`rougeurs: 0%`, etc. — `diagnostic_request.scores_json`)
- [x] Brancher sur le pipeline RabbitMQ de la Phase 2

**Livrable** : diagnostic réel de bout en bout, vérifié depuis le vrai formulaire `/diagnostic-peau` (upload photo → Spring Boot → Claude vision → Neon → RabbitMQ → consumer Laravel). Détail côté Java : `kbeauty-ai-core-service/docs/05-diagnostic-vision-claude.md` (repo séparé) ; côté Laravel : [13-diagnostic-vision-laravel.md](13-diagnostic-vision-laravel.md). Deux bugs trouvés uniquement en testant en conditions réelles (compte Anthropic sans crédit, puis un bloc "extended thinking" mal géré côté parsing Java) — voir le détail dans ces deux docs.

## Phase 6 — Déploiement & Analytics/CI-CD (J6) — ~1-2 semaines

- [x] Déploiement multi-cloud (2026-09-10) : `kbeauty-ai-core-service` sur **Azure App
  Service** (pas Container Apps comme prévu initialement — App Service suffit pour un
  service HTTP unique, pas besoin de l'orchestration Container Apps), RabbitMQ managé
  via **CloudAMQP**, `kbeauty-ingredients-scraper` conteneurisé et planifié via **Azure
  Container Apps Jobs** (cron, adapté à un job ponctuel plutôt qu'un serveur continu).
  Deux bugs de déploiement trouvés et corrigés en chemin (jar Spring Boot non
  exécutable, pipeline Cassandra câblé en dur sur localhost) — détail complet dans
  [15-phase6-deploiement-azure.md](15-phase6-deploiement-azure.md).
- [ ] Export Parquet des données anonymisées, requêtes DuckDB pour 2-3 KPIs concrets
- [x] GitHub Actions : Pest (PHP, déjà en place) + JUnit (Java, nouveau workflow) + scan
  SonarCloud automatique sur les deux repos (2026-09-10) — détail complet dans
  [17-cicd-tests-sonarcloud.md](17-cicd-tests-sonarcloud.md).

**Livrable** : `kbeauty-ai-core-service` et `kbeauty-ingredients-scraper` tournent en continu
sans intervention manuelle (fait) ; pipeline CI qui tourne sur push (fait) + dashboard KPI
basique (restant).

## Phase 7 — Microservice de notifications transactionnelles (NestJS) — [x] Fait (2026-10-14), flux vérifié de bout en bout

Objectif : découpler l'envoi des notifications (aujourd'hui en dur dans
`app/Notifications/` du monolithe) dans un microservice NestJS dédié, consommant
RabbitMQ sur le même principe que l'intégration SAV (Axe hors programme ci-dessous).
Détail complet dans [21-notifications-service.md](21-notifications-service.md).

- [x] Scaffold du projet : repo `kbeauty-notifications-service` créé, `nest new`
  (NestJS v12, ESM, Node 24, Vitest), CI gitleaks + lint/test/build en place.
- [x] Consumer RabbitMQ : décision révisée en cours de route — pas
  `@nestjs/microservices` (son transport RMQ ne se branche pas naturellement sur un
  exchange + routing key déjà gérés par un producteur externe non-Nest), mais
  `amqp-connection-manager`/`amqplib` directement, même principe que
  `sav-ticketing-php`. File `notifications.newsletter` sur `kbeauty.exchange`.
- [x] Contrat JSON Schema par type d'événement : Ajv (draft 2020-12), vérifié à la
  réception, testé (4 tests). `contracts/check-sync.sh` généralisé côté kbeauty-shop
  pour vérifier plusieurs schémas/dépôts.
- [x] Déduplication : `node:sqlite` (natif Node 24, aucune dépendance ajoutée),
  contrainte d'unicité sur `subscriberId`.
- [x] Publication réelle côté `kbeauty-shop` : `NewsletterController` publie
  `newsletter.subscription_requested` dans l'outbox (derrière
  `NOTIFICATIONS_INTEGRATION_ENABLED`, false par défaut), en plus de l'email direct
  existant (conservé, pas remplacé).
- [x] Flux de bout en bout vérifié en conditions réelles : inscription → outbox →
  RabbitMQ (compte `kbeauty_shop`) → consumer `kbeauty-notifications-service`
  (compte `notifications`, droits limités) → déduplication. Comptes RabbitMQ
  vérifiés refusés hors de leur périmètre dans les deux sens.
- [x] Envoi via Resend : code écrit (`EmailService`), journalise au lieu d'envoyer si
  `RESEND_API_KEY` absent. Testé avec un vrai envoi depuis le poste
  local : aucune erreur, `EmailService` confirme l'envoi, à vérifier côté boîte
  de réception (la clé est en mode *send-only*, pas de lecture possible via l'API).

**Livrable** : un événement publié par kbeauty-shop déclenche un email réel envoyé
par `kbeauty-notifications-service`, sans que le monolithe sache comment l'email a
été composé ni envoyé. Entièrement atteint et vérifié de bout en bout.

---

## Ce qu'on ne fait PAS en premier (pièges à éviter)

- Ne pas démarrer Cassandra + Spring Boot + Next.js + Scrapy la même semaine — c'est la garantie de finir avec 4 chantiers à moitié faits.
- Ne pas attendre d'avoir l'IA qui marche pour construire le pont Laravel↔Next.js (Phase 3) — c'est indépendant.
- Ne pas sauter la Phase 0 (modélisation) pour « aller plus vite au code » — c'est justement ce qui a de la valeur pour MIAGE, et ça évite de recoder une structure JPA mal pensée.

## Prochaine étape immédiate

Phases 1, 2, 3, 4 et 5 fonctionnelles de bout en bout (infra Docker vérifiée + baseline SonarQube, microservice Spring Boot + Neon + RabbitMQ, page diagnostic Inertia connectée au panier avec une vraie analyse IA, spider + pipeline Cassandra local/Astra). **Phase 0 (cadrage & modélisation SI) faite le 2026-09-04** ([14-phase0-modelisation.md](14-phase0-modelisation.md) : BPMN, UML, C4, backlog + traçabilité au code). **Déploiement multi-cloud fait le 2026-09-10** ([15-phase6-deploiement-azure.md](15-phase6-deploiement-azure.md) : `kbeauty-ai-core-service` sur Azure App Service + CloudAMQP, `kbeauty-ingredients-scraper` conteneurisé sur Azure Container Apps Jobs). Restent : le contrat OpenAPI/Springdoc (dernier point Phase 2) puis le reste de Phase 6 (export Parquet + KPIs DuckDB, GitHub Actions Pest/JUnit/Sonar) — ce sont exactement les user stories US14/US15/US16 du Sprint 4 du backlog.

**Décision (2026-08-07)** : avant de reprendre Phase 0, deux axes hors programme retenus en priorité (voir [07-axes-hors-programme.md](07-axes-hors-programme.md)) car ils comblent un vrai trou du design event-driven actuel, effort faible :
- [x] Axe 1 — Contrat de données entre services (2026-08-09) : schéma JSON Schema validé sur les messages RabbitMQ Spring Boot ↔ Laravel, voir [détail complet](12-contrat-rabbitmq-laravel.md) (journal côté Spring Boot : `kbeauty-ai-core-service/docs/04-contrat-donnees-json-schema.md`, repo séparé)
- [x] Axe 2 — Résilience applicative (2026-08-10) : Resilience4j (circuit breaker + retry avec backoff exponentiel) sur l'appel à `api.anthropic.com` dans `AnthropicVisionService`, débloqué par la Phase 5 ci-dessus — détail complet côté Spring Boot : `kbeauty-ai-core-service/docs/06-resilience-anthropic.md` (repo séparé)

Les deux axes hors programme priorisés sont maintenant faits, et **Phase 0 est faite** (2026-09-04, [14-phase0-modelisation.md](14-phase0-modelisation.md)) — priorité avait été donnée au code jusque-là, la modélisation documente donc l'existant plutôt qu'une cible.

**Intégration SAV faite** (2026-10-12, [20-integration-sav-rabbitmq.md](20-integration-sav-rabbitmq.md)) : un cinquième dépôt, `sav-ticketing-php`, connecté via RabbitMQ sur le pattern outbox/contrat JSON Schema/idempotence. **Phase 7 faite** (2026-10-14, [21-notifications-service.md](21-notifications-service.md)) : sixième dépôt, `kbeauty-notifications-service` (NestJS), flux vérifié de bout en bout en conditions réelles (inscription newsletter → outbox → RabbitMQ → consumer → déduplication). Seul point non couvert : un envoi Resend réel (code en place, pas de compte Resend de test en local pour le vérifier).
