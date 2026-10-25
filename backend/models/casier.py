"""Schémas Pydantic du casier (modération) et des signalements IA.

Convention : les valeurs calculées à la lecture (statut, origine, format, correspondances de recherche) sont
typées en `Literal` ; les valeurs relues telles quelles en base (type de sanction, statut d'un fichier, revue d'un
signalement…) restent des `str`, pour qu'un document ancien ou inattendu ne casse jamais une liste (lecteurs
tolérants). Les champs internes absents des modèles de réponse (`source_url`, `revisions`, `deleted_*`,
`guild_id`, `channel.parent_id`…) sont ignorés à la validation et ne sont donc jamais renvoyés.
"""
import re
from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, BeforeValidator, Field, StringConstraints, field_validator

# Identifiants internes (sanction, note, fiche S, signalement) et identifiants de fichier (snowflake Discord ou
# identifiant interne). La validation se fait dans le router (400 « Identifiant invalide. »), pas ici (422).
HEX_ID_PATTERN = re.compile(r"[0-9a-f]{24}")
ATTACHMENT_ID_PATTERN = re.compile(r"(?:[0-9]{17,20}|[0-9a-f]{24})")

SANCTION_TYPE_MAX_LENGTH = 40
REASON_MAX_LENGTH = 1000
DURATION_MAX_LENGTH = 80
NOTE_MAX_LENGTH = 4000
FICHE_TITLE_MAX_LENGTH = 160
FICHE_CONTENT_MAX_LENGTH = 200_000
REVIEW_COMMENT_MAX_LENGTH = 500

CasierStatus = Literal["vierge", "averti", "mute", "kick", "banni"]
SanctionOrigin = Literal["discord_log", "manual"]
FicheContentFormat = Literal["blocknote", "text", "html"]
SearchScope = Literal["tout", "membre", "staff", "contenu"]
CasierSort = Literal["recent", "gravite", "nom"]
SearchMatchKind = Literal["membre", "sanction", "note", "fiche_s"]
SearchMatchField = Literal[
    "display_name", "username", "discord_id",
    "reason", "author", "moderator", "filename",
    "content", "title",
]
AiFlagKind = Literal["violation", "refus", "illisible"]
AiFlagReviewStatus = Literal["a_traiter", "pertinent", "faux_positif"]
AiFlagReviewFilter = Literal["a_traiter", "pertinent", "faux_positif", "tous"]


def iso_datetime(value):
    """Datetime → ISO avec fuseau (naïf = UTC, comme relu de Mongo) ; une chaîne passe telle quelle."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    return value


IsoDateTime = Annotated[str, BeforeValidator(iso_datetime)]


def _blank_to_none(value: str | None) -> str | None:
    return value or None


# --- Réponses : membres et auteurs -------------------------------------------------------------------------


class MemberSearchResult(BaseModel):
    id: str
    username: str
    display_name: str | None = None
    avatar_url: str | None = None


class CasierMember(BaseModel):
    id: str
    username: str
    display_name: str | None = None
    avatar_url: str | None = None


class SanctionAuthor(BaseModel):
    id: str | None = None
    username: str | None = None
    display_name: str | None = None


class SanctionSource(BaseModel):
    channel_id: str | None = None
    message_id: str | None = None
    message_url: str | None = None


# --- Réponses : sanctions, informations complémentaires, fichiers, fiches S -------------------------------


class AttachmentOut(BaseModel):
    id: str
    origin: str  # discord | upload
    filename: str
    content_type: str | None = None
    size: int | None = None
    status: str  # pending | stored | failed | too_large
    error: str | None = None
    inline: bool = False
    download_url: str | None = None
    created_at: IsoDateTime | None = None
    uploaded_by: SanctionAuthor | None = None
    can_delete: bool = False


class NoteOut(BaseModel):
    id: str
    content: str
    created_at: IsoDateTime
    created_by: SanctionAuthor | None = None
    updated_at: IsoDateTime | None = None
    updated_by: SanctionAuthor | None = None
    can_edit: bool = False


class SanctionOut(BaseModel):
    id: str
    type: str  # type inconnu conservé et affiché tel quel
    reason: str
    created_at: IsoDateTime
    created_by: SanctionAuthor | None = None
    moderator: SanctionAuthor | None = None
    duration: str | None = None
    duration_seconds: int | None = None
    expires_at: IsoDateTime | None = None
    is_active: bool = False
    origin: SanctionOrigin = "manual"
    source: SanctionSource | None = None
    attachments: list[AttachmentOut] = Field(default_factory=list)
    notes: list[NoteOut] = Field(default_factory=list)
    ai_flag_id: str | None = None


class FicheSOut(BaseModel):
    id: str
    title: str
    content: str
    content_format: FicheContentFormat = "text"
    content_text: str = ""
    created_at: IsoDateTime
    created_by: SanctionAuthor | None = None
    updated_at: IsoDateTime | None = None
    updated_by: SanctionAuthor | None = None
    active: bool
    closed_at: IsoDateTime | None = None
    closed_by: SanctionAuthor | None = None
    can_edit: bool = False
    revisions_count: int = 0


# --- Réponses : recherche et casiers ----------------------------------------------------------------------


class SearchSegment(BaseModel):
    text: str
    match: bool


class SearchMatch(BaseModel):
    kind: SearchMatchKind
    field: SearchMatchField
    sanction_id: str | None = None
    sanction_type: str | None = None
    note_id: str | None = None
    fiche_id: str | None = None
    snippet: str
    segments: list[SearchSegment] = Field(default_factory=list)
    created_at: IsoDateTime | None = None
    author: SanctionAuthor | None = None


class CasierListItem(BaseModel):
    id: str
    member: CasierMember
    status: CasierStatus
    sanctions_count: int
    rappels_count: int = 0
    has_active_fiche_s: bool
    active_fiches_s_count: int = 0
    last_sanction_at: IsoDateTime | None = None
    last_sanction_label: str | None = None
    last_activity_at: IsoDateTime | None = None
    created_at: IsoDateTime
    sanctions_summary: dict[str, int]
    is_prevention: bool = False
    active_mute_until: IsoDateTime | None = None
    ai_flags_total: int = 0
    ai_flags_open: int = 0
    matches: list[SearchMatch] = Field(default_factory=list)
    matches_total: int = 0


class CasierDetailResponse(BaseModel):
    id: str
    member: CasierMember
    status: CasierStatus
    created_at: IsoDateTime
    created_by: SanctionAuthor | None = None
    sanctions_count: int
    rappels_count: int = 0
    sanctions_summary: dict[str, int]
    sanctions: list[SanctionOut]
    fiches_s: list[FicheSOut]
    active_fiches_s_count: int = 0
    is_prevention: bool = False
    active_mute_until: IsoDateTime | None = None
    last_activity_at: IsoDateTime | None = None
    ai_flags_total: int = 0
    ai_flags_open: int = 0


class CasierResponse(BaseModel):
    id: str
    discord_id: str
    created_at: str


class BotCasierResponse(BaseModel):
    """Forme figée (Ghost Bot) : 5 champs, aucun ajout."""

    discord_id: str
    status: str  # anciennes valeurs (legacy) par défaut, nouvelles en v2
    sanctions_count: int
    has_active_fiche_s: bool
    sanctions_markdown: str


# --- Réponses : signalements IA ---------------------------------------------------------------------------


class AiFlagAuthor(BaseModel):
    id: str | None = None
    username: str | None = None
    display_name: str | None = None
    avatar_url: str | None = None


class AiFlagChannel(BaseModel):
    id: str | None = None
    name: str | None = None


class AiFlagMessage(BaseModel):
    id: str | None = None
    content: str | None = None
    content_redacted: bool = False
    created_at: IsoDateTime | None = None
    jump_url: str | None = None

    @field_validator("content_redacted", mode="before")
    @classmethod
    def _redacted_default(cls, value):
        # Document sans la clé ou avec null : lu « non masqué ».
        return False if value is None else value


class AiFlagVerdict(BaseModel):
    violation: bool = False
    categorie: str | None = None
    gravite: int | None = None
    confiance: float | None = None
    raison: str | None = None
    sanction: str | None = None


class AiFlagAlert(BaseModel):
    posted: bool = False
    jump_url: str | None = None
    pinged: bool = False


class AiFlagReview(BaseModel):
    status: str = "a_traiter"  # a_traiter | pertinent | faux_positif
    comment: str | None = None
    reviewed_at: IsoDateTime | None = None
    reviewed_by: SanctionAuthor | None = None


class AiFlagSanctionLink(BaseModel):
    casier_id: str
    sanction_id: str


class AiFlagOut(BaseModel):
    id: str
    created_at: IsoDateTime
    discord_id: str
    author: AiFlagAuthor | None = None
    channel: AiFlagChannel | None = None
    message: AiFlagMessage = Field(default_factory=AiFlagMessage)
    kind: str  # violation | refus | illisible
    verdict: AiFlagVerdict | None = None
    mode: str | None = None
    planned_action: str | None = None
    executed: list[str] = Field(default_factory=list)
    alert: AiFlagAlert | None = None
    model: str | None = None
    review: AiFlagReview = Field(default_factory=AiFlagReview)
    sanction: AiFlagSanctionLink | None = None
    casier_id: str | None = None
    casier_status: CasierStatus | None = None


class AiFlagCounts(BaseModel):
    a_traiter: int = 0
    pertinent: int = 0
    faux_positif: int = 0
    total: int = 0


class AiFlagListResponse(BaseModel):
    total: int
    counts: AiFlagCounts = Field(default_factory=AiFlagCounts)
    items: list[AiFlagOut] = Field(default_factory=list)


# --- Requêtes -----------------------------------------------------------------------------------------------


class CreateCasierPayload(BaseModel):
    discord_id: str = Field(..., min_length=17, max_length=21)
    username: str | None = Field(default=None, min_length=1, max_length=80)


def _stripped(max_length: int, min_length: int = 0):
    return StringConstraints(strip_whitespace=True, min_length=min_length, max_length=max_length)


# Longueurs vérifiées après suppression des espaces de début et de fin.
ReasonText = Annotated[str, _stripped(REASON_MAX_LENGTH, 1)]
DurationText = Annotated[str, _stripped(DURATION_MAX_LENGTH), AfterValidator(_blank_to_none)]
NoteText = Annotated[str, _stripped(NOTE_MAX_LENGTH, 1)]
FicheTitle = Annotated[str, _stripped(FICHE_TITLE_MAX_LENGTH, 1)]
ReviewComment = Annotated[str, _stripped(REVIEW_COMMENT_MAX_LENGTH), AfterValidator(_blank_to_none)]


class CreateSanctionPayload(BaseModel):
    # Type et `ai_flag_id` volontairement libres : le router renvoie ses propres erreurs
    # (422 « Type de sanction invalide… », 400 « Identifiant invalide. »).
    type: str = Field(..., max_length=SANCTION_TYPE_MAX_LENGTH)
    reason: ReasonText
    duration: DurationText | None = None
    ai_flag_id: str | None = None


class NotePayload(BaseModel):
    content: NoteText


class CreateFicheSPayload(BaseModel):
    title: FicheTitle
    # JSON BlockNote attendu, texte brut accepté : assaini et vérifié (« La fiche S est vide. ») par le service.
    content: str = Field(..., min_length=1, max_length=FICHE_CONTENT_MAX_LENGTH)


class UpdateFicheSPayload(BaseModel):
    title: FicheTitle | None = None
    content: str | None = Field(default=None, min_length=1, max_length=FICHE_CONTENT_MAX_LENGTH)

    def is_empty(self) -> bool:
        """Aucun champ à modifier : le router répond 422 « Rien à modifier. »."""
        return self.title is None and self.content is None


class ReviewAiFlagPayload(BaseModel):
    review_status: AiFlagReviewStatus
    comment: ReviewComment | None = None

    @property
    def comment_provided(self) -> bool:
        """Vrai si `comment` figure dans la requête (y compris `null`, qui efface le commentaire)."""
        return "comment" in self.model_fields_set
