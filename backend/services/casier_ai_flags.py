"""Signalements de la modération IA (collection `ai_moderation_flags`).

Seules les alertes sont conservées (violations, refus du modèle, réponses illisibles), jamais les messages jugés
OK ni ceux des salons de tickets/écoute. L'enregistrement ne lève jamais : le worker IA ne doit pas dépendre de
Mongo. Les réglages (`config.*`) sont lus à l'appel pour rester remplaçables dans les tests.
"""
import logging
import re
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone

from bson import ObjectId
from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

import config
from database import db

logger = logging.getLogger(__name__)

KINDS = ("violation", "refus", "illisible")
REVIEW_STATUSES = ("a_traiter", "pertinent", "faux_positif")
MODES = ("log", "act")
PLANNED_ACTIONS = ("delete", "timeout", "alert")

MESSAGE_CONTENT_MAX = 4000
VERDICT_TEXT_MAX = 200
CATEGORY_MAX = 40
COMMENT_MAX = 500
NAME_MAX = 100
EXECUTED_MAX_ITEMS = 10
DEFAULT_LIMIT = 30
MAX_LIMIT = 100
MAX_SKIP = 10_000

FLAG_ID_PATTERN = re.compile(r"[0-9a-f]{24}")
_SNOWFLAKE = re.compile(r"[0-9]{15,22}")
_DISCORD_ID = re.compile(r"[0-9]{17,20}")
_DISCORD_URL = re.compile(r"https://(?:(?:ptb|canary)\.)?discord(?:app)?\.com/\S{1,280}")
_HTTPS_URL = re.compile(r"https://\S{1,500}")

# Valeur par défaut de `comment` dans `review_flag` : commentaire laissé tel quel.
UNCHANGED = object()


# --------------------------------------------------------------------------- utilitaires


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _get(obj, key: str):
    """Lecture tolérante : dict, objet (dataclass, SimpleNamespace) ou None."""
    if obj is None:
        return None
    if isinstance(obj, Mapping):
        return obj.get(key)
    return getattr(obj, key, None)


def _text(value, limit: int, *, strip: bool = True) -> str | None:
    if value is None:
        return None
    text = str(value)
    if strip:
        text = text.strip()
    return text[:limit] or None


def _snowflake(value) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text if _SNOWFLAKE.fullmatch(text) else None


def _url(value, pattern: re.Pattern) -> str | None:
    """Garde seulement une URL sûre (jamais de `javascript:` dans un lien affiché par le frontend)."""
    text = str(value).strip() if value is not None else ""
    return text if pattern.fullmatch(text) else None


def _iso(value) -> str | None:
    """Datetime → ISO avec fuseau (naïf = UTC, comme relu de Mongo) ; chaîne gardée telle quelle."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    if isinstance(value, str) and value:
        return value[:40]
    return None


def _author_dict(author) -> dict | None:
    if author is None:
        return None
    return {
        "id": _text(_get(author, "id"), 32),
        "username": _text(_get(author, "username"), NAME_MAX),
        "display_name": _text(_get(author, "display_name"), NAME_MAX),
    }


def flag_id_or_400(value) -> str:
    if not isinstance(value, str) or not FLAG_ID_PATTERN.fullmatch(value):
        raise HTTPException(status_code=400, detail="Identifiant invalide.")
    return value


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="Signalement introuvable.")


def _review_status(doc: dict | None) -> str:
    """Statut de revue d'un document (absent = « À traiter »)."""
    return _get(_get(doc, "review"), "status") or "a_traiter"


# --------------------------------------------------------------------------- enregistrement


def is_excluded_location(channel_id, parent_id, category_id) -> bool:
    """Vrai si le salon, son parent ou sa catégorie est un ticket/salon d'écoute (jamais enregistré)."""
    excluded = {str(item) for item in getattr(config, "ALLOWED_TICKET_CATEGORY_IDS", ()) or ()}
    excluded |= {str(item) for item in getattr(config, "AI_MODERATION_FLAG_SKIP_IDS", ()) or ()}
    location = {str(item).strip() for item in (channel_id, parent_id, category_id) if item is not None}
    location.discard("")
    return bool(excluded & location)


def _clean_verdict(verdict) -> dict | None:
    if verdict is None:
        return None
    try:
        gravite = max(0, min(3, int(_get(verdict, "gravite") or 0)))
    except (TypeError, ValueError):
        gravite = 0
    try:
        confiance = max(0.0, min(1.0, float(_get(verdict, "confiance") or 0.0)))
    except (TypeError, ValueError):
        confiance = 0.0
    return {
        "violation": bool(_get(verdict, "violation")),
        "categorie": _text(_get(verdict, "categorie"), CATEGORY_MAX),
        "gravite": gravite,
        "confiance": confiance,
        "raison": _text(_get(verdict, "raison"), VERDICT_TEXT_MAX) or "",
        "sanction": _text(_get(verdict, "sanction"), VERDICT_TEXT_MAX) or "",
    }


def _build_document(payload) -> dict | None:
    """Document prêt à insérer, ou None s'il ne doit pas être enregistré."""
    channel = _get(payload, "channel")
    channel_id = _get(channel, "id")
    parent_id = _get(channel, "parent_id")
    category_id = _get(channel, "category_id")
    if is_excluded_location(channel_id, parent_id, category_id):
        logger.debug("Signalement IA non enregistré : salon de ticket ou d'écoute (%s).", channel_id)
        return None

    kind = _get(payload, "kind")
    if kind not in KINDS:
        logger.warning("Signalement IA ignoré : type inconnu %r.", kind)
        return None

    author = _get(payload, "author")
    discord_id = _text(_get(payload, "discord_id") or _get(author, "id"), 32)
    message = _get(payload, "message")
    message_id = _snowflake(_get(message, "id"))
    if not discord_id or not _DISCORD_ID.fullmatch(discord_id) or not message_id:
        logger.warning("Signalement IA ignoré : auteur ou message sans identifiant valide.")
        return None

    verdict = _clean_verdict(_get(payload, "verdict")) if kind == "violation" else None
    if kind == "violation" and (verdict is None or not verdict["violation"] or verdict["gravite"] < 1):
        # Jamais les messages jugés OK : seules les alertes sont conservées.
        return None

    content = _text(_get(message, "content"), MESSAGE_CONTENT_MAX, strip=False)
    redacted = False
    if kind == "refus" and not getattr(config, "AI_MODERATION_FLAG_STORE_REFUSAL_CONTENT", False):
        content, redacted = None, True

    mode = _get(payload, "mode")
    mode = mode if mode in MODES else "log"
    planned = _get(payload, "planned_action")
    raw_executed = _get(payload, "executed")
    executed = []
    if mode == "act" and isinstance(raw_executed, (list, tuple)):
        executed = [text for text in (_text(item, VERDICT_TEXT_MAX) for item in raw_executed) if text]
        executed = executed[:EXECUTED_MAX_ITEMS]
    alert = _get(payload, "alert")
    created_at = _get(payload, "created_at")

    return {
        "id": str(ObjectId()),
        "created_at": created_at if isinstance(created_at, datetime) else _now(),
        "discord_id": discord_id,
        "author": {
            "id": discord_id,
            "username": _text(_get(author, "username"), NAME_MAX),
            "display_name": _text(_get(author, "display_name"), NAME_MAX),
            "avatar_url": _url(_get(author, "avatar_url"), _HTTPS_URL),
        },
        "guild_id": _snowflake(_get(payload, "guild_id")),
        "channel": {
            "id": _snowflake(channel_id),
            "name": _text(_get(channel, "name"), NAME_MAX),
            "parent_id": _snowflake(parent_id),
            "category_id": _snowflake(category_id),
        },
        "message": {
            "id": message_id,
            "content": content,
            "content_redacted": redacted,
            "created_at": _iso(_get(message, "created_at")),
            "jump_url": _url(_get(message, "jump_url"), _DISCORD_URL),
        },
        "kind": kind,
        "verdict": verdict,
        "mode": mode,
        "planned_action": planned if planned in PLANNED_ACTIONS else None,
        "executed": executed,
        "alert": {
            "posted": bool(_get(alert, "posted")),
            "channel_id": _snowflake(_get(alert, "channel_id")),
            "message_id": _snowflake(_get(alert, "message_id")),
            "jump_url": _url(_get(alert, "jump_url"), _DISCORD_URL),
            "pinged": bool(_get(alert, "pinged")),
        },
        "model": _text(_get(payload, "model"), NAME_MAX),
        "review": {"status": "a_traiter", "comment": None, "reviewed_at": None, "reviewed_by": None},
        "sanction": None,
    }


async def _existing_flag_id(message_id: str) -> str | None:
    existing = await db.ai_moderation_flags.find_one({"message.id": message_id}, {"_id": 0, "id": 1})
    return (existing or {}).get("id")


async def record_ai_flag(payload: dict) -> str | None:
    """Enregistre un signalement (dédupliqué sur `message.id`) et renvoie son id, ou None.

    Ne lève jamais : toute erreur est journalisée (le worker IA continue même si Mongo est indisponible).
    """
    try:
        document = _build_document(payload)
        if document is None:
            return None
        message_id = document["message"]["id"]
        try:
            result = await db.ai_moderation_flags.update_one(
                {"message.id": message_id}, {"$setOnInsert": document}, upsert=True
            )
        except DuplicateKeyError:
            # Deux enregistrements simultanés du même message : l'autre a gagné.
            return await _existing_flag_id(message_id)
        if result.upserted_id is not None:
            return document["id"]
        return await _existing_flag_id(message_id)
    except Exception:
        logger.exception("Signalement IA non enregistré (message %s).", _get(_get(payload, "message"), "id"))
        return None


# --------------------------------------------------------------------------- lecture


def build_query(filters: Mapping | None, *, include_review_status: bool = True) -> dict:
    """Filtre Mongo de la liste (`filters` déjà validés par le router ; valeurs vides = pas de filtre).

    Clés reconnues : discord_id, q, review_status, min_gravity, category, kind.
    """
    filters = filters or {}
    clauses: list[dict] = []

    discord_id = filters.get("discord_id")
    if discord_id:
        clauses.append({"discord_id": str(discord_id)})

    kind = filters.get("kind")
    if kind:
        clauses.append({"kind": str(kind)})

    category = filters.get("category")
    if category:
        clauses.append({"verdict.categorie": str(category)})

    min_gravity = filters.get("min_gravity")
    if min_gravity is not None:
        # Les refus et réponses illisibles (verdict null) sont exclus d'office.
        clauses.append({"verdict.gravite": {"$gte": int(min_gravity)}})

    review_status = filters.get("review_status")
    if include_review_status and review_status and review_status != "tous":
        if review_status == "a_traiter":
            clauses.append({"review.status": {"$in": ["a_traiter", None]}})
        else:
            clauses.append({"review.status": str(review_status)})

    q = str(filters.get("q") or "").strip()[:100]
    if q:
        from services import casier_text  # import local : module partagé du lot casier

        regex = {"$regex": casier_text.accent_insensitive_regex(q), "$options": "i"}
        fields = ("author.display_name", "author.username", "discord_id", "message.content", "verdict.raison")
        clauses.append({"$or": [{field: regex} for field in fields]})

    if not clauses:
        return {}
    return clauses[0] if len(clauses) == 1 else {"$and": clauses}


async def get_flag(flag_id) -> dict | None:
    """Document brut (sans `_id`), ou None si absent ou identifiant mal formé."""
    if not isinstance(flag_id, str) or not FLAG_ID_PATTERN.fullmatch(flag_id):
        return None
    return await db.ai_moderation_flags.find_one({"id": flag_id}, {"_id": 0})


async def list_flags(
    filters: Mapping | None, skip: int = 0, limit: int = DEFAULT_LIMIT
) -> tuple[int, list[dict]]:
    """(total filtré, page de documents bruts), tri `created_at` décroissant."""
    query = build_query(filters)
    skip = max(0, min(MAX_SKIP, int(skip or 0)))
    limit = max(1, min(MAX_LIMIT, int(limit or DEFAULT_LIMIT)))
    total = await db.ai_moderation_flags.count_documents(query)
    cursor = (
        db.ai_moderation_flags.find(query, {"_id": 0})
        .sort([("created_at", -1), ("_id", -1)])
        .skip(skip)
        .limit(limit)
    )
    return total, await cursor.to_list(length=limit)


async def counts_for(filters: Mapping | None) -> dict:
    """Nombre de signalements par revue, avec les mêmes filtres sauf `review_status`."""
    query = build_query(filters, include_review_status=False)
    pipeline = [
        {"$match": query},
        {"$group": {"_id": {"$ifNull": ["$review.status", "a_traiter"]}, "n": {"$sum": 1}}},
    ]
    counts = {status: 0 for status in REVIEW_STATUSES}
    total = 0
    async for row in db.ai_moderation_flags.aggregate(pipeline):
        total += row["n"]
        if row["_id"] in counts:
            counts[row["_id"]] += row["n"]
    counts["total"] = total
    return counts


async def counts_by_discord_ids(ids: Iterable[str] | None) -> dict[str, dict]:
    """{discord_id: {"total", "open"}} en une agrégation ; `ids=None` : tous les membres."""
    pipeline: list[dict] = []
    if ids is not None:
        wanted = sorted({str(item) for item in ids if item})
        if not wanted:
            return {}
        pipeline.append({"$match": {"discord_id": {"$in": wanted}}})
    is_open = {"$eq": [{"$ifNull": ["$review.status", "a_traiter"]}, "a_traiter"]}
    pipeline.append({
        "$group": {
            "_id": "$discord_id",
            "total": {"$sum": 1},
            "open": {"$sum": {"$cond": [is_open, 1, 0]}},
        }
    })
    result: dict[str, dict] = {}
    async for row in db.ai_moderation_flags.aggregate(pipeline):
        if row["_id"]:
            result[str(row["_id"])] = {"total": row["total"], "open": row["open"]}
    return result


async def casier_index_for(discord_ids: Iterable[str]) -> dict[str, dict]:
    """{discord_id: {"casier_id", "casier_status"}} pour `to_out` (doublons historiques : le plus ancien)."""
    from services import casier_service  # import local : évite un cycle avec le service des casiers

    wanted = sorted({str(item) for item in discord_ids if item})
    if not wanted:
        return {}
    cursor = db.casiers.find(
        {"discord_id": {"$in": wanted}},
        {"discord_id": 1, "sanctions.type": 1, "fiches_s.active": 1},
    ).sort("_id", 1)
    index: dict[str, dict] = {}
    async for casier in cursor:
        discord_id = casier.get("discord_id")
        if discord_id in index:
            continue
        index[discord_id] = {
            "casier_id": str(casier["_id"]),
            "casier_status": casier_service.compute_status(casier),
        }
    return index


def to_out(doc: dict, casier_index: Mapping | None = None) -> dict:
    """Format de réponse (section 3.5) : champs internes retirés, valeurs absentes remplacées par défaut."""
    discord_id = str(doc.get("discord_id") or "")
    author = doc.get("author") or {}
    channel = doc.get("channel") or {}
    message = doc.get("message") or {}
    alert = doc.get("alert") or {}
    review = doc.get("review") or {}
    verdict = doc.get("verdict")
    link = doc.get("sanction")
    casier = (casier_index or {}).get(discord_id) or {}

    return {
        "id": doc.get("id"),
        "created_at": _iso(doc.get("created_at")),
        "discord_id": discord_id,
        "author": {
            "id": author.get("id") or discord_id or None,
            "username": author.get("username"),
            "display_name": author.get("display_name"),
            "avatar_url": author.get("avatar_url"),
        },
        "channel": {"id": channel.get("id"), "name": channel.get("name")},
        "message": {
            "id": message.get("id"),
            "content": message.get("content"),
            "content_redacted": bool(message.get("content_redacted")),
            "created_at": _iso(message.get("created_at")),
            "jump_url": message.get("jump_url"),
        },
        "kind": doc.get("kind") or "violation",
        "verdict": (
            {
                "violation": bool(verdict.get("violation")),
                "categorie": verdict.get("categorie"),
                "gravite": verdict.get("gravite"),
                "confiance": verdict.get("confiance"),
                "raison": verdict.get("raison"),
                "sanction": verdict.get("sanction"),
            }
            if isinstance(verdict, Mapping)
            else None
        ),
        "mode": doc.get("mode") or "log",
        "planned_action": doc.get("planned_action"),
        "executed": [str(item) for item in doc.get("executed") or []],
        "alert": {
            "posted": bool(alert.get("posted")),
            "jump_url": alert.get("jump_url"),
            "pinged": bool(alert.get("pinged")),
        },
        "model": doc.get("model"),
        "review": {
            "status": review.get("status") or "a_traiter",
            "comment": review.get("comment"),
            "reviewed_at": _iso(review.get("reviewed_at")),
            "reviewed_by": _author_dict(review.get("reviewed_by")),
        },
        "sanction": (
            {"casier_id": str(link.get("casier_id")), "sanction_id": str(link.get("sanction_id"))}
            if isinstance(link, Mapping) and link.get("casier_id") and link.get("sanction_id")
            else None
        ),
        "casier_id": casier.get("casier_id"),
        "casier_status": casier.get("casier_status"),
    }


async def flag_out(doc: dict) -> dict:
    """`to_out` avec le casier du membre (une requête)."""
    return to_out(doc, await casier_index_for([doc.get("discord_id")]))


async def get_flag_out(flag_id) -> dict:
    """Un signalement au format de réponse ; 400 si l'id est mal formé, 404 s'il est absent ou expiré."""
    doc = await get_flag(flag_id_or_400(flag_id))
    if doc is None:
        raise _not_found()
    return await flag_out(doc)


async def build_list_response(filters: Mapping | None, skip: int = 0, limit: int = DEFAULT_LIMIT) -> dict:
    """Réponse complète de `GET /ai-flags` : {"total", "counts", "items"}."""
    total, docs = await list_flags(filters, skip, limit)
    counts = await counts_for(filters)
    index = await casier_index_for(doc.get("discord_id") for doc in docs)
    return {"total": total, "counts": counts, "items": [to_out(doc, index) for doc in docs]}


# --------------------------------------------------------------------------- revue et lien avec une sanction


async def review_flag(flag_id, status: str, comment=UNCHANGED, reviewer=None) -> tuple[dict, str]:
    """Change la revue d'un signalement ; renvoie (document mis à jour, statut de revue précédent).

    `comment` : texte (≤ 500, vide = effacé), None l'efface, `UNCHANGED` le garde.
    Retour à « À traiter » : `reviewed_at`/`reviewed_by` remis à null.
    """
    flag_id = flag_id_or_400(flag_id)
    if status not in REVIEW_STATUSES:
        raise HTTPException(status_code=422, detail="Statut de revue invalide.")
    doc = await get_flag(flag_id)
    if doc is None:
        raise _not_found()
    linked_error = HTTPException(
        status_code=409,
        detail="Ce signalement est lié à une sanction : il ne peut pas être classé faux positif.",
    )
    if status == "faux_positif" and doc.get("sanction"):
        raise linked_error

    updates: dict = {"review.status": status}
    if status == "a_traiter":
        updates["review.reviewed_at"] = None
        updates["review.reviewed_by"] = None
    else:
        updates["review.reviewed_at"] = _now().isoformat()
        updates["review.reviewed_by"] = _author_dict(reviewer)
    if comment is not UNCHANGED:
        updates["review.comment"] = _text(comment, COMMENT_MAX)

    guard = {"id": flag_id}
    if status == "faux_positif":
        guard["sanction"] = None  # lié entre-temps par une autre requête : refusé
    result = await db.ai_moderation_flags.update_one(guard, {"$set": updates})
    if result.matched_count == 0:
        current = await get_flag(flag_id)
        if current is None:
            raise _not_found()
        raise linked_error
    updated = await get_flag(flag_id)
    if updated is None:
        raise _not_found()
    return updated, _review_status(doc)


async def check_linkable(flag_id, discord_id: str) -> dict:
    """Vérifie, avant toute écriture, qu'une sanction peut être créée depuis ce signalement ; renvoie le document."""
    doc = await get_flag(flag_id_or_400(flag_id))
    if doc is None:
        raise _not_found()
    if str(doc.get("discord_id") or "") != str(discord_id or ""):
        raise HTTPException(status_code=422, detail="Ce signalement ne concerne pas ce membre.")
    if doc.get("sanction"):
        raise HTTPException(status_code=409, detail="Ce signalement est déjà lié à une sanction.")
    if _review_status(doc) == "faux_positif":
        raise HTTPException(
            status_code=409,
            detail="Ce signalement a été classé « Faux positif ». Changez sa revue avant de sanctionner.",
        )
    return doc


async def link_sanction(flag_id: str, casier_id: str, sanction_id: str, reviewer=None) -> dict | None:
    """Lie le signalement à la sanction créée, gardé par `sanction: None`.

    « À traiter » passe à « Pertinent » (`reviewed_by` = auteur de la sanction) ; « Pertinent » est gardé.
    Renvoie {"review_before", "review_after", "review_changed"} si le lien est posé, sinon None (lié ou
    classé faux positif entre-temps : avertissement journalisé, la sanction garde son `ai_flag_id`).
    """
    link = {"casier_id": str(casier_id), "sanction_id": str(sanction_id)}
    result = await db.ai_moderation_flags.update_one(
        {"id": flag_id, "sanction": None, "review.status": {"$in": ["a_traiter", None]}},
        {"$set": {
            "sanction": link,
            "review.status": "pertinent",
            "review.reviewed_at": _now().isoformat(),
            "review.reviewed_by": _author_dict(reviewer),
        }},
    )
    if result.matched_count:
        return {"review_before": "a_traiter", "review_after": "pertinent", "review_changed": True}
    result = await db.ai_moderation_flags.update_one(
        {"id": flag_id, "sanction": None, "review.status": "pertinent"},
        {"$set": {"sanction": link}},
    )
    if result.matched_count:
        return {"review_before": "pertinent", "review_after": "pertinent", "review_changed": False}
    logger.warning(
        "Signalement IA %s non lié à la sanction %s (casier %s) : déjà lié ou classé faux positif entre-temps.",
        flag_id, sanction_id, casier_id,
    )
    return None
