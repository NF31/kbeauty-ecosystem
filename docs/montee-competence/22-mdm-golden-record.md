---
title: Service de référentiel client unique — MDM (Go)
group: Montée en compétence
order: 22
---

← [Retour au sommaire](README.md)

# 22. Service de référentiel client unique — MDM (Go)

> **Statut (2026-10-15)** : pipeline complet mergé et vérifié de bout en bout en
> conditions réelles (vrais comptes RabbitMQ, vrai consumer SAV, vrais utilisateurs
> de la base locale). Désactivé par défaut en prod (`MDM_INTEGRATION_ENABLED=false`).

## En une phrase

Dès que plusieurs applications possèdent leur propre copie d'un même client
(`kbeauty-shop`, `sav-ticketing-php`), le risque classique en entreprise est la
**divergence de données** : un client renommé dans la boutique, mais pas dans le
SAV, qui garde sa copie figée au moment de l'import. Le MDM (Master Data
Management) centralise la **source de vérité** d'une donnée partagée et pousse les
mises à jour aux systèmes avals — concept-clé en **urbanisation SI**.

## 1. Pourquoi faire ça (le point de vue entreprise)

| Besoin | Ce que le MDM apporte |
|---|---|
| Éviter la divergence silencieuse | Sans lui, `sav-ticketing-php` ne voit jamais qu'un client a changé de nom/email dans la boutique après son premier retour importé |
| Un seul endroit où trancher un conflit | Si deux systèmes ont des vues différentes du même client, le golden record dit laquelle est la bonne |
| Réutilisable au-delà du SAV | Un futur service (facturation, CRM) n'a qu'à écouter le même événement, pas à interroger `kbeauty-shop` directement |

**Limite honnête** : à la taille actuelle de l'écosystème (deux systèmes avals, un
seul champ d'identité partagé), un simple appel HTTP direct de `sav-ticketing-php`
vers `kbeauty-shop` aurait suffi. Le MDM se justifie dès qu'un **troisième** système
a besoin de la même donnée — c'est l'exercice pédagogique : construire le bon
réflexe (centraliser plutôt que multiplier les appels point à point) avant d'en
avoir besoin en vrai.

## 2. Vue d'ensemble

```
 kbeauty-shop (Laravel)              RabbitMQ              kbeauty-customer-mdm (Go)              sav-ticketing-php (PHP natif)
 ─────────────────────               ────────              ───────────────────────                ─────────────────────────────
 profil utilisateur modifie
 (nom et/ou email)
        │
        ▼  meme pattern outbox que le SAV/notifications (doc 20)
 outbox_messages
        │
        ▼  rabbitmq:publish-outbox (chaque minute)
 kbeauty.exchange ──(customer.updated)──► file mdm.customer-updates
                                                                    │
                                                                    ▼
                                                         golden record (SQLite)
                                                         upsert idempotent, timestamp-compare
                                                                    │
                                                                    ▼
                                            kbeauty.exchange ◄──(customer.golden_record.updated)
                                                   │
                                                   ▼ file sav.clients
                                                                                        ConsommateurClientMiseAJour
                                                                                        met a jour clients.nom/email
                                                                                        (retrouve par source_user_id,
                                                                                        ou par email en 1ere synchro)
```

Le MDM **republie** l'événement après l'avoir appliqué à son golden record — il
n'est pas un simple relais, il arbitre d'abord (idempotence par comparaison
d'horodatage : un message en retard ou déjà appliqué est ignoré sans effet).

## 3. Choix d'architecture

### 3.1 Pourquoi Go plutôt qu'une 4e stack choisie au hasard

Java (Spring Boot), Python (Scrapy), Node (NestJS) et PHP (deux fois, avec et sans
framework) couvraient déjà la diversité de paradigmes utile à l'exercice. Go a été
choisi pour montrer un style radicalement différent des précédents : pas de
framework, pas d'injection de dépendances façon Spring/NestJS — juste la bibliothèque
standard (`net/http`, `database/sql`) et un typage explicite sans magie. Un langage
très présent dans l'infrastructure/plateforme d'entreprise (Kubernetes, Docker,
Terraform sont écrits en Go), contrairement aux trois précédents plutôt côté
applicatif.

### 3.2 Idempotence par comparaison d'horodatage, pas par UNIQUE

Contrairement au SAV (`retour_kbeauty_id` UNIQUE — un même retour ne crée jamais
deux tickets) ou aux notifications (déduplication par identifiant d'événement), le
golden record n'a pas vocation à être créé une fois puis figé : il doit accepter
des mises à jour répétées, mais jamais revenir à un état plus ancien si RabbitMQ
livre deux messages dans le désordre. D'où la règle : `Upsert` compare
`updatedAt` du message entrant à celui du record existant, et ignore silencieusement
tout message qui n'est pas strictement plus récent.

### 3.3 Limite assumée : la toute première synchro d'un client déjà ancien

`sav-ticketing-php` a des clients créés par import de retour, **avant** que cette
intégration existe (`source_user_id` encore `NULL`). La première mise à jour reçue
pour un tel client doit le retrouver par email, faute de mieux. Si cette toute
première mise à jour change **le nom et l'email en même temps**, la recherche par
(nouvel) email ne retrouve jamais la ligne existante (qui porte encore l'ancien
email) : un nouveau client est créé à tort, l'ancien reste orphelin. Une fois
`source_user_id` lié, ce problème disparaît pour les mises à jour suivantes.

**Pourquoi ce choix plutôt qu'une solution plus robuste** : corriger ça
proprement demanderait de transporter l'ancien email dans le contrat d'événement
(`previousEmail`), ce que `kbeauty-shop` ne sait pas reconstituer facilement après
coup (il ne garde pas d'historique d'email). Documenté explicitement dans le code
(`MettreAJourClientGolden`) et le README plutôt que masqué — un jury MIAGE valorise
plus la lucidité sur une limite connue qu'une solution qui prétend ne pas en avoir.
Découvert via un test, pas anticipé à la conception : preuve que le TDD sert aussi à
cartographier les angles morts d'un design, pas seulement à vérifier le code écrit.

### 3.4 Sécurité : le seul compte RabbitMQ qui publie ET consomme sur l'exchange commun

Tous les autres comptes applicatifs (`kbeauty_shop`, `sav`, `notifications`) ne font
qu'un seul sens sur `kbeauty.exchange` (publier seulement, ou lire seulement). Le
compte `mdm` est le seul à faire les deux, parce que le service republie après avoir
arbitré — droit limité strictement à ce que ça impose (lecture/écriture sur
`kbeauty.exchange`, propriété exclusive de ses deux files `mdm.customer-updates` et
`mdm.rejected`), jamais un accès large type `guest`.

## 4. Les fichiers

### kbeauty-customer-mdm (repo séparé, Go)

| Fichier | Rôle |
|---|---|
| `main.go` | Câblage (env, SQLite, consumer, serveur HTTP), arrêt propre sur SIGINT/SIGTERM |
| `internal/mdm/store.go` | Golden record SQLite, `Upsert` idempotent par comparaison d'horodatage |
| `internal/mdm/contract.go` | Validation JSON Schema (`jsonschema/v5`, `AssertFormat = true`) |
| `internal/rabbitmq/consumer.go` | Consumer/republisher `amqp091-go`, file quorum + dead-letter |
| `internal/httpapi/server.go` | `GET /health`, `GET /customers/{email}` (lecture du golden record) |
| `contracts/rabbitmq/*.schema.json` | Les deux contrats (entrant, sortant) |

### kbeauty-shop (producteur, extension de l'outbox existant)

| Fichier | Rôle |
|---|---|
| `app/Infrastructure/Rabbitmq/CustomerUpdatedPayload.php` | Corps de l'événement `customer.updated` |
| `app/Http/Controllers/Settings/ProfileController.php` | Publie l'événement si `isDirty(['name','email'])`, derrière `MDM_INTEGRATION_ENABLED` |
| `app/Notifications/EmailAddressChanged.php` | Alerte de sécurité envoyée à l'**ancienne** adresse si l'email change — pas du MDM à proprement parler, mais déclenché par le même code |

### sav-ticketing-php (consommateur du golden record)

| Fichier | Rôle |
|---|---|
| `src/Integration/Kbeauty/ConsommateurClientMiseAJour.php` | Consumer RabbitMQ, même triptyque (contrat/idempotence/dead-letter) que `ConsommateurRetours` |
| `src/Service/MettreAJourClientGolden.php` | Retrouve le client (par `source_user_id`, puis par email), applique la mise à jour |
| `database/migrations/004_mdm_client.sql` | Colonne `source_user_id` sur `clients` (NULL, UNIQUE) |

### kbeauty-ecosystem (infra commune)

| Fichier | Rôle |
|---|---|
| `rabbitmq/creer-comptes.sh` | Compte `mdm` (seul profil publie+consomme sur `kbeauty.exchange`), extension du compte `sav` à ses nouvelles files `sav.clients(.rejetes)?` |

## 5. Lancer en local

```bash
# 1. RabbitMQ + comptes dedies (infra partagee)
cd ~/projects/kbeauty-ecosystem
docker start kbeauty_rabbitmq
./rabbitmq/creer-comptes.sh

# 2. Service MDM (Go)
cd ~/projects/kbeauty-customer-mdm
cp .env.example .env
go run .

# 3. Consumer SAV
cd ~/projects/sav-ticketing-php
php bin/consommer-clients-kbeauty.php

# 4. Boutique : modifier un profil utilisateur (nom/email) avec
#    MDM_INTEGRATION_ENABLED=true dans .env, puis :
php artisan rabbitmq:publish-outbox
```

Vérifier la propagation : `curl http://localhost:3001/customers/<email>` (golden
record côté MDM) puis la table `clients` de `sav_ticketing` (colonne
`source_user_id`).

## 6. Limites et suite

- **Pas de résolution automatique du cas §3.3** — resterait à concevoir un contrat
  v2 avec `previousEmail` si l'écosystème grandissait réellement.
- **Flux à sens unique uniquement** — le SAV ne peut pas corriger une donnée client
  et la faire remonter vers la boutique ; la boutique reste la seule source de
  vérité. Un vrai MDM d'entreprise gère aussi la réconciliation bidirectionnelle
  (qui gagne en cas de conflit entre deux sources), hors scope ici.
- **Production** : comme pour le SAV et les notifications, pas de RabbitMQ hébergé
  en prod aujourd'hui — intégration désactivée tant que ce n'est pas le cas.

## 7. Hébergement envisagé (pas encore fait)

**Railway**, même choix que `kbeauty-notifications-service` (doc 21, §7) et
pour les mêmes raisons (pas de dogme "tout sur Azure", coût de mise en route
Azure déjà amorti sur les deux services existants, CloudAMQP réutilisable
tel quel). Un argument supplémentaire propre à Go : un binaire statique
compile en une image Docker minuscule, donc un démarrage très rapide — l'un
des arguments de diversité technique à citer en entretien (face à la JVM,
plus lourde à démarrer, de `kbeauty-ai-core-service`).

L'alternative sérieuse écartée est **Fly.io** (très orienté Go/latence
faible) : techniquement pertinent, mais ajouterait un deuxième hébergeur à
gérer pour un service aussi simple — pas justifié ici.

## 8. Questions d'entretien probables

**« C'est quoi un MDM, en une phrase ? »**
Un système qui dit "voici la version officielle de cette donnée" quand plusieurs
applications en ont chacune leur propre copie — évite qu'elles divergent en
silence.

**« Pourquoi pas un simple appel HTTP de sav-ticketing-php vers kbeauty-shop ? »**
Ça marcherait à deux systèmes. Le MDM devient utile au troisième système qui a
besoin de la même donnée : un seul point à interroger/écouter plutôt que des
appels point à point qui se multiplient en carré du nombre de systèmes.

**« Quelle est la limite que tu as trouvée toi-même, pas qu'on t'a signalée ? »**
Le cas du client jamais lié dont le tout premier événement change nom et email en
même temps (§3.3) — trouvé en écrivant un test, pas en concevant le système à
l'avance. Assumé et documenté plutôt que masqué.

**« Pourquoi Go, cette fois ? »**
Pour une 5e stack réellement différente des précédentes (pas de framework, typage
explicite) — voir §3.1.
