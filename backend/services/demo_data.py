"""Legacy module no longer imported by Iris after demo removal."""

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
            "title": "Anxiété avant un entretien important",
            "member": {
                "id": "demo-alexandre",
                "username": "alexandre.dev",
                "display_name": "Alexandre D.",
                "avatar_url": DEMO_AVATARS["alex"],
                "joined_at": "2025-03-14T10:22:00+00:00",
            },
            "channel_id": "demo-ecoute-anxiete",
            "channel_name": "écoute-confidentielle",
            "status": "active",
            "priority": "prioritaire",
            "follow_up_status": "en suivi",
            "message_count": 4,
            "transcript": [
                message("demo-891-1", "Bonjour, je ressens beaucoup d’anxiété depuis ce matin à l’idée de mon entretien demain.", "2026-07-24T08:42:00+00:00", "demo-alexandre", "alexandre.dev", "Alexandre D.", DEMO_AVATARS["alex"]),
                message("demo-891-2", "Merci de l’avoir partagé. Nous pouvons prendre quelques minutes pour poser ce qui vous inquiète le plus.", "2026-07-24T08:44:00+00:00", DEMO_HELPER_ID, "iris.helper", "Lina · Helper", DEMO_AVATARS["helper"]),
                message("demo-891-3", "J’ai peur de perdre mes moyens et de décevoir les personnes qui comptent sur moi.", "2026-07-24T08:47:00+00:00", "demo-alexandre", "alexandre.dev", "Alexandre D.", DEMO_AVATARS["alex"]),
                message("demo-891-4", "C’est compréhensible. Nous avons identifié deux appuis concrets pour ce soir et un point de suivi après l’entretien.", "2026-07-24T08:51:00+00:00", DEMO_HELPER_ID, "iris.helper", "Lina · Helper", DEMO_AVATARS["helper"]),
            ],
            "notes": "Alexandre verbalise une anxiété anticipatoire forte. Écoute active réalisée ; proposer un retour bref après l’entretien.",
            "vocal_summary": "Échange de 01:12 — Alexandre a identifié la peur de décevoir comme déclencheur. Une respiration guidée et la préparation de deux phrases-repères ont été proposées.",
            "last_synced_at": "2026-07-24T08:52:00+00:00",
            "created_by": DEMO_HELPER_ID,
            "created_at": "2026-07-24T08:42:00+00:00",
            "updated_at": "2026-07-24T08:52:00+00:00",
            "is_demo": True,
        },
        {
            "id": "TKT-0890",
            "demo_ticket": True,
            "title": "Isolement et difficultés de sommeil",
            "member": {"id": "demo-sarah", "username": "sarah.m", "display_name": "Sarah M.", "avatar_url": DEMO_AVATARS["sarah"], "joined_at": "2025-11-03T19:20:00+00:00"},
            "channel_id": "demo-ecoute-sommeil",
            "channel_name": "écoute-confidentielle",
            "status": "active",
            "priority": "routine",
            "follow_up_status": "à écouter",
            "message_count": 3,
            "transcript": [
                message("demo-890-1", "Je dors très peu depuis quelques jours et j’ai du mal à en parler autour de moi.", "2026-07-24T09:03:00+00:00", "demo-sarah", "sarah.m", "Sarah M.", DEMO_AVATARS["sarah"]),
                message("demo-890-2", "Merci de nous l’écrire. Est-ce que vous vous sentez en sécurité pour cette nuit ?", "2026-07-24T09:05:00+00:00", DEMO_HELPER_ID, "iris.helper", "Lina · Helper", DEMO_AVATARS["helper"]),
                message("demo-890-3", "Oui, je suis en sécurité. J’aimerais simplement retrouver un rythme plus apaisé.", "2026-07-24T09:07:00+00:00", "demo-sarah", "sarah.m", "Sarah M.", DEMO_AVATARS["sarah"]),
            ],
            "notes": "Sarah indique être en sécurité. Prioriser l’écoute et un prochain point de suivi dans les 48 heures.",
            "vocal_summary": "Échange de 00:45 — Sarah parle d’isolement et d’un sommeil fragilisé. Orientation vers des repères de routine douce et proposition de recontacter l’équipe.",
            "last_synced_at": "2026-07-24T09:08:00+00:00",
            "created_by": DEMO_HELPER_ID,
            "created_at": "2026-07-24T09:03:00+00:00",
            "updated_at": "2026-07-24T09:08:00+00:00",
            "is_demo": True,
        },
        {
            "id": "TKT-0888",
            "demo_ticket": True,
            "title": "Besoin de ressources pour un proche",
            "member": {"id": "demo-marc", "username": "marc.t", "display_name": "Marc T.", "avatar_url": DEMO_AVATARS["marc"], "joined_at": "2024-08-17T12:10:00+00:00"},
            "channel_id": "demo-ressources-proche",
            "channel_name": "écoute-confidentielle",
            "status": "archived",
            "priority": "routine",
            "follow_up_status": "stable",
            "message_count": 3,
            "transcript": [
                message("demo-888-1", "Je cherche des ressources pour accompagner un proche qui traverse une période difficile.", "2026-07-23T16:30:00+00:00", "demo-marc", "marc.t", "Marc T.", DEMO_AVATARS["marc"]),
                message("demo-888-2", "Vous faites bien de chercher du soutien. Je vous partage des pistes adaptées et des contacts utiles.", "2026-07-23T16:34:00+00:00", DEMO_HELPER_ID, "iris.helper", "Lina · Helper", DEMO_AVATARS["helper"]),
                message("demo-888-3", "Merci, cela me donne une première direction et je me sens moins seul face à la situation.", "2026-07-23T16:40:00+00:00", "demo-marc", "marc.t", "Marc T.", DEMO_AVATARS["marc"]),
            ],
            "notes": "Ressources transmises. Marc indique savoir vers qui se tourner et ne sollicite pas de suivi immédiat.",
            "vocal_summary": "Échange de 02:03 — Présentation de ressources généralistes et rappel des relais adaptés. Marc se sent mieux outillé pour soutenir son proche.",
            "last_synced_at": "2026-07-23T16:41:00+00:00",
            "created_by": DEMO_HELPER_ID,
            "created_at": "2026-07-23T16:30:00+00:00",
            "updated_at": "2026-07-23T16:41:00+00:00",
            "is_demo": True,
        },
    ]


async def seed_demo_tickets() -> None:
    for ticket in demo_tickets():
        ticket["demo_schema_version"] = 2
        existing = await db.tickets.find_one(
            {"id": ticket["id"], "demo_ticket": True},
            {"_id": 0, "demo_schema_version": 1},
        )
        if not existing or existing.get("demo_schema_version") != 2:
            await db.tickets.update_one(
                {"id": ticket["id"]},
                {"$set": ticket},
                upsert=True,
            )


def is_demo_helper(helper_id: str, mode: str) -> bool:
    return helper_id == DEMO_HELPER_ID and mode == "demo"