import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, Calendar, FileText, NotebookPen, Plus, Radio, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { api, getErrorMessage } from "../api/client";

export default function MeetingSummariesPage() {
  const [meetings, setMeetings] = useState([]);
  const [loading, setLoading] = useState(true);

  const loadMeetings = () => {
    setLoading(true);
    api
      .get("/staff/meetings")
      .then((response) => setMeetings(response.data))
      .catch((error) => toast.error(getErrorMessage(error)))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadMeetings();
  }, []);

  const handleDelete = async (meetingId) => {
    if (!window.confirm("Supprimer ce résumé ?")) return;
    try {
      await api.delete(`/staff/meetings/${meetingId}`);
      toast.success("Résumé supprimé.");
      setMeetings((prev) => prev.filter((m) => m.id !== meetingId));
    } catch (error) {
      toast.error(getErrorMessage(error));
    }
  };

  const pendingCount = meetings.filter((m) => m.status === "en_attente_resume").length;
  const doneCount = meetings.filter((m) => m.status === "redige").length;
  const latest = meetings[0];

  return (
    <section className="page-content dashboard-page" data-testid="meetings-page">
      <header className="page-header">
        <div>
          <p className="eyebrow">ESPACE HELPERS</p>
          <h1>Résumés de réunion.</h1>
        </div>
        <div className="dashboard-actions">
          <Link className="calm-primary-button" to="/staff/meetings/new" data-testid="new-meeting-button">
            <Plus size={17} /> Nouveau résumé
          </Link>
        </div>
      </header>

      <div className="metrics-grid" data-testid="meeting-statistics">
        <div className="metric-block">
          <NotebookPen size={18} />
          <span>Résumés totaux</span>
          <strong>{meetings.length}</strong>
        </div>
        <div className="metric-block">
          <FileText size={18} />
          <span>À rédiger</span>
          <strong>{pendingCount}</strong>
        </div>
        <div className="metric-block">
          <Calendar size={18} />
          <span>Rédigés</span>
          <strong>{doneCount}</strong>
        </div>
      </div>

      <section className="care-hero" data-testid="latest-meeting-hero">
        <div>
          <p className="eyebrow">À RÉDIGER</p>
          <h2>{latest ? latest.title : "Aucune réunion pour le moment."}</h2>
          <p>
            {latest
              ? `${new Date(latest.meeting_date).toLocaleDateString("fr-FR", { day: "numeric", month: "long", year: "numeric" })} · ${latest.agenda || "Ouvrez le résumé pour le compléter."}`
              : "Créez un nouveau résumé pour commencer."}
          </p>
        </div>
        {latest ? (
          <Link to={`/staff/meetings/${latest.id}`} className="care-open">
            <span>Ouvrir le résumé</span>
            <ArrowRight size={20} />
          </Link>
        ) : (
          <Radio size={32} />
        )}
      </section>

      <div className="dashboard-grid">
        <section className="activity-pane" data-testid="meetings-list-panel">
          <div className="section-heading">
            <span>RÉUNIONS</span>
            <span className="live-dot">CONFIDENTIEL</span>
          </div>

          {loading ? (
            <p className="dashboard-loading">Chargement…</p>
          ) : meetings.length === 0 ? (
            <div className="dashboard-empty">
              <Radio size={28} />
              <p>Aucun résumé pour le moment.</p>
              <Link to="/staff/meetings/new">
                Créer un premier résumé <ArrowRight size={14} />
              </Link>
            </div>
          ) : (
            
 <div className="ticket-table">
  {meetings.map((meeting) => (
    <div className="meeting-row-stacked" key={meeting.id}>
      <div className="meeting-row-top">
        <div className="meeting-row-heading">
          <strong>{meeting.title}</strong>
          <span className="meeting-row-date-inline">
            {new Date(meeting.meeting_date).toLocaleDateString("fr-FR", {
              day: "numeric",
              month: "long",
              year: "numeric",
            })}
          </span>
        </div>
        <span className={`status-dot ${meeting.status === "redige" ? "active" : "archived"}`}>
          {meeting.status === "redige" ? "RÉDIGÉ" : "À RÉDIGER"}
        </span>
      </div>

      <p className="meeting-agenda-full">{meeting.agenda || "Aucun ordre du jour renseigné."}</p>

      <div className="meeting-row-buttons">
        <Link to={`/staff/meetings/${meeting.id}`} className="btn-consult">
          Consulter <ArrowRight size={14} />
        </Link>
        <button
          type="button"
          className="icon-btn-danger"
          onClick={() => handleDelete(meeting.id)}
        >
          <Trash2 size={15} />
        </button>
      </div>
    </div>
  ))}
</div>
          )}
        </section>

        <aside className="system-pane">
          <p className="eyebrow">REPÈRES</p>
          <div>
            <span><NotebookPen size={15} /> Résumés en attente</span>
            <b>{pendingCount}</b>
          </div>
          <div>
            <span><FileText size={15} /> Résumés rédigés</span>
            <b>{doneCount}</b>
          </div>
          <div>
            <span>Dernière réunion</span>
            <strong>{latest ? latest.title : "—"}</strong>
          </div>
        </aside>
      </div>
    </section>
  );
}
