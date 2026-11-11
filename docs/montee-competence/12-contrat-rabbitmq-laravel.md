---
title: Consommateur RabbitMQ Laravel & contrat JSON Schema
group: Montée en compétence
order: 12
---

← [Retour au sommaire](README.md)

# 12. Consommateur RabbitMQ Laravel & contrat JSON Schema

## Objectif

Axe 1 des [axes hors programme](07-axes-hors-programme.md) (priorisé le
2026-08-07) : valider chaque message RabbitMQ échangé entre
`kbeauty-ai-core-service` (Spring Boot, producteur) et `kbeauty-shop`
(Laravel, consommateur) contre un contrat de données versionné — pas de
confiance aveugle dans le format du message. Ce document couvre le côté
Laravel ; le côté Spring Boot est documenté dans
`kbeauty-ai-core-service/docs/04-contrat-donnees-json-schema.md`.

**Point de départ inattendu** : `kbeauty-shop` n'avait jusqu'ici aucun
consommateur RabbitMQ. `DiagnosticEventListener` (Phase 2) vit entièrement
côté Java, dans le même service que le producteur — une boucle fermée pour
prouver que l'event-driven fonctionne, jamais reliée à Laravel. Cet axe a
donc dû construire ce consommateur depuis zéro, pas seulement lui ajouter
une validation.

## Le contrat partagé

`contracts/rabbitmq/diagnostic-created.schema.json` — copie identique du
schéma défini côté `kbeauty-ai-core-service` (source de vérité, ce service
étant le producteur). Synchronisation vérifiée avec
`kbeauty-ai-core-service/contracts/check-sync.sh ../kbeauty-shop`, pas de
schema registry partagé (hors scope pédagogique pour un seul type
d'événement — voir `contracts/README.md`).

## Fichiers créés

### config/rabbitmq.php

Connexion RabbitMQ (host/port/user/password/vhost), lue depuis `.env`
(`RABBITMQ_*`). **Sans rapport avec `QUEUE_CONNECTION`** : cette variable
pilote Valkey/Horizon (les jobs internes Laravel, `dispatch()` +
`queue:work`), un système totalement différent de ce bus d'événements
inter-services. Les deux coexistent dans le projet sans interférer.

### app/Infrastructure/Rabbitmq/DiagnosticCreatedEventValidator.php

Charge le schéma partagé une fois (constructeur) et expose `validate()`,
qui décode le JSON reçu et le valide via `justinrainbow/json-schema`
(implémentation JSON Schema pure PHP). Lève
`InvalidDiagnosticCreatedEventException` sur JSON malformé ou message hors
contrat (champ manquant, type incorrect, valeur d'enum inattendue, champ en
trop grâce à `additionalProperties: false`).

### app/Console/Commands/ConsumeDiagnosticCreatedEventsCommand.php

Une commande Artisan **process long-vivant**, pas une tâche planifiée
(`routes/console.php`) : elle ouvre une connexion RabbitMQ
(`php-amqplib/php-amqplib`) et boucle indéfiniment sur `$channel->wait()`,
comme `php artisan queue:work` pour Valkey. Se lance manuellement
(`php artisan rabbitmq:consume-diagnostic-created`) ; en prod, un vrai
déploiement la superviserait via `supervisor`/`systemd` (redémarrage auto si
le process meurt) — non mis en place ici, hors scope pédagogique.

Déclare l'exchange/queue/binding de façon **idempotente**, avec les mêmes
noms et la même durabilité que côté Java (`RabbitMQConfig.java`) : permet de
lancer ce consommateur même si `kbeauty-ai-core-service` n'a jamais tourné.

Sur chaque message : décode + valide via `DiagnosticCreatedEventValidator`.
- **Valide** : logué (`Log::info`), acquitté (`$message->ack()`).
- **Invalide** : logué en warning (payload brut inclus, pour diagnostic),
  puis `$message->nack(requeue: false)` — pas de re-livraison infinie d'un
  message qui ne respectera jamais le contrat sans intervention humaine. Un
  vrai dead-letter exchange (RabbitMQ redirige automatiquement les messages
  `nack`és vers une queue dédiée à l'inspection) serait l'étape suivante en
  prod, pas mise en place ici.

Le traitement s'arrête au log : cet axe portait sur la **validation du
contrat**, pas sur une nouvelle action métier. Brancher une vraie réaction
(ex. notifier l'utilisateur que son diagnostic est prêt) est un chantier
séparé, pour la Phase 5.

### tests/Feature/Infrastructure/Rabbitmq/DiagnosticCreatedEventValidatorTest.php

6 cas, sans connexion RabbitMQ réelle (le validateur est testé isolément) :
événement valide, `status` hors enum, `diagnosticId` manquant, `eventType`
inattendu, champ en trop, JSON malformé.

## Deux bugs trouvés en testant en conditions réelles (pas juste via les tests unitaires)

Les tests unitaires (Java et PHP) passaient tous les deux avant même
d'avoir testé la boucle complète — et pourtant, le premier essai réel
(`kbeauty-ai-core-service` démarré + `rabbitmq:consume-diagnostic-created`
en écoute + `curl -X POST /diagnostics`) a échoué deux fois de suite, pour
deux raisons différentes que les tests unitaires ne pouvaient pas voir :

1. **`Jackson2JsonMessageConverter` avec un `ObjectMapper` non configuré.**
   `DiagnosticCreatedEventSchemaValidator` (côté Java) valide un
   `JsonNode` construit avec le bean `ObjectMapper` de Spring
   (`WRITE_DATES_AS_TIMESTAMPS` désactivé) — la validation passait. Mais
   `Jackson2JsonMessageConverter()` sans argument construit son **propre**
   `ObjectMapper` par défaut en interne, qui lui sérialise `Instant` en
   nombre. Le message qui partait réellement sur le fil différait de celui
   validé. Fix : `new Jackson2JsonMessageConverter(objectMapper)`, en
   injectant explicitement le même bean partout.
2. **Nanosecondes Java vs microsecondes PHP.** Une fois le point 1 corrigé,
   `occurredAt` arrivait bien en string ISO-8601
   (`2026-08-09T23:05:50.358053291Z`), mais `justinrainbow/json-schema`
   rejetait quand même le message : sa validation `format: date-time`
   utilise `DateTime::createFromFormat` avec un spécificateur `u`
   (microsecondes, exactement 6 chiffres) — `Instant.toString()` produit
   jusqu'à 9 chiffres (nanosecondes), et PHP échoue silencieusement
   au-delà de 6. Fix côté Java : `Instant.now().truncatedTo(ChronoUnit.MILLIS)`
   avant sérialisation — 3 chiffres suffisent largement pour un horodatage
   d'événement, et passent la validation des deux côtés.

Ces deux bugs auraient été invisibles en ne testant que les schémas et les
validateurs isolément (comme fait initialement) : ils ne se manifestent
qu'en observant le JSON réellement transporté sur le fil, entre deux
implémentations différentes du même contrat.

## Vérification

```bash
# Terminal 1 : consommateur Laravel
cd ~/projects/kbeauty-shop && php artisan rabbitmq:consume-diagnostic-created

# Terminal 2 : microservice Spring Boot
cd ~/projects/kbeauty-ai-core-service && mvn spring-boot:run

# Terminal 3
curl -X POST http://localhost:8080/diagnostics
```

Le terminal 1 ne montre rien de plus que "En écoute..." (le traitement va
dans les logs), mais `storage/logs/laravel.log` confirme :

```
[...] local.INFO: RabbitMQ diagnostic.created : evenement recu et valide {"diagnosticId":39,"status":"pending","occurredAt":"2026-08-09T23:08:10.090Z"}
```

Vérifié aussi côté broker (`localhost:15672`, `guest`/`guest`) :
`GET /api/queues/%2f/diagnostic.created` confirme `messages: 0` (le message
a bien été acquitté, pas laissé en attente) avec 2 consommateurs actifs
pendant le test (le `DiagnosticEventListener` Java et la commande Artisan
tournaient tous les deux sur la même queue en parallèle).
