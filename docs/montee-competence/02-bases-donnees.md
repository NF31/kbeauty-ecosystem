---
title: Référentiel des bases de données & flux
group: Montée en compétence
order: 2
---

← [Retour au sommaire](README.md)

# 2. Référentiel des bases de données & flux (persistance polyglotte)

| Composant | Technologie Retenue | Type / Modèle | Rôle & Justification Technique |
| :--- | :--- | :--- | :--- |
| **Transactions, Stocks, Commandes** | **Neon (PostgreSQL 17)** | Relationnel SQL | Source de vérité absolue. Garantie ACID, verrous pessimistes (`lockForUpdate`), recherche vectorielle (`pgvector`) pour le RAG. Connexion directe (sans pooler en mode *transaction pooling*) car ce mode casse les *prepared statements* et les fonctionnalités de session (`LISTEN/NOTIFY`, variables de session) — pas parce qu'il causerait des « bugs de rollback » (une transaction reste ACID quel que soit le mode de connexion). |
| **Cache local & Queues de la Boutique** | **Valkey 8+** | In-Memory Key-Value | Fork open-source de Redis sous gouvernance Linux Foundation depuis 2024, prévu ici à titre d'expérimentation pour sa compatibilité protocolaire avec Redis (donc avec Laravel Horizon). ⚠️ **Non branché en pratique** (trouvé en vérifiant Phase 1, voir `ROADMAP.md`) : Laravel utilise en réalité un `redis-server` natif (paquet apt, service systemd sur le port 6379) — le conteneur `valkey` du docker-compose tourne et répond, mais n'est jamais sollicité par l'application. Bascule vers le conteneur = choix d'architecture encore à trancher. |
| **Bus de Messages Central** | **RabbitMQ (AMQP)** | Message Broker | Découplage complet inter-services. Sécurise le transfert asynchrone des ordres de diagnostic. Persistance des messages sur disque en cas de panne de Spring Boot. |
| **Data Lake (Scraping brut)** | **Apache Cassandra** | NoSQL Wide-Column | Choix pédagogique pour manipuler un moteur wide-column distribué. ⚠️ À l'échelle réelle de ce projet (une VM de scraping), Cassandra est surdimensionné — un MongoDB ou même des fichiers Parquet directs suffiraient largement. L'intérêt ici est l'apprentissage du modèle de données NoSQL à grande échelle, pas une nécessité de charge. |
| **Moteur Analytique (Business Intelligence)** | **DuckDB + Fichiers Parquet** | Colonnaire / OLAP | Traite et analyse les fichiers Parquet (logs massifs compressés archivés sur Cloudflare R2/Azure) à haute vitesse pour les calculs de KPIs, sans l'infrastructure lourde d'un cluster Hadoop/Spark. |
| **Moteur de recherche Storefront** | **Meilisearch** | Search Engine | Indexation en Rust. Recherche live (debounce 400ms) avec tolérance native aux fautes de frappe. |

> **Note (2026-08-06)** : le package Laravel `related-content` (veille Laravel News) implémente exactement le pattern `pgvector` visé pour le RAG — embeddings précalculés à la sauvegarde (pas de calcul de similarité en temps réel), stockés comme lignes en base pour des lookups en O(1) (~5ms), API OpenAI ou instance Ollama locale pour générer les vecteurs. Pas installable tel quel côté `kbeauty-ai-core-service` (Java, pas Laravel), mais son architecture est une bonne référence concrète à reproduire côté Spring Boot pour la Phase 5 plutôt que de réinventer le pattern d'embeddings à partir de zéro.
