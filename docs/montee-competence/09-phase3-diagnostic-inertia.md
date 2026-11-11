---
title: Phase 3 — Page diagnostic en Inertia
group: Montée en compétence
order: 9
---

← [Retour au sommaire](README.md)

# 9. Phase 3 — Page diagnostic en Inertia

## Pourquoi pas de pont Next.js finalement ?

Le plan initial de la Phase 3 prévoyait un pont Laravel (Sanctum, jeton signé) → Next.js (Server Component) → retour Laravel. En le concevant, la question s'est posée : **est-ce vraiment la meilleure solution pour faire communiquer Laravel et Next.js ?**

Réponse honnête : non, pas pour ce cas précis. Inertia fait déjà tourner du React moderne (composants, hooks, SSR optionnel) directement dans le monolithe Laravel — sans jeton, sans synchronisation entre deux applications séparées. Le pont Sanctum + Next.js n'aurait ajouté que de la complexité architecturale, pour zéro bénéfice produit. Sa seule justification aurait été pédagogique (pratiquer Next.js/Server Components), donc il est **repoussé** à un morceau où une vraie séparation frontend a du sens (ex. Phase 6 — dashboard analytics découplé), plutôt que d'être forcé ici.

La Phase 3 devient donc : une page diagnostic **normale**, dans le même monolithe, avec le même stack Inertia que tout le reste de la boutique.

## Ce qui a été construit

### Le flux

1. Le visiteur clique sur "Besoin d'aide pour choisir ?" (page d'accueil) → `GET /diagnostic-peau`.
2. Il choisit un type de peau parmi les 9 options de l'enum `SkinType` existant.
3. Ce choix part en `POST /diagnostic-peau` (même URL, méthode différente — même pattern que `commande/paiement` dans `CheckoutController`).
4. Le contrôleur :
   - notifie `kbeauty-ai-core-service` (le microservice Spring Boot de la Phase 2) via un `POST /diagnostics` HTTP — ça enregistre une ligne en base Neon et publie un événement RabbitMQ, exactement le pipeline construit en Phase 2 ;
   - construit une analyse **bidon** (texte hardcodé par type de peau — le vrai contenu IA arrive en Phase 5) ;
   - cherche jusqu'à 4 produits publiés qui correspondent à ce type de peau (`whereJsonContains('skin_types', ...)`, un champ qui existait déjà pour le filtre catalogue) ;
   - renvoie la même page Inertia, mais avec un `result` rempli.
5. Le visiteur clique "Ajouter au panier" → ça réutilise directement la route `storefront.cart.store` existante (`POST /panier`), le même chemin que le bouton "Ajouter au panier" de la fiche produit. Aucune logique panier dupliquée.

### Pourquoi l'appel au microservice ne bloque jamais la page

`AiCoreDiagnosticClient::createDiagnosticRequest()` est en `try/catch` avec un timeout de 2 secondes. Si `kbeauty-ai-core-service` n'est pas lancé (ce qui sera le cas la plupart du temps, puisque c'est un service pédagogique optionnel tournant sous WSL), l'appel échoue silencieusement (juste un `Log::warning`) et la page continue de fonctionner normalement. **Un module expérimental ne doit jamais pouvoir casser la boutique.**

### Fichiers créés/modifiés

- `app/Services/AiCoreDiagnosticClient.php` — le pont HTTP vers le microservice Spring Boot.
- `app/Http/Controllers/Storefront/DiagnosticController.php` — `index()` (formulaire) + `analyze()` (résultat).
- `resources/js/pages/storefront/diagnostic.tsx` — la page React/Inertia (formulaire + résultat + bouton panier).
- `routes/storefront.php` — routes `storefront.diagnostic.index`/`.analyze`, en français ET dans le miroir `/en` (throttle `3,60` uniquement sur le `POST`, pas sur l'affichage du formulaire).
- `resources/js/components/language-switcher.tsx` — ajout de `diagnostic-peau` au pattern des chemins traduits (sinon le sélecteur FR/EN serait tombé sur `/produits` par défaut).
- `resources/js/pages/storefront/home.tsx` — le CTA "Besoin d'aide pour choisir ?" pointe maintenant vers `/diagnostic-peau` plutôt que `/guide-de-choix` (la page guide reste accessible, juste plus mise en avant sur l'accueil).
- `config/services.php` / `.env.example` — `AI_CORE_SERVICE_URL` (défaut `http://localhost:8080`).

## Comment tester toi-même

1. Assure-toi que `composer run dev` tourne (Laravel).
2. Optionnel : lance aussi `kbeauty-ai-core-service` (`mvn spring-boot:run` sous WSL) + RabbitMQ pour voir le pipeline Phase 2 se déclencher réellement. Sans ça, la page fonctionne quand même (juste un warning dans les logs Laravel).
3. Va sur `http://localhost:8000/diagnostic-peau`, choisis un type de peau, vérifie que :
   - une analyse texte s'affiche ;
   - un produit recommandé apparaît (si un produit publié a ce `skin_type` en base) ;
   - "Ajouter au panier" fonctionne et redirige bien vers un panier peuplé.
4. Si `kbeauty-ai-core-service` tourne, regarde ses logs : tu devrais voir la ligne insérée en base Neon et le message consommé par le `@RabbitListener` (comme en Phase 2).

## Prochaine étape

Phase 0 (BPMN/UML — toujours en attente) ou Phase 4 (Scrapy/Cassandra), à ton choix.
