"""Lecture des logs OasisBot (services/casier_log_parser.py) : durées, modérateur, fichiers.

Fonctions pures : aucun accès réseau ni base. Les messages de test reprennent le format réel
d'OasisBot (Components V2, voir la docstring de services/moderation_bot.py) et passent par
`moderation_bot.raw_message_full_text`, comme dans le bot.
"""
import security_harness as h  # noqa: F401  (environnement de test, à importer en premier)

import re
from datetime import datetime, timedelta, timezone

import pytest

import config
from services import casier_log_parser as parser
from services import moderation_bot
from services.casier_log_parser import DurationInfo, extract_duration, extract_message_files, parse_duration_text

NOW = datetime(2026, 10, 25, 17, 25, tzinfo=timezone.utc)
NOW_TS = int(NOW.timestamp())
MOD_ID = "900000000000000001"
MEMBER_ID = "1153638521786093578"
ROLE_ID = "1200000000000000001"
MUTE_CHANNEL_ID = "600000000000000005"
ATTACHMENT_ROUTE_ID = re.compile(r"^(?:[0-9]{17,20}|[0-9a-f]{24})$")


def _cdn(attachment_id: str, filename: str, host: str = "cdn.discordapp.com",
         query: str = "?ex=6718&is=6716&hm=ab12") -> str:
    return f"https://{host}/attachments/{MUTE_CHANNEL_ID}/{attachment_id}/{filename}{query}"


def _attachment(attachment_id: str, filename: str, size=183224, content_type="image/png") -> dict:
    return {
        "id": attachment_id,
        "filename": filename,
        "size": size,
        "url": _cdn(attachment_id, filename),
        "proxy_url": _cdn(attachment_id, filename, host="media.discordapp.net", query=""),
        "content_type": content_type,
        "width": 1280,
        "height": 720,
    }


def _oasis_log(body: str, *, extra_components=(), attachments=None, embeds=None) -> dict:
    """Message OasisBot tel que renvoyé par l'API REST (Container + Text Display + Separator)."""
    return {
        "id": "1299887766554433200",
        "channel_id": MUTE_CHANNEL_ID,
        "flags": 32768,
        "content": "",
        "embeds": embeds or [],
        "attachments": attachments or [],
        "components": [
            {
                "type": 17,
                "components": [
                    {"type": 10, "content": body},
                    *extra_components,
                    {"type": 14},
                    {"type": 10, "content": "-# Action manuelle via commande"},
                ],
            }
        ],
    }


def _mute_body(reason: str = "Propos humiliants répétés envers un membre.", tail: str = "",
               head_suffix: str = ".") -> str:
    return (
        f"<@{MOD_ID}> a mit <@{MEMBER_ID}> (`{MEMBER_ID}`) en <@&{ROLE_ID}>{head_suffix}\n"
        f"### Raison de l'ajout : \n```{reason}```{tail}"
    )


def _full_text(raw: dict) -> str:
    return moderation_bot.raw_message_full_text(raw)


def _duration_of(body: str, now: datetime = NOW) -> DurationInfo:
    return extract_duration(_full_text(_oasis_log(body)), now=now)


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat()


# --------------------------------------------------------------------------------------
# parse_duration_text
# --------------------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("10 minutes", ("10 min", 600)),
        ("10m", ("10 min", 600)),
        ("10 mn", ("10 min", 600)),
        ("30 sec", ("30 s", 30)),
        ("1h30", ("1 h 30", 5400)),
        ("1 h 30", ("1 h 30", 5400)),
        ("1h05", ("1 h 05", 3900)),
        ("2h 30min", ("2 h 30", 9000)),
        ("1.5h", ("1 h 30", 5400)),
        ("1,5 h", ("1 h 30", 5400)),
        ("1 h 30 s", ("1 h 30 s", 3630)),
        ("2 jours", ("2 jours", 172800)),
        ("48 h", ("2 jours", 172800)),
        ("7j", ("1 semaine", 604800)),
        ("1 semaine", ("1 semaine", 604800)),
        ("2 weeks", ("2 semaines", 1209600)),
        ("10 jours", ("10 jours", 864000)),
        ("3 mois", ("3 mois", 7776000)),
        ("1 an", ("1 an", 31536000)),
        ("2 years", ("2 ans", 63072000)),
        ("une heure", ("1 h", 3600)),
        ("deux jours", ("2 jours", 172800)),
        ("**1 h**", ("1 h", 3600)),
        ("`7 jours`", ("1 semaine", 604800)),
        ("||10 minutes||", ("10 min", 600)),
        ("1 jour et 12 heures", ("1 jour 12 h", 129600)),
        # Formes compactes : un jeton peut suivre directement une unité.
        ("1h30m", ("1 h 30", 5400)),
        ("2h30min", ("2 h 30", 9000)),
        ("1j12h", ("1 jour 12 h", 129600)),
        ("10min30s", ("10 min 30 s", 630)),
        ("1h, 30min", ("1 h 30", 5400)),
        ("1 h + 30 min", ("1 h 30", 5400)),
        # Demis et journées.
        ("1 heure et demie", ("1 h 30", 5400)),
        ("2 jours et demi", ("2 jours 12 h", 216000)),
        ("une demi-heure", ("30 min", 1800)),
        ("une demi heure", ("30 min", 1800)),
        ("une journée", ("1 jour", 86400)),
        # Heure ou date de fin retirée avant la lecture des jetons.
        ("1 h (jusqu'à 18h30)", ("1 h", 3600)),
        ("2 jours, jusqu'au 27/10", ("2 jours", 172800)),
    ],
)
def test_parse_duration_text_recognized(text, expected):
    assert parse_duration_text(text) == expected


@pytest.mark.parametrize("text", ["permanent", "Permanente", "Définitif", "définitivement", "À vie",
                                  "indéfiniment", "ILLIMITÉE", "999999 ans", "2000 years"])
def test_parse_duration_text_permanent(text):
    assert parse_duration_text(text) == ("Permanent", None)


@pytest.mark.parametrize(
    ("text", "label"),
    [
        ("jusqu'à nouvel ordre", "jusqu'à nouvel ordre"),
        ("  jusqu'à   la fin de l'event ", "jusqu'à la fin de l'event"),
        ("à 18h30", "à 18h30"),               # heure de fin, pas une durée de 18 h 30
        ("jusqu’à 20 h", "jusqu’à 20 h"),
        ("jusqu'au 25/10", "jusqu'au 25/10"),
        ("jusqu'au 25/10/2026", "jusqu'au 25/10/2026"),
        ("vers 21:00", "vers 21:00"),
        ("24-48h", "24-48h"),                 # fourchette : jamais lue « 48 h »
        ("dix-huit heures", "dix-huit heures"),  # jamais lu « huit heures »
        ("en même temps", "en même temps"),
        ("0 min", "0 min"),
    ],
)
def test_parse_duration_text_free_text_is_kept(text, label):
    assert parse_duration_text(text) == (label, None)


@pytest.mark.parametrize("text", ["", "   ", "**", "``` ```", None, 42])
def test_parse_duration_text_empty(text):
    assert parse_duration_text(text) == (None, None)


def test_parse_duration_text_free_text_truncated_to_80():
    label, seconds = parse_duration_text("jusqu'à ce que " + "x" * 200)
    assert seconds is None
    assert len(label) == 80


@pytest.mark.parametrize(
    ("seconds", "label"),
    [(30, "30 s"), (90, "1 min 30 s"), (600, "10 min"), (3600, "1 h"), (3900, "1 h 05"), (5400, "1 h 30"),
     (86400, "1 jour"), (91800, "1 jour 1 h 30"), (604800, "1 semaine"), (864000, "10 jours"),
     (2592000, "1 mois"), (31536000, "1 an"), (400 * 86400, "400 jours"),
     (31536000 + 2592000 + 5 * 86400 + 5400, "1 an 1 mois 5 jours 1 h 30")],
)
def test_format_duration(seconds, label):
    assert parser.format_duration(seconds) == label


# --------------------------------------------------------------------------------------
# extract_duration
# --------------------------------------------------------------------------------------

def test_duration_from_labelled_heading_with_code_block():
    info = _duration_of(_mute_body(tail="\n### Durée : \n```1h30```"))

    assert info == DurationInfo("1 h 30", 5400, _iso(NOW + timedelta(seconds=5400)))


def test_duration_from_inline_labelled_field():
    info = _duration_of(_mute_body(tail="\nDurée : 2 jours"))

    assert info == DurationInfo("2 jours", 172800, _iso(NOW + timedelta(days=2)))


@pytest.mark.parametrize("line", ["**Durée :** 1h", "> Durée du mute : 1 heure", "-# Duration: 60 minutes",
                                  "Temps : 1 h", "### Durée : `1 h`"])
def test_duration_labelled_variants(line):
    assert _duration_of(_mute_body(tail="\n" + line)).seconds == 3600


def test_duration_pendant_outside_reason():
    info = _duration_of(_mute_body(head_suffix=" pendant 10 minutes."))

    assert info == DurationInfo("10 min", 600, _iso(NOW + timedelta(minutes=10)))


def test_duration_pour_in_action_line():
    assert _duration_of(_mute_body(head_suffix=" pour 1 h.")).label == "1 h"
    assert _duration_of(_mute_body(head_suffix=" pour une heure et demie suite à 3 spams en 5 min.")).seconds == 5400


def test_pour_without_leading_duration_is_ignored():
    # « pour » introduit souvent une cause : la durée doit suivre immédiatement.
    assert _duration_of(_mute_body(head_suffix=" pour spam répété 3 fois en 5 min.")) == DurationInfo(None, None, None)
    assert _duration_of(_mute_body(head_suffix=" pour une durée indéfinie.")) == DurationInfo(None, None, None)


@pytest.mark.parametrize(
    ("head_suffix", "expected"),
    [
        (" pendant 1 h pour spam de 5 min.", ("1 h", 3600)),            # seule la première durée compte
        (" pendant 10 minutes (définitif si récidive).", ("10 min", 600)),
        (" pendant 2h30min.", ("2 h 30", 9000)),
        (" durant 2 jours.", ("2 jours", 172800)),
        (" pendant une durée indéfinie.", ("Permanent", None)),
    ],
)
def test_duration_pendant_phrase(head_suffix, expected):
    info = _duration_of(_mute_body(head_suffix=head_suffix))

    assert (info.label, info.seconds) == expected
    assert info.expires_at == (_iso(NOW + timedelta(seconds=expected[1])) if expected[1] else None)


def test_plain_oasis_log_has_no_duration():
    # Format documenté dans moderation_bot.py : ni les snowflakes ni le pied de page ne sont des durées.
    for reason in ["Spam de liens en 5 min dans #général.", "Propos haineux (3 messages).", "1h30 de spam vocal"]:
        assert _duration_of(_mute_body(reason=reason)) == DurationInfo(None, None, None)


def test_duration_from_labelled_discord_timestamp():
    expires = NOW + timedelta(hours=1, seconds=2)  # log publié 2 s après la sanction
    info = _duration_of(_mute_body(tail=f"\n### Fin du mute : <t:{int(expires.timestamp())}:R>"))

    assert info.expires_at == _iso(expires)
    assert info.seconds == 3600
    assert info.label == "1 h"


def test_duration_from_bare_discord_timestamp():
    expires = NOW + timedelta(minutes=10)
    info = _duration_of(_mute_body(tail=f"\nExpire <t:{int(expires.timestamp())}:R>"))

    assert info == DurationInfo("10 min", 600, _iso(expires))


def test_discord_timestamp_wins_over_computed_end():
    expires = NOW + timedelta(hours=1, minutes=1)
    info = _duration_of(_mute_body(tail=f"\nDurée : 1 h\nFin : <t:{int(expires.timestamp())}:f>"))

    assert info == DurationInfo("1 h", 3600, _iso(expires))


def test_past_discord_timestamp_is_not_an_end():
    info = _duration_of(_mute_body(tail=f"\n-# Sanction appliquée <t:{NOW_TS - 5}:f>"))

    assert info == DurationInfo(None, None, None)


@pytest.mark.parametrize("stamp", ["<t:999999999999>", "<t:999999999999:R>"])
def test_absurd_discord_timestamp_is_ignored(stamp):
    assert _duration_of(_mute_body(tail=f"\nFin : {stamp}")) == DurationInfo(None, None, None)
    # Horodatage ignoré : on passe à « pendant … ».
    info = _duration_of(_mute_body(head_suffix=f" pendant 10 minutes {stamp}."))
    assert info.seconds == 600


def test_far_future_timestamp_is_permanent():
    far = int(datetime(2300, 1, 1, tzinfo=timezone.utc).timestamp())

    assert _duration_of(_mute_body(tail=f"\nFin : <t:{far}:D>")) == DurationInfo("Permanent", None, None)


def test_labelled_permanent_and_free_text():
    assert _duration_of(_mute_body(tail="\n### Durée : \n```Définitif```")) == DurationInfo("Permanent", None, None)
    assert _duration_of(_mute_body(tail="\nDurée : jusqu'à nouvel ordre")) == DurationInfo(
        "jusqu'à nouvel ordre", None, None
    )


def test_duration_written_in_reason_is_ignored():
    body = _mute_body(reason="Spam pendant 3 jours.\nDurée : 1 h\nFin : <t:%d:R>" % (NOW_TS + 3600))

    assert _duration_of(body) == DurationInfo(None, None, None)


def test_inline_reason_line_is_ignored():
    body = f"<@{MOD_ID}> a mit <@{MEMBER_ID}> (`{MEMBER_ID}`) en <@&{ROLE_ID}>.\nRaison : spam pendant 3 jours"

    assert _duration_of(body) == DurationInfo(None, None, None)


@pytest.mark.parametrize(
    "tail",
    ["\nEnfin, le membre a été prévenu.", "\nEn même temps, un ticket a été ouvert.", "\nTemps de réaction rapide",
     "\nFinalement : rien à signaler", "\n-# 3 membres concernés"],
)
def test_words_that_are_not_durations(tail):
    assert _duration_of(_mute_body(tail=tail)) == DurationInfo(None, None, None)


def test_extract_duration_never_raises_and_accepts_any_now():
    assert extract_duration("", now=NOW) == DurationInfo(None, None, None)
    assert extract_duration(None, now=NOW) == DurationInfo(None, None, None)
    assert extract_duration(12, now=NOW) == DurationInfo(None, None, None)
    # `now` naïf : considéré comme UTC ; absent : heure courante.
    naive = extract_duration("Durée : 1 h", now=datetime(2026, 10, 25, 17, 25))
    assert naive.expires_at == "2026-10-25T18:25:00+00:00"
    assert extract_duration("Durée : 1 h").seconds == 3600
    # Ancres et motifs piégeux, sans exception.
    for text in ["Durée :", "Durée : ```", "```", "<t:>", "<t:abc:R>", "pendant", "Durée : <t:1:R>" * 50]:
        extract_duration(text, now=NOW)


# --------------------------------------------------------------------------------------
# extract_moderator_id
# --------------------------------------------------------------------------------------

def test_moderator_from_oasis_format():
    text = _full_text(_oasis_log(_mute_body()))

    assert parser.extract_moderator_id(text, MEMBER_ID) == MOD_ID
    assert parser.extract_moderator_id(text, int(MEMBER_ID)) == MOD_ID


def test_moderator_nickname_mention_and_role_mention_ignored():
    text = f"<@&{ROLE_ID}> <@!{MOD_ID}> a mis <@{MEMBER_ID}> (`{MEMBER_ID}`) en <@&{ROLE_ID}>."

    assert parser.extract_moderator_id(text, MEMBER_ID) == MOD_ID


def test_only_member_mentioned_gives_none():
    text = f"<@&{ROLE_ID}> a mit <@{MEMBER_ID}> (`{MEMBER_ID}`) en <@&{ROLE_ID}>.\n### Raison de l'ajout : \n```spam```"

    assert parser.extract_moderator_id(text, MEMBER_ID) is None


def test_mention_in_reason_is_ignored():
    text = (
        f"Sanction : <@{MEMBER_ID}> (`{MEMBER_ID}`) a été mis en sourdine.\n"
        f"### Raison de l'ajout : \n```Insultes envers <@{MOD_ID}> en vocal.```"
    )

    assert parser.extract_moderator_id(text, MEMBER_ID) is None


def test_moderator_outside_action_line():
    text = f"<@{MEMBER_ID}> (`{MEMBER_ID}`) a été mis en sourdine par <@{MOD_ID}>."

    assert parser.extract_moderator_id(text, MEMBER_ID) == MOD_ID


def test_action_line_takes_precedence():
    other = "900000000000000777"
    text = f"-# Signalé par <@{other}>\n<@{MOD_ID}> a ajouté <@{MEMBER_ID}> (`{MEMBER_ID}`) en <@&{ROLE_ID}>."

    assert parser.extract_moderator_id(text, MEMBER_ID) == MOD_ID


@pytest.mark.parametrize("text", [None, 12, "", "aucune mention", "<@123>"])
def test_moderator_none_cases(text):
    assert parser.extract_moderator_id(text, MEMBER_ID) is None


# --------------------------------------------------------------------------------------
# extract_message_files
# --------------------------------------------------------------------------------------

def test_classic_attachment():
    raw = _oasis_log(_mute_body(), attachments=[_attachment("1299887766554433221", "capture-salon-general.png")])

    files = extract_message_files(raw, now=NOW)

    assert files == [{
        "id": "1299887766554433221",
        "origin": "discord",
        "filename": "capture-salon-general.png",
        "extension": "png",
        "content_type": "image/png",
        "size": 183224,
        "source_url": _cdn("1299887766554433221", "capture-salon-general.png"),
        "status": "pending",
        "error": None,
        "created_at": NOW.isoformat(),
        "stored_at": None,
        "uploaded_by": None,
        "deleted_at": None,
        "deleted_by": None,
    }]


def test_file_component_attachment_reference_is_resolved_and_merged():
    attachment = _attachment("1299887766554433221", "conversation.txt", size=None, content_type=None)
    raw = _oasis_log(
        _mute_body(),
        attachments=[attachment],
        extra_components=[{"type": 13, "file": {"url": "attachment://conversation.txt"}, "name": "conversation.txt",
                           "size": 2048, "spoiler": False}],
    )

    files = extract_message_files(raw, now=NOW)

    assert len(files) == 1
    assert files[0]["id"] == "1299887766554433221"
    assert files[0]["size"] == 2048  # complété depuis le composant Fichier
    assert files[0]["extension"] == "txt"
    assert files[0]["source_url"].startswith("https://cdn.discordapp.com/attachments/")


def test_file_component_alone_with_resolved_url():
    url = _cdn("1299887766554433230", "preuve.pdf")
    raw = _oasis_log(_mute_body(), extra_components=[
        {"type": 13, "file": {"url": url, "attachment_id": "1299887766554433230", "content_type": "application/pdf"},
         "name": "preuve.pdf", "size": 4096},
    ])

    files = extract_message_files(raw, now=NOW)

    assert [(f["id"], f["filename"], f["size"], f["content_type"]) for f in files] == [
        ("1299887766554433230", "preuve.pdf", 4096, "application/pdf")
    ]


def test_file_component_by_attachment_id_when_names_differ():
    attachment = _attachment("1299887766554433221", "capture_1.png")
    raw = _oasis_log(_mute_body(), attachments=[attachment], extra_components=[
        {"type": 13, "file": {"url": "attachment://capture 1.png", "attachment_id": "1299887766554433221"}},
    ])

    assert [f["id"] for f in extract_message_files(raw)] == ["1299887766554433221"]


def test_unresolvable_attachment_reference_is_skipped():
    raw = _oasis_log(_mute_body(), extra_components=[{"type": 13, "file": {"url": "attachment://absent.png"}}])

    assert extract_message_files(raw) == []


def test_media_gallery_items_and_proxy_duplicates():
    first = _cdn("1299887766554433241", "capture_1.png")
    second = _cdn("1299887766554433242", "capture_2.jpg")
    raw = _oasis_log(_mute_body(), extra_components=[
        {"type": 12, "items": [
            {"media": {"url": first, "proxy_url": first.replace("cdn.discordapp.com", "media.discordapp.net")},
             "description": "Capture 1"},
            {"media": {"url": second, "content_type": "image/jpeg"}, "spoiler": True},
            # même fichier via le proxy média (autre hôte, autre requête) : doublon
            {"media": {"url": _cdn("1299887766554433241", "capture_1.png", host="media.discordapp.net",
                                   query="?width=400&height=225")}},
        ]},
    ])

    files = extract_message_files(raw, now=NOW)

    assert [f["filename"] for f in files] == ["capture_1.png", "capture_2.jpg"]
    assert files[1]["content_type"] == "image/jpeg"
    for item in files:
        # Sans id de pièce jointe : sha1 du chemin CDN, stable d'une lecture à l'autre.
        assert re.fullmatch(r"[0-9a-f]{24}", item["id"])
    assert extract_message_files(raw)[0]["id"] == files[0]["id"]


def test_section_thumbnail_avatar_is_excluded_but_attachment_thumbnail_kept():
    avatar = "https://cdn.discordapp.com/avatars/1153638521786093578/a_1f2e3d4c5b6a.png?size=256"
    raw = _oasis_log(_mute_body(), extra_components=[
        {"type": 9, "components": [{"type": 10, "content": "Membre"}],
         "accessory": {"type": 11, "media": {"url": avatar}}},
        {"type": 9, "components": [{"type": 10, "content": "Preuve"}],
         "accessory": {"type": 11, "media": {"url": _cdn("1299887766554433251", "preuve.webp")}}},
    ])

    files = extract_message_files(raw)

    assert [f["filename"] for f in files] == ["preuve.webp"]


@pytest.mark.parametrize(
    "url",
    [
        "https://cdn.discordapp.com/avatars/1153638521786093578/abc.png",
        "https://cdn.discordapp.com/emojis/1200000000000000009.webp",
        "https://cdn.discordapp.com/banners/1/abc.png",
        "https://cdn.discordapp.com/ephemeral-attachments/1/2/x.png",
        "https://i.imgur.com/attachments/abc.png",
        "https://images-ext-1.discordapp.net/external/abc/https/example.org/x.png",
        "http://cdn.discordapp.com/attachments/1/2/x.png",
        "https://cdn.discordapp.com.evil.example/attachments/1/2/x.png",
        "https://user@evil.example/cdn.discordapp.com/attachments/1/2/x.png",
        "https://user@cdn.discordapp.com/attachments/1/2/x.png",
        "https://cdn.discordapp.com:8443/attachments/1/2/x.png",
        "https://cdn.discordapp.com/attachments/../avatars/1/x.png",
        "https://cdn.discordapp.com/attachments/1/%2e%2e/x.png",
        "javascript:alert(1)",
        "attachment://x.png",
        "",
        None,
        12,
    ],
)
def test_non_attachment_urls_are_excluded(url):
    raw = _oasis_log(_mute_body(), embeds=[{"image": {"url": url}, "thumbnail": {"url": url}}],
                     extra_components=[{"type": 12, "items": [{"media": {"url": url}}]}])

    assert extract_message_files(raw) == []


def test_embed_images_are_collected():
    attachment = _attachment("1299887766554433261", "ancienne-capture.gif", content_type="image/gif")
    raw = {
        "content": "",
        "attachments": [attachment],
        "embeds": [
            {"title": "Mute", "image": {"url": "attachment://ancienne-capture.gif"},
             "thumbnail": {"url": "https://cdn.discordapp.com/avatars/1/abc.png"}},
            {"image": {"url": _cdn("1299887766554433262", "log%20complet.txt"), "proxy_url": None}},
        ],
    }

    files = extract_message_files(raw)

    assert [(f["id"], f["filename"]) for f in files][0] == ("1299887766554433261", "ancienne-capture.gif")
    assert files[1]["filename"] == "log complet.txt"
    assert len(files) == 2


def test_more_than_ten_files_are_truncated_in_order():
    attachments = [_attachment(str(1299887766554433300 + i), f"capture_{i}.png") for i in range(12)]

    files = extract_message_files(_oasis_log(_mute_body(), attachments=attachments))

    assert len(files) == parser.MAX_LOG_FILES == 10
    assert [f["filename"] for f in files] == [f"capture_{i}.png" for i in range(10)]
    assert len(extract_message_files(_oasis_log(_mute_body(), attachments=attachments), limit=3)) == 3


def test_declared_size_over_limit_is_too_large(monkeypatch):
    monkeypatch.setattr(config, "CASIER_ATTACHMENT_MAX_BYTES", 10 * 1024 * 1024, raising=False)
    raw = _oasis_log(_mute_body(), attachments=[
        _attachment("1299887766554433271", "video.mp4", size=10 * 1024 * 1024 + 1, content_type="video/mp4"),
        _attachment("1299887766554433272", "capture.png", size=10 * 1024 * 1024),
    ])

    files = extract_message_files(raw)

    assert files[0]["status"] == "too_large"
    assert files[0]["error"] == "Fichier trop volumineux (max 10 Mo)."
    assert files[1]["status"] == "pending"
    assert files[1]["error"] is None
    # Limite explicite prioritaire sur la configuration.
    assert extract_message_files(raw, max_bytes=100)[1]["status"] == "too_large"


def test_default_limit_is_25_mb(monkeypatch):
    monkeypatch.delattr(config, "CASIER_ATTACHMENT_MAX_BYTES", raising=False)
    raw = _oasis_log(_mute_body(), attachments=[
        _attachment("1299887766554433281", "a.png", size=25 * 1024 * 1024),
        _attachment("1299887766554433282", "b.png", size=25 * 1024 * 1024 + 1),
    ])

    assert [f["status"] for f in extract_message_files(raw)] == ["pending", "too_large"]


def test_size_learned_from_duplicate_can_mark_too_large():
    attachment = _attachment("1299887766554433291", "enregistrement.ogg", size=None, content_type="audio/ogg")
    raw = _oasis_log(_mute_body(), attachments=[attachment], extra_components=[
        {"type": 13, "file": {"url": "attachment://enregistrement.ogg"}, "size": 400},
    ])

    files = extract_message_files(raw, max_bytes=100)

    assert files[0]["size"] == 400
    assert files[0]["status"] == "too_large"


@pytest.mark.parametrize(
    ("filename", "expected_name", "expected_extension"),
    [
        ("../../etc/passwd", "passwd", "bin"),
        ("..\\..\\boot.ini", "boot.ini", "ini"),
        ("capture\r\nSet-Cookie: x.png", "captureSet-Cookie: x.png", "png"),
        ("facture‮gnp.exe", "facturegnp.exe", "exe"),
        ("archive.tar.gz", "archive.tar.gz", "gz"),
        ("SCREEN.PNG", "SCREEN.PNG", "png"),
        ("note.ph%00p", "note.ph%00p", "bin"),
        ("   ", "x.png", "png"),  # nom vide : celui de l'URL CDN
    ],
)
def test_filenames_are_cleaned(filename, expected_name, expected_extension):
    attachment = _attachment("1299887766554433301", "x.png")
    attachment["filename"] = filename
    files = extract_message_files(_oasis_log(_mute_body(), attachments=[attachment]))

    assert files[0]["filename"] == expected_name
    assert files[0]["extension"] == expected_extension


def test_long_filename_keeps_extension():
    name = parser.clean_filename("a" * 300 + ".png")

    assert len(name) == 200
    assert name.endswith(".png")
    assert parser.clean_filename("b" * 300) == "b" * 200
    assert parser.clean_filename(None) == "fichier"
    assert parser.clean_filename(" \r\n\u200b ") == "fichier"


def test_invalid_attachment_id_falls_back_to_path_hash():
    attachment = _attachment("../../x", "x.png")
    attachment["url"] = _cdn("1299887766554433311", "x.png")

    files = extract_message_files(_oasis_log(_mute_body(), attachments=[attachment]))

    assert re.fullmatch(r"[0-9a-f]{24}", files[0]["id"])


@pytest.mark.parametrize("size", ["183224", True, -5, 1.5, None])
def test_invalid_declared_sizes_are_ignored(size):
    files = extract_message_files(_oasis_log(_mute_body(), attachments=[_attachment("1299887766554433321", "x.png",
                                                                                    size=size)]))

    assert files[0]["size"] is None
    assert files[0]["status"] == "pending"


def test_malformed_messages_never_raise():
    assert extract_message_files(None) == []
    assert extract_message_files("message") == []
    assert extract_message_files({}) == []
    assert extract_message_files({"attachments": 3, "components": "x", "embeds": {"image": 1}}) == []
    junk = {
        "attachments": [None, 1, "x", {"id": None}, {"url": 5}],
        "components": [None, 1, {"type": 13}, {"type": 13, "file": "x"}, {"type": 12, "items": [None, {"media": 3}]},
                       {"type": 11, "media": None}, {"type": 9, "accessory": "x", "components": {"a": 1}}],
        "embeds": [None, {"image": "x"}, {"thumbnail": {"url": None}}],
    }
    assert extract_message_files(junk) == []


def test_deep_and_cyclic_component_trees_terminate():
    url = _cdn("1299887766554433331", "profond.png")
    node = {"type": 13, "file": {"url": url}}
    for _ in range(200):
        node = {"type": 17, "components": [node]}
    assert extract_message_files({"components": [node]}) == []  # au-delà de la profondeur bornée

    shallow = {"type": 17, "components": [{"type": 13, "file": {"url": url}}]}
    shallow["components"].append(shallow)  # cycle
    files = extract_message_files({"components": [shallow]})
    assert [f["filename"] for f in files] == ["profond.png"]


def test_all_ids_match_attachment_route_pattern():
    raw = _oasis_log(
        _mute_body(),
        attachments=[_attachment("1299887766554433341", "a.png")],
        extra_components=[{"type": 12, "items": [{"media": {"url": _cdn("1299887766554433342", "b.png")}}]}],
        embeds=[{"image": {"url": _cdn("1299887766554433343", "c.png")}}],
    )

    files = extract_message_files(raw)

    assert len(files) == 3
    assert all(ATTACHMENT_ROUTE_ID.fullmatch(item["id"]) for item in files)


# --------------------------------------------------------------------------------------
# Message OasisBot complet (comme dans moderation_bot.handle_sanction_log_message)
# --------------------------------------------------------------------------------------

def test_full_oasis_mute_log():
    expires = NOW + timedelta(hours=1)
    attachment = _attachment("1299887766554433221", "capture-salon-general.png")
    raw = _oasis_log(
        _mute_body(
            reason="Récidive : propos humiliants envers <@1153638521786093579> pendant 3 jours.",
            tail=f"\n### Durée : \n```1 h```\n### Fin : <t:{int(expires.timestamp())}:R>",
        ),
        attachments=[attachment],
        extra_components=[
            {"type": 12, "items": [{"media": {"url": "attachment://capture-salon-general.png"}}]},
            {"type": 9, "components": [{"type": 10, "content": "Profil"}],
             "accessory": {"type": 11, "media": {"url": "https://cdn.discordapp.com/avatars/1/abc.png"}}},
        ],
    )
    full_text = _full_text(raw)

    assert moderation_bot.extract_discord_id(full_text) == MEMBER_ID
    assert extract_duration(full_text, now=NOW) == DurationInfo("1 h", 3600, _iso(expires))
    assert parser.extract_moderator_id(full_text, MEMBER_ID) == MOD_ID
    files = extract_message_files(raw, now=NOW)
    assert [(f["id"], f["status"]) for f in files] == [("1299887766554433221", "pending")]


def test_oasis_log_with_file_component_by_attachment_id():
    # Forme renvoyée par l'API REST pour un composant Fichier : `attachment://` + `attachment_id` résolus.
    staff_id = "400000000000000003"
    member_id = "1153638521786093582"
    attachment_id = "1299887766554433201"
    raw = {
        "id": "1299887766554433200",
        "channel_id": MUTE_CHANNEL_ID,
        "flags": 32768,
        "content": "",
        "embeds": [],
        "attachments": [_attachment(attachment_id, "preuve-log.png", size=4096)],
        "components": [{
            "type": 17,
            "components": [
                {"type": 10, "content": f"<@{staff_id}> a mit <@{member_id}> (`{member_id}`) en <@&3>.\n"
                                        "### Raison de l'ajout : \n```démo aperçu```"},
                {"type": 13, "file": {"url": "attachment://preuve-log.png", "attachment_id": attachment_id}},
            ],
        }],
    }
    full_text = _full_text(raw)

    assert moderation_bot.extract_discord_id(full_text) == member_id
    assert parser.extract_moderator_id(full_text, member_id) == staff_id
    assert extract_duration(full_text, now=NOW) == DurationInfo(None, None, None)
    files = extract_message_files(raw, now=NOW)
    assert [(f["id"], f["filename"], f["size"], f["status"]) for f in files] == [
        (attachment_id, "preuve-log.png", 4096, "pending")
    ]


def test_legacy_embed_ban_log():
    # Ancien format (embed) : la durée est dans un champ, le modérateur dans la description.
    raw = {
        "content": "",
        "components": [],
        "attachments": [],
        "embeds": [{
            "title": "Bannissement",
            "description": f"<@{MOD_ID}> a mis <@{MEMBER_ID}> (`{MEMBER_ID}`) en <@&{ROLE_ID}>.",
            "fields": [{"name": "Raison", "value": "```Arnaque aux cartes cadeaux.```"},
                       {"name": "Durée :", "value": "Définitif"}],
            "thumbnail": {"url": f"https://cdn.discordapp.com/avatars/{MEMBER_ID}/abc.png"},
            "image": {"url": _cdn("1299887766554433401", "preuve.jpg")},
            "footer": {"text": "OasisBot"},
        }],
    }
    full_text = _full_text(raw)

    assert parser.extract_moderator_id(full_text, MEMBER_ID) == MOD_ID
    assert extract_duration(full_text, now=NOW) == DurationInfo("Permanent", None, None)
    assert [f["filename"] for f in extract_message_files(raw)] == ["preuve.jpg"]


def test_local_patterns_match_moderation_bot():
    # Copies locales : le motif et le verbe d'ajout doivent rester alignés sur ceux du bot.
    assert parser.REASON_CODEBLOCK_PATTERN.pattern == moderation_bot.REASON_CODEBLOCK_PATTERN.pattern
    assert parser.REASON_CODEBLOCK_PATTERN.flags == moderation_bot.REASON_CODEBLOCK_PATTERN.flags
    assert parser.ADD_VERB_PATTERN.pattern == moderation_bot.ADD_VERB_PATTERN.pattern
