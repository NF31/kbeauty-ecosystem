# kbeauty-ecosystem

Infrastructure commune (Docker Compose) pour les microservices de montee en competence
lies au projet Kbeauty (boutique `kbeauty-shop`, depot prive). Le dossier technique
complet est dans [docs/montee-competence/](docs/montee-competence/README.md).

Ne contient pas de code applicatif : chaque microservice (Spring Boot, Scrapy,
PHP natif, NestJS, Go) vit dans son propre repo, clone a cote de celui-ci sous
~/projects/. Un pont
Next.js avait ete envisage au depart pour la page diagnostic, mais abandonne
des la Phase 3 au profit d'Inertia (integre au monolithe Laravel) - jamais
cree, voir [09-phase3-diagnostic-inertia.md](docs/montee-competence/09-phase3-diagnostic-inertia.md).

## Services

- **cassandra** (:9042) : data lake NoSQL pour le scraping
- **rabbitmq** (:5672, dashboard :15672) : bus de messages AMQP
- **valkey** (:6379) : cache/queue compatible Redis
- **sonarqube** (:9000) : qualimetrie de code

## Comptes RabbitMQ (moindre privilege)

```bash
./rabbitmq/creer-comptes.sh   # rejouable
```

Cree l'exchange commun `kbeauty.exchange` et un compte par application,
avec seulement les droits dont elle a besoin :

- `kbeauty_shop` : publie sur `kbeauty.exchange` (retours, newsletter,
  changement d'identite client), consomme `diagnostic.created` ;
- `sav` (sav-ticketing-php) : possede ses files `sav.retours`, `sav.clients`
  et leurs files de rejets associees, lit `kbeauty.exchange` (pour y lier
  ses files) ; ne peut ni publier sur `kbeauty.exchange` ni le supprimer ;
- `notifications` (kbeauty-notifications-service) : possede sa file
  `notifications.newsletter` et sa file de rejets, meme principe que `sav` ;
- `mdm` (kbeauty-customer-mdm) : seul compte qui publie ET lit sur
  `kbeauty.exchange` (il republie le golden record apres chaque mise a
  jour), possede ses files `mdm.customer-updates` et `mdm.rejected`.

Mots de passe de developpement par defaut, a fournir en variables
d'environnement en production (voir l'en-tete du script). Integration
detaillee : [20-integration-sav-rabbitmq.md](docs/montee-competence/20-integration-sav-rabbitmq.md)
(SAV), [21-notifications-service.md](docs/montee-competence/21-notifications-service.md) (notifications),
[22-mdm-golden-record.md](docs/montee-competence/22-mdm-golden-record.md) (MDM).

`guest` (droits complets) sert encore a kbeauty-ai-core-service : lui creer
un compte limite, puis supprimer `guest`.

## Usage

```bash
docker compose up -d              # tout demarrer
docker compose stop cassandra sonarqube   # arreter les services lourds si RAM limitee
docker compose ps -a              # etat des conteneurs
```

**Attention memoire** : cassandra et sonarqube sont bases sur la JVM et consomment
2-4 Go de RAM chacun. Sur une VM WSL a RAM limitee, ne les laisser actifs que
lorsqu'ils sont utilises (Phase 4 pour cassandra, scan qualite pour sonarqube).

**Piege reseau (trouve le 2026-08-10)** : pour joindre un conteneur depuis un
autre conteneur sur `kbeauty_network`, utiliser le nom du **service** Compose
(ex. `sonarqube`, `cassandra`), pas le `container_name` (ex. `kbeauty_sonarqube`).
Les `container_name` de ce fichier contiennent un underscore, invalide dans un
en-tete HTTP `Host` strict (RFC 952/1123) — des serveurs comme Tomcat
(SonarQube) rejettent la requete en `400 Bad Request` sans message clair.

## Scan de secrets (gitleaks)

Garde-fou contre le commit accidentel de clés API / tokens.

```bash
# Une fois par clone :
git config core.hooksPath .githooks
```

Le hook `pre-commit` lance `gitleaks git --staged` et bloque le commit si un
secret est détecté (`git commit --no-verify` pour forcer). Même scan en CI sur
chaque push / PR (`.github/workflows/gitleaks.yml`), sur l'historique complet.
Faux positifs éventuels à déclarer dans `.gitleaks.toml`.
