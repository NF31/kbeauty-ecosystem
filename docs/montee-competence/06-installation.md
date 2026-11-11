---
title: Manuel d'installation des composants
group: Montée en compétence
order: 6
---

← [Retour au sommaire](README.md)

# 6. Manuel d'installation des composants (WSL Ubuntu)

## 📂 A. Infrastructure Commune : `docker-compose.yml`

```yaml
version: '3.8'

services:
  cassandra:
    image: cassandra:latest
    container_name: kbeauty_cassandra
    ports:
      - "9042:9042"
    volumes:
      - cassandra_data:/var/lib/cassandra
    environment:
      - CASSANDRA_CLUSTER_NAME=KBeautyBigDataCluster
    networks:
      - kbeauty_network

  rabbitmq:
    image: rabbitmq:3-management-alpine
    container_name: kbeauty_rabbitmq
    ports:
      - "5672:5672"   # Port AMQP
      - "15672:15672" # Dashboard Web (guest / guest)
    volumes:
      - rabbitmq_data:/var/lib/rabbitmq
    networks:
      - kbeauty_network

  valkey:
    image: bitnami/valkey:latest
    container_name: kbeauty_valkey
    ports:
      - "6379:6379" # Port compatible avec la configuration Redis de Laravel Horizon
    environment:
      - ALLOW_EMPTY_PASSWORD=yes # Dev uniquement — l'image Bitnami refuse de demarrer sans mot de passe ni ce flag
    volumes:
      - valkey_data:/bitnami/valkey/data
    networks:
      - kbeauty_network

  sonarqube:
    image: sonarqube:community
    container_name: kbeauty_sonarqube
    ports:
      - "9000:9000" # Interface d'analyse de qualité de code
    volumes:
      - sonarqube_data:/opt/sonarqube/data
      - sonarqube_extensions:/opt/sonarqube/extensions
    networks:
      - kbeauty_network

volumes:
  cassandra_data:
  rabbitmq_data:
  valkey_data:
  sonarqube_data:
  sonarqube_extensions:

networks:
  kbeauty_network:
    driver: bridge
```

*Commandes d'exécution dans votre terminal Ubuntu :*
```bash
docker compose up -d
docker compose ps
```

## 📁 B. Configuration du Micro-service Java Spring Boot (`pom.xml`)

`~/projects/kbeauty-ai-core-service` — dépendances réellement utilisées aujourd'hui (2026-08-10, après les Axes 1 et 2 hors programme). L'OpenAPI/Springdoc et Lombok, envisagés au départ, n'ont toujours pas été ajoutés (dernier point restant de la Phase 2, voir [`ROADMAP.md`](ROADMAP.md)) :

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.4.1</version>
        <relativePath/>
    </parent>
    <groupId>com.kbeauty</groupId>
    <artifactId>ai-core-service</artifactId>
    <version>1.0.0</version>
    <name>ai-core-service</name>
    <description>Moteur IA sémantique et RAG pour boutique e-commerce</description>
    <properties>
        <java.version>21</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-jpa</artifactId>
        </dependency>
        <dependency>
            <groupId>org.postgresql</groupId>
            <artifactId>postgresql</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-amqp</artifactId>
        </dependency>
        <dependency>
            <!-- Validation des evenements RabbitMQ contre contracts/rabbitmq/*.schema.json
                 avant publication (Axe 1 hors programme). -->
            <groupId>com.networknt</groupId>
            <artifactId>json-schema-validator</artifactId>
            <version>1.5.6</version>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <!-- Circuit breaker + retry sur l'appel a l'API Anthropic (Axe 2 hors programme). -->
            <groupId>io.github.resilience4j</groupId>
            <artifactId>resilience4j-spring-boot3</artifactId>
            <version>2.4.0</version>
        </dependency>
        <dependency>
            <!-- Requis pour que Spring proxy (AOP) les methodes annotees
                 @CircuitBreaker/@Retry - sans ce starter, les annotations
                 sont silencieusement ignorees. -->
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-aop</artifactId>
        </dependency>
    </dependencies>
</project>
```

Les deux dernières (`resilience4j-spring-boot3`, `spring-boot-starter-aop`) et `json-schema-validator` viennent des axes hors programme (voir [07-axes-hors-programme.md](07-axes-hors-programme.md)), pas de la Phase 2 initiale — détail complet côté Spring Boot dans `kbeauty-ai-core-service/docs/04-contrat-donnees-json-schema.md` et `kbeauty-ai-core-service/docs/06-resilience-anthropic.md` (repo séparé).

*Compilation initiale sous Linux :*
```bash
mkdir -p src/main/java/com/kbeauty/aicore src/main/resources
mvn clean compile
```

## 📁 C. Configuration du Robot Scrapy Python

Repo réel : `kbeauty-ingredients-scraper` (module Python `ingredients_scraper`, pas `core_scraper`) — voir [`10-phase4-scraping-cassandra.md`](10-phase4-scraping-cassandra.md) pour le détail de ce qui a été construit dessus.

```bash
cd ~/projects/kbeauty-ingredients-scraper
python3 -m venv .venv
source .venv/bin/activate
pip install scrapy cassandra-driver
scrapy startproject ingredients_scraper .
```

`scrapy-playwright`, `pika` et `python-dotenv` envisagés au départ ne sont pas encore installés — à ajouter quand la Phase 4 avancée (JS rendering, social listening) démarrera réellement (dernier point non coché de la Phase 4).

## 📁 D. Interface Next.js — abandonnée pour la page diagnostic

> Décision (2026-08-02, voir [`ROADMAP.md`](ROADMAP.md) et [`09-phase3-diagnostic-inertia.md`](09-phase3-diagnostic-inertia.md)) : la page diagnostic utilise Inertia (React déjà intégré au monolithe Laravel), pas un frontend Next.js séparé — un pont Sanctum + Next.js aurait ajouté de la complexité sans bénéfice produit pour cette fonctionnalité précise. Next.js reste une option pour un futur découplage frontend (Phase 6, dashboard analytics) ou un projet dédié si l'objectif est de pratiquer Next.js pour lui-même — pas de commande d'installation à date, cette section n'est plus d'actualité pour le diagnostic peau.
