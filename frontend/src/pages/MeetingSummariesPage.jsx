import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import { ArrowLeft, Calendar, Save } from "lucide-react";
import { api, getErrorMessage } from "../api/client";
import TiptapSummaryEditor from "../components/TiptapSummaryEditor";

export default function MeetingSummaryEditorPage() {
  const { meetingId } = useParams();
  const navigate = useNavigate();
  const isNew = meetingId === "new";

  const [title, setTitle] = useState("");
  const [agenda, setAgenda] = useState("");
  const [meetingDate, setMeetingDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [content, setContent] = useState("");
  const [loading, setLoading] = useState(!isNew);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (isNew) return;
    api
      .get(`/staff/meetings/${meetingId}`)
      .then((response) => {
        setTitle(response.data.title);
        setAgenda(response.data.agenda || "");
        setMeetingDate(response.data.meeting_date);
        setContent(response.data.content_markdown);
      })
      .catch((error) => toast.error(getErrorMessage(error)))
      .finally(() => setLoading(false));
  }, [meetingId, isNew]);

  const save = async (event) => {
    event.preventDefault();
    setSaving(true);
    try {
      if (isNew) {
        const response = await api.post("/staff/meetings", {
          title,
          agenda,
          content_markdown: content,
          meeting_date: meetingDate,
        });
        toast.success("Résumé créé.");
        navigate(`/staff/meetings/${response.data.id}`, { replace: true });
      } else {
        await api.put(`/staff/meetings/${meetingId}`, {
          title,
          agenda,
          content_markdown: content,
        });
        toast.success("Résumé mis à jour.");
      }
    } catch (error) {
      toast.error(getErrorMessage(error));
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="dashboard-page">
        <p className="dashboard-loading">Chargement…</p>
      </div>
    );
  }

  return (
    <div className="dashboard-page">
      <div className="dashboard-header">
        <div>
          <span className="dashboard-eyebrow">Espace Helpers</span>
          <h1 className="dashboard-title">
            {isNew ? "Nouveau résumé" : title || "Résumé de réunion"}
          </h1>
        </div>
        <button type="button" className="btn-ghost" onClick={() => navigate("/staff/meetings")}>
          <ArrowLeft size={16} />
          Retour aux résumés
        </button>
      </div>

      <form onSubmit={save} className="summary-form">
        <div className="dashboard-card summary-meta-card">
          <div className="summary-field">
            <label htmlFor="title">Titre</label>
            <input
              id="title"
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Titre de la réunion"
              required
            />
          </div>

          <div className="summary-field">
            <label htmlFor="meeting-date">
              <Calendar size={14} />
              Date
            </label>
            <input
              id="meeting-date"
              type="date"
              value={meetingDate}
              onChange={(e) => setMeetingDate(e.target.value)}
              required
            />
          </div>

          <div className="summary-field summary-field-full">
            <label htmlFor="agenda">Ordre du jour</label>
            <textarea
              id="agenda"
              value={agenda}
              onChange={(e) => setAgenda(e.target.value)}
              placeholder="Points abordés, décisions à prendre…"
              rows={2}
            />
          </div>
        </div>

        <div className="dashboard-card summary-editor-card">
          <div className="summary-editor-label">Résumé</div>
          <TiptapSummaryEditor
            value={content}
            onChange={setContent}
            placeholder="Rédiger le résumé… (tapez / pour les commandes)"
          />
        </div>

        <div className="summary-actions">
          <button type="button" className="btn-ghost" onClick={() => navigate("/staff/meetings")}>
            Annuler
          </button>
          <button type="submit" className="btn-primary" disabled={saving}>
            <Save size={16} />
            {saving ? "Enregistrement…" : "Enregistrer le résumé"}
          </button>
        </div>
      </form>
    </div>
  );
}
