---
title: Phase 6 — Déploiement multi-cloud (Azure + services manages)
group: Montée en compétence
order: 15
---

← [Retour au sommaire](README.md)

# 15. Phase 6 — Déploiement multi-cloud (Azure + services manages)

## Objectif

Jusqu'ici, `kbeauty-ai-core-service` et `kbeauty-ingredients-scraper` ne
tournaient qu'en local (WSL Ubuntu, dépendants d'un `docker-compose.yml`
lancé à la main). Cette phase les fait tourner en continu, sans intervention
manuelle, sur une vraie infra cloud — condition pour que le pipeline
event-driven (Phases 2-5) fonctionne même machine de dev éteinte.

Compte utilisé : **Azure for Students** (abonnement gratuit, 100$ de
crédits/an, `ut-capitole.fr` comme tenant — accès via GitHub Student
Developer Pack). Contrainte découverte en pratique : une police Azure au
niveau du tenant restreint les régions de déploiement à cinq (`spaincentral`,
`polandcentral`, `austriaeast`, `belgiumcentral`, `germanywestcentral`) —
`francecentral`/`westeurope`, pourtant plus proches, sont refusées
(`RequestDisallowedByAzure`). Déployé en `germanywestcentral`, la plus proche
disponible.

## `kbeauty-ai-core-service` → Azure App Service

- **Runtime** : `JAVA|21-java21` (jar Spring Boot standalone, pas de conteneur
  Tomcat séparé — Spring Boot embarque son propre serveur).
- **Bug trouvé en déployant** : `pom.xml` ne déclarait jamais
  `spring-boot-maven-plugin`. `mvn package` produisait donc un jar "thin" de
  36 Ko (les classes du projet seules, sans les dépendances) au lieu d'un jar
  exécutable — invisible en local car le service n'avait jusqu'ici tourné
  que via l'IDE (exécution directe de la classe `Application`). Corrigé côté
  `kbeauty-ai-core-service` (repo séparé, PR #14) : jar exécutable de 56 Mo
  après correction (`Main-Class:
  org.springframework.boot.loader.launch.JarLauncher`).
- **RabbitMQ managé** : Azure n'a pas d'offre RabbitMQ native. Choix :
  **CloudAMQP** (plan gratuit "Little Lemur", AWS EU-West-3 Paris — proximité
  géographique privilégiée plutôt que colocalisation stricte avec Azure ;
  latence cross-cloud négligeable pour ce volume de messages). Le
  `docker-compose.yml` local (`kbeauty-ecosystem`) reste utilisé en dev.
- **Neon (Postgres)** : la base PostgreSQL managée de l'écosystème
  (`DB_URL` posé en variable d'environnement, comme les autres secrets).
- **Secrets** : toutes les valeurs sensibles (clé Anthropic, clé Voyage AI,
  identifiants Neon/CloudAMQP, clé interne partagée) posées via
  `az webapp config appsettings set` — jamais commit, jamais dans l'image.
- **Vérification** : `GET /hello` → `200 kbeauty-ai-core-service is running`.
  Le fait que cette route réponde confirme que tout le contexte Spring Boot a
  démarré sans erreur (une connexion Neon ou RabbitMQ cassée au démarrage
  aurait fait échouer le contexte entier, pas seulement les routes qui en
  dépendent).

## `kbeauty-shop` ↔ `kbeauty-ai-core-service` — connexion inter-cloud

Deux variables posées sur l'environnement `production` Laravel Cloud
(`AI_CORE_SERVICE_URL` → URL Azure App Service, `AI_CORE_INTERNAL_KEY` →
même valeur que côté Java) puis redéploiement pour les prendre en compte.
Testé via `cloud tinker` (`GET /diagnostics` avec le header
`X-Internal-Api-Key`) : `200 OK`, liste des diagnostics existants renvoyée —
confirme l'authentification server-to-server et la connectivité réseau
Laravel Cloud → Azure. Test utilisateur réel ensuite via
`/diagnostic-peau` : le service a correctement **rejeté** une image non
conforme (capture d'écran au lieu d'une photo de visage), preuve que la
validation par l'API vision Claude fonctionne de bout en bout, pas
seulement le chemin "succès".

## `kbeauty-ingredients-scraper` → conteneurisation + Astra DB direct

- **Bug d'archi trouvé en préparant le déploiement** : `CassandraPipeline`
  (`ingredients_scraper/pipelines.py`) était codé en dur pour se connecter
  au Cassandra **local** (`127.0.0.1:9042`) — inutilisable en conteneur
  cloud où aucun Cassandra local n'existe. La synchronisation vers Astra DB
  se faisait jusque-là en 2 temps via un script manuel séparé
  (`scripts/sync_astra.py`). Corrigé (PR #7, repo séparé) : le pipeline
  détecte `ASTRA_TOKEN` dans l'environnement et bascule sur une connexion
  cloud directe (keyspace `default_keyspace` — seul disponible sur le tier
  Astra Serverless gratuit, contrainte différente du `kbeauty_ingredients`
  utilisé en local) ; comportement local inchangé si absent.
- **Astra DB découvert en hibernation** : le tier gratuit met les instances
  en veille après inactivité — `401 Unauthorized` sur le service de
  métadonnées, pas une erreur de token. Résolu via "Resume" sur le dashboard
  Astra (délai de propagation de quelques minutes).
- **`Dockerfile`** ajouté (`python:3.13-slim`, dépendances système
  `lxml`/`cryptography`, `ENTRYPOINT scrapy crawl uniikon_gammes`) — testé
  en local avec un crawl complet avant de pousser sur Azure : 78 pages,
  335 items, 78/78 réponses `200`, données confirmées dans Astra (67
  products, 5 gammes — écriture idempotente par clé primaire, donc pas de
  doublons en re-crawlant).
- **Registre** : **Azure Container Registry** (`kbeautyscraperacr*.azurecr.io`).
  `az acr build` (build cloud) refusé sur cet abonnement étudiant
  (`TasksOperationsNotAllowed`) — build + push en local via `az acr login`
  (auth AAD) à la place.
- **Exécution planifiée** : **Azure Container Apps Jobs** (cron natif,
  facturé au temps d'exécution réel plutôt qu'un serveur qui tourne en
  continu — cohérent avec la nature ponctuelle d'un crawl quotidien).
  Remplace le cron utilisateur local (`scripts/run_crawl.sh`, Phase 4).

## Ce qui reste sur l'infra locale

Redis/Valkey (`kbeauty-ecosystem`) et SonarQube ne sont pas hébergés en
continu — le premier n'est utilisé par aucun service en prod pour l'instant
(migration vers **Azure Cache for Redis** si un besoin réel apparaît), le
second est un outil de scan ponctuel (CI/dev), pas un service applicatif.

## Enseignement (portée MIAGE)

Les deux bugs trouvés dans cette phase (`pom.xml` sans plugin Spring Boot,
pipeline câblé en dur sur `localhost`) n'étaient visibles qu'en essayant
réellement de déployer — aucun test local ne les aurait révélés puisque le
code fonctionnait très bien en dev. Ça illustre concrètement pourquoi
"ça marche sur ma machine" ne suffit pas : la préparation au déploiement
(configuration externalisée, jar/image autonomes) fait partie du travail,
pas une formalité à la fin.
