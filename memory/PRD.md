# Iris — Product Requirements Document

## Énoncé initial
Créer Iris, un outil interne de gestion pour les helpers d’un serveur Discord : création de profils par ID Discord, import de l’historique complet d’un salon-ticket avec pagination, et espace de traitement avec transcription, note interne et compte-rendu vocal.

## Décisions d’architecture
- Frontend React avec routes dashboard, création de ticket et espace de travail par ticket.
- API FastAPI modulaire, MongoDB via Motor et schémas Pydantic.
- API REST Discord v10 utilisée côté serveur uniquement : accès membre ciblé par guild, contrôle du salon puis pagination de l’historique par pages de 100 messages.
- Authentification Discord OAuth2 avec cookies de session HTTP-only, signés HMAC et limitation aux membres du serveur configuré.
- Toutes les informations sensibles restent dans les variables d’environnement du backend et ne sont jamais exposées au navigateur.

## Utilisateurs
- Helper : importe un ticket, lit la transcription, rédige une note interne et un résumé vocal, synchronise et archive le dossier.
- Responsable helpers : consulte les tickets actifs, les archives et les volumes de messages.

## Exigences principales
- Limiter Discord au serveur 1081957992188088391.
- Enregistrer une copie locale des transcriptions et permettre une synchronisation manuelle.
- Vérifier le membre et le salon Discord avant création d’un dossier.
- Conserver les notes et synthèses vocales dans MongoDB.
- Prévoir une connexion via compte Discord.

## Implémenté — 2026-07-24
- Interface Iris complète et responsive : écran de connexion, tableau de bord, liste de tickets, création de dossier et espace à trois colonnes.
- Modèles MongoDB/Pydantic pour tickets, membres, messages, pièces jointes, notes et compte-rendu vocal.
- Endpoints de ticket : création, liste, statistiques, détail, modification, archivage et synchronisation.
- Service Discord : recherche de membre, vérification du serveur/salon et historique paginé de manière exhaustive.
- OAuth2 Discord prêt à être activé, session sécurisée et garde d’accès sur toutes les routes métier.
- Tests : 18/18 vérifications API réussies et rendu desktop/mobile validé.

## Extension démo premium — 2026-07-24
- Refonte « Performance Pro » : file de tickets tactique, dashboard immersif, panneau d’intelligence vocale et rendu mobile adapté.
- Mode démo local explicite : session helper fictive séparée du flux OAuth Discord réel, sans appel à Discord.
- Trois dossiers de démonstration réalistes préchargés : historique de discussion, note interne, synthèse vocale, archivage et synchronisation locale.
- Correction validée par contrôle indépendant : les réponses helper de la transcription s’affichent désormais à largeur normale sur desktop ; aucun débordement mobile détecté.

## Backlog priorisé
### P0 — configuration nécessaire
- Ajouter un nouveau `DISCORD_BOT_TOKEN` après réinitialisation.
- Ajouter `DISCORD_CLIENT_ID`, `DISCORD_CLIENT_SECRET` et une valeur aléatoire robuste pour `APP_SESSION_SECRET`.
- Renseigner l’URL de retour OAuth2 dans le portail Discord : `https://iris-logs.preview.emergentagent.com/api/auth/discord/callback`.

### P1
- Tester en direct le parcours OAuth et l’import/synchronisation Discord avec les identifiants configurés.
- Ajouter une liste explicite de rôles Discord autorisés à accéder à Iris.
- Remplacer ou compléter le mode démo par des scénarios de formation supplémentaires pour les helpers.

### P2
- Ajouter recherche plein texte, filtres avancés, export de dossier et journal d’activité.

## Prochaines tâches
1. Configurer les quatre secrets Discord/session côté backend.
2. Réaliser le premier import réel d’un ticket et vérifier les permissions du bot.
3. Définir la politique d’autorisation des helpers par rôle Discord.
