---
title: Intégration avec le SAV (sav-ticketing-php) via RabbitMQ
group: Montée en compétence
order: 20
---

← [Retour au sommaire](README.md)

# 20. Intégration avec le SAV (sav-ticketing-php) via RabbitMQ

## En une phrase

Quand un client fait une demande de retour sur la boutique, un ticket est
créé automatiquement dans l'application SAV `sav-ticketing-php`, sans que
les deux applications partagent leur base ou leur code : elles s'échangent
des **messages** via RabbitMQ.

## 1. Pourquoi faire ça (le point de vue entreprise)

| Besoin | Ce que la liaison apporte |
|---|---|
| Ne perdre aucune demande client | Toutes les demandes (retours aujourd'hui, messages de contact ou autres canaux demain) deviennent des tickets, avec un responsable et un statut |
| Séparer les métiers | Le service client travaille dans le SAV ; il n'a pas besoin d'accéder à l'admin de la boutique (prix, stocks, paiements) |
| Décider avec des chiffres | Tickets rattachés aux commandes et produits : taux de retour par produit, par motif, délai de traitement → déréférencer un produit, changer de transporteur, dimensionner l'équipe |
| Grandir sans tout refaire | Un autre canal de vente (marketplace, boutique physique) peut envoyer ses retours au même SAV |

**Limite honnête** : à la taille actuelle de la boutique, la gestion des
retours intégrée à l'admin suffit. Cette intégration est un exercice :
*« je me place dans le cas d'une entreprise qui a grandi, avec une vraie
équipe SAV »*. Le dire en entretien est un point fort, pas une faiblesse.

## 2. Vue d'ensemble

```
 kbeauty-shop (Laravel)                       RabbitMQ                          sav-ticketing-php (PHP natif)
 ─────────────────────                        ────────                          ────────────────────────────
 client soumet un retour
        │
        ▼  une seule transaction
 return_requests  +  outbox_messages
        │
        ▼  chaque minute
 rabbitmq:publish-outbox ──► kbeauty.exchange ──(return_request.submitted)──► file sav.retours
                                                                                     │
                                                                                     ▼
                                                                     bin/consommer-retours-kbeauty.php
                                                                       1. vérifie le contrat
                                                                       2. client + commande (retrouvés ou créés)
                                                                       3. ticket "Retour client (boutique)"
                                                                       4. notifie les admins SAV
                                                                                     │
                                                         message refusé ou en échec ─┴─► file sav.retours.rejetes
```

Chaque application garde **ses** données et **son** rôle :

- la boutique reste maître du client, de la commande et du remboursement ;
- le SAV gère le traitement (diagnostic, échange, suivi par un technicien).

## 3. Les choix, un par un

Pour chaque choix : le problème, la solution, et ce qui se passerait sans.

### 3.1 Des messages plutôt qu'une base partagée

- **Problème** : le SAV a besoin des infos du retour.
- **Solution** : la boutique *publie* un événement, le SAV *s'abonne*.
- **Sans** (base partagée) : renommer une colonne côté boutique casserait le
  SAV ; un SAV piraté pourrait lire ou modifier les comptes clients et les
  commandes. Avec des messages, le pire qu'un SAV piraté puisse faire est…
  rien vers la boutique : dans ce sens-là, il ne publie aucun message.
- **Bonus** : si le SAV est arrêté, la boutique continue de vendre ; les
  messages attendent dans la file (vérifié, §6).

Le choix Laravel d'un côté / PHP natif de l'autre n'a **aucune importance**
ici : les deux ne partagent que du JSON.

### 3.2 Un contrat de données (JSON Schema)

`contracts/rabbitmq/return-request-submitted.schema.json` décrit exactement
le message : champs obligatoires, types, tailles maximales, aucun champ en
plus (`additionalProperties: false`).

- La boutique est le **producteur** → elle détient la version de référence.
  Le SAV en garde une copie ; `contracts/check-sync.sh ../sav-ticketing-php`
  vérifie qu'elles sont identiques (même convention que pour
  `diagnostic.created`, doc 12).
- Côté boutique, un test vérifie que le message produit respecte le schéma.
- Côté SAV, **chaque message reçu** est vérifié avant tout traitement : un
  message est une donnée non fiable, comme un formulaire rempli par un
  inconnu. Un message hors contrat n'est jamais traité.

**RGPD — minimisation** : le message ne contient que ce dont le SAV a
besoin (nom, email, numéro de commande, articles, motif). Ni adresse, ni
téléphone, ni donnée de paiement. Le schéma l'impose : un champ en plus
ferait rejeter le message.

### 3.3 L'outbox : ne jamais perdre un événement, ne jamais bloquer le client

C'est le choix le plus important, et une question d'entretien classique.

- **Problème** : enregistrer la demande en base ET envoyer le message à
  RabbitMQ sont deux opérations sur deux systèmes différents. Si on envoie
  directement :
  - RabbitMQ en panne → soit la demande du client échoue (mauvais pour le
    client), soit elle est enregistrée sans message (le SAV ne la verra
    jamais) ;
  - message envoyé puis transaction annulée → le SAV traite une demande
    qui n'existe pas.
- **Solution** (*transactional outbox*) : le message est d'abord écrit dans
  la table `outbox_messages`, **dans la même transaction** que la demande de
  retour. Les deux existent ensemble ou pas du tout. Ensuite, la commande
  `rabbitmq:publish-outbox` (planifiée chaque minute) envoie ce qui est en
  attente.
- **Résultat** : RabbitMQ en panne = le client ne voit rien, le message part
  plus tard. Délai maximum en temps normal : environ une minute.

Détails de la commande de publication :

- messages envoyés **dans l'ordre** ; au premier échec elle s'arrête, pour
  qu'un message plus récent ne double pas un plus ancien ;
- en cas d'échec : `attempts` +1 et `last_error` renseigné, pour le
  diagnostic ;
- les messages publiés sont gardés 7 jours puis supprimés (la table ne
  grossit pas indéfiniment — leçon de l'incident Telescope).

### 3.4 Publication fiable côté RabbitMQ

Dans `AmqpMessagePublisher` :

- **publisher confirms** : la boutique attend que RabbitMQ confirme avoir
  pris le message en charge avant de le marquer « publié » ;
- **mandatory** : si aucune file n'écoute (SAV jamais démarré), RabbitMQ
  *renvoie* le message au lieu de le jeter en silence → il reste dans
  l'outbox (vérifié, §6) ;
- **message persistant** : il survit à un redémarrage de RabbitMQ.

### 3.5 Idempotence : un message reçu deux fois = un seul ticket

RabbitMQ garantit une livraison **« au moins une fois »**, pas « exactement
une fois » : après une coupure au mauvais moment, un message peut arriver
deux fois. Le SAV stocke l'identifiant de la demande de retour
(`tickets.retour_kbeauty_id`, contrainte `UNIQUE`) : le deuxième passage
voit que le ticket existe et ne fait rien. La contrainte en base tranche
même si deux consommateurs traitent le même message en même temps.

### 3.6 Que faire d'un message qui échoue ?

| Cas | Réaction du SAV | Pourquoi |
|---|---|---|
| Importé (ou déjà importé) | `ack` : retiré de la file | Travail fait |
| Hors contrat | `reject` sans remise en file → `sav.retours.rejetes` | Il ne sera jamais valide : le réessayer ne sert à rien, mais on le garde pour examen |
| Erreur (base arrêtée…) | remis en file, nouvel essai 10 s plus tard | Panne probablement temporaire |
| 5 échecs de suite | RabbitMQ le range dans `sav.retours.rejetes` | Évite qu'un message « empoisonné » bloque la file à l'infini |

La file `sav.retours` est une file **quorum** : RabbitMQ compte lui-même les
livraisons (`x-delivery-limit: 5`) et sait où envoyer les messages rejetés
(`x-dead-letter-exchange`). Il note aussi la raison de chaque rejet :
`rejected` (hors contrat) ou `delivery_limit` (trop d'échecs).

Le consommateur traite **un message à la fois** (`prefetch 1`) et n'accuse
réception qu'après l'enregistrement en base : s'il s'arrête en plein
travail, le message est redonné au prochain démarrage.

### 3.7 Un processus qui tourne des jours

Le consommateur est un processus long (contrairement à une requête web qui
dure quelques millisecondes). Piège : MariaDB coupe une connexion inactive
au bout de 8 h (`wait_timeout`). Solution : une connexion à la base **neuve
pour chaque message**, comme pour une requête HTTP (`Database::fermer()`).
Coût négligeable au volume d'un SAV.

En production, il se lance sous **supervisor** ou **systemd**, qui le
relance s'il s'arrête (même principe que `queue:work` / Horizon côté
Laravel).

### 3.8 Sécurité

**Moindre privilège dans RabbitMQ** (`kbeauty-ecosystem/rabbitmq/creer-comptes.sh`) :
un compte par application, avec seulement les droits nécessaires.

| Compte | Peut | Ne peut pas |
|---|---|---|
| `kbeauty_shop` | publier sur `kbeauty.exchange`, consommer `diagnostic.created` | lire ou supprimer les files du SAV |
| `sav` | créer/consommer ses files `sav.retours*`, les lier à `kbeauty.exchange` | publier sur `kbeauty.exchange`, le supprimer, lire les autres files |

`kbeauty.exchange` est créé par le script d'infrastructure ; le SAV vérifie
seulement qu'il existe (déclaration *passive*, qui ne demande aucun droit).
Ces refus ont été testés (§6).

C'est le même principe que le compte MariaDB `sav_app` du SAV (lecture et
écriture des données, mais pas de `DROP`) : si une application est
compromise, les dégâts restent dans son périmètre.

**Autres protections** :

- chaque message vérifié contre le contrat (§3.2) ;
- le motif et le nom saisis par le client sont affichés comme du **texte**
  dans le SAV, jamais comme du HTML (testé avec `<img onerror=…>`, §6) ;
- les messages rejetés ne sont **pas** recopiés dans les journaux du SAV (ils
  contiennent des données personnelles) : seule l'erreur l'est ;
- requêtes SQL du SAV préparées, vérifiées par `RequetesSqlTest`.

### 3.9 Désactivé par défaut

`SAV_INTEGRATION_ENABLED=false` par défaut : tant qu'aucun SAV n'est
branché (cas de la production actuelle), la boutique n'enregistre aucun
événement et la tâche planifiée ne fait rien. La seule trace en production
est une table `outbox_messages` vide.

## 4. Les fichiers

### kbeauty-shop (producteur)

| Fichier | Rôle |
|---|---|
| `contracts/rabbitmq/return-request-submitted.schema.json` | Le contrat (source de vérité) |
| `contracts/check-sync.sh` | Vérifie que la copie du SAV est identique |
| `database/migrations/…_create_outbox_messages_table.php`, `app/Models/OutboxMessage.php` | Table outbox |
| `app/Domain/Returns/Contracts/ReturnRequestEventsInterface.php` | « Un retour a été soumis » — ce que le use case sait |
| `app/Infrastructure/Rabbitmq/OutboxReturnRequestEvents.php` | Comment : écrire dans l'outbox |
| `app/Infrastructure/Rabbitmq/ReturnRequestSubmittedPayload.php` | Construction du message |
| `app/Infrastructure/Rabbitmq/AmqpMessagePublisher.php` | Envoi fiable (confirms, mandatory) |
| `app/Console/Commands/PublishOutboxMessagesCommand.php` | `rabbitmq:publish-outbox` |
| `app/Application/Returns/UseCases/SubmitReturnRequest.php` | Appelle l'événement dans la transaction |
| `routes/console.php` | Planification chaque minute |
| `tests/Feature/Infrastructure/Rabbitmq/ReturnRequestOutboxTest.php` | 5 tests |

L'interface dans `Domain` et l'implémentation dans `Infrastructure` suivent
la Clean Architecture du projet (§3bis de `ARCHITECTURE.md`) : le use case
ne sait pas que RabbitMQ existe.

### sav-ticketing-php (consommateur)

| Fichier | Rôle |
|---|---|
| `contracts/rabbitmq/return-request-submitted.schema.json` | Copie du contrat |
| `src/Integration/Kbeauty/ContratRetourSoumis.php` | Vérification de chaque message |
| `src/Integration/Kbeauty/ConsommateurRetours.php` | Files, ack/reject, réessais |
| `src/Service/ImportRetourKbeauty.php` | Retour → client, commande, ticket, notification |
| `bin/consommer-retours-kbeauty.php` | Point d'entrée du processus |
| `database/migrations/003_integration_kbeauty.sql` | Type `retour`, `retour_kbeauty_id`, `reference_externe` |
| `tests/Unit/ContratRetourSoumisTest.php`, `tests/Integration/ImportRetourKbeautyTest.php` | 18 tests |

Le type « Retour client (boutique) » n'est pas proposé dans le formulaire
de création du SAV : un retour vient uniquement de la boutique.

### kbeauty-ecosystem (infrastructure)

| Fichier | Rôle |
|---|---|
| `rabbitmq/creer-comptes.sh` | Exchange commun + comptes `kbeauty_shop` et `sav` à droits limités |

## 5. Lancer en local

```bash
# 1. RabbitMQ + comptes (rejouable)
cd ~/projects/kbeauty-ecosystem
docker start kbeauty_rabbitmq          # ou docker compose up -d rabbitmq
./rabbitmq/creer-comptes.sh

# 2. SAV : migration, config, consommateur
cd ~/projects/sav-ticketing-php
docker exec -i sav-ticketing-mysql mariadb -uroot -proot sav_ticketing < database/migrations/003_integration_kbeauty.sql
# .env : ajouter les lignes RABBITMQ_* de .env.example (compte sav)
php bin/consommer-retours-kbeauty.php  # laisser tourner

# 3. Boutique
cd ~/projects/kbeauty-shop
# .env : SAV_INTEGRATION_ENABLED=true, RABBITMQ_USER=kbeauty_shop, RABBITMQ_PASSWORD=kbeauty_shop
php artisan migrate                    # crée outbox_messages (voir l'avertissement ci-dessous)
php artisan schedule:work              # ou à la main : php artisan rabbitmq:publish-outbox
```

Puis : faire une demande de retour sur une commande livrée depuis « Mon
compte » → dans la minute, le ticket apparaît dans le SAV et la cloche des
admins s'allume.

Interface RabbitMQ : http://localhost:15672 (onglet *Queues* : `sav.retours`,
`sav.retours.rejetes`).

**Rejouer un message rejeté** (après avoir corrigé la cause) : dans
l'interface, file `sav.retours.rejetes` → *Get messages* (mode *Ack*), puis
le republier sur `kbeauty.exchange` avec la routing key
`return_request.submitted`. Grâce à l'idempotence, rejouer un message déjà
traité ne crée pas de doublon.

## 6. Ce qui a été vérifié

Tests automatiques : boutique `composer test` (Pint, PHPStan niveau 7,
Pest) ; SAV `composer test` (PHPUnit, 205 tests dont 20 nouveaux).

Essai de bout en bout, avec un vrai RabbitMQ, le vrai consommateur SAV et le
vrai use case de la boutique (base de la boutique : SQLite jetable, aucun
service externe) :

| Scénario | Résultat |
|---|---|
| Retour soumis alors que le SAV n'a jamais démarré | RabbitMQ renvoie le message (aucune file) → reste dans l'outbox, `attempts=1` |
| SAV démarré, outbox republiée | Ticket `retour` créé, client et commande créés, admin notifié |
| Même message envoyé deux fois | « déjà importé, ignoré », un seul ticket |
| SAV arrêté pendant un retour | Message en attente dans `sav.retours` ; traité dès le redémarrage |
| Motif `<img src=x onerror=…>`, nom `Paul <b>Durand</b>` | Affichés comme du texte dans la page du ticket |
| Message hors contrat (`returnRequestId: "DROP TABLE tickets"`) | Rejeté vers `sav.retours.rejetes`, raison `rejected` |
| Base du SAV inaccessible | 6 essais espacés de 10 s, puis `sav.retours.rejetes` (raison `delivery_limit`) ; rejoué après réparation → ticket créé |
| `sav` publie sur `kbeauty.exchange` / le supprime / lit `diagnostic.created` ; `kbeauty_shop` lit une file du SAV | Tous refusés (`Access refused`) |

## 7. Limites et suite

- **Sens retour (SAV → boutique) pas encore fait** : quand le technicien
  fait avancer le ticket, le client ne le voit pas encore dans « Mon
  compte ». Prochaine étape : un événement `ticket.statut_change` publié par
  le SAV, avec le même outillage (contrat, outbox, idempotence).
- **Articles** : les produits retournés sont listés dans le texte du ticket,
  pas reliés au catalogue d'articles du SAV (les deux catalogues sont
  différents). Un tableau « taux de retour par produit » demanderait de
  stocker ces lignes à part.
- **Production** : pas de RabbitMQ en production aujourd'hui (d'où
  l'intégration désactivée). Il faudrait un RabbitMQ hébergé, en **TLS**,
  jamais exposé sans authentification, et le consommateur sous supervisor.
- `kbeauty-ai-core-service` utilise encore le compte `guest` (droits
  complets) : lui créer son propre compte limité, puis supprimer `guest`.
- Délai jusqu'à une minute (rythme de la tâche planifiée) : suffisant pour
  un SAV ; on pourrait publier immédiatement après la transaction et garder
  la tâche planifiée comme filet de sécurité.

## 8. Hébergement envisagé (pas encore fait)

**Railway**, même choix que `kbeauty-notifications-service` (doc 21, §7) et
`kbeauty-customer-mdm` (doc 22, §7), pour les mêmes raisons (pas de dogme
"tout sur Azure", coût de mise en route Azure déjà amorti sur les deux
services existants) :

- **Process worker, pas serveur web classique** : `sav-ticketing-php` n'est
  pas qu'un site (back-office technicien, en PHP natif derrière un serveur
  web) — le consommateur RabbitMQ (`bin/consommer-retours-kbeauty.php`,
  `bin/consommer-clients-kbeauty.php`) est un **processus de fond** qui tourne
  en continu, pas une route HTTP. Railway supporte nativement ce type de
  déploiement ("worker", sans port HTTP exposé), contrairement à App Service
  (Azure) pensé d'abord pour du HTTP.
- **Base de données** : Railway propose une **MariaDB managée** en
  complément — pas besoin d'un service séparé comme pour Neon/Astra
  (`kbeauty-shop`/`kbeauty-ai-core-service`).
- **RabbitMQ** : CloudAMQP déjà en place (doc 15) — réutilisable tel quel.
- **Supervision du process worker** : en l'absence de `supervisor` (utilisé
  en local pour relancer le consommateur s'il crashe), Railway relance
  automatiquement un service qui s'arrête — à vérifier en pratique au moment
  du déploiement réel, pas encore fait aujourd'hui.

## 9. Questions d'entretien probables

**« Pourquoi pas une API REST entre les deux ? »**
Avec un appel HTTP, si le SAV est en panne au moment de la demande, il faut
gérer soi-même les réessais, et la boutique attend la réponse. Avec une file
de messages, la boutique dépose le message et continue ; le SAV le traite
quand il peut. Les deux applications ne dépendent pas de la disponibilité
de l'autre.

**« Que se passe-t-il si RabbitMQ tombe ? »**
Côté boutique, rien de visible : les demandes sont enregistrées avec leur
événement dans l'outbox, publié dès le retour de RabbitMQ. Côté SAV, le
consommateur s'arrête et doit être relancé (supervisor). Les messages déjà
dans la file sont persistants : ils survivent au redémarrage.

**« Et si un message arrive deux fois ? »**
Idempotence : identifiant unique de la demande, contrainte `UNIQUE` en base.

**« Comment savez-vous que le message est valide ? »**
Contrat JSON Schema, vérifié à la production (test) et à la réception
(chaque message). Un message hors contrat est mis de côté, jamais traité.

**« Pourquoi un compte RabbitMQ par application ? »**
Moindre privilège, défense en profondeur : si une application est
compromise, elle ne peut toucher qu'à ses propres files.

**« Ce n'est pas trop complexe pour une petite boutique ? »**
Si, aujourd'hui. Je l'ai fait pour apprendre à relier deux systèmes de
technologies différentes avec des contraintes réelles (pannes, doublons,
sécurité, RGPD), en me plaçant dans le cas d'une entreprise qui a grandi.
L'intégration est désactivée par défaut et n'a aucun impact sur la
boutique en production.

## 9. Glossaire

- **Exchange** : « bureau de tri » de RabbitMQ ; reçoit les messages et les
  distribue aux files selon leur *routing key*.
- **File (queue)** : boîte aux lettres où les messages attendent leur
  consommateur.
- **Routing key** : étiquette du message (`return_request.submitted`).
- **ack / reject / nack** : le consommateur dit « traité », « refusé
  définitivement » ou « échec, à refaire ».
- **Dead-letter (file des rejetés)** : où vont les messages refusés ou
  en échec répété, pour examen humain.
- **Outbox** : table où l'événement est écrit dans la même transaction que
  la donnée, puis publié plus tard.
- **Idempotent** : faire l'opération deux fois donne le même résultat
  qu'une seule fois.
- **Contrat de données** : description formelle (ici JSON Schema) de ce
  qu'un message doit contenir.
- **Moindre privilège** : chaque compte n'a que les droits dont il a besoin.
