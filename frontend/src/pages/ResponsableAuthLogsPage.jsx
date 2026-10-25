import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import {
  ArrowRight,
  ChevronLeft,
  ChevronRight,
  FileText,
  LoaderCircle,
  RefreshCw,
  Search,
  Shield,
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

import "@/Casier.css";
import "@/ResponsableAuthLogs.css";

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
  const tone =
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
          : isCasierEvent(eventType)
            ? casierEventTone(eventType)
            : AGENDA_EVENT_LABELS[eventType]
              ? "status-pending"
              : "";

  return (
    <span className={`status-badge ${tone}`}>
      {EVENT_LABELS[eventType] || eventType}
    </span>
  );
}

function DetailLine({ label, value }) {
  if (value === undefined || value === null || value === "") return null;

  return (
    <span className="ral-detail">
      <b>{label}</b>
      {String(value)}
    </span>
  );
}

function CasierLogDetails({ eventType, details }) {
  const data = details || {};
  const link = casierLogLink(eventType, data);

  const member =
    data.member_username || data.member_id
      ? `${data.member_username || "Membre"}${
          data.member_id ? ` (${data.member_id})` : ""
        }`
      : undefined;

  const files =
    data.files_found !== undefined || data.files_queued !== undefined
      ? `${data.files_found ?? 0} trouvé${
          Number(data.files_found) > 1 ? "s" : ""
        } · ${data.files_queued ?? 0} en copie`
      : undefined;

  const fileSize = formatBytes(data.size);

  const file = data.original_filename
    ? `${data.original_filename}${fileSize ? ` (${fileSize})` : ""}`
    : undefined;

  return (
    <div className="ral-details">
      <DetailLine label="Membre" value={member} />

      <DetailLine
        label="Statut"
        value={data.status ? statusMeta(data.status).label : undefined}
      />

      <DetailLine
        label="Revue"
        value={data.review ? reviewMeta(data.review).label : undefined}
      />

      <DetailLine
        label="Sanction"
        value={
          data.sanction_type
            ? sanctionTypeMeta(data.sanction_type).label
            : undefined
        }
      />

      <DetailLine
        label="Commentaire"
        value={
          data.comment_length > 0
            ? `${data.comment_length} caractères`
            : undefined
        }
      />

      {(data.before_length !== undefined ||
        data.after_length !== undefined) && (
        <span className="ral-detail">
          <b>Contenu</b>
          {data.before_length ?? 0} → {data.after_length ?? 0} caractères
        </span>
      )}

      {data.content_length !== undefined &&
        data.before_length === undefined && (
          <span className="ral-detail">
            <b>Contenu</b>
            {data.content_length} caractères
          </span>
        )}

      <DetailLine label="Fichiers" value={files} />
      <DetailLine label="Fichier" value={file} />

      {link && (
        <Link to={link} className="ral-detail-link">
          {data.casier_id ? "Ouvrir le casier" : "Voir le signalement"}
          <ArrowRight size={13} aria-hidden="true" />
        </Link>
      )}
    </div>
  );
}

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

  useEffect(() => {
    document.body.classList.add("casier-no-nav");

    return () => {
      document.body.classList.remove("casier-no-nav");
    };
  }, []);

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
    <section
      className="cz-page ral-page"
      data-testid="responsable-auth-logs-page"
    >
      <header className="cz-header">
        <div className="cz-header-copy">
          <p className="cz-eyebrow">ESPACE RESPONSABLE</p>

          <h1>Journal d’activité</h1>

          <p className="cz-intro">
            Consultez les connexions, accès refusés et actions
            enregistrées dans Iris.
          </p>
        </div>

        <div className="cz-header-actions">
          <Link to="/" className="cz-home">
            Accueil
            <ArrowRight size={18} aria-hidden="true" />
          </Link>
        </div>
      </header>

      <section className="cz-panel ral-panel">
        <header className="cz-panel-header cz-panel-header--red">
          <span className="cz-panel-icon" aria-hidden="true">
            <Shield size={23} />
          </span>

          <div className="cz-panel-heading">
            <h2>Filtrer le journal</h2>
            <p>
              Recherchez une activité par type d’événement ou
              identifiant helper.
            </p>
          </div>

          <span className="cz-count-live">
            <span className="cz-count">
              {total} entrée{total > 1 ? "s" : ""}
            </span>
          </span>
        </header>

        <div className="cz-panel-toolbar">
          <form className="ral-filters" onSubmit={applyFilters}>
            <label className="ral-field">
              <span>Type d’événement</span>

              <select
                value={eventType}
                onChange={(event) => {
                  setEventType(event.target.value);
                  setPage(1);
                }}
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
            </label>

            <label className="ral-field">
              <span>ID helper</span>

              <input
                value={helperIdInput}
                onChange={(event) =>
                  setHelperIdInput(event.target.value)
                }
                placeholder="Ex. 123456789"
              />
            </label>

            <label className="ral-field">
              <span>Par page</span>

              <select
                value={limit}
                onChange={(event) => {
                  setLimit(Number(event.target.value));
                  setPage(1);
                }}
              >
                <option value={25}>25 entrées</option>
                <option value={50}>50 entrées</option>
                <option value={100}>100 entrées</option>
                <option value={200}>200 entrées</option>
              </select>
            </label>

            <div className="ral-filter-actions">
              <button type="submit" className="cz-button cz-button--primary">
                <Search size={16} aria-hidden="true" />
                Rechercher
              </button>

              <button
                type="button"
                className="cz-button"
                onClick={resetFilters}
              >
                Réinitialiser
              </button>
            </div>
          </form>
        </div>

        <div className="cz-panel-scroll">
          {loading ? (
            <div className="ral-state" role="status">
              <LoaderCircle className="spin" size={24} aria-hidden="true" />
              <p>Chargement du journal…</p>
            </div>
          ) : items.length === 0 ? (
            <div className="ral-state">
              <FileText size={30} aria-hidden="true" />
              <h2>Aucun log trouvé pour ces filtres.</h2>
              <p>Modifiez le type d’événement ou l’identifiant helper.</p>
            </div>
          ) : (
            <div className="ral-table-wrap">
              <table className="ral-table">
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Événement</th>
                    <th>Utilisateur</th>
                    <th>IP</th>
                    <th>Méthode</th>
                    <th>Chemin</th>
                    <th>Code</th>
                    <th>Détails</th>
                  </tr>
                </thead>

                <tbody>
                  {items.map((log) => (
                    <tr
                      key={`${log.id ?? log.created_at}-${log.event_type}`}
                    >
                      <td>{formatDateTime(log.created_at)}</td>

                      <td>
                        <EventBadge eventType={log.event_type} />
                      </td>

                      <td>
                        <strong>{log.username || "Inconnu"}</strong>
                        <small>{log.helper_id || "—"}</small>
                      </td>

                      <td>{log.ip || "—"}</td>
                      <td>{log.method || "—"}</td>
                      <td className="ral-path">{log.path || "—"}</td>
                      <td>{log.status_code ?? "—"}</td>

                      <td>
                        {isCasierEvent(log.event_type) ? (
                          <CasierLogDetails
                            eventType={log.event_type}
                            details={log.details}
                          />
                        ) : (
                          <div className="ral-details">
                            {(log.details?.before_length !== undefined ||
                              log.details?.after_length !== undefined) && (
                              <span className="ral-detail">
                                <b>Contenu</b>
                                {log.details?.before_length ?? 0} →{" "}
                                {log.details?.after_length ?? 0} caractères
                              </span>
                            )}

                            {(log.details?.before?.content_length !==
                              undefined ||
                              log.details?.after?.content_length !==
                                undefined) && (
                              <span className="ral-detail">
                                <b>Contenu</b>
                                {log.details?.before?.content_length ?? 0} →{" "}
                                {log.details?.after?.content_length ?? 0}{" "}
                                caractères
                              </span>
                            )}

                            {(!log.details ||
                              Object.keys(log.details).length === 0) && "—"}
                          </div>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <footer className="ral-pagination">
          <span>
            Page {page} sur {totalPages}
          </span>

          <div>
            <button
              type="button"
              onClick={() =>
                setPage((current) => Math.max(1, current - 1))
              }
              disabled={page <= 1}
            >
              <ChevronLeft size={15} aria-hidden="true" />
              Précédent
            </button>

            <button
              type="button"
              onClick={() =>
                setPage((current) => Math.min(totalPages, current + 1))
              }
              disabled={page >= totalPages}
            >
              Suivant
              <ChevronRight size={15} aria-hidden="true" />
            </button>
          </div>
        </footer>
      </section>
    </section>
  );
}
