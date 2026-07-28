import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Calendar, FileText, NotebookPen, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { api, getErrorMessage } from "../api/client";

function StatusBadge({ status }) {
  const isPending = status === "en_attente_resume";
  return (
    <span className={`status-badge ${isPending ? "status-pending" : "status-done"}`}>
      {isPending ? "À rédiger" : "Rédigé"}
    </span>
  );
}

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

  return (
    <div className="dashboard-page">
      <div className="dashboard-header">
        <div>
          <span className="dashboard-eyebrow">Espace Helpers</span>
          <h1 className="dashboard-title">Résumés de réunion</h1>
        </div>
        <Link to="/staff/meetings/new" className="btn-primary">
          <Plus size={16} />
          Nouveau résumé
        </Link>
      </div>

      <div className="stats-row">
        <div className="dashboard-card stat-card">
          <div className="stat-icon">
            <NotebookPen size={18} />
          </div>
          <div>
            <div className="stat-label">Résumés totaux</div>
            <div className="stat-value">{meetings.length}</div>
          </div>
        </div>

        <div className="dashboard-card stat-card">
          <div className="stat-icon stat-icon-pending">
            <FileText size={18} />
          </div>
          <div>
            <div className="stat-label">À rédiger</div>
            <div className="stat-value">{pendingCount}</div>
          </div>
        </div>

        <div className="dashboard-card stat-card">
          <div className="stat-icon stat-icon-done">
            <Calendar size={18} />
          </div>
          <div>
            <div className="stat-label">Rédigés</div>
            <div className="stat-value">{doneCount}</div>
          </div>
        </div>
      </div>

      <div className="dashboard-card meetings-list-card">
        <div className="meetings-list-header">
          <span>Réunions</span>
        </div>

        {loading ? (
          <p className="dashboard-loading">Chargement…</p>
        ) : meetings.length === 0 ? (
          <p className="dashboard-empty">Aucun résumé pour le moment.</p>
        ) : (
          <div className="meetings-list">
            {meetings.map((meeting) => (
              <Link
                to={`/staff/meetings/${meeting.id}`}
                key={meeting.id}
                className="meeting-row"
              >
                <div className="meeting-row-main">
                  <div className="meeting-row-title">{meeting.title}</div>
                  <div className="meeting-row-date">
                    <Calendar size={13} />
                    {new Date(meeting.meeting_date).toLocaleDateString("fr-FR", {
                      day: "numeric",
                      month: "long",
                      year: "numeric",
                    })}
                  </div>
                </div>

                {meeting.agenda && (
                  <div className="meeting-row-agenda">{meeting.agenda}</div>
                )}

                <div className="meeting-row-actions">
                  <StatusBadge status={meeting.status} />
                  <button
                    type="button"
                    className="icon-btn-danger"
                    onClick={(e) => {
                      e.preventDefault();
                      handleDelete(meeting.id);
                    }}
                  >
                    <Trash2 size={15} />
                  </button>
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
