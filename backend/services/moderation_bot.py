"""
Bot Discord (Gateway) qui écoute en permanence les salons de modération
configurés, détecte un ID Discord dans le contenu du message, et
crée/alimente automatiquement le casier correspondant.

Le TYPE de sanction est déterminé par le SALON d'où provient le message
(voir DISCORD_MODERATION_CHANNEL_TYPES dans config.py).

Format réel observé (OasisBot, message Components V2, confirmé via
l'API brute) :

    {
      "flags": 32768,   # IS_COMPONENTS_V2
      "content": "",
      "embeds": [],
      "components": [
        {
          "type": 17,   # Container
          "components": [
            {
              "type": 10,   # Text Display
              "content": "<@MOD_ID> a mit <@MEMBER_ID> (`MEMBER_ID`) en <@&ROLE_ID>.\n"
                         "### Raison de l'ajout : \n"
                         "```texte de la raison```"
            },
            { "type": 14 },  # Separator
            { "type": 10, "content": "-# Action manuelle via commande" }
          ]
        }
      ]
    }

Tout le texte utile est concentré dans UN seul Text Display :
  - l'ID du membre sanctionné, entre parenthèses ET entre backticks :
    "(`1153638521786093578`)"
  - la raison, dans un bloc de code ``` ``` juste après le libellé
    "Raison de l'ajout".
"""

import logging
import re

import discord
import httpx

from config import DISCORD_BOT_TOKEN, DISCORD_MODERATION_CHANNEL_TYPES
from services.casier_service import add_sanction

logger = logging.getLogger("moderation_bot")

DISCORD_API_BASE = "https://discord.com/api/v10"

# ID entre parenthèses, avec ou sans backticks autour : "(`123...`)" ou "(123...)"
PAREN_ID_PATTERN = re.compile(r"\(\s*`?(\d{17,20})`?\s*\)")

# Segment "id: ..." explicite (repli si un autre bot utilise ce format)
LABELLED_ID_PATTERN = re.compile(r"\bid\b\s*[:\-]?\s*<?@?!?(\d{17,20})>?", re.IGNORECASE)

# Mention brute <@123...> (dernier repli)
USER_MENTION_PATTERN = re.compile(r"<@!?(\d{17,20})>")

# Raison dans un bloc de code juste après le libellé (format OasisBot exact)
REASON_CODEBLOCK_PATTERN = re.compile(
    r"(?:raison|motif|reason)[^\n]*\n?```(.*?)```",
    re.IGNORECASE | re.DOTALL,
)

# Repli si jamais pas de bloc de code : tout ce qui suit le libellé
REASON_PLAIN_PATTERN = re.compile(
    r"(?:raison|motif|reason)[^\n:]*[:\-]?\s*\n?(.+)",
    re.IGNORECASE | re.DOTALL,
)

REMOVE_VERB_PATTERN = re.compile(r"\b(a\s+retir[ée]|a\s+enlev[ée])\b", re.IGNORECASE)
ADD_VERB_PATTERN = re.compile(r"\b(a\s+mit|a\s+mis|a\s+ajout[ée])\b", re.IGNORECASE)

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

moderation_client = discord.Client(intents=intents)


async def fetch_raw_message(channel_id: int, message_id: int) -> dict | None:
    """Récupère le JSON brut du message via l'API REST."""
    url = f"{DISCORD_API_BASE}/channels/{channel_id}/messages/{message_id}"
    headers = {"Authorization": f"Bot {DISCORD_BOT_TOKEN}"}

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(url, headers=headers)

    if response.is_error:
        logger.warning(
            "Impossible de récupérer le message brut %s/%s (%s).",
            channel_id,
            message_id,
            response.status_code,
        )
        return None

    return response.json()


def components_to_text(components: list[dict]) -> str:
    """Aplatit récursivement l'arborescence de components en texte exploitable."""
    parts: list[str] = []

    def walk(items: list[dict]) -> None:
        for item in items or []:
            content = (item.get("content") or "").strip()
            if content:
                parts.append(content)

            label = (item.get("label") or "").strip()
            if label:
                parts.append(label)

            placeholder = (item.get("placeholder") or "").strip()
            if placeholder:
                parts.append(placeholder)

            for option in item.get("options", []) or []:
                option_label = (option.get("label") or "").strip()
                option_desc = (option.get("description") or "").strip()
                if option_label:
                    parts.append(option_label)
                if option_desc:
                    parts.append(option_desc)

            children = item.get("components", []) or []
            if children:
                walk(children)

    walk(components)
    return "\n".join(dict.fromkeys(part for part in parts if part))


def embeds_to_text(embeds: list[dict]) -> str:
    parts: list[str] = []

    for embed in embeds or []:
        title = (embed.get("title") or "").strip()
        description = (embed.get("description") or "").strip()
        if title:
            parts.append(title)
        if description:
            parts.append(description)

        for field in embed.get("fields", []) or []:
            name = (field.get("name") or "").strip()
            value = (field.get("value") or "").strip()
            if name:
                parts.append(name)
            if value:
                parts.append(value)

        footer_text = (embed.get("footer", {}) or {}).get("text")
        if footer_text and str(footer_text).strip():
            parts.append(str(footer_text).strip())

    return "\n".join(part for part in parts if part)


def raw_message_full_text(raw_message: dict) -> str:
    parts = [
        (raw_message.get("content") or "").strip(),
        embeds_to_text(raw_message.get("embeds", []) or []),
        components_to_text(raw_message.get("components", []) or []),
    ]
    return "\n".join(part for part in parts if part)


def extract_discord_id(text: str) -> str | None:
    match = PAREN_ID_PATTERN.search(text)
    if match:
        return match.group(1)

    match = LABELLED_ID_PATTERN.search(text)
    if match:
        return match.group(1)

    mentions = USER_MENTION_PATTERN.findall(text)
    if mentions:
        # S'il y a plusieurs mentions, la première est en général le
        # modérateur et la seconde le membre visé.
        return mentions[1] if len(mentions) > 1 else mentions[0]

    return None


def extract_reason(full_text: str) -> str:
    match = REASON_CODEBLOCK_PATTERN.search(full_text)
    if match:
        return match.group(1).strip()

    match = REASON_PLAIN_PATTERN.search(full_text)
    if match:
        reason = match.group(1).strip().split("\n\n")[0].strip()
        return reason.strip("`").strip()

    return full_text.strip()


def build_snapshot(member: discord.Member | None, fallback_id: str) -> dict:
    if member is None:
        return {
            "id": fallback_id,
            "username": fallback_id,
            "display_name": fallback_id,
            "avatar_url": None,
        }

    return {
        "id": str(member.id),
        "username": member.name,
        "display_name": member.display_name,
        "avatar_url": str(member.display_avatar.url) if member.display_avatar else None,
    }


@moderation_client.event
async def on_ready():
    logger.info("Bot de modération connecté en tant que %s", moderation_client.user)
    if not DISCORD_MODERATION_CHANNEL_TYPES:
        logger.warning(
            "Aucun salon de modération configuré (DISCORD_MODERATION_CHANNELS vide) — "
            "le bot ne traitera aucun message."
        )
    else:
        logger.info("Salons surveillés : %s", DISCORD_MODERATION_CHANNEL_TYPES)


@moderation_client.event
async def on_message(message: discord.Message):
    sanction_type = DISCORD_MODERATION_CHANNEL_TYPES.get(message.channel.id)
    if sanction_type is None:
        return

    raw_message = await fetch_raw_message(message.channel.id, message.id)
    if raw_message is None:
        return

    full_text = raw_message_full_text(raw_message)
    if not full_text.strip():
        logger.debug("Message %s sans texte exploitable.", message.id)
        return

    if REMOVE_VERB_PATTERN.search(full_text) and not ADD_VERB_PATTERN.search(full_text):
        logger.debug("Message de retrait ignoré (message %s).", message.id)
        return

    discord_id = extract_discord_id(full_text)
    if not discord_id:
        logger.debug("Aucun ID détecté dans le message %s (salon %s).", message.id, message.channel.id)
        return

    member = None
    if message.guild:
        try:
            member = message.guild.get_member(int(discord_id)) or await message.guild.fetch_member(int(discord_id))
        except (discord.NotFound, discord.HTTPException):
            member = None

    snapshot = build_snapshot(member, discord_id)
    reason = extract_reason(full_text)[:1000]

    source = {
        "channel_id": str(message.channel.id),
        "message_id": str(message.id),
        "message_url": message.jump_url,
    }

    try:
        await add_sanction(
            discord_id=discord_id,
            sanction_type=sanction_type,
            reason=reason,
            snapshot=snapshot,
            created_by=None,
            source=source,
            dedupe_message_id=str(message.id),
        )
        logger.info(
            "Sanction '%s' enregistrée pour %s (message %s, salon %s).",
            sanction_type,
            discord_id,
            message.id,
            message.channel.id,
        )
    except Exception:
        logger.exception("Échec de l'enregistrement automatique (message %s).", message.id)


async def start_moderation_bot() -> None:
    if not DISCORD_BOT_TOKEN:
        logger.warning("DISCORD_BOT_TOKEN manquant — bot de modération non démarré.")
        return

    await moderation_client.start(DISCORD_BOT_TOKEN)


async def stop_moderation_bot() -> None:
    if not moderation_client.is_closed():
        await moderation_client.close()
