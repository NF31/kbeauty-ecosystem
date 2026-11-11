---
title: Outils de gouvernance, modélisation & pilotage
group: Montée en compétence
order: 5
---

← [Retour au sommaire](README.md)

# 5. Outils de gouvernance, modélisation & pilotage (SI)

> Cette page décrit l'outillage **prévu** pour la gouvernance du dossier, pas ce qui est déjà produit. Statut réel (voir [`ROADMAP.md`](ROADMAP.md), Phase 0) : Jira, BPMN et UML sont toujours en attente au 2026-08-10 — repoussés volontairement au profit du code. SonarQube, lui, est en place depuis Phase 1 (2026-08-10), voir le détail plus bas.

*   **Gestion de Projet Agile (Jira / Kanban)** : sprints de 2 semaines, User Stories, Story Points, Burndown Chart. *Prévu, pas encore fait (Phase 0).*
*   **Modélisation des Processus (BPMN 2.0 via Draw.io)** : cartographie du tunnel d'achat Stripe et du circuit asynchrone des diagnostics de peau. *Prévu, pas encore fait (Phase 0).*
*   **Modélisation Objet (UML 2.5 via Draw.io)** : diagrammes de cas d'utilisation (rôles Spatie), diagrammes de séquence (échange de jetons), diagrammes de classes (entités Hibernate/JPA). *Prévu, pas encore fait (Phase 0).*
*   **Qualimétrie et Sécurité (SonarQube via Docker local)** : analyse statique continue TypeScript/Java, dette technique, couverture de tests, détection OWASP. **Fait (2026-08-10)** : premier scan baseline sur kbeauty-shop, voir Phase 1 dans `ROADMAP.md`.
*   **Intégration Google Docs** : schémas centralisés sur Draw.io, synchronisés avec le rapport d'études. *Prévu, dépend de la Phase 0.*
