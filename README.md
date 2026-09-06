# kbeauty-ecosystem

Infrastructure commune (Docker Compose) pour les microservices de montee en competence
lies au projet Kbeauty (voir le repo principal kbeauty-shop, dossier docs/montee-competence/).

Ne contient pas de code applicatif : chaque microservice (Spring Boot, Scrapy)
vit dans son propre repo, clone a cote de celui-ci sous ~/projects/. Un pont
Next.js avait ete envisage au depart pour la page diagnostic, mais abandonne
des la Phase 3 au profit d'Inertia (integre au monolithe Laravel) - jamais
cree, voir kbeauty-shop/docs/montee-competence/09-phase3-diagnostic-inertia.md.

## Services

- **cassandra** (:9042) : data lake NoSQL pour le scraping
- **rabbitmq** (:5672, dashboard :15672) : bus de messages AMQP
- **valkey** (:6379) : cache/queue compatible Redis
- **sonarqube** (:9000) : qualimetrie de code

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
