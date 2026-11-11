---
title: Architecture de sécurité & authentification
group: Montée en compétence
order: 4
---

← [Retour au sommaire](README.md)

# 4. Architecture de sécurité & authentification

> Mis à jour le 2026-08-06 : le pont Next.js décrit initialement (jeton signé Laravel → Next.js) a été abandonné en Phase 3 (voir [décision détaillée](09-phase3-diagnostic-inertia.md#pourquoi-pas-de-pont-nextjs-finalement)). Ce document reflète l'architecture réellement construite.

Le site principal utilise Laravel Fortify (formulaires gérés en React/Inertia) pour l'authentification cliente. La page diagnostic de peau (Phase 3) tourne **dans le même monolithe Laravel/Inertia** que le reste de la boutique — pas de service frontend séparé, donc pas de jeton cross-service à émettre ni à valider.

## Le flux réel

1. La cliente, connectée sur la boutique principale via Fortify, clique sur « Besoin d'aide pour choisir ? » (page d'accueil).
2. Elle arrive sur `GET /diagnostic-peau`, une route Laravel classique protégée par le middleware `auth` standard — même mécanisme de session que le reste du site, aucune émission de jeton supplémentaire.
3. Le formulaire choisi part en `POST /diagnostic-peau` (même URL, méthode différente, même pattern que `commande/paiement`).
4. Le contrôleur (`Storefront\DiagnosticController`) notifie en arrière-plan `kbeauty-ai-core-service` (microservice Spring Boot, Phase 2) via `AiCoreDiagnosticClient` — un appel HTTP en `try/catch` avec timeout de 2 secondes, qui échoue silencieusement (juste un `Log::warning`) si le microservice n'est pas lancé. **Un module expérimental ne doit jamais pouvoir casser la boutique.**
5. **Rate limiting** : `throttle:3,60` sur la route `POST` uniquement (pas sur l'affichage du formulaire) — le garde-fou contre l'abus existe dès le début, même avec une analyse encore bidon (hardcodée, le vrai contenu IA arrive en Phase 5).
6. **Protection des données (RGPD)**, prévue pour la Phase 5 quand l'IA réelle sera branchée : les photos transmises à Spring Boot seront traitées en mémoire vive uniquement, puis détruites immédiatement. Seuls des scores textuels anonymisés (`rougeurs: 40%`) seront persistés — aucune photo en base.

## Pourquoi pas de Sanctum/JWT cross-service

Fortify headless + Sanctum/JWT signé n'était nécessaire que dans l'hypothèse d'un frontend Next.js séparé. Puisque la Phase 3 a été construite directement dans le monolithe Inertia (voir [09-phase3-diagnostic-inertia.md](09-phase3-diagnostic-inertia.md)), ce besoin a disparu : la session Laravel standard suffit, aucune couche d'échange de jeton à maintenir ni à sécuriser en plus.

Cette question redeviendrait pertinente uniquement si une vraie séparation frontend est un jour construite pour un autre morceau (ex. Phase 6 — dashboard analytics découplé), et non pour se justifier elle-même.
