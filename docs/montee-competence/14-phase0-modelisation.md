---
title: Phase 0 — Modélisation SI (BPMN, UML, C4)
group: Montée en compétence
order: 14
---

← [Retour au sommaire](README.md)

# 14. Phase 0 — Cadrage & modélisation du SI

> Fondation d'urbanisation demandée par la [ROADMAP](ROADMAP.md#phase-0--cadrage-j1--1-semaine) et
> jamais posée jusqu'ici (tout a été codé d'abord). C'est le livrable le plus attendu côté MIAGE :
> il documente le **processus métier** (BPMN 2.0), la **structure logicielle** (UML) et
> l'**architecture système** (modèle C4) de l'écosystème distribué déjà construit aux Phases 1 à 5,
> puis en tire un **backlog priorisé** pour le MVP « diagnostic connecté au panier ».
>
> Les diagrammes décrivent l'état **réellement en place** dans le code (au 2026-09-04), pas une
> cible. Chaque section renvoie aux classes concernées pour rester vérifiable.

## Sommaire

1. [Outillage](#1-outillage-extensions-vs-code)
2. [Modèle C4 — architecture système](#2-modèle-c4--architecture-système)
3. [BPMN 2.0 — processus métier](#3-bpmn-20--processus-métier)
4. [UML — structure & dynamique](#4-uml--structure--dynamique)
5. [Backlog — MVP « diagnostic connecté au panier »](#5-backlog--mvp-diagnostic-connecté-au-panier)
6. [Traçabilité modèle ↔ code](#6-traçabilité-modèle--code)

---

## 1. Outillage (extensions VS Code)

Fichiers de diagrammes versionnés avec le code, pas d'outil SaaS. Les extensions sont déclarées
dans `.vscode/extensions.json` à la racine de l'espace de travail (`~/projects/`, hors dépôt —
`.vscode/` est gitignore côté `kbeauty-shop`) : VS Code propose de les installer à l'ouverture du
dossier.

| Besoin | Format | Extension | Rendu GitHub | Pourquoi |
|---|---|---|---|---|
| C4, séquence, classes | Mermaid dans le `.md` | `bierner.markdown-mermaid` *(preview locale ; GitHub rend nativement)* | ✅ natif | texte diffable, zéro binaire, revue en PR |
| BPMN 2.0 | `.bpmn` (XML standard OMG) | `bpmn-io.vs-code-bpmn-io` | ❌ (aperçu dans l'IDE seulement) | vrai BPMN 2.0, importable Camunda Modeler / bizagi |
| Retouche visuelle libre | `.drawio.svg` | `hediet.vscode-drawio` | ✅ (c'est un SVG) | si besoin d'un export image propre pour un rapport |

Les deux processus BPMN sont fournis comme fichiers éditables :

- [`diagrams/tunnel-achat-stripe.bpmn`](diagrams/tunnel-achat-stripe.bpmn)
- [`diagrams/diagnostic-peau-async.bpmn`](diagrams/diagnostic-peau-async.bpmn)

Ils s'ouvrent **rendus** dans l'extension bpmn-io (clic droit → *Open With… → BPMN Editor*). Le
layout est généré automatiquement (lignes = lanes, colonnes = étapes) et peut être réorganisé à la
souris ; la version Mermaid ci-dessous sert de rendu de secours lisible directement dans GitHub.

> **Génération** : [`diagrams/gen_bpmn.py`](diagrams/gen_bpmn.py) produit les deux `.bpmn` (avec
> layout + DI) à partir d'une liste de nœuds/flux Python — `python3 diagrams/gen_bpmn.py`. Modifier
> un processus = éditer la liste et régénérer, ou retoucher le `.bpmn` à la souris dans bpmn-io.
> Les `.bpmn` sont vérifiés au parsing (`bpmn-moddle`, 0 warning) et les 9 blocs Mermaid de cette
> page par `@mermaid-js/mermaid-cli`.

---

## 2. Modèle C4 — architecture système

### Niveau 1 — Contexte

Qui utilise le système, et à quels systèmes externes il est relié.

```mermaid
C4Context
    title Écosystème kbeauty — diagramme de contexte

    Person(client, "Client", "Achète des cosmétiques, veut une recommandation adaptée à sa peau")
    Person(admin, "Équipe kbeauty", "Gère le catalogue, les commandes, les remboursements")

    System(eco, "Écosystème kbeauty", "Boutique e-commerce + moteur de diagnostic IA + extraction de données marché")

    System_Ext(stripe, "Stripe", "Paiement, webhooks de confirmation")
    System_Ext(claude, "API Claude (Anthropic)", "Analyse vision de la photo de peau")
    System_Ext(voyage, "Voyage AI", "Embeddings de texte pour le matching produit")
    System_Ext(resend, "Resend", "Emails transactionnels")
    System_Ext(catalog, "Sites catalogues d'ingrédients", "Sources publiques scrapées (robots.txt respecté)")

    Rel(client, eco, "Navigue, commande, fait un diagnostic", "HTTPS")
    Rel(admin, eco, "Back-office", "HTTPS")
    Rel(eco, stripe, "Crée les sessions de paiement, reçoit les webhooks", "HTTPS")
    Rel(eco, claude, "Envoie la photo (en mémoire), reçoit scores + analyse", "HTTPS")
    Rel(eco, voyage, "Vectorise les requêtes de matching", "HTTPS")
    Rel(eco, resend, "Envoie les emails de confirmation", "HTTPS")
    Rel(eco, catalog, "Extraction quotidienne", "HTTPS / Scrapy")

    UpdateLayoutConfig($c4ShapeInRow="3", $c4BoundaryInRow="2")
```

### Niveau 2 — Conteneurs

Les unités déployables et leurs dépendances de données. Trois dépôts Git distincts
(`kbeauty-shop`, `kbeauty-ai-core-service`, `kbeauty-ingredients-scraper`) + l'infra partagée
(`kbeauty-ecosystem`).

```mermaid
C4Container
    title Écosystème kbeauty — diagramme de conteneurs

    Person(client, "Client", "Navigateur")
    Person(admin, "Équipe kbeauty")

    System_Boundary(eco, "Écosystème kbeauty") {
        Container(web, "kbeauty-shop", "PHP 8.5 / Laravel 13 / Inertia / React / TS", "Catalogue, panier, checkout Stripe, page diagnostic, back-office. Hébergé sur Laravel Cloud")
        Container(horizon, "Workers Horizon", "PHP / Redis", "Jobs asynchrones : webhooks Stripe, emails, décrément stock, création Shipment")
        Container(consumer, "Consumer RabbitMQ", "PHP (commande artisan long-vivante)", "Consomme diagnostic.created, valide contre le JSON Schema partagé")
        Container(aicore, "kbeauty-ai-core-service", "Java 21 / Spring Boot 3.4 / Hibernate", "Analyse vision + matching vectoriel d'ingrédients. Cible : Azure Container Apps")
        Container(scraper, "kbeauty-ingredients-scraper", "Python 3.12 / Scrapy", "Extraction du catalogue d'ingrédients INCI de sites publics")

        ContainerDb(neon, "Neon PostgreSQL", "PostgreSQL 18 + pgvector", "Données transactionnelles (commandes, panier, catalogue) + embeddings d'ingrédients + diagnostics anonymisés")
        ContainerDb(cassandra, "Cassandra / Astra DB", "Cassandra", "Données de marché scrapées (gammes, produits concurrents)")
        ContainerDb(redis, "Redis / Valkey", "Redis", "Cache applicatif + file de jobs Horizon")
        ContainerQueue(rmq, "RabbitMQ", "AMQP", "Bus d'événements entre ai-core-service et kbeauty-shop")
    }

    System_Ext(stripe, "Stripe")
    System_Ext(claude, "API Claude (Anthropic)")
    System_Ext(voyage, "Voyage AI")
    System_Ext(resend, "Resend")

    Rel(client, web, "HTTPS")
    Rel(admin, web, "HTTPS")
    Rel(web, neon, "Lit / écrit", "SQL (TLS)")
    Rel(web, redis, "Cache + dispatch de jobs", "TCP")
    Rel(horizon, redis, "Consomme la file", "TCP")
    Rel(horizon, neon, "Met à jour Order / Payment", "SQL")
    Rel(horizon, resend, "Envoie les emails", "HTTPS")
    Rel(web, stripe, "Checkout Session", "HTTPS")
    Rel(stripe, web, "Webhook checkout.session.completed", "HTTPS")
    Rel(web, aicore, "POST /diagnostics/analyze (+ X-Internal-Api-Key)", "HTTPS")
    Rel(aicore, claude, "Analyse vision", "HTTPS")
    Rel(aicore, voyage, "Embeddings", "HTTPS")
    Rel(aicore, neon, "Persiste le diagnostic, recherche pgvector", "SQL")
    Rel(aicore, rmq, "Publie diagnostic.created", "AMQP")
    Rel(rmq, consumer, "Livre diagnostic.created", "AMQP")
    Rel(consumer, neon, "Journalise", "SQL")
    Rel(scraper, cassandra, "Écrit les pages extraites", "CQL")
    Rel(scraper, neon, "Écrit les embeddings d'ingrédients", "SQL")

    UpdateLayoutConfig($c4ShapeInRow="3", $c4BoundaryInRow="1")
```

> Si le rendu C4 ne s'affiche pas (version de Mermaid trop ancienne), voici la même vue en
> `flowchart`, toujours rendue :

```mermaid
flowchart TB
    client([Client]) -->|HTTPS| web
    admin([Équipe kbeauty]) -->|HTTPS| web
    subgraph eco["Écosystème kbeauty"]
        web["kbeauty-shop<br/>Laravel 13 / Inertia / React"]
        horizon["Workers Horizon<br/>PHP / Redis"]
        consumer["Consumer RabbitMQ<br/>artisan long-vivant"]
        aicore["kbeauty-ai-core-service<br/>Java 21 / Spring Boot"]
        scraper["kbeauty-ingredients-scraper<br/>Python / Scrapy"]
        neon[("Neon PostgreSQL<br/>+ pgvector")]
        cassandra[("Cassandra / Astra")]
        redis[("Redis / Valkey")]
        rmq{{"RabbitMQ"}}
    end
    stripe[[Stripe]]
    claude[[API Claude]]
    voyage[[Voyage AI]]
    resend[[Resend]]

    web --> neon & redis
    web -->|Checkout Session| stripe
    stripe -->|webhook| web
    web -->|dispatch| horizon
    horizon --> redis & neon --> resend
    web -->|POST /diagnostics/analyze<br/>X-Internal-Api-Key| aicore
    aicore --> claude & voyage
    aicore --> neon
    aicore -->|publie diagnostic.created| rmq --> consumer --> neon
    scraper --> cassandra
    scraper -->|embeddings ingrédients| neon
```

### Niveau 3 — Composants (`kbeauty-ai-core-service`)

Découpage interne du microservice Java. Voir le [diagramme de classes](#diagramme-de-classes--cœur-de-kbeauty-ai-core-service) pour les attributs.

```mermaid
flowchart LR
    http["HTTP entrant<br/>kbeauty-shop"] --> filter["InternalApiKeyFilter<br/>(secret partagé, fail-closed,<br/>comparaison temps constant)"]
    filter --> ctrl["DiagnosticController<br/>POST /diagnostics/analyze"]
    ctrl --> vision["AnthropicVisionService"]
    vision --> apiclient["AnthropicApiClient<br/>(Resilience4j : retry + circuit breaker)"]
    apiclient --> claude[[API Claude]]
    ctrl --> matching["ProductMatchingService<br/>(best-effort)"]
    matching --> voyagecli["VoyageEmbeddingClient"] --> voyage[[Voyage AI]]
    matching --> matchrepo["ProductMatchRepository<br/>(SELECT ... ORDER BY embedding &lt;=&gt; ?)"]
    ctrl --> reqrepo["DiagnosticRequestRepository<br/>(JpaRepository)"]
    matchrepo --> neon[("Neon<br/>shop_ingredient_embeddings")]
    reqrepo --> neon2[("Neon<br/>diagnostic_request")]
    ctrl --> publisher["DiagnosticEventPublisher"]
    publisher --> validator["DiagnosticCreatedEventSchemaValidator<br/>(contracts/rabbitmq/*.json)"]
    publisher --> rmq{{RabbitMQ}}
```

---

## 3. BPMN 2.0 — processus métier

**Légende** : `(cercle fin)` événement de début · `(cercle épais)` événement de fin ·
`(cercle double)` événement intermédiaire (message) · `<losange>` passerelle exclusive (XOR) ·
`[rectangle]` tâche · les bandes horizontales sont des **lanes** (qui fait quoi).

### 3.1 Processus A — Tunnel d'achat et paiement Stripe

Existant `kbeauty-shop` (`ARCHITECTURE.md` §4 du dépôt `kbeauty-shop`, privé).
Point clé : la commande ne passe à `paid` **que** sur réception du webhook Stripe côté serveur,
jamais sur le retour navigateur. Le webhook est dédupliqué (idempotence) et rejouable.

Fichier éditable : [`diagrams/tunnel-achat-stripe.bpmn`](diagrams/tunnel-achat-stripe.bpmn)

```mermaid
flowchart TD
    subgraph client["Lane — Client (navigateur)"]
        S(("Panier prêt,<br/>clic Commander")) --> A1["Saisir / choisir<br/>les adresses"]
        A1 --> A2["Valider le<br/>récapitulatif (Payer)"]
        A5["Confirmer le paiement<br/>(Payment Element)"]
        EOK((("Commande payée,<br/>page confirmation")))
    end
    subgraph app["Lane — Application Laravel (Inertia)"]
        L1["Créer Order + Payment<br/>(statut pending)"]
        L2["Créer Checkout Session Stripe<br/>(ui_mode: elements)"]
        L3["Vérifier la signature,<br/>persister webhook_call"]
        G1{"Event déjà traité<br/>avec succès ?"}
        EDUP((("Ignoré<br/>(idempotence)")))
    end
    subgraph stripe["Lane — Stripe"]
        ST1["Autoriser la carte,<br/>créer le PaymentIntent"]
        SW(("checkout.session.completed")):::evt
    end
    subgraph worker["Lane — Worker Horizon (asynchrone)"]
        W1["Order=paid, Payment=succeeded,<br/>repointer provider_payment_id<br/>sur le vrai PaymentIntent"]
        W2["Email confirmation (Resend),<br/>décrément stock, créer Shipment"]
    end

    A2 --> L1 --> L2 --> A5 --> ST1 --> SW --> L3 --> G1
    G1 -->|oui| EDUP
    G1 -->|non| W1 --> W2 --> EOK
    classDef evt fill:#eef,stroke:#88a
```

### 3.2 Processus B — Diagnostic de peau connecté au panier

Circuit synchrone (HTTP `kbeauty-shop` → `kbeauty-ai-core-service`) **plus** une branche
asynchrone (RabbitMQ) consommée séparément. Contraintes : la photo n'est **jamais** persistée
(RGPD), l'appel inter-service exige le secret `X-Internal-Api-Key`, le matching produit est
*best-effort* (une panne Voyage AI ne fait pas échouer le diagnostic).

Fichier éditable : [`diagrams/diagnostic-peau-async.bpmn`](diagrams/diagnostic-peau-async.bpmn)

```mermaid
flowchart TD
    subgraph cl["Lane — Client"]
        DS(("Ouvre<br/>/diagnostic-peau")) --> D1["Choisir type de peau,<br/>envoyer une photo"]
        DC["Ajouter une routine<br/>au panier"]
        DEOK((("Panier peuplé,<br/>tunnel d'achat")))
        D401((("401 — erreur<br/>affichée")))
    end
    subgraph shop["Lane — kbeauty-shop (Laravel)"]
        L1["Valider (image, max 8 Mo),<br/>throttle 3 / 60 min"]
        L2["POST /diagnostics/analyze<br/>+ X-Internal-Api-Key"]
        L3["Rendre la page Inertia :<br/>analyse + produits (ordre similarité)"]
    end
    subgraph ai["Lane — kbeauty-ai-core-service (Spring Boot)"]
        G0{"Clé interne<br/>valide ?"}
        G1{"Photo de visage<br/>exploitable ?"}
        P1["Persister scores anonymisés<br/>+ ids produits<br/>(jamais la photo)"]
        PUB(("Publier<br/>diagnostic.created")):::evt
    end
    subgraph ext["Lane — Services externes"]
        V1["Analyse vision Claude<br/>(image en mémoire)"]
        V2["Embedding requête +<br/>recherche pgvector"]
    end
    subgraph async["Lane — Consumer RabbitMQ (Laravel)"]
        MS(("Message diagnostic.created<br/>reçu")) --> C1["Valider contre<br/>le JSON Schema partagé"]
        GC{"Contrat<br/>respecté ?"}
        CEOK((("Log info, ack")))
        CNACK((("Log warning,<br/>nack sans requeue")))
    end

    D1 --> L1 --> L2 --> G0
    G0 -->|non| D401
    G0 -->|oui| V1 --> G1
    G1 -->|oui| V2 --> P1
    G1 -->|non : pas de matching| P1
    P1 --> PUB --> L3 --> DC --> DEOK
    C1 --> GC
    GC -->|oui| CEOK
    GC -->|non| CNACK
    PUB -. RabbitMQ .-> MS
    classDef evt fill:#eef,stroke:#88a
```

---

## 4. UML — structure & dynamique

### Diagramme de séquence — analyse d'un diagnostic

De l'envoi du formulaire au rendu de la page, branche asynchrone incluse. Reflète
`Storefront\DiagnosticController::analyze`, `AiCoreDiagnosticClient`, le `DiagnosticController`
Java et `ConsumeDiagnosticCreatedEventsCommand`.

```mermaid
sequenceDiagram
    autonumber
    actor U as Client
    participant L as kbeauty-shop<br/>DiagnosticController
    participant AC as AiCoreDiagnosticClient
    participant F as ai-core<br/>InternalApiKeyFilter
    participant J as ai-core<br/>DiagnosticController
    participant AV as AnthropicVisionService
    participant CL as API Claude
    participant PM as ProductMatchingService
    participant DB as Neon (PostgreSQL)
    participant MQ as RabbitMQ
    participant CO as Consumer RabbitMQ (Laravel)

    U->>L: POST /diagnostic-peau (skin_type, photo)
    L->>L: validate(image, max 8192 Ko) + throttle 3/60
    L->>AC: analyzeSkin(file, skinType)
    AC->>J: POST /diagnostics/analyze (multipart, X-Internal-Api-Key)
    J->>F: doFilterInternal(request)
    alt clé absente ou invalide
        F-->>AC: 401 Unauthorized
        AC-->>L: null
        L-->>U: page formulaire + erreur "analyse indisponible"
    else clé valide
        F->>J: passe la requête
        J->>AV: analyze(bytes, mediaType, skinType)
        AV->>CL: messages API (image en mémoire, jamais sur disque)
        Note over AV,CL: AnthropicApiClient — Resilience4j<br/>retry backoff expo. puis circuit breaker
        CL-->>AV: { validPhoto, scores, analysis }
        alt validPhoto == true
            J->>PM: recommendProducts(result)
            PM->>CL: (Voyage AI) embedQuery(texte analyse + scores triés)
            PM->>DB: SELECT ... ORDER BY embedding <=> :q LIMIT 4<br/>(shop_ingredient_embeddings)
            DB-->>PM: [products.id ...]
            PM-->>J: List<Long> (ordre de similarité)
        else validPhoto == false
            J->>J: recommendedProductIds = []
        end
        J->>DB: save(DiagnosticRequest: completed, analysis,<br/>scoresJson, recommendedProductIdsJson)
        J->>MQ: publish diagnostic.created<br/>{ diagnosticId, status, occurredAt }
        J-->>AC: 200 { id, analysis, validPhoto, scores, recommendedProductIds }
        AC-->>L: array
        L->>DB: publishedByIds(ids) — sinon repli randomPublishedForSkinType
        L-->>U: Inertia render storefront/diagnostic<br/>{ analysis, scores, recommendedProducts }
    end

    par Branche asynchrone (découplée de la réponse HTTP)
        MQ->>CO: diagnostic.created
        CO->>CO: validate(body) contre diagnostic-created.schema.json
        alt message conforme
            CO->>CO: Log::info + ack
        else contrat non respecté
            CO->>CO: Log::warning + nack(requeue: false)
        end
    end
```

### Diagramme de classes — cœur de `kbeauty-ai-core-service`

```mermaid
classDiagram
    class DiagnosticController {
        +create() DiagnosticRequest
        +list() List~DiagnosticRequest~
        +analyze(image, skinType) ResponseEntity
    }
    class DiagnosticRequest {
        <<@Entity>>
        -Long id
        -String status
        -String analysis
        -String scoresJson
        -String recommendedProductIdsJson
    }
    class DiagnosticRequestRepository {
        <<interface>>
        +save(DiagnosticRequest) DiagnosticRequest
        +findAll() List~DiagnosticRequest~
    }
    class JpaRepository {
        <<Spring Data>>
    }
    class AnthropicVisionService {
        +analyze(bytes, mediaType, skinType) SkinAnalysisResult
    }
    class AnthropicApiClient {
        <<Resilience4j>>
        +send(requestBody) String
    }
    class SkinAnalysisResult {
        <<record>>
        +boolean validPhoto
        +Map~String,Integer~ scores
        +String analysis
    }
    class ProductMatchingService {
        +recommendProducts(SkinAnalysisResult) List~Long~
        ~buildQueryText(SkinAnalysisResult) String
    }
    class VoyageEmbeddingClient {
        +embedQuery(String) float[]
    }
    class ProductMatchRepository {
        +findClosestPublishedProducts(float[], int) List~ProductMatch~
    }
    class ProductMatch {
        <<record>>
        +Long productId
        +double distance
    }
    class DiagnosticEventPublisher {
        +publishDiagnosticCreated(Long, String) void
    }
    class DiagnosticCreatedEvent {
        <<record>>
        +String eventType
        +Long diagnosticId
        +String status
        +Instant occurredAt
    }
    class DiagnosticCreatedEventSchemaValidator {
        +validate(DiagnosticCreatedEvent) void
    }
    class InternalApiKeyFilter {
        <<OncePerRequestFilter>>
        -String expectedKey
        +doFilterInternal(req, res, chain) void
    }

    JpaRepository <|-- DiagnosticRequestRepository
    DiagnosticController --> DiagnosticRequestRepository
    DiagnosticController --> AnthropicVisionService
    DiagnosticController --> ProductMatchingService
    DiagnosticController --> DiagnosticEventPublisher
    DiagnosticRequestRepository ..> DiagnosticRequest
    AnthropicVisionService --> AnthropicApiClient
    AnthropicVisionService ..> SkinAnalysisResult
    ProductMatchingService --> VoyageEmbeddingClient
    ProductMatchingService --> ProductMatchRepository
    ProductMatchRepository ..> ProductMatch
    ProductMatchingService ..> SkinAnalysisResult
    DiagnosticEventPublisher --> DiagnosticCreatedEventSchemaValidator
    DiagnosticEventPublisher ..> DiagnosticCreatedEvent
    InternalApiKeyFilter ..> DiagnosticController : garde /diagnostics/**
```

### Diagramme de classes — frontière côté `kbeauty-shop`

```mermaid
classDiagram
    class DiagnosticController {
        <<Storefront>>
        +index() Response
        +analyze(Request, AiCoreDiagnosticClient, ...) Response
        -recommendedProducts(repo, ids, SkinType) Collection
    }
    class AiCoreDiagnosticClient {
        +analyzeSkin(UploadedFile, string skinType) ?array
    }
    class RecommendedProductRepositoryInterface {
        <<interface>>
        +publishedByIds(ids) Collection
        +randomPublishedForSkinType(SkinType, int) Collection
    }
    class ConsumeDiagnosticCreatedEventsCommand {
        +handle(DiagnosticCreatedEventValidator) int
        -handleMessage(AMQPMessage, validator) void
    }
    class DiagnosticCreatedEventValidator {
        +validate(string json) DiagnosticCreatedEvent
    }
    class SkinType {
        <<enum>>
        Dry
        Oily
        Combination
        Normal
        Sensitive
    }
    class AiCoreService {
        <<external : kbeauty-ai-core-service>>
        +POST /diagnostics/analyze
    }

    DiagnosticController --> AiCoreDiagnosticClient
    DiagnosticController --> RecommendedProductRepositoryInterface
    DiagnosticController ..> SkinType
    ConsumeDiagnosticCreatedEventsCommand --> DiagnosticCreatedEventValidator
    AiCoreDiagnosticClient ..> AiCoreService : HTTP + X-Internal-Api-Key
```

---

## 5. Backlog — MVP « diagnostic connecté au panier »

Objectif du MVP : **un client peut, depuis la boutique, faire analyser une photo de sa peau et
recevoir des produits kbeauty-shop pertinents qu'il ajoute au panier**. Format des stories :
*En tant que … je veux … afin de …*. Estimation en points (suite de Fibonacci), vélocité cible
~20 pts / sprint de 2 semaines.

### Épics

| ID | Épic | Objectif |
|---|---|---|
| E1 | Socle microservice & contrat | Un Spring Boot qui lit/écrit Neon et publie un événement fiable |
| E2 | Analyse vision | Transformer une photo en scores + texte, sans jamais la stocker |
| E3 | Matching produit | Relier le résultat du diagnostic au catalogue réel |
| E4 | Parcours client | Page diagnostic → panier, dans le monolithe Inertia |
| E5 | Robustesse & conformité | Auth inter-service, RGPD, résilience, idempotence |
| E6 | Observabilité & industrialisation | Contrat OpenAPI, CI, déploiement |

### User stories

| ID | Story | Épic | Pts | Sprint | Definition of Done |
|---|---|---|---|---|---|
| US1 | En tant que dev, je veux un endpoint `POST /diagnostics` qui persiste une ligne en base Neon, afin d'avoir un socle vérifiable | E1 | 3 | 1 | `curl` → ligne visible dans Neon ; test JUnit vert |
| US2 | En tant que dev, je veux publier un événement `diagnostic.created` sur RabbitMQ à la création, afin de découpler les traitements aval | E1 | 5 | 1 | message visible dans la file ; `@RabbitListener` de test le loggue |
| US3 | En tant qu'architecte, je veux un contrat **JSON Schema versionné** partagé pour cet événement, afin que producteur et consommateur ne divergent pas | E1/E5 | 5 | 1 | schéma dans `contracts/` ; publication rejetée si non conforme ; `check-sync.sh` |
| US4 | En tant que client, je veux envoyer une photo + mon type de peau depuis `/diagnostic-peau`, afin de lancer une analyse | E4 | 5 | 1 | page Inertia ; validation `image`, max 8 Mo ; `throttle:3,60` |
| US5 | En tant que client, je veux que ma photo ne soit **jamais stockée**, afin que ma vie privée soit respectée | E2/E5 | 3 | 2 | image lue en mémoire (`getBytes()`), aucun `transferTo` ; test le prouve ; mention RGPD dans la doc |
| US6 | En tant que client, je veux une analyse (scores + texte type dermatologue) à partir de ma photo, afin de comprendre l'état de ma peau | E2 | 8 | 2 | appel API Claude ; `SkinAnalysisResult{validPhoto, scores, analysis}` persisté anonymisé |
| US7 | En tant que client qui envoie une photo inexploitable, je veux un message clair plutôt qu'un faux résultat, afin de ne pas être induit en erreur | E2 | 3 | 2 | `validPhoto=false` → pas de scores, pas de matching, message explicatif |
| US8 | En tant qu'exploitant, je veux que l'appel `kbeauty-shop → ai-core` exige un secret partagé, afin que le service ne soit pas appelable publiquement | E5 | 3 | 2 | `InternalApiKeyFilter` sur `/diagnostics/**` ; fail-closed si clé vide ; comparaison temps constant ; 401 testé |
| US9 | En tant que client, je veux des **produits kbeauty-shop réels** adaptés à mon diagnostic, afin de pouvoir les acheter | E3 | 8 | 3 | embeddings catalogue (`products:embed-ingredients`) ; recherche pgvector ; ids renvoyés dans l'ordre de similarité |
| US10 | En tant que client, je veux quand même des recommandations si le moteur de matching est en panne, afin que la page reste utile | E3/E5 | 3 | 3 | matching *best-effort* (liste vide sur erreur) ; repli `randomPublishedForSkinType` côté Laravel |
| US11 | En tant que client, je veux ajouter une routine recommandée au panier en un clic, afin d'enchaîner sur l'achat | E4 | 5 | 3 | bouton « ajouter au panier » → `CartService` ; panier peuplé ; redirige vers le tunnel |
| US12 | En tant qu'exploitant, je veux que l'appel vision soit protégé par retry + circuit breaker, afin d'absorber les incidents Anthropic | E5 | 5 | 3 | Resilience4j sur `AnthropicApiClient` ; test d'ouverture du circuit |
| US13 | En tant que consommateur d'événements, je veux rejeter sans requeue un message non conforme au contrat, afin de ne pas boucler à l'infini | E5 | 3 | 3 | `nack(requeue:false)` + `Log::warning` ; test avec payload invalide |
| US14 | En tant que dev intégrateur, je veux un contrat **OpenAPI/Swagger** de `ai-core`, afin de consommer l'API sans lire le code | E6 | 5 | 4 | Springdoc ; Swagger UI accessible ; schéma commité |
| US15 | En tant qu'équipe, je veux une CI qui lance Pest + JUnit + scan Sonar au push, afin de ne pas régresser | E6 | 8 | 4 | GitHub Actions vert sur PR ; badge ; seuil qualité Sonar |
| US16 | En tant qu'exploitant, je veux `ai-core` déployé sur Azure Container Apps, afin qu'il ne dépende plus d'un poste local | E6 | 8 | 4 | image Docker ; déploiement ; URL privée consommée par `kbeauty-shop` |

### Découpage en sprints

| Sprint | Thème | Stories | Pts | Incrément livré |
|---|---|---|---|---|
| **1** (S1–S2) | Socle event-driven + entrée du parcours | US1, US2, US3, US4 | 18 | `curl` / formulaire → ligne Neon → événement contractualisé sur RabbitMQ |
| **2** (S3–S4) | Analyse vision réelle & sécurisée | US5, US6, US7, US8 | 17 | photo → scores + texte, non stockée, service non appelable publiquement |
| **3** (S5–S6) | Matching produit & bouclage panier | US9, US10, US11, US12, US13 | 19 | diagnostic → vrais produits → panier ; résilient aux pannes externes |
| **4** (S7–S8) | Industrialisation | US14, US15, US16 | 21 | API documentée, CI, service déployé hors poste local |

> **État réel au 2026-09-04** : Sprints 1 à 3 **livrés** (Phases 1–5 + axes hors programme). Sprint 4
> ouvert : US14/US15/US16 correspondent exactement aux points restants
> ([ROADMAP](ROADMAP.md) Phase 2 dernier item + Phase 6). Le backlog est donc rétro-documenté pour
> les 3 premiers sprints et prospectif pour le 4ᵉ — ce qui est assumé : Phase 0 a été faite après
> le code, pas avant.

---

## 6. Traçabilité modèle ↔ code

| Élément du modèle | Où c'est dans le code |
|---|---|
| BPMN A — création Order/Payment `pending` | `App\Http\Controllers\Storefront\CheckoutController::pay` → `PlaceOrder`, `ProcessCheckoutPayment` |
| BPMN A — confirmation par webhook + idempotence | `App\Http\Controllers\Webhooks\StripeWebhookController` → `ProcessStripeWebhookJob` (dédup sur `payload->id`, `webhook_calls`) |
| BPMN A — traitement asynchrone (email, stock, Shipment) | Jobs Horizon déclenchés par le webhook (`ARCHITECTURE.md §4`) |
| BPMN B — validation & throttle | `routes/storefront.php` (`throttle:3,60,storefront-diagnostic`), `Storefront\DiagnosticController::analyze` |
| BPMN B — appel inter-service authentifié | `App\Services\AiCoreDiagnosticClient` (header `X-Internal-Api-Key`) ↔ `config/InternalApiKeyFilter.java` |
| BPMN B — analyse en mémoire, jamais stockée | `service/AnthropicVisionService.java`, entité `DiagnosticRequest` (aucun champ image) |
| BPMN B — photo inexploitable | `SkinAnalysisResult.validPhoto` → `DiagnosticController.analyze` (Java) + `Storefront\DiagnosticController` (Laravel) |
| BPMN B — matching best-effort + repli | `matching/ProductMatchingService.java` (catch → `List.of()`), `Storefront\DiagnosticController::recommendedProducts` (repli aléatoire) |
| BPMN B — publication d'événement contractualisée | `amqp/DiagnosticEventPublisher.java` + `DiagnosticCreatedEventSchemaValidator` + `contracts/rabbitmq/diagnostic-created.schema.json` |
| BPMN B — consommation + rejet sans requeue | `App\Console\Commands\ConsumeDiagnosticCreatedEventsCommand` + `DiagnosticCreatedEventValidator` |
| Séquence — recherche vectorielle | `matching/ProductMatchRepository.java`, table `shop_ingredient_embeddings` (`php artisan products:embed-ingredients`) |
| Classes — entité JPA | `entity/DiagnosticRequest.java` |
| C4 conteneurs — bus d'événements | `config/RabbitMQConfig.java` (Java) ↔ `config('rabbitmq')` (Laravel), déclarations idempotentes des deux côtés |

Voir aussi : [01 — Vue d'ensemble](01-vue-ensemble.md), [12 — Contrat RabbitMQ ↔ Laravel](12-contrat-rabbitmq-laravel.md),
[13 — Diagnostic vision](13-diagnostic-vision-laravel.md), [ROADMAP](ROADMAP.md).
