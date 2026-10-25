"""Tests hors-ligne de services/casier_text.py (fonctions pures) et des réglages casier de config.py."""
import security_harness as h  # noqa: F401  (environnement de test et base simulée, avant l'application)

import copy
import json
import os
import random
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest

import config
from services import casier_text as t

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _para(*inlines, children=None, **extra):
    block = {"type": "paragraph", "props": {}, "content": list(inlines), "children": children or []}
    block.update(extra)
    return block


def _text(value, **styles):
    return {"type": "text", "text": value, "styles": styles}


def _link(href, *inlines):
    return {"type": "link", "href": href, "content": list(inlines)}


def _image(url, **props):
    return {"id": "img-1", "type": "image", "props": {"url": url, **props}, "children": []}


def _nested(depth):
    """Chaîne de `depth` blocs imbriqués (le premier au niveau 1)."""
    block = _para(_text(f"niveau {depth}"))
    for level in range(depth - 1, 0, -1):
        block = _para(_text(f"niveau {level}"), children=[block])
    return [block]


def _depth(blocks):
    if not blocks:
        return 0
    return 1 + max(_depth(block.get("children") or []) for block in blocks)


# --- fold -------------------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Éloïse", "eloise"),
        ("ÉCART", "ecart"),
        ("François", "francois"),
        ("Niño", "nino"),
        ("straße", "strasse"),
        ("Œuvre", "oeuvre"),
        ("cœur", "coeur"),
        ("Ægir", "aegir"),
        ("ﬁn", "fin"),
        ("İstanbul", "istanbul"),
        ("été", "ete"),  # accents combinants (forme décomposée)
        ("  Inès \n\t (staff)  ", "ines (staff)"),
        ("Ｆｕｌｌ", "full"),
        ("🔥🔥 SPAM massif", "🔥🔥 spam massif"),
        ("1153638521786093580", "1153638521786093580"),
        ("", ""),
    ],
)
def test_fold(raw, expected):
    assert t.fold(raw) == expected


def test_fold_non_texte_et_idempotence():
    assert t.fold(None) == ""
    assert t.fold(1153638521786093580) == "1153638521786093580"
    for sample in ["Éloïse", "STRAßE", "Œuvre", "ﬃ", "İ", "ΣΑΣ", "Ǆ", "é", "´ ¨", "🔥 x"]:
        assert t.fold(t.fold(sample)) == t.fold(sample)


def test_fold_avec_origine_identique_a_fold():
    rng = random.Random(42)
    alphabet = "aéÉeiïoôœŒßﬁ İ́\n\t´🔥👨‍👩Zz-1"
    for _ in range(300):
        sample = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 30)))
        folded, origin = t._fold_with_origin(sample)
        assert folded == t.fold(sample)
        assert len(origin) == len(folded)
        assert origin == sorted(origin)
        assert all(0 <= index < len(sample) for index in origin)


# --- regex insensible aux accents ---------------------------------------------------------------

def _finds(needle, haystack):
    return re.search(t.accent_insensitive_regex(needle), haystack, re.IGNORECASE) is not None


@pytest.mark.parametrize(
    ("needle", "haystack"),
    [
        ("eloise", "Éloïse"),
        ("ÉLOÏSE", "eloise"),
        ("ecart", "un écart"),
        ("francois", "François"),
        ("nino", "Niño"),
        ("cafe", "CAFÉ"),
        ("yvon", "Ÿvon"),
        ("coeur", "cœur"),
        ("coeur", "coeur"),
        ("cœur", "coeur"),
        ("CŒUR", "cœur"),
        ("aegir", "Ægir"),
        ("straße", "strasse"),
        ("straße", "STRAßE"),
        ("mathis b", "mathis   b"),
        ("ines (staff)", "Inès (staff)"),
        ("115363852", "1153638521786093580"),
    ],
)
def test_accent_insensitive_regex_trouve(needle, haystack):
    assert _finds(needle, haystack)


@pytest.mark.parametrize(
    ("needle", "haystack"),
    [
        ("hiver.*", "hiver prochain"),
        ("a.b", "axb"),
        ("eloise", "elise"),
        ("[abc]", "a"),
    ],
)
def test_accent_insensitive_regex_echappe(needle, haystack):
    assert not _finds(needle, haystack)


def test_accent_insensitive_regex_classes_du_contrat():
    for letter, variants in {
        "a": "aàâäáãå", "e": "eéèêë", "i": "iîïíì", "o": "oôöóòõ",
        "u": "uùûüú", "c": "cç", "n": "nñ", "y": "yÿý",
    }.items():
        pattern = t.accent_insensitive_regex(letter)
        for variant in variants + variants.upper():
            assert re.fullmatch(pattern, variant), (letter, variant)


def test_accent_insensitive_regex_motifs_speciaux_valides():
    for needle in ["(test", "a+b?", "\\d", "x{2}", "$^|", "[", "100%", "hiver.*", "é́", "  ", ""]:
        re.compile(t.accent_insensitive_regex(needle))
    assert t.accent_insensitive_regex("   ") == ""
    assert _finds("hiver.*", "Préparation hiver.* test")


def test_accent_insensitive_regex_avec_mongomock():
    collection = h.db.casier_text_regex_test

    async def scenario():
        await collection.delete_many({})
        await collection.insert_many(
            [{"n": 1, "name": "Éloïse"}, {"n": 2, "name": "eloise"}, {"n": 3, "name": "Élise"},
             {"n": 4, "name": "cœur fragile"}, {"n": 5, "name": "hiver.*"}]
        )

        async def found(needle):
            query = {"name": {"$regex": t.accent_insensitive_regex(needle), "$options": "i"}}
            return sorted([doc["n"] async for doc in collection.find(query)])

        result = (await found("ELOISE"), await found("coeur"), await found("hiver.*"))
        await collection.drop()
        return result

    assert h.run(scenario()) == ([1, 2], [4], [5])


# --- extraits surlignés ------------------------------------------------------------------------

def _check_snippet(snippet, segments, terms, width=t.SNIPPET_WIDTH):
    assert "".join(segment["text"] for segment in segments) == snippet
    assert len(snippet) <= width
    assert all(segment["text"] for segment in segments)
    assert all(set(segment) == {"text", "match"} for segment in segments)
    for previous, current in zip(segments, segments[1:]):
        assert previous["match"] != current["match"]
    folded_terms = [t.fold(term) for term in terms if t.fold(term)]
    for segment in segments:
        if segment["match"]:
            assert any(term in t.fold(segment["text"]) for term in folded_terms)


def test_make_snippet_exemple_du_contrat():
    snippet, segments = t.make_snippet("Récidive : lien de phishing supprimé.", ["phishing"])
    assert snippet == "Récidive : lien de phishing supprimé."
    assert segments == [
        {"text": "Récidive : lien de ", "match": False},
        {"text": "phishing", "match": True},
        {"text": " supprimé.", "match": False},
    ]


@pytest.mark.parametrize(
    ("text", "term", "matched"),
    [
        ("🔥🔥 spam massif", "spam", "spam"),
        ("👨‍👩‍👧 famille 🔥 SPAM", "spam", "SPAM"),
        ("Une Œuvre collective", "oeuvre", "Œuvre"),
        ("Une Œuvre collective", "œuvre", "Œuvre"),
        ("Grande straße du village", "strasse", "straße"),
        ("Grande straße du village", "straße", "straße"),
        ("Message d'Éloïse", "eloise", "Éloïse"),
        ("café noir", "cafe", "café"),
        ("ID 1153638521786093580", "86093580", "86093580"),
        ("ID 1153638521786093580", "11536385", "11536385"),
    ],
)
def test_make_snippet_segments_exacts(text, term, matched):
    snippet, segments = t.make_snippet(text, [term])
    _check_snippet(snippet, segments, [term])
    marks = [segment["text"] for segment in segments if segment["match"]]
    assert marks == [matched]
    assert t.fold(marks[0]) == t.fold(term)


def test_make_snippet_plusieurs_termes_et_fusion():
    snippet, segments = t.make_snippet("Lien de phishing envoyé, phishing encore", ["phishing", "lien"])
    _check_snippet(snippet, segments, ["phishing", "lien"])
    assert [s["text"] for s in segments if s["match"]] == ["Lien", "phishing", "phishing"]

    snippet, segments = t.make_snippet("spamspam ok", ["spam"])
    assert segments == [{"text": "spamspam", "match": True}, {"text": " ok", "match": False}]

    snippet, segments = t.make_snippet("aaa", ["aa"])
    assert segments == [{"text": "aaa", "match": True}]


def test_make_snippet_texte_long_centre_sur_la_correspondance():
    text = ("mot " * 100) + "phishing " + ("autre " * 100)
    snippet, segments = t.make_snippet(text, ["phishing"])
    _check_snippet(snippet, segments, ["phishing"])
    assert snippet.startswith(t.ELLIPSIS) and snippet.endswith(t.ELLIPSIS)
    assert [s["text"] for s in segments if s["match"]] == ["phishing"]
    body = snippet.strip(t.ELLIPSIS)
    assert body == body.strip()
    assert body.split(" ")[0] == "mot" and body.split(" ")[-1] == "autre"  # mots entiers


def test_make_snippet_correspondance_en_debut_et_en_fin():
    text = "phishing " + ("autre " * 60)
    snippet, segments = t.make_snippet(text, ["phishing"])
    _check_snippet(snippet, segments, ["phishing"])
    assert not snippet.startswith(t.ELLIPSIS) and snippet.endswith(t.ELLIPSIS)
    assert segments[0] == {"text": "phishing", "match": True}

    text = ("autre " * 60) + "fin phishing"
    snippet, segments = t.make_snippet(text, ["phishing"])
    _check_snippet(snippet, segments, ["phishing"])
    assert snippet.startswith(t.ELLIPSIS) and snippet.endswith("fin phishing")
    assert segments[-1] == {"text": "phishing", "match": True}


def test_make_snippet_sans_correspondance():
    assert t.make_snippet("Motif court", ["absent"]) == ("Motif court", [{"text": "Motif court", "match": False}])
    snippet, segments = t.make_snippet("mot " * 100, ["absent"])
    _check_snippet(snippet, segments, [])
    assert snippet.endswith(t.ELLIPSIS) and not snippet.startswith(t.ELLIPSIS)
    assert segments == [{"text": snippet, "match": False}]
    assert t.make_snippet("Motif", []) == ("Motif", [{"text": "Motif", "match": False}])
    assert t.make_snippet("Motif", ["", "   "]) == ("Motif", [{"text": "Motif", "match": False}])


def test_make_snippet_entrees_limites():
    assert t.make_snippet("", ["x"]) == ("", [])
    assert t.make_snippet(None, ["x"]) == ("", [])
    assert t.make_snippet("  \n ", ["x"]) == ("", [])
    snippet, segments = t.make_snippet("ligne 1\n\nligne   2 avec phishing", "phishing")
    assert snippet == "ligne 1 ligne 2 avec phishing"
    assert segments[-1] == {"text": "phishing", "match": True}


def test_make_snippet_largeur_personnalisee():
    text = "x" * 50 + " cible " + "y" * 50
    snippet, segments = t.make_snippet(text, ["cible"], width=40)
    _check_snippet(snippet, segments, ["cible"], width=40)
    assert any(s["match"] and s["text"] == "cible" for s in segments)


def test_make_snippet_ne_coupe_pas_un_accent_combinant():
    text = "é" * 200 + " cible"
    snippet, segments = t.make_snippet(text, ["cible"])
    _check_snippet(snippet, segments, ["cible"])
    body = snippet.lstrip(t.ELLIPSIS)
    assert body[0] == "e"  # jamais un accent combinant orphelin en tête


def test_make_snippet_invariants_aleatoires():
    rng = random.Random(7)
    alphabet = list("abcdeéèsß ") + ["Œ", "œ", "🔥", "👨‍👩", "é", "\n"]
    for _ in range(400):
        text = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 260)))
        folded = t.fold(text)
        terms = []
        if folded and rng.random() < 0.8:
            start = rng.randrange(len(folded))
            terms.append(folded[start:start + rng.randint(1, 6)].strip())
        terms.append(rng.choice(["e", "ss", "oe", "spam", ""]))
        width = rng.choice([20, 60, 160])
        snippet, segments = t.make_snippet(text, terms, width=width)
        _check_snippet(snippet, segments, terms, width=width)


def test_make_snippet_rapide_sur_texte_long():
    text = ("Récidive : propos humiliants répétés envers luna.matcha. " * 400)[: t.CONTENT_TEXT_MAX_LENGTH]
    started = time.perf_counter()
    for _ in range(20):
        snippet, segments = t.make_snippet(text, ["humiliants", "luna", "e"])
    assert time.perf_counter() - started < 5
    _check_snippet(snippet, segments, ["humiliants", "luna", "e"])


# --- format du contenu -------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ("[]", "blocknote"),
        (' [ {"type": "paragraph"} ] ', "blocknote"),
        (json.dumps([_para(_text("Bonjour"))]), "blocknote"),
        ([{"type": "paragraph"}], "blocknote"),
        ("[1,2]", "text"),
        ('["a"]', "text"),
        ('[{"type": 1}]', "text"),
        ('[{"type": "paragraph"}, 3]', "text"),
        ('{"type": "paragraph"}', "text"),
        ('[{"type": "paragraph", "props": {"x": NaN}}]', "text"),
        ("[{\"type\": \"paragraph\"", "text"),
        ("<p>Bonjour</p>", "html"),
        ("Texte <b>gras</b>", "html"),
        ("3 < 5 et 6 > 2", "text"),
        ("Bonjour", "text"),
        ("", "text"),
        (None, "text"),
        (42, "text"),
    ],
)
def test_detect_content_format(content, expected):
    assert t.detect_content_format(content) == expected


def test_parse_blocks():
    assert t.parse_blocks("[]") == []
    assert t.parse_blocks('[{"type":"paragraph"}]') == [{"type": "paragraph"}]
    assert t.parse_blocks("[1,2]") is None
    assert t.parse_blocks("") is None
    assert t.parse_blocks(None) is None
    assert t.parse_blocks("[" * 100_000 + "]" * 100_000) is None  # imbrication excessive : pas d'exception


def test_formats_lineaires_sur_entree_hostile():
    started = time.perf_counter()
    assert t.detect_content_format("<a" * 100_000) == "text"
    assert t.content_to_text("<a" * 100_000) == ("<a" * 100_000)[: t.CONTENT_TEXT_MAX_LENGTH]
    assert t.content_to_text("<script>" * 25_000 + "<p>x</p>") == ""
    assert t.content_to_text("<p>a</p>" + "<!--" * 50_000) == "a"
    assert time.perf_counter() - started < 3


# --- assainissement BlockNote -----------------------------------------------------------------

@pytest.mark.parametrize(
    "href",
    [
        "javascript:alert(1)",
        " JaVaScRiPt:alert(1)",
        "java\tscript:alert(1)",
        "java\nscript:alert(1)",
        "\x01javascript:alert(1)",
        "java​script:alert(1)",
        "data:text/html,<script>alert(1)</script>",
        "vbscript:msgbox(1)",
        "/casier/relatif",
        "//evil.example/x",
        "",
        None,
        42,
    ],
)
def test_sanitize_lien_refuse_garde_le_texte(href):
    blocks = [_para(_text("Avant "), _link(href, _text("clic", bold=True)), _text(" après"))]
    clean = t.sanitize_blocknote(blocks)
    assert clean[0]["content"] == [_text("Avant "), _text("clic", bold=True), _text(" après")]


@pytest.mark.parametrize(
    "href",
    ["https://loasis.example/regles", "http://exemple.fr", "mailto:staff@example.org", "  HTTPS://exemple.fr  "],
)
def test_sanitize_lien_autorise(href):
    clean = t.sanitize_blocknote([_para(_link(href, _text("lien")))])
    link = clean[0]["content"][0]
    assert link["type"] == "link"
    assert link["href"] == href.strip()
    assert link["content"] == [_text("lien")]


def test_sanitize_liens_imbriques_et_contenu_chaine():
    blocks = [
        _para(
            {"type": "link", "href": "https://ok.example", "content": [
                _text("a"), {"type": "link", "href": "https://autre.example", "content": "b"}]},
            {"type": "link", "href": "javascript:x", "content": "texte brut"},
        )
    ]
    clean = t.sanitize_blocknote(blocks)
    assert clean[0]["content"] == [
        {"type": "link", "href": "https://ok.example", "content": [_text("a"), _text("b")]},
        _text("texte brut"),
    ]


@pytest.mark.parametrize("block_type", ["image", "video", "audio", "file"])
@pytest.mark.parametrize(
    "url",
    [
        "https://tracker.example/p.gif",
        "http://api.loasis.app/api/staff/meetings/images/a.png",
        "https://api.loasis.app.evil.example/api/staff/meetings/images/a.png",
        "https://evil.example/api/staff/meetings/images/a.png",
        "/api/staff/meetings/images/a.png?x=1",
        "/api/staff/meetings/images/a.png\nhttps://evil.example",
        "/api/staff/meetings/images/",
        "/api/staff/meetings/images/" + "a" * 201,
        "data:image/png;base64,iVBORw0KGgo=",
        "//tracker.example/p.gif",
    ],
)
def test_sanitize_media_externe_remplace(block_type, url):
    child = _para(_text("enfant"))
    block = {"id": "b1", "type": block_type, "props": {"url": url, "caption": "légende"}, "children": [child]}
    clean = t.sanitize_blocknote([block])
    assert clean == [
        {
            "id": "b1",
            "type": "paragraph",
            "content": [_text(f"Média externe non affiché : {url.strip()[:200]}")],
            "children": [child],
        }
    ]


@pytest.mark.parametrize(
    "url",
    [
        "/api/staff/meetings/images/a.png",
        "https://api.loasis.app/api/staff/meetings/images/a.png",
        "/api/staff/meetings/images/2026-10_capture-1.JPEG",
        "/api/staff/meetings/images/" + "a" * 200,
    ],
)
def test_sanitize_media_iris_garde(url):
    block = _image(url, caption="Capture", previewWidth=512)
    assert t.sanitize_blocknote([block]) == [block]


def test_sanitize_media_cas_limites():
    padded = _image("  /api/staff/meetings/images/a.png\n")
    assert t.sanitize_blocknote([padded])[0]["props"]["url"] == "/api/staff/meetings/images/a.png"
    for empty in [_image(""), _image("   "), {"type": "image", "props": {}}, {"type": "file"}]:
        assert t.sanitize_blocknote([empty]) == [empty]
    weird = {"type": "image", "props": {"url": 12345}}
    assert t.sanitize_blocknote([weird])[0]["content"] == [_text("Média externe non affiché : 12345")]
    long_url = "https://tracker.example/" + "x" * 500
    text = t.sanitize_blocknote([_image(long_url)])[0]["content"][0]["text"]
    assert text == "Média externe non affiché : " + long_url[:200]


def test_sanitize_profondeur_limitee_a_20():
    clean = t.sanitize_blocknote(_nested(25))
    assert _depth(_nested(25)) == 25
    assert _depth(clean) == 20
    assert t.sanitize_blocknote(_nested(20)) == _nested(20)
    assert t.blocknote_to_text(clean).splitlines() == [f"niveau {n}" for n in range(1, 21)]


def test_sanitize_elements_non_objets_et_cles_inconnues():
    blocks = [
        {
            "id": "p1",
            "type": "paragraph",
            "props": {"textColor": "red"},
            "content": [_text("a"), "brut", 3, None, ["x"], _text("b")],
            "children": [_para(_text("c")), "x", 1, {"pas": "de type"}, {"type": 7}],
            "extension": {"cle": "conservée"},
        },
        {"type": "heading", "props": {"level": 2}, "content": "titre en chaîne", "children": "pas une liste"},
    ]
    clean = t.sanitize_blocknote(blocks)
    assert clean[0]["content"] == [_text("a"), _text("b")]
    assert clean[0]["children"] == [_para(_text("c"))]
    assert clean[0]["extension"] == {"cle": "conservée"}
    assert clean[0]["props"] == {"textColor": "red"}
    assert clean[1]["content"] == "titre en chaîne"
    assert clean[1]["children"] == []


def test_sanitize_tableaux():
    table_v023 = {
        "type": "table",
        "content": {
            "type": "tableContent",
            "columnWidths": [None, None],
            "rows": [
                {"cells": [[_text("Nom")], [_link("javascript:x", _text("piège"))]]},
                {"cells": [[_link("https://ok.example", _text("ok"))], "cellule brute"]},
                "ligne invalide",
                {"cells": "pas une liste"},
            ],
        },
        "children": [],
    }
    table_cells = {
        "type": "table",
        "content": {
            "type": "tableContent",
            "rows": [{"cells": [{"type": "tableCell", "props": {"colspan": 1},
                                  "content": [_link("javascript:y", _text("lien"))]}, 5]}],
        },
    }
    clean = t.sanitize_blocknote([table_v023, table_cells])
    rows = clean[0]["content"]["rows"]
    assert clean[0]["content"]["columnWidths"] == [None, None]
    assert rows[0]["cells"] == [[_text("Nom")], [_text("piège")]]
    assert rows[1]["cells"][0][0]["href"] == "https://ok.example"
    assert rows[1]["cells"][1] == "cellule brute"
    assert rows[2] == {"cells": []}
    assert len(rows) == 3
    assert clean[1]["content"]["rows"][0]["cells"] == [
        {"type": "tableCell", "props": {"colspan": 1}, "content": [_text("lien")]}, []]


def test_sanitize_entrees_non_conformes():
    for value in [None, "[]", {"type": "paragraph"}, 42, "texte"]:
        assert t.sanitize_blocknote(value) == []
    assert t.sanitize_blocknote([]) == []
    assert t.sanitize_blocknote([1, "a", None]) == []


def test_sanitize_pur_et_idempotent():
    blocks = [
        _para(_text("x"), _link("javascript:alert(1)", _text("y")), children=[_image("https://t.example/a.gif")]),
        _image("/api/staff/meetings/images/a.png"),
        {"type": "table", "content": {"type": "tableContent", "rows": [{"cells": [[_link("data:x", _text("z"))]]}]}},
    ]
    original = copy.deepcopy(blocks)
    once = t.sanitize_blocknote(blocks)
    assert blocks == original
    assert t.sanitize_blocknote(once) == once
    assert t.sanitize_blocknote(json.loads(json.dumps(once))) == once


# --- texte extrait ----------------------------------------------------------------------------

FICHE_BLOCKS = [
    {"id": "h", "type": "heading", "props": {"level": 2}, "content": [_text("Contexte")], "children": []},
    _para(_text("Messages privés "), _text("insistants", bold=True), _text(" envers les nouveaux.")),
    _para(),
    {"type": "bulletListItem", "content": [_text("Premier point")], "children": [
        {"type": "numberedListItem", "content": [_text("Sous-point")], "children": []}]},
    {"type": "checkListItem", "props": {"checked": True}, "content": [_text("Vérifié")], "children": []},
    _para(_text("Voir "), _link("https://discord.com/channels/1/2/3", _text("le message")), _text(".")),
    {"type": "table", "content": {"type": "tableContent", "rows": [
        {"cells": [[_text("Date")], [_text("Fait")]]},
        {"cells": [[_text("23/10")], {"type": "tableCell", "content": [_text("MP insistant")]}]},
        {"cells": [[], []]},
    ]}, "children": []},
    _image("/api/staff/meetings/images/capture.png", caption="Capture du salon", name="capture.png"),
    {"type": "file", "props": {"url": "/api/staff/meetings/images/preuve.pdf", "name": "preuve.pdf"}},
    {"type": "codeBlock", "props": {"language": "text"}, "content": [_text("ligne 1\nligne 2")]},
]

FICHE_TEXT = "\n".join(
    [
        "Contexte",
        "Messages privés insistants envers les nouveaux.",
        "Premier point",
        "Sous-point",
        "Vérifié",
        "Voir le message.",
        "Date | Fait",
        "23/10 | MP insistant",
        "Capture du salon — capture.png",
        "preuve.pdf",
        "ligne 1\nligne 2",
    ]
)


def test_blocknote_to_text():
    assert t.blocknote_to_text(FICHE_BLOCKS) == FICHE_TEXT
    assert t.blocknote_to_text(json.dumps(FICHE_BLOCKS)) == FICHE_TEXT


def test_blocknote_to_text_entrees_limites():
    assert t.blocknote_to_text("[]") == ""
    assert t.blocknote_to_text("Texte brut") == ""
    assert t.blocknote_to_text(None) == ""
    assert t.blocknote_to_text([1, None, {"type": "paragraph", "content": [None, _text("ok")]}]) == "ok"
    assert t.blocknote_to_text([{"type": "paragraph", "content": "chaîne"}]) == "chaîne"
    deep = _nested(500)
    assert t.blocknote_to_text(deep).splitlines()[-1] == "niveau 20"
    huge = [_para(_text("x" * 1000)) for _ in range(30)]
    assert len(t.blocknote_to_text(huge)) == t.CONTENT_TEXT_MAX_LENGTH


def test_content_to_text_selon_le_format():
    assert t.content_to_text(json.dumps(FICHE_BLOCKS)) == FICHE_TEXT
    raw = json.dumps([_para(_link("javascript:alert(1)", _text("clic"))), _image("https://tracker.example/p.gif")])
    assert t.content_to_text(raw) == "clic\nMédia externe non affiché : https://tracker.example/p.gif"
    legacy_html = (
        "<h2>Contexte</h2><p>Bonjour&nbsp;<b>Éloïse</b> &amp; co</p><p>Ligne 2<br>Ligne 3</p>"
        "<ul><li>Point</li></ul><table><tr><td>A</td><td>B</td></tr></table>"
        "<script>alert(1)</script><style>p{}</style><!-- note --><p>3 &lt; 5</p>"
    )
    assert t.content_to_text(legacy_html) == "Contexte\nBonjour Éloïse & co\nLigne 2\nLigne 3\nPoint\nA B\n3 < 5"
    assert t.content_to_text("Ancienne fiche\n  en texte brut ") == "Ancienne fiche\n  en texte brut "
    assert t.content_to_text("[1,2]") == "[1,2]"
    assert t.content_to_text("") == ""
    assert t.content_to_text(None) == ""
    assert len(t.content_to_text("a" * 30_000)) == t.CONTENT_TEXT_MAX_LENGTH
    assert len(t.content_to_text("<p>" + "a" * 30_000 + "</p>")) == t.CONTENT_TEXT_MAX_LENGTH


# --- fiche vide et préparation ------------------------------------------------------------------

@pytest.mark.parametrize(
    "content",
    [
        '[{"type":"paragraph","content":[]}]',
        "[]",
        json.dumps([_para(_text("   ")), _para(children=[_para(_text("\n"))])]),
        json.dumps([_image("")]),
        json.dumps([_image("   ")]),
        "",
        "   \n ",
        "<p> </p><br>",
        None,
    ],
)
def test_is_fiche_empty_vrai(content):
    assert t.is_fiche_empty(content)


@pytest.mark.parametrize(
    "content",
    [
        json.dumps([_para(_text("Texte"))]),
        json.dumps([_image("/api/staff/meetings/images/x.png")]),
        json.dumps([_para(children=[_image("https://api.loasis.app/api/staff/meetings/images/x.png")])]),
        json.dumps([_image("https://tracker.example/p.gif")]),  # devient un paragraphe de texte
        json.dumps([{"type": "table", "content": {"type": "tableContent", "rows": [{"cells": [[_text("x")]]}]}}]),
        "Texte brut",
        "<p>Bonjour</p>",
        "[1,2]",
    ],
)
def test_is_fiche_empty_faux(content):
    assert not t.is_fiche_empty(content)


def test_prepare_fiche_content_blocknote():
    raw = json.dumps(
        [_para(_text("Élément "), _link(" JaVaScRiPt:alert(1)", _text("piège"))), _image("https://t.example/p.gif")],
        indent=2,
    )
    stored, content_format, text = t.prepare_fiche_content(raw)
    assert content_format == "blocknote"
    assert "javascript" not in stored.lower()
    assert "Élément" in stored  # ensure_ascii=False
    assert ", " not in stored and ": " not in stored.replace("affiché : ", "")  # JSON compact
    assert json.loads(stored) == t.sanitize_blocknote(json.loads(raw))
    assert text == "Élément piège\nMédia externe non affiché : https://t.example/p.gif"
    assert t.prepare_fiche_content(stored) == (stored, "blocknote", text)  # idempotent (lecture)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("[1,2]", ("[1,2]", "text", "[1,2]")),
        ("Texte brut", ("Texte brut", "text", "Texte brut")),
        ("<p>Bonjour <i>toi</i></p>", ("<p>Bonjour <i>toi</i></p>", "html", "Bonjour toi")),
        ("[]", ("[]", "blocknote", "")),
        ("", ("", "text", "")),
        (None, ("", "text", "")),
    ],
)
def test_prepare_fiche_content_autres_formats(raw, expected):
    assert t.prepare_fiche_content(raw) == expected


def test_prepare_fiche_content_profondeur_et_contenu_lu_directement_en_base():
    stored, content_format, _ = t.prepare_fiche_content(json.dumps(_nested(25)))
    assert content_format == "blocknote"
    assert _depth(json.loads(stored)) == 20
    stored_in_db = json.dumps([_para(_link("javascript:alert(document.cookie)", _text("voir")))])
    read_back, _, _ = t.prepare_fiche_content(stored_in_db)
    assert json.loads(read_back) == [_para(_text("voir"))]


# --- config.py --------------------------------------------------------------------------------

def test_config_type_mute_et_salons_de_moderation():
    assert config.VALID_SANCTION_TYPES == {"avertissement", "mute", "bannissement", "kick", "rappel_a_lordre"}
    assert config.parse_moderation_channels("mute:600000000000000005") == {600000000000000005: "mute"}
    raw = (
        "avertissement:111111111111111111, mute:555555555555555555,kick:222222222222222222,"
        "bannissement:333333333333333333,rappel_a_lordre:444444444444444444"
    )
    assert config.parse_moderation_channels(raw) == {
        111111111111111111: "avertissement",
        555555555555555555: "mute",
        222222222222222222: "kick",
        333333333333333333: "bannissement",
        444444444444444444: "rappel_a_lordre",
    }
    assert config.parse_moderation_channels(" MUTE : 600000000000000005 ") == {600000000000000005: "mute"}
    assert config.parse_moderation_channels("mute:abc,inconnu:123,,mute,unmute:600000000000000006") == {}


def test_config_lecture_des_entiers_et_booleens(monkeypatch):
    monkeypatch.setenv("IRIS_TEST_INT", " 2048 ")
    assert config._int_env("IRIS_TEST_INT", 10, minimum=1) == 2048
    monkeypatch.setenv("IRIS_TEST_INT", "dix")
    assert config._int_env("IRIS_TEST_INT", 10) == 10
    monkeypatch.setenv("IRIS_TEST_INT", "0")
    assert config._int_env("IRIS_TEST_INT", 10, minimum=1) == 10
    assert config._int_env("IRIS_TEST_INT", 10, minimum=0) == 0
    monkeypatch.setenv("IRIS_TEST_INT", "-5")
    assert config._int_env("IRIS_TEST_INT", 180, minimum=0) == 180
    assert config._int_env("IRIS_TEST_INT", 180) == -5  # comportement historique sans minimum
    monkeypatch.delenv("IRIS_TEST_INT")
    assert config._int_env("IRIS_TEST_INT", 7) == 7

    for raw, expected in [("1", True), (" TRUE ", True), ("yes", True), ("On", True),
                          ("false", False), ("0", False), ("non", False), ("", False)]:
        monkeypatch.setenv("IRIS_TEST_BOOL", raw)
        assert config._bool_env("IRIS_TEST_BOOL") is expected
    monkeypatch.setenv("IRIS_TEST_BOOL", "  ")
    assert config._bool_env("IRIS_TEST_BOOL", True) is True
    monkeypatch.delenv("IRIS_TEST_BOOL")
    assert config._bool_env("IRIS_TEST_BOOL") is False


CASIER_SETTINGS = (
    "CASIER_ATTACHMENT_MAX_BYTES",
    "CASIER_UPLOAD_MAX_BYTES",
    "AI_MODERATION_FLAG_TTL_DAYS",
    "AI_MODERATION_FLAG_SKIP_IDS",
    "AI_MODERATION_FLAG_STORE_REFUSAL_CONTENT",
)


def _config_values(extra_env: dict) -> dict:
    """Importe config.py dans un processus neuf (variables d'environnement maîtrisées)."""
    env = {key: value for key, value in os.environ.items() if key not in CASIER_SETTINGS}
    env.update(extra_env)
    script = (
        "import json, config\n"
        "print(json.dumps({name: sorted(value) if isinstance(value, frozenset) else value\n"
        f"    for name, value in ((n, getattr(config, n)) for n in {list(CASIER_SETTINGS)!r})}}))\n"
        "assert isinstance(config.AI_MODERATION_FLAG_SKIP_IDS, frozenset)\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script], cwd=BACKEND_DIR, env=env, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_config_reglages_casier_par_defaut():
    dotenv = BACKEND_DIR / ".env"
    if dotenv.exists() and any(name in dotenv.read_text(errors="ignore") for name in CASIER_SETTINGS):
        pytest.skip("backend/.env définit déjà des réglages du casier")
    assert _config_values({}) == {
        "CASIER_ATTACHMENT_MAX_BYTES": 25 * 1024 * 1024,
        "CASIER_UPLOAD_MAX_BYTES": 10 * 1024 * 1024,
        "AI_MODERATION_FLAG_TTL_DAYS": 180,
        "AI_MODERATION_FLAG_SKIP_IDS": [],
        "AI_MODERATION_FLAG_STORE_REFUSAL_CONTENT": False,
    }


def test_config_reglages_casier_surcharges():
    values = _config_values(
        {
            "CASIER_ATTACHMENT_MAX_BYTES": "1048576",
            "CASIER_UPLOAD_MAX_BYTES": "0",
            "AI_MODERATION_FLAG_TTL_DAYS": "0",
            "AI_MODERATION_FLAG_SKIP_IDS": " 700000000000000001, abc,700000000000000002,,../x",
            "AI_MODERATION_FLAG_STORE_REFUSAL_CONTENT": "True",
        }
    )
    assert values == {
        "CASIER_ATTACHMENT_MAX_BYTES": 1048576,
        "CASIER_UPLOAD_MAX_BYTES": 10 * 1024 * 1024,  # 0 : valeur invalide, défaut conservé
        "AI_MODERATION_FLAG_TTL_DAYS": 0,  # 0 = conservation illimitée
        "AI_MODERATION_FLAG_SKIP_IDS": ["700000000000000001", "700000000000000002"],
        "AI_MODERATION_FLAG_STORE_REFUSAL_CONTENT": True,
    }
    assert _config_values({"AI_MODERATION_FLAG_TTL_DAYS": "-1"})["AI_MODERATION_FLAG_TTL_DAYS"] == 180
