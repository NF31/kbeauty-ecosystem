---
title: Gestion des emails & monitoring croisé
group: Montée en compétence
order: 3
---

← [Retour au sommaire](README.md)

# 3. Gestion des emails & monitoring croisé

## A. Centralisation de la Logique d'Envoi (Resend)

*   **Principe architectural** : centraliser l'envoi d'e-mails côté Laravel pour éviter de dupliquer clés API, configuration de domaine (`boutique.nfdev.fr`) et gabarits HTML/CSS bilingues (FR/EN) entre plusieurs services.
*   **Le flux** : lorsqu'un événement nécessite un e-mail (ex. diagnostic de peau terminé), Spring Boot publie un message dans RabbitMQ. Un worker Laravel intercepte l'ordre, génère l'e-mail via son infrastructure native et l'expédie via le SDK `resend/resend-laravel`.

## B. Observabilité et Résilience (Sentry & Horizon)

*   **Sentry Unifié** : un DSN unique configuré sur toutes les briques applicatives (Laravel, Next.js, Spring Boot) avec des tags de segmentation (`environment`, `service`).
*   **Observabilité des Files d'Attente** : un listener personnalisé sur l'événement `JobFailed` de Laravel Horizon permet d'alerter l'administrateur en cas d'échec d'une tâche asynchrone (timeout LLM, quota API dépassé), avec la trace d'exception associée.
