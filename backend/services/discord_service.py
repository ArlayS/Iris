import asyncio
from typing import Any

import httpx
from fastapi import HTTPException, status

from config import DISCORD_BOT_TOKEN, DISCORD_GUILD_ID, missing_discord_bot_settings
from models.ticket import DiscordAttachment, DiscordAuthor, DiscordMember, TranscriptMessage


DISCORD_API_BASE = "https://discord.com/api/v10"


def ensure_bot_configuration() -> None:
    missing = missing_discord_bot_settings()
    if missing:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Configuration Discord incomplète : {', '.join(missing)}.",
        )


def avatar_url(user: dict[str, Any]) -> str | None:
    avatar = user.get("avatar")
    if avatar:
        return f"https://cdn.discordapp.com/avatars/{user['id']}/{avatar}.png?size=128"
    discriminator = user.get("discriminator", "0")
    try:
        default_index = int(discriminator) % 5
    except ValueError:
        default_index = 0
    return f"https://cdn.discordapp.com/embed/avatars/{default_index}.png"


class DiscordService:
    def __init__(self) -> None:
        ensure_bot_configuration()
        self.headers = {"Authorization": f"Bot {DISCORD_BOT_TOKEN}"}

    async def _get(self, path: str, params: dict[str, str | int] | None = None) -> dict | list:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{DISCORD_API_BASE}{path}",
                headers=self.headers,
                params=params,
            )
        if response.status_code == 429:
            retry_after = response.json().get("retry_after", 1)
            await asyncio.sleep(float(retry_after))
            return await self._get(path, params)
        if response.status_code == 404:
            raise HTTPException(status_code=404, detail="Ressource Discord introuvable.")
        if response.status_code == 403:
            raise HTTPException(
                status_code=403,
                detail="Le bot ne peut pas accéder à cette ressource Discord.",
            )
        if response.is_error:
            raise HTTPException(
                status_code=502,
                detail="Discord n’a pas pu traiter la demande. Réessayez dans un instant.",
            )
        return response.json()

    async def fetch_member(self, member_id: str) -> DiscordMember:
        payload = await self._get(f"/guilds/{DISCORD_GUILD_ID}/members/{member_id}")
        user = payload["user"]
        return DiscordMember(
            id=user["id"],
            username=user["username"],
            display_name=payload.get("nick") or user.get("global_name"),
            avatar_url=avatar_url(user),
            joined_at=payload.get("joined_at"),
        )

    async def member_has_role(self, member_id: str, role_id: str) -> bool:
        payload = await self._get(f"/guilds/{DISCORD_GUILD_ID}/members/{member_id}")
        return role_id in payload.get("roles", [])

    async def fetch_text_channel(self, channel_id: str) -> dict[str, Any]:
        channel = await self._get(f"/channels/{channel_id}")
        if channel.get("guild_id") != DISCORD_GUILD_ID:
            raise HTTPException(status_code=403, detail="Ce salon n’appartient pas au serveur Iris.")
        if channel.get("type") not in {0, 5, 15}:
            raise HTTPException(status_code=422, detail="L’identifiant doit désigner un salon textuel.")
        return channel

    async def fetch_channel_history(self, channel_id: str) -> list[TranscriptMessage]:
        await self.fetch_text_channel(channel_id)
        messages: list[TranscriptMessage] = []
        before: str | None = None
        while True:
            params: dict[str, str | int] = {"limit": 100}
            if before:
                params["before"] = before
            page = await self._get(f"/channels/{channel_id}/messages", params)
            if not page:
                break
            for raw_message in page:
                author = raw_message["author"]
                messages.append(
                    TranscriptMessage(
                        id=raw_message["id"],
                        content=raw_message.get("content", ""),
                        timestamp=raw_message["timestamp"],
                        author=DiscordAuthor(
                            id=author["id"],
                            username=author["username"],
                            display_name=raw_message.get("member", {}).get("nick")
                            or author.get("global_name"),
                            avatar_url=avatar_url(author),
                        ),
                        attachments=[
                            DiscordAttachment(
                                id=attachment["id"],
                                filename=attachment["filename"],
                                url=attachment["url"],
                                content_type=attachment.get("content_type"),
                            )
                            for attachment in raw_message.get("attachments", [])
                        ],
                    )
                )
            if len(page) < 100:
                break
            before = page[-1]["id"]
        return list(reversed(messages))