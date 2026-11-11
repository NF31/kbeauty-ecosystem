# Dossier technique — Montée en compétence (préparation Master MIAGE)

> Exercice de montée en compétence dans le cadre des études (préparation à un Master MIAGE — ingénierie des processus métier). Ne décrit **pas** l'architecture réelle du projet Kbeauty en production, qui reste un monolithe Laravel/Inertia/React volontairement simple. L'objectif est pédagogique : manipuler des briques (microservices Java, event-driven, NoSQL, Big Data, urbanisation SI) absentes de la stack de production, connectées en périphérie du projet existant à titre d'expérimentation.

## Sommaire

0. [Portefeuille de projets — écosystème kbeauty](00-portfolio.md)
1. [Vue d'ensemble de l'écosystème distribué](01-vue-ensemble.md)
2. [Référentiel des bases de données & flux (persistance polyglotte)](02-bases-donnees.md)
3. [Gestion des emails & monitoring croisé](03-emails-monitoring.md)
4. [Architecture de sécurité & authentification (Fortify Headless)](04-securite-auth.md)
5. [Outils de gouvernance, modélisation & pilotage (SI)](05-gouvernance-outils.md)
6. [Manuel d'installation des composants (WSL Ubuntu)](06-installation.md)
7. [Axes hors programme (extensions libres)](07-axes-hors-programme.md)
8. [Structure de dossiers sous WSL Ubuntu](08-structure-ubuntu.md)
9. [Roadmap de développement phasée](ROADMAP.md)
10. [Phase 3 — Page diagnostic en Inertia (pas de pont Next.js)](09-phase3-diagnostic-inertia.md)
11. [Phase 4 — Scraping Scrapy & pipeline Cassandra](10-phase4-scraping-cassandra.md)
12. [Embeddings, RAG & pgvector — comprendre la brique avant de la coder](11-embeddings-rag-pgvector.md)
13. [Consommateur RabbitMQ Laravel & contrat JSON Schema](12-contrat-rabbitmq-laravel.md)
14. [Phase 5 — Diagnostic peau réel (vision Claude)](13-diagnostic-vision-laravel.md)
15. [Phase 0 — Modélisation SI (BPMN, UML, C4) & backlog](14-phase0-modelisation.md)
16. [Phase 6 — Déploiement multi-cloud (Azure + services manages)](15-phase6-deploiement-azure.md)
17. [CI/CD — Pest, JUnit & scan qualité SonarCloud](17-cicd-tests-sonarcloud.md)
18. [Observabilité — APM New Relic (Java & Python)](18-observabilite-newrelic.md)
19. [Intégration avec le SAV (sav-ticketing-php) via RabbitMQ](20-integration-sav-rabbitmq.md)
20. [Microservice de notifications transactionnelles (NestJS)](21-notifications-service.md)
21. [Service de référentiel client unique — MDM (Go)](22-mdm-golden-record.md)
