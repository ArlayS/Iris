"""Super recherche de la liste des casiers : termes, correspondances surlignées, filtres et tris.

Recherche en Python sur les documents déjà chargés par le router (quelques milliers de casiers au
plus), insensible à la casse et aux accents (`casier_text.fold`). Aucun accès à la base ni au réseau.
Portées : `membre` (nom affiché, pseudo, ID Discord), `staff` (auteur Iris et modérateur réel des
sanctions), `contenu` (motifs, informations complémentaires, fiches S, noms de fichiers), `tout`.
"""
from datetime import datetime, timezone

from fastapi import HTTPException

from services import casier_service, casier_text

MAX_TERMS = 5
MAX_MATCHES = 5
STATUS_FILTER_ECHO_LENGTH = 40

SCOPES = ("tout", "membre", "staff", "contenu")
SORTS = ("recent", "gravite", "nom")

_SCOPE_PARTS = {
    "tout": frozenset({"membre", "staff", "contenu"}),
    "membre": frozenset({"membre"}),
    "staff": frozenset({"staff"}),
    "contenu": frozenset({"contenu"}),
}
_MEMBER_FIELDS = ("display_name", "username", "discord_id")
_PERSON_KEYS = ("display_name", "username", "id")
_PERSON_SEPARATOR = " · "


# --- Termes et filtres ------------------------------------------------------------------------


def parse_terms(q) -> list[str]:
    """Termes pliés de la requête (découpée sur les espaces, doublons retirés) ; 422 au-delà de 5 mots."""
    text = q.strip() if isinstance(q, str) else ""
    if not text:
        return []
    words = text.split()
    if len(words) > MAX_TERMS:
        raise HTTPException(status_code=422, detail="5 mots maximum.")
    terms: list[str] = []
    for word in words:
        folded = casier_text.fold(word)
        if folded and folded not in terms:
            terms.append(folded)
    return terms


def parse_status_filter(raw) -> frozenset[str] | None:
    """`"banni,mute"` → {"banni", "mute"} ; vide = pas de filtre ; valeur inconnue → 422."""
    if not isinstance(raw, str):
        return None
    values = [value.strip() for value in raw.split(",") if value.strip()]
    if not values:
        return None
    known = set(casier_service.STATUS_ORDER)
    for value in values:
        if value not in known:
            raise HTTPException(
                status_code=422,
                detail=f"Statut inconnu : {value[:STATUS_FILTER_ECHO_LENGTH]}.",
            )
    return frozenset(values)


# --- Correspondances --------------------------------------------------------------------------


def _items(container, key: str) -> list[dict]:
    value = container.get(key) if isinstance(container, dict) else None
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _clean(value) -> str:
    return value.strip() if isinstance(value, str) else ""


def _author(person) -> dict | None:
    if not isinstance(person, dict):
        return None
    return {key: person.get(key) for key in ("id", "username", "display_name")}


def _person_parts(person) -> list[str]:
    """Nom affiché, pseudo et id d'un auteur, sans doublon (après pliage)."""
    if not isinstance(person, dict):
        return []
    parts: list[str] = []
    seen: set[str] = set()
    for key in _PERSON_KEYS:
        text = _clean(person.get(key))
        folded = casier_text.fold(text)
        if folded and folded not in seen:
            parts.append(text)
            seen.add(folded)
    return parts


def _member_candidates(casier: dict) -> list[dict]:
    snapshot = casier.get("discord_member_snapshot") if isinstance(casier.get("discord_member_snapshot"), dict) else {}
    discord_id = _clean(casier.get("discord_id")) or _clean(snapshot.get("id"))
    values = {
        "display_name": _clean(snapshot.get("display_name")),
        "username": _clean(snapshot.get("username")),
        "discord_id": discord_id,
    }
    candidates = []
    seen: set[str] = set()
    for field in _MEMBER_FIELDS:
        text = values[field]
        folded = casier_text.fold(text)
        if not folded or folded in seen:
            continue  # pseudo identique au nom affiché : une seule correspondance
        seen.add(folded)
        candidates.append({"kind": "membre", "field": field, "text": text, "created_at": None, "author": None})
    return candidates


def _fiche_text(fiche: dict) -> str:
    text = fiche.get("content_text")
    if isinstance(text, str):
        return text
    # Fiche écrite avant la refonte et pas encore migrée : texte calculé à la volée.
    return casier_text.content_to_text(fiche.get("content"))


def _sanction_candidates(sanction: dict, parts: frozenset[str]) -> list[dict]:
    base = {
        "sanction_id": sanction.get("id") or None,
        "sanction_type": sanction.get("type"),
    }
    created_at = sanction.get("created_at")
    candidates = []
    if "contenu" in parts:
        candidates.append({
            **base, "kind": "sanction", "field": "reason", "text": _clean(sanction.get("reason")),
            "created_at": created_at, "author": _author(sanction.get("created_by")),
        })
    if "staff" in parts:
        for field, key in (("author", "created_by"), ("moderator", "moderator")):
            person = sanction.get(key)
            if _person_parts(person):
                candidates.append({
                    **base, "kind": "sanction", "field": field, "person": person,
                    "created_at": created_at, "author": _author(person),
                })
    if "contenu" in parts:
        for note in _items(sanction, "notes"):
            if note.get("deleted_at"):
                continue
            candidates.append({
                **base, "kind": "note", "field": "content", "note_id": note.get("id") or None,
                "text": _clean(note.get("content")), "created_at": note.get("created_at"),
                "author": _author(note.get("created_by")),
            })
        for attachment in _items(sanction, "attachments"):
            if attachment.get("deleted_at"):
                continue
            candidates.append({
                **base, "kind": "sanction", "field": "filename", "text": _clean(attachment.get("filename")),
                "created_at": attachment.get("created_at") or created_at,
                "author": _author(attachment.get("uploaded_by") or sanction.get("created_by")),
            })
    return candidates


def _fiche_candidates(fiche: dict) -> list[dict]:
    base = {
        "kind": "fiche_s", "fiche_id": fiche.get("id") or None,
        "created_at": fiche.get("created_at"), "author": _author(fiche.get("created_by")),
    }
    return [
        {**base, "field": "title", "text": _clean(fiche.get("title"))},
        {**base, "field": "content", "text": _fiche_text(fiche)},
    ]


def _candidates(casier: dict, scope: str) -> list[dict]:
    parts = _SCOPE_PARTS.get(scope, _SCOPE_PARTS["tout"])
    candidates: list[dict] = []
    if "membre" in parts:
        candidates.extend(_member_candidates(casier))
    for sanction in _items(casier, "sanctions"):
        candidates.extend(_sanction_candidates(sanction, parts))
    if "contenu" in parts:
        for fiche in _items(casier, "fiches_s"):
            candidates.extend(_fiche_candidates(fiche))
    return candidates


def _hits(candidate: dict, terms: list[str]) -> list[str]:
    if "person" in candidate:
        folded_parts = [casier_text.fold(part) for part in _person_parts(candidate["person"])]
        return [term for term in terms if any(term in part for part in folded_parts)]
    folded = casier_text.fold(candidate.get("text"))
    return [term for term in terms if term in folded] if folded else []


def _person_label(person: dict, hits: list[str]) -> str:
    """Nom de l'auteur ; pseudo ou id ajoutés seulement s'ils portent un terme absent du nom."""
    parts = _person_parts(person)
    shown = [parts[0]]
    covered = {term for term in hits if term in casier_text.fold(parts[0])}
    for part in parts[1:]:
        folded = casier_text.fold(part)
        extra = {term for term in hits if term in folded and term not in covered}
        if extra:
            shown.append(part)
            covered |= extra
    return _PERSON_SEPARATOR.join(shown)


def timestamp_of(value) -> float:
    """Date ISO (ou datetime) → timestamp ; illisible ou absente → -inf (classée en dernier)."""
    moment = None
    if isinstance(value, datetime):
        moment = value
    elif isinstance(value, str) and value.strip():
        try:
            moment = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            moment = None
    if moment is None:
        return float("-inf")
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    try:
        return moment.timestamp()
    except (OverflowError, OSError, ValueError):
        return float("-inf")


def _to_match(candidate: dict, hits: list[str]) -> dict:
    if "person" in candidate:
        text = _person_label(candidate["person"], hits)
    else:
        text = candidate.get("text") or ""
    snippet, segments = casier_text.make_snippet(text, hits)
    return {
        "kind": candidate["kind"],
        "field": candidate["field"],
        "sanction_id": candidate.get("sanction_id"),
        "sanction_type": candidate.get("sanction_type"),
        "note_id": candidate.get("note_id"),
        "fiche_id": candidate.get("fiche_id"),
        "snippet": snippet,
        "segments": segments,
        "created_at": candidate.get("created_at"),
        "author": candidate.get("author"),
    }


def search_casier(casier: dict, terms: list[str], scope: str = "tout") -> tuple[bool, list[dict], int]:
    """(trouvé, correspondances ≤ 5, nombre total de correspondances) pour un document casier.

    Tous les termes doivent être trouvés, pas forcément dans le même champ. Correspondances : membre
    d'abord, puis par date décroissante. Sans terme : (True, [], 0).
    """
    if not terms:
        return True, [], 0
    found: set[str] = set()
    hits_by_candidate: list[tuple[dict, list[str]]] = []
    for candidate in _candidates(casier or {}, scope):
        hits = _hits(candidate, terms)
        if hits:
            found.update(hits)
            hits_by_candidate.append((candidate, hits))
    if len(found) < len(set(terms)):
        return False, [], 0

    members = [pair for pair in hits_by_candidate if pair[0]["kind"] == "membre"]
    others = [pair for pair in hits_by_candidate if pair[0]["kind"] != "membre"]
    others.sort(key=lambda pair: timestamp_of(pair[0].get("created_at")), reverse=True)
    ordered = members + others
    return True, [_to_match(candidate, hits) for candidate, hits in ordered[:MAX_MATCHES]], len(ordered)


# --- Filtres et tris de la liste --------------------------------------------------------------


def apply_filters(
    items: list[dict],
    status=None,
    has_active_fiche_s: bool | None = None,
    prevention: bool | None = None,
    has_open_ai_flags: bool | None = None,
) -> list[dict]:
    """Filtre les éléments de liste (dicts au format `CasierListItem`). `None` = pas de filtre ;
    `True` = seulement les éléments concernés ; `False` = les exclure."""
    wanted = frozenset(status) if status else None
    result = []
    for item in items:
        if wanted is not None and item.get("status") not in wanted:
            continue
        if has_active_fiche_s is not None and bool(item.get("has_active_fiche_s")) != has_active_fiche_s:
            continue
        if prevention is not None and bool(item.get("is_prevention")) != prevention:
            continue
        if has_open_ai_flags is not None and (int(item.get("ai_flags_open") or 0) > 0) != has_open_ai_flags:
            continue
        result.append(item)
    return result


def _member_name(item: dict) -> str:
    member = item.get("member") or {}
    return casier_text.fold(member.get("display_name") or member.get("username") or member.get("id") or "")


def _recent_key(item: dict) -> tuple[float, float, str]:
    return (
        -timestamp_of(item.get("last_activity_at")),
        -timestamp_of(item.get("created_at")),
        str(item.get("id") or ""),
    )


def sort_items(items: list[dict], sort: str = "recent") -> list[dict]:
    """`recent` : activité la plus récente d'abord ; `gravite` : statut le plus grave puis récent ;
    `nom` : nom affiché replié (accents) par ordre alphabétique."""
    if sort == "nom":
        return sorted(items, key=lambda item: (_member_name(item), str(item.get("id") or "")))
    if sort == "gravite":
        order = list(casier_service.STATUS_ORDER)

        def severity(item: dict) -> int:
            value = item.get("status")
            return order.index(value) if value in order else 0

        return sorted(items, key=lambda item: (-severity(item), *_recent_key(item)))
    return sorted(items, key=_recent_key)
