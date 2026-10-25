import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import {
  Search,
  RefreshCw,
  Shield,
  ChevronLeft,
  ChevronRight,
  ArrowRight,
} from "lucide-react";
import { api, getErrorMessage } from "../api/client";
import {
  CASIER_EVENT_LABELS,
  CASIER_EVENT_TYPES,
  casierEventTone,
  isCasierEvent,
  reviewMeta,
  sanctionTypeMeta,
  statusMeta,
} from "../components/casier/casierConstants";
import { casierLogLink, formatBytes } from "../components/casier/formatters";

const AGENDA_EVENT_LABELS = {
  "agenda.settings.updated": "Agenda : réglages des rappels modifiés",
  "agenda.settings.test_sent": "Agenda : message de test envoyé",
};

const EVENT_LABELS = {
  "auth.login.started": "Connexion démarrée",
  "auth.login.success": "Connexion réussie",
  "auth.login.failure": "Connexion échouée",
  "auth.logout": "Déconnexion",
  "auth.session.invalid": "Session invalide",
  "auth.session.check_failed": "Vérification session échouée",
  "authz.forbidden": "Accès refusé",

  "project.viewed": "Projet consulté",
  "project.created": "Projet créé",
  "project.content.updated": "Projet modifié",
  "project.deleted": "Projet supprimé",
  "project.member.added": "Membre ajouté",
  "project.task.created": "Tâche créée",
  "project.task.submitted": "Tâche rendue",
  "project.task.validated": "Tâche validée",
  "project.task.deleted": "Tâche supprimée",
  "project.resource.uploaded": "Ressource ajoutée",
  "project.resource.deleted": "Ressource supprimée",

  ...CASIER_EVENT_LABELS,
  ...AGENDA_EVENT_LABELS,
};

// Options du filtre « événement », regroupées (filtre exact côté serveur).
const EVENT_GROUPS = [
  {
    label: "Connexions",
    types: [
      "auth.login.started",
      "auth.login.success",
      "auth.login.failure",
      "auth.logout",
      "auth.session.invalid",
      "auth.session.check_failed",
      "authz.forbidden",
    ],
  },
  {
    label: "Projets",
    types: [
      "project.viewed",
      "project.created",
      "project.content.updated",
      "project.deleted",
      "project.member.added",
      "project.task.created",
      "project.task.submitted",
      "project.task.validated",
      "project.task.deleted",
      "project.resource.uploaded",
      "project.resource.deleted",
    ],
  },
  { label: "Casiers", types: CASIER_EVENT_TYPES },
  { label: "Agenda", types: Object.keys(AGENDA_EVENT_LABELS) },
];

function formatDateTime(value) {
  if (!value) return "—";
  try {
    return new Date(value).toLocaleString("fr-FR", {
      dateStyle: "medium",
      timeStyle: "medium",
    });
  } catch {
    return value;
  }
}

function EventBadge({ eventType }) {
  const colorClass =
    eventType === "auth.login.success" ||
    eventType === "project.created" ||
    eventType === "project.task.created" ||
    eventType === "project.task.validated" ||
    eventType === "project.resource.uploaded"
      ? "status-done"
      : eventType === "auth.logout" ||
        eventType === "project.viewed" ||
        eventType === "project.content.updated" ||
        eventType === "project.member.added" ||
        eventType === "project.task.submitted"
      ? "status-pending"
      : eventType === "auth.login.failure" ||
        eventType === "authz.forbidden" ||
        eventType === "project.deleted" ||
        eventType === "project.task.deleted" ||
        eventType === "project.resource.deleted"
      ? "status-bad"
      : "";
  const tone = isCasierEvent(eventType)
    ? casierEventTone(eventType)
    : AGENDA_EVENT_LABELS[eventType]
    ? "status-pending"
    : colorClass;

  return (
    <span className={`status-badge ${tone}`}>
      {EVENT_LABELS[eventType] || eventType}
    </span>
  );
}

function DetailLine({ label, value }) {
  if (value === undefined || value === null || value === "") return null;
  return (
    <span style={{ fontSize: 12, color: "var(--muted)" }}>
      {label} : {String(value)}
    </span>
  );
}

const yesNo = (value) => (value === undefined || value === null ? undefined : value ? "Oui" : "Non");

function transition(before, after, label) {
  if (!before && !after) return undefined;
  if (before && after && before !== after) return `${label(before)} → ${label(after)}`;
  return label(after || before);
}

// Détails lisibles d'une entrée casier.* (sans dupliquer member_id / member_username).
function CasierLogDetails({ eventType, details }) {
  const data = details || {};
  const link = casierLogLink(eventType, data);
  const member =
    data.member_username || data.member_id
      ? `${data.member_username || "Membre"}${data.member_id ? ` (${data.member_id})` : ""}`
      : undefined;
  const files =
    data.files_found !== undefined || data.files_queued !== undefined
      ? `${data.files_found ?? 0} trouvé${Number(data.files_found) > 1 ? "s" : ""} · ${data.files_queued ?? 0} en copie`
      : undefined;
  const fileSize = formatBytes(data.size);
  const file = data.original_filename
    ? `${data.original_filename}${fileSize ? ` (${fileSize})` : ""}`
    : undefined;

  return (
    <>
      <DetailLine label="Membre" value={member} />
      <DetailLine label="Casier en prévention" value={yesNo(data.is_prevention)} />
      <DetailLine
        label="Sanction"
        value={data.sanction_type ? sanctionTypeMeta(data.sanction_type).label : undefined}
      />
      <DetailLine
        label="Statut"
        value={transition(data.status_before, data.status_after, (value) => statusMeta(value).label)}
      />
      <DetailLine label="Extrait" value={data.reason_excerpt} />
      <DetailLine label="Durée" value={data.duration} />
      <DetailLine label="Créée depuis un signalement IA" value={data.ai_flag_id ? "Oui" : undefined} />
      <DetailLine label="Fiche S" value={data.fiche_title} />
      <DetailLine label="Titre précédent" value={data.previous_title} />
      <DetailLine label="Version n°" value={data.revision_number} />
      <DetailLine label="Fichier" value={file} />
      <DetailLine label="Fichiers du log" value={files} />
      <DetailLine label="Modérateur complété" value={yesNo(data.moderator_filled)} />
      <DetailLine
        label="Décision"
        value={transition(data.review_before, data.review_after, (value) => reviewMeta(value).label)}
      />
      <DetailLine
        label="Commentaire"
        value={Number(data.comment_length) > 0 ? `${data.comment_length} caractères` : undefined}
      />

      {(data.before_length !== undefined || data.after_length !== undefined) && (
        <span style={{ fontSize: 12, color: "var(--muted)" }}>
          Contenu : {data.before_length ?? 0} → {data.after_length ?? 0} caractères
        </span>
      )}
      {data.content_length !== undefined && data.before_length === undefined && (
        <span style={{ fontSize: 12, color: "var(--muted)" }}>
          Contenu : {data.content_length} caractères
        </span>
      )}

      {link && (
        <Link
          to={link}
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 4,
            marginTop: 2,
            fontSize: 12,
            fontWeight: 600,
            color: "var(--sage)",
          }}
        >
          {data.casier_id ? "Ouvrir le casier" : "Voir le signalement"}
          <ArrowRight size={13} aria-hidden="true" />
        </Link>
      )}
    </>
  );
}

const thStyle = {
  textAlign: "left",
  fontSize: 12,
  color: "var(--muted)",
  fontWeight: 700,
  padding: "14px 16px",
  whiteSpace: "nowrap",
};

const tdStyle = {
  padding: "14px 16px",
  verticalAlign: "top",
  fontSize: 13,
  color: "var(--ink)",
};

const codeStyle = {
  fontSize: 12,
  background: "rgba(0,0,0,0.04)",
  padding: "3px 6px",
  borderRadius: 6,
  wordBreak: "break-all",
};

export default function ResponsableAuthLogsPage() {
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);

  const [eventType, setEventType] = useState("");
  const [helperIdInput, setHelperIdInput] = useState("");
  const [helperIdFilter, setHelperIdFilter] = useState("");

  const [page, setPage] = useState(1);
  const [limit, setLimit] = useState(50);

  const skip = useMemo(() => (page - 1) * limit, [page, limit]);
  const totalPages = Math.max(1, Math.ceil(total / limit));

  const load = async () => {
    setLoading(true);
    try {
      const response = await api.get("/responsable/auth-logs", {
        params: {
          skip,
          limit,
          event_type: eventType || undefined,
          helper_id: helperIdFilter || undefined,
        },
      });
      setItems(response.data.items || []);
      setTotal(response.data.total || 0);
    } catch (error) {
      toast.error(getErrorMessage(error));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [skip, limit, eventType, helperIdFilter]);

  const applyFilters = (event) => {
    event.preventDefault();
    setPage(1);
    setHelperIdFilter(helperIdInput.trim());
  };

  const resetFilters = () => {
    setEventType("");
    setHelperIdInput("");
    setHelperIdFilter("");
    setPage(1);
    setLimit(50);
  };

  return (
    <section className="page-content dashboard-page" data-testid="responsable-auth-logs-page">
      <header className="page-header">
        <div>
          <p className="eyebrow">ESPACE RESPONSABLE</p>
          <h1>Logs de plateforme</h1>
          <p style={{ color: "var(--muted)", marginTop: 6 }}>
            Historique des connexions, accès refusés, actions sur les projets et modifications des casiers.
          </p>
        </div>
      </header>

      <form
        onSubmit={applyFilters}
        className="meeting-inline-form"
        style={{ marginBottom: 24 }}
      >
        <div className="meeting-inline-form-header">
          <span>Filtres</span>
        </div>

        <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          <select
            className="meeting-inline-input"
            value={eventType}
            onChange={(e) => {
              setEventType(e.target.value);
              setPage(1);
            }}
            style={{ minWidth: 260 }}
          >
            <option value="">Tous les événements</option>

            {EVENT_GROUPS.map((group) => (
              <optgroup key={group.label} label={group.label}>
                {group.types.map((type) => (
                  <option key={type} value={type}>
                    {EVENT_LABELS[type] || type}
                  </option>
                ))}
              </optgroup>
            ))}
          </select>

          <input
            className="meeting-inline-input"
            value={helperIdInput}
            onChange={(e) => setHelperIdInput(e.target.value)}
            placeholder="Filtrer par ID helper"
            style={{ minWidth: 240 }}
          />

          <select
            className="meeting-inline-input"
            value={limit}
            onChange={(e) => {
              setLimit(Number(e.target.value));
              setPage(1);
            }}
            style={{ width: 120 }}
          >
            <option value={25}>25 / page</option>
            <option value={50}>50 / page</option>
            <option value={100}>100 / page</option>
            <option value={200}>200 / page</option>
          </select>

          <button type="submit" className="meeting-inline-submit">
            <Search size={16} /> Rechercher
          </button>

          <button type="button" className="btn-ghost" onClick={resetFilters}>
            <RefreshCw size={16} /> Réinitialiser
          </button>
        </div>
      </form>

      <div className="dashboard-card" style={{ padding: 0 }}>
        <div
          className="section-heading"
          style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}
        >
          <span>JOURNAL D’ACTIVITÉ</span>
          <span style={{ color: "var(--muted)", fontSize: 13 }}>
            {total} entrée{total > 1 ? "s" : ""}
          </span>
        </div>

        {loading ? (
          <div style={{ padding: 20 }}>
            <p className="dashboard-loading">Chargement…</p>
          </div>
        ) : items.length === 0 ? (
          <div style={{ padding: 20 }}>
            <p className="dashboard-empty">Aucun log trouvé pour ces filtres.</p>
          </div>
        ) : (
          <>
            <div style={{ overflowX: "auto" }}>
              <table>
                <thead>
                  <tr style={{ borderBottom: "1px solid var(--line)" }}>
                    <th style={thStyle}>Date</th>
                    <th style={thStyle}>Événement</th>
                    <th style={thStyle}>Utilisateur</th>
                    <th style={thStyle}>IP</th>
                    <th style={thStyle}>Méthode</th>
                    <th style={thStyle}>Chemin</th>
                    <th style={thStyle}>Code</th>
                    <th style={thStyle}>Détails</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((log) => (
                    <tr key={log.id} style={{ borderBottom: "1px solid var(--line)" }}>
                      <td style={tdStyle}>{formatDateTime(log.created_at)}</td>
                      <td style={tdStyle}>
                        <EventBadge eventType={log.event_type} />
                      </td>
                      <td style={tdStyle}>
                        <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                          <strong style={{ fontSize: 13 }}>
                            {log.username || "Inconnu"}
                          </strong>
                          <span style={{ color: "var(--muted)", fontSize: 12 }}>
                            {log.helper_id || "—"}
                          </span>
                        </div>
                      </td>
                      <td style={tdStyle}>{log.ip || "—"}</td>
                      <td style={tdStyle}>{log.method || "—"}</td>
                      <td style={tdStyle}>
                        <code style={codeStyle}>{log.path || "—"}</code>
                      </td>
                      <td style={tdStyle}>{log.status_code ?? "—"}</td>
                      <td style={tdStyle}>
                        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                          {isCasierEvent(log.event_type) ? (
                            <CasierLogDetails eventType={log.event_type} details={log.details} />
                          ) : (
                            <>
                              <DetailLine label="Raison" value={log.details?.reason} />
                              <DetailLine label="Provider" value={log.details?.provider} />
                              <DetailLine label="Mode" value={log.details?.mode} />
                              <DetailLine label="Projet" value={log.details?.title} />
                              <DetailLine label="ID projet" value={log.details?.project_id} />
                              <DetailLine label="ID tâche" value={log.details?.task_id} />
                              <DetailLine label="ID ressource" value={log.details?.resource_id} />
                              <DetailLine label="ID membre" value={log.details?.member_id} />
                              <DetailLine label="Utilisateur membre" value={log.details?.member_username} />
                              <DetailLine label="Fichier" value={log.details?.original_filename} />
                              <DetailLine label="A un fichier" value={
                                log.details?.has_file !== undefined
                                  ? log.details.has_file ? "Oui" : "Non"
                                  : undefined
                              } />
                              <DetailLine label="IP client" value={log.details?.client_ip} />
                              <DetailLine label="User-Agent" value={log.details?.user_agent} />

                              {(log.details?.before_length !== undefined ||
                                log.details?.after_length !== undefined) && (
                                <span style={{ fontSize: 12, color: "var(--muted)" }}>
                                  Contenu : {log.details?.before_length ?? 0} → {log.details?.after_length ?? 0} caractères
                                </span>
                              )}

                              {(log.details?.before?.content_length !== undefined ||
                                log.details?.after?.content_length !== undefined) && (
                                <span style={{ fontSize: 12, color: "var(--muted)" }}>
                                  Contenu : {log.details?.before?.content_length ?? 0} → {log.details?.after?.content_length ?? 0} caractères
                                </span>
                              )}

                              <DetailLine label="Avant - titre" value={log.details?.before?.title} />
                              <DetailLine label="Après - titre" value={log.details?.after?.title} />
                              <DetailLine label="Avant - description" value={log.details?.before?.description} />
                              <DetailLine label="Après - description" value={log.details?.after?.description} />
                              <DetailLine label="Avant - fin" value={log.details?.before?.end_date} />
                              <DetailLine label="Après - fin" value={log.details?.after?.end_date} />
                              <DetailLine label="Avant - statut" value={log.details?.before?.status} />
                              <DetailLine label="Après - statut" value={log.details?.after?.status} />
                            </>
                          )}

                          {(!log.details || Object.keys(log.details).length === 0) && "—"}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                gap: 12,
                padding: 16,
                flexWrap: "wrap",
              }}
            >
              <div style={{ color: "var(--muted)", fontSize: 13 }}>
                Page {page} sur {totalPages}
              </div>

              <div style={{ display: "flex", gap: 8 }}>
                <button
                  type="button"
                  className="btn-ghost"
                  onClick={() => setPage((current) => Math.max(1, current - 1))}
                  disabled={page <= 1}
                >
                  <ChevronLeft size={16} /> Précédent
                </button>

                <button
                  type="button"
                  className="btn-ghost"
                  onClick={() => setPage((current) => Math.min(totalPages, current + 1))}
                  disabled={page >= totalPages}
                >
                  Suivant <ChevronRight size={16} />
                </button>
              </div>
            </div>
          </>
        )}
      </div>

      <div className="lock-banner" style={{ marginTop: 20 }}>
        <Shield size={14} />
        Ces logs sont conservés pendant une durée limitée (180 jours par défaut, AUTH_LOG_TTL_DAYS).
      </div>
    </section>
  );
}
