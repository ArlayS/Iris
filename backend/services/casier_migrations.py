"""Mise à niveau des casiers écrits avant la refonte.

- `ensure_item_ids` : migration paresseuse (détail d'un casier, avant une écriture ciblant une
  sanction ou une fiche S) qui attribue un id aux éléments qui n'en ont pas ;
- `migrate_casiers` : passage complet au démarrage (ids, `content_text` des fiches S, copies de
  fichiers interrompues).

Tout est idempotent : chaque écriture est gardée par index (les sanctions et fiches ne sont jamais
retirées des tableaux) et ne touche que les éléments encore incomplets. Aucune autre réécriture :
ni statut, ni type, ni `updated_at`.
"""
import logging
from datetime import datetime, timedelta, timezone

from bson import ObjectId

from database import db

logger = logging.getLogger(__name__)

# Couvre la clé absente, `null` et la chaîne vide ({"$exists": False} ne verrait pas `id: null`).
MISSING_ID = {"$in": [None, ""]}
ITEM_ARRAYS = ("sanctions", "fiches_s")
PENDING_STALE_AFTER = timedelta(minutes=15)
INTERRUPTED_COPY_ERROR = "Copie interrompue (redémarrage d'Iris). Utilisez « Récupérer les fichiers du log »."
FICHE_TEXT_MAX_LENGTH = 20_000
# Les versions précédentes des fiches S ne servent pas à la migration.
MIGRATION_PROJECTION = {"fiches_s.revisions": 0}


def _new_id() -> str:
    return str(ObjectId())


def _items(casier: dict, field: str) -> list:
    items = casier.get(field)
    return items if isinstance(items, list) else []


def has_missing_ids(casier: dict | None) -> bool:
    """Vrai si une sanction ou une fiche S n'a pas d'id (clé absente, `None` ou `""`)."""
    if not casier:
        return False
    return any(
        isinstance(item, dict) and not item.get("id")
        for field in ITEM_ARRAYS
        for item in _items(casier, field)
    )


async def _assign_missing_ids(casier: dict) -> int:
    assigned = 0
    for field in ITEM_ARRAYS:
        for index, item in enumerate(_items(casier, field)):
            if not isinstance(item, dict) or item.get("id"):
                continue
            # La date garde l'identité de l'élément ; si un autre worker a gagné, rien n'est écrit.
            result = await db.casiers.update_one(
                {
                    "_id": casier["_id"],
                    f"{field}.{index}.id": MISSING_ID,
                    f"{field}.{index}.created_at": item.get("created_at"),
                },
                {"$set": {f"{field}.{index}.id": _new_id()}},
            )
            assigned += result.modified_count
    return assigned


async def ensure_item_ids(casier: dict, *, projection: dict | None = None) -> dict:
    """Attribue un id aux sanctions et fiches S qui n'en ont pas, puis renvoie le document relu.

    Sans élément à compléter, renvoie `casier` tel quel (aucune requête). `casier` doit contenir le
    `created_at` des éléments (garde d'identité). `projection` sert à la relecture (ex. la liste,
    qui n'a pas besoin du contenu des fiches).
    """
    if not casier or "_id" not in casier or not has_missing_ids(casier):
        return casier
    await _assign_missing_ids(casier)
    refreshed = await db.casiers.find_one({"_id": casier["_id"]}, projection)
    return refreshed or casier


def _load_text_extractor():
    from services import casier_text  # import local : chargé seulement au moment de la migration

    return casier_text.content_to_text


async def _fill_content_text(casier: dict, content_to_text) -> int:
    filled = 0
    for index, fiche in enumerate(_items(casier, "fiches_s")):
        if not isinstance(fiche, dict) or not fiche.get("id") or fiche.get("content_text") is not None:
            continue
        content = fiche.get("content")
        text = content_to_text(content if isinstance(content, str) else "") or ""
        # Garde `content_text: None` : une modification concurrente (qui l'écrit) n'est pas écrasée.
        result = await db.casiers.update_one(
            {
                "_id": casier["_id"],
                f"fiches_s.{index}.id": fiche["id"],
                f"fiches_s.{index}.content_text": None,
            },
            {"$set": {f"fiches_s.{index}.content_text": str(text)[:FICHE_TEXT_MAX_LENGTH]}},
        )
        filled += result.modified_count
    return filled


def _parse_datetime(value) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


async def _fail_stale_pending(casier: dict, now: datetime) -> int:
    """Copies `pending` de plus de 15 minutes : aucune tâche ne survit à un redémarrage."""
    failed = 0
    for index, sanction in enumerate(_items(casier, "sanctions")):
        if not isinstance(sanction, dict) or not sanction.get("id"):
            continue
        for position, attachment in enumerate(_items(sanction, "attachments")):
            if not isinstance(attachment, dict) or attachment.get("status") != "pending":
                continue
            created = _parse_datetime(attachment.get("created_at"))
            if created is not None and now - created < PENDING_STALE_AFTER:
                continue
            prefix = f"sanctions.{index}.attachments.{position}"
            guard = {
                "_id": casier["_id"],
                f"sanctions.{index}.id": sanction["id"],
                f"{prefix}.status": "pending",
            }
            if attachment.get("id"):
                guard[f"{prefix}.id"] = attachment["id"]
            result = await db.casiers.update_one(
                guard,
                {"$set": {f"{prefix}.status": "failed", f"{prefix}.error": INTERRUPTED_COPY_ERROR}},
            )
            failed += result.modified_count
    return failed


async def migrate_casiers(*, now: datetime | None = None) -> dict:
    """Passe sur tous les casiers (idempotent). Un casier illisible est journalisé puis ignoré."""
    now = now or datetime.now(timezone.utc)
    stats = {"casiers": 0, "ids": 0, "content_text": 0, "attachments_failed": 0, "errors": 0}

    try:
        content_to_text = _load_text_extractor()
    except Exception:
        # Le texte des fiches reste calculé à la volée par les lecteurs.
        logger.exception("Extraction du texte des fiches S indisponible : content_text non migré")
        content_to_text = None

    async for casier in db.casiers.find({}, MIGRATION_PROJECTION):
        stats["casiers"] += 1
        try:
            if has_missing_ids(casier):
                stats["ids"] += await _assign_missing_ids(casier)
                casier = await db.casiers.find_one({"_id": casier["_id"]}, MIGRATION_PROJECTION) or casier
            if content_to_text is not None:
                stats["content_text"] += await _fill_content_text(casier, content_to_text)
            stats["attachments_failed"] += await _fail_stale_pending(casier, now)
        except Exception:
            stats["errors"] += 1
            logger.exception("Migration impossible pour le casier %s", casier.get("_id"))

    logger.info(
        "Migration des casiers : %d casier(s) parcouru(s), %d identifiant(s) attribué(s), "
        "%d texte(s) de fiche S calculé(s), %d copie(s) interrompue(s), %d erreur(s).",
        stats["casiers"], stats["ids"], stats["content_text"], stats["attachments_failed"], stats["errors"],
    )
    return stats
