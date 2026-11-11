---
title: Vue d'ensemble de l'écosystème distribué
group: Montée en compétence
order: 1
---

← [Retour au sommaire](README.md)

# 1. Vue d'ensemble de l'écosystème distribué (2026)

Le système d'information est conçu selon les principes modernes de la **Persistance Polyglotte** et de l'**Architecture Orientée Événements (Event-Driven)**. Le cœur transactionnel (ventes, paniers, stocks) est isolé des calculs lourds d'Intelligence Artificielle et de la collecte de données de masse (Big Data) pour garantir une tolérance aux pannes et des performances optimales.

> Mis à jour le 2026-08-10 : le pont Next.js décrit initialement plus bas a été abandonné dès la Phase 3 (2026-08-02) au profit d'Inertia — voir [04-securite-auth.md](04-securite-auth.md) et [09-phase3-diagnostic-inertia.md](09-phase3-diagnostic-inertia.md) pour l'architecture réellement construite. Ce document reflète maintenant l'état réel, pas l'intention de départ.

## 🏢 Répartition des Modules et Hébergement Cloud

*   **Boutique E-Commerce Principale** : Propulsée par **Laravel 13.20.0 / Inertia.js / React / TypeScript / Tailwind v4**. Elle gère le catalogue multi-axes, l'authentification Fortify Headless (Passkeys, 2FA), le panier via un `CartService` natif, le tunnel d'achat Stripe, et — depuis la Phase 3 — la page diagnostic de peau, servie **dans le même monolithe Inertia** (pas de frontend séparé).
    *   *Hébergement* : **Laravel Cloud** (Infrastructure managée native pour PHP, Vite et les workers Horizon).
*   **Moteur d'IA & RAG Sémantique** : Propulsé par **Java 21 / Spring Boot 3.4+ / Hibernate**. API REST asynchrone de calcul métier et de matching d'ingrédients INCI.
    *   *Hébergement* : **Azure Container Apps** (Serverless Docker à scalabilité automatique).
*   **Social Listening & Extraction Data** : Propulsé par **Python 3.12 / Scrapy Framework / Scrapy-Playwright**. Robot d'extraction industrielle de données de marché.
    *   *Hébergement* : **Azure Virtual Machine (Ubuntu Server)** pour un contrôle total sur les entrées/sorties du système de fichiers.
