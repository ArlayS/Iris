"""
Lecture des messages de log OasisBot (fonctions pures, sans accès réseau ni base).

- `parse_duration_text` : texte libre (« 1h30 », « 2 jours », « permanent »…) -> libellé + secondes ;
- `extract_duration` : durée / fin d'une sanction dans le texte complet d'un log ;
- `extract_moderator_id` : modérateur réel cité dans le log (« <@MOD> a mit <@MEMBRE> … ») ;
- `extract_message_files` : fichiers du message (pièces jointes, composants V2, images d'embed)
  hébergés sur le CDN Discord, au format Attachment du casier.

Aucune de ces fonctions ne lève pour une entrée texte ou JSON mal formée : le bot les appelle en plus
dans des `try/except` séparés, pour qu'une extraction ratée n'empêche jamais d'enregistrer la sanction.
"""

import hashlib
import math
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import NamedTuple
from urllib.parse import unquote, urlsplit

from services import file_response_service, storage_service

MINUTE = 60
HOUR = 3_600
DAY = 86_400
WEEK = 604_800
MONTH = 2_592_000
YEAR = 31_536_000
# Au-delà, la durée est considérée comme permanente.
MAX_DURATION_SECONDS = 100 * YEAR

PERMANENT_LABEL = "Permanent"
MAX_DURATION_LABEL = 80

MAX_LOG_FILES = 10
MAX_FILENAME_LENGTH = 200
DEFAULT_FILENAME = "fichier"
DEFAULT_ATTACHMENT_MAX_BYTES = 25 * 1024 * 1024


class DurationInfo(NamedTuple):
    label: str | None
    seconds: int | None
    expires_at: str | None  # ISO 8601 UTC


# --------------------------------------------------------------------------------------
# Durées
# --------------------------------------------------------------------------------------

_UNIT_FORMS = {
    1: ("s", "sec", "secs", "seconde", "secondes", "second", "seconds"),
    MINUTE: ("m", "mn", "min", "mins", "minute", "minutes"),
    HOUR: ("h", "hr", "hrs", "heure", "heures", "hour", "hours"),
    DAY: ("j", "jr", "jrs", "d", "jour", "jours", "journee", "journees", "day", "days"),
    WEEK: ("sem", "semaine", "semaines", "w", "week", "weeks"),
    MONTH: ("mois", "month", "months"),
    YEAR: ("an", "ans", "annee", "annees", "y", "year", "years"),
}
_UNIT_SECONDS = {form: seconds for seconds, forms in _UNIT_FORMS.items() for form in forms}
# Formes longues d'abord : « min » avant « m », « mois » avant « m ».
_UNIT_ALTERNATION = "|".join(sorted(_UNIT_SECONDS, key=len, reverse=True))

_NUMBER_WORDS = {
    "un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "six": 6, "sept": 7,
    "huit": 8, "neuf": 9, "dix": 10, "quinze": 15, "trente": 30, "demi": 0.5,
}

# Appliqués au texte plié (minuscules, sans accents). Un nombre ne commence pas au milieu d'un autre
# (« 1.5h », « 24-48h ») mais peut suivre une unité (« 1h30m », « 1j12h ») ; un mot ne suit ni lettre ni
# trait d'union (« dix-huit heures » n'est jamais lu « huit heures »).
_DURATION_TOKEN = re.compile(
    r"(?:(?<![\d.,-])(?P<num>\d+(?:[.,]\d+)?)\s*"
    r"|(?<![\w-])(?P<word>" + "|".join(sorted(_NUMBER_WORDS, key=len, reverse=True)) + r")[\s-]+)"
    r"(?P<unit>" + _UNIT_ALTERNATION + r")(?![a-z])"
)
# « 1h30 » : nombre nu juste après les heures = minutes (sauf s'il porte sa propre unité).
_BARE_MINUTES = re.compile(r"\s*(\d{1,2})(?![\w.,])(?!\s*(?:" + _UNIT_ALTERNATION + r")(?![a-z]))")
# « 1 heure et demie », « 2 jours et demi ».
_AND_HALF = re.compile(r"\s+et\s+demie?(?![a-z])")
# Entre deux jetons d'une même durée : espaces, virgule, « et », « + ».
_TOKEN_JOINER = re.compile(r"[\s,]*(?:(?:et|and|\+)\s*)?")
_PERMANENT = re.compile(r"\b(?:permanent|definiti[fv]|indefini|illimite|a\s+vie\b)")
# Date ou heure de fin (« jusqu'au 25/10 », « à 18h30 ») : retirées avant la lecture des jetons.
_DATE_OR_CLOCK = re.compile(
    r"\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b"
    r"|\b(?:a|jusqu\W{0,2}au?|vers)\s+\d{1,2}\s*(?:h|:)(?:\s*\d{2}(?!\d))?"
)
_MARKDOWN_NOISE = re.compile(r"[*_`|]")

# Appliqués au texte d'origine.
_TIMESTAMP = re.compile(r"<t:(\d{1,12})(?::[tTdDfFR])?>")
_LABELLED_FIELD = re.compile(
    r"^[^\w\n]*(?:dur[ée]e|duration|temps|expiration|expire[sr]?|fin)\b[^\n:<>`]{0,30}:\s*\n?"
    r"(?:```(.*?)```|([^\n]+))",
    re.M | re.S | re.I,
)
# « pendant 10 minutes », « durant 2 jours » : retenus seulement si une durée y est reconnue ;
# « pour 1 h » : seulement si la durée suit immédiatement (« pour spam … en 5 min » n'est pas une durée).
_PENDANT = re.compile(
    r"\b(?P<keyword>pendant|durant|pour)\s+(?P<value>(?:[^\n.,;]|(?<=\d)[.,](?=\d))+)", re.I
)

# Copie locale du motif de moderation_bot (qui garde le sien) : le motif n'est jamais analysé.
REASON_CODEBLOCK_PATTERN = re.compile(r"(?:raison|motif|reason)[^\n]*\n?```(.*?)```", re.I | re.S)
_REASON_LINE = re.compile(r"^[^\w\n]*(?:raison|motif|reason)\b[^\n]*$", re.M | re.I)

ADD_VERB_PATTERN = re.compile(r"\b(a\s+mit|a\s+mis|a\s+ajout[ée])\b", re.I)
_USER_MENTION = re.compile(r"<@!?(\d{17,20})>")


def _fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    without_marks = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", without_marks.casefold()).strip()


def _clean_duration_text(text: str) -> str:
    return re.sub(r"\s+", " ", _MARKDOWN_NOISE.sub(" ", text)).strip()


def _plural(count: int, singular: str, plural: str) -> str:
    return f"{count} {singular if count == 1 else plural}"


_LARGE_UNITS = (
    (YEAR, "an", "ans"),
    (MONTH, "mois", "mois"),
    (WEEK, "semaine", "semaines"),
    (DAY, "jour", "jours"),
)


def format_duration(seconds: int) -> str:
    """Libellé lisible : « 10 min », « 1 h », « 1 h 30 », « 2 jours », « 1 semaine », « 3 mois »."""
    seconds = int(seconds)
    if seconds <= 0:
        return "0 s"
    for unit, singular, plural in _LARGE_UNITS:
        if seconds % unit == 0:
            return _plural(seconds // unit, singular, plural)

    parts = []
    rest = seconds
    for unit, singular, plural in _LARGE_UNITS:
        if unit == WEEK:  # semaines seulement pour un compte exact (« 10 jours », pas « 1 semaine 3 jours »)
            continue
        count, rest = divmod(rest, unit)
        if count:
            parts.append(_plural(count, singular, plural))
    hours, rest = divmod(rest, HOUR)
    minutes, secs = divmod(rest, MINUTE)
    if hours and minutes and not secs:
        parts.append(f"{hours} h {minutes:02d}")
    else:
        if hours:
            parts.append(f"{hours} h")
        if minutes:
            parts.append(f"{minutes} min")
        if secs:
            parts.append(f"{secs} s")
    return " ".join(parts)


def _sum_tokens(folded: str, *, phrase: bool = False) -> float | None:
    """Somme des jetons de durée (secondes), None sans jeton.

    `phrase` : seulement la première suite de jetons contiguës (« 1 h pour spam en 5 min » → 1 h).
    """
    total = 0.0
    found = False
    position = 0
    for match in _DURATION_TOKEN.finditer(folded):
        if match.start() < position:
            continue
        if found and phrase and not _TOKEN_JOINER.fullmatch(folded, position, match.start()):
            break
        found = True
        if match.group("num") is not None:
            amount = float(match.group("num").replace(",", "."))
        else:
            amount = float(_NUMBER_WORDS[match.group("word")])
        unit = _UNIT_SECONDS[match.group("unit")]
        total += amount * unit
        position = match.end()
        half = _AND_HALF.match(folded, position)
        if half:
            total += unit / 2
            position = half.end()
        elif unit == HOUR:
            bare = _BARE_MINUTES.match(folded, position)
            if bare and int(bare.group(1)) < 60:
                total += int(bare.group(1)) * MINUTE
                position = bare.end()
    return total if found else None


def _parse_duration(text, *, phrase: bool = False, anchored: bool = False) -> tuple[str | None, int | None]:
    if not isinstance(text, str):
        return None, None
    cleaned = _clean_duration_text(text)
    if not cleaned:
        return None, None
    fallback = (cleaned[:MAX_DURATION_LABEL], None)

    folded = _fold(cleaned)
    if not phrase and _PERMANENT.search(folded):
        return PERMANENT_LABEL, None
    folded = re.sub(r"\s+", " ", _DATE_OR_CLOCK.sub(" ", folded)).strip()
    if anchored and not _DURATION_TOKEN.match(folded):
        total = None
    else:
        total = _sum_tokens(folded, phrase=phrase)

    if total is None:
        # Dans une phrase (« pendant … »), « définitif » ne compte qu'en l'absence de durée chiffrée.
        if phrase and (_PERMANENT.match(folded) if anchored else _PERMANENT.search(folded)):
            return PERMANENT_LABEL, None
        return fallback
    if not math.isfinite(total) or total > MAX_DURATION_SECONDS:
        return PERMANENT_LABEL, None
    seconds = int(round(total))
    if seconds <= 0:
        return fallback
    return format_duration(seconds), seconds


def parse_duration_text(text) -> tuple[str | None, int | None]:
    """(libellé, secondes) : ("1 h 30", 5400), ("Permanent", None), (texte libre, None) ou (None, None)."""
    return _parse_duration(text)


def _aware(now) -> datetime:
    if not isinstance(now, datetime):
        return datetime.now(timezone.utc)
    if now.tzinfo is None:
        return now.replace(tzinfo=timezone.utc)
    return now


def _iso_after(now: datetime, seconds: int | None) -> str | None:
    if not seconds:
        return None
    try:
        return (now + timedelta(seconds=seconds)).astimezone(timezone.utc).isoformat()
    except (OverflowError, ValueError):
        return None


def _future_timestamp(text: str, now: datetime) -> datetime | None:
    """Premier horodatage Discord valide et postérieur à `now` (une date passée n'est pas une fin)."""
    for match in _TIMESTAMP.finditer(text):
        try:
            moment = datetime.fromtimestamp(int(match.group(1)), tz=timezone.utc)
        except (ValueError, OverflowError, OSError):
            continue
        if moment > now:
            return moment
    return None


def _info_from_timestamp(moment: datetime, now: datetime) -> DurationInfo:
    seconds = int(round((moment - now).total_seconds()))
    if seconds > MAX_DURATION_SECONDS:
        return DurationInfo(PERMANENT_LABEL, None, None)
    if seconds >= 10 * MINUTE:
        # Le log est publié quelques secondes après la sanction : « 59 min 58 s » devient « 1 h ».
        seconds = int(round(seconds / MINUTE)) * MINUTE
    return DurationInfo(format_duration(seconds), seconds, moment.isoformat())


def _strip_reason(text: str) -> str:
    text = REASON_CODEBLOCK_PATTERN.sub("\n", text)
    return _REASON_LINE.sub("", text)


def extract_duration(full_text, now: datetime | None = None) -> DurationInfo:
    """Durée d'une sanction lue dans le log, hors motif : champ libellé, horodatage <t:…>, « pendant … »."""
    if not isinstance(full_text, str) or not full_text.strip():
        return DurationInfo(None, None, None)
    now = _aware(now)
    text = _strip_reason(full_text)
    expiry = _future_timestamp(text, now)

    # (1) Champ libellé en début de ligne : « ### Durée : », « Fin du mute : », « Expiration : »…
    for match in _LABELLED_FIELD.finditer(text):
        value = (match.group(1) if match.group(1) is not None else match.group(2) or "").strip()
        if not value:
            continue
        if _TIMESTAMP.search(value):
            moment = _future_timestamp(value, now)
            if moment is not None:
                return _info_from_timestamp(moment, now)
            continue
        label, seconds = parse_duration_text(value)
        if label is None:
            continue
        if label == PERMANENT_LABEL:
            return DurationInfo(PERMANENT_LABEL, None, None)
        if expiry is not None:
            # L'horodatage Discord fait foi pour la fin.
            if seconds is None:
                seconds = _info_from_timestamp(expiry, now).seconds
            return DurationInfo(label, seconds, expiry.isoformat())
        return DurationInfo(label, seconds, _iso_after(now, seconds))

    # (2) Horodatage Discord seul.
    if expiry is not None:
        return _info_from_timestamp(expiry, now)

    # (3) « pendant … » hors motif.
    for match in _PENDANT.finditer(text):
        anchored = match.group("keyword").lower() == "pour"
        label, seconds = _parse_duration(match.group("value"), phrase=True, anchored=anchored)
        if label == PERMANENT_LABEL:
            return DurationInfo(PERMANENT_LABEL, None, None)
        if seconds:
            return DurationInfo(label, seconds, _iso_after(now, seconds))

    return DurationInfo(None, None, None)


# --------------------------------------------------------------------------------------
# Modérateur
# --------------------------------------------------------------------------------------

def extract_moderator_id(full_text, member_id) -> str | None:
    """Id du modérateur : première mention d'utilisateur différente du membre, ligne « a mit » d'abord."""
    if not isinstance(full_text, str):
        return None
    member = str(member_id) if member_id is not None else None
    text = _strip_reason(full_text)

    def first_other_mention(chunk: str) -> str | None:
        for mention in _USER_MENTION.findall(chunk):
            if mention != member:
                return mention
        return None

    for line in text.split("\n"):
        if ADD_VERB_PATTERN.search(line):
            found = first_other_mention(line)
            if found:
                return found
    return first_other_mention(text)


# --------------------------------------------------------------------------------------
# Fichiers du message
# --------------------------------------------------------------------------------------

_SNOWFLAKE = re.compile(r"\d{17,20}")
_FORBIDDEN_FILENAME_CATEGORIES = {"Cc", "Cf", "Zl", "Zp"}
_MAX_COMPONENT_NODES = 500


def clean_filename(name) -> str:
    """Nom affichable : dernier segment, sans caractères de contrôle, ≤ 200 caractères, « fichier » sinon."""
    if not isinstance(name, str):
        return DEFAULT_FILENAME
    name = name.replace("\\", "/").rsplit("/", 1)[-1]
    name = "".join(char for char in name if unicodedata.category(char) not in _FORBIDDEN_FILENAME_CATEGORIES)
    name = name.strip()
    if len(name) > MAX_FILENAME_LENGTH:
        stem, dot, extension = name.rpartition(".")
        if dot and stem and 0 < len(extension) <= 10:
            name = stem[: MAX_FILENAME_LENGTH - len(extension) - 1].rstrip() + "." + extension
        else:
            name = name[:MAX_FILENAME_LENGTH].rstrip()
    return name or DEFAULT_FILENAME


def _as_list(value) -> list:
    return value if isinstance(value, list) else []


def _snowflake(value) -> str | None:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        return None
    value = str(value).strip()
    return value if _SNOWFLAKE.fullmatch(value) else None


def _declared_size(value) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _declared_type(value) -> str | None:
    if not isinstance(value, str):
        return None
    return value.strip()[:100] or None


def _cdn_attachment_path(url) -> str | None:
    """Chemin de l'URL si elle désigne une pièce jointe du CDN Discord (`/attachments/…`), sinon None."""
    if not isinstance(url, str) or not file_response_service.is_discord_cdn_url(url):
        return None
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return None
    if parts.username is not None or parts.password is not None or port is not None:
        return None
    path = parts.path
    if not path.startswith("/attachments/"):
        return None
    decoded = unquote(path)
    if "\\" in decoded or any(segment in {".", ".."} for segment in decoded.split("/")):
        return None
    return path


def _too_large_message(max_bytes: int) -> str:
    megabytes = max_bytes / (1024 * 1024)
    shown = f"{megabytes:.0f}" if megabytes.is_integer() else f"{megabytes:.1f}".replace(".", ",")
    return f"Fichier trop volumineux (max {shown} Mo)."


def _attachment_max_bytes() -> int:
    import config  # import local : lu à l'appel, remplaçable dans les tests

    return getattr(config, "CASIER_ATTACHMENT_MAX_BYTES", DEFAULT_ATTACHMENT_MAX_BYTES)


def extract_message_files(
    raw_message,
    *,
    max_bytes: int | None = None,
    limit: int = MAX_LOG_FILES,
    now: datetime | None = None,
) -> list[dict]:
    """Fichiers d'un message de log au format Attachment (casier), sans doublon, `limit` au plus.

    Sources : `attachments`, composants V2 (Fichier 13, Galerie 12, Miniature 11, y compris dans
    `components` / `accessory` imbriqués), `embeds[].image` / `thumbnail`. Seules les URL du CDN Discord
    sous `/attachments/` sont gardées (ni avatars, ni emojis, ni hôtes externes) ; `attachment://nom`
    est résolu dans les pièces jointes du message.
    """
    if not isinstance(raw_message, dict):
        return []
    if max_bytes is None:
        max_bytes = _attachment_max_bytes()
    created_at = _aware(now).astimezone(timezone.utc).isoformat()

    raw_attachments = [item for item in _as_list(raw_message.get("attachments")) if isinstance(item, dict)]
    attachments_by_id: dict[str, dict] = {}
    attachments_by_name: dict[str, dict] = {}
    for item in raw_attachments:
        attachment_id = _snowflake(item.get("id"))
        if attachment_id:
            attachments_by_id.setdefault(attachment_id, item)
        if isinstance(item.get("filename"), str):
            attachments_by_name.setdefault(item["filename"], item)

    files: list[dict] = []
    by_id: dict[str, dict] = {}
    by_path: dict[str, dict] = {}

    def add(attachment_id, urls, filename, content_type, size) -> None:
        path = url = None
        for candidate in urls:
            path = _cdn_attachment_path(candidate)
            if path:
                url = candidate
                break
        if not path:
            return
        entry_id = attachment_id or hashlib.sha1(path.encode("utf-8")).hexdigest()[:24]
        existing = by_id.get(entry_id) or by_path.get(path)
        if existing is not None:
            # Même fichier cité deux fois (pièce jointe + composant) : on complète la première entrée.
            if existing["content_type"] is None:
                existing["content_type"] = content_type
            if existing["size"] is None and size is not None:
                existing["size"] = size
                if size > max_bytes:
                    existing["status"] = "too_large"
                    existing["error"] = _too_large_message(max_bytes)
            return
        if len(files) >= limit:
            return
        name = clean_filename(filename if isinstance(filename, str) and filename.strip()
                              else unquote(path.rsplit("/", 1)[-1]))
        too_large = size is not None and size > max_bytes
        entry = {
            "id": entry_id,
            "origin": "discord",
            "filename": name,
            "extension": storage_service.sanitize_extension(file_response_service.attachment_extension(name)),
            "content_type": content_type,
            "size": size,
            "source_url": url,
            "status": "too_large" if too_large else "pending",
            "error": _too_large_message(max_bytes) if too_large else None,
            "created_at": created_at,
            "stored_at": None,
            "uploaded_by": None,
            "deleted_at": None,
            "deleted_by": None,
        }
        files.append(entry)
        by_id[entry_id] = entry
        by_path[path] = entry

    def add_attachment(item: dict, extra_urls=(), content_type=None, size=None) -> None:
        declared_size = _declared_size(item.get("size"))
        add(
            _snowflake(item.get("id")),
            [item.get("url"), item.get("proxy_url"), *extra_urls],
            item.get("filename"),
            _declared_type(item.get("content_type")) or content_type,
            declared_size if declared_size is not None else size,
        )

    def add_media(media, *, name=None, size=None) -> None:
        if not isinstance(media, dict):
            return
        url = media.get("url")
        linked = attachments_by_id.get(_snowflake(media.get("attachment_id")) or "")
        if linked is None and isinstance(url, str) and url.startswith("attachment://"):
            linked = attachments_by_name.get(url[len("attachment://"):])
        content_type = _declared_type(media.get("content_type"))
        if linked is not None:
            add_attachment(linked, (url, media.get("proxy_url")), content_type, _declared_size(size))
            return
        add(_snowflake(media.get("attachment_id")), [url, media.get("proxy_url")], name, content_type,
            _declared_size(size))

    for item in raw_attachments:
        add_attachment(item)

    # Parcours itératif des composants (profondeur et nombre de nœuds bornés).
    stack = [(node, 0) for node in reversed(_as_list(raw_message.get("components")))]
    visited = 0
    while stack and visited < _MAX_COMPONENT_NODES:
        node, depth = stack.pop()
        visited += 1
        if not isinstance(node, dict):
            continue
        kind = node.get("type")
        if kind == 13:
            add_media(node.get("file"), name=node.get("name"), size=node.get("size"))
        elif kind == 12:
            for gallery_item in _as_list(node.get("items")):
                if isinstance(gallery_item, dict):
                    add_media(gallery_item.get("media"))
        elif kind == 11:
            add_media(node.get("media"))
        if depth >= 20:
            continue
        accessory = node.get("accessory")
        nested = _as_list(node.get("components")) + ([accessory] if isinstance(accessory, dict) else [])
        stack.extend((child, depth + 1) for child in reversed(nested))

    for embed in _as_list(raw_message.get("embeds")):
        if isinstance(embed, dict):
            add_media(embed.get("image"))
            add_media(embed.get("thumbnail"))

    return files
