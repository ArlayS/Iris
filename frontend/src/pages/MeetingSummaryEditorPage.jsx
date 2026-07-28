import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import { ArrowLeft, Calendar, Lock, Pencil, Save, Unlock, X } from "lucide-react";
import { api, getErrorMessage } from "../api/client";
import TiptapSummaryEditor from "../components/TiptapSummaryEditor";
import SummaryReader from "../components/SummaryReader";

export default function MeetingSummaryEditorPage({ isResponsable }) {
  const { meetingId } = useParams();
  const navigate = useNavigate();
  const isNew = meetingId === "new";

  const [title, setTitle] = useState("");
  const [agenda, setAgenda] = useState("");
  const [meetingDate, setMeetingDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [content, setContent] = useState("");
  const [loading, setLoading] = useState(!isNew);
  const [saving, setSaving] = useState(false);
  const [isEditing, setIsEditing] = useState(isNew);
  const [isLocked, setIsLocked] = useState(false);
  const [togglingLock, setTogglingLock] = useState(false);

  useEffect(() => {
    if (isNew) return;
    api
      .get(`/staff/meetings/${meetingId}`)
      .then((response) => {
        setTitle(response.data.title);
        setAgenda(response.data.agenda || "");
        setMeetingDate(response.data.meeting_date);
        setContent(response.data.content_markdown);
        setIsLocked(response.data.is_locked || false);
      })
      .catch((error) => toast.error(getErrorMessage(error)))
      .finally(() => setLoading(false));
  }, [meetingId, isNew]);

  const toggleLock = async () => {
    setTogglingLock(true);
    try {
      const response = await api.post(`/staff/meetings/${meetingId}/lock`);
      setIsLocked(response.data.is_locked);
      setIsEditing(false);
      toast.success(response.data.is_locked ? "Résumé verrouillé." : "Résumé déverrouillé.");
    } catch (error) {
      toast.error(getErrorMessage(error));
    } finally {
      setTogglingLock(false);
    }
  };

  const save = async (event) => {
    event.preventDefault();
    if (isLocked) {
      toast.error("Ce résumé est verrouillé.");
      return;
    }
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
        setIsEditing(false);
      } else {
        await api.put(`/staff/meetings/${meetingId}`, {
          title,
          agenda,
          content_markdown: content,
        });
        toast.success("Résumé mis à jour.");
        setIsEditing(false);
      }
    } catch (error) {
      toast.error(getErrorMessage(error));
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <section className="page-content dashboard-page">
        <p className="dashboard-loading">Chargement…</p>
      </section>
    );
  }

  return (
    <section className="page-content dashboard-page" data-testid="meeting-editor-page">
      <header className="page-header">
        <div>
          <p className="eyebrow">ESPACE STAFF</p>
          <h1>{isNew ? "Nouveau résumé" : title || "Résumé de réunion"}</h1>
        </div>
        <div className="dashboard-actions">
          {isResponsable && !isNew && (
            <button
              type="button"
              className={`btn-ghost ${isLocked ? "btn-locked" : ""}`}
              onClick={toggleLock}
              disabled={togglingLock}
            >
              {isLocked ? <Unlock size={16} /> : <Lock size={16} />}
              {isLocked ? "Déverrouiller" : "Verrouiller"}
            </button>
          )}
          {!isEditing && !isNew && !isLocked && (
            <button type="button" className="calm-primary-button" onClick={() => setIsEditing(true)}>
              <Pencil size={16} /> Éditer
            </button>
          )}
          <button type="button" className="btn-ghost" onClick={() => navigate("/staff/meetings")}>
            <ArrowLeft size={17} /> Retour
          </button>
        </div>
      </header>

      {isLocked && (
        <div className="lock-banner">
          <Lock size={14} /> Ce résumé est verrouillé et ne peut plus être modifié.
        </div>
      )}

      {isEditing ? (
        <form onSubmit={save} className="dashboard-grid">
          <section className="activity-pane">
            <div className="section-heading">
              <span>DÉTAILS</span>
            </div>

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
                <Calendar size={14} /> Date
              </label>
              <input
                id="meeting-date"
                type="date"
                value={meetingDate}
                onChange={(e) => setMeetingDate(e.target.value)}
                required
              />
            </div>

            <div className="summary-field">
              <label htmlFor="agenda">Ordre du jour</label>
              <textarea
                id="agenda"
                value={agenda}
                onChange={(e) => setAgenda(e.target.value)}
                placeholder="Points abordés, décisions à prendre…"
                rows={3}
              />
            </div>

            <div className="section-heading" style={{ marginTop: "20px" }}>
              <span>RÉSUMÉ</span>
            </div>
            <TiptapSummaryEditor
              value={content}
              onChange={setContent}
              placeholder="Rédiger le résumé… (tapez / pour les commandes)"
            />

            <div className="summary-actions" style={{ marginTop: "20px" }}>
              <button
                type="button"
                className="btn-ghost"
                onClick={() => (isNew ? navigate("/staff/meetings") : setIsEditing(false))}
              >
                <X size={16} /> Annuler
              </button>
              <button type="submit" className="calm-primary-button" disabled={saving}>
                <Save size={16} /> {saving ? "Enregistrement…" : "Enregistrer le résumé"}
              </button>
            </div>
          </section>

          <aside className="system-pane">
            <p className="eyebrow">REPÈRES</p>
            <div>
              <span>Statut</span>
              <b>{content.trim() ? "RÉDIGÉ" : "EN ATTENTE"}</b>
            </div>
            <div>
              <span>Date de réunion</span>
              <strong>
                {new Date(meetingDate).toLocaleDateString("fr-FR", {
                  day: "numeric",
                  month: "long",
                  year: "numeric",
                })}
              </strong>
            </div>
          </aside>
        </form>
      ) : (
        <div className="dashboard-grid">
          <section className="activity-pane">
            <div className="section-heading">
              <span>ORDRE DU JOUR</span>
            </div>
            <p className="meeting-agenda-full" style={{ marginBottom: "20px", background: "#FFFFFF" }}>
              {agenda || "Aucun ordre du jour renseigné."}
            </p>

            <div className="section-heading">
              <span>RÉSUMÉ</span>
            </div>
            <SummaryReader content={content} />
          </section>

          <aside className="system-pane">
            <p className="eyebrow">REPÈRES</p>
            <div>
              <span>Statut</span>
              <b>{content.trim() ? "RÉDIGÉ" : "EN ATTENTE"}</b>
            </div>
            <div>
              <span>Date de réunion</span>
              <strong>
                {new Date(meetingDate).toLocaleDateString("fr-FR", {
                  day: "numeric",
                  month: "long",
                  year: "numeric",
                })}
              </strong>
            </div>
          </aside>
        </div>
      )}
    </section>
  );
}
