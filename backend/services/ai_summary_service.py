import json
from datetime import datetime, timezone
from uuid import uuid4

from emergentintegrations.llm.chat import LlmChat, StreamDone, TextDelta, UserMessage
from fastapi import HTTPException, status

from config import EMERGENT_LLM_KEY
from models.ticket import AiSummary


SYSTEM_PROMPT = """Tu rédiges des synthèses concises en français pour des helpers d’un espace d’écoute.
Utilise exclusivement les informations présentes dans le dossier fourni.
N’établis aucun diagnostic, ne formule aucune recommandation médicale et n’invente aucun fait.
Retourne strictement un objet JSON valide avec les clés : context, expressed_needs, actions, next_follow_up.
Chaque valeur est une phrase ou une liste courte, claire et factuelle."""


def ensure_ai_configuration() -> None:
    if not EMERGENT_LLM_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="La clé Gemini n’est pas configurée.",
        )


def summary_input(ticket: dict) -> str:
    messages = [
        {
            "auteur": message["author"].get("display_name") or message["author"]["username"],
            "message": message.get("content", ""),
            "date": message.get("timestamp", ""),
        }
        for message in ticket.get("transcript", [])
    ]
    return json.dumps(
        {
            "titre": ticket.get("title", ""),
            "statut_de_suivi": ticket.get("follow_up_status", ""),
            "transcription": messages,
            "notes_privees": ticket.get("notes", ""),
            "compte_rendu_vocal": ticket.get("vocal_summary", ""),
        },
        ensure_ascii=False,
    )


def parse_summary(raw_text: str, helper_id: str) -> AiSummary:
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", maxsplit=1)[1]
        cleaned = cleaned.rsplit("```", maxsplit=1)[0]
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError as error:
        raise ValueError("Gemini a retourné un format de résumé invalide.") from error
    aliases = {
        "context": ("context", "contexte"),
        "expressed_needs": ("expressed_needs", "needs", "besoins_exprimés", "besoins"),
        "actions": ("actions", "action"),
        "next_follow_up": ("next_follow_up", "follow_up", "prochain_suivi", "suivi"),
    }
    normalized: dict[str, str] = {}
    for key, choices in aliases.items():
        value = next((payload.get(choice) for choice in choices if payload.get(choice) is not None), None)
        if isinstance(value, str) and value.strip():
            normalized[key] = value.strip()
        elif isinstance(value, list):
            bullet_points = [str(item).strip() for item in value if str(item).strip()]
            normalized[key] = " · ".join(bullet_points) or "Non précisé dans le dossier."
        else:
            normalized[key] = "Non précisé dans le dossier."
    return AiSummary(
        context=normalized["context"],
        expressed_needs=normalized["expressed_needs"],
        actions=normalized["actions"],
        next_follow_up=normalized["next_follow_up"],
        generated_at=datetime.now(timezone.utc).isoformat(),
        generated_by=helper_id,
    )


async def stream_summary(ticket: dict, helper_id: str):
    ensure_ai_configuration()
    chat = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=f"iris-summary-{ticket['id']}-{uuid4()}",
        system_message=SYSTEM_PROMPT,
    ).with_model("gemini", "gemini-3.5-flash")
    chunks: list[str] = []
    async for event in chat.stream_message(UserMessage(text=summary_input(ticket))):
        if isinstance(event, TextDelta):
            chunks.append(event.content)
            yield "progress", "Gemini rédige la synthèse…"
        elif isinstance(event, StreamDone):
            break
    yield "complete", parse_summary("".join(chunks), helper_id)