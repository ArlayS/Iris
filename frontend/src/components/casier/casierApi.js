import { api } from "../../api/client";

const BASE = "/moderation/casiers";

const GENERIC_ERROR = "Une erreur est survenue. Réessayez.";
const VALIDATION_ERROR = "Certaines informations sont invalides.";
const TOO_LARGE_ERROR = "Fichier trop volumineux.";

const seg = (value) => encodeURIComponent(String(value ?? ""));

const casierPath = (casierId) => `${BASE}/${seg(casierId)}`;
const sanctionPath = (casierId, sanctionId) => `${casierPath(casierId)}/sanctions/${seg(sanctionId)}`;
const fichePath = (casierId, ficheId) => `${casierPath(casierId)}/fiches-s/${seg(ficheId)}`;
const aiFlagPath = (flagId) => `${BASE}/ai-flags/${seg(flagId)}`;

/* ---------------------------------- */
/* Erreurs                            */
/* ---------------------------------- */

// detail texte → tel quel ; detail liste (422 Pydantic) → message générique de validation.
export function errorMessage(error) {
  const detail = error?.response?.data?.detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  if (Array.isArray(detail)) return VALIDATION_ERROR;
  // 413 renvoyé par un proxy (corps HTML, sans detail).
  if (error?.response?.status === 413) return TOO_LARGE_ERROR;
  return GENERIC_ERROR;
}

export function errorStatus(error) {
  return error?.response?.status ?? null;
}

export function isApiError(error, status) {
  return errorStatus(error) === status;
}

/* ---------------------------------- */
/* Clés react-query                   */
/* ---------------------------------- */

export const casierKeys = {
  lists: () => ["casiers"],
  list: (filters) => ["casiers", filters ?? {}],
  detail: (casierId) => ["casier", casierId],
  aiFlags: () => ["ai-flags"],
  aiFlagList: (params) => ["ai-flags", params ?? {}],
  aiFlag: (flagId) => ["ai-flags", "item", flagId],
};

/* ---------------------------------- */
/* Normalisation des réponses         */
/* ---------------------------------- */

const asArray = (value) => (Array.isArray(value) ? value : []);

// Paramètres de requête : retire undefined/null/""/NaN et tableaux vides ; tableau → "a,b" (jamais `x[]=`).
export function cleanParams(params) {
  const out = {};
  Object.entries(params || {}).forEach(([key, value]) => {
    if (value === undefined || value === null) return;
    if (Array.isArray(value)) {
      const joined = value
        .filter((item) => item !== undefined && item !== null && String(item).trim() !== "")
        .map((item) => String(item).trim())
        .join(",");
      if (joined) out[key] = joined;
      return;
    }
    if (typeof value === "number") {
      if (Number.isFinite(value)) out[key] = value;
      return;
    }
    if (typeof value === "boolean") {
      out[key] = value;
      return;
    }
    const text = String(value).trim();
    if (text) out[key] = text;
  });
  return out;
}

function normalizeSanction(sanction) {
  return {
    ...sanction,
    moderator: sanction?.moderator ?? null,
    attachments: asArray(sanction?.attachments),
    notes: asArray(sanction?.notes),
    ai_flag_id: sanction?.ai_flag_id ?? null,
  };
}

export function normalizeCasierDetail(detail) {
  if (!detail || typeof detail !== "object") return detail ?? null;
  return {
    ...detail,
    sanctions: asArray(detail.sanctions).map(normalizeSanction),
    fiches_s: asArray(detail.fiches_s),
    sanctions_summary: detail.sanctions_summary || {},
    rappels_count: detail.rappels_count ?? 0,
    active_fiches_s_count: detail.active_fiches_s_count ?? 0,
    ai_flags_total: detail.ai_flags_total ?? 0,
    ai_flags_open: detail.ai_flags_open ?? 0,
  };
}

function normalizeListItem(item) {
  return {
    ...item,
    matches: asArray(item?.matches),
    matches_total: item?.matches_total ?? 0,
    ai_flags_total: item?.ai_flags_total ?? 0,
    ai_flags_open: item?.ai_flags_open ?? 0,
  };
}

function normalizeAiFlagList(data) {
  const counts = data?.counts || {};
  const items = asArray(data?.items);
  return {
    total: Number.isFinite(data?.total) ? data.total : items.length,
    counts: {
      a_traiter: counts.a_traiter ?? 0,
      pertinent: counts.pertinent ?? 0,
      faux_positif: counts.faux_positif ?? 0,
      total: counts.total ?? 0,
    },
    items,
  };
}

const requestConfig = (options, extra) => {
  const config = { ...(extra || {}) };
  if (options?.signal) config.signal = options.signal;
  return config;
};

/* ---------------------------------- */
/* Casiers                            */
/* ---------------------------------- */

// params : { q, scope, status (tableau ou "a,b"), has_active_fiche_s, prevention, has_open_ai_flags, sort }.
export async function listCasiers(params = {}, options = {}) {
  const response = await api.get(BASE, requestConfig(options, { params: cleanParams(params) }));
  return asArray(response?.data).map(normalizeListItem);
}

export async function getCasier(casierId, options = {}) {
  const response = await api.get(casierPath(casierId), requestConfig(options));
  return normalizeCasierDetail(response?.data);
}

// body : { discord_id, username? } → { id, discord_id, created_at }.
export async function createCasier(body) {
  const payload = { discord_id: String(body?.discord_id ?? "").trim() };
  const username = typeof body?.username === "string" ? body.username.trim() : "";
  if (username) payload.username = username;
  const response = await api.post(BASE, payload);
  return response?.data ?? null;
}

// Après un 409 « Un casier existe déjà… » : retrouve le casier existant (élément de liste) ou null.
export async function findCasierByDiscordId(discordId, options = {}) {
  const needle = String(discordId ?? "").trim();
  if (!needle) return null;
  const items = await listCasiers({ q: needle, scope: "membre" }, options);
  return items.find((item) => item?.member?.id === needle) || null;
}

export async function searchMembers(q, options = {}) {
  const needle = String(q ?? "").trim();
  if (!needle) return [];
  const response = await api.get(`${BASE}/search-members`, requestConfig(options, { params: { q: needle } }));
  return asArray(response?.data);
}

/* ---------------------------------- */
/* Sanctions                          */
/* ---------------------------------- */

// body : { type, reason, duration?, ai_flag_id? } → détail du casier.
export async function addSanction(casierId, body) {
  const payload = {
    type: body?.type,
    reason: typeof body?.reason === "string" ? body.reason.trim() : body?.reason,
  };
  const duration = typeof body?.duration === "string" ? body.duration.trim() : "";
  if (duration) payload.duration = duration;
  if (body?.ai_flag_id) payload.ai_flag_id = body.ai_flag_id;
  const response = await api.post(`${casierPath(casierId)}/sanctions`, payload);
  return normalizeCasierDetail(response?.data);
}

export async function addNote(casierId, sanctionId, content) {
  const response = await api.post(`${sanctionPath(casierId, sanctionId)}/notes`, {
    content: String(content ?? "").trim(),
  });
  return normalizeCasierDetail(response?.data);
}

export async function updateNote(casierId, sanctionId, noteId, content) {
  const response = await api.patch(`${sanctionPath(casierId, sanctionId)}/notes/${seg(noteId)}`, {
    content: String(content ?? "").trim(),
  });
  return normalizeCasierDetail(response?.data);
}

export async function deleteNote(casierId, sanctionId, noteId) {
  const response = await api.delete(`${sanctionPath(casierId, sanctionId)}/notes/${seg(noteId)}`);
  return normalizeCasierDetail(response?.data);
}

/* ---------------------------------- */
/* Fichiers                           */
/* ---------------------------------- */

// onProgress(percent 0-100 | null si taille inconnue, événement axios). Content-Type laissé à axios (boundary).
export async function uploadAttachment(casierId, sanctionId, file, onProgress, options = {}) {
  const formData = new FormData();
  formData.append("file", file);
  const config = requestConfig(options);
  if (typeof onProgress === "function") {
    config.onUploadProgress = (event) => {
      const total = event?.total;
      const percent = total ? Math.min(100, Math.round((event.loaded / total) * 100)) : null;
      onProgress(percent, event);
    };
  }
  const response = await api.post(`${sanctionPath(casierId, sanctionId)}/attachments`, formData, config);
  return normalizeCasierDetail(response?.data);
}

export async function deleteAttachment(casierId, sanctionId, attachmentId) {
  const response = await api.delete(`${sanctionPath(casierId, sanctionId)}/attachments/${seg(attachmentId)}`);
  return normalizeCasierDetail(response?.data);
}

// 202 : fichiers en `pending`, le détail est ensuite sondé.
export async function resyncAttachments(casierId, sanctionId) {
  const response = await api.post(`${sanctionPath(casierId, sanctionId)}/attachments/resync`);
  return normalizeCasierDetail(response?.data);
}

/* ---------------------------------- */
/* Fiches S                           */
/* ---------------------------------- */

// body : { title, content } (content = JSON BlockNote en chaîne).
export async function createFiche(casierId, body) {
  const response = await api.post(`${casierPath(casierId)}/fiches-s`, {
    title: typeof body?.title === "string" ? body.title.trim() : body?.title,
    content: body?.content,
  });
  return normalizeCasierDetail(response?.data);
}

// body : { title?, content? } — seules les clés fournies sont envoyées.
export async function updateFiche(casierId, ficheId, body) {
  const payload = {};
  if (body?.title !== undefined) payload.title = typeof body.title === "string" ? body.title.trim() : body.title;
  if (body?.content !== undefined) payload.content = body.content;
  const response = await api.patch(fichePath(casierId, ficheId), payload);
  return normalizeCasierDetail(response?.data);
}

export async function closeFiche(casierId, ficheId) {
  const response = await api.patch(`${fichePath(casierId, ficheId)}/close`);
  return normalizeCasierDetail(response?.data);
}

/* ---------------------------------- */
/* Signalements IA                    */
/* ---------------------------------- */

// params : { discord_id, q, review_status, min_gravity, category, kind, skip, limit } → { total, counts, items }.
export async function listAiFlags(params = {}, options = {}) {
  const response = await api.get(`${BASE}/ai-flags`, requestConfig(options, { params: cleanParams(params) }));
  return normalizeAiFlagList(response?.data);
}

export async function getAiFlag(flagId, options = {}) {
  const response = await api.get(aiFlagPath(flagId), requestConfig(options));
  return response?.data ?? null;
}

// body : { review_status, comment? } — comment null efface, absent ne change rien.
export async function reviewAiFlag(flagId, body) {
  const payload = { review_status: body?.review_status };
  if (body?.comment !== undefined) {
    payload.comment = typeof body.comment === "string" ? body.comment.trim() || null : body.comment;
  }
  const response = await api.patch(aiFlagPath(flagId), payload);
  return response?.data ?? null;
}
