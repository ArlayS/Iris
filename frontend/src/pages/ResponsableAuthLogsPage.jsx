import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Search, RefreshCw, Shield, ChevronLeft, ChevronRight } from "lucide-react";
import { api, getErrorMessage } from "../api/client";

const EVENT_LABELS = {
  "auth.login.started": "Connexion démarrée",
  "auth.login.success": "Connexion réussie",
  "auth.login.failure": "Connexion échouée",
  "auth.logout": "Déconnexion",
  "auth.session.invalid": "Session invalide",
  "auth.session.check_failed": "Vérification session échouée",
  "authz.forbidden": "Accès refusé",
  "project.content.updated": "Contenu projet modifié",
};

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
    eventType === "auth.login.success"
      ? "status-done"
      : eventType === "auth.logout"
      ? "status-pending"
      : eventType === "project.content.updated"
      ? "status-pending"
      : eventType === "auth.login.failure" || eventType === "authz.forbidden"
      ? "status-bad"
      : "";

  return (
    <span className={`status-badge ${colorClass}`}>
      {EVENT_LABELS[eventType] || eventType}
    </span>
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
          <h1>Logs de connexion</h1>
          <p style={{ color: "var(--muted)", marginTop: 6 }}>
            Historique des connexions, déconnexions, sessions invalides et accès refusés.
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
            style={{ minWidth: 240 }}
          >
            <option value="">Tous les événements</option>
            <option value="auth.login.started">Connexion démarrée</option>
            <option value="auth.login.success">Connexion réussie</option>
            <option value="auth.login.failure">Connexion échouée</option>
            <option value="auth.logout">Déconnexion</option>
            <option value="auth.session.invalid">Session invalide</option>
            <option value="auth.session.check_failed">Vérification session échouée</option>
            <option value="authz.forbidden">Accès refusé</option>
            <option value="project.content.updated">Contenu projet modifié</option>
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

          <button
            type="button"
            className="btn-ghost"
            onClick={resetFilters}
          >
            <RefreshCw size={16} /> Réinitialiser
          </button>
        </div>
      </form>

      <div className="dashboard-card" style={{ padding: 0 }}>
        <div
          className="section-heading"
          style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}
        >
          <span>JOURNAL D’AUTHENTIFICATION</span>
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
    {log.details?.reason && (
      <span style={{ fontSize: 12, color: "var(--muted)" }}>
        Raison : {String(log.details.reason)}
      </span>
    )}

    {log.details?.provider && (
      <span style={{ fontSize: 12, color: "var(--muted)" }}>
        Provider : {String(log.details.provider)}
      </span>
    )}

    {log.details?.mode && (
      <span style={{ fontSize: 12, color: "var(--muted)" }}>
        Mode : {String(log.details.mode)}
      </span>
    )}

    {log.details?.title && (
      <span style={{ fontSize: 12, color: "var(--muted)" }}>
        Projet : {String(log.details.title)}
      </span>
    )}

    {log.details?.project_id && (
      <span style={{ fontSize: 12, color: "var(--muted)" }}>
        ID projet : {String(log.details.project_id)}
      </span>
    )}

    {(log.details?.before_length !== undefined ||
      log.details?.after_length !== undefined) && (
      <span style={{ fontSize: 12, color: "var(--muted)" }}>
        Contenu : {log.details?.before_length ?? 0} → {log.details?.after_length ?? 0} caractères
      </span>
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
        Ces logs sont conservés sans suppression automatique.
      </div>
    </section>
  );
}
