import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  AlertTriangle,
  ArrowRight,
  FolderOpen,
  Plus,
  ShieldAlert,
  ShieldCheck,
  ShieldX,
  UserRound,
} from "lucide-react";
import { toast } from "sonner";

import { api, getErrorMessage } from "../api/client";
import CreateCasierModal from "../components/CreateCasierModal";

function CasierAvatar({ member, size = 32 }) {
  const label = member?.display_name || member?.username || "?";
  return (
    <span className="absence-avatar" style={{ width: size, height: size }} title={label}>
      {member?.avatar_url ? <img src={member.avatar_url} alt="" /> : <UserRound size={Math.round(size * 0.55)} />}
    </span>
  );
}

function statusLabel(status) {
  switch (status) {
    case "surveillance":
      return "SURVEILLANCE";
    case "sanctionne":
      return "SANCTIONNÉ";
    case "bloque":
      return "BLOQUÉ";
    default:
      return "VIERGE";
  }
}

function statusClass(status) {
  switch (status) {
    case "surveillance":
      return "pending";
    case "sanctionne":
      return "alert";
    case "bloque":
      return "danger";
    default:
      return "active";
  }
}

export default function CasierPage() {
  const [casiers, setCasiers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [createOpen, setCreateOpen] = useState(false);

  const loadCasiers = () => {
    setLoading(true);
    api
      .get("/moderation/casiers")
      .then((response) => setCasiers(response.data))
      .catch((error) => toast.error(getErrorMessage(error)))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadCasiers();
  }, []);

  const viergeCount = useMemo(() => casiers.filter((item) => item.status === "vierge").length, [casiers]);
  const watchCount = useMemo(() => casiers.filter((item) => item.status === "surveillance").length, [casiers]);
  const sanctionCount = useMemo(
    () => casiers.filter((item) => item.status === "sanctionne" || item.status === "bloque").length,
    [casiers]
  );

  const latest = casiers[0];

  return (
    <section className="page-content dashboard-page casier-dashboard-page" data-testid="casier-page">
      <header className="page-header">
        <div>
          <p className="eyebrow">ESPACE STAFF</p>
          <h1>Casier.</h1>
        </div>

        <div className="dashboard-actions">
          <button
            className="calm-primary-button"
            type="button"
            onClick={() => setCreateOpen(true)}
          >
            <Plus size={17} />
            Créer un casier
          </button>
        </div>
      </header>

      <div className="metrics-grid" data-testid="casier-statistics">
        <div className="metric-block">
          <FolderOpen size={18} />
          <span>Casiers totaux</span>
          <strong>{casiers.length}</strong>
        </div>
        <div className="metric-block">
          <ShieldCheck size={18} />
          <span>Dossiers vierges</span>
          <strong>{viergeCount}</strong>
        </div>
        <div className="metric-block">
          <AlertTriangle size={18} />
          <span>Sous surveillance</span>
          <strong>{watchCount}</strong>
        </div>
      </div>

      <section className="care-hero" data-testid="latest-casier-hero">
        <div>
          <p className="eyebrow">DOSSIER PRIORITAIRE</p>
          <h2>
            {latest
              ? latest.member?.display_name || latest.member?.username
              : "Aucun casier pour le moment."}
          </h2>
          <p>
            {latest
              ? `${statusLabel(latest.status)} · ${latest.last_entry_label || "Ouvrez le dossier pour consulter l’historique."}`
              : "Créez un premier dossier membre pour commencer."}
          </p>
        </div>

        {latest ? (
          <Link to={`/staff/casiers/${latest.id}`} className="care-open">
            <span>Ouvrir le dossier</span>
            <ArrowRight size={20} />
          </Link>
        ) : (
          <ShieldAlert size={32} />
        )}
      </section>

      <div className="dashboard-grid">
        <section className="activity-pane" data-testid="casier-list-panel">
          <div className="section-heading">
            <span>DOSSIERS</span>
            <span className="live-dot">CONFIDENTIEL</span>
          </div>

          {loading ? (
            <p className="dashboard-loading">Chargement…</p>
          ) : casiers.length === 0 ? (
            <div className="dashboard-empty">
              <ShieldAlert size={28} />
              <p>Aucun casier pour le moment.</p>
              <button
                type="button"
                className="calm-primary-button"
                onClick={() => setCreateOpen(true)}
              >
                Créer un premier casier <ArrowRight size={14} />
              </button>
            </div>
          ) : (
            <div className="ticket-table">
              {casiers.map((casier) => (
                <div className="meeting-row-stacked casier-row-stacked" key={casier.id}>
                  <div className="meeting-row-top">
                    <div className="meeting-row-heading casier-row-heading">
                      <div className="casier-row-member">
                        <CasierAvatar member={casier.member} size={30} />
                        <div>
                          <strong>{casier.member?.display_name || casier.member?.username}</strong>
                          <span className="meeting-row-date-inline">@{casier.member?.username}</span>
                        </div>
                      </div>

                      <span className={`status-dot ${statusClass(casier.status)}`}>
                        {statusLabel(casier.status)}
                      </span>
                    </div>
                  </div>

                  <p className="meeting-agenda-full">
                    {casier.last_entry_label || "Aucune note récente sur ce dossier."}
                  </p>

                  <div className="casier-row-meta">
                    <span>{casier.notes_count || 0} note(s)</span>
                    <span>{casier.sanctions_count || 0} sanction(s)</span>
                    <span>{casier.last_entry_at || "Aucune activité récente"}</span>
                  </div>

                  <div className="meeting-row-buttons">
                    <Link to={`/staff/casiers/${casier.id}`} className="btn-consult">
                      Consulter <ArrowRight size={14} />
                    </Link>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>

        <aside className="system-pane">
          <p className="eyebrow">REPÈRES</p>
          <div>
            <span><ShieldCheck size={15} /> Dossiers vierges</span>
            <b>{viergeCount}</b>
          </div>
          <div>
            <span><AlertTriangle size={15} /> Sous surveillance</span>
            <b>{watchCount}</b>
          </div>
          <div>
            <span><ShieldX size={15} /> Sanctionnés / bloqués</span>
            <b>{sanctionCount}</b>
          </div>
          <div>
            <span>Dossier prioritaire</span>
            <strong>{latest ? latest.member?.display_name || latest.member?.username : "—"}</strong>
          </div>
        </aside>
      </div>

      {createOpen && (
        <CreateCasierModal
          onClose={() => setCreateOpen(false)}
          onCreated={() => {
            setCreateOpen(false);
            loadCasiers();
          }}
        />
      )}
    </section>
  );
}
