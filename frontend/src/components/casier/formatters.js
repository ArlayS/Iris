import { api } from "../../api/client";
import {
  BOT_AUTHOR_USERNAME,
  BOT_DISPLAY_LABEL,
  CASIER_PAGE_PATH,
  REMINDER_TYPE,
  SANCTION_TYPES,
  aiCategoryLabel,
  sanctionTypeMeta,
} from "./casierConstants";

const LOCALE = "fr-FR";
const NBSP = " ";

function toDate(value) {
  if (value === null || value === undefined || value === "") return null;
  const date = value instanceof Date ? value : new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

function sameDay(a, b) {
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
}

/* ---------------------------------- */
/* Dates                              */
/* ---------------------------------- */

// « 25 oct. 2026, 17:25 » ; withTime=false → « 25 oct. 2026 ». Valeur vide → "" ; illisible → texte brut.
export function formatDate(value, { withTime = true } = {}) {
  const date = toDate(value);
  if (!date) return value ? String(value) : "";
  const options = { day: "numeric", month: "short", year: "numeric" };
  if (withTime) {
    options.hour = "2-digit";
    options.minute = "2-digit";
  }
  return date.toLocaleString(LOCALE, options);
}

// « 17:25 »
export function formatTime(value) {
  const date = toDate(value);
  if (!date) return "";
  return date.toLocaleTimeString(LOCALE, { hour: "2-digit", minute: "2-digit" });
}

// « 25 oct. » (année ajoutée si différente de l'année en cours), avec l'heure si withTime.
export function formatShortDate(value, { withTime = false, now = new Date() } = {}) {
  const date = toDate(value);
  if (!date) return "";
  const options = { day: "numeric", month: "short" };
  if (date.getFullYear() !== toDate(now)?.getFullYear()) options.year = "numeric";
  const text = date.toLocaleDateString(LOCALE, options);
  return withTime ? `${text} ${formatTime(date)}` : text;
}

// « jusqu'à 21:30 » (même jour) ou « jusqu'au 26 oct. 21:30 ».
export function formatUntil(value, now = new Date()) {
  const date = toDate(value);
  if (!date) return "";
  const reference = toDate(now) || new Date();
  if (sameDay(date, reference)) return `jusqu'à ${formatTime(date)}`;
  return `jusqu'au ${formatShortDate(date, { withTime: true, now: reference })}`;
}

const RELATIVE_STEPS = [
  { unit: "minute", seconds: 60, limit: 3600 },
  { unit: "hour", seconds: 3600, limit: 86400 },
  { unit: "day", seconds: 86400, limit: 7 * 86400 },
];

let relativeFormatter = null;
function getRelativeFormatter() {
  if (relativeFormatter === null) {
    try {
      relativeFormatter = new Intl.RelativeTimeFormat("fr", { numeric: "auto" });
    } catch {
      relativeFormatter = false;
    }
  }
  return relativeFormatter;
}

// « à l'instant », « il y a 5 minutes », « hier », « dans 45 minutes » ; au-delà de 7 jours : « 12 oct. ».
export function formatRelative(value, now = Date.now()) {
  const date = toDate(value);
  if (!date) return "";
  const reference = toDate(now) || new Date();
  const diffSeconds = (date.getTime() - reference.getTime()) / 1000;
  const absolute = Math.abs(diffSeconds);
  if (absolute < 45) return "à l'instant";

  const formatter = getRelativeFormatter();
  const step = RELATIVE_STEPS.find((item) => absolute < item.limit);
  if (!step || !formatter) return formatShortDate(date, { now: reference });

  const amount = Math.round(diffSeconds / step.seconds) || (diffSeconds < 0 ? -1 : 1);
  return formatter.format(amount, step.unit);
}

/* ---------------------------------- */
/* Nombres                            */
/* ---------------------------------- */

const BYTE_UNITS = ["o", "ko", "Mo", "Go"];

// « 0 o », « 1,7 ko », « 2,4 Mo » (base 1024, comme les plafonds du serveur). Valeur absente → "".
export function formatBytes(bytes) {
  const value = Number(bytes);
  if (bytes === null || bytes === undefined || bytes === "" || !Number.isFinite(value) || value < 0) return "";
  let size = value;
  let unit = 0;
  while (size >= 1024 && unit < BYTE_UNITS.length - 1) {
    size /= 1024;
    unit += 1;
  }
  const digits = unit === 0 || size >= 100 ? 0 : 1;
  return `${size.toLocaleString(LOCALE, { maximumFractionDigits: digits })}${NBSP}${BYTE_UNITS[unit]}`;
}

// « 88 % » depuis 0.88.
export function formatPercent(ratio) {
  const value = Number(ratio);
  if (ratio === null || ratio === undefined || !Number.isFinite(value)) return "";
  return `${Math.round(value * 100)}${NBSP}%`;
}

// plural(1, "casier") → « 1 casier » ; plural(3, "casier") → « 3 casiers ».
export function plural(count, singular, pluralForm) {
  const value = Number(count) || 0;
  const word = Math.abs(value) >= 2 ? pluralForm || `${singular}s` : singular;
  return `${value.toLocaleString(LOCALE)} ${word}`;
}

export function capitalize(text) {
  if (!text) return "";
  const value = String(text);
  return value.charAt(0).toLocaleUpperCase(LOCALE) + value.slice(1);
}

/* ---------------------------------- */
/* Fichiers                           */
/* ---------------------------------- */

// URL absolue d'un fichier de sanction (download_url relatif à /api, comme les archives de salons).
export function attachmentHref(downloadUrl, download = false) {
  if (typeof downloadUrl !== "string" || !downloadUrl.startsWith("/")) return null;
  const base = `${api.defaults?.baseURL || "/api"}${downloadUrl}`;
  if (!download) return base;
  return `${base}${base.includes("?") ? "&" : "?"}download=1`;
}

/* ---------------------------------- */
/* Personnes                          */
/* ---------------------------------- */

export function memberName(member) {
  return member?.display_name || member?.username || (member?.id ? `ID ${member.id}` : "Membre inconnu");
}

// « @pseudo » ou "" si inconnu.
export function memberHandle(member) {
  return member?.username ? `@${member.username}` : "";
}

export function authorName(author, fallback = "Staff") {
  return author?.display_name || author?.username || fallback;
}

export function isBotAuthor(author) {
  return Boolean(author) && !author.id && author.username === BOT_AUTHOR_USERNAME;
}

export function moderatorName(moderator) {
  if (!moderator) return "";
  return moderator.display_name || moderator.username || `un modérateur (ID ${moderator.id ?? "?"})`;
}

// « Par Inès (staff) (via OasisBot) » | « Par OasisBot » | « Par Lou » | « Par Staff ».
export function sanctionAuthorLabel(sanction) {
  if (sanction?.moderator) return `Par ${moderatorName(sanction.moderator)} (via ${BOT_DISPLAY_LABEL})`;
  if (isBotAuthor(sanction?.created_by)) return `Par ${BOT_DISPLAY_LABEL}`;
  return `Par ${authorName(sanction?.created_by)}`;
}

export function sanctionOrigin(sanction) {
  return sanction?.origin || (sanction?.source?.message_id ? "discord_log" : "manual");
}

/* ---------------------------------- */
/* Résumés                            */
/* ---------------------------------- */

// « 2 avert. · 1 ban » depuis sanctions_summary (rappels exclus par défaut). Rien → "".
export function formatSanctionsSummary(summary, { includeReminders = false } = {}) {
  if (!summary) return "";
  return SANCTION_TYPES.filter((item) => includeReminders || item.value !== REMINDER_TYPE)
    .map((item) => {
      const count = Number(summary[item.value]) || 0;
      if (count <= 0) return null;
      return `${count} ${count >= 2 ? item.shortPlural : item.short}`;
    })
    .filter(Boolean)
    .join(" · ");
}

const MEMBER_FIELD_LABELS = {
  display_name: "Nom affiché",
  username: "Pseudo",
  discord_id: "ID Discord",
};

// Préfixe d'un extrait de recherche ; afficher « <libellé> : <segments> ».
export function matchLabel(match) {
  if (!match) return "";
  const typeLabel = match.sanction_type ? sanctionTypeMeta(match.sanction_type).label : "";
  switch (match.kind) {
    case "membre":
      return MEMBER_FIELD_LABELS[match.field] || "Membre";
    case "sanction":
      if (match.field === "author") return "Staff";
      if (match.field === "moderator") return "Modérateur";
      if (match.field === "filename") return typeLabel ? `Fichier · ${typeLabel}` : "Fichier";
      return typeLabel ? `Motif · ${typeLabel}` : "Motif";
    case "note":
      return "Information";
    case "fiche_s":
      return match.field === "title" ? "Titre de fiche S" : "Fiche S";
    default:
      return "";
  }
}

// « Insulte · gravité 2/3 · confiance 88 % » ; null pour un refus / une analyse illisible.
export function formatVerdict(verdict) {
  if (!verdict) return null;
  const parts = [aiCategoryLabel(verdict.categorie)];
  if (Number.isFinite(Number(verdict.gravite)) && verdict.gravite !== null) parts.push(`gravité ${verdict.gravite}/3`);
  const confidence = formatPercent(verdict.confiance);
  if (confidence) parts.push(`confiance ${confidence}`);
  return parts.join(" · ");
}

// « message supprimé » → « Message supprimé ».
export function formatExecutedAction(action) {
  return capitalize(action);
}

/* ---------------------------------- */
/* Liens profonds                     */
/* ---------------------------------- */

// casierLink({ casierId, onglet, sanctionId, signalementId, vue }) → "/moderation/casiers?casier=…".
export function casierLink({ casierId, onglet, sanctionId, signalementId, vue } = {}) {
  const params = new URLSearchParams();
  if (vue) params.set("vue", vue);
  if (casierId) params.set("casier", casierId);
  if (onglet) params.set("onglet", onglet);
  if (sanctionId) params.set("sanction", sanctionId);
  if (signalementId) params.set("signalement", signalementId);
  const query = params.toString();
  return query ? `${CASIER_PAGE_PATH}?${query}` : CASIER_PAGE_PATH;
}

// Lien « Ouvrir le casier » d'une entrée auth_logs casier.* (null si aucun casier ni signalement).
export function casierLogLink(eventType, details) {
  const data = details || {};
  const type = String(eventType || "");
  if (type === "casier.ai_flag.reviewed") {
    if (data.casier_id) {
      return casierLink({ casierId: data.casier_id, onglet: "signalements", signalementId: data.flag_id });
    }
    return data.flag_id ? casierLink({ vue: "signalements", signalementId: data.flag_id }) : null;
  }
  if (!data.casier_id) return null;
  if (type.startsWith("casier.fiche_s.")) return casierLink({ casierId: data.casier_id, onglet: "fiches" });
  return casierLink({ casierId: data.casier_id, sanctionId: data.sanction_id });
}
