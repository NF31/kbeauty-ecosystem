---
title: Structure de dossiers sous WSL Ubuntu
group: Montée en compétence
order: 8
---

← [Retour au sommaire](README.md)

# 8. Structure de dossiers sous WSL Ubuntu

> Tous les services (hors boutique Laravel/Inertia, qui reste sur Windows/le repo actuel) tournent depuis WSL Ubuntu pour éviter la couche de traduction Docker Desktop↔WSL2 et coller à l'environnement de production (Azure Container Apps et la VM de scraping sont Linux).

## Arborescence réelle

> Contrairement à une première version de ce document (repos imbriqués dans `kbeauty-ecosystem/`), la structure retenue en pratique est **des clones siblings** sous `~/projects/` — plus simple à cloner/pusher indépendamment un par un, chacun avec son propre historique Git et son propre remote GitHub. `kbeauty-ecosystem/` ne contient que l'infra partagée (Docker Compose), pas de code applicatif.

```
~/projects/
├── kbeauty-shop/                    # Boutique Laravel/Inertia (aussi clonée sous Windows, tenue synchronisée)
│   └── docs/montee-competence/      # Cette documentation
│
├── kbeauty-ecosystem/                # Infra commune uniquement, pas de code applicatif
│   ├── docker-compose.yml           # Cassandra, RabbitMQ, Valkey, SonarQube
│   ├── .env                          # Variables partagées (jamais commit)
│   └── README.md
│
├── kbeauty-ai-core-service/          # Microservice Java Spring Boot (Phase 2)
│   ├── src/main/java/com/kbeauty/aicore/
│   │   ├── controller/               # Endpoints REST (DiagnosticController, HealthController)
│   │   ├── repository/               # Accès JPA/Hibernate vers Neon
│   │   ├── entity/                   # Entités JPA (DiagnosticRequest)
│   │   ├── amqp/                     # Listener/Publisher RabbitMQ
│   │   └── config/                   # Config Spring (RabbitMQConfig)
│   ├── src/main/resources/application.properties   # (gitignored, .example committé)
│   ├── docs/                          # Journal pédagogique Java/Spring, une entrée par étape
│   └── pom.xml
│
└── kbeauty-ingredients-scraper/      # Robot Python Scrapy (Phase 4)
    ├── .venv/                         # (non versionné)
    ├── .astra-secrets/                # Secure Connect Bundle Astra (non versionné)
    ├── ingredients_scraper/
    │   ├── spiders/uniikon_gammes.py
    │   ├── pipelines.py               # Pipeline vers Cassandra (local + Astra)
    │   ├── items.py
    │   └── settings.py
    ├── scripts/                       # Tests manuels (fixture hors-ligne, insert Astra)
    ├── fixtures/                      # HTML capturé pour tester le parsing sans réseau
    └── scrapy.cfg
```

Pas de `kbeauty-diagnostic-frontend/` Next.js : décision prise en Phase 3 de garder Inertia pour la page diagnostic plutôt qu'un pont Next.js séparé (voir [`ROADMAP.md`](ROADMAP.md) et [`09-phase3-diagnostic-inertia.md`](09-phase3-diagnostic-inertia.md)) — Next.js reste une option pour un futur découplage frontend (Phase 6) ou un projet dédié, pas pour cette fonctionnalité.

## Pourquoi cette structure

- **Des clones siblings**, chacun avec son propre repo GitHub, plutôt qu'un monorepo imbriqué — plus simple à cloner/pusher indépendamment, et ça reflète le fait que chaque service a son propre rythme de vie.
- **Le repo Laravel/Inertia (Kbeauty) reste séparé**, cloné à la fois sous Windows (usage quotidien) et sous WSL Ubuntu (là où tournent les autres services) — ce n'est pas un microservice de cet écosystème, c'est le système existant auquel on se connecte.
- **`kbeauty-ecosystem/` ne contient que l'infra partagée** : un seul `docker-compose.yml` orchestre Cassandra/RabbitMQ/Valkey/SonarQube pour tous les services, sans dupliquer la config dans chaque repo.

## Commandes de mise en place

```bash
mkdir -p ~/projects && cd ~/projects

git clone <url> kbeauty-shop
git clone <url> kbeauty-ecosystem
git clone <url> kbeauty-ai-core-service
git clone <url> kbeauty-ingredients-scraper

cd kbeauty-ecosystem && docker compose up -d
```
