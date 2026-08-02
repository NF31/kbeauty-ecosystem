# kbeauty-ecosystem

Infrastructure commune (Docker Compose) pour les microservices de montee en competence
lies au projet Kbeauty (voir le repo principal kbeauty-shop, dossier docs/montee-competence/).

Ne contient pas de code applicatif : chaque microservice (Spring Boot, Scrapy, Next.js)
vit dans son propre repo, clone a cote de celui-ci sous ~/projects/.

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
