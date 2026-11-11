---
title: Microservice de notifications transactionnelles (NestJS)
group: Montée en compétence
order: 21
---

← [Retour au sommaire](README.md)

# 21. Microservice de notifications transactionnelles (NestJS)

> **Statut (2026-10-15)** : pipeline complet mergé et vérifié de bout en bout en
> conditions réelles (PR #324, `kbeauty-shop` → RabbitMQ → `kbeauty-notifications-service`).
> `NewsletterController::store()` publie désormais `newsletter.subscription_requested`
> dans l'outbox, **en plus** de l'envoi direct via `NewsletterSubscriptionConfirmation`
> (coexistence volontaire, pas un remplacement — voir §3.3), derrière
> `NOTIFICATIONS_INTEGRATION_ENABLED` (`false` par défaut). Décision révisée en cours
> de route : pas `@nestjs/microservices` (§3.2) mais `amqp-connection-manager`/
> `amqplib` directement, même principe que `sav-ticketing-php`.

## En une phrase

Aujourd'hui, les notifications (confirmation de commande, retour, newsletter...) sont
envoyées en dur depuis `app/Notifications/` dans le monolithe Laravel. L'exercice
consiste à extraire cette responsabilité transverse dans un microservice NestJS
dédié, qui écoute les mêmes événements RabbitMQ que l'intégration SAV
([doc 20](20-integration-sav-rabbitmq.md)) plutôt que d'être appelé en direct.

## 1. Pourquoi faire ça (le point de vue entreprise)

| Besoin | Ce que le découplage apporte |
|---|---|
| Ne pas coupler l'envoi au flux métier | Un incident du provider email (Resend) ne doit jamais ralentir ni faire échouer le traitement d'une commande |
| Ajouter des canaux sans polluer le métier | SMS, push, WhatsApp s'ajoutent dans un seul service, pas dans chaque use case (`PlaceOrder`, `SubmitReturnRequest`...) qui en a besoin |
| Centraliser les préférences utilisateur | Opt-out marketing, rate-limiting anti-spam : logique transverse, un seul endroit où la gérer |
| Réutiliser au-delà de la boutique | Le SAV (`sav-ticketing-php`) ou un futur canal de vente pourraient publier leurs propres événements et profiter du même service |

**Limite honnête** : comme pour l'intégration SAV, à la taille actuelle de la
boutique (un seul canal de vente, un seul provider email), les 12 classes
`Notification` Laravel actuelles suffisent largement en production. Cet exercice se
place dans le cas d'une entreprise qui a grandi avec plusieurs canaux/produits — à
dire explicitement en entretien, ce n'est pas une faiblesse de l'avouer.

## 2. Vue d'ensemble

```
 kbeauty-shop (Laravel)                    RabbitMQ                    kbeauty-notifications-service (NestJS)
 ─────────────────────                     ────────                   ──────────────────────────────────────
 commande payée / retour soumis / etc.
        │
        ▼  même pattern outbox que le SAV (doc 20)
 outbox_messages
        │
        ▼  rabbitmq:publish-outbox (chaque minute)
 kbeauty.exchange ──(order.paid, return_request.submitted, ...)──► file notifications.*
                                                                              │
                                                                              ▼
                                                                   NotificationsConsumer
                                                                     1. vérifie le contrat (JSON Schema)
                                                                     2. résout le template par type d'événement
                                                                     3. déduplique (idempotence)
                                                                     4. envoie (Resend pour l'email)
                                                              échec/hors contrat ─┴─► file notifications.rejetees
```

Même triptyque que l'intégration SAV : **outbox** (ne jamais perdre un événement),
**contrat JSON Schema** (un message est une donnée non fiable tant qu'il n'est pas
vérifié), **idempotence** (RabbitMQ livre "au moins une fois", pas "exactement une
fois").

## 3. Choix d'architecture

### 3.1 Réutiliser l'outbox et le contrat existants plutôt qu'en inventer un nouveau

La boutique publie déjà des événements vers RabbitMQ pour le SAV via le pattern
outbox (`OutboxMessage`, `PublishOutboxMessagesCommand`). Plutôt que bâtir un
mécanisme de notification séparé, le plan est de **réutiliser le même exchange**
(`kbeauty.exchange`) avec de nouvelles routing keys (`order.paid`,
`return_request.submitted`...) consommées par une nouvelle file dédiée
(`notifications.*`), sur le modèle de `sav.retours`.

### 3.2 Pourquoi NestJS plutôt que Go, et pourquoi pas `@nestjs/microservices` finalement

Décision prise en amont (voir discussion du 2026-10-14) : les décorateurs/DI de
NestJS suivent la même logique que Spring Boot (`kbeauty-ai-core-service`, déjà
fait) et que les Service Providers Laravel — réutilisation d'un paradigme déjà
acquis plutôt qu'un nouveau à apprendre. Go resterait un bon argument de diversité
de stack, mais pour lui-même, pas pour ce service précis.

**Révisé en cours de route (2026-10-14)** : `@nestjs/microservices` (transport RMQ)
semblait la bonne option au départ, mais son transport gère ses propres
files/exchanges à sa façon (patterns de message, files par pattern) et ne se branche
pas naturellement sur un exchange + routing key déjà gérés par un producteur externe
non-Nest (`kbeauty-shop`, en PHP). `sav-ticketing-php` consomme déjà ce même exchange
avec `amqplib` brut plutôt qu'un framework — le consumer de ce service suit le même
principe (`amqp-connection-manager`/`amqplib` directement) plutôt que de forcer une
abstraction qui ne correspond pas à la topologie réelle. `@nestjs/microservices`
retiré du projet.

### 3.3 Migration progressive, pas un big-bang

Les 12 `Notification` Laravel actuelles ne migrent pas toutes en même temps.
Commencer par une notification **non critique** (ex. `NewsletterSubscriptionConfirmation`
ou `AbandonedCartReminder`) pour valider le flux de bout en bout, avant de toucher
aux notifications transactionnelles sensibles (`OrderConfirmation`, `OrderShipped`).
Pendant la transition, les deux mécanismes coexistent (le monolithe garde ses
`Notification` existantes tant qu'un événement n'a pas été migré).

### 3.4 Déduplication

Même logique que `tickets.retour_kbeauty_id` côté SAV (doc 20, §3.5) : une table
légère (SQLite au départ, le volume ne justifie pas Neon dès le début) garde
l'identifiant de chaque événement déjà traité, avec une contrainte d'unicité.

### 3.5 Sécurité et RGPD

- Compte RabbitMQ dédié **fait** (2026-10-14) : `notifications`, droits limités à ses
  deux files (`notifications.newsletter`, `notifications.rejetees`) et à la lecture
  de `kbeauty.exchange` — même script `kbeauty-ecosystem/rabbitmq/creer-comptes.sh`
  que pour `sav`. Vérifié : ce compte ne peut ni publier sur `kbeauty.exchange` ni
  lire `sav.retours` (`Access refused` dans les deux cas).
- Le contrat JSON Schema limite les champs transmis au strict nécessaire pour
  composer le message (email, lien de confirmation) — ni mot de passe, ni données de
  paiement.
- Désactivé par défaut côté `kbeauty-shop` (`NOTIFICATIONS_INTEGRATION_ENABLED=false`,
  voir §4) — aucun événement accumulé dans l'outbox tant que ce n'est pas activé.

## 4. Les fichiers

### kbeauty-notifications-service (repo séparé)

| Fichier | Rôle | Statut |
|---|---|---|
| `src/main.ts`, `src/app.module.ts` | Scaffold NestJS de base | ✅ fait (`nest new`) |
| `.github/workflows/gitleaks.yml`, `ci.yml` | CI (scan secrets, lint/test/build) | ✅ fait |
| `src/notifications/notifications.consumer.ts` | Consumer AMQP (`amqp-connection-manager`/`amqplib`, pas `@nestjs/microservices` — voir §3.2) | ✅ fait, vérifié en conditions réelles |
| `src/notifications/templates.ts` | Template email newsletter | ✅ fait (un seul événement pour l'instant) |
| `src/notifications/dedup.service.ts` | Déduplication (`node:sqlite`) | ✅ fait |
| `src/notifications/contract-validator.service.ts` | Validation Ajv (draft 2020-12) | ✅ fait, 4 tests |
| `src/notifications/email.service.ts` | Envoi Resend (journalise si pas de clé API) | ✅ fait, pas encore teste avec un vrai envoi |
| `contracts/rabbitmq/newsletter-subscription-requested.schema.json` | Contrat du premier événement | ✅ fait |

### kbeauty-shop (producteur, extension de l'outbox existant)

| Fichier | Rôle | Statut |
|---|---|---|
| `app/Infrastructure/Rabbitmq/NewsletterSubscriptionRequestedPayload.php` | Corps de l'événement, conforme au contrat partagé | ✅ fait (PR #324), vérifié en conditions réelles |
| `app/Http/Controllers/Storefront/NewsletterController.php` | Publie l'événement dans l'outbox si `NOTIFICATIONS_INTEGRATION_ENABLED` ; envoi direct conservé en parallèle (§3.3) | ✅ fait (PR #324) |

## 5. Lancer en local

```bash
# 1. RabbitMQ + compte dedie (infra partagee, voir kbeauty-ecosystem)
cd ~/projects/kbeauty-ecosystem
docker start kbeauty_rabbitmq
./rabbitmq/creer-comptes.sh

# 2. Service de notifications
cd ~/projects/kbeauty-notifications-service
cp .env.example .env   # ajuster RABBITMQ_URL/RESEND_API_KEY si besoin
npm run start:dev

# 3. Boutique (NOTIFICATIONS_INTEGRATION_ENABLED=true dans .env)
cd ~/projects/kbeauty-shop
php artisan schedule:work   # ou rabbitmq:publish-outbox directement
```

S'inscrire à la newsletter publie reellement l'evenement via l'outbox. Pour tester
le consumer sans passer par la boutique, on peut aussi simuler un message a la main :

```bash
docker exec kbeauty_rabbitmq rabbitmqadmin -q publish \
  exchange=kbeauty.exchange \
  routing_key=newsletter.subscription_requested \
  payload='{"eventType":"newsletter.subscription_requested","subscriberId":1,"email":"test@example.com","confirmUrl":"https://kbeauty-shop.test/newsletter/confirm?signature=abc","occurredAt":"2026-10-14T15:00:00Z"}'
```

## 6. Limites et suite

- **L'envoi direct (email synchrone) n'a pas ete retire** — il coexiste
  volontairement avec l'evenement RabbitMQ (voir §3.3) tant que le flux par
  microservice n'est pas confirme en conditions reelles de production (pas
  seulement en local). Prochaine étape concrète une fois ce point confirmé :
  retirer l'envoi direct dans `NewsletterSubscriptionConfirmation`, pour que
  le microservice devienne la seule source d'envoi.
- **Pas de SMS/push réels prévus dans un premier temps** — seul le canal email
  (Resend) est visé pour la première itération ; les autres canaux resteront des
  stubs qui montrent l'extensibilité sans complexifier l'exercice pour rien.
- **Envoi Resend pas encore testé avec un vrai envoi** — `EmailService` journalise
  au lieu d'envoyer tant qu'aucun `RESEND_API_KEY` n'est configuré en local.
- **Production** : comme pour le SAV, pas de RabbitMQ hébergé en production
  aujourd'hui — l'intégration restera désactivée tant que ce n'est pas le cas.

## 7. Hébergement envisagé (pas encore fait)

**Railway**, plutôt qu'Azure comme `kbeauty-ai-core-service`/`kbeauty-ingredients-scraper`
(doc 15) :

- **Pas de cohérence forcée avec Azure** : rien n'impose un cloud unique pour
  l'exercice — chaque service choisit l'hébergement qui lui correspond, c'est
  en soi un point à défendre en entretien (pas de dogme "tout sur le même
  cloud" par habitude).
- **Pourquoi pas Azure quand même** : App Service a un vrai coût de mise en
  route pour un service aussi petit (image, variables, registre) déjà amorti
  sur les deux autres services — ne pas le dupliquer pour un troisième alourdit
  l'exercice sans rien démontrer de nouveau.
- **Pourquoi Railway spécifiquement** : déploiement par `git push` sans
  configuration d'infra à écrire, support natif Node/NestJS, prix au
  plus proche de l'usage réel (pas d'abonnement fixe) adapté à un service qui
  tournera par intermittence pour la démo plutôt qu'en continu.
- **RabbitMQ** : CloudAMQP déjà en place pour `kbeauty-ai-core-service`
  (doc 15) — réutilisable tel quel, pas de nouvel hébergement de bus à gérer.

## 8. Questions d'entretien probables

**« Pourquoi un service séparé plutôt que garder les `Notification` Laravel ? »**
Découplage : un incident du provider email ne doit jamais impacter le traitement
d'une commande, et chaque nouveau canal (SMS, push) s'ajoute à un seul endroit
plutôt que dans chaque use case métier qui en a besoin.

**« Pourquoi NestJS et pas rester en PHP ? »**
Pour montrer une troisième stack dans l'écosystème (Java, Python, PHP natif, et donc
Node/TypeScript), tout en réutilisant un paradigme (décorateurs/DI) déjà acquis via
Spring Boot — pas un choix arbitraire.

**« C'est utilisé en vrai, ce pattern ? »**
Oui : Netflix et Uber ont leurs plateformes de notification internes ; Twilio,
SendGrid/Resend, OneSignal sont littéralement ce pattern vendu comme produit SaaS.

**« Ce n'est pas trop tôt pour une boutique de cette taille ? »**
Si, comme pour le SAV — c'est assumé : l'objectif est l'apprentissage du découplage
d'une responsabilité transverse dans un contexte réaliste, pas un besoin actuel de
production.
