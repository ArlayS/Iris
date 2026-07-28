import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Clock3, FileText, NotebookPen, Plus, Trash2, X } from "lucide-react";
import { toast } from "sonner";

import { api, getErrorMessage } from "../api/client";
import TiptapSummaryEditor from "../components/TiptapSummaryEditor";


function StatusBadge({ status }) {
  const isPending = status === "en_attente_resume";
  return (
    <span className={`meeting-status-badge ${isPending ? "is-pending" : "is-done"}`}>
      {isPending ? <Clock3 size={13} /> : <FileText size={13} />}
      {isPending ? "En attente de résumé" : "Rédigé"}
    </span>
  );
}

function SummaryModal({ meeting, onClose, onSaved }) {
  const [content, setContent] = useState(meeting.content_markdown || "");
  const [saving, setSaving] = useState(false);

  const save = async () => {
    setSaving(true);
    try {
      const response = await api.put(`/staff/meetings/${meeting.id}`, {
        title: meeting.title,
        agenda: meeting.agenda,
        content_markdown: content,
      });
      onSaved(response.data);
      toast.success("Résumé enregistré.");
      onClose();
    } catch (error) {
      toast.error(getErrorMessage(error));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="meeting-summary-modal-backdrop" onClick={onClose}>
      <div className="meeting-summary-modal" onClick={(event) => event.stopPropagation()}>
        <div className="meeting-summary-modal-header">
          <div>
            <p className="eyebrow">{new Date(meeting.meeting_date).toLocaleDateString("fr-FR", { day: "numeric", month: "long", year: "numeric" })}</p>
            <h2>{meeting.title}</h2>
            {meeting.agenda && <p className="meeting-summary-modal-agenda">{meeting.agenda}</p>}
          </div>
          <button type="button" className="icon-button" onClick={onClose} aria-label="Fermer">
            <X size={18} />
          </button>
        </div>

        <TiptapSummaryEditor value={content} onChange={setContent} autoFocus />

        <div className="meeting-summary-modal-footer">
          <button type="button" className="calm-primary-button is-cancel" onClick={onClose}>
            Annuler
          </button>
          <button type="button" className="calm-primary-button" onClick={save} disabled={saving}>
            {saving ? "Enregistrement…" : "Enregistrer le résumé"}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function MeetingSummariesPage({ isResponsable }) {
  const [meetings, setMeetings] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editingMeeting, setEditingMeeting] = useState(null);

  const loadMeetings = async () => {
    try {
      const response = await api.get("/staff/meetings");
      setMeetings(response.data);
    } catch (error) {
      toast.error(getErrorMessage(error));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadMeetings();
  }, []);

  const removeMeeting = async (meetingId) => {
    try {
      await api.delete(`/staff/meetings/${meetingId}`);
      setMeetings((current) => current.filter((meeting) => meeting.id !== meetingId));
    } catch (error) {
      toast.error(getErrorMessage(error));
    }
  };

  const handleSaved = (updatedMeeting) => {
    setMeetings((current) => current.map((meeting) => (meeting.id === updatedMeeting.id ? updatedMeeting : meeting)));
  };

  return (
    <section className="page-content staff-page" data-testid="meeting-summaries-page">
      <header className="page-header">
        <div>
          <p className="eyebrow">ESPACE STAFF</p>
          <h1>Résumés de réunions</h1>
        </div>
        {isResponsable && (
          <Link className="calm-primary-button" to="/staff/meetings/new" data-testid="add-meeting-button">
            <Plus size={17} /> Ajouter une réunion
          </Link>
        )}
      </header>

      {loading ? (
        <p>Chargement…</p>
      ) : meetings.length === 0 ? (
        <p>Aucun résumé pour l’instant.</p>
      ) : (
        <div className="meeting-list">
          {meetings.map((meeting) => (
            <div className="meeting-row" key={meeting.id}>
              <Link to={`/staff/meetings/${meeting.id}`}>
                <FileText size={16} />
                <span>{meeting.title}</span>
                <small>{new Date(meeting.meeting_date).toLocaleDateString("fr-FR")}</small>
              </Link>
              <StatusBadge status={meeting.status} />
              <button
                type="button"
                className="calm-primary-button is-secondary meeting-row-write-button"
                onClick={() => setEditingMeeting(meeting)}
              >
                <NotebookPen size={15} /> {meeting.status === "en_attente_resume" ? "Rédiger le résumé" : "Modifier le résumé"}
              </button>
              <button type="button" className="icon-button" onClick={() => removeMeeting(meeting.id)} aria-label="Supprimer le résumé">
                <Trash2 size={16} />
              </button>
            </div>
          ))}
        </div>
      )}

      {editingMeeting && (
        <SummaryModal
          meeting={editingMeeting}
          onClose={() => setEditingMeeting(null)}
          onSaved={handleSaved}
        />
      )}
    </section>
  );
}
