from datetime import datetime, timezone

from database import db


DEMO_HELPER_ID = "iris-demo-helper"
DEMO_AVATARS = {
    "helper": "https://images.pexels.com/photos/31869537/pexels-photo-31869537.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=150&w=150",
    "alex": "https://images.pexels.com/photos/33605541/pexels-photo-33605541.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=150&w=150",
    "sarah": "https://images.unsplash.com/photo-1494790108377-be9c29b29330?auto=format&fit=crop&w=150&q=85",
    "marc": "https://images.unsplash.com/photo-1500648767791-00dcc994a43e?auto=format&fit=crop&w=150&q=85",
}


def message(
    message_id: str,
    content: str,
    timestamp: str,
    author_id: str,
    username: str,
    display_name: str,
    avatar: str,
) -> dict:
    return {
        "id": message_id,
        "content": content,
        "timestamp": timestamp,
        "author": {
            "id": author_id,
            "username": username,
            "display_name": display_name,
            "avatar_url": avatar,
        },
        "attachments": [],
    }


def demo_tickets() -> list[dict]:
    return [
        {
            "id": "TKT-0891",
            "demo_ticket": True,
            "title": "Problème de synchronisation API",
            "member": {
                "id": "demo-alexandre",
                "username": "alexandre.dev",
                "display_name": "Alexandre D.",
                "avatar_url": DEMO_AVATARS["alex"],
                "joined_at": "2025-03-14T10:22:00+00:00",
            },
            "channel_id": "demo-support-api",
            "channel_name": "support-api-184",
            "status": "active",
            "message_count": 4,
            "transcript": [
                message("demo-891-1", "Bonjour, mon tableau de bord ne synchronise plus les données depuis ce matin.", "2026-07-24T08:42:00+00:00", "demo-alexandre", "alexandre.dev", "Alexandre D.", DEMO_AVATARS["alex"]),
                message("demo-891-2", "Bonjour Alexandre, je regarde les journaux de synchronisation avec vous.", "2026-07-24T08:44:00+00:00", DEMO_HELPER_ID, "iris.helper", "Lina · Helper", DEMO_AVATARS["helper"]),
                message("demo-891-3", "Le jeton est bien reconnu, mais le dernier événement date d’hier soir.", "2026-07-24T08:47:00+00:00", "demo-alexandre", "alexandre.dev", "Alexandre D.", DEMO_AVATARS["alex"]),
                message("demo-891-4", "Merci, nous avons isolé le délai et l’équipe technique suit le correctif.", "2026-07-24T08:51:00+00:00", DEMO_HELPER_ID, "iris.helper", "Lina · Helper", DEMO_AVATARS["helper"]),
            ],
            "notes": "Incident reproduit sur le compte d’Alexandre. Priorité élevée : surveiller le retour du traitement asynchrone.",
            "vocal_summary": "Point vocal de 01:12 — Le décalage est apparu après la synchronisation nocturne. Alexandre a confirmé que ses identifiants n’ont pas changé. Relance planifiée avec le pôle technique.",
            "last_synced_at": "2026-07-24T08:52:00+00:00",
            "created_by": DEMO_HELPER_ID,
            "created_at": "2026-07-24T08:42:00+00:00",
            "updated_at": "2026-07-24T08:52:00+00:00",
            "is_demo": True,
        },
        {
            "id": "TKT-0890",
            "demo_ticket": True,
            "title": "Accès refusé au serveur vocal",
            "member": {"id": "demo-sarah", "username": "sarah.m", "display_name": "Sarah M.", "avatar_url": DEMO_AVATARS["sarah"], "joined_at": "2025-11-03T19:20:00+00:00"},
            "channel_id": "demo-vocal-access",
            "channel_name": "vocal-aide-023",
            "status": "active",
            "message_count": 3,
            "transcript": [
                message("demo-890-1", "Je peux rejoindre le serveur mais aucun salon vocal n’est accessible.", "2026-07-24T09:03:00+00:00", "demo-sarah", "sarah.m", "Sarah M.", DEMO_AVATARS["sarah"]),
                message("demo-890-2", "Je vérifie les rôles associés à votre compte. Avez-vous accepté les règles du serveur ?", "2026-07-24T09:05:00+00:00", DEMO_HELPER_ID, "iris.helper", "Lina · Helper", DEMO_AVATARS["helper"]),
                message("demo-890-3", "Oui, c’est fait. Le rôle n’apparaissait simplement pas après ma validation.", "2026-07-24T09:07:00+00:00", "demo-sarah", "sarah.m", "Sarah M.", DEMO_AVATARS["sarah"]),
            ],
            "notes": "Rôle Vocal Help appliqué manuellement. Demander à Sarah de se reconnecter avant de clôturer.",
            "vocal_summary": "Point vocal de 00:45 — Contrôle des permissions effectué. Le rôle d’accès vocal était absent après validation des règles. Correctif appliqué en direct.",
            "last_synced_at": "2026-07-24T09:08:00+00:00",
            "created_by": DEMO_HELPER_ID,
            "created_at": "2026-07-24T09:03:00+00:00",
            "updated_at": "2026-07-24T09:08:00+00:00",
            "is_demo": True,
        },
        {
            "id": "TKT-0888",
            "demo_ticket": True,
            "title": "Question sur la facturation premium",
            "member": {"id": "demo-marc", "username": "marc.t", "display_name": "Marc T.", "avatar_url": DEMO_AVATARS["marc"], "joined_at": "2024-08-17T12:10:00+00:00"},
            "channel_id": "demo-billing-question",
            "channel_name": "facturation-067",
            "status": "archived",
            "message_count": 3,
            "transcript": [
                message("demo-888-1", "Bonjour, puis-je recevoir une facture au nom de mon association ?", "2026-07-23T16:30:00+00:00", "demo-marc", "marc.t", "Marc T.", DEMO_AVATARS["marc"]),
                message("demo-888-2", "Oui. Je vous indique le parcours à suivre depuis les paramètres de facturation.", "2026-07-23T16:34:00+00:00", DEMO_HELPER_ID, "iris.helper", "Lina · Helper", DEMO_AVATARS["helper"]),
                message("demo-888-3", "Parfait, c’est bon pour moi. Merci pour votre aide !", "2026-07-23T16:40:00+00:00", "demo-marc", "marc.t", "Marc T.", DEMO_AVATARS["marc"]),
            ],
            "notes": "Dossier résolu. Marc a trouvé l’option de facturation professionnelle.",
            "vocal_summary": "Point vocal de 02:03 — Présentation du circuit de facturation association et vérification de l’adresse de réception. Aucune action complémentaire requise.",
            "last_synced_at": "2026-07-23T16:41:00+00:00",
            "created_by": DEMO_HELPER_ID,
            "created_at": "2026-07-23T16:30:00+00:00",
            "updated_at": "2026-07-23T16:41:00+00:00",
            "is_demo": True,
        },
    ]


async def seed_demo_tickets() -> None:
    for ticket in demo_tickets():
        await db.tickets.update_one(
            {"id": ticket["id"]},
            {"$setOnInsert": ticket},
            upsert=True,
        )


def is_demo_helper(helper_id: str, mode: str) -> bool:
    return helper_id == DEMO_HELPER_ID and mode == "demo"