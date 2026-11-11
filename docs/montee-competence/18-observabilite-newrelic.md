---
title: Observabilité — APM New Relic (Java & Python)
group: Montée en compétence
order: 18
---

← [Retour au sommaire](README.md)

# 18. Observabilité — APM New Relic (Java & Python)

## Objectif

Passer de « je lis les logs quand quelque chose casse » à « je vois en continu
la santé de chaque service » : temps de réponse, débit, taux d'erreur, temps
passé dans chaque dépendance (base, API externe, file de messages), traces
détaillées des requêtes lentes.

L'outil est **New Relic** (offre gratuite via GitHub Education / GitHub Student
Developer Pack — 100 Go d'ingestion/mois, un utilisateur full-platform). Deux
services de l'écosystème sont instrumentés :

- `kbeauty-ai-core-service` (Spring Boot, Azure App Service) — agent **Java**.
- `kbeauty-ingredients-scraper` (Scrapy, Azure Container App Job) — agent
  **Python**.

Les deux remontent dans le **même compte, région EU** (`one.eu.newrelic.com`,
compte `8496139`). Le choix EU est définitif à la création du compte et
change le collecteur à viser (voir pièges plus bas).

## Pourquoi un agent APM, et pas juste des logs

Un agent APM s'attache au **runtime** (JVM, interpréteur Python) et
instrumente automatiquement les frameworks connus : chaque requête HTTP,
chaque requête SQL, chaque appel HTTP sortant, chaque publication/consommation
de message devient un *span* chronométré, rattaché à une *transaction*. On
obtient sans écrire une ligne de code :

- la décomposition du temps d'une requête (« 3 s dont 2,4 s en appel Anthropic,
  0,2 s en JPA, le reste en calcul ») ;
- le débit et le taux d'erreur par endpoint, en séries temporelles ;
- la liste des transactions les plus lentes, avec la trace complète ;
- le **traçage distribué** : quand un service en appelle un autre (HTTP ou
  file de messages), les spans des deux côtés sont reliés en une seule
  timeline.

Les logs restent utiles pour le détail applicatif ; l'APM donne la vue
d'ensemble et le chemin critique.

## Service 1 — `kbeauty-ai-core-service` (agent Java)

### Méthode : agent embarqué dans le package de déploiement

Azure App Service Linux en runtime « Java SE » (`JAVA|21-java21`) exécute un
fat jar, sans serveur d'applications où brancher un agent globalement. La
méthode prescrite par la [doc New Relic pour Java sur Azure App
Service](https://docs.newrelic.com/docs/apm/agents/java-agent/additional-installation/azure-web-apps/)
est :

1. **embarquer** `newrelic.jar` dans le package déployé ;
2. l'attacher au démarrage de la JVM via la variable d'environnement
   `JAVA_TOOL_OPTIONS=-javaagent:/home/site/wwwroot/newrelic/newrelic.jar`
   (la JVM honore `JAVA_TOOL_OPTIONS` inconditionnellement).

La CLI `newrelic install` (guided install) **ne s'applique pas** ici : elle
installe un agent d'infrastructure au niveau de l'OS sur une VM accessible en
SSH. App Service est du PaaS — pas d'hôte à administrer, et tout ce qui est
hors `/home` est effacé à chaque redémarrage.

### Changement CI ([PR #16](https://github.com/NF31/kbeauty-ai-core-service/pull/16))

Le workflow de déploiement (généré par Azure, `main_kbeauty-ai-core.yml`) a
reçu une étape de *staging* entre le build Maven et le déploiement :

```yaml
- name: Stage deployment package with New Relic agent
  run: |
    mkdir -p deploy
    curl -sfL -o /tmp/newrelic-java.zip https://download.newrelic.com/newrelic/java-agent/newrelic-agent/current/newrelic-java.zip
    unzip -oq /tmp/newrelic-java.zip -d deploy
    cp target/*.jar deploy/app.jar
```

et le paramètre `package:` de `azure/webapps-deploy` est passé de
`target/*.jar` au **dossier** `deploy/`. Quand `package` pointe un dossier,
l'action fait un *zip deploy* : le contenu atterrit directement sous
`/home/site/wwwroot/`. Le conteneur Java SE d'Azure lance `app.jar` à la
racine de wwwroot (nom canonique attendu), d'où le `cp target/*.jar
deploy/app.jar` ; le sous-dossier `newrelic/` ne gêne pas la détection du jar.

Résultat sur la box : `/home/site/wwwroot/app.jar` +
`/home/site/wwwroot/newrelic/newrelic.jar` (≈ 41 Mo).

### Variables d'environnement (app settings App Service, jamais dans git)

| Réglage | Valeur | Rôle |
|---|---|---|
| `NEW_RELIC_LICENSE_KEY` | `eu01x…NRAL` | clé d'ingestion, type **INGEST - LICENSE** |
| `NEW_RELIC_APP_NAME` | `kbeauty-ai-core-service` | nom de l'entité APM |
| `NEW_RELIC_HOST` | `collector.eu01.nr-data.net` | collecteur EU (voir piège) |
| `JAVA_TOOL_OPTIONS` | `-javaagent:/home/site/wwwroot/newrelic/newrelic.jar` | attache l'agent à la JVM |

### Piège — l'ordre de mise en place

`JAVA_TOOL_OPTIONS` qui pointe `-javaagent` sur un fichier **absent** empêche
la JVM de démarrer (appli complètement à terre). Il faut donc poser ce réglage
**après** que le déploiement ayant placé `newrelic/newrelic.jar` sur la box
soit passé. Séquence suivie :

1. poser `NEW_RELIC_LICENSE_KEY` / `_APP_NAME` / `_HOST` (sans effet tant que
   l'agent n'est pas attaché) ;
2. merger la PR → le déploiement embarque le jar ;
3. vérifier la présence du jar (API Kudu VFS :
   `https://<app>.scm.azurewebsites.net/api/vfs/site/wwwroot/newrelic/`) ;
4. poser `JAVA_TOOL_OPTIONS` → redémarrer.

### Piège — format de la clé de licence

Une clé d'ingestion valide fait **exactement 40 caractères**, se termine par
`NRAL`, et pour un compte EU commence par `eu01x`. Elle doit être de type
**INGEST - LICENSE**. Confusions rencontrées :

- une chaîne de **64 caractères hexadécimaux** (ce n'est **pas** une clé de
  licence, quelle que soit la colonne « type » affichée dans l'UI) ;
- une clé **INGEST - BROWSER** (agent JavaScript RUM, pas l'agent serveur) ;
- une clé `NRAK-…` (User API key, pour l'API REST, pas l'ingestion).

Symptôme d'une mauvaise clé, dans
`/home/site/wwwroot/newrelic/logs/newrelic_agent.log` :

```
com.newrelic ERROR: Remote preconnect call failed : com.newrelic.agent.LicenseException: {}.
com.newrelic ERROR: Invalid license key, the agent is no longer reporting information.
```

### Piège — le collecteur EU n'est pas auto-détecté de façon fiable

Même avec une clé qui commence par `eu01x`, l'agent Java ne bascule pas
toujours sur le collecteur européen. On le force explicitement via
`NEW_RELIC_HOST=collector.eu01.nr-data.net`. Marqueurs de succès dans le log :

```
com.newrelic INFO: Configured to connect to New Relic at collector.eu01.nr-data.net:443
com.newrelic INFO: Agent run id: …
com.newrelic INFO: Reporting to: https://one.eu.newrelic.com/redirect/entity/…
```

### Piège — le process JVM ne se recycle pas toujours

Après correction d'un app setting, `az webapp config appsettings set`
déclenche en principe un redémarrage — mais le conteneur (et donc la JVM)
peut survivre, et rester bloqué sur l'ancienne configuration (ici : l'ancienne
clé invalide, visible aux timestamps figés du process dans le log). Un `az
webapp restart` simple ne suffit pas toujours. Ce qui a marché : un **arrêt à
froid** —

```bash
az webapp stop  -n kbeauty-ai-core -g kbeauty-ai-core-rg
sleep 8
az webapp start -n kbeauty-ai-core -g kbeauty-ai-core-rg
```

— qui force un conteneur neuf, lequel relit l'environnement.

### Générer du trafic pour peupler les courbes

Le service est quasi inactif (il réagit à des événements RabbitMQ). Pour voir
autre chose que des graphes vides, on lui envoie du trafic réel :
`GET /hello`, `POST /diagnostics` et `GET /diagnostics` (en boucle, avec le
header `X-Internal-Api-Key`), plus quelques requêtes sans clé pour alimenter
la courbe d'erreurs (401). Chaque `POST /diagnostics` déclenche en plus une
publication RabbitMQ consommée par le `@RabbitListener` du même service —
c'est **la** trace distribuée réelle de l'écosystème aujourd'hui (producteur →
file → consommateur, à l'intérieur d'`ai-core`).

## Service 2 — `kbeauty-ingredients-scraper` (agent Python)

### Ce que ça apporte — et ce que ça n'apporte pas

Le scraper est un **job batch** (le conteneur exécute un crawl puis s'arrête ;
Azure Container App Job, cron `0 3 * * *`). Il **écrit dans Astra DB** et ne
communique ni avec `ai-core`, ni avec RabbitMQ. Il n'y a donc **pas** de trace
distribuée reliant le scraper à `ai-core` — rien ne les relie dans le code.

Ce que l'agent apporte quand même, en tant que **2ᵉ entité APM** de type
non-web : durée du crawl nocturne, débit, taux d'erreur, temps passé en E/S
réseau, tendance jour après jour, traces des runs anormaux — au lieu de ne
disposer que du log brut d'un `scrapy crawl`.

### Méthode : lanceur dédié + `newrelic-admin run-program`

L'agent Python instrumente automatiquement les frameworks **web**
(WSGI/ASGI), **pas** Scrapy, qui tourne sur le réacteur Twisted. Sans
transaction ouverte explicitement, `newrelic-admin run-program scrapy crawl …`
démarre bien l'agent mais n'enregistre **aucune** donnée applicative.

Solution retenue ([PR
#8](https://github.com/NF31/kbeauty-ingredients-scraper/pull/8)) : un point
d'entrée `ingredients_scraper/run.py` qui exécute tout le crawl à l'intérieur
d'une fonction décorée `@newrelic.agent.background_task` —

```python
@newrelic.agent.background_task(name="uniikon_gammes", group="Scrapy")
def _crawl():
    process = CrawlerProcess(get_project_settings())
    process.crawl(UniikonGammesSpider)
    process.start()  # bloque jusqu'à la fin du crawl

def main():
    if os.environ.get("NEW_RELIC_LICENSE_KEY"):
        newrelic.agent.register_application(timeout=25.0)
    try:
        _crawl()
    finally:
        newrelic.agent.shutdown_agent(timeout=15.0)
```

`ENTRYPOINT` du Dockerfile :
`newrelic-admin run-program python -m ingredients_scraper.run`.

Une extension Scrapy (`newrelic_extension.py`) se contente d'ajouter, sur
`spider_closed`, les compteurs de `crawler.stats` (items, réponses, erreurs,
retries) en attributs de la transaction, et de la marquer en erreur si le
crawl s'est arrêté anormalement.

### Piège — transaction à cheval sur deux signaux : « no active trace »

Première version : l'extension ouvrait la `BackgroundTask` sur
`spider_opened` et la fermait sur `spider_closed`. La transaction est
suivie par thread dans un *trace cache* ; à la fermeture, l'agent lève
`TraceCacheNoActiveTraceError: no active trace`. En faisant porter toute la
durée du crawl par **un seul appel de fonction** décoré (le lanceur
ci-dessus), la transaction reste active du début à la fin, sur le thread du
réacteur — plus d'erreur.

### Piège — pas d'interpolation `${...}` dans `newrelic.ini`

Mettre `license_key = ${NEW_RELIC_LICENSE_KEY}` dans le `.ini` envoie la
chaîne **littérale** `${NEW_RELIC_LICENSE_KEY}` au collecteur → *« an
incorrect license key has been supplied »*. Le fichier `.ini` ne fait pas
d'interpolation d'environnement, et un réglage présent dans le `.ini` **prime**
sur la variable d'environnement correspondante. Conclusion : **ne pas mettre
`license_key` dans le fichier du tout** — l'agent lit alors
`NEW_RELIC_LICENSE_KEY` dans l'environnement. Le collecteur EU, lui, est une
valeur littérale (`host = collector.eu01.nr-data.net`), donc il reste dans le
`.ini`.

### Piège — job court : enregistrement et flush explicites

- `register_application(timeout=25)` avant le crawl : sur un job de quelques
  minutes, une transaction démarrée avant que l'appli soit enregistrée auprès
  du collecteur devient un no-op silencieux.
- `shutdown_agent(timeout=15)` à la fin : sans lui, le process se termine
  avant le prochain *harvest* (envoi périodique, ~60 s) et le run ne remonte
  jamais.

### Configuration Azure

Secret `newrelic-license-key` + variables d'environnement
`NEW_RELIC_LICENSE_KEY` (secretRef), `NEW_RELIC_APP_NAME`,
`NEW_RELIC_ENVIRONMENT=production` posés sur le Container App Job via
`az containerapp job secret set` / `az containerapp job update` — même schéma
que `ASTRA_TOKEN` / `VOYAGE_API_KEY`, jamais dans le repo.

### Comportement en local

Sans `NEW_RELIC_LICENSE_KEY` dans l'environnement, `@background_task` et
l'extension (qui lève `NotConfigured`) sont des no-op : `scrapy crawl
uniikon_gammes` fonctionne à l'identique en dev.

## Lire le dashboard APM d'un service quasi inactif

Points relevés sur la page d'`ai-core-service` juste après l'installation, et
leur interprétation :

- **Throughput 0,03 rpm** : le service est au repos (aucun événement dans la
  file). Normal — d'où la génération de trafic ci-dessus.
- **« 5 slowest transactions » →
  `Initializer/ServletContextListener/…/contextInitialized`** : c'est la
  transaction de **démarrage** Spring/Tomcat, pas du trafic réel. Sur un
  service sans requêtes, c'est la seule « transaction » que l'agent a vue.
- **« Distributed tracing — No data »** + invite *« use our guided install »* :
  attendu tant qu'un seul service instrumenté envoie des traces. L'invite
  *guided install* est à ignorer (le traçage distribué est actif par défaut
  dans l'agent). Se peuple dès qu'`ai-core` reçoit du trafic (spans
  publication → consommation RabbitMQ).
- **« Infrastructure — No infrastructure agent data found »** : attendu en
  PaaS — pas d'hôte où poser un agent d'infrastructure. À ignorer.
- **« Vulnerabilities — 7 Critical / 27 High »** : c'est le scan **SCA** de New
  Relic (les dépendances du jar comparées à des bases de CVE). À distinguer de
  SonarCloud, qui analyse le **code du projet** lui-même
  ([doc 17](17-cicd-tests-sonarcloud.md)), pas ses dépendances.

## Vérification

- `kbeauty-ai-core-service` : agent Java 9.4.0, `newrelic_agent.log` →
  `Agent run id` + `Reporting to: https://one.eu.newrelic.com/…` (entité APM
  `440830275`) ; `GET /hello` répond 200, agent attaché ; courbes de débit /
  temps de réponse alimentées après génération de trafic.
- `kbeauty-ingredients-scraper` : agent Python 13.5.0, d'abord validé en
  exécution locale (`newrelic-admin run-program` + crawl réduit) → `Reporting
  to: one.eu.newrelic.com`, entité APM `430639273` créée, transaction
  `Scrapy/uniikon_gammes` fermée proprement, arrêt d'agent propre. Secret +
  variables d'env posés sur le Container App Job. Puis confirmé en conditions
  réelles : après merge de la PR #8 et rebuild de l'image, un run manuel du
  job Azure remonte la transaction `OtherTransaction/Scrapy/uniikon_gammes`
  (≈ 149 s, sans erreur, `host` = le replica du Container App Job), vérifiée
  par requête NerdGraph (`SELECT … FROM Transaction WHERE appName =
  'kbeauty-ingredients-scraper'`).

## Ce qui reste

- ~~**Rebuild de l'image du scraper** après merge de la PR #8, puis un run
  manuel du job pour valider le premier crawl instrumenté~~ — fait. Piège
  rencontré : `az acr build` (build côté serveur du registre) est **refusé**
  sur cette souscription — `TasksOperationsNotAllowed`, les ACR Tasks sont
  désactivées pour tout le registre (palier MSDN/Free ; ne se débloque que
  par une demande de support Azure). Contournement immédiat : build **local**
  `docker build --platform linux/amd64` + `docker push` vers
  `kbeautyscraperacr2734.azurecr.io`, puis `az containerapp job start` →
  exécution `Succeeded`, 78/78 pages, 335 items, `finish_reason: finished`.
  Correctif durable : un workflow GitHub Actions
  (`docker/build-push-action` + `azure/login`) qui build et pousse l'image à
  chaque `push` sur `main` — c'est le seul repo de l'écosystème sans CD
  d'image, à ajouter séparément.
- **Alertes** (1–2) : temps de réponse `ai-core` > 2 s, taux d'erreur > 5 %,
  ou échec du job scraper.
- **Un dashboard custom** : latence du matching produit, temps d'appel Voyage,
  durée du dernier crawl, nombre d'items — une vue métier plutôt que par
  service.
- **Marqueurs de déploiement** depuis la GitHub Action d'`ai-core` (annoter le
  graphe APM à chaque déploiement).

## Enseignement (portée MIAGE)

L'observabilité n'est pas un ajout cosmétique : c'est la condition pour
**piloter** un SI distribué plutôt que le subir. Trois principes se dégagent
de la mise en place :

1. **La méthode d'instrumentation dépend du modèle d'exécution.** Serveur
   web long-vivant (agent global via la JVM), job batch court (transaction
   explicite + flush forcé), PaaS vs VM (pas d'agent d'infra) : le même outil
   se pose différemment selon le contexte de déploiement. Reconnaître le
   modèle d'exécution avant de choisir la recette évite les impasses.
2. **Le traçage distribué ne se décrète pas, il suit les intégrations
   réelles.** Deux services n'apparaissent sur une même timeline que s'ils
   s'appellent effectivement. Le scraper reste isolé parce que
   l'architecture le veut ainsi (il alimente Astra, point) — et c'est un
   choix défendable, pas un manque à combler.
3. **Un signal d'outil se lit dans son périmètre.** « 7 vulnérabilités
   critiques » côté New Relic (dépendances) et un quality gate vert côté
   SonarCloud (code) ne se contredisent pas : ils ne mesurent pas la même
   chose. Croiser les sources sans confondre leurs périmètres est une
   compétence de gouvernance à part entière.
