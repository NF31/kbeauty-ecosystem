---
title: CI/CD — Pest, JUnit & scan qualité SonarCloud
group: Montée en compétence
order: 17
---

← [Retour au sommaire](README.md)

# 17. CI/CD — Pest, JUnit & scan qualité SonarCloud

## Objectif

Automatiser ce qui se faisait jusque-là à la main : lancer les tests (Pest côté
Laravel, JUnit côté Spring Boot) et un scan de qualité de code à chaque `push`/
pull request, plutôt qu'au bon vouloir du développeur. C'est la dernière case
non cochée de la Phase 6 côté CI (le déploiement multi-cloud lui-même est
documenté dans [15-phase6-deploiement-azure.md](15-phase6-deploiement-azure.md)).

## État de départ

- `kbeauty-shop` avait déjà `tests.yml` (Pest + Pint + PHPStan + lint JS/TS),
  fonctionnel depuis longtemps — rien à faire côté tests PHP.
- `kbeauty-ai-core-service` et `kbeauty-ingredients-scraper` n'avaient que
  `gitleaks.yml` (scan de secrets) — aucun test automatisé en CI.
- Un `sonar-project.properties` existait déjà sur `kbeauty-shop`, mais pointait
  vers l'instance **SonarQube locale** (`kbeauty-ecosystem/docker-compose.yml`,
  Phase 1) — jamais exécuté qu'à la main, jamais en CI. Un scan cloud (GitHub
  Actions) ne peut pas atteindre un conteneur Docker qui tourne sur la machine
  du développeur : il fallait un service **hébergé**.

## SonarQube local vs SonarCloud — pourquoi changer d'outil

SonarQube (le moteur d'analyse statique) existe sous deux formes :

- **auto-hébergé** (ce qui tournait déjà dans `kbeauty-ecosystem`) : gratuit,
  mais seulement joignable depuis le réseau local — inutilisable par un runner
  GitHub Actions qui tourne sur une machine Microsoft, ailleurs sur Internet.
- **SonarQube Cloud** (le nom actuel de SonarCloud) : même moteur, hébergé par
  Sonar, avec une intégration GitHub Actions native. Plan **Free** : jusqu'à
  50 000 lignes de code privées, 5 membres — largement suffisant ici
  (`kbeauty-shop` ≈ 31 000 lignes en Phase 1, `kbeauty-ai-core-service` ≈ 700).

Décision : garder l'instance locale pour l'exploration ponctuelle en dev (déjà
documentée en Phase 1), utiliser SonarCloud pour le scan automatique en CI.

## Mise en place SonarCloud

1. Compte créé sur [sonarcloud.io](https://sonarcloud.io) via connexion GitHub
   (pas de mot de passe séparé à gérer).
2. Organisation `nf31` créée, plan **Free** sélectionné explicitement (l'écran
   par défaut pousse vers un essai payant "Team" — il faut cliquer sur le lien
   du plan gratuit, pas sur "Continue"/"Start trial").
3. Import des deux repos concernés (`kbeauty-shop`, `kbeauty-ai-core-service`)
   — `kbeauty-ingredients-scraper` (Python) laissé de côté pour l'instant, pas
   demandé explicitement dans la roadmap ("Pest + JUnit" ne couvre que
   PHP/Java).
4. Pour chaque projet : génération d'un **token** (Mon compte → Security),
   posé comme secret GitHub `SONAR_TOKEN` sur les deux repos via
   `gh secret set SONAR_TOKEN --repo <owner>/<repo>` — jamais commit en clair.

### Le piège : Automatic Analysis vs CI-based Analysis

SonarCloud propose par défaut un mode **Automatic Analysis** : dès qu'un repo
est importé, il scanne lui-même le code à chaque push, sans configuration.
Pratique, mais **incompatible** avec un scan piloté depuis la CI (erreur
explicite à l'exécution : *"You are running CI analysis while Automatic
Analysis is enabled. Please consider disabling one or the other."*) — les deux
modes écrivent une analyse pour le même projet et se marchent dessus.

Fix : dans chaque projet SonarCloud → **Administration → Analysis Method**
(accessible aussi via `Project onboarding` lors du premier import) → toggle
**"Automatic analysis"** désactivé. Piège rencontré en pratique : le CI avait
tourné une première fois *avant* la désactivation du toggle sur les deux
projets → premier run en échec sur les deux repos → re-run après
désactivation → passe.

## `kbeauty-shop` — job SonarQube ajouté à `tests.yml`

Nouveau job `sonarqube`, déclenché après le job `ci` existant (`needs: ci`) :

```yaml
sonarqube:
  name: SonarQube
  runs-on: ubuntu-latest
  needs: ci
  steps:
    - uses: actions/checkout@...
      with:
        fetch-depth: 0 # historique complet requis pour l'analyse SonarQube
    - uses: SonarSource/sonarqube-scan-action@...
      env:
        SONAR_TOKEN: ${{ secrets.SONAR_TOKEN }}
```

`fetch-depth: 0` : par défaut `actions/checkout` ne récupère que le dernier
commit (clone superficiel) — SonarQube a besoin de l'historique complet pour
calculer les métriques de nouveauté ("new code" vs code existant).

`sonar-project.properties` (déjà présent, Phase 1) mis à jour : `projectKey`
et `organization` pointent maintenant vers `NF31_kbeauty-shop`/`nf31` au lieu
de la config locale générique — le reste (exclusions vendor/node_modules,
encodage) était déjà correct et conservé tel quel.

## `kbeauty-ai-core-service` — nouveau workflow `tests.yml`

Rien n'existait : création du workflow complet, deux jobs.

```yaml
jobs:
  junit:
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
      - uses: actions/setup-java@v4
        with: { java-version: '21', distribution: 'temurin', cache: maven }
      - run: mvn --batch-mode test
      - uses: mikepenz/action-junit-report@v5
        if: always()
        with: { report_paths: 'target/surefire-reports/TEST-*.xml' }
      - if: github.event.pull_request.head.repo.fork == false
        env: { SONAR_TOKEN: ${{ secrets.SONAR_TOKEN }} }
        run: mvn --batch-mode verify sonar:sonar
```

- **JDK 21** explicitement (pas la dernière version disponible) : doit
  correspondre à `<java.version>` dans `pom.xml`. Testé en local avec le
  mauvais JDK par défaut (21 **et** 25 installés sur la machine dev, 25 actif
  par défaut) : `mvn test` échouait avec une erreur Mockito ("cannot mock this
  class") — un JDK trop récent casse l'instrumentation bytecode de Mockito.
  Aucun rapport avec le code lui-même ; en forçant `JAVA_HOME` sur le JDK 21,
  les 30 tests passent. La CI ne rencontre pas ce problème car
  `actions/setup-java` installe précisément la version demandée.
- **`action-junit-report`** : transforme les rapports XML Surefire
  (`target/surefire-reports/TEST-*.xml`, format JUnit standard) en résumé
  lisible directement dans l'onglet "Checks" de la PR, sans avoir à ouvrir les
  logs bruts.
- **`sonar:sonar` skip sur les forks** (`github.event.pull_request.head.repo.fork
  == false`) : un token secret n'est jamais transmis aux workflows déclenchés
  depuis une PR d'un fork externe (mesure de sécurité GitHub) — le job
  planterait sans cette garde. Non pertinent tant que le repo reste privé et
  sans contributeur externe, mais coûte rien à poser dès maintenant.

`pom.xml` : ajout du plugin `sonar-maven-plugin` (fournit le goal
`sonar:sonar`) et de trois propriétés (`sonar.projectKey`,
`sonar.organization`, `sonar.host.url`) — équivalent Maven du fichier
`sonar-project.properties` utilisé côté PHP.

## Vérification

- `kbeauty-shop` : jobs `ci` et `sonarqube` verts sur `main` après merge
  ([PR #290](https://github.com/NF31/kbeauty-shop/pull/290)).
- `kbeauty-ai-core-service` : job `junit` (30/30 tests) et scan SonarCloud
  verts sur la PR ([PR #15](https://github.com/NF31/kbeauty-ai-core-service/pull/15))
  après correction du conflit Automatic/CI Analysis.
- Sur SonarCloud, chaque projet affiche désormais `github` comme source de la
  dernière analyse (pas `automatic`) — confirme que c'est bien le scan piloté
  par CI qui alimente le dashboard.

## Ce qui reste

- `kbeauty-ingredients-scraper` (Python) n'a pas de CI de tests — hors
  périmètre de la demande initiale ("Pest + JUnit"), à considérer séparément
  si des tests `pytest` sont ajoutés au projet.
- ~~Déploiement continu (CD) automatique côté Azure App Service
  (`kbeauty-ai-core-service`)~~ — fait : le workflow `main_kbeauty-ai-core.yml`
  généré par Azure (`az webapp deployment github-actions add`) redéploie à
  chaque push sur `main`, distinct de la CI qualité documentée ici. Étendu
  depuis pour embarquer l'agent APM New Relic dans le package
  ([doc 18](18-observabilite-newrelic.md)).

## Enseignement (portée MIAGE)

Le conflit Automatic Analysis / CI Analysis illustre un principe plus large :
deux systèmes d'automatisation qui touchent la même ressource sans se
coordonner finissent par se marcher dessus, même quand chacun fonctionne
correctement pris isolément. C'est le même type de problème qu'un
ordonnancement de traitements batch mal conçu en urbanisation SI — la
solution n'est jamais de désactiver l'un au hasard, mais de comprendre lequel
des deux doit rester la source de vérité.
