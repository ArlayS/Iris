import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { FileText, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { api, getErrorMessage } from "../api/client";


export default function MeetingSummariesPage() {
  const [meetings, setMeetings] = useState([]);
  const [loading, setLoading] = useState(true);

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

  return (
    <section className="page-content staff-page" data-testid="meeting-summaries-page">
      <header className="page-header">
        <div>
          <p className="eyebrow">ESPACE STAFF</p>
          <h1>Résumés de réunions</h1>
        </div>
        <Link className="calm-primary-button" to="/staff/meetings/new">
          <Plus size={17} /> Nouveau résumé
        </Link>
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
                <small>{new Date(meeting.created_at).toLocaleDateString("fr-FR")}</small>
              </Link>
              <button type="button" className="icon-button" onClick={() => removeMeeting(meeting.id)} aria-label="Supprimer le résumé">
                <Trash2 size={16} />
              </button>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
