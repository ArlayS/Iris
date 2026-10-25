"""Texte du casier : pliage (accents, casse), contenu des fiches S et extraits surlignés.

Fonctions pures (aucun accès à la base ni au réseau), partagées par la recherche, les fiches S,
la migration et les signalements IA.
"""
import html
import json
import re
import unicodedata

CONTENT_TEXT_MAX_LENGTH = 20_000
SNIPPET_WIDTH = 160
MAX_BLOCK_DEPTH = 20
MAX_INLINE_DEPTH = 10
MEDIA_URL_PREVIEW_LENGTH = 200
ELLIPSIS = "…"

CONTENT_FORMATS = ("blocknote", "html", "text")
MEDIA_BLOCK_TYPES = frozenset({"image", "video", "audio", "file"})
SAFE_LINK_SCHEMES = ("http:", "https:", "mailto:")
EXTERNAL_MEDIA_LABEL = "Média externe non affiché : "

# `[^<>]` (et non `[^>]`) : temps linéaire même sur « <a<a<a… » sans « > » (200 000 caractères).
_HTML_TAG = re.compile(r"<[a-zA-Z][^<>]*>")
# Seules les images uploadées dans Iris (forme relative, ou ancienne forme absolue de l'éditeur).
_IRIS_MEDIA_URL = re.compile(
    r"(?:https://api\.loasis\.app)?/api/staff/meetings/images/[A-Za-z0-9._-]{1,200}"
)

_HTML_HIDDEN = re.compile(
    r"<(script|style|template)\b[^<>]*>.*?(?:</\1\s*>|\Z)", re.IGNORECASE | re.DOTALL
)
_HTML_COMMENT = re.compile(r"<!--.*?(?:-->|\Z)", re.DOTALL)
_HTML_LINE_BREAK = re.compile(
    r"<br\s*/?>|</(?:p|div|li|h[1-6]|tr|blockquote|pre|ul|ol|table|section|article|header|footer)\s*>",
    re.IGNORECASE,
)
_HTML_CELL_END = re.compile(r"</t[dh]\s*>", re.IGNORECASE)
_HTML_STRIP = re.compile(r"</?[a-zA-Z][^<>]*>|<![^<>]*>")

_ACCENT_VARIANTS = {
    "a": "aàâäáãå",
    "e": "eéèêë",
    "i": "iîïíì",
    "o": "oôöóòõ",
    "u": "uùûüú",
    "c": "cç",
    "n": "nñ",
    "y": "yÿý",
}
_ACCENT_CLASSES = {letter: f"[{chars}{chars.upper()}]" for letter, chars in _ACCENT_VARIANTS.items()}
_LIGATURE_CLASSES = {"oe": "[œŒ]", "ae": "[æÆ]"}


# --- Pliage -------------------------------------------------------------------------------

def _strip_marks(text: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch))


def _fold_char(ch: str) -> str:
    folded = _strip_marks(_strip_marks(ch).casefold())
    return folded.replace("œ", "oe").replace("æ", "ae")


class _FoldTable(dict):
    """Table de `str.translate` remplie à la demande : un caractère → sa forme pliée."""

    def __missing__(self, code: int) -> str:
        value = _fold_char(chr(code))
        self[code] = value
        return value


_FOLD_TABLE = _FoldTable()


def fold(text) -> str:
    """Forme de comparaison : NFKD, sans diacritiques, casefold, ligatures œ/æ dépliées,
    espaces compactés et retirés aux extrémités. `fold("  Éloïse  STRAßE ")` → `"eloise strasse"`."""
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)
    if not text:
        return ""
    return " ".join(text.translate(_FOLD_TABLE).split())


def _fold_with_origin(text: str) -> tuple[str, list[int]]:
    """Comme `fold`, avec pour chaque caractère plié l'indice du caractère d'origine."""
    chars: list[str] = []
    origin: list[int] = []
    for index, ch in enumerate(text):
        for out in _FOLD_TABLE[ord(ch)]:
            if out.isspace():
                if not chars or chars[-1] == " ":
                    continue
                out = " "
            chars.append(out)
            origin.append(index)
    if chars and chars[-1] == " ":
        chars.pop()
        origin.pop()
    return "".join(chars), origin


def accent_insensitive_regex(needle) -> str:
    """Motif de regex (à utiliser avec l'option `i`) qui trouve `needle` quels que soient les accents.

    Les caractères spéciaux sont échappés (`re.escape`) ; chaque voyelle, `c`, `n`, `y` devient
    une classe (`e` → `[eéèêë…]`), les espaces deviennent `\\s+`, « oe »/« ae » trouvent aussi
    « œ »/« æ » (et inversement), « ß » trouve aussi « ss ».
    """
    text = " ".join(str(needle or "").split())
    pieces: list[str] = []
    index = 0
    while index < len(text):
        ch = text[index]
        if ch == " ":
            pieces.append(r"\s+")
            index += 1
            continue
        folded = _FOLD_TABLE[ord(ch)]
        if folded in ("o", "a") and index + 1 < len(text) and _FOLD_TABLE[ord(text[index + 1])] == "e":
            pair = folded + "e"
            pieces.append(f"(?:{_regex_for_folded(pair)}|{_LIGATURE_CLASSES[pair]})")
            index += 2
            continue
        if not folded:
            pass  # diacritique isolé : déjà couvert par la classe de la lettre précédente
        elif len(folded) == 1 and folded in _ACCENT_CLASSES:
            pieces.append(_ACCENT_CLASSES[folded])
        elif folded in _LIGATURE_CLASSES:
            pieces.append(f"(?:{_LIGATURE_CLASSES[folded]}|{_regex_for_folded(folded)})")
        elif folded == ch.lower():
            pieces.append(re.escape(ch))
        else:
            pieces.append(f"(?:{re.escape(ch)}|{_regex_for_folded(folded)})")
        index += 1
    return "".join(pieces)


def _regex_for_folded(folded: str) -> str:
    return "".join(_ACCENT_CLASSES.get(ch) or re.escape(ch) for ch in folded)


# --- Extraits surlignés -------------------------------------------------------------------

def _is_extender(ch: str) -> bool:
    """Caractère qui prolonge le précédent (diacritique, ZWJ, sélecteur de variante, teinte d'emoji)."""
    return unicodedata.category(ch) in ("Mn", "Me", "Cf") or 0x1F3FB <= ord(ch) <= 0x1F3FF


def _match_spans(text: str, terms: list[str]) -> list[tuple[int, int]]:
    folded, origin = _fold_with_origin(text)
    spans: list[tuple[int, int]] = []
    for needle in terms:
        position = folded.find(needle)
        while position != -1:
            start = origin[position]
            end = origin[position + len(needle) - 1] + 1
            # Diacritiques détachés (« e » + accent combinant) : rattachés à la correspondance.
            while end < len(text) and not text[end].isspace() and _FOLD_TABLE[ord(text[end])] == "":
                end += 1
            spans.append((start, end))
            position = folded.find(needle, position + 1)
    spans.sort()
    merged: list[tuple[int, int]] = []
    for start, end in spans:
        if merged and start < merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _window(text: str, anchor: tuple[int, int] | None, width: int) -> tuple[int, int]:
    """Bornes [start, end) de l'extrait : correspondance visible, mots entiers si possible."""
    length = len(text)
    inner = width - 2  # place des deux « … »
    if anchor is None:
        start, end = 0, width - 1
        match_start = match_end = 0
    else:
        match_start, match_end = anchor
        if match_end - match_start >= inner:
            start, end = match_start, min(length, match_start + inner)
            match_end = end
        else:
            before = min(match_start, (inner - (match_end - match_start)) // 3)
            start = match_start - before
            end = start + inner
            if end > length:
                end = length
                start = max(0, length - inner)
        if start == 0:
            end = min(length, end + 1)
        if end == length:
            start = max(0, start - 1)

    if start > 0 and not text[start - 1].isspace():
        space = text.find(" ", start, min(match_start, start + 20))
        if space != -1:
            start = space + 1
    if end < length and not text[end].isspace():
        space = text.rfind(" ", max(match_end, end - 20), end)
        if space != -1:
            end = space
    while start < match_start and (text[start].isspace() or _is_extender(text[start])):
        start += 1
    while end > max(match_end, start) and end < length and _is_extender(text[end]):
        end -= 1
    while end > max(match_end, start) and text[end - 1].isspace():
        end -= 1
    return start, end


def _merge_segments(parts: list[tuple[str, bool]]) -> list[dict]:
    segments: list[dict] = []
    for text, match in parts:
        if not text:
            continue
        if segments and segments[-1]["match"] == match:
            segments[-1]["text"] += text
        else:
            segments.append({"text": text, "match": match})
    return segments


def make_snippet(text, terms, width: int = SNIPPET_WIDTH) -> tuple[str, list[dict]]:
    """Extrait (≤ `width` caractères, « … » si coupé) centré sur la première correspondance.

    Renvoie `(snippet, segments)` avec `"".join(s["text"] for s in segments) == snippet`, segments
    jamais vides, adjacents de même `match` fusionnés. Les espaces (retours à la ligne compris) sont
    compactés. Correspondance insensible à la casse et aux accents, calculée en points de code.
    """
    clean = " ".join(str(text or "").split())
    if not clean:
        return "", []
    if isinstance(terms, str):
        terms = [terms]
    needles = sorted({fold(term) for term in terms or () if fold(term)})
    width = max(int(width or SNIPPET_WIDTH), 20)

    spans = _match_spans(clean, needles) if needles else []
    if len(clean) <= width:
        start, end = 0, len(clean)
    else:
        start, end = _window(clean, spans[0] if spans else None, width)

    parts: list[tuple[str, bool]] = [(ELLIPSIS, False)] if start > 0 else []
    cursor = start
    for span_start, span_end in spans:
        if span_start < start or span_end > end:
            continue  # correspondance coupée par le bord de l'extrait : non surlignée
        parts.append((clean[cursor:span_start], False))
        parts.append((clean[span_start:span_end], True))
        cursor = span_end
    parts.append((clean[cursor:end], False))
    if end < len(clean):
        parts.append((ELLIPSIS, False))

    segments = _merge_segments(parts)
    return "".join(segment["text"] for segment in segments), segments


# --- Contenu des fiches S -----------------------------------------------------------------

def _reject_constant(value: str):
    raise ValueError(f"Constante JSON non standard : {value}")


def _is_block_list(value) -> bool:
    return isinstance(value, list) and all(
        isinstance(block, dict) and isinstance(block.get("type"), str) for block in value
    )


def parse_blocks(content) -> list | None:
    """Liste de blocs BlockNote (chaque élément est un objet avec une clé `type` chaîne, `[]`
    compris), depuis une chaîne JSON ou une liste ; sinon `None`."""
    if isinstance(content, list):
        return content if _is_block_list(content) else None
    if not isinstance(content, str) or not content.strip():
        return None
    try:
        value = json.loads(content, parse_constant=_reject_constant)
    except Exception:  # JSON invalide, NaN/Infinity, imbrication trop profonde
        return None
    return value if _is_block_list(value) else None


def detect_content_format(content) -> str:
    """`"blocknote"`, `"html"` (au moins une balise) ou `"text"`."""
    if parse_blocks(content) is not None:
        return "blocknote"
    if isinstance(content, str) and _HTML_TAG.search(content):
        return "html"
    return "text"


def _href_scheme_text(href: str) -> str:
    return "".join(
        ch for ch in href if not (ch.isspace() or unicodedata.category(ch) in ("Cc", "Cf"))
    ).lower()


def _is_safe_href(href) -> bool:
    return isinstance(href, str) and _href_scheme_text(href).startswith(SAFE_LINK_SCHEMES)


def _is_iris_media_url(url: str) -> bool:
    return bool(_IRIS_MEDIA_URL.fullmatch(url.strip()))


def _text_inline(text: str) -> dict:
    return {"type": "text", "text": text, "styles": {}}


def _sanitize_inlines(items: list, depth: int = 0) -> list:
    result = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get("type") != "link":
            result.append(item)
            continue
        inner = _link_inner(item.get("content"), depth)
        href = item.get("href")
        if depth == 0 and _is_safe_href(href):
            link = dict(item)
            link["href"] = href.strip()
            link["content"] = inner
            result.append(link)
        else:
            # Lien refusé (ou imbriqué dans un autre lien) : le texte reste, le lien disparaît.
            result.extend(inner)
    return result


def _link_inner(content, depth: int) -> list:
    if isinstance(content, str):
        return [_text_inline(content)] if content else []
    if isinstance(content, list) and depth < MAX_INLINE_DEPTH:
        return _sanitize_inlines(content, depth + 1)
    return []


def _sanitize_cell(cell):
    if isinstance(cell, list):
        return _sanitize_inlines(cell)
    if isinstance(cell, dict):
        clean = dict(cell)
        if isinstance(cell.get("content"), list):
            clean["content"] = _sanitize_inlines(cell["content"])
        return clean
    if isinstance(cell, str):
        return cell
    return []


def _sanitize_table(table: dict) -> dict:
    clean = dict(table)
    rows = []
    for row in table.get("rows") if isinstance(table.get("rows"), list) else []:
        if not isinstance(row, dict):
            continue
        clean_row = dict(row)
        cells = row.get("cells")
        clean_row["cells"] = [_sanitize_cell(cell) for cell in cells] if isinstance(cells, list) else []
        rows.append(clean_row)
    clean["rows"] = rows
    return clean


def _external_media_paragraph(block: dict, url) -> dict:
    preview = str(url).strip()[:MEDIA_URL_PREVIEW_LENGTH]
    paragraph = {
        "type": "paragraph",
        "content": [_text_inline(f"{EXTERNAL_MEDIA_LABEL}{preview}")],
        "children": block.get("children") or [],
    }
    if isinstance(block.get("id"), str):
        paragraph = {"id": block["id"], **paragraph}
    return paragraph


def _sanitize_block(block: dict, depth: int) -> dict:
    clean = dict(block)
    content = block.get("content")
    if isinstance(content, list):
        clean["content"] = _sanitize_inlines(content)
    elif isinstance(content, dict) and content.get("type") == "tableContent":
        clean["content"] = _sanitize_table(content)
    if "children" in block:
        children = block.get("children")
        if isinstance(children, list) and depth < MAX_BLOCK_DEPTH:
            clean["children"] = _sanitize_blocks(children, depth + 1)
        else:
            clean["children"] = []

    if clean["type"] in MEDIA_BLOCK_TYPES:
        props = block.get("props")
        url = props.get("url") if isinstance(props, dict) else None
        if isinstance(url, str) and not url.strip():
            return clean  # URL vide : BlockNote n'affiche rien
        if url is not None:
            if not isinstance(url, str) or not _is_iris_media_url(url):
                return _external_media_paragraph(clean, url)
            if url != url.strip():
                clean["props"] = {**props, "url": url.strip()}
    return clean


def _sanitize_blocks(blocks: list, depth: int) -> list:
    return [
        _sanitize_block(block, depth)
        for block in blocks
        if isinstance(block, dict) and isinstance(block.get("type"), str)
    ]


def sanitize_blocknote(blocks) -> list:
    """Copie assainie d'une liste de blocs BlockNote (l'entrée n'est jamais modifiée).

    Liens : seuls `http:`, `https:`, `mailto:` sont gardés (sinon le texte reste, le lien disparaît).
    Médias (`image`, `video`, `audio`, `file`) : seules les images uploadées dans Iris sont gardées,
    les autres deviennent un paragraphe « Média externe non affiché : <url> ». Profondeur de
    `children` limitée à 20, éléments non-objets retirés, clés inconnues conservées.
    Ne lève jamais : une entrée non conforme donne `[]`.
    """
    if not isinstance(blocks, list):
        return []
    try:
        return _sanitize_blocks(blocks, 1)
    except Exception:
        return []


def _inline_text(items: list, depth: int = 0) -> str:
    parts = []
    for item in items:
        if not isinstance(item, dict):
            continue
        text = item.get("text")
        if isinstance(text, str):
            parts.append(text)
        inner = item.get("content")
        if isinstance(inner, str):
            parts.append(inner)
        elif isinstance(inner, list) and depth < MAX_INLINE_DEPTH:
            parts.append(_inline_text(inner, depth + 1))
    return "".join(parts)


def _cell_text(cell) -> str:
    if isinstance(cell, list):
        return _inline_text(cell)
    if isinstance(cell, str):
        return cell
    if isinstance(cell, dict):
        inner = cell.get("content")
        if isinstance(inner, list):
            return _inline_text(inner)
        if isinstance(inner, str):
            return inner
    return ""


def _table_lines(table: dict) -> list[str]:
    lines = []
    rows = table.get("rows")
    for row in rows if isinstance(rows, list) else []:
        cells = row.get("cells") if isinstance(row, dict) else None
        if not isinstance(cells, list):
            continue
        texts = [_cell_text(cell).strip() for cell in cells]
        line = " | ".join(text for text in texts if text)
        if line:
            lines.append(line)
    return lines


def _collect_lines(blocks: list, lines: list[str], depth: int) -> None:
    for block in blocks:
        if not isinstance(block, dict):
            continue
        parts = []
        content = block.get("content")
        if isinstance(content, list):
            parts.append(_inline_text(content))
        elif isinstance(content, str):
            parts.append(content)
        props = block.get("props")
        if block.get("type") in MEDIA_BLOCK_TYPES and isinstance(props, dict):
            for key in ("caption", "name"):
                value = props.get(key)
                if isinstance(value, str) and value.strip() and value.strip() not in parts:
                    parts.append(value.strip())
        line = " — ".join(part.strip() for part in parts if part.strip())
        if line:
            lines.append(line)
        if isinstance(content, dict) and content.get("type") == "tableContent":
            lines.extend(_table_lines(content))
        children = block.get("children")
        if isinstance(children, list) and depth < MAX_BLOCK_DEPTH:
            _collect_lines(children, lines, depth + 1)


def blocknote_to_text(content) -> str:
    """Texte brut d'un document BlockNote (liste de blocs ou JSON) : une ligne par bloc (et par
    ligne de tableau), légendes et noms des médias compris. Tronqué à 20 000 caractères."""
    blocks = content if isinstance(content, list) else parse_blocks(content)
    if not blocks:
        return ""
    lines: list[str] = []
    _collect_lines(blocks, lines, 1)
    return "\n".join(lines)[:CONTENT_TEXT_MAX_LENGTH]


def html_to_text(content: str) -> str:
    """Texte d'un ancien contenu HTML : balises retirées, entités décodées, une ligne par bloc."""
    text = _HTML_HIDDEN.sub(" ", content)
    text = _HTML_COMMENT.sub(" ", text)
    text = _HTML_LINE_BREAK.sub("\n", text)
    text = _HTML_CELL_END.sub(" ", text)
    text = html.unescape(_HTML_STRIP.sub("", text))
    lines = (" ".join(line.split()) for line in text.splitlines())
    return "\n".join(line for line in lines if line)


def content_to_text(content) -> str:
    """Texte de recherche d'une fiche S, quel que soit son format (BlockNote assaini d'abord,
    HTML sans balises, texte tel quel). Tronqué à 20 000 caractères."""
    if not isinstance(content, str) or not content:
        return ""
    blocks = parse_blocks(content)
    if blocks is not None:
        return blocknote_to_text(sanitize_blocknote(blocks))
    if _HTML_TAG.search(content):
        return html_to_text(content)[:CONTENT_TEXT_MAX_LENGTH]
    return content[:CONTENT_TEXT_MAX_LENGTH]


def _has_visible_media(blocks: list, depth: int = 1) -> bool:
    for block in blocks:
        if not isinstance(block, dict):
            continue
        props = block.get("props")
        if block.get("type") in MEDIA_BLOCK_TYPES and isinstance(props, dict):
            url = props.get("url")
            if isinstance(url, str) and url.strip():
                return True
        children = block.get("children")
        if isinstance(children, list) and depth < MAX_BLOCK_DEPTH and _has_visible_media(children, depth + 1):
            return True
    return False


def is_fiche_empty(content) -> bool:
    """Vrai si la fiche n'a ni texte ni média affichable (évalué après assainissement)."""
    blocks = parse_blocks(content)
    if blocks is not None:
        clean = sanitize_blocknote(blocks)
        return not blocknote_to_text(clean).strip() and not _has_visible_media(clean)
    return not content_to_text(content).strip()


def prepare_fiche_content(raw) -> tuple[str, str, str]:
    """`(contenu stocké, format, content_text)` pour l'écriture (POST/PATCH) comme pour la lecture.

    BlockNote : assaini puis sérialisé en JSON compact (`ensure_ascii=False`) ; HTML et texte :
    gardés tels quels. Idempotent : appliqué au contenu stocké, il le renvoie inchangé.
    """
    raw = raw if isinstance(raw, str) else ""
    blocks = parse_blocks(raw)
    if blocks is None:
        return raw, detect_content_format(raw), content_to_text(raw)
    clean = sanitize_blocknote(blocks)
    text = blocknote_to_text(clean)
    try:
        stored = json.dumps(clean, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError, RecursionError):
        # Inattendu (contenu issu de json.loads) : on ne garde que le texte, jamais le JSON brut.
        return text, "text", text
    return stored, "blocknote", text
